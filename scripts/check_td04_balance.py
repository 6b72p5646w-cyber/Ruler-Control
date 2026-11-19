#!/usr/bin/env python3
"""Recompute TD04 calibration, contracts, geometry fixtures and week cashflow.

No third-party dependencies. Run from any directory. The output is a design
reference report; the existing gameplay runtime is deliberately not imported.
"""
from pathlib import Path
from collections import deque
from fractions import Fraction as F
import argparse
import hashlib
import json
import math

from td04_reference import (q, clean, nodes, segment_spans, merge_sample_spans,
                            normal_toll, phase_toll, actual_damage, repeat_events,
                            offense, curse_expected, run_electric, complete_edges,
                            raw_primary_profile, ElectricModel, electric_reservation_fixture)
from td04_economy_reference import week_replay, depleted_sale_comparisons, repair_sale_comparisons

ROOT = Path(__file__).resolve().parents[1]


def locate(path):
    candidates = [ROOT / path]
    if path.endswith('_td03.json'):
        candidates.append(ROOT.parent / 'ruler-control-td03' / path)
    if path == 'content/maps.json':
        candidates.append(ROOT.parent / 'ruler-control-source' / path)
    for candidate in candidates:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(path)


def read(path):
    return json.loads(locate(path).read_text())


def radii(value, prefix=''):
    if isinstance(value, dict):
        for key, child in value.items():
            # Historical diff values and benchmarks are not live parameters.
            if key in ('balance_profile', 'changed_from_td03', 'complete_tree_review'):
                continue
            if 'radius' in key and isinstance(child, (int, float)) and child > 0:
                yield prefix + key, child
            yield from radii(child, prefix + key + '.')
    elif isinstance(value, list):
        for i, child in enumerate(value):
            yield from radii(child, prefix + str(i) + '.')


def trap_nodes(trap):
    yield trap, 1
    for branch in trap['l2']:
        yield branch, 2
        yield branch['l3'], 3


def inside_rect(point, rect):
    x, y = point
    rx, ry, w, h = rect
    return rx <= x < rx + w and ry <= y < ry + h


def distance_to_rect(point, rect):
    x, y = point
    rx, ry, w, h = rect
    return math.hypot(max(rx - x, 0, x - rx - w), max(ry - y, 0, y - ry - h))


def rect_distance(a, b):
    return math.hypot(max(a[0] - b[0] - b[2], b[0] - a[0] - a[2], 0),
                      max(a[1] - b[1] - b[3], b[1] - a[1] - a[3], 0))


def geometry_examples(traps, maps):
    scene = next(s for s in maps['scenes'] if s['id'] == 'MAP_STORE')
    fixtures = {f['id']: f for f in scene['fixtures']}
    solids = [w['rect'] for w in scene['walls']] + [f['rect'] for f in scene['fixtures'] if f['blocks_navigation']]
    surfaces = [s['rect'] for s in scene['walk_surfaces']]

    def legal(point, body_radius=0):
        return (any(inside_rect(point, surface) for surface in surfaces)
                and not any(inside_rect(point, rect) or distance_to_rect(point, rect) < body_radius - 1e-9 for rect in solids))

    valid_cells = {(x, y) for x in range(-1, 35) for y in range(-9, 39) if legal((x + .5, y + .5), .3)}
    start = (15, 30)
    reached, queue = {start}, deque([start])
    while queue:
        x, y = queue.popleft()
        for nxt in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if nxt in valid_cells and nxt not in reached:
                reached.add(nxt)
                queue.append(nxt)
    rows = []
    for example in traps['map_constraints']['side_hung_projection_examples']:
        cx, cy = example['field_center']
        radius = example['radius_tiles']
        occupied_area, body_area = 0, 0
        step = .025
        side = round(2 * radius / step)
        for i in range(side):
            for j in range(side):
                point = (cx - radius + (i + .5) * step, cy - radius + (j + .5) * step)
                if math.dist((cx, cy), point) < radius:
                    occupied_area += legal(point)
                    body_area += legal(point, .3)
        rows.append({'anchor': example['tower_anchor_id'], 'fixture': example['fixture_id'],
                     'anchor_in_actual_fixture': inside_rect(example['anchor_position'], fixtures[example['fixture_id']]['rect']),
                     'center': [cx, cy], 'radius': radius,
                     'center_clear_for_0_3_body': legal((cx, cy), .3),
                     'connected_to_front': (math.floor(cx), math.floor(cy)) in reached,
                     'clipped_floor_area': round(occupied_area * step * step, 4),
                     'legal_body_center_area': round(body_area * step * step, 4),
                     'full_circle_area': round(math.pi * radius * radius, 4)})
    devices = {a['id']: a['rect'] for a in traps['appliances'] if a['design_enabled']}
    edges = []
    for a, b in (('AP_HOT_FOOD', 'AP_FREEZER'), ('AP_FREEZER', 'AP_COLD_CABINET'), ('AP_HOT_FOOD', 'AP_COLD_CABINET')):
        distance = rect_distance(devices[a], devices[b])
        edges.append({'from': a, 'to': b, 'surface_distance': round(distance, 6),
                      'within_2_5_edge_distance': distance <= 2.5})
    return {'examples': rows, 'appliance_distance_examples': edges,
            'scope': 'static_fixture_geometry_and_cell_graph_not_runtime_LOS_or_dynamic_navigation'}


