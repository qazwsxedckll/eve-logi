from asyncio import tasks
import requests
import secrets
import asyncio
import aiohttp
from urllib.parse import urlparse, urljoin, urlencode

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError, JWTClaimsError

from flask import request, redirect, url_for, current_app, abort, session
from flask_login import current_user

from evelogi.exceptions import GetESIDataError, GetESIDataNotFound

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
    session['state'] = secrets.token_urlsafe(8)
    params = {
        'response_type': current_app.config['RESPONSE_TYPE'],
        'redirect_uri': current_app.config['REDIRECT_URL'],
        'client_id': current_app.config['CLIENT_ID'],
        'scope': current_app.config['SCOPE'],
        'state': session['state'],
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
        abort(400)

    jwk_set = next((item for item in jwk_sets if item["alg"] == "RS256"))

    try:
        return jwt.decode(
            jwt_token,
            jwk_set,
            algorithms=jwk_set["alg"],
            issuer="login.eveonline.com"
        )
    except ExpiredSignatureError:
        current_app.logger.warning(
            "The JWT token has expired: {}".format(str(e)))
        abort(400)
    except JWTError as e:
        current_app.logger.warning(
            "The JWT signature was invalid: {}".format(str(e)))
        abort(400)
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
            abort(400)

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
                if resp.status == 200:
                    return result
                else:
                    current_app.logger.warning(
                        "SSO response JSON is: {}, attempt: {}".format(result, i+1))
            except Exception as e:
                current_app.logger.warning('status code: {}, attempt: {}'.format(resp.status, i+1))
                current_app.logger.warning(e)
        raise GetESIDataError