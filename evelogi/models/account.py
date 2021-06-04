import os
import base64
import requests

from flask import current_app, abort
from flask_login import UserMixin, AnonymousUserMixin

from evelogi.extensions import db, cache
from evelogi.utils import get_esi_data, validate_eve_jwt

class Guest(AnonymousUserMixin):
    def can(self, permission_name):
        return False

class User(db.Model, UserMixin):
    id = db.Column(db.Integer, primary_key=True)
    characters = db.relationship(
        'Character_', back_populates='user', cascade='all, delete-orphan')
    role_id = db.Column(db.Integer, db.ForeignKey("role.id"))
    role = db.relationship('Role', back_populates='users')

    def __init__(self):
        super().__init__()
        self.set_role()
    
    def set_role(self):
        if self.role is None:
            self.role = Role.query.filter_by(name='Free').first()
        db.session.commit()

    def can(self, permission_name):
        permission = Permission.query.filter_by(name=permission_name).first()
        return permission is not None and self.role is not None and permission in self.role.permissions

    def get_orders(self):
        """Retrive orders of a user.
        """
        characters = self.characters
        data = []
        for character in characters:
            data += character.get_orders()
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

    def get_orders_count(self):
        return len(self.get_orders())

    def get_orders(self):
        """Retrive orders of a character.
        """
        access_token = self.get_access_token()
        path = "https://esi.evetech.net/latest/characters/" + \
            str(self.character_id) + \
            "/orders/?datasource=tranquility&token=" + access_token
        data = get_esi_data(path)
        return data

    def get_wallet(self):
        access_token = self.get_access_token()
        path = 'https://esi.evetech.net/latest/characters/' + \
            str(self.character_id) + \
            '/wallet/?datasource=tranquility&token=' + access_token
        data = get_esi_data(path)
        current_app.logger.debug(data)
        return data

    @cache.memoize(600)
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
                "\nSSO response JSON is: {}".format(res.text))
            abort(400)
            


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
        try:
            return data[field]
        except KeyError as e:
            current_app.logger.error(e)

    def get_structure_orders(self):
        """Retrive orders in a structure.
        """
        path = "https://esi.evetech.net/latest/markets/structures/" + \
            str(self.structure_id) + "/?datasource=tranquility&token=" + \
            self.character.get_access_token()
        return get_esi_data(path)

roles_permissions = db.Table("roles_permissions",
                            db.Column("role_id", db.Integer, db.ForeignKey("role.id")),
                            db.Column("permission_id", db.Integer, db.ForeignKey("permission.id")))

class Permission(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True)
    roles = db.relationship("Role", secondary=roles_permissions, back_populates='permissions')

class Role(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(30), unique=True)
    permissions = db.relationship("Permission", secondary=roles_permissions, back_populates='roles')
    users = db.relationship("User", back_populates='role')

    @staticmethod
    def init_role():
        roles_permissions_map = {
            "Free": ["CHECK"],
            "Trade": ["CHECK", "TRADE"],
            "Industry": ["CHECK", "INDUSTRY"],
            "All": ["CHECK", "TRADE", "INDUSTRY"],
            "Admin": ["CHECK", "TRADE", "INDUSTRY", "ADMIN"]
        }

        for role_name in roles_permissions_map:
            role = Role.query.filter_by(name=role_name).first()
            if role is None:
                role = Role(name=role_name)
                db.session.add(role)
            role.permissions = []
            for permission_name in roles_permissions_map[role_name]:
                permission = Permission.query.filter_by(name=permission_name).first()
                if permission is None:
                    permission = Permission(name=permission_name)
                    db.session.add(permission)
                role.permissions.append(permission)
        db.session.commit()