def primary_swarm(node, hp=18, count=8):
    """Direct-only overkill fixture. Targets are already in a legal firing lane."""
    health = [q(hp)] * count
    p, shot, raw_wasted = node['parameters'], 0, F(0)
    time = q(p.get('first_attack_delay_s', 0))
    while any(h > 0 for h in health):
        active = [i for i, h in enumerate(health) if h > 0]
        shot += 1
        if 'ordered_pool_multipliers' in p:
            impacts = list(zip(active, [q(p['damage']) * q(m) for m in p['ordered_pool_multipliers']]))
        else:
            impacts = [(active[0], q(p['damage']))]
        for idx, damage in impacts:
            raw_wasted += max(F(0), damage - health[idx])
            health[idx] -= damage
        if shot % p.get('secondary_every_primary_attacks', 10 ** 9) == 0:
            secondary = next((i for i in active[1:] if health[i] > 0), None)
            if secondary is not None:
                damage = q(p['secondary_damage'])
                raw_wasted += max(F(0), damage - health[secondary])
                health[secondary] -= damage
        if not any(h > 0 for h in health):
            break
        time += q(p['interval_s'])
        if shot > 10000:
            raise AssertionError('swarm fixture failed to finish')
    return clean({'last_defeat_s': time, 'shots': shot, 'wasted_raw_damage': raw_wasted,
                  'targets': count, 'hp_each': hp,
                  'scope': 'direct_packets_only_all_targets_legally_visible_no_targeting_AI'})


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--report', default='docs/td04_balance_report.json')
    args = parser.parse_args()
    files = ['content/tower_defense_td04.json', 'content/combat_contracts_td04.json',
             'content/traps_facilities_td04.json', 'content/monster_matchups_td04.json',
             'content/economy_week_td04.json', 'content/balance_scenarios_td04.json']
    tree, contracts, traps, matchups, economy, fixtures = map(read, files)
    before = read('content/tower_defense_td03.json')
    old_monsters = read('content/monster_matchups_td03.json')
    all_nodes = {n['id']: n for n in nodes(tree)}
    old_nodes = {n['id']: n for n in nodes(before)}
    checks = []

    def check(name, condition, details=None):
        if not condition:
            raise AssertionError(f'{name}: {details}')
        checks.append(name)

    check('ten_families_twenty_l2_forty_l3_seventy_unique',
          len(tree['families']) == 10 and len(all_nodes) == 70
          and sum(n['tier'] == 2 for n in all_nodes.values()) == 20
          and sum(n['tier'] == 3 for n in all_nodes.values()) == 40)
    check('eight_requested_behavior_axes', len(fixtures['behaviors']) == 8)
    for family in tree['families']:
        check(f"{family['id']}_2_by_2_topology", len(family['l2']) == 2 and all(len(b['l3']) == 2 for b in family['l2']))
    for node in all_nodes.values():
        nid, tier = node['id'], node['tier']
        profile = node['balance_profile']
        correct_price = tier == 1 or node['cost'] == economy['costs'][f'tower_l{tier}_increment']
        good_parent = tier == 1 or (node['parent'] in all_nodes and all_nodes[node['parent']]['tier'] == tier - 1)
        check(nid + '_review_parameters_parent_and_price',
              correct_price and good_parent and bool(profile.get('benchmark_measures'))
              and bool(profile.get('reviewed_against_all_behaviors'))
              and node['parameters'].get('parameters_are_absolute') is True)
        check(nid + '_usable_positive_circle_radii', all(radius >= 1 for _, radius in radii(node)), list(radii(node)))
    check('all_tower_paths_115_to_125_coin_16_spirit',
          all(115 <= family['l1']['cost']['coin'] + 80 <= 125 for family in tree['families'])
          and economy['costs']['tower_l2_increment']['spirit'] + economy['costs']['tower_l3_increment']['spirit'] == 16)
    broadcast_rate = next(e['amount'] for e in all_nodes['T06.B1']['effects'] if e['status'] == 'attack_speed')
    check('broadcast_real_consumer_matches_shared_contract_snapshot', broadcast_rate == .12 and contracts['damage']['vulnerability']['rule_cooperation_source']['base_attack_rate_bonus'] == broadcast_rate)
    flat_traps = [(trap, node, tier) for trap in traps['traps'] for node, tier in trap_nodes(trap)]
    check('sixteen_traps_eighty_reviewed_nodes', len(traps['traps']) == 16 and len(flat_traps) == 80)
    for trap, node, tier in flat_traps:
        check(node['id'] + '_trap_review_and_parameters',
              bool(node['balance_profile'].get('benchmark_measures')) and bool(node['balance_profile'].get('weakness')))
        if tier > 1:
            expected = economy['costs'][f'barrier_l{tier}_per_tile' if trap['id'] == 'R12' else f'trap_l{tier}_increment_except_R12']
            check(node['id'] + '_trap_price', all(node['cost'][k] == expected[k] for k in ('coin', 'spirit')))
    check('all_trap_positive_circular_effects_at_least_one_tile', all(radius >= 1 for _, radius in radii(traps['traps'])))
    baseline_monsters = {m['id']: m for m in old_monsters['monsters']}
    for monster in matchups['monsters']:
        check(monster['id'] + '_preserves_actual_identity_and_action',
              all(monster[key] == baseline_monsters[monster['id']][key] for key in ('id', 'name', 'action', 'default_enabled')))
        categories = [set(monster[k]) for k in ('favorable', 'conditional', 'weak')]
        check(monster['id'] + '_valid_disjoint_branch_choices',
              all(len(s) >= 2 for s in categories) and len(set.union(*categories)) == sum(map(len, categories))
              and all(all_nodes[n]['tier'] == 3 for n in set.union(*categories)))
    check('sixty_existing_monsters_no_new_crowd_skills', len(matchups['monsters']) == 60 and all(not m['crowd_abilities_added'] for m in matchups['monsters']))

    # Same packet, same horizon: short exposure, long investment, physical armor,
    # and spiritual ward are kept distinct rather than averaged into one score.
    offense_rows = []
    for nid in ('T01.A1', 'T01.B1', 'T02.A1', 'T02.A2', 'T07.A1', 'T07.B1', 'T07.B2'):
        for horizon in fixtures['default_fixture']['horizons_s']:
            for label, armor, ward in (('unarmored', 0, 0), ('armor75', .75, 0), ('ward75', 0, .75)):
                result = offense(all_nodes[nid], horizon, armor=armor, ward=ward)
                offense_rows.append({'node': nid, 'defense_case': label, **result})
    get = lambda nid, h, case='unarmored': next(r for r in offense_rows if r['node'] == nid and r['horizon_s'] == h and r['defense_case'] == case)
    check('sniper_wins_8_second_poison_race', get('T01.A1', 8)['damage'] > get('T02.A1', 8)['damage'])
    check('permanent_poison_wins_60_second_continuous_investment', get('T02.A1', 60)['damage'] > get('T01.A1', 60)['damage'])
    check('spiritual_ward_changes_matchup_without_hidden_poison_cap', get('T02.A1', 60, 'ward75')['damage'] < get('T01.A1', 60, 'ward75')['damage'])
    check('sniper_armor_penetration_effective', get('T01.A1', 24, 'armor75')['damage'] == 230.4)
    check('poison_reference_8_24_60', [get('T02.A1', h)['damage'] for h in (8, 24, 60)] == [25.6, 182.8, 1124.8])
    poison_departed = offense(all_nodes['T02.A1'], 60, windows=[(0, 8)])
    check('applied_poison_and_paid_maturation_persist_after_source_los_loss', poison_departed['damage'] > get('T02.A1', 8)['damage'] and poison_departed['poison_q_per_hit_target'] == 12)
    crossover = next(float(t) for t in (q(i) / 10 for i in range(1, 1201))
                     if t >= 8 and offense(all_nodes['T02.A1'], t)['damage'] >= offense(all_nodes['T01.A1'], t)['damage'])
    broad = offense(all_nodes['T07.A1'], 24, target_count=6, partner_dps_per_pool=5)
    sustain = offense(all_nodes['T07.B1'], 24, target_count=6)
    residence = [{'seconds': seconds, 'raw_residence_damage': clean(q(all_nodes['T07.B1']['parameters']['damage_per_second']) * q(seconds))}
                 for seconds in (.75, 2.25, 6)]
    check('minimum_circle_increase_is_paid_with_lower_dps', all_nodes['T07.B1']['parameters']['field_radius_tiles'] >= 1 and all_nodes['T07.B1']['parameters']['damage_per_second'] < old_nodes['T07.B1']['parameters']['damage_per_second'])
    check('small_field_residence_not_full_tick_on_entry', [r['raw_residence_damage'] for r in residence] == [9, 27, 72])
    check('broad_burn_reports_real_ally_increment', broad['partner_extra'] > 0 and broad['damage'] < sustain['damage'])
    curse = curse_expected(all_nodes['T08.A1'])
    check('curse_expected_damage_prevention_not_guaranteed_attack_cancel', 0 < curse['prevented_fraction'] < .5 and curse['expected_incoming_with_curse'] > 0)
    swarm = {nid: primary_swarm(all_nodes[nid]) for nid in ('T01.A1', 'T01.A2', 'T01.B2')}
    check('rapid_split_and_real_line_have_low_hp_swarm_advantage', swarm['T01.B2']['last_defeat_s'] < swarm['T01.A1']['last_defeat_s'] and swarm['T01.A2']['last_defeat_s'] < swarm['T01.A1']['last_defeat_s'])

    # Phase is a named damage audit, never fictitious physical collision.
    fields = {(x, 0): q(6) for x in range(4)}
    ledger, receipts = {}, set()
    walk = normal_toll('P', segment_spans((.25, .5), (3.75, .5), 0, 1), ledger, fields)
    walked = sum(h[2] for h in walk)
    returning = normal_toll('P', segment_spans((3.75, .5), (.25, .5), 1, 1.5), ledger, fields)
    phase = phase_toll('P', 'real_phase_1', (.25, .5), (3.75, .5), 1.5, ledger, receipts, fields)
    duplicate = phase_toll('P', 'real_phase_1', (.25, .5), (3.75, .5), 1.5, ledger, receipts, fields)
    second = phase_toll('P', 'real_phase_2', (3.75, .5), (.25, .5), 1.75, ledger, receipts, fields)
    check('continuous_four_fresh_cells_pay_four', walked == 24)
    check('ordinary_immediate_return_does_not_reset_old_deadlines', not returning)
    check('phase_pays_all_four_despite_old_cooldown', len(phase) == 4 and sum(h[2] for h in phase) == 24)
    check('same_phase_receipt_is_idempotent', not duplicate)
    untouched, untouched_receipts = {}, set()
    zero_phase = phase_toll('Q', 'zero', (.5, .5), (.5, .5), 0, untouched, untouched_receipts, fields)
    canceled_phase = phase_toll('Q', 'canceled', (.5, .5), (3.5, .5), 0, untouched, untouched_receipts, fields, committed=False)
    check('zero_or_canceled_phase_does_not_charge_or_retime', not zero_phase and not canceled_phase and not untouched and not untouched_receipts)
    boundary_fields = {(x, 0): 6 for x in range(5)}
    boundary = phase_toll('Q', 'boundary', (.25, .5), (4, .5), 0, {}, set(), boundary_fields)
    check('actual_boundary_landing_cell_is_included_once', len(boundary) == 5 and sum(h[2] for h in boundary) == 30)
    check('another_real_phase_can_recharge_audit_before_two_seconds', len(second) == 4)
    check('phase_rewrites_only_crossed_deadlines_from_arrival', all(deadline == q(3.75) for deadline in ledger.values()))
    clipped_fields = {cell: damage for cell, damage in fields.items() if cell != (1, 0)}
    clipped = phase_toll('Q', 'phase_over_fixture', (.25, .5), (3.75, .5), 0, {}, set(), clipped_fields)
    check('unprojectable_fixture_cell_excluded_from_phase_audit', sum(h[2] for h in clipped) == 18)
    check('corner_touch_does_not_invent_zones', len(segment_spans((.5, .5), (2.5, 2.5))) == 3)
    samples = [(q(i) / 120, (q(.25) + q(3.5) * q(i) / 120, q(.5))) for i in range(121)]
    many = normal_toll('P', merge_sample_spans(samples), {}, fields)
    check('continuous_toll_is_render_sampling_invariant', many == walk)
    check('mixed_physical_spiritual_overlap_compares_resolved_damage', actual_damage(2, 'physical', ward=.75) > actual_damage(3, 'spiritual', ward=.75))
    zone_rows = {'four_fresh_cells_raw': clean(walked), 'ordinary_immediate_return_raw': 0,
                 'phase_same_cells_raw': clean(sum(h[2] for h in phase)),
                 'duplicate_phase_raw': 0, 'new_phase_before_old_deadline_raw': clean(sum(h[2] for h in second)),
                 'one_solid_cell_excluded_raw': clean(sum(h[2] for h in clipped)),
                 'last_deadline_s': 3.75, 'phase_modes': ['true_teleport', 'shadow_jump', 'mirror_transfer']}

    ec = contracts['statuses']['electric']
    check('electric_calibration_matches_shared_contract', ec['default_overload_base_damage'] == fixtures['electric']['native_overload_D'] and ec['feedback']['per_wave_total_charge_budget'] == fixtures['electric']['feedback_charge_budget_per_wave'])
    for node in all_nodes.values():
        for effect in node['effects']:
            if effect['status'] == 'electric':
                check(node['id'] + '_electric_D_matches_contract', effect['overload_base_damage'] == ec['default_overload_base_damage'])
    electric_rows = []
    aps = ['AP_HOT_FOOD', 'AP_FREEZER']
    for count in (1, 3, 6):
        pools = [f'P{i}' for i in range(count)]
        inputs = [(t, pool, all_nodes['T09.B1']['parameters']['damage'], 1)
                  for t in repeat_events(all_nodes['T09.B1']['parameters']['pulse_cycle_s'], [0], 24) for pool in pools]
        result = run_electric(pools, aps, complete_edges(pools + aps), inputs=inputs, horizon=24,
                              base_d=ec['default_overload_base_damage'], ordinary_bounce=True,
                              feedback_budget=ec['feedback']['per_wave_total_charge_budget'])
        electric_rows.append({'case': f'dense_{count}_two_appliances_24s', 'scope': 'legal_given_edge_graph_infinite_hp_with_once_per_phase_bounce', **result})
        check(f'electric_{count}_feedback_strictly_dissipative', result['all_waves_strictly_dissipative'])
    pools = [f'P{i}' for i in range(6)]
    separated_edges = complete_edges(pools[:3] + aps[:1]) + complete_edges(pools[3:] + aps[1:])
    inputs = [(t, p, 2, 1) for t in repeat_events(all_nodes['T09.B1']['parameters']['pulse_cycle_s'], [0], 24) for p in pools]
    spread = run_electric(pools, aps, separated_edges, inputs=inputs, ordinary_bounce=True)
    electric_rows.append({'case': 'two_disconnected_three_pool_groups', **spread})
    dark = run_electric(pools, aps, complete_edges(pools + aps), inputs=[], powered=False, ordinary_bounce=True)
    electric_rows.append({'case': 'T09_B1_unpowered_no_paid_induction', **dark})
    check('unpowered_induction_does_not_produce_damage_or_marks', dark['total_damage'] == 0 and dark['external_charge'] == 0)
    chain_pools = ['P0', 'P1', 'P2', 'P3']
    chain_edges = [('P0', 'P1'), ('P1', aps[0]), (aps[0], 'P2'), ('P2', 'P3')]
    linked = run_electric(chain_pools, aps[:1], chain_edges, initial={'P0': 5, 'P1': 4.5, 'P2': 4.5, 'P3': 4.5}, horizon=16)
    electric_rows.append({'case': 'multi_hop_partial_charge_chain_no_new_input', **linked})
    check('overload_reaches_remote_connected_pool_beyond_seed_neighbors', 'P3' in linked['wave_trace'][0]['damage'])
    check('electric_damage_feedback_can_trigger_additional_overloads', linked['waves'] > 1)
    check('connected_component_wave_uses_local_not_component_multiplier', len(set(linked['wave_trace'][0]['damage'].values())) > 1)
    check('no_input_chain_eventually_stops', linked['ready_requests'] == 0 and linked['waves'] <= math.floor(18.5 / (5 - ec['feedback']['per_wave_total_charge_budget'])))
    eight = [f'P{i}' for i in range(8)]
    stress = run_electric(eight, aps, complete_edges(eight + aps), initial={p: 5 for p in eight}, horizon=16)
    electric_rows.append({'case': 'eight_full_pools_closed_network', **stress})
    check('eight_pool_overflow_preserved_and_chain_finite', stress['maximum_pool_charge'] > 5 and stress['ready_requests'] == 0 and stress['waves'] <= 40 / 3)
    check('electrical_charge_budget_balances', all(abs(r['external_charge'] + r['feedback_charge'] - r['consumed_charge'] - r['expired_charge'] - r['remaining_charge']) < 1e-4 for r in electric_rows))
    reservations = electric_reservation_fixture()
    check('expired_reserved_charge_requeues_even_when_total_still_five', reservations['A_load_after_reserved_expiry'] == 7 and reservations['new_ready_at'] == 1 and reservations['first_seed_after_expiry'] == 'B' and reservations['broken_reservations'] == 1)
    check('earliest_expiry_reserved_exactly_five_preserves_remainder', reservations['earliest_expiry_reserved_lots'] == [['inherited-earlier-deadline', 4], ['newer-deadline', 1]] and reservations['post_consumption_surplus'] == 2 and reservations['post_consumption_lots'][0]['expires'] == 8)
    dense_six = next(r for r in electric_rows if r['case'] == 'dense_6_two_appliances_24s')
    check('dense_resonance_requires_setup_but_is_not_four_times_sustain', 1 < dense_six['total_damage'] / sustain['damage'] < 2.2)

    check('map_fixture_hash_matches_actual_repository_bytes', traps['map_constraints']['source_sha256'] == hashlib.sha256(locate('content/maps.json').read_bytes()).hexdigest())
    geometry = geometry_examples(traps, read('content/maps.json'))
    for row in geometry['examples']:
        check(row['anchor'] + '_real_floor_field_and_reachable_body', row['anchor_in_actual_fixture'] and row['center_clear_for_0_3_body'] and row['connected_to_front'] and 0 < row['legal_body_center_area'] <= row['clipped_floor_area'] < row['full_circle_area'])
    check('twelve_fixture_projection_examples', len(geometry['examples']) == 12)
    check('actual_appliance_graph_needs_intermediate_freezer', [r['within_2_5_edge_distance'] for r in geometry['appliance_distance_examples']] == [True, True, False])

    weeks = [week_replay(economy, tree, traps, scenario) for scenario in economy['replay_assumptions']['scenarios']]
    for week in weeks:
        check(week['scenario']['id'] + '_seven_days_no_negative_cash_or_spirit', len(week['before_night_rows']) == 7 and all(r['before_night_coin'] >= 0 and r['before_night_spirit'] >= 0 for r in week['before_night_rows']))
        check(week['scenario']['id'] + '_same_week_assets_and_capacity', all(r['tower_count'] <= 8 and r['trap_count'] <= 8 for r in week['before_night_rows']))
        check(week['scenario']['id'] + '_new_week_fresh_budget', week['next_week_coin'] == 120 and week['next_week_spirit'] == 0 and week['next_week_defense_instances'] == ['free_T02_L1'])
        check(week['scenario']['id'] + '_actual_refills_repairs_affordable', week['actual_stock_service_plan_feasible'])
        check(week['scenario']['id'] + '_reset_once_and_old_week_commands_rejected', week['week_boundary']['applied'] and week['repeated_week_reset']['applied'] is False and week['old_week_command_accepted_after_reset'] is False)
        for previous, current in zip(week['before_night_rows'], week['before_night_rows'][1:]):
            check(f"{week['scenario']['id']}_night_{current['night']}_actual_stock_survives_transition",
                  previous['inventory_after_night'] == current['inventory_brought_from_previous_night'])
    standard = next(w for w in weeks if w['scenario']['id'] == 'standard')
    check('standard_has_first_specialist_by_second_preparation', standard['before_night_rows'][1]['l3_towers'] >= 1)
    check('standard_does_not_fill_eight_L3_on_second_night', standard['before_night_rows'][1]['l3_towers'] < 8)
    check('weekly_free_job_tower_cannot_be_sold', economy['wallet_policy']['free_job_tower_sellable'] is False)
    check('daily_change_not_free_refill_or_repair', economy['resupply']['no_per_night_free_charge_or_repair'] is True)
    check('week_reset_clears_inventory_and_late_commands', economy['persistence']['week_clear_includes_undeployed_defense_inventory'] and economy['persistence']['old_week_refund_or_income_can_credit_new_week'] is False)

    depleted_sales = depleted_sale_comparisons(economy, traps)
    repaired_sales = repair_sale_comparisons(economy, traps)
    check('depleted_trap_sale_rebuild_never_beats_equal_refill', len(depleted_sales) == 80 and all(r['rebuild_not_cheaper'] for r in depleted_sales))
    check('repair_then_resale_never_creates_positive_extra_cash', len(repaired_sales) == 400 and all(r['repair_then_sale_not_profitable'] for r in repaired_sales))
    upgrade_receipts = [event for week in weeks for row in week['before_night_rows'] for event in row['purchase_events'] if event.get('before') and event.get('after')]
    capacity_changes = [e for e in upgrade_receipts if e['before'].get('charge_capacity') != e['after'].get('charge_capacity') and e['before'].get('charge_capacity') is not None]
    check('new_charge_capacity_starts_empty_in_actual_purchase_replay', bool(capacity_changes) and all(e['before']['charges'] == e['after']['charges'] for e in capacity_changes))

    all_tree_rows = []
    for nid, node in all_nodes.items():
        ancestor = node
        cost = {'coin': 0, 'spirit': 0}
        while ancestor:
            cost = {key: cost[key] + ancestor['cost'][key] for key in cost}
            ancestor = all_nodes.get(ancestor.get('parent'))
        all_tree_rows.append({'id': nid, 'name': node['name'], 'tier': node['tier'], 'full_path_cost': cost,
                              'td03_nominal': raw_primary_profile(old_nodes[nid]),
                              'td04_nominal': raw_primary_profile(node),
                              'review_decision': node['balance_profile']['review_decision'],
                              'changed_field_names': [change.get('field', change.get('path', str(change))) if isinstance(change, dict) else change for change in node['balance_profile']['changed_from_td03']]})
    script_files = ['scripts/check_td04_balance.py', 'scripts/td04_reference.py', 'scripts/td04_economy_reference.py']
    report = {'version': 'TD04', 'runtime_integrated': False,
              'status': 'all_listed_reference_checks_passed_not_full_gameplay_validation',
              'checks_passed': len(checks), 'checks': checks,
              'input_sha256': {path: hashlib.sha256(locate(path).read_bytes()).hexdigest() for path in files + ['content/maps.json']},
              'model_sha256': {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in script_files},
              'counts': {'tower_families': 10, 'tower_l2': 20, 'tower_l3': 40, 'tower_nodes_reviewed': 70,
                         'trap_families': 16, 'trap_l2': 32, 'trap_l3': 32, 'trap_nodes_reviewed': 80,
                         'monster_entries': 60, 'behavior_axes': 8, 'map_projection_examples': 12},
              'eight_behavior_results': {'offense_windows': offense_rows, 'poison_los_lost_after_8s': poison_departed,
                                         'first_poison_crossover_sample_s': crossover,
                                         'broad_burn_six_with_total_30_ally_dps': broad,
                                         'small_sustain_six_full_residence': sustain,
                                         'residence_raw_examples': residence, 'group_curse': curse,
                                         'direct_only_low_hp_swarm': swarm, 'zone_toll': zone_rows,
                                         'electric_cases': [{key: value for key, value in row.items() if key != 'reservation_trace'} for row in electric_rows], 'electric_reservation_case': reservations},
              'all_70_tower_node_comparisons': all_tree_rows,
              'all_80_trap_node_measures': [{'id': n['id'], 'tier': tier, 'role': n['balance_profile']['intended_role'], 'weakness': n['balance_profile']['weakness'], 'measures': n['balance_profile']['benchmark_measures'], 'full_smallest_path_cost': n['balance_profile']['full_path_cost_for_smallest_footprint']} for _, n, tier in flat_traps],
              'geometry': geometry, 'seven_night_replays': weeks,
              'depleted_sale_comparisons': depleted_sales, 'repair_sale_comparisons': repaired_sales,
              'limits': ['Exact fixtures use given legal hits, occupants and graph edges; actual AI/LOS/navigation is not implemented here.',
                         'Electric graph geometry examples do not prove every runtime connection or dynamic body fit.',
                         'All-node direct metrics are conditional nominal measures, not universal DPS scores.',
                         'Infinite-health fixtures do not estimate actual monster survival except the named direct-only swarm case.',
                         'Income profiles are assumptions for affordability, not measured player success rates.',
                         'Reference week reset is a model, not a tested production save-file transaction.',
                         'V0.10 runtime and artwork are unchanged.']}
    # Keep receipts useful but do not duplicate large inventory snapshots many
    # times. The functions above still expose full state for further analysis.
    inventory_keys = ('instance_id', 'node_id', 'tier', 'charges', 'charge_capacity', 'hp', 'max_hp', 'location')
    mini = lambda asset: {k: asset[k] for k in inventory_keys if k in asset}
    for week in report['seven_night_replays']:
        for row in week['before_night_rows']:
            for key in ('inventory_brought_from_previous_night', 'inventory_before_night', 'inventory_after_night'):
                row[key] = [mini(a) for a in row[key]]
            for event in row['purchase_events']:
                for key in ('before', 'after'):
                    if key in event and isinstance(event[key], dict):
                        event[key] = mini(event[key])
        week['week_boundary']['cleared_instances'] = [mini(a) for a in week['week_boundary']['cleared_instances']]
    output = ROOT / args.report
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(clean(report), ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'checks_passed': len(checks), 'report': str(output),
                      'poison_first_crossover_s': crossover,
                      'dense_resonance_24s': dense_six['total_damage'],
                      'small_sustain_six_24s': sustain['damage'],
                      'week_7_l3_counts': {w['scenario']['id']: w['before_night_rows'][-1]['l3_towers'] for w in weeks}}, ensure_ascii=False))


if __name__ == '__main__':
    main()
