#!/usr/bin/env python3
"""Finite TD05 budget and inventory reference model, not the game runtime.

The input schedule supplies successful orders, root defeats and trap uses. This
module does not predict combat success, path finding, human input or deadlines.
It does track real balances, charged stock, durability, empty upgrade slots and
the identity boundary between two seven-night defense weeks.
"""

import copy
import math
import re
from fractions import Fraction


def q(value):
    return value if isinstance(value, Fraction) else Fraction(str(value))


def clean(value):
    if isinstance(value, Fraction):
        return int(value) if value.denominator == 1 else round(float(value), 6)
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(x) for x in value]
    return value


def tower_nodes(tree):
    for family in tree['families']:
        yield family['l1']
        for branch in family['l2']:
            yield branch
            yield from branch['l3']


def _actual_base_cost(trap, footprint):
    normalized = tuple(sorted(footprint))
    valid = [tuple(sorted(x)) for x in trap['footprint_variants']]
    if normalized not in valid:
        raise ValueError('undeclared trap footprint')
    for variant in trap.get('footprint_costs', []):
        if tuple(sorted(variant['footprint'])) == normalized:
            return int(variant['coin'])
    if normalized != valid[0]:
        raise ValueError('missing explicit price for this footprint')
    return int(trap['base_cost']['coin'])


def charge_price(asset, economy):
    """Price uses actual L1 size and L1 capacity, never upgraded capacity."""
    if asset['initial_capacity'] is None:
        raise ValueError('asset does not use charges')
    share = q(economy['resupply']['base_initial_consumable_fraction'])
    return max(1, math.ceil(share * asset['base_coin'] / asset['initial_capacity']))


def repair_price(asset, economy):
    policy = economy['resupply']
    key = 'repair_coin_hardware_fraction'
    if key in policy:
        share = q(policy[key])
    else:
        # Read the authored scalar from the small declarative formula, no eval.
        match = re.search(r'ceil\(\s*([0-9.]+)\s*\*\s*refundable_hardware_principal\s*\)', policy['repair_coin_formula'])
        if not match:
            raise ValueError('repair formula needs its authored refundable-hardware fraction')
        share = q(match.group(1))
    return max(1, math.ceil(share * refundable_hardware_principal(asset, economy)))


def make_trap_asset(trap, economy, footprint=None, week_id='reference-week-1', instance_id=None):
    footprint = list(footprint or trap['footprint_variants'][0])
    cells = math.prod(footprint)
    base_coin = _actual_base_cost(trap, footprint)
    hp = trap['durability']
    if hp is not None and trap.get('durability_scales_with_footprint_cells'):
        hp *= cells
    cap = trap['charges']
    return {
        'instance_id': instance_id or f'{week_id}:{trap["id"]}',
        'week_id': week_id, 'kind': 'trap', 'root_id': trap['id'],
        'node_id': trap['id'], 'tier': 1, 'path': [trap['id']],
        'location': 'backpack', 'footprint': footprint, 'footprint_cells': cells,
        'base_coin': base_coin, 'paid_base_coin': base_coin,
        'paid_upgrade_coin': 0, 'net_paid_coin': base_coin,
        'free_job_asset': False, 'initial_capacity': cap,
        'charge_capacity': cap, 'charges': cap, 'paid_charges': cap,
        'max_hp': None if hp is None else q(hp),
        'hp': None if hp is None else q(hp),
    }


def make_tower_asset(node, week_id='reference-week-1', free_job=False, instance_id=None):
    paid = 0 if free_job else node['cost']['coin']
    return {
        'instance_id': instance_id or f'{week_id}:{node["id"]}',
        'week_id': week_id, 'kind': 'tower', 'root_id': node['id'],
        'node_id': node['id'], 'tier': 1, 'path': [node['id']],
        'location': 'placed', 'footprint': None, 'footprint_cells': 0,
        'base_coin': node['cost']['coin'], 'paid_base_coin': paid,
        'paid_upgrade_coin': 0, 'net_paid_coin': paid,
        'free_job_asset': free_job, 'initial_capacity': None,
        'charge_capacity': None, 'charges': None, 'paid_charges': None,
        'max_hp': None, 'hp': None,
    }


def can_sell(asset):
    return (not asset['free_job_asset']
            and asset.get('location') != 'destroyed'
            and (asset['hp'] is None or asset['hp'] > 0))


def refundable_hardware_principal(asset, economy):
    """H excludes consumables, repairs and reselection fees; no salvage rate yet."""
    charged = asset['initial_capacity'] is not None
    share = q(economy['resupply']['base_hardware_fraction_for_charged_trap']) if charged else q(1)
    return share * asset['paid_base_coin'] + asset['paid_upgrade_coin']


def sale_refund(asset, economy):
    """Floor each component, then apply floored net-paid cap; job assets cannot sell.

    Services do not become hardware principal. Only actual remaining paid
    charges have a consumable refund. The total still cannot exceed half the
    asset's actual net paid coin. This helper computes value, not authorization
    to sell during combat or after its week has closed.
    """
    if not can_sell(asset):
        return 0
    policy = economy['sale_and_reselection']
    ratio = q(1) if asset['max_hp'] is None else max(q(0), min(q(1), q(asset['hp']) / q(asset['max_hp'])))
    charged = asset['initial_capacity'] is not None
    hardware_principal = refundable_hardware_principal(asset, economy)
    hardware = math.floor(q(policy['hardware_refund_fraction']) * hardware_principal * ratio)
    charges = 0
    if charged:
        refundable_count = min(asset['charges'], asset['paid_charges'])
        charges = math.floor(q(policy['charge_refund_fraction_of_recharge_value']) * refundable_count * charge_price(asset, economy))
    cap = math.floor(q(policy['net_paid_coin_refund_ceiling_fraction']) * asset['net_paid_coin'])
    return max(0, min(cap, hardware + charges))


