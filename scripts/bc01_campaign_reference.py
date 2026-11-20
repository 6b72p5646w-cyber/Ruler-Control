#!/usr/bin/env python3
"""BC01 design reference: HP, growth, power gate, single reward ledger, SQLite.

This is deliberately separate from the V0.10 client. Geometry/hit/normal-sale
facts must come from the corresponding adapters, not an arbitrary UI button.
The finite combat resolver conditions on a legal, exposed post-rule target in
the authored firing lane; it measures damage/time, never player win probability.
"""
from __future__ import annotations

from copy import deepcopy
from dataclasses import asdict, dataclass, field
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import json
import math
import sqlite3

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = json.loads((ROOT / 'content/campaign_bc01.json').read_text())
ATTACKS = {a['attack_id']: a for a in CONTRACT['attack_migration']['entries']}


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def digest(value):
    return sha256(canonical(value).encode()).hexdigest()


def level_threshold(level):
    if not isinstance(level, int) or not 1 <= level <= 20:
        raise ValueError('level out of range')
    return 100 * (level - 1) + 20 * (level - 1) * (level - 2)


def level_for_xp(total_xp):
    if not isinstance(total_xp, int) or isinstance(total_xp, bool) or total_xp < 0:
        raise ValueError('XP must be a nonnegative integer')
    return max(level for level in range(1, 21) if total_xp >= level_threshold(level))


def level_stats(level):
    level_threshold(level)
    return {'level': level, 'max_hp': 100 + 8 * (level - 1),
            'defense': 2 * (level - 1),
            'manual_duration_factor': max(.75, 1 - .015 * (level - 1))}


def manual_duration(base_seconds, level, kind, gear_factor=1, facility_factor=1):
    if not math.isfinite(base_seconds) or base_seconds < 0:
        raise ValueError('invalid action duration')
    if kind in CONTRACT['player']['invariant_action_types']:
        return float(base_seconds)
    if kind not in CONTRACT['player']['manual_action_types']:
        raise ValueError('unregistered action cannot receive proficiency')
    if not .8 <= gear_factor <= 1 or not .9 <= facility_factor <= 1:
        raise ValueError('modifier outside registered group')
    if base_seconds == 0:
        return 0.
    factor = max(.6, level_stats(level)['manual_duration_factor'] * gear_factor * facility_factor)
    return max(.25, base_seconds * factor)


def integrate_manual_progress(base_seconds, level, kind, intervals, gear_factor=1):
    """Each interval is (world_duration, currently_valid_facility_factor).

    Caller splits at power, buff expiry and pause boundaries. Returns the exact
    completion time, or unfinished progress; a start snapshot cannot extend a buff.
    """
    elapsed = progress = 0.
    for dt, facility_factor in intervals:
        if not math.isfinite(dt) or dt < 0:
            raise ValueError('invalid interval')
        duration = manual_duration(base_seconds, level, kind, gear_factor, facility_factor)
        if duration == 0:
            return {'completed': True, 'duration_s': 0., 'progress': 1.}
        need = (1 - progress) * duration
        if dt >= need - 1e-10:
            return {'completed': True, 'duration_s': elapsed + need, 'progress': 1.}
        progress += dt / duration
        elapsed += dt
    return {'completed': False, 'duration_s': elapsed, 'progress': progress}


def movement_speed(*, permanent_walk=3., item_walk_bonus=0., facility_haste=False,
                   sprint_speed=None, heavy_carry_speed=None, carry_support=False):
    if heavy_carry_speed is not None:
        if heavy_carry_speed < 0:
            raise ValueError('invalid carry speed')
        return heavy_carry_speed * max(1.1 if carry_support else 1., 1.08 if facility_haste else 1.)
    if sprint_speed is not None:
        if sprint_speed not in (4.1, 4.2, 4.5):
            raise ValueError('unregistered sprint profile')
        return min(4.5, sprint_speed * (1.08 if facility_haste else 1.))
    if not 0 <= permanent_walk <= 3.15 or not 0 <= item_walk_bonus <= .15:
        raise ValueError('invalid ordinary movement modifier')
    item_speed = min(3.3, permanent_walk + item_walk_bonus)
    return min(3.6, max(item_speed, permanent_walk * (1.08 if facility_haste else 1.)))


