import requests
from urllib.parse import urlparse, urljoin, urlencode

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError, JWTClaimsError

from flask import request, redirect, url_for, current_app, abort

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
        
        current_app.logger.debug("x-pages: {}".format(pages))
        for i in range(1, int(pages) + 1):
            res = requests.get(path + "&page={}".format(i))
            if res.status_code == 200:
                data += res.json()
                current_app.logger.debug("{}".format(i))
            else:
                current_app.logger.warning(
                    "\nSSO response JSON is: {}".format(res.json()))
                abort(res.status_code)
        return data
    else:
        current_app.logger.warning(
            "\nSSO response JSON is: {}".format(res.json()))
        abort(res.status_code)