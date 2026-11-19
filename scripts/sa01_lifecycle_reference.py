"""SA01 finite transaction reference, not a game engine or storage adapter.

World/day adapters must supply already verified source facts. Deep copies model
atomic commits in memory; they do not authenticate observations or crash-proof a
production save. No old prototype is changed by importing this module.
"""
from copy import deepcopy
import hashlib
import json
import math


SNAPSHOT_FIELDS = (
    'wallet', 'defenses', 'refill_stock', 'personal', 'resources', 'clocks',
    'cooldowns', 'rng', 'world', 'opening_manifest', 'provisional',
    'day_state', 'night_uses', 'pending_actions', 'attempt_receipts',
)


def encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return hashlib.sha256(encoded(value).encode('utf-8')).hexdigest()


def denied(reason):
    return {'applied': False, 'reason': reason}


def replace(state, draft):
    state.clear()
    state.update(draft)


def night_key(state):
    return encoded([state['campaign_id'], state['week_id'], state['night_index']])


def absolute_night(state):
    return 7 * (state['week_number'] - 1) + state['night_index']


def legacy_night_id(state):
    return 'night:' + str(absolute_night(state))


def free_tower(week_id):
    return {'instance_id': week_id + ':free:T02', 'definition_id': 'T02',
            'week_id': week_id, 'free_base': True, 'paid_coin': 0}


def new_campaign(campaign_id='reference-campaign'):
    if not isinstance(campaign_id, str) or not campaign_id:
        raise ValueError('campaign_id is required')
    week = campaign_id + ':week:1'
    tower = free_tower(week)
    return {
        'schema': 'SA01-reference', 'campaign_id': campaign_id,
        'week_number': 1, 'week_id': week, 'night_index': 1,
        'completed_in_week': 0, 'phase': 'pre_shift',
        'attempt_serial': 0, 'attempt_id': None, 'checkpoint': None,
        'wallet': {'coin': 120, 'spirit': 0},
        'defenses': {tower['instance_id']: tower}, 'refill_stock': {},
        'personal': {'gear': ['Q09', 'Q13', 'Q21'], 'items': {},
                     'tickets': 1, 'fragments': 0,
                     'pity': {'common': 0, 'nonrare': 0},
                     'claims': {}, 'pending_draw': None, 'draw_receipts': {},
                     'loadout': {}, 'consumed': {}},
        'resources': {'energy': 50, 'san': 70, 'satiety': 70, 'stamina': 75},
        'clocks': {'world_s': 0.0, 'game_minute': 1440.0, 'budget_s': 0.0},
        'cooldowns': {},
        'rng': {'state': 'after-preparation', 'director_plan': [], 'content_version': 'SA01'},
        'world': {'entities': {}, 'rule_objects': {}, 'attacks': {}, 'stones': {},
                  'devices': {}, 'panic': {'active': False}, 'manager': {}},
        'opening_manifest': [],
        'provisional': {'orders': {}, 'roots': {}, 'gifts': {}},
        'day_state': {'coffee_debts': [], 'food_claims': {}, 'action_receipts': {}},
        'night_uses': {}, 'pending_actions': {}, 'attempt_receipts': {},
        'stable_awards': {}, 'day_wallet_receipts': {}, 'closed_week_ids': [],
        'meta': {'knowledge_pages': [], 'observation_archive': [], 'week_results': []},
    }


def open_night(state):
    if state['phase'] != 'pre_shift':
        return denied('not_pre_shift')
    key = night_key(state)
    if key in state['stable_awards']:
        return denied('logical_night_already_settled')
    if state['personal']['pending_draw'] is not None or state['pending_actions']:
        return denied('unresolved_preparation_transaction')
    if state['clocks']['budget_s'] != 0 or state['clocks']['game_minute'] != absolute_night(state) * 1440:
        return denied('actual_ready_to_open_clock_required')
    snapshot = {k: deepcopy(state[k]) for k in SNAPSHOT_FIELDS}
    checkpoint = {'night_key': key, 'snapshot': snapshot, 'digest': digest(snapshot)}
    state['checkpoint'] = checkpoint
    state['attempt_serial'] += 1
    state['attempt_id'] = key + ':attempt:' + str(state['attempt_serial'])
    state['phase'] = 'open'
    return {'applied': True, 'night_key': key, 'attempt_id': state['attempt_id']}


def active_guard(state, expected_attempt):
    if state['phase'] != 'open' or state['attempt_id'] != expected_attempt:
        return denied('stale_attempt_or_not_open')
    if state['week_id'] in state['closed_week_ids']:
        return denied('closed_week')
    return None


def advance_world(state, seconds, expected_attempt):
    guard = active_guard(state, expected_attempt)
    if guard:
        return guard
    if not isinstance(seconds, (int, float)) or not math.isfinite(seconds) or seconds < 0:
        return denied('invalid_elapsed_time')
    if state['clocks']['budget_s'] + seconds > 720:
        return denied('past_true_six')
    state['clocks']['world_s'] += seconds
    state['clocks']['budget_s'] += seconds
    state['clocks']['game_minute'] += seconds / 2
    return {'applied': True}


