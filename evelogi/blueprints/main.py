from flask import Blueprint
from flask import render_template, session
from flask.globals import current_app

from flask_login import login_required

main_bp = Blueprint('main', __name__) 

@main_bp.route('/')
def index():
    return render_template('main/index.html')

@main_bp.route('/account')
@login_required
def account():
    return render_template('main/account.html')
