import os
import base64
import requests

from flask import current_app, abort
from flask_login import UserMixin

from evelogi.extensions import db

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True) 
    subscription = db.Column(db.Integer, default=0)
    characters = db.relationship('Character_', back_populates='user', cascade='all, delete-orphan')

# use character as table name will cause unknown error in mysql
class Character_(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    character_id = db.Column(db.Integer, unique=True, nullable=False)
    owner_hash = db.Column(db.String(128), unique=True, nullable=False)

    user_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    user = db.relationship('User', back_populates="characters")

    refresh_tokens = db.relationship('RefreshToken', cascade='all, delete-orphan')

    structures = db.relationship('Structure',
                                 back_populates='character',
                                 cascade='all, delete-orphan')

    def get_access_token(self):
        form_values = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_tokens[0].token
        }

        client_id = current_app.config['CLIENT_ID']
        eve_app_secret = os.environ.get('EVELOGI_SECRET_KEY')
        user_pass = "{}:{}".format(client_id, eve_app_secret)
        basic_auth = base64.urlsafe_b64encode(user_pass.encode('utf-8')).decode()
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
            return data['access_token']
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