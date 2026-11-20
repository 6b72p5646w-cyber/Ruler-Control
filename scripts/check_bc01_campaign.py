#!/usr/bin/env python3
"""Finite BC01 player/ledger/persistence counterexamples; no AI win-rate claim."""
from copy import deepcopy
from pathlib import Path
import json
import os
import sqlite3
import subprocess
import sys
import tempfile

from bc01_campaign_reference import (ATTACKS, CONTRACT, ROOT, ElectricGate,
    NightLedger, Player, RunStore, canonical, digest, integrate_manual_progress,
    level_for_xp, level_stats, level_threshold, logical_night, manual_duration,
    movement_speed, new_campaign, open_night, retry_night, settle_night,
    validate_snapshot)

checks = []


def check(name, condition):
    checks.append({'name': name, 'passed': bool(condition)})
    if not condition:
        raise AssertionError(name)


def rejects(name, action):
    try:
        action()
    except (ValueError, RuntimeError):
        check(name, True)
    else:
        check(name, False)


def empty_opening(state):
    """Explicit finite fixture; the joint test replaces it with actual modules."""
    level = level_for_xp(state['permanent']['total_xp'])
    attempt = {name: {} for name in CONTRACT['persistence']['partitions']['attempt']}
    attempt.update({'world_clock': 0., 'player': Player(level, level_stats(level)['max_hp']).export(),
                    'electric': ElectricGate().export(), 'manual_action': None,
                    'pending_reward_ledger': NightLedger(logical_night(state), state['attempt_id'] + 1).export(),
                    'rng_streams': {'director': 'fixed-stream-state', 'customer': 1789},
                    'store_stock': {'rice': {'units': 5, 'owner': 'employer'}}})
    return attempt


def reward_base(ledger, event_id):
    return {'night_id': ledger.night_id, 'attempt_id': ledger.attempt_id,
            'event_id': event_id, 'verified': True}


