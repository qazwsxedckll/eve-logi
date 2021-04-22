from datetime import date, timedelta
from concurrent import futures
import math

from flask import Blueprint, render_template, redirect, flash

from flask_login import login_required, current_user
from flask.globals import current_app
from flask_migrate import history
from sqlalchemy import and_

from evelogi.utils import eve_oauth_url, get_esi_data, get_multiple_esi_data
from evelogi.extensions import cache, db, Base
from evelogi.forms.trade import TradeGoodsForm
from evelogi.models.account import Structure
from evelogi.models.trade import MonthVolume
from evelogi.exceptions import GetESIDataError

trade_bp = Blueprint('trade', __name__)


@trade_bp.route('/trade', methods=['GET', 'POST'])
def trade():
    if not current_user.is_authenticated:
        return redirect(eve_oauth_url())
    else:
        structures = [
            structure for character in current_user.characters for structure in character.structures]

        choices = [(structure.id, structure.get_structure_data('name'))
                   for structure in structures]
        form = TradeGoodsForm()
        form.structure.choices = choices
        form.multiple.choices = [(i, i) for i in range(1, 6)]
        if form.validate_on_submit():
            jita_sell_data = get_jita_sell_orders()
            type_ids = list({item['type_id'] for item in jita_sell_data})

            my_orders = current_user.get_orders()
            filter(lambda item: item['is_buy_order'] == False, my_orders)
            my_sell_order_ids = {item['type_id'] for item in my_orders}
            for id in type_ids:
                if id in my_sell_order_ids:
                    type_ids.remove(id)

            SolarSystems = Base.classes.mapSolarSystems
            InvTypes = Base.classes.invTypes
            InvVolumes = Base.classes.invVolumes

            structure = Structure.query.get(form.structure.data)
            structure_orders = structure.get_structure_orders()

            region_id = db.session.query(
                SolarSystems).get(structure.get_structure_data('solar_system_id')).regionID

            records = []
            month_volumes = get_region_month_volume(type_ids, region_id)
            for type_id in type_ids:
                month_volume = month_volumes[type_id]
                if month_volume is None:
                    db.session.add(MonthVolume(
                        type_id=type_id, region_id=region_id, volume=0, update_time=date.today()))
                    db.session.commit()
                    continue

                if month_volume == 0:
                    continue

                stockout = False

                jita_sell_price = float('inf')
                for item in jita_sell_data:
                    if item['type_id'] == type_id:
                        jita_sell_price = item['price'] if item['price'] < jita_sell_price else jita_sell_price

                local_price = float("inf")
                for item in structure_orders:
                    if item['type_id'] == type_id and item['is_buy_order'] == False:
                        local_price = item['price'] if item['price'] < local_price else local_price
                if local_price == float("inf"):
                    local_price = jita_sell_price * 1.3
                    stockout = True

                type_name = db.session.query(InvTypes).get(type_id).typeName
                packeaged_volume = db.session.query(InvVolumes).get(type_id)
                if packeaged_volume is None:
                    packeaged_volume = db.session.query(
                        InvTypes).get(type_id).volume
                else:
                    packeaged_volume = packeaged_volume.volume
                jita_to_cost = float(packeaged_volume * structure.jita_to_fee)
                sales_cost = local_price * \
                    (structure.sales_tax * 0.01 + structure.brokers_fee * 0.01)
                profit_per_item = local_price - jita_sell_price - jita_to_cost - sales_cost
                if profit_per_item <= 0:
                    continue
                estimate_profit = profit_per_item * month_volume
                margin = profit_per_item / \
                    (jita_sell_price + jita_to_cost + sales_cost)

                records.append({'type_id': type_id,
                                'type_name': type_name,
                                'jita_sell_price': jita_sell_price,
                                'daily_volume': math.ceil((month_volume / 30) * form.multiple.data),
                                'local_price': local_price,
                                'estimate_profit': estimate_profit,
                                'margin': margin,
                                'stockout': stockout
                                })
            records.sort(key=lambda item: item.get(
                'estimate_profit'), reverse=True)

            return render_template('trade/trade.html', form=form, records=records[:200])
        return render_template('trade/trade.html', form=form)


@cache.cached(timeout=36000, key_prefix='jita_sell_orders')
def get_jita_sell_orders():
    """Retrive Jita sell orders. Takes about 5min. Should not be called simultaneously.
    """
    path = "https://esi.evetech.net/latest/markets/10000002/orders/?datasource=tranquility&order_type=sell"
    return get_esi_data(path)

def get_region_month_volume(type_ids, region_id, days=30):
    result = {}
    new_to_get = {}
    outdate_to_get = {}
    outdate_item = {}
    for type_id in type_ids:
        month_volume = MonthVolume.query.filter(
            and_(MonthVolume.type_id == type_id, MonthVolume.region_id == region_id)).first()
        if month_volume is None:
            new_to_get[type_id] = "https://esi.evetech.net/latest/markets/" + \
                str(region_id) + \
                "/history/?datasource=tranquility&type_id=" + str(type_id)
        else:
            if date.today() - month_volume.update_time > timedelta(days=current_app.config['HISTORY_VOLUME_UPDATE_INTERVAL']):
                outdate_to_get[type_id] = "https://esi.evetech.net/latest/markets/" + \
                    str(region_id) + \
                    "/history/?datasource=tranquility&type_id=" + str(type_id)
                outdate_item[type_id] = month_volume
            else:
                result[type_id] = month_volume.volume
    
    current_app.logger.debug("to get: {}".format(len(outdate_to_get)))
    current_app.logger.debug("to get: {}".format(len(new_to_get)))
    get_multiple_esi_data(new_to_get)
    for id, data in new_to_get.items():
        accumulate_volume = 0.0
        if data is not None:
            for daily_volume in data:
                if date.today() - date.fromisoformat(daily_volume['date']) <= timedelta(days=days):
                    accumulate_volume += daily_volume['volume']

        month_volume = MonthVolume(
            type_id=id, region_id=region_id, volume=accumulate_volume, update_time=date.today())
        result[id] = accumulate_volume
        current_app.logger.debug("item: {}".format(id))
        current_app.logger.debug("volume: {}".format(accumulate_volume))
        db.session.add(month_volume)

    get_multiple_esi_data(outdate_to_get)
    for id, data in outdate_to_get.items():
        accumulate_volume = 0.0
        if data is not None:
            for daily_volume in data:
                if date.today() - date.fromisoformat(daily_volume['date']) <= timedelta(days=days):
                    accumulate_volume += daily_volume['volume']

        outdate_item[id].volume = accumulate_volume
        outdate_item[id].update_time = date.today()
        current_app.logger.debug("item: {}".format(id))
        current_app.logger.debug("volume: {}".format(accumulate_volume))
        result[id] = accumulate_volume.volume

    db.session.commit()
    return result