def upgrade_inventory(asset, node, economy, paid_cost):
    """Apply one purchased child, preserving HP ratio and present charge count."""
    if node['parent'] != asset['node_id']:
        raise ValueError('upgrade must follow the currently active parent, not an old purchased branch')
    if asset['hp'] is not None and asset['hp'] <= 0:
        raise ValueError('destroyed trap cannot be repaired by upgrading')
    before = asset_snapshot(asset)
    parameters = node.get('parameters', {})
    old_max, old_hp = asset['max_hp'], asset['hp']
    if asset['kind'] == 'trap':
        if 'capacity_delta_from_l1' in parameters:
            asset['charge_capacity'] = asset['initial_capacity'] + parameters['capacity_delta_from_l1']
        elif 'capacity_delta_from_l2' in parameters:
            asset['charge_capacity'] += parameters['capacity_delta_from_l2']
        if 'durability_per_cell' in parameters:
            asset['max_hp'] = q(parameters['durability_per_cell'] * asset['footprint_cells'])
        elif 'durability' in parameters:
            asset['max_hp'] = q(parameters['durability'])
        if old_max is not None and asset['max_hp'] != old_max:
            asset['hp'] = old_hp / old_max * asset['max_hp']
        # No new charge is added here. The next actual paid service may fill it.
        if asset['charges'] is not None:
            assert asset['charges'] <= asset['charge_capacity']
    asset['node_id'] = node['id']
    asset['path'].append(node['id'])
    asset['tier'] += 1
    asset['paid_upgrade_coin'] += paid_cost['coin']
    asset['net_paid_coin'] += paid_cost['coin']
    return {'before': before, 'after': asset_snapshot(asset), 'paid_cost': dict(paid_cost)}


def consume_charges(asset, requested):
    if requested < 0 or int(requested) != requested:
        raise ValueError('charge uses are nonnegative integers')
    before = asset['charges']
    actual = min(requested, before)
    asset['charges'] -= actual
    asset['paid_charges'] = max(0, asset['paid_charges'] - actual)
    return {'requested': requested, 'actual': actual, 'unserved': requested - actual,
            'before': before, 'after': asset['charges']}