def run():
    check('184 explicit attack replacements, no duplicate IDs', len(ATTACKS) == 184)
    check('13 child attack overrides explicitly migrated', CONTRACT['attack_migration']['child_override_count'] == 13)
    for filename in ('monster_attacks_folklore_ma01.json', 'monster_attacks_scp_ma01.json'):
        records = json.loads((ROOT / 'content' / filename).read_text())['monsters']
        check(filename + ': all source numbers preserved without same-hit SAN', all(
            ATTACKS[a['id']]['hp_damage'] == a['damage']['san'] and
            ATTACKS[a['id']]['hp_damage_after_rule'] == a['aftermath']['post_rule']['damage_san'] and
            ATTACKS[a['id']]['san_damage_from_same_attack'] == 0
            for m in records for a in m['attacks']))
    for level in (1, 5, 10, 20):
        check(f'level {level}: exact XP boundary', level_for_xp(level_threshold(level)) == level)
        if level > 1:
            check(f'level {level}: below boundary', level_for_xp(level_threshold(level) - 1) == level - 1)
    check('growth cap and defense are explicit', level_for_xp(100000) == 20 and level_stats(20)['max_hp'] == 252 and level_stats(20)['defense'] == 38)
    p = Player()
    hit = p.attack('F01:BASIC', ['r1', 'p1', 'a1', 1], 0, collision=True, hostile=True)
    check('new HP damage does not also deduct SAN', hit['hp_loss'] == 10 and p.hp == 90 and p.san == 100)
    check('same sequence never damages twice', not p.attack('F01:BASIC', ['r1', 'p1', 'a1', 1], 3, collision=True, hostile=True)['applied'])
    check('other root respects global two-second grace', not p.attack('F01:BASIC', ['r2', 'p2', 'a2', 1], 1, collision=True, hostile=True)['applied'])
    check('blocked hit is not delivered after leaving geometry', not p.attack('F01:BASIC', ['r2', 'p2', 'a2', 1], 2, collision=False, hostile=True)['applied'])
    check('valid fresh contact after grace works', p.attack('F01:BASIC', ['r2', 'p2', 'a2', 1], 2, collision=True, hostile=True)['applied'])
    check('normal customer cannot deal a monster hit', not p.attack('F01:BASIC', ['customer', 'p', 'a', 1], 4, collision=True, hostile=False)['applied'])
    end = Player(20, 252)
    top_hit = end.attack('F01:BASIC', ['r', 'p', 'a', 1], 0, collision=True, hostile=True, gear_reduction=.2, facility_reduction=.08)
    check('level and gear/facility DR multiply once', abs(top_hit['hp_loss'] - 10 * 100 / 138 * .8 * .92) < 1e-9)
    end.fear(10)
    check('HP defense does not reduce fear SAN', end.san == 90)
    h = Player(hp=95)
    check('healing clamps at max HP', h.heal('food:1', 8) == 5 and h.hp == 100)
    h.hp = 50
    check('duplicate regen receipt is not replayed', h.heal('food:1', 8) == 0 and h.hp == 50)
    h.hp = 0
    check('regen never resurrects failed attempt', h.heal('food:2', 8) == 0 and not h.alive)
    check('Lv20, equipment and facility action floor', abs(manual_duration(10, 20, 'pick_up', .8, .9) - 6) < 1e-9)
    check('short hand action has visible floor', manual_duration(.3, 20, 'latch', .8, .9) == .25)
    for kind in CONTRACT['player']['invariant_action_types']:
        check('real-world timing unchanged: ' + kind, manual_duration(2.5, 20, kind, .8, .9) == 2.5)
    rejects('unmapped work cannot silently gain proficiency', lambda: manual_duration(3, 20, 'unknown_work'))
    work = integrate_manual_progress(10, 1, 'pick_up', [(2, .9), (10, 1)])
    check('power-loss recomputes ongoing hand work', abs(work['duration_s'] - (2 + 10 * (1 - 2 / 9))) < 1e-9)
    paused = integrate_manual_progress(10, 1, 'pick_up', [(0, .9)])
    check('pause does not advance work', paused['progress'] == 0)
    check('facility ordinary movement gain', abs(movement_speed(facility_haste=True) - 3.24) < 1e-9)
    check('item/facility haste takes stronger, does not multiply', abs(movement_speed(permanent_walk=3.15, item_walk_bonus=.15, facility_haste=True) - 3.402) < 1e-9)
    check('sprint still capped', movement_speed(sprint_speed=4.2, facility_haste=True) == 4.5)
    check('carry support uses carry source, not sprint', movement_speed(heavy_carry_speed=2, carry_support=True, facility_haste=True) == 2.2)
    e = ElectricGate()
    e.add_charge('m1', 7, 8)
    check('powered threshold commits actual charge', e.reserve_overload('over:1', 'm1', ['m2']) and e.charges['m1']['units'] == 2)
    e.change_power('outage:1', False, .1)
    check('blackout cancels queued overload with no refund', not e.queue and e.charges['m1']['units'] == 2 and not e.deliver(lambda _: True))
    check('off rejects new charge including positive feedback', not e.add_charge('m1', 5, 8))
    check('off rejects even enemy-to-enemy overload', not e.reserve_overload('over:2', 'm1', ['m2']))
    e.advance(9)
    e.change_power('restore:1', True, 9)
    check('charge expiry continues through outage', not e.charges and not e.deliver(lambda _: True))
    check('normal power receipt cannot replay epoch', not e.change_power('restore:1', False, 9))
    check('power snapshot restores exact queue/epoch', ElectricGate.restore(e.export()).export() == e.export())
    ledger = NightLedger('night:one', 1)
    order = {**reward_base(ledger, 'paid:1'), 'order_id': 'o1', 'paid': True,
             'payment_kind': 'ordinary_store_sale', 'items': [{'source_item_id': 'store:1'}]}
    check('real order rewards coin and XP once', ledger.apply('order', order) == {'applied': True, 'coin': 6, 'spirit': 0, 'xp': 8})
    check('new event ID cannot duplicate same sale', not ledger.apply('order', {**order, 'event_id': 'paid:fake'})['applied'])
    check('old attempt cannot award', not ledger.apply('order', {**order, 'attempt_id': 0, 'event_id': 'paid:2', 'order_id': 'o2'})['applied'])
    check('unpaid evacuation is not a sale', not ledger.apply('order', {**order, 'paid': False, 'event_id': 'paid:2', 'order_id': 'o2'})['applied'])
    chore = {**reward_base(ledger, 'breaker:1'), 'chore_id': 'j1', 'kind': 'breaker_reset',
             'completed': True, 'outage_id': 'out:1', 'monster_caused': True}
    check('real repair gets independent reward', ledger.apply('chore', chore)['coin'] == 4)
    check('same outage with new work ID cannot farm', not ledger.apply('chore', {**chore, 'event_id': 'breaker:2', 'chore_id': 'j2'})['applied'])
    check('player toggle cannot farm repair', not ledger.apply('chore', {**chore, 'event_id': 'breaker:3', 'chore_id': 'j3', 'outage_id': 'out:2', 'monster_caused': False})['applied'])
    root = {**reward_base(ledger, 'root:1'), 'raid_id': 'raid:1', 'actual_terminal': True,
            'source': 'root_lifecycle', 'terminal_kind': 'defeated', 'hp_after': 1, 'main_rule_completed': True}
    check('rule-only nonzero HP does not reward combat kill', not ledger.apply('root', root)['applied'])
    check('actual HP zero + main rule pays correct reward', ledger.apply('root', {**root, 'hp_after': 0}) == {'applied': True, 'coin': 12, 'spirit': 6, 'xp': 25})
    for i in range(1, 14):
        request = {**reward_base(ledger, f'survive:{i}'), 'source': 'FR10', 'unit_index': i,
                   'eligible_alive_raid_seconds': 15, 'completed_at': 100 + 15 * i}
        result = ledger.apply('survival', request)
        check(f'survival unit {i} bounded', result['applied'] == (i <= 12))
    late = NightLedger('late', 1)
    check('overtime cannot farm survival income', not late.apply('survival', {**reward_base(late, 's:1'), 'source': 'FR10', 'unit_index': 1, 'eligible_alive_raid_seconds': 15, 'completed_at': 721})['applied'])
    check('ledger serialization retains dedupe and totals', NightLedger.restore(ledger.export()).export() == ledger.export())
    campaign = new_campaign('counterexample')
    open_night(campaign, empty_opening(campaign))
    start = deepcopy(campaign['checkpoint']['snapshot'])
    campaign['week']['coin'] += 999
    campaign['permanent']['total_xp'] = 500
    campaign['attempt']['player']['hp'] = 1
    campaign['attempt']['rng_streams']['director'] = 'rerolled'
    campaign['attempt']['electric']['powered'] = False
    attempt = retry_night(campaign)
    check('failure rolls back all transient coin/XP/HP/power', campaign['week'] == start['week'] and campaign['permanent'] == start['permanent'] and campaign['attempt']['player'] == start['attempt']['player'] and campaign['attempt']['electric'] == start['attempt']['electric'])
    check('retry RNG fixed, new attempt ID only', campaign['attempt']['rng_streams'] == start['attempt']['rng_streams'] and attempt == 2 and campaign['attempt']['pending_reward_ledger']['attempt_id'] == 2)
    live = NightLedger(logical_night(campaign), campaign['attempt_id'])
    kwargs = dict(actual_time=720, player_alive=True, san_safe=True, all_roots_terminal=True, customers_outside=True)
    rejects('deadline alone cannot settle unresolved root', lambda: settle_night(campaign, live, **{**kwargs, 'all_roots_terminal': False}))
    rejects('customers must actually finish evacuation', lambda: settle_night(campaign, live, **{**kwargs, 'customers_outside': False}))
    rejects('HP zero cannot be revived by settling wage', lambda: settle_night(campaign, live, **{**kwargs, 'player_alive': False}))
    receipt = settle_night(campaign, live, **kwargs)
    check('no chore quota/manager/keys required for safe completion', receipt['applied'] and receipt['receipt']['coin'] == 80 and receipt['receipt']['xp'] == 20)
    saved = deepcopy(campaign)
    check('repeated night settle returns original no new payout', not settle_night(campaign, live, **kwargs)['applied'] and campaign == saved)
    rejects('settled night cannot fail-retry', lambda: retry_night(campaign))
    campaign['night_index'] = 7
    campaign['phase'] = 'pre_shift'
    campaign['permanent']['total_xp'] = 500
    campaign['permanent']['equipment'] = ['Q09']
    open_night(campaign, empty_opening(campaign))
    seven = NightLedger(logical_night(campaign), campaign['attempt_id'])
    last = settle_night(campaign, seven, **kwargs)
    check('night7 XP and ticket survive atomic week close', campaign['permanent']['total_xp'] == 520 and campaign['permanent']['equipment'] == ['Q09'] and campaign['permanent']['tickets'] == 3)
    check('week reset grants exactly fresh120/onefreeT02', campaign['week']['coin'] == 120 and campaign['week']['spirit'] == 0 and len(campaign['week']['defense_instances']) == 1 and campaign['week_id'] == 2 and campaign['night_index'] == 1)
    check('night7 earned coin recorded before reset', campaign['permanent']['week_scores'][0]['coin_at_close'] == 280 and last['receipt']['night7_income_recorded_in_old_week'])
    previous = deepcopy(campaign)
    check('duplicate night7 does not clear new week again', not settle_night(campaign, seven, **kwargs)['applied'] and campaign == previous)
    # Real files, reopen, rollback, lost acknowledgement, crash before COMMIT.
    with tempfile.TemporaryDirectory(prefix='bc01-persistence-') as tmp:
        path = Path(tmp) / 'run.sqlite'
        original = new_campaign('disk')
        disk = RunStore(path)
        check('first actual durable snapshot', disk.save(original, command_id='create', expected_revision=0)['revision'] == 1)
        next_state = deepcopy(original)
        next_state['permanent']['total_xp'] = 100
        for fault in ('after_journal', 'after_snapshot'):
            rejects(f'{fault}: transaction interruption', lambda f=fault: disk.save(next_state, command_id=f, expected_revision=1, fault=f))
            check(f'{fault}: no partial state survives', disk.load('disk') == {'revision': 1, 'state': original})
        disk.close()
        code = "import sqlite3,os,sys; c=sqlite3.connect(sys.argv[1],isolation_level=None); c.execute('BEGIN IMMEDIATE'); c.execute(\"UPDATE run SET state='BROKEN',hash='BROKEN',revision=999 WHERE id='disk'\"); os._exit(37)"
        crashed = subprocess.run([sys.executable, '-c', code, str(path)], capture_output=True)
        disk = RunStore(path)
        check('process dies mid-transaction: old snapshot intact after reopen', crashed.returncode == 37 and disk.load('disk') == {'revision': 1, 'state': original})
        result = disk.save(next_state, command_id='growth', expected_revision=1)
        disk.close()  # lose acknowledgement and reconnect
        disk = RunStore(path)
        check('lost ack retry is idempotent', disk.save(next_state, command_id='growth', expected_revision=1) == {'applied': False, 'duplicate': True, 'revision': 2})
        check('reopen preserves exact committed snapshot', disk.load('disk') == {'revision': 2, 'state': next_state})
        rejects('stale writer cannot overwrite live run', lambda: disk.save(original, command_id='old-writer', expected_revision=1))
        rejects('same command with altered payload rejected', lambda: disk.save(original, command_id='growth', expected_revision=2))
        corrupt = deepcopy(next_state)
        corrupt['content_version'] = 'SA02'
        rejects('old mode cannot silently enter BC01 save', lambda: disk.save(corrupt, command_id='legacy', expected_revision=2))
        disk.db.execute("UPDATE run SET hash='bad' WHERE id='disk'")
        rejects('corrupt payload digest rejected', lambda: disk.load('disk'))
        disk.close()
    full = new_campaign('incomplete')
    open_night(full, empty_opening(full))
    del full['attempt']['facilities']
    rejects('incomplete live world save rejected', lambda: validate_snapshot(full))
    report = {'version': 'BC01', 'passed': len(checks), 'failed': 0, 'checks': checks,
              'attack_replacements': 184, 'child_override_replacements': 13,
              'levels': [level_stats(level) | {'total_xp_threshold': level_threshold(level)} for level in (1, 5, 10, 20)],
              'actual_disk_interruption_recovery': True,
              'scope': 'finite HP/power/economy/lifecycle plus real local SQLite; no production cloud storage or full AI',
              'inputs_sha256': {str(p.relative_to(ROOT)): __import__('hashlib').sha256(p.read_bytes()).hexdigest()
                                for p in [ROOT / 'content/campaign_bc01.json', Path(__file__), ROOT / 'scripts/bc01_campaign_reference.py']}}
    (ROOT / 'docs/bc01_campaign_report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n')
    print(f'BC01 campaign: {len(checks)} passed, 0 failed')
    return report


if __name__ == '__main__':
    run()
