#!/usr/bin/env python3
"""Deterministic TD05 design models. These are not the V0.10 game runtime.

Models deliberately take legal hits, contact, LOS and occupants as inputs. They
do not pretend to simulate path finding, enemy AI, player skill or a phone UI.
"""
from fractions import Fraction as F
from collections import defaultdict, deque
import math


def q(value):
    return value if isinstance(value, F) else F(str(value))


def clean(value):
    if isinstance(value, F):
        return int(value) if value.denominator == 1 else round(float(value), 6)
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


def nodes(tree):
    for family in tree['families']:
        yield family['l1']
        for branch in family['l2']:
            yield branch
            yield from branch['l3']


def segment_spans(a, b, ta=0, tb=1):
    """Positive-length intersections; corner touches do not invent cells."""
    a, b, ta, tb = tuple(map(q, a)), tuple(map(q, b)), q(ta), q(tb)
    cuts = {F(0), F(1)}
    for left, right in zip(a, b):
        if left == right:
            continue
        for boundary in range(math.floor(min(left, right)) + 1,
                              math.ceil(max(left, right))):
            t = (boundary - left) / (right - left)
            if 0 < t < 1:
                cuts.add(t)
    result = []
    cuts = sorted(cuts)
    for left, right in zip(cuts, cuts[1:]):
        mid = (left + right) / 2
        point = tuple(x + (y - x) * mid for x, y in zip(a, b))
        result.append((tuple(math.floor(x) for x in point),
                       ta + (tb - ta) * left, ta + (tb - ta) * right))
    return result


def merge_sample_spans(samples):
    result = []
    for (ta, a), (tb, b) in zip(samples, samples[1:]):
        for cell, start, end in segment_spans(a, b, ta, tb):
            if result and result[-1][0] == cell and result[-1][2] == start:
                result[-1] = (cell, result[-1][1], end)
            else:
                result.append((cell, start, end))
    return result


def normal_toll(pool, spans, ledger, fields, period=2):
    hits = []
    for cell, start, end in spans:
        if cell not in fields:
            continue
        key = pool, cell
        due = max(q(start), ledger.get(key, q(start)))
        while due < end:
            hits.append((cell, due, q(fields[cell])))
            ledger[key] = due + q(period)
            due = ledger[key]
    return hits


def phase_toll(pool, phase_id, a, b, arrival, ledger, receipts, fields, period=2, committed=True):
    """One atomic audit of the active field snapshot, independent of old CDs."""
    if not committed or tuple(map(q, a)) == tuple(map(q, b)):
        return []
    receipt = pool, phase_id
    if receipt in receipts:
        return []
    receipts.add(receipt)
    cells = dict.fromkeys(cell for cell, _, _ in segment_spans(a, b))
    for point in (a, b):
        cells[tuple(math.floor(q(x)) for x in point)] = None
    hits = [(cell, q(arrival), q(fields[cell])) for cell in cells if cell in fields]
    for cell, _, _ in hits:
        ledger[pool, cell] = q(arrival) + q(period)
    return hits


def actual_damage(raw, channel, armor=0, ward=0, penetration_pp=0, vulnerability=0):
    defense = q(armor if channel == 'physical' else ward)
    if channel == 'physical':
        defense -= q(penetration_pp) / 100
    defense = max(F(0), min(F(3, 4), defense))
    return q(raw) * (1 - defense) * (1 + min(F(2, 5), q(vulnerability)))


def repeat_events(cycle, offsets, horizon, shift=0):
    cycle, horizon, shift = q(cycle), q(horizon), q(shift)
    result = []
    k = 0
    while k * cycle + shift < horizon:
        for offset in offsets:
            time = k * cycle + q(offset) + shift
            if 0 <= time < horizon:
                result.append(time)
        k += 1
    return sorted(result)


def hit_schedule(node, horizon):
    p = node['parameters']
    if 'damage_schedule_offsets_s' in p:
        return repeat_events(p['cycle_s'], p['damage_schedule_offsets_s'], horizon)
    if 'wave_offsets_s' in p:
        return repeat_events(p['cycle_s'], p['wave_offsets_s'], horizon)
    if 'shot_offsets_s' in p:
        return repeat_events(p['cycle_s'], p['shot_offsets_s'], horizon)
    delay = q(p.get('first_attack_delay_s', 0)) + q(p.get('projectile_travel_s', 0))
    return repeat_events(p['interval_s'], [0], horizon, delay)


def effect_schedule(effect, node, horizon):
    if effect.get('trigger') == 'target_attack_payload_committed':
        return []  # A conditional external attack is never invented here.
    if 'schedule_offsets_s' in effect:
        return repeat_events(effect['cycle_s'], effect['schedule_offsets_s'], horizon)
    if effect.get('trigger') in ('primary_hit', 'actual_wave_contact', 'field_pulse'):
        return hit_schedule(node, horizon)
    interval = effect.get('application_interval_s', 0)
    if interval and effect.get('trigger') in ('independent_field_status_pulse', 'independent_appliance_pulse'):
        return repeat_events(interval, [0], horizon, effect.get('first_application_s', 0))
    return []


def inside(time, windows):
    return any(q(a) <= time < q(b) for a, b in windows)


