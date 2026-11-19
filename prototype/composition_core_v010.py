"""Pure admission of a concrete measured plan. Does not manufacture source facts.

Each operation needs its actual start/end controls and object binding. Historical
commitments occupy resources but are not a newly spawned primary.  The caller
must provide actual world observations; this is not a complete game director.
"""
from copy import deepcopy
from math import isfinite


def expand_e045_operations(event, branch_id, actual_due_contract_ids):
    """Expand a manual debt plan from the supplied original due-contract IDs.

    This is read-only planning, not payment, loan creation or wage settlement.
    A caller must separately verify each original debt in the persistent ledger.
    Automatic wage-offset fallback is deliberately not a manual-action branch.
    """
    ids = actual_due_contract_ids
    if (not isinstance(ids, list) or not 1 <= len(ids) <= 3
            or any(not isinstance(i, str) or not i for i in ids)
            or len(ids) != len(set(ids))):
        raise ValueError('one_to_three_distinct_original_due_contract_ids_required')
    if event.get('id') != 'E045':
        raise ValueError('wrong_event_contract')
    branch = next((b for b in event['branches'] if b['id'] == branch_id), None)
    if branch is None:
        raise ValueError('manual_settlement_branch_required')
    operations = []
    for authored in branch['operations']:
        repeated = authored.get('repeat_for') == 'actual_due_contract_ids'
        bound_ids = ids if repeated else [None]
        for contract_id in bound_ids:
            operation = {'operation_receipt_key': authored['id'] + (':' + contract_id if contract_id else ''),
                         'anchor': authored['anchor'], 'seconds': authored['world_seconds']}
            if contract_id:
                operation['object_id'] = contract_id
            else:
                operation['bound_original_contract_ids'] = list(ids)
            operations.append(operation)
    return operations


def admit_e035_public_exit(event, world, routes):
    """Read-only late visitor route; the verified manager and player stay put."""
    details = event['mechanic_details']
    reasons = []
    budget = world.get('shift_budget')
    first_omen = world.get('first_omen_shift_budget')
    if (not isinstance(budget, (int, float)) or not isfinite(budget)
            or budget < details['earliest_shift_budget']
            or budget > details['latest_start_shift_budget']):
        reasons.append('outside_E035_offer_window')
    if (not isinstance(first_omen, (int, float)) or not isfinite(first_omen)
            or first_omen < details['earliest_shift_budget']
            or first_omen > details['latest_first_omen_shift_budget']):
        reasons.append('late_or_missing_first_omen')
    elif isinstance(budget, (int, float)) and budget < first_omen + details['minimum_recognition_preparation_world_seconds']:
        reasons.append('recognition_preparation_margin_missing')
    station = routes.anchors[details['manager_station_anchor']]
    if world.get('manager_position') != station or not world.get('manager_verified_current', False):
        reasons.append('current_verified_manager_must_stay_at_desk')
    if world.get('player_position') != station or not world.get('handover_capacity_reserved', False):
        reasons.append('player_and_handover_reservation_required_before_offer')
    if world.get('visitor_position') != details['visitor_initial_public_position']:
        reasons.append('actual_adjacent_public_visitor_required')
    if 'DOOR_FRONT' in world.get('closed_doors', []) or not world.get('public_exit_safe', False):
        reasons.append('actual_open_safe_public_exit_required')
    elapsed = None
    if not reasons:
        try:
            distance = routes.distance(world['visitor_position'], details['visitor_exit_position'], world.get('closed_doors', []))
            elapsed = 2 + distance / details['visitor_speed_tiles_per_world_second']
            if elapsed > 720-budget + 1e-8:
                reasons.append('visitor_cannot_exit_before_handover')
        except (ValueError, TypeError, KeyError):
            reasons.append('unreachable_public_exit')
    return {'allowed': not reasons, 'reasons': reasons, 'elapsed_seconds': elapsed,
            'manager_extra_route_tiles': 0, 'player_extra_route_tiles': 0,
            'scope': 'Actual fixed public exit route with supplied current actor evidence; no actor movement or handover mutation.'}


