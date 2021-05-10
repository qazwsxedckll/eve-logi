import os
import base64
import requests
import time

from flask import Blueprint, flash, session
from flask.templating import render_template
from flask import request, current_app, redirect, url_for

from flask_login import login_user, current_user, logout_user, login_required

from evelogi.models.account import RefreshToken, Character_, User, Structure
from evelogi.extensions import db
from evelogi.utils import redirect_back, validate_eve_jwt
from evelogi.forms.account import StructureForm
from evelogi.exceptions import GetESIDataError

account_bp = Blueprint('account', __name__)


@account_bp.route('/login/')
def login():
    state = request.args.get('state')
    if state is None or state != current_app.config.get('STATE'):
        current_app.logger.warning('state from eve:{} does not match state sent:{}'.format(
            state, current_app.config.get('STATE')))
        flash('state error')
        return url_for('main.index')

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
        try:
            jwt = validate_eve_jwt(access_token)
        except Exception as e:
            flash('validate jwt error')
            return url_for('main.index')

        character_id = jwt["sub"].split(":")[2]
        character_name = jwt["name"]
        owner_hash = jwt['owner']
        character = Character_.query.filter_by(name=character_name).first()
        if character:
            if current_user.is_authenticated:
                # add a existing character
                if character not in current_user.characters:
                    flash('Character has been bound.')
                return redirect(url_for('main.account'))
            else:
                # login a existing user
                if character.user:
                    if character.owner_hash != owner_hash:
                        db.session.delete(character)
                        db.session.commit()
                        current_app.logger.warning('owner has changed.')
                        flash('owner has changed.')
                        return url_for('main.index')
                    else:
                        login_user(character.user)
                        current_app.logger.info(
                            'user:{} logined'.format(current_user.id))
                else:
                    db.session.delete(character)
                    db.session.commit()
                    current_app.logger.error(
                        'orphan character, something need to be fixed')
                    flash('Error')
                    return url_for('main.index')
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
            "\nSSO response JSON is: {}, code: {}".format(res.text, res.status_code))
        return url_for('main.index')


@account_bp.route('/logout/')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))


@account_bp.route('/character/del/<int:id>', methods=['POST'])
@login_required
def del_character(id):
    character = Character_.query.get_or_404(id)
    db.session.commit()
    db.session.delete(character)
    return redirect(url_for('main.account'))


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

        structures = [
            structure for character in current_user.characters for structure in character.structures]
        for item in structures:
            if item.structure_id == structure_id:
                flash('Add structure failed. Sturcture already exists.')
                return render_template('main/structure.html', form=form)

        name = form.name.data
        jita_to_fee = form.jita_to_fee.data
        jita_to_collateral = form.jita_to_collateral.data
        to_jita_fee = form.to_jita_fee.data
        to_jita_collateral = form.to_jita_collateral.data
        sales_tax = form.sales_tax.data
        brokers_fee = form.brokers_fee.data
        character_id = form.character_id.data
        character = Character_.query.get_or_404(character_id)
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
        try:
            structure.get_structure_data('name')
        except GetESIDataError as e:
            current_app.logger.debug(e)
            flash('Add structure failed, Check structure id or access control.')
            return render_template('main/structure.html', form=form)
        db.session.add(structure)
        db.session.commit()
        return redirect(url_for('main.account'))
    return render_template('main/structure.html', form=form)


@account_bp.route('/structure/edit/<int:id>', methods=['GET', 'POST'])
@login_required
def edit_structure(id):
    structure = Structure.query.get_or_404(id)
    characters = current_user.characters
    choices = [(character.id, character.name)
               for character in characters]
    form = StructureForm()
    form.character_id.choices = choices
    if form.validate_on_submit():
        former_structure_id = structure.structure_id

        if structure.structure_id != form.structure_id.data:
            structures = [
                structure for character in current_user.characters for structure in character.structures]

            for item in structures:
                if item.structure_id == form.structure_id.data:
                    form.structure_id.data = structure.structure_id
                    flash('Edit structure failed. Sturcture already exists.')
                    return render_template('main/structure.html', form=form)

        structure.structure_id = form.structure_id.data
        structure.name = form.name.data
        structure.jita_to_fee = form.jita_to_fee.data
        structure.jita_to_collateral = form.jita_to_collateral.data
        structure.to_jita_fee = form.to_jita_fee.data
        structure.to_jita_collateral = form.to_jita_collateral.data
        structure.sales_tax = form.sales_tax.data
        structure.brokers_fee = form.brokers_fee.data
        structure.character_id = form.character_id.data

        try:
            structure.get_structure_data('name')
        except GetESIDataError as e:
            form.structure_id.data = former_structure_id
            flash('Edit structure failed, Check structure id or access control.')
            return render_template('main/structure.html', form=form)
        db.session.commit()
        return redirect(url_for('main.account'))

    form.structure_id.data = structure.structure_id
    form.name.data = structure.name
    form.jita_to_fee.data = structure.jita_to_fee
    form.jita_to_collateral.data = structure.jita_to_collateral
    form.to_jita_fee.data = structure.to_jita_fee
    form.to_jita_collateral.data = structure.to_jita_collateral
    form.sales_tax.data = structure.sales_tax
    form.brokers_fee.data = structure.brokers_fee
    form.character_id.data = structure.character_id
    return render_template('main/structure.html', form=form)


@account_bp.route('/structure/del/<int:id>', methods=['POST'])
@login_required
def del_structure(id):
    structure = Structure.query.get_or_404(id)
    db.session.delete(structure)
    db.session.commit()
    return redirect(url_for('main.account'))