def offense(node, horizon, armor=0, ward=0, target_count=1,
            windows=None, partner_dps_per_pool=0, susceptible=False):
    """Exact event/integral model for legal direct, poison and heat hits.

    Target order, overlap and LOS are authored inputs. Infinite-HP test bodies
    prevent early kills from silently inflating or removing comparisons.
    """
    if susceptible:
        import copy
        node = copy.deepcopy(node)
        for effect in node.get('effects', []):
            if effect.get('status') == 'heat':
                effect['threshold'] = max(1, effect['threshold'] - 1)
    horizon = q(horizon)
    p = node['parameters']
    windows = [(0, horizon)] if windows is None else windows
    target_count = min(target_count, p.get('target_cap', 1))
    poison = next((e for e in node['effects'] if e['status'] == 'poison'), None)
    heat = next((e for e in node['effects'] if e['status'] == 'heat'), None)
    events = defaultdict(list)
    if p.get('damage_timing') != 'integrate_actual_residence':
        for time in hit_schedule(node, horizon):
            if inside(time, windows):
                events[time].append(('hit', None))
    if p.get('damage_timing') == 'integrate_actual_residence' and heat:
        for time in effect_schedule(heat, node, horizon):
            if inside(time, windows):
                events[time].append(('heat', None))
    if poison:
        maturation = poison.get('maturation')
        for time in hit_schedule(node, horizon):
            if inside(time, windows) and maturation:
                mature_at = time + q(maturation['delay_s'])
                if mature_at < horizon:
                    events[mature_at].append(('mature', q(maturation['additional_amount_q'])))
    # Every possible state boundary is explicit, avoiding frame-count damage.
    breaks = {F(0), horizon, *events.keys()}
    for a, b in windows:
        breaks.update([max(F(0), q(a)), min(horizon, q(b))])
    if p.get('damage_timing') == 'integrate_actual_residence':
        for time in repeat_events(p['cycle_s'], [0, p['active_duration_s']], horizon):
            breaks.add(time)
    if heat:
        for time in list(events):
            if time + q(heat['burn_duration_s']) < horizon:
                breaks.add(time + q(heat['burn_duration_s']))
    times = sorted(t for t in breaks if 0 <= t <= horizon)
    heat_marks, burns = [], []
    poison_q = F(0)
    totals = {'primary': F(0), 'poison': F(0), 'burn': F(0),
              'partner_extra': F(0), 'burn_uptime_s': F(0), 'hits': 0}
    for idx, time in enumerate(times):
        heat_marks = [expiry for expiry in heat_marks if expiry > time]
        burns = [expiry for expiry in burns if expiry > time]
        for event, value in events.get(time, []):
            vuln = q(heat['burn_vulnerability']) if heat and burns else F(0)
            if event == 'hit':
                totals['primary'] += actual_damage(p['damage'], p['channel'], armor,
                                                  ward, p.get('armor_penetration_pp', 0), vuln)
                totals['hits'] += 1
                if poison:
                    poison_q += q(poison['amount'])
                if heat:
                    event = 'heat'
            if event == 'mature':
                poison_q += value
            if event == 'heat':
                for _ in range(int(heat['amount'])):
                    heat_marks.append(time + q(heat['stack_duration_s']))
                    if len(heat_marks) >= heat['threshold']:
                        del heat_marks[:heat['threshold']]
                        burns.append(time + q(heat['burn_duration_s']))
        if idx == len(times) - 1:
            continue
        end = times[idx + 1]
        dt = end - time
        vuln = q(heat['burn_vulnerability']) if heat and burns else F(0)
        totals['poison'] += actual_damage(poison_q * q(poison.get('poison_dps_per_q', .5)) * dt,
                                         'spiritual', armor, ward, 0, vuln) if poison else 0
        if heat and burns:
            totals['burn'] += actual_damage(q(heat['burn_dps']) * dt, 'spiritual', armor, ward, 0, vuln)
            totals['burn_uptime_s'] += dt
            totals['partner_extra'] += q(partner_dps_per_pool) * vuln * dt
        if p.get('damage_timing') == 'integrate_actual_residence':
            active = time % q(p['cycle_s']) < q(p['active_duration_s'])
            if active and inside(time, windows):
                totals['primary'] += actual_damage(q(p['damage_per_second']) * dt, p['channel'],
                                                  armor, ward, 0, vuln)
    for key in ('primary', 'poison', 'burn', 'partner_extra'):
        totals[key] *= target_count
    totals['damage'] = totals['primary'] + totals['poison'] + totals['burn']
    totals['poison_q_per_hit_target'] = poison_q
    totals['target_count'] = target_count
    totals['horizon_s'] = horizon
    totals['scope'] = 'legal_hit_and_residence_fixture_not_AI_or_TTK'
    return clean(totals)


def curse_expected(node, horizon=24, pools=5, incoming_hit=20, enemy_interval=2):
    """Expectation over independent per-attack rolls; never guarantees safety."""
    effect = next(e for e in node['effects'] if e['status'] == 'curse')
    curse_events = {t: 'curse' for t in effect_schedule(effect, node, horizon)}
    enemy_events = repeat_events(enemy_interval, [enemy_interval], horizon)
    marks, doom_until, next_doom = [], F(-1), F(0)
    base, reduced, attack_count, doom_attacks = F(0), F(0), 0, 0
    trace = []
    for t in sorted(set(curse_events) | set(enemy_events)):
        marks = [expiry for expiry in marks if expiry > t]
        if t in curse_events:
            for _ in range(int(effect['amount'])):
                if len(marks) >= effect['threshold']:
                    marks.pop(0)
                marks.append(t + q(effect['stack_duration_s']))
            if len(marks) >= effect['threshold'] and t >= next_doom:
                doom_until = t + q(effect['doom_duration_s'])
                next_doom = t + q(effect['doom_trigger_icd_s'])
        if t in enemy_events:
            amount = q(incoming_hit) * (1 - len(marks) * q(effect['attack_reduction_per_stack']))
            if t < doom_until:
                amount *= 1 - q(effect['doom_failure_normal'])
                doom_attacks += 1
            base += q(incoming_hit)
            reduced += amount
            attack_count += 1
            trace.append({'at_s': t, 'marks': len(marks), 'doom': t < doom_until,
                          'expected_damage_per_pool': amount})
    pools = min(pools, node['parameters']['target_cap'])
    return clean({'incoming_without_curse': base * pools, 'expected_incoming_with_curse': reduced * pools,
                  'expected_prevented': (base - reduced) * pools,
                  'prevented_fraction': 0 if not base else 1 - reduced / base,
                  'pools': pools, 'attacks_per_pool': attack_count, 'doom_attacks_per_pool': doom_attacks,
                  'attack_trace': trace, 'does_not_include_fear_or_order_penalty': True})


