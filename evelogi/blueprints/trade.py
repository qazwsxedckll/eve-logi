from flask import Blueprint, render_template

from flask_login import login_required, current_user
from flask.globals import current_app

from evelogi.utils import redirect_back
from evelogi.models.trade import jita_sell_orders

trade_bp = Blueprint('trade', __name__)

@trade_bp.route('/trade')
# @login_required
def trade():
    orders = jita_sell_orders()
    for i in range(10):
        current_app.logger.debug(orders[i])
    return redirect_back()