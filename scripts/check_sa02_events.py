#!/usr/bin/env python3
"""Validate explicit migration coverage and bounded economic counterexamples."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
from sa02_event_reference import new_state, command_for, runtime_admission, apply_reference

ROOT = Path(__file__).resolve().parents[1]
contract = json.loads((ROOT / 'content/event_migrations_sa02.json').read_text())
legacy = json.loads((ROOT / 'content/event_contracts_v010.json').read_text())
rows = []


def check(name, condition, detail=None):
    rows.append({'name': name, 'passed': bool(condition), 'detail': detail})


def facts(source='actual-source-1', **values):
    return {'validated_completion': True, 'source_receipt_id': source, **values}


def run(state, branch, evidence=None, receipt='command-1', **overrides):
    command = command_for(state, branch.split(':')[0], branch, receipt, evidence or facts())
    command.update(overrides)
    return apply_reference(state, contract, command)


def reject(name, state, branch, evidence=None, receipt='command-1', **overrides):
    before = deepcopy(state)
    result = run(state, branch, evidence, receipt, **overrides)
    check(name, not result['applied'] and state == before, result)


ids = [e['id'] for e in contract['entries']]
check('exactly_72_original_IDs_not_72_new_runtime_adapters', len(ids) == 72 and set(ids) == {e['id'] for e in legacy['events']} and len(set(ids)) == 72)
check('review_scope_24_boundary_reviews_48_not_reaudited', contract['catalog_counts'] == {'indexed_total': 72, 'targeted_boundary_reviews': 24, 'not_reaudited': 48, 'runtime_enabled': 0})
check('explicitly_not_a_runtime_integration', contract['runtime_integrated'] is False and contract['reference_fixture_only'] is True)
old = {e['id']: e for e in legacy['events']}
for entry in contract['entries']:
    check(entry['id'] + '_source_and_branches_preserved', entry['legacy_source'] == old[entry['id']]['source'] and entry['legacy_branch_ids'] == [b['id'] for b in old[entry['id']]['branches']])
    check(entry['id'] + '_runtime_closed_even_after_finite_validation', entry['runtime_enabled'] is False and not runtime_admission(contract, entry['id'])['applied'])

for event in ('E040', 'E045', 'E046', 'E047', 'E051', 'E052', 'E071'):
    for night in (1, 7):
        s = new_state(); s['night_index'] = night
        s['phase'] = 'open' if old[event]['phase'] == 'night' else 'pre_shift'
        reject(event + '_night_' + str(night) + '_has_no_unmigrated_purchase_or_loan', s, event + ':B1')
reject('unreviewed_original_event_is_not_auto_enabled_by_old_flag', new_state(), 'E001:B1')
reject('unknown_event_has_no_side_effects', new_state(), 'E999:B1')
reject('unknown_branch_has_no_side_effects', new_state(), 'E054:B9')
reject('transport_fee_waits_for_its_real_adapter', new_state(), 'E048:B2')
reject('free_transport_reservation_is_not_claimed_as_implemented', new_state(), 'E048:B1')

# Static witness of the OLD authored quote, not an assertion that its client ran.
old_recycle_fraction = old['E066']['mechanic_details']['quote_fraction']
legacy_quote_witness = int(min(60, 42) * old_recycle_fraction)
check('legacy_contract_quote_would_be_eight_for_42_paid_item', legacy_quote_witness == 8, {'scope': 'authored arithmetic, not legacy runtime execution', 'paid': 42, 'catalog': 60, 'quote': legacy_quote_witness})
s = new_state(); s['week_id'] = 'fixture-week-2'
s['items']['old-personal-I21'] = {'definition_id': 'I21', 'location': 'carried', 'acquisition_week': 'fixture-week-1', 'actual_paid': 42}
reject('cross_week_personal_asset_cannot_sell_into_new_week', s, 'E066:B2', facts(object_id='old-personal-I21'))
result = run(s, 'E066:B1', facts(object_id='old-personal-I21'))
check('same_cross_week_personal_object_can_be_stored_without_money', result['applied'] and s['coin'] == 120 and s['items']['old-personal-I21']['location'] == 'personal_storage')
reject('no_second_store_of_same_already_stored_object', s, 'E066:B1', facts('other-store', object_id='old-personal-I21'), receipt='other-command')
s = new_state(); s['storage_capacity'] = 0
s['items']['owned'] = {'definition_id': 'I21', 'location': 'carried'}
reject('full_storage_does_not_erase_item_or_create_coin', s, 'E066:B1', facts(object_id='owned'))
reject('unknown_item_does_not_get_guessed_catalog_price', new_state(), 'E066:B2', facts(object_id='unknown', product_price=999))

s = new_state(); s['phase'] = 'day'
job = facts(action_id='A09', slots_used=1, energy_delta=-12)
result = run(s, 'E054:B1', job)
check('actual_A09_routes_exactly_30_to_one_week_wallet', result['applied'] and s['coin'] == 150 and result['coin_delta'] == 30)
reject('same_job_original_receipt_cannot_pay_again_with_new_command', s, 'E054:B1', job, receipt='renamed-command')
reject('A09_does_not_duplicate_already_credited_legacy_wallet', new_state(), 'E054:B1', {**job, 'credited_to_legacy_wallet': True})
reject('unknown_coin_delta_not_accepted', new_state(), 'E054:B1', {**job, 'coin_delta': 300})
reject('fake_job_without_real_action_costs_denied', new_state(), 'E054:B1', {**job, 'energy_delta': 0})
reject('unverified_job_denied', new_state(), 'E054:B1', {**job, 'validated_completion': False})
reject('old_week_job_receipt_not_paid_into_new_week', new_state(), 'E054:B1', job, week_id='closed-old-week')
reject('old_attempt_command_rejected', new_state(), 'E054:B1', job, attempt_id='stale-attempt')

s = new_state(); s['phase'] = 'open'
result = run(s, 'E038:B1', facts(actual_passage_completed=True, original_strip_returned=True))
check('actual_procession_gives_6_once_and_provisionally', result['applied'] and s['coin'] == 126 and result['provisional_until_safe_handover'])
reject('procession_does_not_pay_before_original_strip_returns', new_state() | {'phase': 'open'}, 'E038:B1', facts(actual_passage_completed=True, original_strip_returned=False))
s = new_state(); s['phase'] = 'open'
result = run(s, 'E042:B1', facts(two_work_food_delivered=True, personal_food_excluded=True))
check('actual_optional_work_food_delivery_gives_4', result['applied'] and s['coin'] == 124)
reject('free_personal_food_cannot_fund_event_reward', new_state() | {'phase': 'open'}, 'E042:B1', facts(two_work_food_delivered=True, personal_food_excluded=False))
s = new_state(); s['phase'] = 'day'
sleep = facts(action_id='A01', slots_used=1, quiet_place_reserved=True)
result = run(s, 'E062:B2', sleep)
check('actual_quiet_sleep_costs_10_once', result['applied'] and s['coin'] == 110)
reject('quiet_sleep_does_not_make_wallet_negative', new_state() | {'coin': 9}, 'E062:B2', sleep)

s = new_state(); s['phase'] = 'open'
gift = facts(object_id='actual-box-content', definition_id='I21', claim_id='claim-I21', matching_real_batch_and_seal=True)
result = run(s, 'E067:B1', gift)
check('gift_becomes_one_provisional_claim_not_current_inventory', result['applied'] and not s['items'] and not s['opening_manifest'] and len(s['pending_claims']) == 1 and not s['pending_claims']['claim-I21']['usable_this_shift'])
reject('same_gift_object_cannot_get_another_claim', s, 'E067:B1', {**gift, 'source_receipt_id': 'another-source', 'claim_id': 'another-claim'}, receipt='another-command')
reject('unverified_gift_batch_not_a_reward', new_state() | {'phase': 'open'}, 'E067:B1', {**gift, 'matching_real_batch_and_seal': False})
reject('unknown_or_random_gift_definition_denied', new_state() | {'phase': 'open'}, 'E067:B1', {**gift, 'definition_id': 'I999'})

for branch, location in (('E069:B1', 'pet_stash'), ('E069:B2', 'declared_opening_stash')):
    s = new_state(); s['phase'] = 'open'
    s['items']['same-item'] = {'definition_id': 'I30', 'location': location, 'consumed': False}
    hidden_id = 'same-item'
    if branch == 'E069:B2':
        hidden_id = 'hidden-original'
        s['items'][hidden_id] = {'definition_id': 'I30', 'location': 'pet_stash', 'consumed': False}
    s['opening_manifest'] = ['same-item']
    evidence = facts(object_id='same-item', hidden_object_id=hidden_id, pet_id='P01', actual_pet_action=True)
    count_before = len(s['items'])
    result = run(s, branch, evidence)
    check(branch + '_returns_only_original_opening_item', result['applied'] and len(s['items']) == count_before and s['items']['same-item']['location'] == 'carried' and s['opening_manifest'] == ['same-item'])
    s = new_state(); s['phase'] = 'open'; s['items']['same-item'] = {'definition_id': 'I30', 'location': location}
    if branch == 'E069:B2':
        s['items'][hidden_id] = {'definition_id': 'I30', 'location': 'pet_stash', 'consumed': False}
    reject(branch + '_warehouse_item_not_added_to_opening_manifest', s, branch, evidence)
    s['opening_manifest'] = ['same-item']; s['items']['same-item']['critical'] = True
    reject(branch + '_critical_object_cannot_be_hidden_or_replaced', s, branch, evidence)

s = new_state(); s['phase'] = 'open'; s['opening_manifest'] = ['spare']
s['items'] = {'spare': {'definition_id': 'I30', 'location': 'declared_opening_stash'}}
evidence = facts(object_id='spare', hidden_object_id='hidden', pet_id='P01', actual_pet_action=True)
reject('pet_spare_requires_actual_hidden_original', s, 'E069:B2', evidence)
s['items']['hidden'] = {'definition_id': 'I31', 'location': 'pet_stash'}
reject('pet_spare_must_be_same_kind_as_original', s, 'E069:B2', evidence)


def purchase_state():
    state = new_state()
    state['items']['bought'] = {'definition_id': 'Q05', 'location': 'carried'}
    state['purchase_lines']['paid-line'] = {'object_id': 'bought', 'source': 'paid_shop_purchase', 'actual_paid': 42,
        'week_id': state['week_id'], 'window': state['procurement_window'], 'refunded': False}
    return state


returned = facts(object_id='bought', purchase_line_id='paid-line', actual_return_minutes=5)
s = purchase_state(); result = run(s, 'E072:B1', returned)
check('refund_uses_actual_42_paid_not_catalog_60_and_removes_item', result['applied'] and s['coin'] == 162 and 'bought' not in s['items'] and s['purchase_lines']['paid-line']['refunded'])
reject('refund_original_source_cannot_pay_twice', s, 'E072:B1', returned, receipt='new-command')
for label, modify in (
    ('old_week_purchase', lambda s: s['purchase_lines']['paid-line'].update(week_id='old-week')),
    ('old_window_purchase', lambda s: s['purchase_lines']['paid-line'].update(window='old-window')),
    ('lottery_item', lambda s: s['purchase_lines']['paid-line'].update(source='lottery')),
    ('gift_item', lambda s: s['purchase_lines']['paid-line'].update(source='gift')),
    ('already_used_item', lambda s: s['items']['bought'].update(used=True)),
    ('already_transferred_item', lambda s: s['items']['bought'].update(transferred=True)),
    ('pending_draw_ownership_snapshot', lambda s: s.update(pending_draw=True)),
):
    s = purchase_state(); modify(s)
    reject('refund_rejects_' + label, s, 'E072:B1', returned)

paths = [
    'content/event_migrations_sa02.json', 'content/event_contracts_v010.json',
    'content/equipment_contracts_eq01.json', 'content/lottery_rewards_eq01.json',
    'content/run_lifecycle_sa01.json', 'scripts/sa02_event_reference.py',
    'scripts/check_sa02_events.py',
]
report = {
    'version': 'SA02', 'scope': 'Explicit 72-ID migration index; 24 targeted economic/inventory/pet boundary reviews and 48 NOT reaudited lifecycles. Bounded supplied-fact accounting/claim examples only.',
    'runtime_integrated': False, 'all_event_gameplay_proven': False,
    'world_sources_authenticated': False, 'loan_ledger_implemented': False,
    'storage_durability_proven': False, 'full_week_playtested': False,
    'coverage': contract['catalog_counts'], 'passed': sum(r['passed'] for r in rows),
    'failed': sum(not r['passed'] for r in rows), 'checks': rows,
    'check_categories': {'index_source_runtime_gate': 147, 'targeted_accounting_rejection_and_old_contract_examples': len(rows) - 147},
    'inputs_sha256': {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
    'legacy_quote_witness_scope': 'Old policy arithmetic only; no claim that the legacy client executed a paid recycling route.',
    'remaining': contract['reference_does_not_prove'],
}
(ROOT / 'docs/sa02_event_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
print(json.dumps({k: report[k] for k in ('passed', 'failed', 'coverage', 'all_event_gameplay_proven')}, ensure_ascii=False))
raise SystemExit(1 if report['failed'] else 0)