class ElectricModel:
    """TD05 charge/queue model on a supplied lawful spatial graph.

    Every positive electric hit returns its actual declared charge. There is
    no total per-wave feedback budget, potency attenuation or stored cap.
    Finite health, simultaneous terminal cleanup and graph changes are modeled;
    navigation/LOS and source hit eligibility are explicit fixture inputs.
    """
    def __init__(self, pools, appliances, edges, base_d=6, duration=8, ward=0,
                 edge_distances=None, health=None):
        self.pools, self.appliances = set(pools), set(appliances)
        self.powered = set(appliances)
        self.live = set(pools)
        self.edges = {tuple(sorted(edge)) for edge in edges}
        self.edge_distances = {tuple(sorted(edge)): q(distance)
                               for edge, distance in (edge_distances or {}).items()}
        self.loads = {pool: [] for pool in self.pools}
        self.initial_health = {p: None if health is None or health.get(p) is None else q(health[p])
                               for p in self.pools}
        if any(v is not None and v <= 0 for v in self.initial_health.values()):
            raise ValueError('fixture pools must start alive')
        self.health = dict(self.initial_health)
        self.susceptible_until = {p: F(0) for p in self.pools}
        self.ready, self.requests = {}, {}
        self.base_d, self.duration = q(base_d), q(duration)
        self.ward = {p: q(ward.get(p, 0) if isinstance(ward, dict) else ward) for p in self.pools}
        self.damage, self.offered_damage = defaultdict(F), defaultdict(F)
        self.wave_trace, self.reservation_trace, self.bounce_trace = [], [], []
        self.death_trace, self.primary_trace = [], []
        self.external_charge = self.expired_charge = self.terminal_charge = F(0)
        self.feedback_charge = self.consumed_charge = F(0)
        self.primary_damage = self.bounce_damage = F(0)
        self.max_charge = self.now = self.next_wave_at = F(0)
        self.lot_sequence = self.request_sequence = self.wave_sequence = 0
        self.broken_reservation_count = 0
        self.used_request_ids, self.used_bounce_phases = set(), set()
        self.used_primary_receipts = set()

    def load(self, pool):
        return sum((lot['quantity'] for lot in self.loads[pool]), F(0))

    def total_load(self):
        return sum((self.load(pool) for pool in self.pools), F(0))

    def total_potency(self):
        return sum((lot['quantity'] * lot['source_D']
                    for pool in self.pools for lot in self.loads[pool]), F(0))

    def threshold(self, pool):
        return 4 if self.susceptible_until[pool] > self.now else 5

    @staticmethod
    def _lot_order(lot):
        return lot['expires'], lot['applied'], lot['lot_id']

    def _queue_if_ready(self, pool, at):
        k = self.threshold(pool)
        if pool not in self.live or pool in self.requests or self.load(pool) < k:
            return False
        remaining, reserved = F(k), []
        for lot in sorted(self.loads[pool], key=self._lot_order):
            if lot['expires'] <= at or lot['quantity'] <= 0:
                continue
            take = min(remaining, lot['quantity'])
            reserved.append((lot['lot_id'], take))
            remaining -= take
            if not remaining:
                break
        if remaining:
            return False
        self.request_sequence += 1
        request = {'request_id': f'ready-{self.request_sequence:08d}',
                   'ready_at': q(at), 'threshold': k, 'reserved': reserved}
        self.requests[pool], self.ready[pool] = request, q(at)
        self.reservation_trace.append(clean({'event': 'ready', 'pool': pool,
                                            'at_s': at, **request}))
        return True

    def _cancel_reservation(self, pool, at, reason):
        request = self.requests.pop(pool, None)
        self.ready.pop(pool, None)
        if request is not None:
            self.broken_reservation_count += 1
            self.reservation_trace.append(clean({'event': 'invalidated', 'pool': pool,
                                                'at_s': at, 'reason': reason, **request}))

    def expire(self, t):
        t = q(t)
        if t < self.now:
            raise ValueError('world time cannot move backwards')
        self.now = t
        for pool in sorted(self.pools):
            kept = []
            for lot in self.loads[pool]:
                if lot['expires'] > t:
                    kept.append(lot)
                else:
                    self.expired_charge += lot['quantity']
            self.loads[pool] = kept
            request = self.requests.get(pool)
            if request is not None:
                live_lots = {lot['lot_id']: lot['quantity'] for lot in kept}
                if request['threshold'] != self.threshold(pool):
                    self._cancel_reservation(pool, t, 'effective_threshold_changed')
                elif any(live_lots.get(identity, F(0)) < amount
                         for identity, amount in request['reserved']):
                    self._cancel_reservation(pool, t, 'reserved_lot_expired_or_removed')
        for pool in sorted(self.live):
            self._queue_if_ready(pool, t)

    def set_susceptible(self, pool, at, duration):
        self.expire(at)
        if pool not in self.live:
            return
        self.susceptible_until[pool] = max(self.susceptible_until[pool], q(at) + q(duration))
        self.expire(at)  # Revalidate same-time reservations using the new threshold.

    def set_powered(self, appliance, enabled):
        if appliance not in self.appliances:
            raise ValueError('not a registered fixture appliance')
        if enabled:
            self.powered.add(appliance)
        else:
            self.powered.discard(appliance)

    def add(self, pool, amount, at, source_d=None, external=True,
            expires_at=None, applied_at=None, source_id=None, lot_id=None):
        amount, at = q(amount), q(at)
        if at < self.now:
            raise ValueError('charge event precedes world time')
        if at > self.now:
            self.expire(at)
        if amount <= 0 or pool not in self.live:
            return None
        source_d = self.base_d if source_d is None else q(source_d)
        if source_d < 0:
            raise ValueError('negative source potency')
        expiry = at + self.duration if expires_at is None else q(expires_at)
        applied = at if applied_at is None else q(applied_at)
        self.lot_sequence += 1
        identity = lot_id or f'lot-{self.lot_sequence:08d}'
        if any(lot['lot_id'] == identity for lots in self.loads.values() for lot in lots):
            raise ValueError('duplicate charge lot ID')
        if external:
            self.external_charge += amount
        else:
            self.feedback_charge += amount
        if expiry <= at:
            self.expired_charge += amount
            return None
        self.loads[pool].append({'lot_id': identity, 'quantity': amount,
                                 'source_D': source_d, 'applied': applied, 'expires': expiry,
                                 'source_id': source_id or ('external' if external else 'feedback')})
        self._queue_if_ready(pool, at)
        self.max_charge = max(self.max_charge, self.load(pool))
        return identity

    def _damage(self, pool, damage):
        if pool not in self.live or self.health[pool] == 0:
            return F(0)
        offered = actual_damage(damage, 'spiritual', ward=self.ward[pool])
        dealt = offered if self.health[pool] is None else min(self.health[pool], offered)
        self.offered_damage[pool] += offered
        self.damage[pool] += dealt
        if self.health[pool] is not None:
            self.health[pool] -= dealt
        return dealt

    def finish_batch(self, at):
        dead = sorted(p for p in self.live if self.health[p] == 0)
        for pool in dead:
            lost = self.load(pool)
            self.terminal_charge += lost
            self.loads[pool] = []
            self._cancel_reservation(pool, at, 'true_terminal')
            self.live.remove(pool)
            self.death_trace.append(clean({'pool': pool, 'at_s': at, 'discarded_charge': lost}))
        return dead

    def primary(self, pool, at, damage, charge=1, source_d=None,
                source_id=None, pure_charge=False, receipt=None, finish=True):
        self.expire(at)
        if receipt is not None:
            receipt = tuple(receipt)
            if receipt in self.used_primary_receipts:
                return F(0)
            self.used_primary_receipts.add(receipt)
        if pool not in self.live:
            return F(0)
        if q(charge) < 0:
            raise ValueError('negative electric charge payload')
        dealt = self._damage(pool, damage)
        self.primary_damage += dealt
        # A native +2 replaces the generic +1; it is not +3. Conversely a
        # positive electric packet cannot silently declare zero feedback.
        granted = max(F(1), q(charge)) if dealt > 0 else (q(charge) if pure_charge else F(0))
        if granted:
            self.add(pool, granted, at, source_d=source_d, source_id=source_id)
        self.primary_trace.append(clean({'at_s': at, 'pool': pool, 'actual_damage': dealt,
                                        'charge': granted, 'source': source_id}))
        if finish:
            self.finish_batch(at)
        return dealt

    def graph(self):
        eligible = self.powered | {pool for pool in self.live if self.load(pool) > 0}
        graph = {node: set() for node in eligible}
        for a, b in self.edges:
            if a in graph and b in graph:
                graph[a].add(b)
                graph[b].add(a)
        return graph

    def ordinary_bounce(self, impacts, at, phase_key):
        """One real direct pool-to-pool arc per entire eligible source phase."""
        phase_key = tuple(phase_key)
        if phase_key in self.used_bounce_phases:
            return False
        self.used_bounce_phases.add(phase_key)
        graph, candidates = self.graph(), []
        for origin, source_d in impacts:
            for target in graph.get(origin, set()) & self.live:
                if target == origin:
                    continue
                edge = tuple(sorted((origin, target)))
                candidates.append((self.edge_distances.get(edge, F(1)), origin, target, q(source_d)))
        if not candidates:
            return False
        _, origin, target, source_d = min(candidates)
        dealt = self._damage(target, 3)
        self.bounce_damage += dealt
        if dealt > 0:
            self.add(target, 1, at, source_d=source_d, source_id='ordinary_bounce')
        self.bounce_trace.append(clean({'at_s': at, 'phase': phase_key, 'origin': origin,
                                       'target': target, 'damage': dealt,
                                       'charge_units': 1 if dealt > 0 else 0, 'source_D': source_d}))
        self.finish_batch(at)
        return True

    def consume(self, pool):
        request = self.requests.get(pool)
        if request is None:
            self._queue_if_ready(pool, self.now)
            request = self.requests.get(pool)
        if request is None or request['request_id'] in self.used_request_ids:
            raise ValueError('no unused valid reservation')
        k = self.threshold(pool)
        if request['threshold'] != k:
            raise ValueError('threshold changed before consumption')
        by_id = {lot['lot_id']: lot for lot in self.loads[pool]}
        for identity, quantity in request['reserved']:
            lot = by_id.get(identity)
            if lot is None or lot['quantity'] < quantity or lot['expires'] <= self.now:
                raise ValueError('reserved charge expired or removed')
        mass, consumed = F(0), []
        for identity, quantity in request['reserved']:
            lot = by_id[identity]
            mass += quantity * lot['source_D']
            lot['quantity'] -= quantity
            consumed.append({'lot_id': identity, 'quantity': quantity,
                             'source_D': lot['source_D'], 'expiry': lot['expires']})
        self.loads[pool] = [lot for lot in self.loads[pool] if lot['quantity'] > 0]
        self.used_request_ids.add(request['request_id'])
        self.requests.pop(pool)
        self.ready.pop(pool, None)
        self.consumed_charge += k
        d = mass / k
        self.reservation_trace.append(clean({'event': 'consumed', 'pool': pool, 'at_s': self.now,
                                            'request_id': request['request_id'], 'threshold': k,
                                            'lots': consumed, 'D': d}))
        return d

    def wave(self, at):
        at = q(at)
        self.expire(at)
        if not self.ready or at < self.next_wave_at:
            return False
        seed = min(self.ready, key=lambda pool: (self.ready[pool], pool))
        graph = self.graph()
        reached, todo = set(), [seed]
        while todo:
            point = todo.pop()
            if point in reached:
                continue
            reached.add(point)
            todo.extend(graph.get(point, set()) - reached)
        targets = sorted(reached & self.live)
        before = self.total_load()
        counts = {pool: (1 + len(graph[pool] & self.live), len(graph[pool] & self.powered))
                  for pool in targets}
        request_id = self.requests[seed]['request_id']
        k = self.requests[seed]['threshold']
        d = self.consume(seed)
        self.wave_sequence += 1
        wave_id = f'wave-{self.wave_sequence:08d}'
        self.next_wave_at = at + F(1, 4)
        offered = {pool: actual_damage(d * (n + e), 'spiritual', ward=self.ward[pool])
                   for pool, (n, e) in counts.items()}
        dealt = {pool: self._damage(pool, d * sum(counts[pool])) for pool in targets}
        positive = [pool for pool in targets if dealt[pool] > 0]
        for pool in positive:
            self.add(pool, 1, at, source_d=d, external=False, source_id=wave_id,
                     lot_id=f'{wave_id}:{pool}:feedback')
        dead = self.finish_batch(at)
        for pool in sorted(self.live):
            self._queue_if_ready(pool, at)
        self.wave_trace.append(clean({'at_s': at, 'wave_id': wave_id, 'request_id': request_id,
                                      'seed': seed, 'consumed_threshold': k,
                                      'connected': sorted(reached), 'D': d, 'local_counts': counts,
                                      'offered_damage': offered, 'actual_damage': dealt,
                                      'feedback_per_positive_pool': 1,
                                      'feedback_generated': len(positive),
                                      'feedback_surviving_this_wave': len(set(positive) - set(dead)),
                                      'dead_after_wave': dead, 'live_after_wave': sorted(self.live),
                                      'charge_before': before, 'charge_after': self.total_load()}))
        return True

    def summary(self):
        total_damage = sum(self.damage.values(), F(0))
        return clean({'total_damage': total_damage, 'damage_by_pool': dict(self.damage),
                      'offered_damage': sum(self.offered_damage.values(), F(0)),
                      'overkill': sum(self.offered_damage.values(), F(0)) - total_damage,
                      'primary_damage': self.primary_damage, 'ordinary_bounce_damage': self.bounce_damage,
                      'ordinary_bounces': len(self.bounce_trace),
                      'overload_damage': total_damage - self.primary_damage - self.bounce_damage,
                      'waves': len(self.wave_trace), 'external_charge': self.external_charge,
                      'feedback_charge': self.feedback_charge, 'consumed_charge': self.consumed_charge,
                      'expired_charge': self.expired_charge, 'terminal_charge': self.terminal_charge,
                      'remaining_charge': self.total_load(), 'maximum_pool_charge': self.max_charge,
                      'charge_ledger_balances': self.external_charge + self.feedback_charge == self.consumed_charge + self.expired_charge + self.terminal_charge + self.total_load(),
                      'ready_requests': len(self.ready), 'ready_pool_ids': sorted(self.ready),
                      'broken_reservation_count': self.broken_reservation_count,
                      'finite_health': all(v is not None for v in self.initial_health.values()),
                      'initial_health': self.initial_health, 'remaining_health': self.health,
                      'deaths': len(self.death_trace), 'living_pools': sorted(self.live),
                      'kill_times': {row['pool']: row['at_s'] for row in self.death_trace},
                      'per_wave_feedback_total_cap': None, 'feedback_potency_multiplier': 1,
                      'geometry_scope': 'fixture-supplied legal graph, not inferred map LOS or navigation',
                      'wave_trace': self.wave_trace, 'bounce_trace': self.bounce_trace,
                      'reservation_trace': self.reservation_trace, 'death_trace': self.death_trace,
                      'primary_trace': self.primary_trace})


