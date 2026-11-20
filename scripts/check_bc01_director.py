#!/usr/bin/env python3
"""Behavioral BC01 director checks using assembled-map routes and continuous time."""
from __future__ import annotations
import copy
import json
import math
from pathlib import Path

from bc01_director_reference import Director, run_night
from bc01_map_reference import StoreMap, encounter_catalog

ROOT = Path(__file__).resolve().parents[1]
CHECKS = []

def check(name, condition, evidence=None):
    row = {'name': name, 'passed': bool(condition)}
    if evidence is not None:
        row['evidence'] = evidence
    CHECKS.append(row)
    if not condition:
        raise AssertionError(name + ': ' + repr(evidence))


def finish(d):
    while not d.state['settled'] and d.now < 1800:
        d.advance(.25)
        if d.state['error']:
            break
    return d.report()


def main():
    nav = StoreMap()
    leave_pool = [p for p in encounter_catalog(7) if not p['requires_combat_after_rule']]
    cases = []
    trace = None
    for seed in range(1, 25):
        r = run_night(seed, nav, encounter_pool=leave_pool, night_index=7)
        s = r['summary']; cases.append(s)
        if seed == 4:
            trace = r
        check(f'seed {seed}: actual route night settles', s['settled'] and s['finished_at'] >= 720 and s['error'] is None)
        check(f'seed {seed}: no ordinary chores during RAID', s['ordinary_work_during_raid_seconds'] == 0)
        check(f'seed {seed}: bounded orders are real outputs', 0 < s['paid_orders'] <= 12 and s['customer_travel_tiles'] > 0)
        check(f'seed {seed}: bounded roots and actual raid time', 1 <= s['resolved_raids'] <= 4 and s['active_raid_seconds'] > 0)
        check(f'seed {seed}: no safe idle survival reward', 0 <= s['survival_eligible_seconds'] <= s['active_raid_seconds'] < 720)
        check(f'seed {seed}: world blackout cap', 0 <= s['grid_surge_count'] <= 2)
        active_customers = set(); raid_active = False; posted_orders = set(); posted_rewards = set()
        for event in r['events']:
            if event['kind'] == 'customer_arrived':
                check(f'seed {seed}: arrival has a safe phase at {event["time"]}', event['phase'] == 'BUSINESS' and not raid_active)
                active_customers.add(event['customer_id'])
            elif event['kind'] == 'customer_exit_completed':
                active_customers.discard(event['customer_id'])
                check(f'seed {seed}: exit reaches actual boundary {event["customer_id"]}', math.dist(event['position'], nav.position('street_boundary')) < 1e-6)
            elif event['kind'] == 'raid_started':
                check(f'seed {seed}: no customer or shop cargo at raid spawn {event["raid_id"]}', not active_customers and not raid_active and event['ordinary_cargo_in_hands'] is False)
                check(f'seed {seed}: actual spawn gap {event["raid_id"]}', all(math.dist(event['player_position'], pos) >= 5 for pos in event['initial_actor_positions'].values()))
                raid_active = True
            elif event['kind'] == 'raid_ended':
                check(f'seed {seed}: completed route needed for terminal {event["raid_id"]}', raid_active and event['receipt']['main_rule_completed'] is True)
                raid_active = False
            elif event['kind'] == 'order_paid':
                receipt = event['receipt']; posted_orders.add(receipt['event_id'])
                check(f'seed {seed}: sale has actual entry/use/payment {receipt["order_id"]}', receipt['physical_entry_at'] < receipt['completed_at'] and receipt['paid'] and receipt['verified'] and receipt['actual_action_receipts'][-1]['action_id'] == 'normal_checkout')
                check(f'seed {seed}: sale receipt unique {receipt["order_id"]}', receipt['event_id'] not in posted_rewards)
                posted_rewards.add(receipt['event_id'])
            elif event['kind'] == 'chore_completed':
                receipt = event['receipt']
                check(f'seed {seed}: chore never billed twice {receipt["chore_id"]}', receipt['event_id'] not in posted_rewards and receipt['completed'] and receipt['verified'])
                check(f'seed {seed}: actual chore travel included {receipt["chore_id"]}', receipt['duration_s'] > 0 and any(x['kind'] == 'travel' for x in receipt['actual_action_receipts']))
                if receipt['kind'] == 'restore_power':
                    check(f'seed {seed}: repair has actual outage source {receipt["chore_id"]}', bool(receipt['outage_id']) and receipt['monster_caused'] and receipt['reward_kind'] == 'breaker_reset')
                posted_rewards.add(receipt['event_id'])
            elif event['kind'] == 'facility_use_committed':
                use = event['request']
                check(f'seed {seed}: facility bank follows same paid receipt {use["event_id"]}', use['paid_order_receipt']['event_id'] in posted_orders and use['facts']['actual_use_completed'] and use['facts']['source_item_id'] == use['paid_order_receipt']['items'][0]['source_item_id'])
                if use['facility_id'] == 'FR10':
                    check(f'seed {seed}: door credit after paid physical exit {use["event_id"]}', use['facts']['exit_boundary_crossed'] and use['facts']['actual_use_at'] >= use['paid_order_receipt']['completed_at'])
        check(f'seed {seed}: final ledger receipts unique', len(posted_rewards) == len(r['orders']) + len(r['chores']))
    check('normal shopping never creates blood or player wounds', all(
        e['patch_type'] != 'blood' and e['biological_owner'] is None and not e['is_player_wound']
        for e in trace['events'] if e['kind'] == 'registered_floor_patch_created' and e['source_kind'] == 'normal_customer_use'))
    check('ghost rule-leave residue never creates biological blood', all(
        e['patch_type'] != 'blood' and e['biological_owner'] is None and not e['can_activate_blood_conditional_encounters']
        for e in trace['events'] if e['kind'] == 'registered_floor_patch_created' and e['source_kind'] == 'post_raid_ordinary_residue'))
    check('random first alarms are not fixed hourly slots', len({x['phases'][0]['at'] for x in cases}) >= 6)
    check('normal orders vary with measured routes/actions', len({x['paid_orders'] for x in cases}) > 1)
    check('blackout random stream can generate zero, one or two', {x['grid_surge_count'] for x in cases} == {0, 1, 2})
    check('first two nights never get grid-surge modifier', all(run_night(4, nav, night_index=i)['summary']['grid_surge_count'] == 0 for i in [1, 2]))

    # Restore checkpoints in business, prelude, actor response, blackout and recovery.
    # This compares the entire event suffix + money candidate receipts + RNG + objects.
    replay = []
    for cut in [42.0, 99.25, 100.0, 120.0, 260.0, 420.0, 600.0]:
        d = Director(4, nav, encounter_pool=leave_pool, night_index=7)
        d.advance(cut)
        snapshot = d.snapshot()
        restored = Director.from_snapshot(snapshot, nav)
        left, right = finish(d), finish(restored)
        same = left['snapshot'] == right['snapshot']
        check(f'checkpoint replay exact at {cut}s', same)
        replay.append({'cut_at': cut, 'phase': snapshot['phase'], 'exact_state_and_event_suffix': same})
    d = Director(4, nav, encounter_pool=leave_pool, night_index=7)
    d.advance(99.25); before = d.snapshot(); d.advance(900, paused=True)
    check('pause advances no world work or RNG', before == d.snapshot())

    # A shop item survives interruption with original identity and cannot occupy
    # the hands during combat, then requires a real walk back and pickup.
    stows = [e for e in trace['events'] if e['kind'] == 'store_item_safely_set_down']
    check('actual full-night trace exercises interrupted carried goods', len(stows) >= 1)
    for stow in stows:
        carry = stow['carry_pause']
        pickups = [e for e in trace['events'] if e['kind'] == 'store_item_taken' and e['source_item_id'] == carry['source_item_id'] and e['time'] > stow['time']]
        check('stowed original item remains nonblocking and same identity ' + carry['source_item_id'], carry['released_hands'] and carry['blocks_navigation'] is False and carry['actual_setdown_seconds'] == .5 and bool(pickups) and pickups[0]['same_original'])
        check('resume physically returns to exact original item ' + carry['source_item_id'], math.dist(pickups[0]['position'], carry['position']) < 1e-6)

    # Unsafe commands are rejected. A non-lethal rule script cannot end combat
    # and a 720s deadline does not manufacture a kill or survival money extension.
    damage_plan = next(p for p in encounter_catalog(7) if p['monster_id'] == 'F13')
    blocked = Director(6, nav, encounter_pool=[damage_plan], night_index=7)
    while not (blocked.state['raid'] and blocked.state['raid'].get('unresolved_reason')):
        blocked.advance(.25)
    raid = copy.deepcopy(blocked.state['raid'])
    check('no damage resolver leaves a real unresolved threat', not blocked.state['raids'] and not blocked.state['settled'])
    job = blocked._offer_clean('test-actual-source')
    if job:
        check('ordinary chore start rejected while chased', not blocked.start_chore(job['chore_id']))
    active_before = blocked.state['active_raid_seconds']
    blocked.advance(900)
    check('night deadline cannot auto-win unresolved threat', blocked.state['closing'] and not blocked.state['settled'] and blocked.state['raid']['raid_id'] == raid['raid_id'])
    eligible_before = blocked.state['eligible_survival_seconds']; blocked.advance(10)
    check('extension adds no survival reward seconds', blocked.state['eligible_survival_seconds'] == eligible_before and blocked.state['active_raid_seconds'] > active_before)
    forged = {'event_id': 'forged', 'night_id': raid['night_id'], 'attempt_id': 999, 'raid_id': raid['raid_id'], 'monster_id': raid['monster_id'], 'terminal_kind': 'defeated', 'source': 'root_lifecycle', 'verified': True, 'actual_terminal': True, 'hp_after': 0}
    check('wrong attempt root terminal rejected', not blocked.complete_raid(forged))
    forged['attempt_id'] = raid['attempt_id']; forged['hp_after'] = 1
    check('nonzero HP cannot be called defeated', not blocked.complete_raid(forged))
    # Adapter boundary test, not a claim that this fixture defeated a live F13 AI.
    forged['hp_after'] = 0; forged['main_rule_completed'] = True
    check('scoped true HP-zero terminal permits late settlement', blocked.complete_raid(forged))
    check('duplicate root terminal rejected', not blocked.complete_raid(forged))
    blocked.advance(.25)
    check('late valid terminal auto-settles without manager ceremony', blocked.state['settled'])

    # Proficiency affects only manual base progress and changes live when buffs end.
    d = Director(1, nav, encounter_pool=leave_pool, action_duration_factor=.6)
    p = d._plan([{'kind': 'action', 'seconds': 4, 'action_id': 'manual_test'}])
    d.state['now'] = 1; d._advance_plan(p, 1, owner='test', receipt_prefix='manual')
    remaining = p['remaining']; d.state['action_duration_factor'] = 1
    d.state['now'] += remaining; d._advance_plan(p, remaining, owner='test', receipt_prefix='manual')
    check('buff end immediately changes remaining manual duration', p['done'] and abs(p['used_seconds'] - (1 + 4 - 1/.6)) < 1e-7)
    p = d._plan([{'kind': 'wait', 'actor': 'monster', 'seconds': 2.5, 'reason': 'S40 actual collection'}])
    d.state['action_duration_factor'] = .6; d._advance_plan(p, 2.49, owner='test', receipt_prefix='wait')
    check('NPC world wait never receives player proficiency', not p['done'] and abs(p['remaining'] - .01) < 1e-7)
    d._advance_plan(p, .01, owner='test', receipt_prefix='wait')
    check('NPC wait completes only at full authored duration', p['done'] and abs(p['used_seconds']-2.5) < 1e-7)
    d.state['player_move_speed'] = 3.6
    p = d._plan([{'kind': 'travel', 'to': [8.5, 27.5], 'speed': 3}], start=[7.5, 27.5])
    d._advance_plan(p, 1, owner='test', receipt_prefix='moving')
    check('live movement buff also applies to authored player gait', p['done'] and abs(p['used_seconds'] - 1/3.6) < 1e-7)
    p = d._plan([{'kind': 'travel', 'actor': 'monster', 'from': [7.5, 27.5], 'to': [8.5, 27.5], 'speed': 3}], start=[7.5, 27.5])
    d._advance_plan(p, 1, owner='test', receipt_prefix='npc-moving')
    check('player movement buff does not accelerate monster path', p['done'] and abs(p['used_seconds'] - 1/3) < 1e-7)
    p = d._plan([{'kind': 'travel', 'to': [8.5, 27.5], 'speed': 2.4}], start=[7.5, 27.5])
    d.state['player_carry_multiplier'] = 1.0
    d._advance_plan(p, 1, owner='test', receipt_prefix='carry-unboosted')
    unboosted_seconds = p['used_seconds']
    p = d._plan([{'kind': 'travel', 'to': [8.5, 27.5], 'speed': 2.4}], start=[7.5, 27.5])
    d.state['player_carry_multiplier'] = 1.1
    d._advance_plan(p, 1, owner='test', receipt_prefix='carry-boosted')
    check('ordinary speed cannot boost cargo but explicit carry multiplier can',
          abs(unboosted_seconds - 1/2.4) < 1e-7 and abs(p['used_seconds'] - 1/2.64) < 1e-7)
    d = Director(10, nav, encounter_pool=leave_pool, night_index=7)
    while d.state['phase'] != 'RAID': d.advance(.25)
    check('actual monster blackout changes power', d.monster_blackout('unique-monster-pulse', d.state['raid']['monster_id']))
    check('same outage cannot create another reward', not d.monster_blackout('unique-monster-pulse', d.state['raid']['monster_id']))
    check('second pulse while off cannot create repair job', not d.monster_blackout('other-pulse', d.state['raid']['monster_id']))
    check('tactical breaker requires real panel proximity', not d.request_tactical_breaker())
    # A known at-panel initial condition tests the optional input, not movement.
    d.state['player_position'] = nav.position('power_panel')
    check('at-panel player can opt into tactical reset', d.request_tactical_breaker())
    d.advance(1)
    repairs = [r for r in d.state['chore_receipts'] if r['kind'] == 'restore_power']
    check('optional tactical reset restores once without ordinary chore', d.state['power_on'] and len(repairs) == 1 and repairs[0]['tactical_optional'] and d.state['ordinary_work_during_raid_seconds'] == 0)

    # Repeatable seed on a retried attempt retains root schedule identities, while
    # action/payment receipts belong to their new attempt and external rollback.
    a = run_night(3, nav, encounter_pool=leave_pool, night_index=7, attempt_id=1)
    b = run_night(3, nav, encounter_pool=leave_pool, night_index=7, attempt_id=2)
    check('retry retains planned root identity', [r['raid_id'] for r in a['raids']] == [r['raid_id'] for r in b['raids']])
    check('retry payment receipts remain attempt scoped', {r['event_id'] for r in a['orders']}.isdisjoint({r['event_id'] for r in b['orders']}))
    check('retry root actions remain attempt scoped', {r['actual_action_receipts'][0]['event_id'] for r in a['raids']}.isdisjoint({r['actual_action_receipts'][0]['event_id'] for r in b['raids']}))

    # Real subsystem adapter handshake. Nothing here adds missing truth flags.
    from bc01_facility_reference import FacilitiesBC01
    fixture = run_night(3, nav, encounter_pool=leave_pool, night_index=7, attempt_id=1, action_duration_factor=.75)
    facilities = FacilitiesBC01(fixture['summary']['night_id'], 1, design_simulation=True)
    uses = []
    for i, event in enumerate(fixture['events']):
        if event['time'] > facilities.state['now']:
            facilities.actual_world_tick('director-test-tick-' + str(i), event['time'], True)
        if event['kind'] == 'facility_use_committed':
            result = facilities.customer_use(**event['request'])
            uses.append({'facility_id': event['request']['facility_id'], 'ok': result['ok'], 'reason': result['reason']})
        elif event['kind'] == 'raid_started': facilities.raid_started(event['raid_id'])
        elif event['kind'] == 'raid_ended': facilities.raid_ended(event['raid_id'])
        elif event['kind'] == 'power_changed': facilities.power_changed('director-power-' + str(i), 'MAIN', event['power_on'])
    check('actual routed paid and exit receipts accepted by facilities', bool(uses) and all(u['ok'] for u in uses), uses)
    check('actual facility handshake includes post-payment physical door exit', any(u['facility_id']=='FR10' for u in uses))

    report = {'version': 'BC01', 'scope': 'continuous_720s_director_with_real_routes_and_finite_leave_scripts_not_full_monster_AI',
              'passed': sum(c['passed'] for c in CHECKS), 'failed': sum(not c['passed'] for c in CHECKS),
              'checks': CHECKS, 'continuous_seed_cases': cases, 'snapshot_replays': replay,
              'real_facility_adapter_receipts': uses,
              'full_trace_example': {'seed': 4, 'summary': trace['summary'], 'events': trace['events'],
                                     'orders': trace['orders'], 'chores': trace['chores'],
                                     'raids': [{'raid_id': r['raid_id'], 'monster_id': r['monster_id'], 'started_at': r['started_at'], 'ended_at': r['ended_at'], 'terminal_receipt':r['terminal_receipt']} for r in trace['raids']]},
              'limits': ['No complete 105-monster AI or player input client is simulated.',
                         'Finite leave plans assume registered same-original-object predicates; actual walk, waits, actor exit and timing are executed.',
                         'Combat-required roots stay unresolved without an external actual-damage resolver.',
                         'Tick-boundary timing resolution is 0.25 seconds; routes and action work are not rounded to fake whole durations.',
                         'Order and chore rewards are candidate receipts consumed exactly once by the shared campaign ledger.']}
    path = ROOT / 'docs' / 'bc01_director_report.json'
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(json.dumps({'passed': report['passed'], 'failed': report['failed'],
                      'continuous_nights': len(cases), 'snapshot_replays': len(replay),
                      'actual_facility_uses': len(uses), 'report': str(path.relative_to(ROOT))}, ensure_ascii=False))


if __name__ == '__main__':
    main()
