from flask import Blueprint
from flask.templating import render_template

auth_bp = Blueprint('auth', __name__)

@auth_bp.route('/')
def index():
    return render_template('auth/index.html')