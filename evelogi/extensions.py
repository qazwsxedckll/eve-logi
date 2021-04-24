from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_caching import Cache
from sqlalchemy.ext.automap import automap_base
from flask_wtf.csrf import CSRFProtect
from flask_debugtoolbar import DebugToolbarExtension

db = SQLAlchemy()
Base = automap_base()
migrate = Migrate()
login_manager = LoginManager()
cache = Cache()
csrf = CSRFProtect()
toolbar = DebugToolbarExtension()

from evelogi.models.account import User

@login_manager.user_loader
def load_user(user_id):
    user = User.query.get(int(user_id))
    return user