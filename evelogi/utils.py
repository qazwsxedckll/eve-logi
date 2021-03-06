from asyncio import tasks
import requests
import asyncio
import aiohttp
from urllib.parse import urlparse, urljoin, urlencode
from functools import wraps

import redis
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError, JWTClaimsError

from flask import request, redirect, url_for, current_app, session, g, abort
from flask_login import current_user

from evelogi.exceptions import GetESIDataError, GetESIDataNotFound

def permission_required(permission_name):
    def decorator(func):
        @wraps(func)
        def decorated_function(*args, **kwargs):
            if not current_user.can(permission_name):
                abort(403)
            return func(*args)
        return decorated_function
    return decorator

def get_redis():
    if 'redis' not in g:
        g.redis = redis.StrictRedis('localhost', 6379, charset="utf-8", decode_responses=True)
    return g.redis

def is_safe_url(target):
    ref_url = urlparse(request.host_url)
    test_url = urlparse(urljoin(request.host_url, target))
    return test_url.scheme in ('http', 'https') and ref_url.netloc == test_url.netloc

def redirect_back(default='main.index', **kwargs):
    for target in request.args.get('next'), request.referrer:
        if not target:
            continue
        if is_safe_url(target):
            return redirect(target)
    return redirect(url_for(default, **kwargs))

def eve_oauth_url():
    params = {
        'response_type': current_app.config['RESPONSE_TYPE'],
        'redirect_uri': current_app.config['REDIRECT_URL'],
        'client_id': current_app.config['CLIENT_ID'],
        'scope': current_app.config['SCOPE'],
        'state': current_app.config['STATE'],
    }

    return str(current_app.config['OAUTH_URL'] + urlencode(params))

def validate_eve_jwt(jwt_token):
    """Validate a JWT token retrieved from the EVE SSO.
    Args:
        jwt_token: A JWT token originating from the EVE SSO
    Returns
        dict: The contents of the validated JWT token if there are no
              validation errors
    """

    jwk_set_url = "https://login.eveonline.com/oauth/jwks"

    res = requests.get(jwk_set_url)
    res.raise_for_status()

    data = res.json()

    try:
        jwk_sets = data["keys"]
    except KeyError as e:
        current_app.logger.warning("Something went wrong when retrieving the JWK set. The returned "
                                   "payload did not have the expected key {}. \nPayload returned "
                                   "from the SSO looks like: {}".format(e, data))
        raise

    jwk_set = next((item for item in jwk_sets if item["alg"] == "RS256"))

    try:
        return jwt.decode(
            jwt_token,
            jwk_set,
            algorithms=jwk_set["alg"],
            issuer="login.eveonline.com"
        )
    except ExpiredSignatureError as e:
        current_app.logger.warning(
            "The JWT token has expired: {}".format(str(e)))
        raise
    except JWTError as e:
        current_app.logger.warning(
            "The JWT signature was invalid: {}".format(str(e)))
        raise
    except JWTClaimsError as e:
        try:
            return jwt.decode(
                jwt_token,
                jwk_set,
                algorithms=jwk_set["alg"],
                issuer="https://login.eveonline.com"
            )
        except JWTClaimsError as e:
            current_app.logger.warning("The issuer claim was not from login.eveonline.com or "
                                       "https://login.eveonline.com: {}".format(str(e)))
            raise

def get_esi_data(path):
    res = requests.get(path)
    if res.status_code == 200:
        data = res.json()

        pages = res.headers.get("x-pages")
        if not pages:
            return data
        
        current_app.logger.info("user: {}, x-pages: {}".format(current_user.id ,pages))
        paths = []
        for i in range(2, int(pages) + 1):
            paths.append(path + "&page={}".format(i))
        results = asyncio.run(gather_esi_requests(paths))
        for result in results:
            data += result
        current_app.logger.info("user: {}, finished".format(current_user.id))
        return data
    else:
        current_app.logger.warning(
            "\nSSO response JSON is: {}".format(res.json()))
        raise GetESIDataError(res.json())

async def gather_esi_requests(paths):
    async with aiohttp.ClientSession() as session:
        tasks = []
        for path in paths:
            tasks.append(async_get_esi_data(path, session))
        results = await asyncio.gather(*tasks)
        return results

async def async_get_esi_data(path, session):
    async with session.get(path) as resp:
        for i in range(3):
            try:
                result = await resp.json(content_type=None)
            except Exception as e:
                current_app.logger.warning('status code: {}, message: {}, attempt: {}'.format(resp.status, e, i+1))
            else:
                if resp.status == 200:
                    return result
                elif resp.status == 404:
                    raise GetESIDataNotFound
                else:
                    current_app.logger.warning(
                        "status: {} response: {}, attempt: {}".format(resp.status, result, i+1))
        raise GetESIDataError