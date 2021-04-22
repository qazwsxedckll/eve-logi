from flask import Blueprint
from flask import render_template

from flask_login import login_required, current_user

from evelogi.models.account import Structure

main_bp = Blueprint('main', __name__) 

@main_bp.route('/')
def index():
    return render_template('main/index.html')

@main_bp.route('/account')
@login_required
def account():
    structures = [
        structure for character in current_user.characters for structure in character.structures]
    return render_template('main/account.html', structures=structures)