def refill_missing(asset, economy, available_coin):
    price = charge_price(asset, economy)
    missing = asset['charge_capacity'] - asset['charges']
    bought = min(missing, available_coin // price)
    before = asset['charges']
    asset['charges'] += bought
    asset['paid_charges'] += bought
    cost = bought * price
    asset['net_paid_coin'] += cost
    return {'kind': 'refill', 'root': asset['root_id'], 'missing_before': missing,
            'bought': bought, 'unit_coin': price, 'coin': cost,
            'charges_before': before, 'charges_after': asset['charges'],
            'capacity': asset['charge_capacity'], 'unfilled': missing - bought}


def repair_missing(asset, economy, available_coin):
    price = repair_price(asset, economy)
    per_action = q(economy['resupply']['repair_max_hp_fraction']) * asset['max_hp']
    missing = asset['max_hp'] - asset['hp']
    if asset['hp'] <= 0:
        return clean({'kind': 'repair', 'root': asset['root_id'], 'required_actions': 0,
                      'actions': 0, 'unit_coin': price, 'coin': 0,
                      'hp_before': asset['hp'], 'hp_after': asset['hp'], 'max_hp': asset['max_hp'],
                      'restored': 0, 'unrepaired_hp': missing,
                      'reason': 'destroyed_requires_rebuild_not_repair'})
    required = math.ceil(missing / per_action)
    actual = min(required, available_coin // price)
    before = asset['hp']
    restored = min(missing, actual * per_action)
    asset['hp'] += restored
    cost = actual * price
    asset['net_paid_coin'] += cost
    return clean({'kind': 'repair', 'root': asset['root_id'], 'required_actions': required,
                  'actions': actual, 'unit_coin': price, 'coin': cost,
                  'hp_before': before, 'hp_after': asset['hp'], 'max_hp': asset['max_hp'],
                  'restored': restored, 'unrepaired_hp': missing - restored})


def asset_snapshot(asset):
    keys = ('instance_id', 'week_id', 'root_id', 'node_id', 'tier', 'location',
            'charges', 'charge_capacity', 'initial_capacity', 'hp', 'max_hp',
            'paid_upgrade_coin', 'net_paid_coin', 'footprint_cells', 'paid_charges')
    return clean({key: asset[key] for key in keys})


def accepts_week_command(state, command_week_id):
    return command_week_id == state['week_id'] and command_week_id not in state['closed_week_ids']


def reset_week(state, economy, free_tower_node, expected_week_id):
    """Atomic in-memory reference: old commands and backpack assets cannot leak."""
    if not accepts_week_command(state, expected_week_id):
        return {'applied': False, 'reason': 'stale_or_already_closed_week', 'week_id': state['week_id']}
    if state['completed_nights'] != economy['wallet_policy']['week_days']:
        raise ValueError('the authored seventh-night settlement has not completed')
    record = {
        'applied': True, 'closed_week_id': expected_week_id,
        'closed_coin': state['coin'], 'closed_spirit': state['spirit'],
        'cleared_instances': [asset_snapshot(a) for a in state['assets'].values()],
        'cleared_pending_commands': copy.deepcopy(state['pending_commands']),
        'refund_coin': 0,
        'cleared_refill_stock': copy.deepcopy(state.get('refill_stock', {})),
    }
    state['closed_week_ids'].add(expected_week_id)
    state['week_number'] += 1
    state['week_id'] = f'reference-week-{state["week_number"]}'
    state['coin'] = economy['wallet_policy']['starting_coin']
    state['spirit'] = economy['wallet_policy']['starting_spirit']
    state['assets'].clear()  # Contains placed and backpack instances alike.
    state['pending_commands'].clear()
    state.setdefault('refill_stock', {}).clear()
    state.setdefault('command_receipts', {}).clear()
    state['phase'] = 'pre_shift'
    state['opening_manifest'] = []
    state['night_id'] = 1
    state['completed_nights'] = 0
    free = make_tower_asset(free_tower_node, state['week_id'], free_job=True)
    state['assets'][free['root_id']] = free
    record['next_week_id'] = state['week_id']
    return clean(record)


def _capacity_ok(assets, candidate, economy):
    all_assets = list(assets.values()) + [candidate]
    placed = [a for a in all_assets if a['location'] == 'placed']
    caps = economy['capacity']
    towers = [a for a in placed if a['kind'] == 'tower']
    traps = [a for a in placed if a['kind'] == 'trap']
    return (len(towers) <= caps['active_towers'] and len(traps) <= caps['trap_objects']
            and sum(a['footprint_cells'] for a in traps) <= caps['trap_footprint_tiles']
            and sum(a['footprint_cells'] for a in traps if a['root_id'] == 'R12') <= caps['barrier_tiles'])


def depleted_sale_comparisons(economy, traps):
    """Compare equal final stocks for every charged trap size and legal tier.

    Rebuilding an upgraded trap buys only the L1 initial stock, so its additional
    capacity still needs paid refill. The comparison includes that expenditure;
    comparing a newly bought half-empty item to a fully refilled one is unfair.
    """
    rows = []
    for trap in traps['traps']:
        if trap['charges'] is None:
            continue
        for footprint in trap['footprint_variants']:
            base = make_trap_asset(trap, economy, footprint)
            candidates = [copy.deepcopy(base)]
            for branch in trap['l2']:
                asset = copy.deepcopy(base)
                for node in (branch, branch['l3']):
                    factor = asset['footprint_cells'] if node['cost'].get('basis') else 1
                    cost = {k: node['cost'][k] * factor for k in ('coin', 'spirit')}
                    upgrade_inventory(asset, node, economy, cost)
                    candidates.append(copy.deepcopy(asset))
            for asset in candidates:
                asset['charges'] = 0
                asset['paid_charges'] = 0
                one = charge_price(asset, economy)
                refill = asset['charge_capacity'] * one
                added_slots = asset['charge_capacity'] - asset['initial_capacity']
                refund = sale_refund(asset, economy)
                rebuild_equal_stock = (asset['paid_base_coin'] + asset['paid_upgrade_coin']
                                       + added_slots * one - refund)
                rows.append({'node': asset['node_id'], 'footprint': footprint,
                             'refund_empty': refund, 'refill_to_current_capacity_coin': refill,
                             'sell_rebuild_same_tier_and_fill_same_capacity_coin': rebuild_equal_stock,
                             'rebuild_not_cheaper': rebuild_equal_stock >= refill,
                             'rebuild_also_requires_spirit_again': asset['tier'] > 1})
    return rows


def repair_sale_comparisons(economy, traps):
    """Check paid repair then sale against immediate sale, every size and tier."""
    rows = []
    for trap in traps['traps']:
        if trap['durability'] is None:
            continue
        for footprint in trap['footprint_variants']:
            base = make_trap_asset(trap, economy, footprint)
            candidates = [copy.deepcopy(base)]
            for branch in trap['l2']:
                asset = copy.deepcopy(base)
                for node in (branch, branch['l3']):
                    factor = asset['footprint_cells'] if node['cost'].get('basis') else 1
                    cost = {k: node['cost'][k] * factor for k in ('coin', 'spirit')}
                    upgrade_inventory(asset, node, economy, cost)
                    candidates.append(copy.deepcopy(asset))
            for candidate in candidates:
                # Check lower, middle and partial-final repairs; never revive HP0.
                for ratio in (q('.1'), q('.25'), q('.5'), q('.75'), q('.9')):
                    asset = copy.deepcopy(candidate)
                    asset['hp'] = ratio * asset['max_hp']
                    before = sale_refund(asset, economy)
                    price = repair_price(asset, economy)
                    event = repair_missing(asset, economy, price)  # exactly one affordable action
                    after = sale_refund(asset, economy)
                    rows.append(clean({'node': asset['node_id'], 'footprint': footprint,
                                       'initial_hp_fraction': ratio,
                                       'hardware_principal': refundable_hardware_principal(asset, economy),
                                       'repair_coin': event['coin'], 'refund_before': before,
                                       'refund_after': after,
                                       'repair_then_sale_extra_net_coin': after - before - event['coin'],
                                       'repair_then_sale_not_profitable': after <= before + event['coin']}))
    return rows


# The arithmetic helpers above are pure preparation / quotation primitives.
# Gameplay-like mutations must enter through this transaction boundary.
TRAP_PREPARATION_ACTIONS = {
    'purchase', 'deploy', 'move', 'pack', 'upgrade', 'reselect',
    'reload_purchase', 'reload_load', 'repair', 'sell', 'reward_replenish',
}


def preparation_state(economy, week_id='reference-week-1'):
    return {'week_number':1,'week_id':week_id,'coin':economy['wallet_policy']['starting_coin'],
            'spirit':economy['wallet_policy']['starting_spirit'],'assets':{},
            'pending_commands':[],'closed_week_ids':set(),'completed_nights':0,
            'phase':'pre_shift','night_id':1,'refill_stock':{},
            'command_receipts':{},'opening_manifest':[]}


def trap_action_permission(state, action, week_id):
    if not accepts_week_command(state, week_id):
        return False, 'stale_or_closed_week'
    if action in TRAP_PREPARATION_ACTIONS:
        return (True, 'pre_shift') if state['phase']=='pre_shift' else (False, 'traps_locked_after_opening')
    if action=='consume':
        return (True, 'business_open') if state['phase']=='open' else (False, 'no_combat_trigger_before_opening')
    return False, 'unknown_action'


def _find_asset(state, instance_id):
    for key, asset in state['assets'].items():
        if asset['instance_id']==instance_id:
            return key, asset
    raise ValueError('trap instance does not exist; purchase is required')


def _refill_sku(asset):
    return asset['root_id']+':'+ 'x'.join(map(str,sorted(asset['footprint'])))


def _trap_node(traps, node_id):
    root=node_id.split('.')[0]
    trap=next(t for t in traps['traps'] if t['id']==root)
    if node_id==root:
        return trap, None
    for branch in trap['l2']:
        if branch['id']==node_id:return trap,branch
        if branch['l3']['id']==node_id:return trap,branch['l3']
    raise ValueError('unknown trap specialization')


def apply_trap_command(state, command, economy, traps):
    """Atomic, idempotent purchased-item inventory transaction.

    An OPEN rejection mutates neither wallets, inventory nor receipts, so a
    backpack, refund, upgrade, reward or repair cannot smuggle new uses into a
    night. Consume is the only supported OPEN mutation and can only spend stock
    that was already on a placed item at opening.
    """
    action=command['action']
    allowed,reason=trap_action_permission(state,action,command['week_id'])
    if not allowed:return {'applied':False,'reason':reason,'action':action}
    receipt=command.get('receipt_id')
    if not receipt:return {'applied':False,'reason':'missing_receipt_id','action':action}
    if receipt in state['command_receipts']:
        return {'applied':False,'reason':'duplicate_receipt','action':action}
    work=copy.deepcopy(state)
    before_coin,before_spirit=work['coin'],work['spirit']
    try:
        if action=='purchase':
            trap,_=_trap_node(traps,command['trap_id'])
            instance_id=command['instance_id']
            if any(a['instance_id']==instance_id for a in work['assets'].values()):
                raise ValueError('instance_id already exists')
            asset=make_trap_asset(trap,economy,command.get('footprint'),work['week_id'],instance_id)
            if work['coin']<asset['paid_base_coin']:raise ValueError('insufficient coin')
            key=command.get('asset_key',instance_id)
            if key in work['assets']:raise ValueError('asset key already exists')
            work['coin']-=asset['paid_base_coin'];work['assets'][key]=asset
            detail={'purchased_item':asset_snapshot(asset),'starts_in_backpack':True}
        else:
            key,asset=_find_asset(work,command.get('instance_id'))
            if asset['kind']!='trap':raise ValueError('trap API requires a trap')
            if asset['week_id']!=work['week_id']:raise ValueError('stale item week')
            if asset['location']=='destroyed' or (asset['hp'] is not None and asset['hp']<=0):
                raise ValueError('destroyed items require a newly purchased replacement next preparation')
            if action=='deploy':
                if asset['location']!='backpack':raise ValueError('deploy requires purchased backpack item')
                if not command.get('geometry_valid',False):raise ValueError('placement not validated')
                candidate=copy.deepcopy(asset);candidate['location']='placed'
                other={k:v for k,v in work['assets'].items() if k!=key}
                if not _capacity_ok(other,candidate,economy):raise ValueError('deployed capacity exceeded')
                asset['location']='placed';asset['placement']=command.get('placement','authored_valid_floor')
                detail={'deployed':asset_snapshot(asset),'new_item_created':False}
            elif action in ('move','pack'):
                if asset['location']!='placed':raise ValueError('item is not placed')
                if action=='move':
                    if not command.get('geometry_valid',False):raise ValueError('placement not validated')
                    asset['placement']=command.get('placement','authored_valid_floor')
                else:asset['location']='backpack'
                detail={'after':asset_snapshot(asset),'preserved_stock_hp_identity':True}
            elif action=='reload_purchase':
                units=command['quantity']
                if int(units)!=units or units<=0:raise ValueError('positive integer purchase required')
                price=charge_price(asset,economy);cost=units*price
                if cost>work['coin']:raise ValueError('insufficient coin')
                sku=_refill_sku(asset)
                stock=work['refill_stock'].setdefault(sku,{'week_id':work['week_id'],'quantity':0,'unit_coin':price})
                if stock['unit_coin']!=price:raise ValueError('inconsistent paid stock price')
                stock['quantity']+=units;work['coin']-=cost
                detail={'sku':sku,'purchased_quantity':units,'stock_after':stock['quantity'],'unit_coin':price}
            elif action=='reload_load':
                units=command['quantity']
                if int(units)!=units or units<=0:raise ValueError('positive integer load required')
                sku=_refill_sku(asset);stock=work['refill_stock'].get(sku)
                if not stock or stock['quantity']<units:raise ValueError('load requires previously purchased refill stock')
                if stock['week_id']!=work['week_id']:raise ValueError('refill stock is from another week')
                if asset['charges']+units>asset['charge_capacity']:raise ValueError('charge capacity exceeded')
                before=asset['charges'];stock['quantity']-=units
                asset['charges']+=units;asset['paid_charges']+=units
                asset['net_paid_coin']+=units*stock['unit_coin']
                detail={'sku':sku,'loaded_quantity':units,'stock_after':stock['quantity'],
                        'charges_before':before,'charges_after':asset['charges'],'coin':0}
            elif action=='repair':
                if asset['max_hp'] is None:raise ValueError('item does not have durability')
                cap_coin=min(work['coin'],command.get('max_coin',work['coin']))
                if cap_coin<0 or int(cap_coin)!=cap_coin:raise ValueError('nonnegative integer repair budget required')
                detail=repair_missing(asset,economy,cap_coin)
                work['coin']-=detail['coin']
            elif action=='upgrade':
                _,node=_trap_node(traps,command['node_id'])
                if node is None or node['parent']!=asset['node_id']:raise ValueError('invalid active upgrade parent')
                factor=asset['footprint_cells'] if node['cost'].get('basis') else 1
                cost={k:node['cost'][k]*factor for k in ('coin','spirit')}
                if work['coin']<cost['coin'] or work['spirit']<cost['spirit']:raise ValueError('insufficient upgrade funds')
                detail=upgrade_inventory(asset,node,economy,cost)
                work['coin']-=cost['coin'];work['spirit']-=cost['spirit']
            elif action=='reselect':
                trap,target=_trap_node(traps,command['node_id'])
                if trap['id']!=asset['root_id'] or target is None:raise ValueError('reselect must stay within family')
                branch=next((b for b in trap['l2'] if target['id'] in (b['id'],b['l3']['id'])),None)
                target_tier=2 if target['id']==branch['id'] else 3
                if target_tier!=asset['tier']:raise ValueError('reselect must preserve purchased tier')
                fee=math.ceil(q(economy['sale_and_reselection']['reselection_coin_fraction_of_paid_specializations'])*asset['paid_upgrade_coin'])
                if work['coin']<fee:raise ValueError('insufficient reselection funds')
                prototype=make_trap_asset(trap,economy,asset['footprint'],work['week_id'],asset['instance_id'])
                for node in ([branch] if target_tier==2 else [branch,branch['l3']]):
                    upgrade_inventory(prototype,node,economy,{'coin':0,'spirit':0})
                old_charges=asset['charges']; old_ratio=None if asset['max_hp'] is None else asset['hp']/asset['max_hp']
                if old_charges is not None and old_charges>prototype['charge_capacity']:
                    raise ValueError('lower-capacity branch cannot hold present loaded stock; retain branch until the surplus is used')
                for field in ('node_id','tier','path','charge_capacity','max_hp'):
                    asset[field]=prototype[field]
                if old_ratio is not None:asset['hp']=old_ratio*asset['max_hp']
                asset['net_paid_coin']+=fee;work['coin']-=fee
                detail={'fee':fee,'after':asset_snapshot(asset),'charge_or_hp_refill':False}
            elif action=='sell':
                refund=sale_refund(asset,economy);work['coin']+=refund
                del work['assets'][key]
                detail={'sold_instance_id':asset['instance_id'],'refund_coin':refund}
            elif action=='consume':
                if asset['location']!='placed':raise ValueError('backpack item cannot trigger')
                opening=next((x for x in work['opening_manifest'] if x['instance_id']==asset['instance_id']),None)
                if opening is None:raise ValueError('not present in opening manifest')
                if asset['charges'] is None:raise ValueError('uncharged barrier cannot spend a trigger charge')
                quantity=command.get('quantity',1)
                if quantity<=0 or int(quantity)!=quantity:raise ValueError('positive integer trigger quantity required')
                if asset['charges']<=0:raise ValueError('empty trap cannot trigger or start an effect')
                detail=consume_charges(asset,quantity)
                detail['authorized_effect_count']=detail['actual']
            else:
                raise ValueError('no reward/drop replenishment route; use purchased preparation stock')
    except (ValueError,KeyError,StopIteration,TypeError) as error:
        return {'applied':False,'reason':str(error),'action':action}
    event=clean({'applied':True,'action':action,'receipt_id':receipt,'week_id':work['week_id'],
                 'phase':work['phase'],'coin_spent':before_coin-work['coin'],
                 'spirit_spent':before_spirit-work['spirit'],'detail':detail})
    work['command_receipts'][receipt]=event
    state.clear();state.update(work)
    return event


def begin_shift(state):
    if state['phase']!='pre_shift':return {'applied':False,'reason':'already_open_or_not_preparation'}
    state['opening_manifest']=[asset_snapshot(a) for a in state['assets'].values() if a['location']=='placed']
    state['phase']='open'
    return {'applied':True,'night_id':state['night_id'],'opening_manifest':copy.deepcopy(state['opening_manifest'])}


def settle_shift(state, coin, spirit):
    if state['phase']!='open':return {'applied':False,'reason':'shift_not_open_or_already_settled'}
    if coin<0 or spirit<0:raise ValueError('nonnegative authored income only')
    state['coin']+=coin;state['spirit']+=spirit
    state['completed_nights']=state['night_id'];state['night_id']+=1
    state['phase']='settled_week' if state['completed_nights']==7 else 'pre_shift'
    return {'applied':True,'completed_nights':state['completed_nights'],'coin':state['coin'],'spirit':state['spirit']}


def command_counterexamples(economy,traps):
    """Real paid reserve exists, but it cannot refill or deploy after opening."""
    state=preparation_state(economy); state['coin']=300;state['spirit']=20
    seq=0
    def cmd(action,**kwargs):
        nonlocal seq
        seq+=1
        return apply_trap_command(state,{'action':action,'week_id':state['week_id'],
                                  'receipt_id':f'gate-{seq}',**kwargs},economy,traps)
    events=[]
    events.append(cmd('purchase',trap_id='R01',instance_id='placed-tape'))
    events.append(cmd('deploy',instance_id='placed-tape',geometry_valid=True))
    events.append(cmd('purchase',trap_id='R01',instance_id='spare-tape'))
    events.append(cmd('reload_purchase',instance_id='placed-tape',quantity=4))
    begin_shift(state)
    valid_triggers=[cmd('consume',instance_id='placed-tape',quantity=1) for _ in range(4)]
    spent=valid_triggers[-1]
    before_fifth=copy.deepcopy(state)
    fifth=cmd('consume',instance_id='placed-tape',quantity=1)
    fifth_unchanged=state==before_fifth
    invalid_quantity_rows=[]
    for quantity in (-1,0,0.5):
        old=copy.deepcopy(state)
        bad=cmd('consume',instance_id='placed-tape',quantity=quantity)
        invalid_quantity_rows.append({'quantity':quantity,'denied':not bad['applied'],'state_unchanged':state==old})
    unchanged=[]
    for action in sorted(TRAP_PREPARATION_ACTIONS):
        old=copy.deepcopy(state)
        denied=cmd(action,instance_id='placed-tape',trap_id='R01',node_id='R01.A',quantity=1,geometry_valid=True)
        unchanged.append({'action':action,'denied':not denied['applied'],'reason':denied['reason'],
                          'entire_state_unchanged':state==old})
    spare_before=copy.deepcopy(state)
    spare_denied=cmd('deploy',instance_id='spare-tape',geometry_valid=True)
    stale_before=copy.deepcopy(state)
    stale=apply_trap_command(state,{'action':'consume','week_id':'old-week','receipt_id':'old-receipt',
                                  'instance_id':'placed-tape'},economy,traps)
    stale_unchanged=state==stale_before
    settle_shift(state,0,0)
    carried=copy.deepcopy(state)
    loaded=cmd('reload_load',instance_id='placed-tape',quantity=4)
    reloaded_charge=next(a['charges'] for a in state['assets'].values() if a['instance_id']=='placed-tape')
    duplicate_before=copy.deepcopy(state)
    duplicate=apply_trap_command(state,{'action':'reload_load','week_id':state['week_id'],
                  'receipt_id':loaded['receipt_id'],'instance_id':'placed-tape','quantity':4},economy,traps)
    return clean({'preparation_events':events,'valid_triggers':valid_triggers,'depletion':spent,
                  'fifth_trigger_rejected_without_mutation':not fifth['applied'] and fifth_unchanged,
                  'fifth_trigger':fifth,'invalid_trigger_quantities':invalid_quantity_rows,'open_rejections':unchanged,
                  'purchased_spare_open_deploy_denied':not spare_denied['applied'],
                  'stale_week_rejected_without_mutation':not stale['applied'] and stale_unchanged,
                  'night_transition_preserved_empty_placed_item':next(a['charges'] for a in carried['assets'].values() if a['instance_id']=='placed-tape')==0,
                  'next_preparation_can_load_prepaid_stock':loaded['applied'] and reloaded_charge==4,
                  'duplicate_load_rejected_without_mutation':not duplicate['applied'] and state==duplicate_before,
                  'paid_spare_remained_backpack':next(a['location'] for a in state['assets'].values() if a['instance_id']=='spare-tape')=='backpack'})


def week_replay(economy,tower_tree,traps,scenario):
    """Seven actual pre-purchase / stock / load / deploy cycles with phase gates."""
    tower_defs={n['id']:n for n in tower_nodes(tower_tree)}
    trap_defs={t['id']:t for t in traps['traps']}
    definitions={**tower_defs}
    for trap in trap_defs.values():
        definitions[trap['id']]={'id':trap['id'],'parent':None,'cost':trap['base_cost']}
        for branch in trap['l2']:
            definitions[branch['id']]=branch;definitions[branch['l3']['id']]=branch['l3']
    wallet,income,replay=economy['wallet_policy'],economy['income'],economy['replay_assumptions']
    assert 0<=scenario['orders']<=income['order_limit_per_night']
    assert 0<=scenario['major_rules']<=scenario['roots']<=income['new_root_slots_per_night']
    performance=scenario.get('performance_bonus',income['performance_bonus_in_base_replays'])
    assert 0<=performance<=income['performance_bonus_max']
    daily_coin=(scenario['orders']*income['coin_per_valid_order']+scenario['roots']*income['coin_per_unique_root_defeat']
                +income['completed_handover_wage']+performance)
    daily_spirit=scenario['roots']*income['spirit_per_unique_root_defeat']+scenario['major_rules']*income['spirit_bonus_per_real_major_rule']
    state=preparation_state(economy); free_id=wallet['free_job_tower']
    state['assets'][free_id]=make_tower_asset(tower_defs[free_id],state['week_id'],free_job=True)
    sequence=0
    def command(action,**kwargs):
        nonlocal sequence
        sequence+=1
        return apply_trap_command(state,{'action':action,'week_id':state['week_id'],
                                        'receipt_id':f'{scenario["id"]}-{sequence}',**kwargs},economy,traps)
    def build(nid,footprint=None):
        root=nid.split('.')[0];node=definitions[nid];asset=state['assets'].get(root)
        if root.startswith('R'):
            if node.get('parent'):
                return command('upgrade',instance_id=asset['instance_id'],node_id=nid)
            candidate=make_trap_asset(trap_defs[root],economy,footprint,state['week_id'],root)
            candidate['location']='placed'
            if not _capacity_ok(state['assets'],candidate,economy):return {'applied':False,'reason':'capacity'}
            bought=command('purchase',trap_id=root,footprint=footprint,instance_id=root,asset_key=root)
            if not bought['applied']:return bought
            deployed=command('deploy',instance_id=root,geometry_valid=True)
            assert deployed['applied']
            bought['deploy_event']=deployed
            return bought
        if not node.get('parent'):
            candidate=make_tower_asset(node,state['week_id'])
            if not _capacity_ok(state['assets'],candidate,economy):return {'applied':False,'reason':'capacity'}
            cost=node['cost']
        else:cost=node['cost']
        if state['coin']<cost['coin'] or state['spirit']<cost['spirit']:
            return {'applied':False,'reason':'funds'}
        state['coin']-=cost['coin'];state['spirit']-=cost['spirit']
        if not node.get('parent'):
            state['assets'][root]=candidate;detail={'after':asset_snapshot(candidate)}
        else:detail=upgrade_inventory(asset,node,economy,cost)
        return clean({'applied':True,'action':'tower_build_or_upgrade','node':nid,'phase':state['phase'],
                      'coin_spent':cost['coin'],'spirit_spent':cost['spirit'],'detail':detail})
    initial=[];initial_events=[];initial_cost=0
    for authored in replay['minimum_starting_build']:
        if authored.startswith('free_'):continue
        match=re.fullmatch(r'([TR]\d{2})(?:_(\d+)x(\d+))?_L1',authored)
        root=match.group(1);footprint=None if match.group(2) is None else [int(match.group(2)),int(match.group(3))]
        event=build(root,footprint);assert event['applied']
        initial_events.append(event);initial.append(root);initial_cost+=event['coin_spent']
    rows=[];spent_build=initial_cost;spent_service=0;feasible=True
    for night in range(1,wallet['week_days']+1):
        assert state['phase']=='pre_shift' and state['night_id']==night
        brought=[asset_snapshot(a) for a in state['assets'].values()]
        bought=[];services=[];purchases=[];service=0
        if night>1:
            reserve=replay['non_defense_consumables_per_completed_night_coin'];actual=min(reserve,state['coin'])
            feasible &= actual==reserve;state['coin']-=actual;service+=actual
            services.append({'kind':'explicit_test_consumable_reserve','coin':actual,'requested':reserve,'is_new_game_tax':False})
            for key in list(state['assets']):
                asset=state['assets'][key]
                if asset['kind']!='trap':continue
                if asset['charge_capacity'] is not None:
                    missing=asset['charge_capacity']-asset['charges'];price=charge_price(asset,economy)
                    units=min(missing,state['coin']//price)
                    if units:
                        purchase=command('reload_purchase',instance_id=asset['instance_id'],quantity=units)
                        loaded=command('reload_load',instance_id=asset['instance_id'],quantity=units)
                        assert purchase['applied'] and loaded['applied']
                        service+=purchase['coin_spent'];services.extend([purchase,loaded])
                    feasible &= units==missing
                # The transaction replaces object references; fetch it again.
                asset=state['assets'][key]
                if asset['max_hp'] is not None and asset['hp']<asset['max_hp']:
                    event=command('repair',instance_id=asset['instance_id'])
                    assert event['applied'];service+=event['coin_spent'];services.append(event)
                    feasible &= state['assets'][key]['hp']==state['assets'][key]['max_hp']
            spent_service+=service
            for nid in replay['purchase_priority']:
                root=nid.split('.')[0];node=definitions[nid];asset=state['assets'].get(root);parent=node.get('parent')
                if asset and nid in asset['path']:continue
                if parent and (asset is None or asset['node_id']!=parent):continue
                if not parent and asset:continue
                event=build(nid)
                if event['applied']:
                    bought.append(nid);purchases.append(event);spent_build+=event['coin_spent']
        towers={root:a['tier'] for root,a in state['assets'].items() if a['kind']=='tower'}
        trap_states={root:a['tier'] for root,a in state['assets'].items() if a['kind']=='trap'}
        opening=begin_shift(state);assert opening['applied']
        row={'night':night,'week_id':state['week_id'],'before_night_coin':state['coin'],'before_night_spirit':state['spirit'],
             'purchases':bought if night>1 else initial,'service_and_reserve_before_night_coin':service,
             'service_events':services,'purchase_events':purchases if night>1 else initial_events,
             'inventory_brought_from_previous_night':brought,'inventory_before_night':opening['opening_manifest'],
             'opening_manifest':opening['opening_manifest'],'locked_phase':'open',
             'tower_count':len(towers),'tower_tiers':towers,'l3_towers':sum(x==3 for x in towers.values()),
             'trap_count':len(trap_states),'trap_tiers':trap_states,'l3_traps':sum(x==3 for x in trap_states.values()),
             'trap_footprint_tiles':sum(a['footprint_cells'] for a in state['assets'].values()),
             'income_after_night_coin':daily_coin,'income_after_night_spirit':daily_spirit,
             'handover_wage_only_after_this_night':income['completed_handover_wage']}
        uses=[]
        for root,requested in replay['trap_uses_per_night'].items():
            if root in state['assets']:
                event=command('consume',instance_id=state['assets'][root]['instance_id'],quantity=requested)
                assert event['applied'];uses.append(event)
                feasible &= event['detail']['unserved']==0
        barrier=state['assets'].get('R12')
        if barrier:
            loss=min(barrier['hp'],q(replay['barrier_hp_fraction_lost_per_night'])*barrier['max_hp'])
            barrier['hp']-=loss
            uses.append(clean({'root':'R12','kind':'authored_barrier_damage','hp_lost':loss,'hp_after':barrier['hp'],'max_hp':barrier['max_hp']}))
        row['night_uses']=uses;row['inventory_after_night']=[asset_snapshot(a) for a in state['assets'].values()]
        settled=settle_shift(state,daily_coin,daily_spirit);assert settled['applied']
        row['after_settlement_coin']=state['coin'];row['after_settlement_spirit']=state['spirit']
        rows.append(row)
    old_week=state['week_id'];post_coin,post_spirit=state['coin'],state['spirit']
    boundary=reset_week(state,economy,tower_defs[free_id],old_week)
    repeated=reset_week(state,economy,tower_defs[free_id],old_week)
    return clean({'scenario':scenario,'daily_coin':daily_coin,'daily_spirit':daily_spirit,
                  'initial_purchase_coin':initial_cost,'initial_remaining_coin':wallet['starting_coin']-initial_cost,
                  'before_night_rows':rows,'total_build_coin':spent_build,'total_services_and_reserve_coin':spent_service,
                  'post_week_coin_recorded_then_closed':post_coin,'post_week_spirit_recorded_then_closed':post_spirit,
                  'next_week_coin':state['coin'],'next_week_spirit':state['spirit'],
                  'next_week_defense_instances':[f'free_{free_id}_L1'],'week_boundary':boundary,'repeated_week_reset':repeated,
                  'old_week_command_accepted_after_reset':accepts_week_command(state,old_week),
                  'next_week_id':state['week_id'],'next_week_inventory':[asset_snapshot(a) for a in state['assets'].values()],
                  'next_week_refill_stock':state['refill_stock'],
                  'actual_stock_service_plan_feasible':bool(feasible),
                  'scope':'prepurchase_inventory_phase_gates_finite_budget_and_week_identity_reference_not_runtime_or_combat_probability'})


def stock_pressure_replays(economy,tower_tree,traps):
    """Same earned income, actual 2/4/6 requested nightly uses on owned traps.

    This probes a concrete finite-stock constraint, not combat completion odds.
    Six requests against four loaded uses reports two unserved; it does not
    secretly purchase or deploy the paid backpack reserve after opening.
    """
    scenario=next(s for s in economy['replay_assumptions']['scenarios'] if s['id']=='standard')
    rows=[]
    for demand in (2,4,6):
        candidate=copy.deepcopy(economy)
        candidate['replay_assumptions']['trap_uses_per_night']={k:demand for k in candidate['replay_assumptions']['trap_uses_per_night']}
        result=week_replay(candidate,tower_tree,traps,scenario)
        unserved=sum(event['detail']['unserved'] for day in result['before_night_rows']
                     for event in day['night_uses'] if event.get('action')=='consume')
        final=result['before_night_rows'][-1]
        rows.append({'requested_uses_per_owned_test_trap_per_night':demand,
                     'paid_stock_plan_feasible':result['actual_stock_service_plan_feasible'],
                     'unserved_trigger_count':unserved,'final_l3_towers':final['l3_towers'],
                     'final_l3_traps':final['l3_traps'],'build_coin':result['total_build_coin'],
                     'services_and_reserve_coin':result['total_services_and_reserve_coin'],
                     'scope':'same illustrative earned-income schedule; not actual survival probability'})
    return rows


def unused_stock_week_boundary_fixture(economy,tower_tree,traps):
    """Unopened purchased item plus positive loose ammunition survive six nights
    unchanged, then are cleared with all other week-scoped defense inventory.
    The seven handovers here are authored settled inputs, not simulated play.
    """
    state=preparation_state(economy);old=state['week_id']
    purchase=apply_trap_command(state,{'action':'purchase','week_id':old,'receipt_id':'boundary-buy',
                 'trap_id':'R01','instance_id':'unopened-spare'},economy,traps)
    stock=apply_trap_command(state,{'action':'reload_purchase','week_id':old,'receipt_id':'boundary-stock',
                 'instance_id':'unopened-spare','quantity':4},economy,traps)
    assert purchase['applied'] and stock['applied']
    daily=[]
    for night in range(1,8):
        assert begin_shift(state)['applied']
        assert settle_shift(state,0,0)['applied']
        daily.append({'night':night,'item_location':next(iter(state['assets'].values()))['location'],
                      'paid_item_charges':next(iter(state['assets'].values()))['charges'],
                      'loose_paid_refill_quantity':sum(v['quantity'] for v in state['refill_stock'].values())})
    free=next(n for n in tower_nodes(tower_tree) if n['id']==economy['wallet_policy']['free_job_tower'])
    first=reset_week(state,economy,free,old)
    before=copy.deepcopy(state)
    repeated=reset_week(state,economy,free,old)
    stale=apply_trap_command(state,{'action':'purchase','week_id':old,'receipt_id':'late-old-buy',
                 'trap_id':'R01','instance_id':'late-old-item'},economy,traps)
    return clean({'daily_carry':daily,'first_reset':first,
                  'cleared_positive_refill_quantity':sum(v['quantity'] for v in first['cleared_refill_stock'].values()),
                  'cleared_unopened_spare':any(x['instance_id']=='unopened-spare' and x['location']=='backpack' for x in first['cleared_instances']),
                  'next_week_only_free_job_tower':len(state['assets'])==1 and next(iter(state['assets'].values()))['free_job_asset'],
                  'next_week_loose_refill_quantity':sum(v['quantity'] for v in state['refill_stock'].values()),
                  'repeated_reset_and_old_purchase_rejected_without_mutation':not repeated['applied'] and not stale['applied'] and state==before,
                  'scope':'seven authored settled handovers; not gameplay success simulation'})
