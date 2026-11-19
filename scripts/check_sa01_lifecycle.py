"""Targeted finite SA01 lifecycle cases; no runtime or full-week balance claim."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from sa01_lifecycle_reference import (
    SNAPSHOT_FIELDS, accept_next_preparation, advance_world, consume_personal,
    day_wallet_receipt as apply_day_wallet_receipt, digest, encoded, legacy_night_id, new_campaign,
    night_key, open_night, record_income, retry_same_checkpoint, settle_handover,
)

ROOT = Path(__file__).resolve().parents[1]
checks = []


def check(label, value, evidence=None):
    checks.append({'id': label, 'passed': bool(value), 'evidence': evidence})


def unchanged(label, state, command):
    before = deepcopy(state)
    result = command()
    check(label, not result['applied'] and state == before, result)
    return result


def complete(state):
    key = night_key(state)
    advance_world(state, 720-state['clocks']['budget_s'], state['attempt_id'])
    return settle_handover(state, key, verified=True, unresolved_critical=False, panic_active=False)


def day_wallet_receipt(state, *args, **kwargs):
    # Test inputs explicitly bind their source week; the real API rejects omission.
    kwargs.setdefault('expected_week_id', state['week_id'])
    return apply_day_wallet_receipt(state, *args, **kwargs)


def cleared_world_fixture(state):
    # An explicit prepared-world input, not a claim that this model ran teardown.
    return {'entities': {}, 'rule_objects': {}, 'attacks': {}, 'stones': {},
            'devices': deepcopy(state['world']['devices']),
            'panic': {'active': False}, 'manager': {}, 'paid_effects': {},
            'prepared_for_night_key': night_key(state),
            'previous_night_cleanup_receipt': 'verified-cleanup:' + night_key(state)}


def next_preparation(state):
    return accept_next_preparation(state, verified_day_transition=True,
                                   resources=deepcopy(state['resources']),
                                   world_snapshot=cleared_world_fixture(state),
                                   night_uses={'free_stabilization': 1})


# Same visible day number in different weeks used to collide if passed directly
# to the old [campaignId, nightId] ledger. The adapter now supplies absolute IDs.
a = new_campaign('same-campaign')
b = deepcopy(a)
b.update(week_number=2, week_id='same-campaign:week:2')
check('legacy_local_night_counterexample', encoded([a['campaign_id'], 1]) == encoded([b['campaign_id'], 1]),
      'Hypothetical direct wiring collision; old prototype remains unchanged.')
check('canonical_week_distinguishes_night', night_key(a) != night_key(b))
check('legacy_adapter_absolute_1_vs_8', legacy_night_id(a) == 'night:1' and legacy_night_id(b) == 'night:8')

# A committed pre-opening draw and all paid setup precede the retry checkpoint.
s = new_campaign('retry-case')
s['personal'].update(tickets=0, pity={'common': 1, 'nonrare': 1},
                     draw_receipts={'draw-1': {'reward': 'I25', 'units': 2}})
s['personal']['items'] = {'item-1': {'definition_id': 'I25'}, 'item-2': {'definition_id': 'I25'}}
s['opening_manifest'] = ['item-1', 'item-2']
s['defenses']['trap-1'] = {'instance_id': 'trap-1', 'hp': 80, 'charges': 3, 'week_id': s['week_id']}
s['refill_stock'] = {'R01': 2}
s['day_state']['coffee_debts'] = [{'id': 'coffee-1', 'due_game_minute': 1480, 'settled': False}]
s['day_state']['food_claims'] = {'day:1': 'already-claimed'}
s['cooldowns'] = {'mobility': 12.0}
s['night_uses'] = {'free_stabilization': 1}
s['rng'] = {'state': 'after-draw-before-night', 'director_plan': ['fixed-root-1'], 'content_version': 'SA01'}
check('opens_complete_preparation', open_night(s)['applied'])
old_attempt = s['attempt_id']
snapshot = deepcopy(s['checkpoint']['snapshot'])
check('consumes_real_opening_item', consume_personal(s, 'item-1', 'speed-buff-1', old_attempt)['applied'])
check('records_actual_provisional_order', record_income(s, 'order', 'order-1', old_attempt, verified=True)['applied'])
check('records_actual_provisional_root', record_income(s, 'root', 'fixed-root-1', old_attempt, verified=True, major_rule=True)['applied'])
advance_world(s, 50, old_attempt)
s['resources'].update(san=0, stamina=2)
s['world']['panic']['active'] = True
s['world']['attacks'] = {'old-attack': {'already_hit': True}}
s['world']['stones'] = {'stone-1': 'in_flight'}
s['world']['manager'] = {'false_late_check': True}
s['rng']['state'] = 'after-night-random-draws'
s['cooldowns']['mobility'] = 80.0
s['day_state']['coffee_debts'][0]['settled'] = True
s['day_state']['food_claims']['forbidden-new-day'] = 'failed-attempt-only'
s['night_uses']['free_stabilization'] = 0
s['defenses']['trap-1'].update(hp=12, charges=0)
s['refill_stock']['R01'] = 0
s['personal']['items']['failed-gift'] = {'definition_id': 'I04'}
s['attempt_receipts']['consumed'] = 'old-receipt'
s['pending_actions']['in-progress'] = {'source': 'item-2'}
check('retry_applies_whole_checkpoint', retry_same_checkpoint(s, old_attempt, {'seen': 'actual failed attack'} )['applied'])
check('all_snapshot_partitions_match', all(s[k] == snapshot[k] for k in SNAPSHOT_FIELDS))
check('retry_changes_attempt_not_logical_night', s['attempt_id'] != old_attempt and night_key(s) == s['checkpoint']['night_key'])
check('spent_item_restored_without_paid_buff', 'item-1' in s['personal']['items'] and not s['world'].get('paid_effects'))
check('failed_gift_not_retained', 'failed-gift' not in s['personal']['items'])
check('failed_coin_and_spirit_reverted', s['wallet'] == {'coin': 120, 'spirit': 0})
check('trap_charge_hp_stock_reverted', s['defenses']['trap-1']['hp'] == 80 and s['defenses']['trap-1']['charges'] == 3 and s['refill_stock']['R01'] == 2)
check('resources_panic_and_free_use_reverted', s['resources']['san'] == 70 and not s['world']['panic']['active'] and s['night_uses']['free_stabilization'] == 1)
check('clocks_cooldown_and_rng_reverted_together', s['clocks'] == snapshot['clocks'] and s['cooldowns'] == snapshot['cooldowns'] and s['rng'] == snapshot['rng'])
check('coffee_and_daily_food_receipts_reverted_together', s['day_state'] == snapshot['day_state'])
check('preopening_draw_and_pity_remain_committed', s['personal']['tickets'] == 0 and s['personal']['draw_receipts'] == snapshot['personal']['draw_receipts'] and s['personal']['pity'] == snapshot['personal']['pity'])
check('observation_retained_only_as_failed_archive', len(s['meta']['observation_archive']) == 1 and s['meta']['observation_archive'][0]['archive_only'] and s['meta']['observation_archive'][0]['outcome'] == 'failed')
unchanged('old_attempt_command_rejected', s, lambda: record_income(s, 'order', 'late-order', old_attempt, verified=True))
check('same_root_can_be_paid_once_in_retried_attempt', record_income(s, 'root', 'fixed-root-1', s['attempt_id'], verified=True, major_rule=True)['applied'])
unchanged('root_duplicate_rejected', s, lambda: record_income(s, 'root', 'fixed-root-1', s['attempt_id'], verified=True, major_rule=True))
unchanged('unverified_income_rejected', s, lambda: record_income(s, 'root', 'invented', s['attempt_id']))
unchanged('unknown_income_type_rejected', s, lambda: record_income(s, 'child', 'new-child', s['attempt_id'], verified=True))
unchanged('early_handover_rejected', s, lambda: settle_handover(s, night_key(s), verified=True, unresolved_critical=False, panic_active=False))

# Invalid snapshots and unresolved pre-opening random rewards cannot be retried
# into a partial restore or quietly rerolled.
bad = deepcopy(s)
bad['checkpoint']['snapshot']['wallet']['coin'] += 1
unchanged('tampered_snapshot_rejected', bad, lambda: retry_same_checkpoint(bad, bad['attempt_id']))
bad = deepcopy(s)
del bad['checkpoint']['snapshot']['cooldowns']
bad['checkpoint']['digest'] = digest(bad['checkpoint']['snapshot'])
unchanged('partial_snapshot_rejected', bad, lambda: retry_same_checkpoint(bad, bad['attempt_id']))
bad = deepcopy(s)
bad['checkpoint']['night_key'] = 'another-night'
unchanged('wrong_night_snapshot_rejected', bad, lambda: retry_same_checkpoint(bad, bad['attempt_id']))
pending = new_campaign('pending')
pending['personal']['pending_draw'] = {'draw_id': 'fixed-unresolved-choice'}
unchanged('pending_draw_blocks_opening', pending, lambda: open_night(pending))

# Full seven-night boundary and the second week's first wage.
w = new_campaign('week-case')
w['personal']['gear'].append('Q06')
w['personal']['items'] = {'keep-item': {'definition_id': 'I41'}, 'unused-I16': {'definition_id': 'I16'}}
w['personal']['claims'] = {'fixed-claim': {'definition_id': 'I25', 'units': 2}}
w['personal']['fragments'] = 2
w['personal']['pity'] = {'common': 3, 'nonrare': 6}
w['personal']['draw_receipts'] = {'existing-draw': {'reward': 'Q06'}}
w['cooldowns'] = {'mobility': 10000.0}
w['world']['devices'] = {'fridge-fixed': {'powered': True, 'door': 'closed'}}
w['day_state']['coffee_debts'] = [{'id': 'late-coffee', 'due_game_minute': 10400, 'settled': False}]
w['defenses']['paid-trap'] = {'instance_id': 'paid-trap', 'week_id': w['week_id'], 'hp': 33, 'charges': 1}
# The separate deployment bridge has already moved this same I16 out of personal
# inventory. This reference checks lifecycle partitions, not placement legality.
w['defenses']['deployed-I16'] = {'instance_id': 'deployed-I16', 'definition_id': 'I16', 'week_id': w['week_id'], 'source_kind': 'converted_personal_item'}
w['defenses']['legacy-B01'] = {'instance_id': 'legacy-B01', 'definition_id': 'B01', 'week_id': w['week_id'], 'charges': 1}
w['defenses']['legacy-B05'] = {
    'instance_id': 'legacy-B05', 'definition_id': 'B05', 'week_id': w['week_id'],
    'ammo_portions': {'week-ammo': {'portion_id': 'week-ammo', 'source': 'paperclip_supply'}}}
w['refill_stock'] = {'R16': 4}
first_key = night_key(w)
seventh_key = None
for i in range(1, 8):
    check('week_night_%s_opens' % i, open_night(w)['applied'])
    w['world']['attacks'] = {'ended-old-attack': {'night_key': night_key(w)}}
    w['world']['paid_effects'] = {'old-short-buff': {'night_key': night_key(w)}}
    w['world']['stones'] = {'old-night-stone': {'night_key': night_key(w), 'location': 'landed'}}
    if i == 7:
        seventh_key = night_key(w)
    result = complete(w)
    check('week_night_%s_settles_once' % i, result['applied'] and result['award']['ticket'] == 1)
    unchanged('week_night_%s_duplicate_handover' % i, w,
              lambda key=result['award']['night_key']: settle_handover(w, key))
    if i != 7:
        check('week_night_%s_day_adapter_boundary' % i,
              next_preparation(w)['applied'])
        check('week_night_%s_transients_not_carried' % i,
              not w['world']['attacks'] and not w['world']['paid_effects'] and not w['world']['stones'])
check('week_two_current_identity', w['week_number'] == 2 and w['night_index'] == 1 and legacy_night_id(w) == 'night:8')
check('week_clear_coin_spirit_exact', w['wallet'] == {'coin': 120, 'spirit': 0})
check('week_clear_defenses_and_stock', len(w['defenses']) == 1 and next(iter(w['defenses'].values()))['definition_id'] == 'T02' and not w['refill_stock'])
check('week_keeps_personal_gear_items_claims', 'Q06' in w['personal']['gear'] and 'keep-item' in w['personal']['items'] and 'fixed-claim' in w['personal']['claims'])
check('week_clears_deployed_I16_and_B_without_refund', 'deployed-I16' not in w['defenses'] and 'legacy-B01' not in w['defenses'] and 'deployed-I16' not in w['personal']['items'])
check('week_clears_B05_loaded_ammo_without_personal_refund', 'legacy-B05' not in w['defenses'] and 'week-ammo' not in w['personal']['items'])
check('week_keeps_only_unused_personal_I16', 'unused-I16' in w['personal']['items'])
check('week_keeps_tickets_fragments_pity_draws', w['personal']['tickets'] == 8 and w['personal']['fragments'] == 2 and w['personal']['pity'] == {'common': 3, 'nonrare': 6} and 'existing-draw' in w['personal']['draw_receipts'])
check('week_keeps_cooldowns_and_coffee_debt', w['cooldowns']['mobility'] == 10000.0 and w['day_state']['coffee_debts'][0]['id'] == 'late-coffee')
check('week_records_then_closes_last_wage', w['meta']['week_results'][0]['closed_coin'] == 120+7*80)
check('zero_orders_safe_handover_still_earns_ticket', all(x['orders'] == 0 and x['ticket'] == 1 for x in w['stable_awards'].values()))
unchanged('old_week_handover_cannot_credit_new_week', w, lambda: settle_handover(w, seventh_key))
unchanged('no_unverified_day_jump', w, lambda: accept_next_preparation(w, resources=deepcopy(w['resources'])))
unchanged('over_capacity_day_stamina_rejected', w, lambda: accept_next_preparation(w, verified_day_transition=True, resources={'energy': 0, 'san': 10, 'satiety': 10, 'stamina': 100}))
unchanged('old_week_day_income_cannot_credit_new_week', w, lambda: day_wallet_receipt(w, 'A09', 'old-week-late-slot', verified=True, expected_week_id='week-case:week:1'))
unchanged('no_prepared_world_snapshot_rejected', w, lambda: accept_next_preparation(w, verified_day_transition=True, resources=deepcopy(w['resources']), night_uses={}))
stale_world = cleared_world_fixture(w)
stale_world['stones'] = {'old-night-stone': {'night_key': seventh_key, 'location': 'landed'}}
unchanged('old_night_stone_snapshot_rejected', w, lambda: accept_next_preparation(w, verified_day_transition=True, resources=deepcopy(w['resources']), world_snapshot=stale_world, night_uses={}))
stale_world = cleared_world_fixture(w)
stale_world['paid_effects'] = {'old-short-buff': {'night_key': seventh_key}}
unchanged('old_short_effect_snapshot_rejected', w, lambda: accept_next_preparation(w, verified_day_transition=True, resources=deepcopy(w['resources']), world_snapshot=stale_world, night_uses={}))
next_preparation(w)
check('fixed_device_state_is_preserved_by_prepared_snapshot', w['world']['devices'] == {'fridge-fixed': {'powered': True, 'door': 'closed'}})
check('new_night_free_use_requires_new_snapshot', w['night_uses'] == {'free_stabilization': 1})
open_night(w)
second_week_first_key = night_key(w)
check('week_two_first_key_is_new', second_week_first_key != first_key)
check('second_week_first_wage_is_not_suppressed', complete(w)['applied'] and w['wallet']['coin'] == 200 and w['personal']['tickets'] == 9)
unchanged('settled_night_cannot_retry', w, lambda: retry_same_checkpoint(w, 'discarded-attempt'))

# Supplied B05 load/fire facts follow the deployment bridge. This model checks
# the ownership boundary, not whether the original taking/loading/firing was legal.
b05 = new_campaign('b05-ammo-case')
b05['defenses']['loaded-B05'] = {
    'instance_id': 'loaded-B05', 'definition_id': 'B05', 'week_id': b05['week_id'],
    'ammo_portions': {
        'keep-original': {'portion_id': 'keep-original', 'source': 'paperclip_supply',
                          'source_night_key': night_key(b05)},
        'fired-original': {'portion_id': 'fired-original', 'source': 'paperclip_supply',
                           'source_night_key': night_key(b05)}}}
open_night(b05)
b05_old_key = night_key(b05)
fired = b05['defenses']['loaded-B05']['ammo_portions'].pop('fired-original')
b05['world']['rule_objects']['fired-bait'] = {
    'portion_id': fired['portion_id'], 'source_definition_id': 'B05',
    'night_key': b05_old_key, 'kind': 'paperclip_bait'}
retained_ammo = deepcopy(b05['defenses']['loaded-B05']['ammo_portions'])
check('B05_fixture_actual_handover', complete(b05)['applied'])
stale_bait_world = cleared_world_fixture(b05)
stale_bait_world['rule_objects'] = deepcopy(b05['world']['rule_objects'])
unchanged('B05_emitted_old_night_bait_cannot_carry', b05,
          lambda: accept_next_preparation(b05, verified_day_transition=True,
                                         resources=deepcopy(b05['resources']),
                                         world_snapshot=stale_bait_world, night_uses={}))
duplicate_ammo_world = cleared_world_fixture(b05)
duplicate_ammo_world['rule_objects']['copied-original'] = {
    'portion_id': 'keep-original', 'night_key': night_key(b05), 'kind': 'paperclip_supply'}
unchanged('B05_week_ammo_cannot_be_rekeyed_as_new_night_copy', b05,
          lambda: accept_next_preparation(b05, verified_day_transition=True,
                                         resources=deepcopy(b05['resources']),
                                         world_snapshot=duplicate_ammo_world, night_uses={}))
check('B05_prepared_world_accepts_retained_week_ammo', next_preparation(b05)['applied'])
check('B05_unspent_original_keeps_identity_and_source_night',
      b05['defenses']['loaded-B05']['ammo_portions'] == retained_ammo
      and retained_ammo['keep-original']['source_night_key'] == b05_old_key)
check('B05_emitted_bait_cleared_without_ammo_refund',
      not b05['world']['rule_objects']
      and 'fired-original' not in b05['defenses']['loaded-B05']['ammo_portions']
      and 'fired-original' not in b05['personal']['items'])

# The old day consumers all change one weekly coin balance, once.
d = new_campaign('day-case')
check('A09_existing_amount_maps_once', day_wallet_receipt(d, 'A09', 'day:1:slot:1', verified=True)['applied'] and d['wallet']['coin'] == 150)
unchanged('unbound_source_week_rejected', d, lambda: apply_day_wallet_receipt(d, 'A09', 'unbound', verified=True))
unchanged('A09_duplicate_does_not_double_pay', d, lambda: day_wallet_receipt(d, 'A09', 'day:1:slot:1', verified=True))
check('quiet_rest_uses_same_wallet', day_wallet_receipt(d, 'E062_quiet_sleep', 'day:1:slot:2', verified=True)['applied'] and d['wallet']['coin'] == 140)
check('pet_care_uses_actual_matching_price', day_wallet_receipt(d, 'A08_matching_care_supply', 'day:1:slot:3', verified=True, supply_id='PC08')['applied'] and d['wallet']['coin'] == 130)
unchanged('unknown_coin_source_rejected', d, lambda: day_wallet_receipt(d, 'unimplemented_bonus', 'invented', verified=True, delta=100))
unchanged('altered_A09_amount_rejected', d, lambda: day_wallet_receipt(d, 'A09', 'day:1:slot:4', verified=True, delta=300))
poor = new_campaign('poor')
poor['wallet']['coin'] = 0
unchanged('insufficient_quiet_rest_keeps_state', poor, lambda: day_wallet_receipt(poor, 'E062_quiet_sleep', 'quiet', verified=True))
open_night(d)
unchanged('day_money_cannot_arrive_during_business', d, lambda: day_wallet_receipt(d, 'A09', 'late', verified=True))

# Explicit supplied safety conditions do not manufacture their own witnesses.
g = new_campaign('gates')
open_night(g)
advance_world(g, 720, g['attempt_id'])
unchanged('missing_manager_evidence_blocks_handover', g, lambda: settle_handover(g, night_key(g), unresolved_critical=False, panic_active=False))
unchanged('unresolved_threat_blocks_handover', g, lambda: settle_handover(g, night_key(g), verified=True, panic_active=False))
g['resources']['san'] = 0
unchanged('zero_SAN_blocks_handover', g, lambda: settle_handover(g, night_key(g), verified=True, unresolved_critical=False, panic_active=False))
g['resources']['san'] = 10
g['world']['panic']['active'] = True
unchanged('actual_panic_blocks_false_clear_flag', g, lambda: settle_handover(g, night_key(g), verified=True, unresolved_critical=False, panic_active=False))

input_paths = ['content/run_lifecycle_sa01.json', 'scripts/sa01_lifecycle_reference.py',
               'scripts/check_sa01_lifecycle.py', 'content/economy_week_td05.json',
               'content/equipment_contracts_eq01.json', 'content/lottery_rewards_eq01.json',
               'content/balance.json', 'content/pets.json',
               'content/legacy_deployment_bridge_sa01.json']
report = {
    'version': 'SA01', 'runtime_integrated': False,
    'scope': 'Finite transaction state with supplied verified facts; no actual world, full calendar, production persistence or game completion proof.',
    'input_hashes': {p: hashlib.sha256((ROOT/p).read_bytes()).hexdigest() for p in input_paths},
    'passed': sum(x['passed'] for x in checks), 'failed': sum(not x['passed'] for x in checks),
    'checks': checks,
    'counterexample_interpretation': 'The old week-local night wiring is a demonstrated key collision under naive composition. Partial rollback is an identified integration risk, not a claim that a complete shipped runtime had this bug.',
    'not_covered': ['Authenticating source receipts', 'Old day action and pet adapter implementation',
                    'All actual world fields/AI restoration', 'Database crash recovery or external save tampering',
                    'Complete 105-monster night, phase schedules and seventh-night incentives'],
}
target = ROOT/'docs/sa01_lifecycle_report.json'
target.write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
print(json.dumps({'passed': report['passed'], 'failed': report['failed'], 'report': str(target)}, ensure_ascii=False))
if report['failed']:
    print(json.dumps([x for x in checks if not x['passed']], ensure_ascii=False, indent=2))
    raise SystemExit(1)