def complete_edges(nodes):
    nodes = list(nodes)
    return [(a, b) for i, a in enumerate(nodes) for b in nodes[i + 1:]]


def run_electric(pools, appliances, edges, inputs=(), initial=None, horizon=24,
                 base_d=6, powered=True, ward=0, ordinary_bounce=False,
                 edge_distances=None, health=None, transitions=()):
    """Finite-horizon replay with explicit HP, target hits and graph changes.

    Tuples (time,pool,damage,charge) share one source phase at that time.
    Dictionaries can set source_id/phase_id/source_D/pure_charge. A candidate
    pool list plus target_cap chooses living fixture targets at the real phase
    time, enabling honest retargeting after deaths. Transitions may change
    susceptibility, legal edges or actual registered appliance power.
    """
    model = ElectricModel(pools, appliances, edges, base_d=base_d, ward=ward,
                          edge_distances=edge_distances, health=health)
    if not powered:
        model.powered.clear()
    events, state_events = defaultdict(list), defaultdict(list)
    for item in inputs:
        if isinstance(item, dict):
            event = dict(item)
            time = q(event.get('time', event.get('at_s', 0)))
            event.setdefault('source_id', 'fixture-primary')
            event.setdefault('phase_id', str(time))
            event.setdefault('source_D', base_d)
            event.setdefault('pure_charge', False)
        else:
            time, pool, damage, charge, *optional = item
            time = q(time)
            event = {'pool': pool, 'damage': damage, 'charge': charge,
                     'source_id': optional[0] if optional else 'fixture-primary',
                     'phase_id': optional[1] if len(optional) > 1 else str(time),
                     'source_D': base_d, 'pure_charge': False}
        if 0 <= time < q(horizon):
            events[time].append(event)
    for event in transitions:
        time = q(event['time'])
        if 0 <= time < q(horizon):
            state_events[time].append(event)
    for pool, amount in sorted((initial or {}).items()):
        model.add(pool, amount, 0)
    times = set(events) | set(state_events)
    times.update(repeat_events(.25, [0], horizon))
    for time in sorted(times):
        model.expire(time)
        for transition in state_events.get(time, []):
            if transition['kind'] == 'susceptible':
                model.set_susceptible(transition['pool'], time, transition['duration_s'])
            elif transition['kind'] == 'power':
                model.set_powered(transition['appliance'], transition['enabled'])
            elif transition['kind'] == 'edges':
                model.edges = {tuple(sorted(edge)) for edge in transition['edges']}
            else:
                raise ValueError('unknown state transition')
        phases = defaultdict(list)
        for event in events.get(time, []):
            if event.get('requires_powered_appliance') and event['requires_powered_appliance'] not in model.powered:
                continue
            expanded = [event]
            if 'candidate_pools' in event:
                chosen = [p for p in event['candidate_pools'] if p in model.live][:event.get('target_cap', 1)]
                expanded = [dict(event, pool=p) for p in chosen]
            for impact in expanded:
                phases[(str(impact['source_id']), str(impact['phase_id']))].append(impact)
        for phase, emissions in sorted(phases.items()):
            impacts = []
            for event in emissions:
                dealt = model.primary(event['pool'], time, event['damage'], event['charge'],
                                      source_d=event['source_D'], source_id=event['source_id'],
                                      pure_charge=event['pure_charge'],
                                      receipt=(*phase, event['pool']), finish=False)
                if dealt > 0:
                    impacts.append((event['pool'], event['source_D']))
            model.finish_batch(time)
            if ordinary_bounce and impacts:
                model.ordinary_bounce(impacts, time, phase)
        if time % F(1, 4) == 0:
            model.wave(time)
    model.expire(q(horizon))
    return model.summary()