def record_income(state, kind, source_id, expected_attempt, *, verified=False, major_rule=False):
    """Accept a supplied actual order/root fact, never create that fact."""
    guard = active_guard(state, expected_attempt)
    if guard:
        return guard
    if not verified or not isinstance(source_id, str) or not source_id or kind not in ('order', 'root'):
        return denied('verified_declared_source_required')
    bucket = state['provisional']['orders' if kind == 'order' else 'roots']
    if source_id in bucket:
        return denied('source_already_paid')
    if len(bucket) >= (12 if kind == 'order' else 6):
        return denied('authored_source_budget_exceeded')
    coin, spirit = (6, 0) if kind == 'order' else (12, 4 + (2 if major_rule else 0))
    bucket[source_id] = {'coin': coin, 'spirit': spirit, 'night_key': night_key(state)}
    state['wallet']['coin'] += coin
    state['wallet']['spirit'] += spirit
    return {'applied': True, 'coin': coin, 'spirit': spirit}


def consume_personal(state, item_instance_id, effect_id, expected_attempt):
    """Finite item/effect atomicity only; real cast/target admission is external."""
    guard = active_guard(state, expected_attempt)
    if guard:
        return guard
    items = state['personal']['items']
    if item_instance_id not in items or item_instance_id not in state['opening_manifest']:
        return denied('actual_opening_item_required')
    if not isinstance(effect_id, str) or not effect_id:
        return denied('effect_identity_required')
    item = items.pop(item_instance_id)
    state['personal']['consumed'][item_instance_id] = {'effect_id': effect_id, 'item': item}
    state['world'].setdefault('paid_effects', {})[effect_id] = {'source_item': item_instance_id}
    return {'applied': True}


def retry_same_checkpoint(state, expected_attempt, observation=None):
    guard = active_guard(state, expected_attempt)
    if guard:
        return guard
    cp = state.get('checkpoint')
    if not cp or cp['night_key'] != night_key(state) or cp['digest'] != digest(cp['snapshot']):
        return denied('invalid_whole_checkpoint')
    if set(cp['snapshot']) != set(SNAPSHOT_FIELDS) or night_key(state) in state['stable_awards']:
        return denied('incomplete_or_settled_checkpoint')
    draft = deepcopy(state)
    if observation is not None:
        draft['meta']['observation_archive'].append({
            'attempt_id': expected_attempt, 'night_key': night_key(state),
            'outcome': 'failed', 'archive_only': True, 'record': deepcopy(observation)})
    for key in SNAPSHOT_FIELDS:
        draft[key] = deepcopy(cp['snapshot'][key])
    draft['phase'] = 'pre_shift'
    result = open_night(draft)
    if not result['applied']:
        return result
    replace(state, draft)
    return result


def day_wallet_receipt(state, source, receipt_id, *, verified=False, supply_id=None, delta=None, expected_week_id=None):
    """Only the three concrete legacy day consumers are modelled here."""
    if state['phase'] not in ('pre_shift', 'morning') or not verified or not receipt_id:
        return denied('verified_day_action_required')
    if expected_week_id != state['week_id'] or expected_week_id in state['closed_week_ids']:
        return denied('stale_or_missing_source_week')
    if receipt_id in state['day_wallet_receipts']:
        return denied('day_receipt_already_applied')
    prices = {'PC01': 5, 'PC02': 6, 'PC03': 5, 'PC04': 5,
              'PC05': 5, 'PC06': 5, 'PC07': 8, 'PC08': 10}
    if source == 'A09':
        expected = 30
    elif source == 'E062_quiet_sleep':
        expected = -10
    elif source == 'A08_matching_care_supply' and supply_id in prices:
        expected = -prices[supply_id]
    else:
        return denied('source_adapter_not_modelled')
    if delta is not None and delta != expected:
        return denied('authored_amount_mismatch')
    if state['wallet']['coin'] + expected < 0:
        return denied('insufficient_current_week_coin')
    state['wallet']['coin'] += expected
    state['day_wallet_receipts'][receipt_id] = {
        'source': source, 'coin_delta': expected, 'week_id': state['week_id'],
        'supply_id': supply_id, 'verified_external_action': True}
    return {'applied': True, 'coin_delta': expected}


