import os

from flask import Flask

from evelogi.extensions import db
from evelogi.settings import config
from evelogi.blueprints.auth import auth_bp


def create_app():
    config_name = os.getenv('FLASK_CONFIG', 'development')

    app = Flask('evelogi')
    app.config.from_object(config[config_name])

    register_logging(app)
    register_extensions(app)
    register_blueprint(app)
    register_shell_context(app)
    register_template_context(app)
    register_errors(app)
    register_commands(app)
    return app


def register_logging(app):
    pass


def register_extensions(app):
    db.init_app(app)


def register_blueprint(app):
    app.register_blueprint(auth_bp)


def register_shell_context(app):
    pass


def register_template_context(app):
    pass


def register_errors(app):
    pass


def register_commands(app):
    pass