@dataclass
class Player:
    level: int = 1
    hp: float = 100.
    san: float = 100.
    stamina: float = 100.
    energy: float = 100.
    satiety: float = 100.
    grace_until: float = 0.
    hit_sequences: list = field(default_factory=list)
    heal_receipts: list = field(default_factory=list)
    damage_log: list = field(default_factory=list)

    @property
    def alive(self):
        return self.hp > 0

    @property
    def max_hp(self):
        return level_stats(self.level)['max_hp']

    def attack(self, definition_id, sequence, now, *, collision, hostile,
               gear_reduction=0., facility_reduction=0., curse_reduction=0., post_rule=False):
        if definition_id not in ATTACKS:
            raise ValueError('unknown attack')
        if not isinstance(sequence, (tuple, list)) or len(sequence) != 4:
            raise ValueError('root/pool/actor/persistent-sequence required')
        if not math.isfinite(now) or now < 0:
            raise ValueError('invalid time')
        key = canonical(sequence)
        # A protection-blocked collision does not become a deferred hit.
        if not self.alive or not collision or not hostile or key in self.hit_sequences or now < self.grace_until:
            return {'applied': False, 'hp_loss': 0., 'collision_recorded': bool(collision)}
        if not 0 <= curse_reduction <= 1 or min(gear_reduction, facility_reduction) < 0:
            raise ValueError('invalid damage modifier')
        raw = ATTACKS[definition_id]['hp_damage_after_rule' if post_rule else 'hp_damage']
        raw *= 1 - curse_reduction
        stats = level_stats(self.level)
        factor = max(.35, 100 / (100 + stats['defense']) *
                     (1 - min(.2, gear_reduction)) * (1 - min(.08, facility_reduction)))
        loss = min(self.hp, raw * factor)
        if loss <= 0:
            return {'applied': False, 'hp_loss': 0., 'collision_recorded': True}
        self.hp -= loss
        self.grace_until = now + 2
        self.hit_sequences.append(key)
        row = {'at': now, 'sequence': list(sequence), 'definition_id': definition_id,
               'hp_loss': loss, 'hp': self.hp, 'san_loss': 0., 'defense_factor': factor}
        self.damage_log.append(row)
        return {'applied': True, **row}

    def heal(self, receipt_id, amount):
        if not isinstance(receipt_id, str) or not receipt_id or not math.isfinite(amount) or amount < 0:
            raise ValueError('invalid healing request')
        if receipt_id in self.heal_receipts or not self.alive:
            return 0.
        self.heal_receipts.append(receipt_id)
        restored = min(amount, self.max_hp - self.hp)
        self.hp += restored
        return restored

    def fear(self, amount):
        """Only accepts an already-qualified original fear consumer amount."""
        if amount < 0 or not math.isfinite(amount):
            raise ValueError('invalid SAN loss')
        actual = min(self.san, amount)
        self.san -= actual
        return actual

    def export(self):
        return asdict(self)


