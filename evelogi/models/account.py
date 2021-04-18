import os
import base64
import requests

from flask import current_app, abort
from flask_login import UserMixin

from evelogi.extensions import db, cache
from evelogi.utils import get_esi_data, validate_eve_jwt


class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    subscription = db.Column(db.Integer, default=0)
    characters = db.relationship(
        'Character_', back_populates='user', cascade='all, delete-orphan')

    def orders(self):
        """Retrive orders of a user.
        """
        characters = self.characters
        data = []
        for character in characters:
            data.append(character.orders())
        return data

# use character as table name will cause unknown error in mysql


class Character_(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    character_id = db.Column(db.Integer, unique=True, nullable=False)
    owner_hash = db.Column(db.String(128), unique=True, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', back_populates="characters")

    refresh_tokens = db.relationship(
        'RefreshToken', cascade='all, delete-orphan')

    structures = db.relationship('Structure',
                                 back_populates='character',
                                 cascade='all, delete-orphan')

    def orders(self):
        """Retrive orders of a character.
        """
        access_token = self.get_access_token()
        path = "https://esi.evetech.net/latest/characters/" + \
            str(self.character_id) + \
            "/orders/?datasource=tranquility&token=" + access_token
        data = []

        res = requests.get(path)

        if res.status_code == 200:
            data.append(res.json())

            pages = res.headers.get("x-pages")
            if not pages:
                return data

            current_app.logger.debug("x-pages: {}".format(pages))
            for i in range(2, int(pages) + 1):
                res = requests.get(path + "&page={}".format(i))
                if res.status_code == 200:
                    data.append(res.json())
                    current_app.logger.debug("{}".format(i))
                else:
                    current_app.logger.warning(
                        "\nSSO response JSON is: {}".format(res.json()))
                    abort(res.status_code)
        else:
            current_app.logger.warning(
                "\nSSO response JSON is: {}".format(res.json()))
            abort(res.status_code)
        return data

    @cache.memoize(1000)
    def get_access_token(self):
        form_values = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_tokens[0].token
        }

        client_id = current_app.config['CLIENT_ID']
        eve_app_secret = os.environ.get('EVELOGI_SECRET_KEY')
        user_pass = "{}:{}".format(client_id, eve_app_secret)
        basic_auth = base64.urlsafe_b64encode(
            user_pass.encode('utf-8')).decode()
        auth_header = "Basic {}".format(basic_auth)

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
            validate_eve_jwt(access_token)
            return access_token
        else:
            current_app.logger.warning(
                "\nSSO response JSON is: {}".format(res.json()))
            abort(res.status_code)


class RefreshToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(256), unique=True)
    scope = db.Column(db.Text)

    character_id = db.Column(db.Integer, db.ForeignKey('character_.id'))


class Structure(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    structure_id = db.Column(db.String(32), nullable=False)
    name = db.Column(db.String(20), nullable=False)
    jita_to_fee = db.Column(db.Integer, default=0)
    jita_to_collateral = db.Column(db.Float, default=0)
    to_jita_fee = db.Column(db.Integer, default=0)
    to_jita_collateral = db.Column(db.Float, default=0)
    sales_tax = db.Column(db.Float, default=0)
    brokers_fee = db.Column(db.Float, default=0)

    character_id = db.Column(db.Integer, db.ForeignKey('character_.id'))
    character = db.relationship('Character_', back_populates='structures')

    @cache.memoize(86400)
    def _get_structure_data(self):
        path = 'https://esi.evetech.net/latest/universe/structures/' + \
            str(self.structure_id) + '/?datasource=tranquility&token=' + \
            self.character.get_access_token()
        data = get_esi_data(path)
        return data

    def get_structure_data(self, field):
        data = self._get_structure_data()
        return data[field]

    def get_structure_orders(self):
        """Retrive orders in a structure.
        """
        path = "https://esi.evetech.net/latest/markets/structures/" + \
            str(self.structure_id) + "/?datasource=tranquility&token=" + \
            self.character.get_access_token()
        return get_esi_data(path)