def electric_reservation_fixture():
    model = ElectricModel(['A', 'B'], [], [('A', 'B')], health={'A': 100, 'B': 100})
    model.add('A', 2, 0, expires_at=1, lot_id='A-early')
    model.add('A', 3, 0, expires_at=8, lot_id='A-late')
    original = dict(model.requests['A'])
    model.add('A', 4, .5, expires_at=8.5, lot_id='A-overflow')
    model.add('B', 5, .5, lot_id='B-ready')
    model.expire(1)
    renewed = dict(model.requests['A'])
    held = model.load('A')
    model.wave(1)
    ordering = ElectricModel(['P'], [], [], health={'P': 100})
    ordering.add('P', 3, 0, expires_at=8, lot_id='newer-deadline')
    ordering.add('P', 4, .5, expires_at=2, applied_at=-6, lot_id='inherited-earlier-deadline')
    chosen = list(ordering.requests['P']['reserved'])
    d = ordering.consume('P')
    return clean({'old_request_id': original['request_id'], 'old_ready_at': original['ready_at'],
                  'new_request_id': renewed['request_id'], 'new_ready_at': renewed['ready_at'],
                  'broken_reservations': model.broken_reservation_count,
                  'A_load_after_reserved_expiry': held, 'first_seed_after_expiry': model.wave_trace[0]['seed'],
                  'earliest_expiry_reserved_lots': chosen, 'consumed_D': d,
                  'post_consumption_surplus': ordering.load('P'), 'post_consumption_lots': ordering.loads['P']})


