from flask import Blueprint
from flask import render_template, session
from flask.globals import current_app

main_bp = Blueprint('main', __name__) 

@main_bp.route('/')
def index():
    usename = session.get('username', None)
    return render_template('main/index.html', username=usename)
