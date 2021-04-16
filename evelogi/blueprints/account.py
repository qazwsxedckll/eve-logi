import os
import base64
import requests
import time

from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError, JWTClaimsError

from flask import Blueprint
from flask.templating import render_template
from flask import request, current_app, abort, redirect, url_for

from flask_login import login_user, current_user, logout_user, login_required

from evelogi.models.account import RefreshToken, Character_, User, Structure
from evelogi.extensions import db
from evelogi.utils import redirect_back
from evelogi.forms.account import StructureForm

account_bp = Blueprint('account', __name__)


@account_bp.route('/login/')
def login():
    state = request.args.get('state')
    if state is None or state != current_app.config['STATE']:
        current_app.logger.warning('state from eve:{} does not match state sent:{}'.format(
            state, current_app.config['STATE']))
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
            if current_user.is_authenticated:
                # add a existing character
                redirect(url_for('main.account'))
            else:
                # login a existing user
                if character.user:
                    if character.owner_hash != owner_hash:
                        db.session.delete(character)
                        db.session.commit()
                        current_app.logger.warning('owner has changed.')
                        abort(400)
                    else:
                        login_user(character.user)
                        current_app.logger.info(
                            'user:{} logined'.format(current_user.id))
                else:
                    db.session.delete(character)
                    db.session.commit()
                    current_app.logger.error(
                        'orphan character, something need to be fixed')
                    abort(400)
        else:
            character = Character_(
                name=character_name, character_id=character_id, owner_hash=owner_hash)
            refresh_token = RefreshToken(token=data['refresh_token'])
            character.refresh_tokens.append(refresh_token)
            db.session.add(character)
            db.session.add(refresh_token)

            if current_user.is_authenticated:
                # add character
                current_user.characters.append(character)
                db.session.commit()
                current_app.logger.info(
                    'Add character, user id: {}, character name: {}'.format(current_user.id, character.name))
            else:
                # create a new user
                user = User()
                user.characters.append(character)

                db.session.add(user)
                db.session.commit()
                login_user(user)
                current_app.logger.info(
                    'New user, user id: {}, character name: {}'.format(user.id, character.name))

        return redirect_back()
    else:
        current_app.logger.warning(
            "\nSSO response JSON is: {}".format(res.json()))
        abort(res.status_code)


@account_bp.route('/logout/')
@login_required
def logout():
    logout_user()
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


@account_bp.route('/structure/add', methods=['GET', 'POST'])
@login_required
def add_structure():
    characters = current_user.characters
    choices = [(character.id, character.name)
               for character in characters]
    form = StructureForm()
    form.character_id.choices = choices
    if form.validate_on_submit():
        structure_id = form.structure_id.data
        name = form.name.data
        jita_to_fee = form.jita_to_fee.data
        jita_to_collateral = form.jita_to_collateral.data
        to_jita_fee = form.to_jita_fee.data
        to_jita_collateral = form.to_jita_collateral.data
        sales_tax = form.sales_tax.data
        brokers_fee = form.brokers_fee.data
        character_id = form.character_id.data
        character = Character_.query.get(character_id)
        if character is None:
            current_app.logger.error('character with id {} not found.'.format(character_id))
            abort(400)
        structure = Structure(structure_id=structure_id,
                              name=name,
                              jita_to_fee=jita_to_fee,
                              jita_to_collateral=jita_to_collateral,
                              to_jita_fee=to_jita_fee,
                              to_jita_collateral=to_jita_collateral,
                              sales_tax=sales_tax,
                              brokers_fee=brokers_fee,
                              character=character
                              )
        db.session.add(structure)
        db.session.commit()
        return redirect(url_for('main.account'))
    return render_template('main/structure.html', form=form)