def susceptible_fixture():
    model = ElectricModel(['A'], ['AP1'], [('A', 'AP1')], health={'A': 100})
    model.add('A', 4, 0)
    no_request_at_four = not model.ready
    model.set_susceptible('A', .1, .1)
    low_request = dict(model.requests['A'])
    model.expire(.25)
    no_wave_after_expiry = not model.wave(.25)
    model.add('A', 1, .3)
    model.wave(.5)
    active = ElectricModel(['A'], ['AP1'], [('A', 'AP1')], health={'A': 100})
    active.add('A', 4, 0)
    active.set_susceptible('A', 0, 5)
    active.set_susceptible('A', 0, 2)
    active.wave(0)
    return {'normal_four_not_ready': no_request_at_four,
            'susceptible_four_ready_threshold': low_request['threshold'],
            'expired_four_cannot_emit': no_wave_after_expiry,
            'five_after_expiry': model.summary(), 'four_with_susceptible': active.summary()}


def finite_direct_fixture(damage, cycle, healths, horizon=24):
    """Living lowest-index retarget, no status, measuring overkill explicitly."""
    hp = list(map(q, healths))
    actual = overkill = F(0)
    kills, hits = [], []
    for t in repeat_events(cycle, [0], horizon):
        target = next((i for i, h in enumerate(hp) if h > 0), None)
        if target is None:
            break
        dealt = min(q(damage), hp[target])
        actual += dealt
        overkill += q(damage) - dealt
        hp[target] -= dealt
        hits.append({'at_s': t, 'target': target, 'actual': dealt})
        if hp[target] == 0:
            kills.append({'at_s': t, 'target': target})
    return clean({'actual_damage': actual, 'overkill': overkill, 'kills': kills, 'remaining_hp': hp, 'hits': hits})


