import os
import logging
import time

from logging.handlers import RotatingFileHandler
from urllib.parse import urlencode

import click
from flask import Flask
from flask.logging import default_handler

from evelogi.extensions import db, migrate, login_manager
from evelogi.settings import config
from evelogi.blueprints.auth import auth_bp
from evelogi.blueprints.main import main_bp
from evelogi.models.auth import User, Character_, RefreshToken


def create_app():
    config_name = os.getenv('FLASK_CONFIG', 'development')

    app = Flask('evelogi')
    app.config.from_object(config[config_name])

    register_logger(app)
    register_extensions(app)
    register_blueprints(app)
    register_shell_context(app)
    register_template_context(app)
    register_errors(app)
    register_commands(app)

    return app


def register_logger(app):
    formatter = logging.Formatter('%(asctime)s %(levelname)s %(message)s - %(filename)s:%(lineno)s')
    
    default_handler.setFormatter(formatter)

    # log to file
    if not app.debug:
        file_handler = RotatingFileHandler('logs/{}.log'.format(time.strftime('%Y-%m-%d %H:%M:%S',time.localtime())), maxBytes=10*1024*1024, backupCount=10)
        file_handler.setFormatter(formatter)
        file_handler.setLevel(logging.INFO)

        app.logger.setLevel(logging.INFO)
        app.logger.removeHandler(default_handler)
        app.logger.addHandler(file_handler)

def register_extensions(app):
    db.init_app(app)
    migrate.init_app(app, db)
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"


def register_blueprints(app):
    app.register_blueprint(main_bp)
    app.register_blueprint(auth_bp)


def register_shell_context(app):
    pass


def register_template_context(app):

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


def register_errors(app):
    pass


def register_commands(app):
    @app.cli.command()
    @click.option('--drop', is_flag=True, help='Create after drop.')
    def initdb(drop):
        """Initialize the database."""
        if drop:
            click.confirm('This operation will delete the database, do you want to continue?', abort=True)
            db.drop_all()
            click.echo('Drop tables.')
        db.create_all()
        click.echo('Initialized database.')