def settle_handover(state, requested_night_key, *, verified=False,
                    unresolved_critical=True, panic_active=True,
                    completed_duties=0, debt_deduction=0):
    """Caller must authenticate original keys, current manager and actual work."""
    if requested_night_key in state['stable_awards']:
        return {'applied': False, 'reason': 'already_settled',
                'original_award': deepcopy(state['stable_awards'][requested_night_key])}
    if state['phase'] != 'open' or requested_night_key != night_key(state):
        return denied('wrong_or_inactive_logical_night')
    if not verified or unresolved_critical or panic_active or state['world']['panic']['active'] or state['resources']['san'] <= 0:
        return denied('actual_safe_handover_required')
    if state['clocks']['budget_s'] != 720:
        return denied('true_six_required')
    if type(completed_duties) is not int or not 0 <= completed_duties <= 6 or type(debt_deduction) is not int or not 0 <= debt_deduction <= 20:
        return denied('authored_work_bounds_required')
    if state['night_index'] != state['completed_in_week'] + 1:
        return denied('sequential_night_required')
    draft = deepcopy(state)
    orders = len(draft['provisional']['orders'])
    wage = 80 + min(40, 4 * completed_duties + 2 * min(8, orders)) - debt_deduction
    draft['wallet']['coin'] += wage
    draft['personal']['tickets'] += 1
    award = {'night_key': requested_night_key, 'week_id': draft['week_id'],
             'legacy_night_id': legacy_night_id(draft), 'wage': wage, 'ticket': 1,
             'orders': orders, 'roots': len(draft['provisional']['roots'])}
    draft['stable_awards'][requested_night_key] = award
    draft['completed_in_week'] += 1
    if draft['night_index'] == 7:
        old_week = draft['week_id']
        draft['meta']['week_results'].append({
            'week_id': old_week, 'completed_nights': 7,
            'closed_coin': draft['wallet']['coin'], 'closed_spirit': draft['wallet']['spirit']})
        draft['closed_week_ids'].append(old_week)
        draft['week_number'] += 1
        draft['week_id'] = draft['campaign_id'] + ':week:' + str(draft['week_number'])
        draft['night_index'] = 1
        draft['completed_in_week'] = 0
        draft['wallet'] = {'coin': 120, 'spirit': 0}
        tower = free_tower(draft['week_id'])
        draft['defenses'] = {tower['instance_id']: tower}
        draft['refill_stock'] = {}
    else:
        draft['night_index'] += 1
    draft['phase'] = 'morning'
    draft['attempt_id'] = None
    draft['checkpoint'] = None
    draft['pending_actions'] = {}
    draft['attempt_receipts'] = {}
    draft['opening_manifest'] = []
    draft['provisional'] = {'orders': {}, 'roots': {}, 'gifts': {}}
    replace(state, draft)
    return {'applied': True, 'award': deepcopy(award)}


def accept_next_preparation(state, *, verified_day_transition=False, resources=None,
                            world_snapshot=None, night_uses=None):
    """Boundary stub for the old day adapter, not simulation of 18 daytime hours.

    The caller supplies fully settled day resources and a prepared world snapshot
    bound to the next logical night, with prior transient objects actually closed.
    Loaded, unspent B05 portions remain in defenses[*].ammo_portions by their
    original portion_id. A fired portion must already have left that inventory;
    its night-scoped bait is torn down rather than refunded. Loading and firing
    are verified by the deployment adapter, not performed at this boundary.
    This function verifies ownership/teardown fields, not how the world achieved
    them. The boundary never heals, clears coffee debt, or advances a cooldown.
    """
    if state['phase'] != 'morning' or not verified_day_transition or resources is None:
        return denied('actual_day_transition_required')
    if set(resources) != {'energy', 'san', 'satiety', 'stamina'} or any(not isinstance(v, (int, float)) or not math.isfinite(v) or v < 0 or v > 100 for v in resources.values()):
        return denied('valid_settled_resources_required')
    if resources['stamina'] > 50 + 0.5 * resources['energy']:
        return denied('stamina_exceeds_actual_energy_cap')
    required = {'entities', 'rule_objects', 'attacks', 'stones', 'devices', 'panic', 'manager'}
    if not isinstance(world_snapshot, dict) or not required.issubset(world_snapshot):
        return denied('actual_prepared_world_snapshot_required')
    if world_snapshot.get('prepared_for_night_key') != night_key(state) or not world_snapshot.get('previous_night_cleanup_receipt'):
        return denied('world_snapshot_must_bind_next_night_and_cleanup')
    if world_snapshot['attacks'] or world_snapshot.get('paid_effects') or world_snapshot['manager'].get('verification'):
        return denied('previous_attack_effect_or_manager_verification_not_cleared')
    retained_b05_portions = {
        portion_id
        for defense in state['defenses'].values()
        if defense.get('definition_id') == 'B05'
        for portion_id in defense.get('ammo_portions', {})
    }
    for section in ('entities', 'rule_objects', 'stones'):
        if not isinstance(world_snapshot[section], dict) or any(
                not isinstance(obj, dict) or obj.get('night_key') != night_key(state)
                for obj in world_snapshot[section].values()):
            return denied('dynamic_world_object_has_old_night_scope')
        if any(object_id in retained_b05_portions or obj.get('portion_id') in retained_b05_portions
               for object_id, obj in world_snapshot[section].items()):
            return denied('week_ammo_cannot_also_be_night_object')
    if not isinstance(night_uses, dict):
        return denied('actual_new_night_use_budget_required')
    state['resources'] = deepcopy(resources)
    state['world'] = deepcopy(world_snapshot)
    state['night_uses'] = deepcopy(night_uses)
    state['clocks']['game_minute'] = float(absolute_night(state) * 1440)
    state['clocks']['budget_s'] = 0.0
    state['phase'] = 'pre_shift'
    return {'applied': True}