class StatusMeter:
    """Small event model for paid heat/frost/curse marks and susceptibility.

    This validates threshold/expiry/source strength, not runtime control or
    AI. The source supplied by each real application is retained on its marks.
    """
    def __init__(self, kind):
        if kind not in ('heat', 'frost', 'curse'):
            raise ValueError('this meter does not invent a poison threshold')
        self.kind = kind
        self.base_threshold = {'heat': 8, 'frost': 4, 'curse': 4}[kind]
        self.duration = 10 if kind == 'curse' else 6
        self.cooldown = 0 if kind == 'heat' else 8
        self.now = self.susceptible_until = self.next_attempt = F(0)
        self.marks, self.events = [], []
        self.applied = self.consumed = self.expired = self.replaced = 0

    def threshold(self):
        return self.base_threshold - int(self.susceptible_until > self.now)

    def advance(self, at):
        at = q(at)
        if at < self.now:
            raise ValueError('nonmonotonic meter time')
        self.now = at
        old = len(self.marks)
        self.marks = [m for m in self.marks if m['expires'] > at]
        self.expired += old - len(self.marks)

    def _check(self, reason):
        k = self.threshold()
        if len(self.marks) < k or self.now < self.next_attempt:
            return False
        paid = self.marks[:k]
        if self.kind != 'curse':
            del self.marks[:k]
            self.consumed += k
        self.next_attempt = self.now + self.cooldown
        payload = {}
        if self.kind == 'heat':
            payload = {name: sum(q(m['payload'][name]) for m in paid) / k
                       for name in ('burn_dps', 'vulnerability')}
        elif self.kind == 'frost':
            payload = dict(paid[-1]['payload'])
        else:
            payload = {'attack_failure_probability': q(.3),
                       'direct_attack_reduction': q(.04) * len(self.marks)}
        self.events.append(clean({'at_s': self.now, 'reason': reason, 'threshold': k,
                                  'paid_mark_count': k, 'consumes_marks': self.kind != 'curse',
                                  'payload': payload}))
        return True

    def apply(self, amount, at, payload=None):
        self.advance(at)
        if not isinstance(amount, int) or amount < 0:
            raise ValueError('paid cold/heat/curse applications use nonnegative integer marks')
        payload = payload or ({'burn_dps': 2, 'vulnerability': .15} if self.kind == 'heat' else {})
        for _ in range(amount):
            self.applied += 1
            self.marks.append({'expires': self.now + self.duration, 'payload': dict(payload)})
            cap = 4 if self.kind == 'curse' else (self.threshold() - 1 if self.kind == 'frost' and self.now < self.next_attempt else None)
            if cap is not None and len(self.marks) > cap:
                self.marks.pop(0)
                self.replaced += 1
            self._check('paid_meter_application')

    def susceptible(self, at, duration):
        self.advance(at)
        self.susceptible_until = max(self.susceptible_until, self.now + q(duration))
        self._check('paid_susceptible_application')


def heat_susceptible_fixture():
    heat = StatusMeter('heat')
    heat.apply(7, 0, {'burn_dps': 2, 'vulnerability': .25})
    before = len(heat.events)
    heat.susceptible(.5, 2)
    heat.susceptible(.5, 1)  # Another source is not another missing mark.
    mixed = StatusMeter('heat')
    mixed.apply(3, 0, {'burn_dps': 2, 'vulnerability': .25})
    mixed.apply(4, .1, {'burn_dps': 2, 'vulnerability': .15})
    mixed.susceptible(.2, 4)
    curse = StatusMeter('curse')
    curse.apply(3, 0)
    curse.susceptible(.5, 5)
    curse.susceptible(1, 5)
    curse.apply(1, 2)
    frost = StatusMeter('frost')
    frost.apply(3, 0, {'freeze_duration_s': 1})
    frost.susceptible(.5, 5)
    frost.apply(4, 1, {'freeze_duration_s': 1.5})
    return clean({'marks_before': 7, 'burns_before_susceptible': before,
                  'marks_added_by_susceptible': heat.applied - 7,
                  'consumed_on_gain': heat.consumed, 'burns_on_gain': len(heat.events),
                  'remaining_marks': len(heat.marks),
                  'result_DPS': heat.events[0]['payload']['burn_dps'],
                  'result_vulnerability': heat.events[0]['payload']['vulnerability'],
                  'mixed_source_burn': mixed.events,
                  'curse_events': curse.events, 'curse_marks_after_fourth_real_hit': len(curse.marks),
                  'frost_events': frost.events, 'frost_reserve_during_cooldown': len(frost.marks),
                  'poison_threshold': None})