class ElectricGate:
    """Wraps all TD05 electric-network starts and each queued delivery.

    Native standalone tower damage remains legal while off, but cannot feed the
    network. Existing charges expire normally; this wrapper never resets expiry.
    """
    def __init__(self):
        self.powered = True
        self.power_epoch = 0
        self.now = 0.
        self.charges = {}
        self.queue = []
        self.processed = []
        self.power_receipts = []

    def change_power(self, event_id, powered, now):
        if now < self.now:
            raise ValueError('time reversal')
        if event_id in self.power_receipts:
            return False
        self.advance(now)
        self.power_receipts.append(event_id)
        if self.powered != bool(powered):
            self.power_epoch += 1
            self.powered = bool(powered)
            if not self.powered:
                self.queue.clear()
        return True

    def advance(self, now):
        if not math.isfinite(now) or now < self.now:
            raise ValueError('invalid electric clock')
        self.now = now
        self.charges = {k: v for k, v in self.charges.items() if v['expires_at'] > now}

    def add_charge(self, pool_id, units, expires_at):
        if not self.powered:
            return False
        if not isinstance(units, int) or isinstance(units, bool) or units <= 0 or expires_at <= self.now:
            raise ValueError('invalid charge source')
        old = self.charges.get(pool_id, {'units': 0, 'expires_at': expires_at})
        self.charges[pool_id] = {'units': old['units'] + units, 'expires_at': max(old['expires_at'], expires_at)}
        return True

    def reserve_overload(self, receipt_id, pool_id, recipients, threshold=5):
        if not self.powered or receipt_id in self.processed or any(x['id'] == receipt_id for x in self.queue):
            return False
        if threshold not in (4, 5):
            raise ValueError('unregistered overload threshold')
        pool = self.charges.get(pool_id)
        if not pool or pool['units'] < threshold or not recipients:
            return False
        pool['units'] -= threshold
        self.queue.append({'id': receipt_id, 'source': pool_id, 'recipients': list(recipients),
                           'power_epoch': self.power_epoch})
        self.processed.append(receipt_id)  # committed charge, never refunded on loss
        return True

    def deliver(self, targets_legal):
        delivered = []
        while self.queue:
            job = self.queue.pop(0)
            if not self.powered or job['power_epoch'] != self.power_epoch:
                continue
            delivered += [{'overload_id': job['id'], 'target': target, 'raw_electric_damage': 6}
                          for target in job['recipients'] if targets_legal(target)]
        return delivered

    def export(self):
        return deepcopy(vars(self))

    @classmethod
    def restore(cls, snapshot):
        obj = cls()
        if set(snapshot) != set(vars(obj)):
            raise ValueError('incomplete electric snapshot')
        obj.__dict__.update(deepcopy(snapshot))
        return obj


class NightLedger:
    """One provisional ledger. No caller-chosen amount enters the wallet."""
    def __init__(self, night_id, attempt_id):
        self.night_id = night_id
        self.attempt_id = attempt_id
        self.receipts = {}
        self.coin = self.spirit = self.xp = 0
        self.counts = {'order': 0, 'chore': 0, 'root': 0, 'survival': 0}

    def apply(self, kind, receipt):
        if kind not in self.counts:
            raise ValueError('unregistered reward consumer')
        if (receipt.get('night_id') != self.night_id or receipt.get('attempt_id') != self.attempt_id
                or not receipt.get('event_id') or receipt.get('verified') is not True):
            return {'applied': False, 'reason': 'unverified_or_stale_receipt'}
        source_key = (kind, receipt.get('order_id') if kind == 'order' else
                      receipt.get('chore_id') if kind == 'chore' else
                      receipt.get('raid_id') if kind == 'root' else receipt.get('unit_index'))
        if source_key[1] is None:
            return {'applied': False, 'reason': 'missing_actual_source'}
        key = canonical(source_key)
        if key in self.receipts or any(r['event_id'] == receipt['event_id'] for r in self.receipts.values()):
            return {'applied': False, 'reason': 'already_awarded'}
        coin = spirit = xp = 0
        if kind == 'order':
            if (self.counts[kind] >= 12 or receipt.get('paid') is not True or
                    receipt.get('payment_kind') != 'ordinary_store_sale' or not receipt.get('items')):
                return {'applied': False, 'reason': 'not_paid_sale_or_cap'}
            coin, xp = 6, 8
        elif kind == 'chore':
            job = receipt.get('reward_kind', receipt.get('kind'))
            if job not in CONTRACT['economy']['chore_rewards'] or receipt.get('completed') is not True:
                return {'applied': False, 'reason': 'incomplete_or_unknown_chore'}
            if job == 'breaker_reset' and (not receipt.get('outage_id') or receipt.get('monster_caused') is not True):
                return {'applied': False, 'reason': 'actual_monster_outage_required'}
            if job == 'breaker_reset' and any(r.get('outage_id') == receipt['outage_id'] for r in self.receipts.values()):
                return {'applied': False, 'reason': 'outage_already_rewarded'}
            coin = CONTRACT['economy']['chore_rewards'][job]['coin']
            xp = CONTRACT['economy']['chore_rewards'][job]['xp']
        elif kind == 'root':
            if (receipt.get('actual_terminal') is not True or receipt.get('source') != 'root_lifecycle'
                    or receipt.get('terminal_kind') not in ('defeated', 'left')):
                return {'applied': False, 'reason': 'actual_terminal_required'}
            if receipt['terminal_kind'] == 'defeated' and receipt.get('hp_after') != 0:
                return {'applied': False, 'reason': 'nonzero_hp'}
            coin, spirit, xp = 12, 4, 20
            if receipt.get('main_rule_completed') is True:
                spirit += 2
                xp += 5
        elif kind == 'survival':
            if (self.counts[kind] >= 12 or receipt.get('source') != 'FR10' or
                    receipt.get('eligible_alive_raid_seconds') != 15 or
                    receipt.get('completed_at', 721) > 720 or not 1 <= receipt['unit_index'] <= 12):
                return {'applied': False, 'reason': 'no_finite_alive_credit'}
            coin = xp = 1
        self.receipts[key] = deepcopy(receipt)
        self.coin += coin
        self.spirit += spirit
        self.xp += xp
        self.counts[kind] += 1
        return {'applied': True, 'coin': coin, 'spirit': spirit, 'xp': xp}

    def export(self):
        return deepcopy(vars(self))

    @classmethod
    def restore(cls, snapshot):
        obj = cls(snapshot['night_id'], snapshot['attempt_id'])
        if set(snapshot) != set(vars(obj)):
            raise ValueError('incomplete reward snapshot')
        obj.__dict__.update(deepcopy(snapshot))
        return obj


