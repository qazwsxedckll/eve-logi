from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_caching import Cache

db = SQLAlchemy()
migrate = Migrate()
login_manager = LoginManager()
cache = Cache()

from evelogi.models.auth import User

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    return user