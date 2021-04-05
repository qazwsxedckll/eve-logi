import os
import base64
import requests
import time

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError, JWTClaimsError

from flask import Blueprint
from flask.templating import render_template
from flask import request, current_app, abort, redirect, url_for, session

from flask_login import login_user, current_user, logout_user, login_required

from evelogi.models.auth import RefreshToken, Character_, User
from evelogi.extensions import db
from evelogi.utils import redirect_back

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/login/')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('main.index'))

    state = request.args.get('state')
    if state is None or state != current_app.config['STATE']:
        current_app.logger.warning('state from eve:{} does not match state sent:{}'.format(state, current_app.config['STATE']))
        abort(400)
    
    code = request.args.get('code')
    client_id = current_app.config['CLIENT_ID']
    eve_app_secret = os.environ.get('EVELOGI_SECRET_KEY')
    user_pass = "{}:{}".format(client_id, eve_app_secret)
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
        access_token = data['access_token'] 
        jwt = validate_eve_jwt(access_token)

        character_id = jwt["sub"].split(":")[2]
        character_name = jwt["name"]
        owner_hash = jwt['owner']
        character = Character_.query.filter_by(name=character_name).first()
        if character:
            if character.user:
                if character.owner_hash != owner_hash:
                    db.session.delete(character)
                    db.session.commit()
                    current_app.logger.warning('owner has changed.')
                    abort(400)
                else:
                    login_user(character.user, remember=True)
            else:
                db.session.delete(character)
                db.session.commit()
                current_app.logger.error('orphan character, something need to be fixed')
                abort(400)
        else:
            user = User()
            character = Character_(name=character_name, character_id=character_id, owner_hash=owner_hash)
            user.characters.append(character)

            refresh_token = RefreshToken(token=data['refresh_token'])
            character.refresh_tokens.append(refresh_token)

            db.session.add(user)
            db.session.add(character)
            db.session.add(refresh_token)
            db.session.commit()
            login_user(user)
            current_app.logger.info('New user, user id: {}, character name: {}'.format(user.id, character.name))

        
        current_app.logger.info('user:{} logined'.format(current_user.id))

        session['access_token'] = access_token
        session['access_token_expires'] = int(time.time()) + data['expires_in']
        session['username'] = character_name

        # headers = {
        #     "Authorization": "Bearer {}".format(access_token)
        # }

        return redirect_back()
    else:
        current_app.logger.warning("\nSSO response JSON is: {}".format(res.json()))
        abort(res.status_code)

@auth_bp.route('/logout/')
@login_required
def logout():
    logout_user()
    return redirect_back()

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
        current_app.logger.warning("The JWT token has expired: {}".format(str(e)))
        abort(400)
    except JWTError as e:
        current_app.logger.warning("The JWT signature was invalid: {}".format(str(e)))
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
