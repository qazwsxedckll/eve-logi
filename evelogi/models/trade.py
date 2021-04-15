import requests
import json

from flask import current_app, abort

from evelogi.extensions import cache

@cache.cached(timeout=3600, key_prefix='jita_sell_orders')
def jita_sell_orders():
    """Retrive Jita sell orders. Takes about 5min. Should not be called simultaneously.
    """
    #TODO:should disable others' use if anyone has called the function
    path = "https://esi.evetech.net/latest/markets/10000002/orders/?datasource=tranquility&order_type=sell"
    res = requests.get(path)

    if res.status_code == 200:
        orders = {}
        data = res.json()

        pages = res.headers["x-pages"]
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
