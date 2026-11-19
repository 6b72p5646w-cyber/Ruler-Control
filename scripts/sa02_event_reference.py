"""Bounded SA02 event migration reference, never a world/client adapter.

Commands consume supplied, already verified original action receipts. The module
does not authenticate a player, create a source object, move a pet, spend game
time, finish a job, or make any of the 72 events eligible at runtime. The caller
must integrate accepted provisional income/claims into SA01's whole-checkpoint
transaction. The small dictionary commits here are only in-memory witnesses.
"""
from copy import deepcopy
import json


def denied(reason):
    return {'applied': False, 'reason': reason, 'reference_only': True}


def new_state():
    return {
        'profile': 'current_design_sa02', 'campaign_id': 'fixture-campaign',
        'week_id': 'fixture-week-1', 'night_index': 1, 'attempt_id': 'fixture-attempt-1',
        'phase': 'pre_shift', 'coin': 120, 'storage_capacity': 4,
        'items': {}, 'opening_manifest': [], 'pending_claims': {},
        'purchase_lines': {}, 'procurement_window': 'fixture-window-1',
        'receipts': {}, 'consumed_source_receipts': {}, 'pending_draw': False,
    }


def runtime_admission(contract, event_id):
    """An explicit gate; successful reference traces cannot turn it on."""
    entry = next((e for e in contract['entries'] if e['id'] == event_id), None)
    if entry is None:
        return denied('unknown_event')
    return denied('runtime_adapter_not_registered')


def command_for(state, event_id, branch_id, receipt_id, facts):
    """Convenience for test fixtures, not a factual observation producer."""
    return {
        'event_id': event_id, 'branch_id': branch_id, 'receipt_id': receipt_id,
        'campaign_id': state['campaign_id'], 'week_id': state['week_id'],
        'night_index': state['night_index'], 'attempt_id': state['attempt_id'],
        'facts': deepcopy(facts),
    }


