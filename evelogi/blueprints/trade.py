import requests

from flask import Blueprint, render_template, abort, url_for, redirect, request

from flask_login import login_required, current_user
from flask.globals import current_app

from evelogi.utils import redirect_back, eve_oauth_url
from evelogi.extensions import cache, Base, db
from evelogi.forms.trade import TradeGoodsForm

trade_bp = Blueprint('trade', __name__)

@trade_bp.route('/trade', methods=['GET', 'POST'])
@login_required
def trade():
    if not current_user.is_authenticated:
        return redirect(eve_oauth_url())
    else:
        SolarSystem = Base.classes.mapSolarSystems
        solar_systems = db.session.query(SolarSystem).all()
        choices = [(system.regionID, system.solarSystemName) for system in solar_systems]
        form = TradeGoodsForm()
        form.solar_system.choices = choices
        if form.validate_on_submit():
            region_id = form.solar_system.data
        return render_template("trade/trade.html", form=form)

@cache.cached(timeout=3600, key_prefix='jita_sell_orders')
@login_required
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