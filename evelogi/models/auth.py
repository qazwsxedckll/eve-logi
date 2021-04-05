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

class RefreshToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(256), unique=True)
    scope = db.Column(db.Text)

    character_id = db.Column(db.Integer, db.ForeignKey('character_.id'))