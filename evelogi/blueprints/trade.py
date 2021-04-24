import asyncio
from datetime import date, timedelta
import math

import aiohttp
from flask import Blueprint, render_template, redirect, flash

from flask_login import login_required, current_user
from flask.globals import current_app
from flask_migrate import history
from sqlalchemy import and_

from evelogi.utils import async_get_esi_data, eve_oauth_url, gather_esi_requests, get_esi_data
from evelogi.extensions import cache, db, Base
from evelogi.forms.trade import TradeGoodsForm
from evelogi.models.account import Structure
from evelogi.models.trade import MonthVolume
from evelogi.exceptions import GetESIDataError, GetESIDataNotFound

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
            my_sell_orders = list(filter(lambda item: (item.get(
                'is_buy_order') is None or item.get('is_buy_order') == False), my_orders))
            my_sell_order_ids = {item['type_id'] for item in my_sell_orders}
            current_app.logger.info(
                "user: {}, {} sell orders".format(current_user.id, len(my_sell_order_ids)))
            for id in my_sell_order_ids:
                if id in type_ids:
                    type_ids.remove(id)

            SolarSystems = Base.classes.mapSolarSystems
            InvTypes = Base.classes.invTypes
            InvVolumes = Base.classes.invVolumes

            structure = Structure.query.get(form.structure.data)
            structure_orders = structure.get_structure_orders()

            region_id = db.session.query(
                SolarSystems).get(structure.get_structure_data('solar_system_id')).regionID

            current_app.logger.info(
                "user: {}, before get month volume".format(current_user.id))
            new_to_get = []
            outdate_to_get = []
            volumes = {}
            to_update = {}
            for type_id in type_ids:
                month_volume = MonthVolume.query.filter(
                    and_(MonthVolume.type_id == type_id, MonthVolume.region_id == region_id)).first()
                if month_volume is None:
                    new_to_get.append(type_id)
                else:
                    if (date.today() - month_volume.update_time > timedelta(days=current_app.config['HISTORY_VOLUME_UPDATE_INTERVAL'])) \
                            or (month_volume.volume == -1):
                            # -1 means fetching failed at last time
                        outdate_to_get.append(type_id)
                        to_update[type_id] = month_volume
                    else:
                        volumes[type_id] = month_volume.volume

            current_app.logger.info('user: {}, new {}, outdate {}'.format(
                current_user.id, len(new_to_get), len(outdate_to_get)))

            new_results = asyncio.run(
                get_region_month_volume(new_to_get, region_id))
            for type_id, volume in new_results.items():
                month_volume = MonthVolume(
                    type_id=type_id, region_id=region_id, volume=volume, update_time=date.today())
                db.session.add(month_volume)
            volumes.update(new_results)

            outdate_results = asyncio.run(
                get_region_month_volume(outdate_to_get, region_id))
            for type_id, volume in outdate_results.items():
                to_update[type_id].volume = volume
                to_update[type_id].update_time = date.today()
            volumes.update(outdate_results)
            db.session.commit()

            current_app.logger.info(
                "user: {}, after get month volume".format(current_user.id))

            records = []
            for type_id in type_ids:
                if volumes[type_id] == 0:
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

                inv_type = db.session.query(InvTypes).get(type_id)
                type_name = inv_type.typeName
                packaged_volume = db.session.query(InvVolumes).get(type_id)
                if packaged_volume is None:
                    packaged_volume = inv_type.volume
                else:
                    packaged_volume = packaged_volume.volume

                jita_to_cost = float(packaged_volume * structure.jita_to_fee)

                sales_cost = local_price * \
                    (structure.sales_tax * 0.01 + structure.brokers_fee * 0.01)

                profit_per_item = local_price - jita_sell_price - jita_to_cost - sales_cost
                if profit_per_item <= 0:
                    continue

                margin = profit_per_item / \
                    (jita_sell_price + jita_to_cost + sales_cost)
                if margin < form.margin_filter.data:
                    continue

                estimate_profit = profit_per_item * volumes[type_id]

                records.append({'type_id': type_id,
                                'type_name': type_name,
                                'jita_sell_price': jita_sell_price,
                                'daily_volume': math.ceil((volumes[type_id] / 30) * form.multiple.data),
                                'local_price': local_price,
                                'estimate_profit': estimate_profit,
                                'margin': margin,
                                'stockout': stockout
                                })
            records.sort(key=lambda item: item.get(
                'estimate_profit'), reverse=True)
            current_app.logger.info(
                'user: {}, records returned.'.format(current_user.id))

            return render_template('trade/trade.html', form=form, records=records[:form.quantity_filter.data])
        return render_template('trade/trade.html', form=form)


@cache.cached(timeout=1800, key_prefix='jita_sell_orders')
def get_jita_sell_orders():
    """Retrive Jita sell orders. Takes about 5min. Should not be called simultaneously.
    """
    path = "https://esi.evetech.net/latest/markets/10000002/orders/?datasource=tranquility&order_type=sell"
    return get_esi_data(path)


async def get_region_month_volume(type_ids, region_id):
    volumes = {}
    tasks = []
    async with aiohttp.ClientSession() as session:
        for type_id in type_ids:
            tasks.append(get_item_month_volume(type_id, region_id, session))

        results = await asyncio.gather(*tasks)
        fails = 0
        for result in results:
            volumes[result[0]] = result[1]
            if result[1] == -1:
                fails += 1
        current_app.logger.info(
            'user: {}, get_region_month_volume {} fails.'.format(current_user.id, fails))
        flash("{} fails when fetching data.".format(fails))
    return volumes


async def get_item_month_volume(type_id, region_id, session):
    path = "https://esi.evetech.net/latest/markets/" + \
        str(region_id) + \
        "/history/?datasource=tranquility&type_id=" + str(type_id)
    try:
        data = await async_get_esi_data(path, session)
    except GetESIDataNotFound:
        accumulate_volume = 0
    except GetESIDataError as e:
        accumulate_volume = -1
    else:
        accumulate_volume = 0
        for daily_volume in data:
            if date.today() - date.fromisoformat(daily_volume['date']) <= timedelta(days=30):
                accumulate_volume += daily_volume['volume']

    return (type_id, accumulate_volume)