def new_campaign(campaign_id='bc01-reference'):
    return {'schema_version': 1, 'content_version': 'BC01', 'campaign_id': campaign_id,
            'week_id': 1, 'night_index': 1, 'attempt_id': 0, 'phase': 'pre_shift',
            'permanent': {'total_xp': 0, 'equipment': [], 'unused_personal_items': [],
                          'tickets': 1, 'pity': {}, 'knowledge': [], 'settled_nights': [],
                          'closed_weeks': [], 'week_scores': []},
            'week': {'coin': 120, 'spirit': 0,
                     'defense_instances': [{'id': 'w1:free:T02', 'node': 'T02', 'free': True}],
                     'trap_stock': [], 'preparation_receipts': []},
            'attempt': {}, 'checkpoint': None, 'settlement_receipts': {}}


def logical_night(state):
    return canonical([state['campaign_id'], state['week_id'], state['night_index']])


def open_night(state, attempt_snapshot):
    if state['phase'] != 'pre_shift' or logical_night(state) in state['permanent']['settled_nights']:
        raise ValueError('night cannot open')
    required = set(CONTRACT['persistence']['partitions']['attempt'])
    if not required.issubset(attempt_snapshot):
        raise ValueError('incomplete actual world snapshot: ' + ','.join(sorted(required - set(attempt_snapshot))))
    level = level_for_xp(state['permanent']['total_xp'])
    if attempt_snapshot['player']['level'] != level or attempt_snapshot['player']['hp'] != level_stats(level)['max_hp']:
        raise ValueError('preparation must provide correct free full HP and level')
    state['attempt_id'] += 1
    state['attempt'] = deepcopy(attempt_snapshot)
    state['phase'] = 'open'
    checkpoint = {k: deepcopy(state[k]) for k in ('permanent', 'week', 'attempt')}
    state['checkpoint'] = {'night_id': logical_night(state), 'snapshot': checkpoint, 'digest': digest(checkpoint)}


