#!/usr/bin/env python3
"""Exercise finite full-lifecycle designs and real static map travel, not client AI."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'prototype'))
from mechanism_model_v010 import ContractModel, MapRoutes, all_of, tile, facing_geometry, mutate


def validate(require_all=True):
    maps = json.loads((ROOT / 'content/maps.json').read_text())
    routes = MapRoutes(next(s for s in maps['scenes'] if s['id'] == 'MAP_STORE'))
    files = sorted((ROOT / 'content').glob('mechanism_cases_v010_*.json'))
    cases = [c for f in files for c in json.loads(f.read_text())['cases']]
    errors, results = [], []
    counters = {'scenario_traces': 0, 'reached_guard_mutations': 0,
                'interrupted_operations': 0, 'deadline_cases': 0,
                'post_close_replay_checks': 0, 'local_window_checks': 0, 'geometry_counterexamples':0,
                'committed_actions':0, 'declared_expiry_observations':0, 'dawn_no_late_work_checks':0,
                'elapsed_deadline_checks':0, 'exact_boundary_checks':0,
                'immutable_timer_checks':0, 'automatic_hazard_checks':0}
    ids = [c['id'] for c in cases]
    if len(ids) != len(set(ids)):
        errors.append('Duplicate encounter model IDs')
    if require_all and set(ids) != {f'F{i:02}' for i in range(1, 61)}:
        errors.append('Expected exactly F01–F60 finite models')
    for case in cases:
        cid = case['id']
        try:
            initial = case['initial_state']
            if set(initial) != set(case['state_sources']):
                raise ValueError('Every initial value must have an explicit producer or real-state origin')
            if any(not v.get('description') for v in case['state_sources'].values()):
                raise ValueError('Empty state-source description')
            required = ['deadline', 'cleanup', 'reservations', 'fun', 'success_when', 'unimplemented_world_adapter']
            for field in required:
                if field not in case:
                    raise ValueError('Missing '+field)
            if set(case['fun']) < {'decision', 'observable_feedback', 'skill', 'optional_gain', 'anti_repetition', 'complexity_limit'}:
                raise ValueError('Incomplete gameplay rationale')
            action_ids = [a['id'] for a in case['actions']]
            if len(action_ids) != len(set(action_ids)):
                raise ValueError('Duplicate action ID')
            for action in case['actions']:
                if action.get('seconds', -1) < 0:
                    raise ValueError('Negative or absent duration '+action['id'])
                if action.get('kind') not in ('work', 'observe', 'recovery', 'choice', 'wait'):
                    raise ValueError('Unknown action kind '+action['id'])
                if action.get('clock') not in ('world', 'budget'):
                    raise ValueError('Unspecified clock '+action['id'])
                if not action.get('evidence'):
                    raise ValueError('No physical or observable evidence '+action['id'])
                if tile(routes.point(action)) not in routes.walkable:
                    raise ValueError('Blocked interaction point '+action['id'])
                local = action.get('local_path')
                if local:
                    points = local['positions']
                    if not points or points[0] != routes.point(action) or points[-1] != action.get('end_position'):
                        raise ValueError('Local movement does not preserve actual start/end '+action['id'])
                    if any(tile(point) not in routes.walkable for point in points):
                        raise ValueError('Local timed path crosses a wall '+action['id'])
                    if any(abs(a[0]-b[0])+abs(a[1]-b[1]) != 1 for a,b in zip(points,points[1:])):
                        raise ValueError('Non-adjacent cells in local timed path '+action['id'])
                    if len(points)-1 != local['distance_tiles']:
                        raise ValueError('Incorrect local route length '+action['id'])
                    if local.get('movement_seconds_included',0)+local.get('work_seconds_included',0)>action['seconds']+1e-8:
                        raise ValueError('Local movement omitted from operation time '+action['id'])
                    if action['seconds']>local.get('must_finish_before_window_seconds',float('inf'))+1e-8:
                        raise ValueError('Local operation cannot fit its window '+action['id'])
                    counters['local_window_checks'] += 1
                used = set(action.get('sets', {})) | set(action.get('adds', {})) | set(action.get('consumes', {}))
                used |= {p['key'] for p in action.get('requires', [])}
                if not used <= set(initial):
                    raise ValueError(f"Unregistered state keys in {action['id']}: {sorted(used-set(initial))}")
            kinds = {s['kind'] for s in case['scenarios']}
            if not {'normal', 'recovery'} <= kinds or not kinds & {'prevention', 'decline', 'source_lost'}:
                raise ValueError('Need normal, actual-error recovery and an alternate lifecycle')
            model = ContractModel(case, routes)
            if case.get('geometry_contract'):
                contract=case['geometry_contract']
                for probe in contract['geometry_cases']:
                    geometry_state=deepcopy(initial)
                    for key,value in zip(contract['player_position_keys'],probe['player']):geometry_state[key]=value
                    for key,value in zip(contract['entity_position_keys'],probe['entity']):geometry_state[key]=value
                    geometry_state[contract['player_facing_key']]=probe['player_facing']
                    geometry_state[contract['entity_facing_key']]=probe['entity_facing']
                    geometry_state[contract['curtain_closed_key']]=probe['closed']
                    actual_geometry=facing_geometry(geometry_state,contract,routes.scene)
                    if actual_geometry[contract['derived_line_blocked_key']]!=probe['line_blocked'] or actual_geometry[contract['derived_direct_gaze_key']]!=probe['direct_gaze']:
                        raise ValueError('Geometry counterexample failed '+probe['id'])
                    counters['geometry_counterexamples']+=1
            if model.terminal(model.begin()) != 'active':
                raise ValueError('Initial state is already terminal')
            witnesses = []
            reached = set()
            committed_reached = set()
            explicitly_expired = set()
            for scenario in case['scenarios']:
                if not set(scenario.get('initial_overrides', {})) <= set(initial):
                    raise ValueError('Scenario introduces an unregistered source')
                trace = model.begin(scenario)
                if model.terminal(trace) != 'active':
                    raise ValueError('Scenario injects an already solved state '+scenario['id'])
                for action_id in scenario['steps']:
                    action = model.actions[action_id]
                    if not model.can_start(trace, action):
                        raise ValueError(scenario['id']+': unmet prerequisites for '+action_id)
                    if model.terminal(trace) == 'active':
                        overdue = deepcopy(trace)
                        deadline, clock, due = model.deadline(overdue)
                        setattr(overdue, clock, due + 0.01)
                        expected_expiry = mutate(overdue.state, deadline.get('on_expiry', {}))
                        response = model.perform(overdue, action_id, include_route=False)
                        if response['accepted'] or not overdue.fired_deadline or overdue.state != expected_expiry:
                            raise ValueError('Actual late action escaped its phase deadline '+action_id)
                        counters['elapsed_deadline_checks'] += 1
                    reached.add(action_id)
                    # Test a missing concrete prerequisite from a state that really
                    # reaches the action, rather than testing arbitrary all-false input.
                    for guard in action.get('requires', []):
                        wrong = deepcopy(trace)
                        wrong.state.pop(guard['key'])
                        snapshot = deepcopy(wrong)
                        response = model.perform(wrong, action_id, include_route=False)
                        if response['accepted'] or wrong != snapshot:
                            raise ValueError('Missing prerequisite charged or mutated '+action_id)
                        counters['reached_guard_mutations'] += 1
                    interrupted = deepcopy(trace)
                    before = deepcopy(trace.state)
                    model.perform(interrupted, action_id, cancel=True, include_route=False)
                    expected_cancel = deepcopy(before)
                    for event in interrupted.timer_events[len(trace.timer_events):]:
                        if event['event'] == 'expired':
                            expected_cancel = mutate(expected_cancel, event['effect'])
                    for timer in model._timer_definitions():
                        if timer.get('remaining_key'):
                            expected_cancel[timer['remaining_key']] = interrupted.state[timer['remaining_key']]
                    if interrupted.state != expected_cancel:
                        raise ValueError('Cancelled operation transferred state '+action_id)
                    counters['interrupted_operations'] += 1
                    response=model.perform(trace, action_id)
                    expected_rejection=scenario.get('expected_rejections',{}).get(action_id)
                    if expected_rejection:
                        if response['accepted'] or response.get('reason')!=expected_rejection:
                            raise ValueError('Expected expiry did not occur '+scenario['id']+'/'+action_id)
                        if not any(e['event']=='expired' for e in trace.timer_events):
                            raise ValueError('Declared expiry lacks an actual elapsed timer '+action_id)
                        explicitly_expired.add(action_id)
                        counters['declared_expiry_observations']+=1
                    elif not response['accepted']:
                        raise ValueError('Operation never committed '+scenario['id']+'/'+action_id+': '+response['reason'])
                    else:
                        committed_reached.add(action_id)
                        counters['committed_actions']+=1
                    if cid=='F53':
                        if trace.budget>720+1e-8:
                            raise ValueError('F53 performs work or walks after real 06:00 '+action_id)
                        counters['dawn_no_late_work_checks']+=1
                actual = model.terminal(trace)
                if actual != scenario['expected']:
                    raise ValueError(f"{scenario['id']}: expected {scenario['expected']}, got {actual}; assertion={all_of(trace.state, scenario.get('assert', []))}")
                model.finish(trace)
                for action_id in scenario.get('post_terminal_steps', []):
                    if model.actions[action_id].get('reward_scope') is not True:
                        raise ValueError('Post-terminal action is not an independently declared reward')
                    if not model.perform(trace, action_id)['accepted']:
                        raise ValueError('Post-terminal gift missing concrete claim prerequisites '+action_id)
                    reached.add(action_id)
                    committed_reached.add(action_id)
                    once = deepcopy(trace)
                    if model.perform(trace,action_id,include_route=False)['accepted'] or trace != once:
                        raise ValueError('Separate gift can be claimed twice '+action_id)
                if not all_of(trace.state, scenario.get('assert', [])):
                    raise ValueError('Post-operation state assertion failed '+scenario['id'])
                closed_before = deepcopy(trace)
                for action in case['actions']:
                    if action.get('reward_scope'):
                        continue
                    if model.perform(trace, action['id'], include_route=False)['accepted']:
                        raise ValueError('Closed receipt allowed replay '+action['id'])
                    counters['post_close_replay_checks'] += 1
                if trace != closed_before:
                    raise ValueError('Replay changed closed state')
                witnesses.append({'id': scenario['id'], 'kind': scenario['kind'], 'terminal': actual,
                                  'budget_seconds': round(trace.budget, 4),
                                  'world_seconds': round(trace.world, 4),
                                  'static_travel_seconds': round(trace.travel, 4),
                                  'actual_steps': len(trace.records),
                                  'world_adapter_proven': False})
                counters['scenario_traces'] += 1
            expiry = model.begin()
            _, clock, due = model.deadline(expiry)
            elapsed = due - getattr(expiry, clock)
            model.advance_time(expiry, elapsed, elapsed)
            if not expiry.fired_deadline or model.terminal(expiry) not in ('expired', 'failed'):
                raise ValueError('Missing finite expiry terminal')
            counters['deadline_cases'] += 1
            unexercised=set(action_ids)-committed_reached-explicitly_expired
            if unexercised:
                raise ValueError('Unexercised actual actions: '+', '.join(sorted(unexercised)))
            results.append({'id': cid, 'status': 'PASS', 'witnesses': witnesses,
                            'actions_reached': len(reached), 'actions_authored': len(action_ids),
                            'actions_committed':len(committed_reached),
                            'explicit_expiry_observation_actions':sorted(explicitly_expired),
                            'unexercised_actions': sorted(unexercised),
                            'candidate_enabled': cid != 'F14', 'runtime_enabled': False})
        except (KeyError, ValueError, TypeError, AssertionError) as exc:
            errors.append(cid+': '+str(exc))
            results.append({'id': cid, 'status': 'FAIL', 'reason': str(exc)})
    # Counterexamples run through the public action/time interpreter, not expire().
    by_id = {c['id']:c for c in cases}
    try:
        if 'F01' in by_id:
            model = ContractModel(by_id['F01'], routes)
            late = model.begin({'world':119, 'budget':119})
            if model.perform(late, 'weigh')['accepted'] or late.budget != 120 or late.state['box_location'] != 'receiving':
                raise ValueError('F01: work crossing 120 committed or advanced beyond the deadline')
            counters['exact_boundary_checks'] += 1
            carried = model.begin()
            model.perform(carried, 'weigh')
            carried.world = carried.budget = 119
            if model.perform(carried, 'measure')['accepted'] or carried.budget != 120 or carried.state['volume_seen']:
                raise ValueError('F01: a route crossing 120 reached and completed the remote operation')
            counters['exact_boundary_checks'] += 1
            for extra, expected in [(0, 'resolved'), (0.01, 'expired')]:
                trace = model.begin()
                for action in ['weigh', 'measure']: model.perform(trace, action)
                trace.world = trace.budget = 118 + extra
                response = model.perform(trace, 'sort')
                if model.terminal(trace) != expected or response['accepted'] != (extra == 0):
                    raise ValueError('F01: exact completion and 0.01-second-late completion were not distinguished')
                counters['exact_boundary_checks'] += 1
        if 'F03' in by_id:
            model = ContractModel(by_id['F03'], routes)
            trace = model.begin({'phase_start_budget':600, 'phase_start_world':600,
                                 'budget':600, 'world':600})
            if model.deadline(trace)[2] != 720:
                raise ValueError('F03: unaccepted offer was rebased to late arrival')
            model.perform(trace, 'take_a')
            if model.deadline(trace)[2] != 720:
                raise ValueError('F03: accepted cross-phase threat escaped true dawn')
            counters['exact_boundary_checks'] += 2
        if 'F50' in by_id:
            model = ContractModel(by_id['F50'], routes)
            trace = model.begin()
            model.perform(trace, 'observe_target')
            saved = deepcopy(trace)
            if model.perform(trace, 'observe_target')['accepted'] or trace != saved:
                raise ValueError('F50: observation reset the locked 8-second impact')
            counters['immutable_timer_checks'] += 1
            for extra, hit in [(0, False), (0.01, True)]:
                probe = deepcopy(saved)
                due = probe.timers['locked_dive']
                probe.world = probe.budget = due - 0.25 + extra
                model.perform(probe, 'retreat_safe', include_route=False)
                if not probe.state['impact_completed'] or probe.state['impact_hit'] != hit or probe.state['san'] != (72 if hit else 80):
                    raise ValueError('F50: impact did not distinguish exact safe exit from late exit')
                after_hit = probe.state['san']
                model.advance_time(probe, 3, 3)
                if probe.state['san'] != after_hit:
                    raise ValueError('F50: the same impact was charged twice')
                counters['automatic_hazard_checks'] += 2
        if 'F58' in by_id:
            model = ContractModel(by_id['F58'], routes)
            trace = model.begin()
            model.perform(trace, 'cover_hot_portion')
            before = trace.state['hot_quality_remaining']
            model.advance_time(trace, 5, 5)
            if abs(trace.state['hot_quality_remaining'] - (before-5)) > 1e-8:
                raise ValueError('F58: quality only ages when the scripted wait is clicked')
            counters['automatic_hazard_checks'] += 1
            model.perform(trace, 'wrong_take_last')
            model.advance_time(trace, 3, 3)
            if not trace.state['boundary_contracted'] or model.perform(trace, 'replace_same_portion')['accepted']:
                raise ValueError('F58: late replacement erased an already contracted boundary')
            counters['automatic_hazard_checks'] += 1
    except (KeyError, ValueError, TypeError, AssertionError) as exc:
        errors.append('Clock counterexample: '+str(exc))
    scope = [
        'Executes authored finite object/permission/resource transitions from sourced admission snapshots to terminal predicates.',
        'Calculates four-neighbour walking time between actual authored control positions. Pre-omen approach from the live player position remains a mandatory runtime admission input.',
        'Checks reached prerequisite removal, cancellation without object transfer, expiry, and replay after terminal closure.',
        'Does not prove arbitrary states, simultaneous moving enemies, geometry during pursuit, complete continuous-clock AI, touch input, rendering, or a full seven-night client.',
        'An explicit scenario source is a design producer contract; it is not proof that every corresponding world adapter has shipped.',
    ]
    return {'version': '0.10', 'status': 'PASS' if not errors else 'FAIL',
            'scope': scope, 'model_count': len(cases), 'counts': counters,
            'sources': {f.relative_to(ROOT).as_posix(): hashlib.sha256(f.read_bytes()).hexdigest() for f in files},
            'results': results, 'errors': errors}


if __name__ == '__main__':
    report = validate(require_all='--partial' not in sys.argv)
    (ROOT / 'docs/mechanism_validation_v010.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
    print(json.dumps({k:v for k,v in report.items() if k not in ('results', 'sources')},ensure_ascii=False,indent=2))
    raise SystemExit(bool(report['errors']))
