#!/usr/bin/env python3
"""Finite TD04 budget and inventory reference model, not the game runtime.

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
        'location': 'placed', 'footprint': footprint, 'footprint_cells': cells,
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
            'paid_upgrade_coin', 'net_paid_coin', 'footprint_cells')
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
    }
    state['closed_week_ids'].add(expected_week_id)
    state['week_number'] += 1
    state['week_id'] = f'reference-week-{state["week_number"]}'
    state['coin'] = economy['wallet_policy']['starting_coin']
    state['spirit'] = economy['wallet_policy']['starting_spirit']
    state['assets'].clear()  # Contains placed and backpack instances alike.
    state['pending_commands'].clear()
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


def week_replay(economy, tower_tree, traps, scenario):
    """Replay the authored purchase priorities with actual stock and HP.

    Purchases happen only before a night in this comparison. Orders/defeats and
    that night's wage are paid afterwards, so the seventh wage cannot finance
    seventh-night equipment. Upgrade slots become usable stock only when bought.
    """
    tower_defs = {n['id']: n for n in tower_nodes(tower_tree)}
    trap_defs = {t['id']: t for t in traps['traps']}
    definitions = {**tower_defs}
    for trap in trap_defs.values():
        definitions[trap['id']] = {'id': trap['id'], 'parent': None, 'cost': trap['base_cost']}
        for branch in trap['l2']:
            definitions[branch['id']] = branch
            definitions[branch['l3']['id']] = branch['l3']
    wallet, income, replay = economy['wallet_policy'], economy['income'], economy['replay_assumptions']
    assert 0 <= scenario['orders'] <= income['order_limit_per_night']
    assert 0 <= scenario['major_rules'] <= scenario['roots'] <= income['new_root_slots_per_night']
    performance = scenario.get('performance_bonus', income['performance_bonus_in_base_replays'])
    assert 0 <= performance <= income['performance_bonus_max']
    daily_coin = (scenario['orders'] * income['coin_per_valid_order']
                  + scenario['roots'] * income['coin_per_unique_root_defeat']
                  + income['completed_handover_wage'] + performance)
    daily_spirit = (scenario['roots'] * income['spirit_per_unique_root_defeat']
                    + scenario['major_rules'] * income['spirit_bonus_per_real_major_rule'])
    state = {'week_number': 1, 'week_id': 'reference-week-1',
             'coin': wallet['starting_coin'], 'spirit': wallet['starting_spirit'],
             'assets': {}, 'pending_commands': [], 'closed_week_ids': set(), 'completed_nights': 0}
    free_id = wallet['free_job_tower']
    state['assets'][free_id] = make_tower_asset(tower_defs[free_id], state['week_id'], free_job=True)
    initial, initial_cost = [], 0
    for authored in replay['minimum_starting_build']:
        if authored.startswith('free_'):
            assert authored[5:] == free_id
            continue
        match = re.fullmatch(r'([TR]\d{2})(?:_(\d+)x(\d+))?_L1', authored)
        if not match:
            raise ValueError('unrecognized authored initial build')
        root = match.group(1)
        if root.startswith('T'):
            asset = make_tower_asset(tower_defs[root], state['week_id'])
        else:
            footprint = None if match.group(2) is None else [int(match.group(2)), int(match.group(3))]
            asset = make_trap_asset(trap_defs[root], economy, footprint, state['week_id'])
        assert _capacity_ok(state['assets'], asset, economy)
        assert asset['paid_base_coin'] <= state['coin']
        state['coin'] -= asset['paid_base_coin']
        state['assets'][root] = asset
        initial_cost += asset['paid_base_coin']
        initial.append(root)
    rows, spent_build, spent_service, feasible = [], initial_cost, 0, True
    for night in range(1, wallet['week_days'] + 1):
        brought = [asset_snapshot(a) for a in state['assets'].values()]
        bought, service_events, upgrade_events, service = [], [], [], 0
        if night > 1:
            reserve = replay['non_defense_consumables_per_completed_night_coin']
            affordable = min(reserve, state['coin'])
            feasible &= affordable == reserve
            state['coin'] -= affordable
            service += affordable
            service_events.append({'kind': 'explicit_test_consumable_reserve', 'coin': affordable,
                                   'requested': reserve, 'is_new_game_tax': False})
            for asset in state['assets'].values():
                if asset['kind'] != 'trap':
                    continue
                if asset['charge_capacity'] is not None:
                    event = refill_missing(asset, economy, state['coin'])
                    state['coin'] -= event['coin']; service += event['coin']
                    feasible &= event['unfilled'] == 0
                    service_events.append(event)
                if asset['max_hp'] is not None and asset['hp'] < asset['max_hp']:
                    event = repair_missing(asset, economy, state['coin'])
                    state['coin'] -= event['coin']; service += event['coin']
                    feasible &= event['unrepaired_hp'] == 0
                    service_events.append(event)
            spent_service += service
            for nid in replay['purchase_priority']:
                node = definitions[nid]
                root = nid.split('.')[0]
                asset = state['assets'].get(root)
                if asset and nid in asset['path']:
                    continue
                parent = node.get('parent')
                if parent and (asset is None or asset['node_id'] != parent):
                    continue
                if not parent and asset:
                    continue
                candidate = None
                if not parent:
                    candidate = (make_tower_asset(node, state['week_id']) if root.startswith('T')
                                 else make_trap_asset(trap_defs[root], economy, week_id=state['week_id']))
                    if not _capacity_ok(state['assets'], candidate, economy):
                        continue
                    cost = {'coin': candidate['base_coin'], 'spirit': node['cost']['spirit']}
                else:
                    cost = {k: node['cost'][k] for k in ('coin', 'spirit')}
                    if node['cost'].get('basis') == 'per_actual_footprint_cell':
                        cost = {k: v * asset['footprint_cells'] for k, v in cost.items()}
                if state['coin'] < cost['coin'] or state['spirit'] < cost['spirit']:
                    continue
                state['coin'] -= cost['coin']; state['spirit'] -= cost['spirit']
                spent_build += cost['coin']; bought.append(nid)
                if candidate:
                    state['assets'][root] = candidate
                    upgrade_events.append({'kind': 'build', 'node': nid, 'paid_cost': cost,
                                           'after': asset_snapshot(candidate)})
                else:
                    event = upgrade_inventory(asset, node, economy, cost)
                    event.update(kind='upgrade', node=nid)
                    upgrade_events.append(event)
        towers = {root: a['tier'] for root, a in state['assets'].items() if a['kind'] == 'tower'}
        trap_states = {root: a['tier'] for root, a in state['assets'].items() if a['kind'] == 'trap'}
        row = {'night': night, 'week_id': state['week_id'],
               'before_night_coin': state['coin'], 'before_night_spirit': state['spirit'],
               'purchases': bought if night > 1 else initial,
               'service_and_reserve_before_night_coin': service,
               'service_events': service_events, 'purchase_events': upgrade_events,
               'inventory_brought_from_previous_night': brought,
               'inventory_before_night': [asset_snapshot(a) for a in state['assets'].values()],
               'tower_count': len(towers), 'tower_tiers': towers,
               'l3_towers': sum(tier == 3 for tier in towers.values()),
               'trap_count': len(trap_states), 'trap_tiers': trap_states,
               'trap_footprint_tiles': sum(a['footprint_cells'] for a in state['assets'].values()),
               'l3_traps': sum(tier == 3 for tier in trap_states.values()),
               'income_after_night_coin': daily_coin, 'income_after_night_spirit': daily_spirit,
               'handover_wage_only_after_this_night': income['completed_handover_wage']}
        uses = []
        for root, requested in replay['trap_uses_per_night'].items():
            if root in state['assets']:
                event = consume_charges(state['assets'][root], requested)
                event['root'] = root; uses.append(event)
                feasible &= event['unserved'] == 0
        barrier = state['assets'].get('R12')
        if barrier:
            loss = min(barrier['hp'], q(replay['barrier_hp_fraction_lost_per_night']) * barrier['max_hp'])
            barrier['hp'] -= loss
            uses.append(clean({'root': 'R12', 'kind': 'authored_barrier_damage', 'hp_lost': loss,
                               'hp_after': barrier['hp'], 'max_hp': barrier['max_hp']}))
        row['night_uses'] = uses
        row['inventory_after_night'] = [asset_snapshot(a) for a in state['assets'].values()]
        state['coin'] += daily_coin; state['spirit'] += daily_spirit
        state['completed_nights'] = night
        row['after_settlement_coin'] = state['coin']; row['after_settlement_spirit'] = state['spirit']
        rows.append(row)
    old_week_id = state['week_id']
    post_coin, post_spirit = state['coin'], state['spirit']
    boundary = reset_week(state, economy, tower_defs[free_id], old_week_id)
    repeated = reset_week(state, economy, tower_defs[free_id], old_week_id)
    return clean({'scenario': scenario, 'daily_coin': daily_coin, 'daily_spirit': daily_spirit,
                  'initial_purchase_coin': initial_cost,
                  'initial_remaining_coin': wallet['starting_coin'] - initial_cost,
                  'before_night_rows': rows, 'total_build_coin': spent_build,
                  'total_services_and_reserve_coin': spent_service,
                  'post_week_coin_recorded_then_closed': post_coin,
                  'post_week_spirit_recorded_then_closed': post_spirit,
                  'next_week_coin': state['coin'], 'next_week_spirit': state['spirit'],
                  'next_week_defense_instances': [f'free_{free_id}_L1'],
                  'week_boundary': boundary, 'repeated_week_reset': repeated,
                  'old_week_command_accepted_after_reset': accepts_week_command(state, old_week_id),
                  'next_week_id': state['week_id'],
                  'next_week_inventory': [asset_snapshot(a) for a in state['assets'].values()],
                  'actual_stock_service_plan_feasible': bool(feasible),
                  'scope': 'finite_budget_inventory_and_week_identity_reference_not_runtime_or_combat_probability'})
