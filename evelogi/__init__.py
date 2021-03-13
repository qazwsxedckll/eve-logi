import os

from urllib.parse import urlencode

from flask import Flask

from evelogi.extensions import db
from evelogi.settings import config
from evelogi.blueprints.auth import auth_bp
from evelogi.blueprints.main import main_bp


def create_app():
    config_name = os.getenv('FLASK_CONFIG', 'development')

    app = Flask('evelogi')
    app.config.from_object(config[config_name])

    register_logging(app)
    register_extensions(app)
    register_blueprints(app)
    register_shell_context(app)
    register_template_context(app)
    register_errors(app)
    register_commands(app)

    @app.template_global()
    def eve_oauth_url():
        params = {
            'response_type': app.config['RESPONSE_TYPE'],
            'redirect_uri': app.config['REDIRECT_URL'],
            'client_id': app.config['CLIENT_ID'],
            'scope': app.config['SCOPE'],
            'state': app.config['STATE'],
        }

        return str(app.config['OAUTH_URL'] + urlencode(params))

    return app


def register_logging(app):
    pass


def register_extensions(app):
    db.init_app(app)


def register_blueprints(app):
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)


def register_shell_context(app):
    pass


def register_template_context(app):
    pass


def register_errors(app):
    pass


def register_commands(app):
    pass