def retry_night(state):
    cp = state['checkpoint']
    if (state['phase'] not in ('open', 'failed') or not cp or cp['night_id'] != logical_night(state)
            or cp['digest'] != digest(cp['snapshot']) or logical_night(state) in state['permanent']['settled_nights']):
        raise ValueError('not a valid retry')
    for key in ('permanent', 'week', 'attempt'):
        state[key] = deepcopy(cp['snapshot'][key])
    state['attempt_id'] += 1
    state['phase'] = 'open'
    def rebind(value):
        if isinstance(value, dict):
            for key, child in value.items():
                if key == 'attempt_id':
                    value[key] = state['attempt_id']
                else:
                    rebind(child)
        elif isinstance(value, list):
            for child in value:
                rebind(child)
    rebind(state['attempt'])
    state['attempt']['pending_reward_ledger'] = NightLedger(logical_night(state), state['attempt_id']).export()
    # RNG and scheduled root/object IDs stay fixed. The opening checkpoint has
    # no night rewards; only command envelopes receive the new attempt identity.
    return state['attempt_id']


def settle_night(state, ledger, *, actual_time, player_alive, san_safe,
                 all_roots_terminal, customers_outside, no_active_panic=True):
    key = ledger.night_id
    if key in state['settlement_receipts']:
        return {'applied': False, 'receipt': deepcopy(state['settlement_receipts'][key])}
    if (key != logical_night(state) or state['phase'] != 'open' or actual_time < 720 or not player_alive or not san_safe
            or not all_roots_terminal or not customers_outside or not no_active_panic
            or ledger.night_id != key or ledger.attempt_id != state['attempt_id']):
        raise ValueError('actual automatic settlement gate is not satisfied')
    bonus = min(40, 2 * min(12, ledger.counts['order']) + 2 * min(8, ledger.counts['chore']))
    coin = 80 + bonus + ledger.coin
    state['week']['coin'] += coin
    state['week']['spirit'] += ledger.spirit
    state['permanent']['total_xp'] += ledger.xp + 20
    state['permanent']['tickets'] += 1
    state['permanent']['settled_nights'].append(key)
    result = {'night_id': key, 'coin': coin, 'spirit': ledger.spirit, 'xp': ledger.xp + 20,
              'wage': 80, 'performance_bonus': bonus, 'counts': deepcopy(ledger.counts),
              'next_level': level_for_xp(state['permanent']['total_xp']), 'ticket': 1,
              'night7_income_recorded_in_old_week': state['night_index'] == 7}
    state['settlement_receipts'][key] = result
    state['phase'] = 'settled'
    state['attempt'] = {}
    state['checkpoint'] = None
    if state['night_index'] == 7:
        old_week = state['week_id']
        state['permanent']['week_scores'].append({'week_id': old_week, 'coin_at_close': state['week']['coin'],
                                                  'spirit_at_close': state['week']['spirit'],
                                                  'total_xp': state['permanent']['total_xp']})
        state['permanent']['closed_weeks'].append(old_week)
        state['week_id'] += 1
        state['night_index'] = 1
        state['week'] = {'coin': 120, 'spirit': 0,
                         'defense_instances': [{'id': f"w{state['week_id']}:free:T02", 'node': 'T02', 'free': True}],
                         'trap_stock': [], 'preparation_receipts': []}
    else:
        state['night_index'] += 1
    return {'applied': True, 'receipt': deepcopy(result)}


def validate_snapshot(state):
    required = set(CONTRACT['persistence']['required_state_keys'])
    if not required.issubset(state) or state['schema_version'] != 1 or state['content_version'] != 'BC01':
        raise ValueError('incompatible or incomplete save')
    if state['phase'] in ('open', 'failed'):
        missing = set(CONTRACT['persistence']['partitions']['attempt']) - set(state['attempt'])
        if missing:
            raise ValueError('missing attempt partitions: ' + ','.join(sorted(missing)))
        cp = state['checkpoint']
        if not cp or cp['night_id'] != logical_night(state) or cp['digest'] != digest(cp['snapshot']):
            raise ValueError('invalid checkpoint digest/identity')
    canonical(state)  # rejects NaN, non-JSON objects and unsupported snapshots
    return True


