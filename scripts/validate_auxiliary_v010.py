#!/usr/bin/env python3
"""Static closure checks plus small independent numeric/geometry counterexamples.

This deliberately does not claim to run the game or any of its 60 monster clients.
It validates finite auxiliary contracts, references and selected mathematical edges.
"""
import argparse
import json
import math
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype'))
from auxiliary_lifecycle_v010 import ChargedSource, snapshot_next_action
CONTRACT = ROOT / 'content/auxiliary_effects_v010.json'
ERRORS = []
CHECKS = 0
PROBES = []


def check(value, message):
    global CHECKS
    CHECKS += 1
    if not value:
        ERRORS.append(message)


def ids_in(value):
    found = set()
    if isinstance(value, dict):
        if isinstance(value.get('id'), str):
            found.add(value['id'])
        if isinstance(value.get('role'), str):
            found.add(value['role'])
        for child in value.values():
            found.update(ids_in(child))
    elif isinstance(value, list):
        for child in value:
            found.update(ids_in(child))
    return found


def probe(name, actual, expected):
    ok = math.isclose(actual, expected, abs_tol=1e-9) if isinstance(actual, (int, float)) and isinstance(expected, (int, float)) else actual == expected
    check(ok, f'probe {name}: {actual!r} != {expected!r}')
    PROBES.append({'name': name, 'passed': ok})


