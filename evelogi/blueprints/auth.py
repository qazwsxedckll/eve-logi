import os
import base64
import requests

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError, JWTClaimsError

from flask import Blueprint
from flask.templating import render_template
from flask import request, current_app, abort, redirect, url_for, session


auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login/')
def login():
    state = request.args.get('state')
    if state is None or state != current_app.config['STATE']:
        abort(400)
    
    code = request.args.get('code')
    client_id = current_app.config["CLIENT_ID"]
    app_secret = os.environ.get("EVELOGI_SECRET_KEY")
    user_pass = "{}:{}".format(client_id, app_secret)
    basic_auth = base64.urlsafe_b64encode(user_pass.encode('utf-8')).decode()
    auth_header = "Basic {}".format(basic_auth)

    form_values = {
        "grant_type": "authorization_code",
        "code": code,
    }

    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Host": "login.eveonline.com",
        "Authorization": auth_header
    }

    res = requests.post(
        "https://login.eveonline.com/v2/oauth/token",
        data=form_values,
        headers=headers,
    )

    if res.status_code == 200:
        data = res.json()
        access_token = data["access_token"]

        jwt = validate_eve_jwt(access_token)
        character_id = jwt["sub"].split(":")[2]
        character_name = jwt["name"]

        headers = {
            "Authorization": "Bearer {}".format(access_token)
        }

        session['username'] = character_name

        print(data)
        print('---------------')
        print(jwt)
    else:
        print("\nSSO response JSON is: {}".format(res.json()))
        abort(res.status_code)

    return redirect(url_for('main.index'))

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
        print("Something went wrong when retrieving the JWK set. The returned "
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
        print("The JWT token has expired: {}")
        abort(400)
    except JWTError as e:
        print("The JWT signature was invalid: {}").format(str(e))
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
            print("The issuer claim was not from login.eveonline.com or "
                  "https://login.eveonline.com: {}".format(str(e)))
            abort(400)