def raw_primary_profile(node, horizon=24):
    """All-tree audit metric, with support budgets kept separate from damage."""
    p, mode = node['parameters'], node['mode']
    metrics = {'mode': mode, 'window_s': horizon, 'range_tiles': p.get('range_tiles'),
               'target_cap': p.get('target_cap', 1), 'layers': node['layers']}
    amount, note = F(0), 'one legal stationary pool; direct packets only; excludes status/utility'
    if 'exposure_stages' in p:
        for i, stage in enumerate(p['exposure_stages']):
            end = p['exposure_stages'][i + 1]['at_s'] if i + 1 < len(p['exposure_stages']) else horizon
            amount += q(stage['dps']) * max(F(0), min(q(horizon), q(end)) - q(stage['at_s']))
        metrics['two_pool_total_if_two_streams'] = amount * min(2, p.get('beam_streams', 1))
        note = 'continuous unobstructed exposure; reset-on-switch and lost LOS lower this value'
    elif p.get('damage_timing') == 'integrate_actual_residence':
        active = sum((min(q(p['active_duration_s']), q(horizon) - t)
                      for t in repeat_events(p['cycle_s'], [0], horizon)), F(0))
        amount = active * q(p['damage_per_second'])
        metrics['active_residence_s'] = active
        metrics['radius_tiles'] = p['field_radius_tiles']
        note = 'one pool remaining in each active field for its whole duration; no status damage'
    elif 'cell_damage' in p:
        amount = q(p['cell_damage']) / q(p['cell_period_s']) * q(horizon)
        active_cells = p.get('cells_per_group', p['cell_count'])
        metrics['simultaneously_active_cells'] = active_cells
        metrics['fresh_full_corridor_damage'] = q(p['cell_damage']) * active_cells
        metrics['phase_full_corridor_damage'] = q(p.get('phase_cell_damage', p.get('phase_audit_cell_damage', p['cell_damage']))) * active_cells
        if active_cells != p['cell_count']:
            metrics['all_authored_cells_over_multiple_correctly_timed_passages'] = q(p['cell_damage']) * p['cell_count']
        if 'landing_damage' in p:
            metrics['phase_corridor_with_one_valid_reserved_landing'] = metrics['phase_full_corridor_damage'] - q(p.get('phase_cell_damage', p['cell_damage'])) + q(p['landing_damage'])
        note = 'stationary-cell nominal ceiling before downtime; crossing/phase use dedicated traces'
    elif p.get('damage_on_actual_crossing_only'):
        amount = F(0)
        metrics['one_actual_crossing_damage'] = p['damage']
        note = 'stationary target does not cross curtain: zero; each eligible real crossing has its own event'
    elif 'guard_count' in p:
        contacts = len(repeat_events(p['guard_target_reintercept_icd_s'], [0], horizon))
        amount = contacts * q(p['damage'])
        metrics['team_hp'] = p['guard_hp_each'] * p['guard_count']
        metrics['team_ground_block_slots'] = p['guard_block_count_each'] * p['guard_count']
        metrics['one_pool_ideal_contact_windows'] = contacts
        metrics['one_pool_ideal_hold_s'] = contacts * q(p['guard_max_hold_s'])
        metrics['team_contact_damage_if_each_guard_has_a_real_distinct_target'] = amount * p['guard_count']
        if 'flank_bonus_damage' in p:
            metrics['damage_with_two_real_guard_strikes_and_one_flank_per_window'] = amount * 2 + contacts * p['flank_bonus_damage']
        if 'ranged_damage' in p:
            metrics['ranged_team_damage_only_if_no_interception_or_rebuild'] = q(p['ranged_damage']) * p['guard_count'] * len(hit_schedule(node, horizon))
        note = 'one ground pool actually contacts one ready doll at each six-second boundary; each contact has at most one real attack and one-second hold, not continuous melee DPS'
    elif 'single_target_damage' in p:
        amount = len(repeat_events(p['single_target_interval_s'], [0], horizon)) * q(p['single_target_damage'])
        metrics['two_pool_primary_total'] = len(hit_schedule(node, horizon)) * q(p['damage'])
        note = 'one-pool fallback uses the actual solo damage/cycle; two-pool alternating direct packets reported separately, electric chain in finite-health fixtures'
    else:
        amount = len(hit_schedule(node, horizon)) * q(p['damage'])
        if 'ordered_pool_multipliers' in p:
            metrics['aligned_three_pool_damage'] = amount * sum(map(q, p['ordered_pool_multipliers']))
        if 'secondary_every_primary_attacks' in p:
            metrics['two_pool_damage_with_secondary'] = amount + (len(hit_schedule(node, horizon)) // p['secondary_every_primary_attacks']) * p['secondary_damage']
    metrics['raw_direct_damage_nominal_24s'] = amount
    metrics['raw_direct_dps_nominal'] = amount / q(horizon)
    metrics['fixture_note'] = note
    for effect in node['effects']:
        status = effect['status']
        if status == 'attack_speed':
            metrics['ally_30_raw_normal_dps_gain'] = 30 * q(effect['amount'])
        if status == 'frost':
            metrics['freeze_duration_s'] = effect['freeze_duration_normal_s']
            metrics['freeze_attempt_interval_min_s'] = effect['freeze_attempt_icd_s']
        if status == 'brittle':
            metrics['other_tower_bonus_per_valid_mark'] = effect['amount']
        if status == 'rule_cooperation_vulnerability':
            metrics['one_valid_rule_30_dps_window_bonus'] = 30 * q(effect['amount']) * q(effect['duration_s'])
        if status == 'electric':
            metrics['electric_charge_per_paid_hit'] = effect['amount']
            metrics['overload_D_native'] = effect['overload_base_damage']
        if status == 'poison':
            metrics['poison_q_per_paid_primary'] = effect['amount']
        if status == 'seal':
            metrics['seal_duration_s'] = effect['amount']
        if status == 'root':
            metrics['landing_root_normal_s'] = effect['amount']
            metrics['landing_root_elite_s'] = effect.get('duration_elite_s', effect.get('elite_duration_s', .6))
    for key in ('push_distance_tiles', 'pull_distance_tiles', 'push_pool_cap', 'pull_pool_cap',
                'reload_progress_fraction', 'reload_shared_icd_s', 'light_radius_tiles',
                'spot_count', 'spot_radius_tiles', 'seal_charge_capacity'):
        if key in p:
            metrics[key] = p[key]
    if p.get('seal_field_cycle_s', 'absent') is None and 'seal_field_cooldown_s' in p:
        metrics['seal_field_activation'] = 'stored_permission_requires_real_eligible_preparation'
        metrics['seal_field_active_s'] = p['seal_field_active_s']
        metrics['seal_field_cooldown_from_deployment_s'] = p['seal_field_cooldown_s']
        metrics['seal_field_max_distinct_pools'] = p['seal_field_target_cap']
    return clean(metrics)
