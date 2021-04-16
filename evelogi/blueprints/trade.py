import requests

from flask import Blueprint, render_template, abort

from flask_login import login_required, current_user
from flask.globals import current_app

from evelogi.utils import redirect_back
from evelogi.extensions import cache

trade_bp = Blueprint('trade', __name__)

@trade_bp.route('/trade')
@login_required
def trade():
    return redirect_back()

@cache.cached(timeout=3600, key_prefix='jita_sell_orders')
def jita_sell_orders():
    """Retrive Jita sell orders. Takes about 5min. Should not be called simultaneously.
    """
    #TODO:should disable others' use if anyone has called the function
    #TODO:data unusable while caching
    path = "https://esi.evetech.net/latest/markets/10000002/orders/?datasource=tranquility&order_type=sell"
    res = requests.get(path)

    if res.status_code == 200:
        data = res.json()

        pages = res.headers.get("x-pages")
        if not pages:
            return data
        
        current_app.logger.debug("x-pages: {}".format(pages))
        for i in range(2, int(pages) + 1):
            res = requests.get(path + "&page={}".format(i))
            if res.status_code == 200:
                data.append(res.json())
                current_app.logger.debug("{}".format(i))
            else:
                current_app.logger.warning(
                    "\nSSO response JSON is: {}".format(res.json()))
                abort(res.status_code)
        return data
    else:
        current_app.logger.warning(
            "\nSSO response JSON is: {}".format(res.json()))
        abort(res.status_code)

@login_required
def my_orders():
    """Retrive all orders of a user.
    """
    characters = current_user.characters
    for character in characters:
        access_token = character.get_access_token()
        path = "https://esi.evetech.net/latest/characters/" + str(character.character_id) + "/orders/?datasource=tranquility&token=" + access_token
        current_app.logger.debug("path: {}".format(path))
        data = []

        res = requests.get(path)

        if res.status_code == 200:
            data.append(res.json())

            pages = res.headers.get("x-pages")
            if not pages:
                return data

            current_app.logger.debug("x-pages: {}".format(pages))
            for i in range(2, int(pages) + 1):
                res = requests.get(path + "&page={}".format(i))
                if res.status_code == 200:
                    data.append(res.json())
                    current_app.logger.debug("{}".format(i))
                else:
                    current_app.logger.warning(
                        "\nSSO response JSON is: {}".format(res.json()))
                    abort(res.status_code)
        else:
            current_app.logger.warning(
                "\nSSO response JSON is: {}".format(res.json()))
            abort(res.status_code)
        return data