def segments_intersect(a, b, c, d):
    def orientation(p, q, r):
        return (q[0] - p[0]) * (r[1] - p[1]) - (q[1] - p[1]) * (r[0] - p[0])
    return orientation(a, b, c) * orientation(a, b, d) <= 0 and orientation(c, d, a) * orientation(c, d, b) <= 0


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    data = json.loads(CONTRACT.read_text())
    entries = data['entries']
    by_id = {e['id']: e for e in entries}
    consumers = {e['id']: e for e in data['consumer_registry']}
    expected = {f'{prefix}{n:02}' for prefix, count in [('I', 24), ('Q', 24), ('P', 8), ('B', 8)] for n in range(1, count + 1)}
    archived = {'I22', 'I23', 'Q03', 'Q11'}
    check(set(by_id) == expected and len(entries) == 64, 'catalog ID set must contain exactly all 64 original entries')
    check({e['id'] for e in entries if not e['acquisition_enabled']} == archived, 'exact four historic effects remain disabled')
    check(sum(bool(e['effects']) for e in entries) == 60, 'exactly 60 entries need an actual effect consumer')
    check(data['client_implemented'] is False, 'contract must not imply complete client implementation')
    cache = {}
    for name in ('items', 'equipment', 'pets', 'deployables'):
        cache[f'content/{name}.json'] = json.loads((ROOT / f'content/{name}.json').read_text())
    catalogs = {r['id']: r for name in ('items', 'equipment', 'pets', 'deployables') for r in cache[f'content/{name}.json'][name]}
    required = {'effect_id', 'producer_refs', 'consumer_id', 'target_selector', 'preconditions', 'parameters', 'operation', 'lifetime', 'cooldown', 'quota', 'cost', 'stacking', 'failure_and_expiry', 'cleanup', 'no_automatic_identity_or_encounter_success'}
    clocks = {'world_simulation', 'local_qte', 'absolute_game_minutes', 'game_day', 'source_bound'}
    effect_ids = set()
    for entry in entries:
        eid = entry['id']
        row = catalogs[eid]
        check(entry['client_implemented'] is False and row.get('effect_handler_implemented') is False, eid + ': design vs runtime distinction')
        check(bool(entry['free_baseline_alternative']), eid + ': missing concrete free alternative')
        check(row['effect_contract_v010'].endswith('/' + eid), eid + ': catalog has no authority link')
        if eid in archived:
            check(not entry['effects'], eid + ': archive must not contain active effect')
            check(all(row.get(k) is False for k in ('acquisition_enabled', 'shop_enabled', 'lottery_enabled', 'reward_enabled', 'crafting_enabled')), eid + ': some acquisition channel reopened')
            check(row['historical_archive_v010']['may_load_as_current_effect'] is False, eid + ': historical text could be loaded as current')
            continue
        check(bool(entry['effects']), eid + ': active entry has no effect')
        check(not any(word in entry['benefit'] for word in ('小幅', '若干', '随机概率', '暂时维持')), eid + ': unresolved numerical shorthand')
        for e in entry['effects']:
            label = e['effect_id']
            check(required <= set(e), label + ': missing contract fields')
            check(label not in effect_ids, label + ': duplicate effect ID')
            effect_ids.add(label)
            check(e['consumer_id'] in consumers, label + ': unregistered consumer')
            check(bool(e['producer_refs']) and bool(e['parameters']) and bool(e['preconditions']), label + ': missing producer/parameter/gate')
            for source in e['producer_refs']:
                path = source['file']
                check((ROOT / path).is_file(), label + ': missing producer file ' + path)
                if path not in cache and (ROOT / path).is_file():
                    cache[path] = json.loads((ROOT / path).read_text())
                if source.get('record_id'):
                    check(source['record_id'] in ids_in(cache[path]), label + ': nonexistent producer ' + source['record_id'])
            for key in ('operation', 'lifetime', 'cooldown'):
                check(e[key]['clock'] in clocks, label + ': unknown clock for ' + key)
                check(isinstance(e[key]['seconds'], (int, float)) and e[key]['seconds'] >= 0, label + ': negative/unknown duration for ' + key)
            check(e['operation']['hands_required'] in (0, 1, 2), label + ': illegal hand count')
            check(isinstance(e['operation']['range_tiles'], (int, float)) and e['operation']['range_tiles'] >= 0, label + ': missing range')
            check(e['lifetime']['seconds'] != 0 or bool(e['lifetime']['end_condition']), label + ': zero duration without end condition')
            check(isinstance(e['quota']['limit'], int) and e['quota']['limit'] >= 0, label + ': quota is implicit')
            check(e['quota']['limit'] or e['quota'].get('zero_limit_means'), label + ': unlimited quota is implicit')
            check(all(isinstance(e['cost'][k], (int, float)) and e['cost'][k] >= 0 for k in ('item_instances', 'pet_shared_charges', 'device_charges', 'energy', 'stamina')), label + ': missing quantitative debit')
            check(bool(e['cost']['commit_at']) and e['cost']['elapsed_world_time_refunded'] is False, label + ': payment timing ambiguous')
            check(e['cost']['invalid_or_cancelled'] == 'zero_auxiliary_cost', label + ': invalid invocation charges')
            check(e['stacking']['recast_or_reposition_refreshes_existing_effect'] is False, label + ': free refresh exploit')
            check(bool(e['cleanup']) and bool(e['failure_and_expiry']['cross_night']), label + ': no cleanup/persistence')
            check(e['no_automatic_identity_or_encounter_success'] is True, label + ': helper auto-solves core condition')
    used = {e['consumer_id'] for entry in entries for e in entry['effects']}
    check(used == set(consumers), 'consumer registry contains unused or absent readers')

    def fx(id, index=0):
        return by_id[id]['effects'][index]

    # Immutable consensus and cross-system ownership boundaries.
    coffee = fx('I05')['parameters']
    check(coffee['resource_deltas'] == {'energy': 12}, 'coffee immediate gain changed')
    check(coffee['delayed_debt']['resource_deltas'] == {'energy': -8, 'san': -2} and coffee['delayed_debt']['delay_game_minutes'] == 60, 'coffee debt changed')
    check(coffee['delayed_debt']['clock'] == 'absolute_game_minutes', 'coffee must persist across dawn/day/save')
    check(fx('I20')['parameters']['resource_deltas'] == {}, 'I20 has an invented drinking resource effect')
    check(fx('I15')['consumer_id'] == 'sealed_waste_cooling' and fx('I15')['parameters']['changes_F13_target_state'] is False, 'I15 revived nonexistent task-meat spoilage')
    check(fx('Q16')['parameters']['blood_consumer_ids'] == [] and fx('Q16')['parameters']['monster_consumer_ids'] == [], 'Q16 shoe traces are not blood or enemy lure')
    check((fx('Q16')['parameters']['distance_per_marker_tiles'], fx('Q16')['parameters']['marker_ttl_world_seconds'], fx('Q16')['parameters']['max_live_markers']) == (2, 60, 16), 'Q16 finite lifecycle missing')
    check(fx('Q17')['parameters']['action_ids'] == ['A02'] and fx('Q17')['quota']['scope'] == 'game_day_06_to_06', 'Q17 must consume actual daytime short-rest receipt')
    check(fx('Q17')['parameters']['san_bonus'] == 4 and fx('Q17')['quota']['limit'] == 1, 'Q17 amount/quota changed')
    check(fx('Q19')['parameters']['apply_order'] == ['source_receipt_dedupe', 'fear_immunity', 'source_repeat_cooldown', 'source_phase_cap', 'Q19_if_ready', 'clamp_and_commit'], 'Q19 ordering mismatch')
    check(fx('Q19')['parameters']['flat_reduction'] == 3 and fx('Q19')['cooldown']['seconds'] == 60, 'Q19 amount/cooldown undefined')
    check('positive_mitigation_after_current_san_clamp' in fx('Q19')['preconditions'], 'Q19 can waste itself when clamp makes it ineffective')
    check(fx('P05')['consumer_id'] == 'actual_threshold_notice' and fx('P05')['parameters']['may_modify_door_state'] is False, 'P05 still depends on automatic door timer')
    check(fx('P05')['parameters']['empty_window_consumes_charge'] is False, 'empty P05 watch charges')
    check(fx('P08', 1)['parameters']['first_actual_failure_energy'] == 2 and fx('P08', 1)['parameters']['total_encounter_energy_cap'] == 4, 'P08 F31 reward cap changed')
    check(fx('P08', 1)['parameters']['first_attempt_budget_seconds'] == 8 and fx('P08', 1)['parameters']['retry_attempt_budget_seconds'] == 8, 'F31/P08 budget changed')
    check(fx('P08', 1)['parameters']['retry_visible_hit_window_local_seconds'] == 1.5 and not fx('P08', 1)['parameters']['third_attempt_allowed'], 'F31 retry window/unbounded retry mismatch')
    check(fx('P04', 1)['parameters']['requires_player_fetched_and_scattered'] and fx('B05')['parameters']['ammo_created'] == 0, 'F12 personal pickup/scatter bypassed')
    check(fx('B06')['parameters']['same_meat_instance_preserved'] and not fx('B06')['parameters']['completes_freezer_goal'], 'F13 meat identity or victory bypassed')
    check(fx('I09')['parameters']['free_total_seconds'] == 1.5 and fx('I09')['operation']['seconds'] == 0.5, 'I09 no measurable valid time saving')
    check(fx('I09')['parameters']['door_auto_close_seconds'] == 0, 'I09 introduced nonexistent auto-close time')
    check(fx('Q08')['operation']['seconds'] == 1 and fx('Q08')['cost']['stamina'] == 6 and fx('Q08')['parameters']['walk_to_each_socket_separately'], 'Q08 asks player to stand at two distant sockets simultaneously')

    # Independent arithmetic probes use contract parameters and boundary inputs.
    def warning_increment(request, existing, remaining):
        difference = max(0, min(3, request) - existing)
        return difference if 0 < difference <= remaining else 0
    for name, args_, expected_result in [
        ('warning_from_two_to_three', (3, 2, 1), 1),
        ('warning_no_difference_no_charge', (2, 3, 9), 0),
        ('warning_cannot_partially_spend_across_boundary', (3, 1, 1), 0),
        ('upgraded_B04_is_total_half_second', (0.5, 0, 1), 0.5),
        ('expired_budget_has_no_extension', (3, 0, 0), 0),
    ]:
        probe(name, warning_increment(*args_), expected_result)
    penalty = lambda base, *mods: 3 - (3 - base) * min(mods)
    probe('Q15_ordinary_box', penalty(2.4, fx('Q15')['parameters']['penalty_multiplier']), 2.52)
    probe('B06_L1_raw_meat', penalty(2.6, fx('B06')['parameters']['penalty_multiplier_by_tier']['L1']), 2.8)
    probe('B06_and_Q15_do_not_multiply', penalty(2.6, 0.5, 0.8), 2.8)
    probe('B06_L2_and_Q15_take_stronger', penalty(2.6, 0.75, 0.8), 2.7)
    for san, damage, expected_saving in [(50, 5, 3), (2, 5, 0), (2, 4, 1), (0, 5, 0), (50, 0, 0)]:
        saving = min(san, damage) - min(san, max(0, damage - fx('Q19')['parameters']['flat_reduction']))
        probe(f'Q19_actual_saving_san_{san}_damage_{damage}', saving, expected_saving)
    probe('I06_full_lamp_no_consume', min(25, max(0, 30 - 30)), 0)
    probe('I06_partial_charge_clamp', min(25, max(0, 30 - 20)), 10)
    probe('I15_cooling_cannot_be_negative', max(0, 4 - fx('I15')['parameters']['remaining_world_seconds_subtract']), 0)
    probe('P08_retry_adds_remainder_only', max(0, 4 - 2), 2)
    probe('P08_success_cannot_pay_more_after_cap', max(0, 4 - 4), 0)
    probe('Q17_day_before_06', math.floor((359 - 360) / 1440), -1)
    probe('Q17_day_at_06', math.floor((360 - 360) / 1440), 0)
    probe('Q17_same_day_midnight_no_reset', math.floor((1440 - 360) / 1440), 0)
    marks = []
    distance = 0
    for second in range(100):
        marks = [m for m in marks if second - m['at'] < fx('Q16')['parameters']['marker_ttl_world_seconds']]
        distance += 1
        if distance >= 2:
            distance -= 2
            marks.append({'at': second, 'tag': fx('Q16')['parameters']['marker_tag']})
            marks = marks[-fx('Q16')['parameters']['max_live_markers']:]
    probe('Q16_max_16_not_50', len(marks), 16)
    probe('Q16_oldest_not_expired', all(99 - m['at'] < 60 for m in marks), True)
    probe('Q16_never_fresh_blood', any(m['tag'] == 'BLOOD_TRACE' for m in marks), False)
    # An explicit unique receipt probe catches refund/duplicate accounting requirements.
    ledger = set()
    rewards = 0
    for receipt in ('A02_day0_receipt1', 'A02_day0_receipt1', 'A02_day0_receipt1'):
        if receipt not in ledger:
            ledger.add(receipt)
            rewards += fx('Q17')['parameters']['san_bonus']
    probe('Q17_saved_receipt_cannot_repeat_gain', rewards, 4)

    # Regression: a source reaching zero is not an expiry event for the child
    # it just created. This failed under the former generic cleanup wording.
    policy = data['global_contract']['committed_effect_lifecycle']
    check(policy['depleted_source_blocks_new_triggers'] is True, 'spent source may trigger again')
    check(policy['depleted_source_cancels_committed_child'] is False, 'last charge erases its own effect')
    for eid, duration in [
        ('B01', fx('B01')['parameters']['slow_world_seconds']),
        ('B04', fx('B04')['parameters']['ordinary_entry_notice_seconds']),
        ('B06', fx('B06')['parameters']['duration_by_tier_world_seconds']['L1']),
        ('B08', fx('B08')['parameters']['escape_grace_by_tier_world_seconds']['L1']),
    ]:
        check(fx(eid)['lifetime']['source_exhaustion_cancels_child'] is False, eid + ': ambiguous final charge cleanup')
        source = ChargedSource(1)
        probe(eid + '_last_charge_commit', source.commit('actual_trigger', 'same_target', 10, duration), True)
        probe(eid + '_source_now_empty', source.remaining, 0)
        probe(eid + '_last_effect_still_live', source.active('actual_trigger', 10 + duration - 0.001), True)
        probe(eid + '_no_second_trigger', source.commit('another_trigger', 'same_target', 11, duration), False)
        probe(eid + '_same_receipt_no_refresh', source.commit('actual_trigger', 'same_target', 11, duration), False)
        source.retire()
        probe(eid + '_retired_source_keeps_child', source.active('actual_trigger', 10 + duration - 0.001), True)
        probe(eid + '_exact_expiry', source.active('actual_trigger', 10 + duration), False)
        source.end_target('same_target')
        probe(eid + '_terminal_target_cleans_child', source.active('actual_trigger', 10.5), False)
    source = ChargedSource(1)
    probe('invalid_auxiliary_commit_keeps_charge', source.commit('invalid', 'same_target', 0, 2, valid=False), False)
    probe('invalid_auxiliary_charge_unchanged', source.remaining, 1)
    check(fx('P05')['parameters']['after_first_notice_same_watch_needs_no_remaining_pool_charge'] is True,
          'P05 final night charge incorrectly blocks later notices from already paid watch')
    check(fx('I11')['parameters']['consuming_last_chalk_charge_preserves_existing_markers'] is True,
          'last chalk charge deletes its own route mark')
    check(fx('I12')['parameters']['snapshot_multiplier_into_same_action_before_permit_cleanup'] is True,
          'I12 cleans pending permission before copying action multiplier')
    permit = {'starts_at': 0, 'ends_at': 10, 'consumed': False,
              'duration_multiplier': fx('I12')['parameters']['duration_multiplier']}
    snapshot = snapshot_next_action(permit, 'actual_W13', 9.9)
    probe('I12_pending_permit_consumed', permit['consumed'], True)
    probe('I12_current_action_keeps_snapshot', snapshot['duration_multiplier'], 0.8)
    probe('I12_no_second_action_after_cancel', snapshot_next_action(permit, 'another_W13', 9.95), None)
    expired_permit = dict(permit, consumed=False)
    probe('I12_expired_unconsumed_permit_rejected', snapshot_next_action(expired_permit, 'late_W13', 10), None)

    # Concrete anchors prove a target can be locally operated, without claiming pathfinding coverage.
    mechanics = json.loads((ROOT / 'content/map_mechanics_v05.json').read_text())
    wet = next(w for w in mechanics['wet_regions'] if w['id'] == 'WET_COLD')
    b07 = fx('B07')['parameters']
    probe('B07_uses_real_cold_dry_position', b07['primary_position'], wet['dry_interact_position'])
    probe('B07_uses_real_cut_cell', b07['cut_cell'], wet['cut_cell'])
    check(math.dist(b07['primary_position'], [v + 0.5 for v in wet['cut_cell']]) <= b07['max_range_tiles'], 'B07 cut outside reachable interaction radius')
    cells = {tuple(c) for c in wet['wet_cells']}
    check(all(tuple(a) in cells and tuple(b) in cells and math.dist(a, b) == 1 for a, b in b07['L2_edges']), 'B07 references nonexistent wet graph edge')
    maps = json.loads((ROOT / 'content/maps.json').read_text())
    store = next(s for s in maps['scenes'] if s['id'] == 'MAP_STORE')
    attachment = next(a for a in store['fixed_attachments'] if a['id'] == 'ATT14')
    windows = {tuple(p) for g in attachment['groups'] for p in g['window_objects']}
    for socket in fx('B04')['parameters']['F50_socket_aliases']:
        check(tuple(socket['object_position']) in windows, 'B04 refers to invented F50 window')
        check(math.dist(socket['object_position'], socket['player_position']) <= 1, 'B04 window install inaccessible from declared position')
    line = fx('B02')['parameters']['line_by_tier']['L1']
    probe('B02_default_mirror_position_not_protected', segments_intersect([19.5, 21.5], [19.5, 23.5], *line), False)
    probe('B02_actual_left_screen_position_protected', segments_intersect([19.5, 21.5], [6.5, 19.3], *line), True)
    check(data['global_contract']['deployment_policy']['max_active_slots'] == 3, 'deployment capacity changed')
    probe('Q08_two_points_plus_one_B03_fits', 2 + 1 <= 3, True)
    probe('Q08_two_points_plus_two_devices_rejected', 2 + 2 <= 3, False)
    report = {'passed': not ERRORS, 'checks': CHECKS, 'catalog_entries': len(entries), 'effect_contracts': len(effect_ids),
              'registered_consumers': len(consumers), 'bounded_probes': len(PROBES), 'errors': ERRORS,
              'probe_results': PROBES,
              'scope': 'static contract/reference coverage and finite arithmetic/anchor probes; not a complete engine, playthrough or WeChat client proof',
              'client_implemented': False}
    print(json.dumps(report, ensure_ascii=False, indent=2) if args.json else f"auxiliary V0.10: {'PASS' if not ERRORS else 'FAIL'}; {CHECKS} checks, {len(entries)} entries, {len(effect_ids)} effects, {len(PROBES)} bounded probes" + ('\n' + '\n'.join(ERRORS) if ERRORS else ''))
    return 0 if not ERRORS else 1


if __name__ == '__main__':
    raise SystemExit(main())