def admit(plan, world, routes):
    reasons = []
    before = deepcopy(world)
    if not plan.get('enabled', True):
        return {'allowed': False, 'reasons': ['archived_or_disabled'], 'world_unchanged': world == before}
    for required in plan.get('required_sources', []):
        source = world.get('sources', {}).get(required)
        if not source or source.get('committed') is not True or source.get('expired') is True:
            reasons.append('missing_actual_source:'+required)
    new_primary = plan.get('new_primary_count', 0)
    if world.get('new_primary_this_phase', 0) + new_primary > 1:
        reasons.append('more_than_one_new_primary')
    if world.get('active_pursuers', 0) + plan.get('additional_pursuers', 0) > 1:
        reasons.append('second_active_pursuer')
    if plan.get('major', False) and (world.get('major_reserved_this_night', False) or world.get('active_pursuers', 0)):
        reasons.append('major_quota_or_active_chase')
    for action_id, modifiers in plan.get('action_modifiers', {}).items():
        total = set(modifiers) | set(world.get('existing_action_modifiers', {}).get(action_id, []))
        if world.get('low_san_changes_this_action', {}).get(action_id, False):
            total.add('low_san')
        if len(total) > 2:
            reasons.append('more_than_two_constraints:'+action_id)
    claimed_slots = set()
    for claim in plan.get('slot_claims', []):
        slot = claim['slot_instance_id']
        if slot in claimed_slots:
            reasons.append('duplicate_physical_slot:'+slot)
        claimed_slots.add(slot)
        existing = world.get('slots', {}).get(slot)
        if existing is None:
            reasons.append('nonexistent_slot:'+slot)
        elif existing.get('owner') not in (None, claim.get('owner')):
            reasons.append('occupied_slot:'+slot)
    consumed = {}
    for claim in plan.get('stock_claims', []):
        object_id, quantity = claim['object_instance_id'], claim['quantity']
        if not isinstance(quantity, (int, float)) or quantity < 0:
            reasons.append('invalid_quantity:'+object_id)
            continue
        consumed[object_id] = consumed.get(object_id, 0) + quantity
    for object_id, amount in consumed.items():
        obj = world.get('inventory', {}).get(object_id)
        if not obj or obj.get('quantity', 0) < amount:
            reasons.append('insufficient_same_object:'+object_id)
        elif obj.get('protected_for') not in (None, plan.get('owner')):
            reasons.append('other_obligation_reserved_object:'+object_id)
    operations = plan.get('operations', [])
    # Shared work only deduplicates the same operation ID with identical object,
    # target and duration. Identical labels on different objects are not free work.
    unique, seen = [], {}
    for operation in operations:
        key = operation['operation_receipt_key']
        if key in seen:
            if operation != seen[key]:
                reasons.append('contradictory_shared_operation:'+key)
        else:
            seen[key] = operation
            unique.append(operation)
    elapsed, current = 0.0, world.get('player_position')
    route_rows=[]
    for operation in unique:
        try:
            seconds, speed = operation['seconds'], operation.get('travel_speed', 3.0)
            if not isinstance(seconds, (int,float)) or not isfinite(seconds) or seconds < 0 or speed <= 0:
                raise ValueError('invalid_duration_or_speed')
            target = routes.point(operation)
            distance = routes.distance(current, target, world.get('closed_doors', []))
            cost = distance/speed + seconds
            elapsed += cost
            route_rows.append({'operation':operation['operation_receipt_key'],'tiles':distance,'seconds':round(cost,6)})
            current = operation.get('end_position', target)
        except (KeyError, ValueError, TypeError):
            reasons.append('unmeasurable_operation:'+operation.get('operation_receipt_key','unknown'))
    for name in ('already_committed_seconds','recovery_seconds','next_omen_seconds'):
        value = plan.get(name, 0)
        if not isinstance(value,(int,float)) or not isfinite(value) or value < 0:
            reasons.append('invalid_reservation:'+name)
        else:
            elapsed += value
    remaining = world.get('remaining_phase_budget',0)
    if elapsed > remaining + 1e-8:
        reasons.append('insufficient_actual_phase_budget')
    return {'allowed':not reasons,'reasons':sorted(set(reasons)),
            'measured_plan_seconds':round(elapsed,6),'remaining_seconds':remaining,
            'route_rows':route_rows,'unique_operation_count':len(unique),
            'world_unchanged':world == before,
            'scope':'Read-only admission on supplied actual sources and static measured routes, not moving-enemy execution.'}
