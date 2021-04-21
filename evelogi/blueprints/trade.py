from datetime import date, timedelta

from flask import Blueprint, render_template, redirect

from flask_login import login_required, current_user
from flask.globals import current_app
from flask_migrate import history
from sqlalchemy import and_

from evelogi.utils import eve_oauth_url, get_esi_data
from evelogi.extensions import cache, db, Base
from evelogi.forms.trade import TradeGoodsForm
from evelogi.models.account import Structure
from evelogi.models.trade import HistoryVolume

trade_bp = Blueprint('trade', __name__)


@trade_bp.route('/trade', methods=['GET', 'POST'])
@login_required
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
        if form.validate_on_submit():
            jita_sell_data = get_jita_sell_orders()
            type_ids = {item['type_id'] for item in jita_sell_data}

            my_orders = current_user.get_orders()
            filter(lambda item: item.is_buy_order == False, my_orders)
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
            for type_id in type_ids:
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
                history_volume = item_history_volume(type_id, region_id)
                estimate_profit = profit_per_item * history_volume
                margin = profit_per_item / \
                    (jita_sell_price + jita_to_cost + sales_cost)

                records.append({'type_id': type_id,
                                'type_name': type_name,
                                'jita_sell_price': jita_sell_price,
                                'history_volume': history_volume,
                                'local_price': local_price,
                                'estimate_profit': estimate_profit,
                                'margin': margin,
                                'stockout': stockout
                                })
            records.sort(key=lambda item: item.get(
                'estimate_profit'), reverse=True)

            return render_template('trade/trade.html', form=form, records=records)
        return render_template('trade/trade.html', form=form)


@cache.cached(timeout=36000, key_prefix='jita_sell_orders')
def get_jita_sell_orders():
    """Retrive Jita sell orders. Takes about 5min. Should not be called simultaneously.
    """
    # TODO:should disable others' use if anyone has called the function
    # TODO:data unusable while caching
    # TODO:try coroutines
    path = "https://esi.evetech.net/latest/markets/10000002/orders/?datasource=tranquility&order_type=sell"
    return get_esi_data(path)


def get_region_order_history_by_id(type_id, region_id):
    """Retrive order history in a region by type id
    """
    path = "https://esi.evetech.net/latest/markets/" + \
        str(region_id) + "/history/?datasource=tranquility&type_id=" + str(type_id)
    return get_esi_data(path)


def get_item_history_volume(type_id, region_id, days=30):
    data = get_region_order_history_by_id(type_id, region_id)
    volume = 0
    for item in data:
        if date.today() - date.fromisoformat(item['date']) <= timedelta(days=days):
            volume += item['volume']
    return volume


def item_history_volume(type_id, region_id):
    history_volume = HistoryVolume.query.filter(
        and_(HistoryVolume.type_id == type_id, HistoryVolume.region_id == region_id))
    if history_volume is None:
        volume = get_item_history_volume(type_id, region_id)
        history_volume = HistoryVolume(
            type_id=type_id, region_id=region_id, volume=volume, update_time=date.today())
        db.session.add(history_volume)
        db.session.commit()
    else:
        if date.today() - history_volume.update_time > timedelta(days=current_app.config['HISTORY_VOLUME_UPDATE_INTERVL']):
            volume = get_item_history_volume(type_id, region_id)
            history_volume.volume = volume
            history_volume.update_time = date.today()
            db.session.commit()
    return history_volume.volume