class RunStore:
    """Real local SQLite atomic snapshot + command journal, with CAS updates.

    This tests interruption recovery, not a production remote anti-tamper system.
    """
    def __init__(self, path):
        self.db = sqlite3.connect(str(path), isolation_level=None)
        self.db.execute('PRAGMA journal_mode=WAL')
        self.db.execute('PRAGMA synchronous=FULL')
        self.db.execute('CREATE TABLE IF NOT EXISTS run (id TEXT PRIMARY KEY, revision INTEGER NOT NULL, state TEXT NOT NULL, hash TEXT NOT NULL)')
        self.db.execute('CREATE TABLE IF NOT EXISTS commands (run_id TEXT NOT NULL, command_id TEXT NOT NULL, revision INTEGER NOT NULL, payload_hash TEXT NOT NULL, PRIMARY KEY (run_id,command_id))')

    def close(self):
        self.db.close()

    def save(self, state, *, command_id, expected_revision, fault=None):
        validate_snapshot(state)
        if not command_id or not isinstance(expected_revision, int) or expected_revision < 0:
            raise ValueError('invalid transaction identity')
        payload = canonical(state)
        payload_hash = digest(state)
        run_id = state['campaign_id']
        self.db.execute('BEGIN IMMEDIATE')
        try:
            previous = self.db.execute('SELECT revision,payload_hash FROM commands WHERE run_id=? AND command_id=?', (run_id, command_id)).fetchone()
            if previous:
                if previous[1] != payload_hash:
                    raise ValueError('reused command has different content')
                self.db.execute('ROLLBACK')
                return {'applied': False, 'duplicate': True, 'revision': previous[0]}
            row = self.db.execute('SELECT revision FROM run WHERE id=?', (run_id,)).fetchone()
            revision = row[0] if row else 0
            if revision != expected_revision:
                raise ValueError('stale revision')
            new_revision = revision + 1
            self.db.execute('INSERT INTO commands VALUES (?,?,?,?)', (run_id, command_id, new_revision, payload_hash))
            if fault == 'after_journal':
                raise RuntimeError('simulated interruption before snapshot')
            self.db.execute('INSERT INTO run VALUES (?,?,?,?) ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,state=excluded.state,hash=excluded.hash', (run_id, new_revision, payload, payload_hash))
            if fault == 'after_snapshot':
                raise RuntimeError('simulated interruption before commit')
            self.db.execute('COMMIT')
            return {'applied': True, 'revision': new_revision}
        except BaseException:
            if self.db.in_transaction:
                self.db.execute('ROLLBACK')
            raise

    def load(self, run_id):
        row = self.db.execute('SELECT revision,state,hash FROM run WHERE id=?', (run_id,)).fetchone()
        if not row:
            raise ValueError('no saved run')
        state = json.loads(row[1])
        if digest(state) != row[2]:
            raise ValueError('corrupt snapshot')
        validate_snapshot(state)
        return {'revision': row[0], 'state': state}