def apply_reference(state, contract, command):
    """Atomically map one supplied completion in the declared design fixture.

    Unknown/unreviewed events and unmodelled branches fail closed. A renamed
    command cannot replay the same original action receipt. No generic caller
    supplied coin_delta, catalog price, or award kind is accepted.
    """
    if state.get('profile') != contract['profile'] or not contract.get('reference_fixture_only'):
        return denied('wrong_reference_profile')
    if any(command.get(k) != state[k] for k in ('campaign_id', 'week_id', 'night_index', 'attempt_id')):
        return denied('stale_or_wrong_scope')
    receipt_id = command.get('receipt_id')
    if not isinstance(receipt_id, str) or not receipt_id:
        return denied('command_receipt_required')
    if receipt_id in state['receipts']:
        return denied('command_already_applied')
    event_id, branch = command.get('event_id'), command.get('branch_id')
    entry = next((e for e in contract['entries'] if e['id'] == event_id), None)
    if entry is None or branch not in entry['legacy_branch_ids']:
        return denied('unknown_event_or_branch')
    if entry['migration_status'] in ('disabled_in_seven_night_design', 'legacy_disabled', 'not_reaudited_fail_closed'):
        return denied(entry['migration_status'])
    if entry['branch_overrides'].get(branch, '').startswith('reject_'):
        return denied(entry['branch_overrides'][branch])
    if branch not in contract['bounded_reference_supported_branches']:
        return denied('branch_adapter_not_modelled')
    facts = command.get('facts', {})
    if not isinstance(facts, dict) or facts.get('validated_completion') is not True:
        return denied('actual_verified_completion_required')
    source = facts.get('source_receipt_id')
    if not isinstance(source, str) or not source:
        return denied('original_source_receipt_required')
    source_key = json.dumps([state['campaign_id'], source], ensure_ascii=False)
    if source_key in state['consumed_source_receipts']:
        return denied('original_source_already_applied')
    if facts.get('credited_to_legacy_wallet') or facts.get('debited_from_legacy_wallet'):
        return denied('second_wallet_route_forbidden')
    if 'coin_delta' in facts or 'product_price' in facts:
        return denied('caller_selected_amount_forbidden')
    day = state['phase'] in ('morning', 'day', 'pre_shift')
    night = state['phase'] == 'open'
    draft = deepcopy(state)
    result = {'coin_delta': 0, 'reference_only': True}

    if branch in ('E038:B1', 'E042:B1'):
        if not night:
            return denied('actual_open_shift_required')
        required = ('actual_passage_completed', 'original_strip_returned') if branch == 'E038:B1' else ('two_work_food_delivered', 'personal_food_excluded')
        if any(facts.get(k) is not True for k in required):
            return denied('original_reward_completion_missing')
        result['coin_delta'] = 6 if branch == 'E038:B1' else 4
        result['provisional_until_safe_handover'] = True
    elif branch == 'E054:B1':
        if not day or facts.get('action_id') != 'A09' or facts.get('slots_used') != 1 or facts.get('energy_delta') != -12:
            return denied('actual_A09_completion_required')
        result['coin_delta'] = 30
    elif branch == 'E062:B2':
        if not day or facts.get('action_id') != 'A01' or facts.get('slots_used') != 1 or facts.get('quiet_place_reserved') is not True:
            return denied('actual_quiet_sleep_completion_required')
        result['coin_delta'] = -10
    elif branch == 'E066:B1':
        item_id = facts.get('object_id')
        item = draft['items'].get(item_id)
        stored = sum(x.get('location') == 'personal_storage' for x in draft['items'].values())
        if not day or not item or item.get('consumed') or item.get('critical') or item.get('location') == 'personal_storage':
            return denied('same_owned_storable_object_required')
        if stored >= draft['storage_capacity']:
            return denied('actual_storage_capacity_required')
        item['location'] = 'personal_storage'
        result['same_object_id'] = item_id
    elif branch == 'E067:B1':
        claim_id, object_id = facts.get('claim_id'), facts.get('object_id')
        if not night or facts.get('definition_id') != 'I21' or facts.get('matching_real_batch_and_seal') is not True:
            return denied('same_verified_I21_gift_required')
        if not isinstance(claim_id, str) or not claim_id or not isinstance(object_id, str) or not object_id:
            return denied('actual_gift_identity_required')
        claimed_objects = {x['object_id'] for x in draft['pending_claims'].values()}
        if claim_id in draft['pending_claims'] or object_id in claimed_objects or object_id in draft['items']:
            return denied('original_gift_already_owned_or_claimed')
        draft['pending_claims'][claim_id] = {
            'object_id': object_id, 'definition_id': 'I21', 'quantity': 1,
            'night_key': [state['campaign_id'], state['week_id'], state['night_index']],
            'attempt_id': state['attempt_id'], 'source_receipt_id': source,
            'provisional_until_safe_handover': True, 'usable_this_shift': False,
        }
        result['deferred_claim_id'] = claim_id
    elif branch in ('E069:B1', 'E069:B2'):
        item_id = facts.get('object_id')
        item = draft['items'].get(item_id)
        hidden_id = facts.get('hidden_object_id')
        hidden = draft['items'].get(hidden_id)
        if not night or facts.get('pet_id') not in ('P01', 'P03', 'P04') or facts.get('actual_pet_action') is not True:
            return denied('actual_allowed_pet_action_required')
        if not hidden or hidden.get('location') != 'pet_stash' or hidden.get('critical') or hidden.get('consumed'):
            return denied('same_actual_hidden_original_required')
        if branch == 'E069:B1' and item_id != hidden_id:
            return denied('retrieval_must_return_hidden_original')
        if branch == 'E069:B2' and (item_id == hidden_id or not item or item.get('definition_id') != hidden.get('definition_id')):
            return denied('spare_must_match_hidden_original_kind')
        if not item or item_id not in draft['opening_manifest'] or item.get('consumed') or item.get('critical'):
            return denied('unused_original_opening_item_required')
        required_location = 'pet_stash' if branch == 'E069:B1' else 'declared_opening_stash'
        if item.get('location') != required_location:
            return denied('actual_original_item_location_required')
        item['location'] = 'carried'
        result['same_object_id'] = item_id
    elif branch == 'E072:B1':
        line_id, object_id = facts.get('purchase_line_id'), facts.get('object_id')
        line, item = draft['purchase_lines'].get(line_id), draft['items'].get(object_id)
        if state['phase'] != 'pre_shift' or draft['pending_draw']:
            return denied('available_procurement_window_required')
        if not line or not item or line.get('object_id') != object_id or line.get('source') != 'paid_shop_purchase':
            return denied('same_actual_paid_purchase_required')
        if line.get('week_id') != state['week_id'] or line.get('window') != state['procurement_window']:
            return denied('same_week_same_procurement_window_required')
        if line.get('refunded') or line.get('salvaged') or item.get('consumed') or item.get('used') or item.get('transferred'):
            return denied('unused_untransferred_unrefunded_item_required')
        if facts.get('actual_return_minutes') != 5 or type(line.get('actual_paid')) is not int or line['actual_paid'] <= 0:
            return denied('actual_return_and_original_price_required')
        result['coin_delta'] = line['actual_paid']
        del draft['items'][object_id]
        line['refunded'] = True
    else:
        return denied('branch_adapter_not_modelled')

    if draft['coin'] + result['coin_delta'] < 0:
        return denied('insufficient_current_week_coin')
    draft['coin'] += result['coin_delta']
    result.update({'applied': True, 'event_id': event_id, 'branch_id': branch, 'source_receipt_id': source})
    draft['receipts'][receipt_id] = deepcopy(result)
    draft['consumed_source_receipts'][source_key] = receipt_id
    state.clear()
    state.update(draft)
    return result