def make_combat_resolver(navigation, tower_node='T02', max_seconds=240):
    """Finite post-rule damage scenario on the registered, unobstructed loop.

    The player is NOT simulated as invulnerable. No enemy-attack/dodge claim is
    made; this feeds a conditional successful-route schedule to design analysis.
    Missing legal route / targeting evidence produces no terminal receipt.
    """
    from md01_reference import LifeState, clean
    from td05_reference import nodes
    roster = {}
    for filename in ('monster_folklore_md01.json', 'monster_scp_a_md01.json', 'monster_scp_b_md01.json'):
        roster.update({m['id']: m for m in json.loads((ROOT / 'content' / filename).read_text())['monsters']})
    tree = json.loads((ROOT / 'content/tower_defense_td05.json').read_text())
    node = next(n for n in nodes(tree) if n['id'] == tower_node)
    if not tower_node.startswith('T02'):
        raise ValueError('bounded resolver only implements the registered T02 family')

    def resolve(raid_state, director_context):
        monster_id = raid_state['monster_id']
        if monster_id not in roster or not raid_state.get('actual_action_receipts'):
            return None
        if not raid_state.get('requires_combat_after_rule'):
            return None  # rule-leave remains owned by the real mechanism script
        # Map API supplies a proven finite firing lane. Validate it again at use.
        if not hasattr(navigation, 'combat_reference'):
            return None
        geometry = navigation.combat_reference(monster_id)
        if not geometry or not geometry.get('legal'):
            return None
        # The same root must have physically arrived; a valid empty firing lane
        # cannot teleport a monster out of the warehouse into this calculation.
        actual_position = raid_state.get('plan', {}).get('actor_positions', {}).get('monster')
        expected_position = navigation.position(geometry['target_anchor'])
        if (actual_position is None or math.dist(actual_position, expected_position) > 1e-6
                or not navigation.los_clear(geometry['emitter'], actual_position)
                or math.dist(geometry['tower_anchor_position'], actual_position) > node['parameters']['range_tiles']):
            return None
        if not any(r.get('actor') == 'monster' and r.get('kind') == 'travel'
                   and math.dist(r.get('position', [-100, -100]), actual_position) < 1e-6
                   for r in raid_state['actual_action_receipts']):
            return None
        record = roster[monster_id]
        if record['resolution']['type'] == 'rule_leave':
            return None
        life = LifeState(record, root=raid_state['raid_id'])
        if not life.complete_rule({'verified': True, 'root': raid_state['raid_id'],
                                   'id': f"{raid_state['raid_id']}:verified-main-rule"}):
            return None
        interval = Fraction(str(node['parameters'].get('interval_s', 2.4)))
        if 'shot_offsets_s' in node['parameters']:
            # Unsupported branch must not borrow another tower's timing.
            return None
        poison = next(e for e in node['effects'] if e['status'] == 'poison')
        next_shot = Fraction(0)
        next_tick = Fraction(1)
        maturities = []
        log = []
        # Only actual impacts create poison. Discrete one-second ticks preserve
        # original maturity/terminal semantics and finite overkill accounting.
        while life.hp > 0:
            t = min(next_shot, next_tick, min((x[0] for x in maturities), default=Fraction(10**9)))
            if t > max_seconds:
                return None
            life.advance(t - life.now)
            for due, amount in list(maturities):
                if due == t:
                    life.add_poison(amount)
                    maturities.remove((due, amount))
                    log.append({'offset_s': float(t), 'kind': 'paid_poison_maturity', 'q': float(life.poison)})
            if next_shot == t:
                before = life.hp
                loss = life.apply_damage(node['parameters']['damage'], node['parameters']['channel'],
                                         receipt=f"{raid_state['raid_id']}:shot:{next_shot}")
                if life.hp > 0 and loss > 0:
                    life.add_poison(poison['amount'])
                    if poison.get('maturation'):
                        m = poison['maturation']
                        maturities.append((t + Fraction(str(m['delay_s'])), Fraction(str(m['additional_amount_q']))))
                log.append({'offset_s': float(t), 'kind': 'legal_T02_impact', 'hp_before': float(before),
                            'hp_after': float(life.hp), 'actual_damage': float(loss), 'q': float(life.poison)})
                next_shot += interval
            if next_tick == t and life.hp > 0:
                before = life.hp
                loss = life.poison_tick()
                log.append({'offset_s': float(t), 'kind': 'poison_tick', 'hp_before': float(before),
                            'hp_after': float(life.hp), 'actual_damage': float(loss), 'q': float(life.poison)})
                next_tick += 1
        if not life.root_finished or life.state != 'defeated':
            return None
        return {'duration_s': float(life.now), 'combat_log': log,
                'geometry_evidence': geometry,
                'scope': 'conditional_post_rule_legal_hits_not_AI_winrate',
                'terminal_receipt': {'event_id': f"{raid_state['raid_id']}:attempt:{raid_state['attempt_id']}:hp-zero", 'night_id': raid_state['night_id'],
                                     'attempt_id': raid_state['attempt_id'], 'raid_id': raid_state['raid_id'],
                                     'monster_id': monster_id, 'terminal_kind': 'defeated',
                                     'source': 'root_lifecycle', 'verified': True, 'hp_after': 0,
                                     'actual_terminal': True, 'main_rule_completed': True}}
    return resolve
