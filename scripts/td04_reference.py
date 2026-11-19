#!/usr/bin/env python3
"""Deterministic TD04 design models. These are not the V0.10 game runtime.

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
            windows=None, partner_dps_per_pool=0):
    """Exact event/integral model for legal direct, poison and heat hits.

    Target order, overlap and LOS are authored inputs. Infinite-HP test bodies
    prevent early kills from silently inflating or removing comparisons.
    """
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
    """Finite feedback on an externally supplied, already-legal spatial graph.

    This is a charge/queue/damage model, not a LOS or navigation generator.
    Charge quantities and potency use exact rational arithmetic.  Every ready
    request reserves five real quantities from immutable, expiring lot IDs.
    """
    def __init__(self, pools, appliances, edges, base_d=2.5, feedback_budget=2,
                 feedback_energy_factor=.75, duration=8, ward=0,
                 edge_distances=None):
        self.pools, self.appliances = set(pools), set(appliances)
        self.edges = {tuple(sorted(edge)) for edge in edges}
        self.edge_distances = {tuple(sorted(edge)): q(distance)
                               for edge, distance in (edge_distances or {}).items()}
        self.loads = {pool: [] for pool in self.pools}
        self.ready, self.requests = {}, {}
        self.base_d, self.feedback_budget = q(base_d), q(feedback_budget)
        self.feedback_energy_factor = q(feedback_energy_factor)
        self.duration, self.ward = q(duration), q(ward)
        if not 0 < self.feedback_budget < 5:
            raise ValueError('feedback budget must be positive and below five')
        self.damage = defaultdict(F)
        self.wave_trace, self.reservation_trace, self.bounce_trace = [], [], []
        self.external_charge = self.expired_charge = F(0)
        self.feedback_charge = self.consumed_charge = F(0)
        self.primary_damage = self.bounce_damage = F(0)
        self.max_charge = self.now = F(0)
        self.next_wave_at = F(0)
        self.lot_sequence = self.request_sequence = self.wave_sequence = 0
        self.broken_reservation_count = 0
        self.used_request_ids, self.used_bounce_phases = set(), set()

    def load(self, pool):
        return sum((lot['quantity'] for lot in self.loads[pool]), F(0))

    def total_load(self):
        return sum((self.load(pool) for pool in self.pools), F(0))

    def total_potency(self):
        return sum((lot['quantity'] * lot['coefficient']
                    for pool in self.pools for lot in self.loads[pool]), F(0))

    @staticmethod
    def _lot_order(lot):
        return lot['expires'], lot['applied'], lot['lot_id']

    def _queue_if_ready(self, pool, at):
        if pool in self.requests or self.load(pool) < 5:
            return False
        remaining, reserved = F(5), []
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
                   'ready_at': q(at), 'reserved': reserved}
        self.requests[pool], self.ready[pool] = request, q(at)
        self.reservation_trace.append(clean({'event': 'ready', 'pool': pool,
                                            'at_s': at, **request}))
        return True

    def _cancel_reservation(self, pool, at, reason):
        request = self.requests.pop(pool, None)
        self.ready.pop(pool, None)
        if request is not None:
            self.broken_reservation_count += 1
            self.reservation_trace.append(clean({'event': 'invalidated',
                                                'pool': pool, 'at_s': at,
                                                'reason': reason, **request}))

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
                live = {lot['lot_id']: lot['quantity'] for lot in kept}
                if any(live.get(lot_id, F(0)) < amount
                       for lot_id, amount in request['reserved']):
                    # Losing one reserved unit invalidates queue priority even
                    # when new unreserved overflow still leaves total q >= 5.
                    self._cancel_reservation(pool, t, 'reserved_lot_expired_or_removed')
        for pool in sorted(self.pools):
            self._queue_if_ready(pool, t)

    def add(self, pool, amount, at, contribution_per_q=None, external=True,
            expires_at=None, applied_at=None, source_id=None, lot_id=None):
        amount, at = q(amount), q(at)
        if at < self.now:
            raise ValueError('charge event time precedes current world time')
        if at > self.now:
            self.expire(at)
        if amount <= 0:
            return None
        coefficient = self.base_d / 5 if contribution_per_q is None else q(contribution_per_q)
        expiry = at + self.duration if expires_at is None else q(expires_at)
        applied = at if applied_at is None else q(applied_at)
        self.lot_sequence += 1
        identity = lot_id or f'lot-{self.lot_sequence:08d}'
        if any(lot['lot_id'] == identity for lots in self.loads.values() for lot in lots):
            raise ValueError('charge lot IDs must be unique')
        if external:
            self.external_charge += amount
        else:
            self.feedback_charge += amount
        if expiry <= at:
            self.expired_charge += amount
            return None
        self.loads[pool].append({'lot_id': identity, 'quantity': amount,
                                 'coefficient': coefficient, 'applied': applied,
                                 'expires': expiry,
                                 'source_id': source_id or ('external' if external else 'feedback')})
        self._queue_if_ready(pool, at)
        self.max_charge = max(self.max_charge, self.load(pool))
        return identity

    def primary(self, pool, at, damage, charge, source_d=None,
                source_id=None, pure_charge=False):
        dealt = actual_damage(damage, 'spiritual', ward=self.ward)
        self.damage[pool] += dealt
        self.primary_damage += dealt
        if dealt > 0 or pure_charge:
            coefficient = (self.base_d if source_d is None else q(source_d)) / 5
            self.add(pool, charge, at, coefficient, source_id=source_id)
        return dealt

    def graph(self):
        eligible = self.appliances | {pool for pool in self.pools if self.load(pool) > 0}
        graph = {node: set() for node in eligible}
        for a, b in self.edges:
            if a in graph and b in graph:
                graph[a].add(b)
                graph[b].add(a)
        return graph

    def ordinary_bounce(self, impacts, at, phase_key):
        """At most one direct pool-to-pool arc for an entire source phase.

        impacts contains (actual primary impact pool, source D). Edges supplied
        by a fixture are already legal. Without edge_distances they are treated
        as equal-distance examples, with stable IDs deciding the one arc.
        """
        phase_key = tuple(phase_key)
        if phase_key in self.used_bounce_phases:
            return False
        self.used_bounce_phases.add(phase_key)
        graph = self.graph()
        candidates = []
        for origin, source_d in impacts:
            for target in graph.get(origin, set()) & self.pools:
                if target == origin:
                    continue
                edge = tuple(sorted((origin, target)))
                candidates.append((self.edge_distances.get(edge, F(1)),
                                   origin, target, q(source_d)))
        if not candidates:
            return False
        _, origin, target, source_d = min(candidates)
        dealt = actual_damage(3, 'spiritual', ward=self.ward)
        self.damage[target] += dealt
        self.bounce_damage += dealt
        if dealt > 0:
            self.add(target, 1, at, source_d * self.feedback_energy_factor / 5,
                     source_id='ordinary_bounce')
        self.bounce_trace.append(clean({'at_s': at, 'phase': phase_key,
                                       'origin': origin, 'target': target,
                                       'damage': dealt,
                                       'charge_units': 1 if dealt > 0 else 0,
                                       'source_D': source_d * self.feedback_energy_factor}))
        return True

    def consume(self, pool, amount=5):
        if q(amount) != 5:
            raise ValueError('an overload must consume exactly five reserved units')
        request = self.requests.get(pool)
        if request is None:
            self._queue_if_ready(pool, self.now)
            request = self.requests.get(pool)
        if request is None or request['request_id'] in self.used_request_ids:
            raise ValueError('no unused valid five-unit reservation')
        by_id = {lot['lot_id']: lot for lot in self.loads[pool]}
        for lot_id, quantity in request['reserved']:
            lot = by_id.get(lot_id)
            if lot is None or lot['quantity'] < quantity or lot['expires'] <= self.now:
                raise ValueError('reserved charge expired or was removed')
        d, consumed = F(0), []
        for lot_id, quantity in request['reserved']:
            lot = by_id[lot_id]
            contribution = quantity * lot['coefficient']
            d += contribution
            lot['quantity'] -= quantity
            consumed.append({'lot_id': lot_id, 'quantity': quantity,
                             'contribution': contribution, 'expiry': lot['expires']})
        self.loads[pool] = [lot for lot in self.loads[pool] if lot['quantity'] > 0]
        self.used_request_ids.add(request['request_id'])
        self.requests.pop(pool)
        self.ready.pop(pool, None)
        self.consumed_charge += 5
        self.reservation_trace.append(clean({'event': 'consumed', 'pool': pool,
                                            'at_s': self.now,
                                            'request_id': request['request_id'],
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
        targets = sorted(reached & self.pools)
        before, potency_before = self.total_load(), self.total_potency()
        counts = {pool: (1 + len(graph[pool] & self.pools), len(graph[pool] & self.appliances))
                  for pool in targets}
        request_id = self.requests[seed]['request_id']
        d = self.consume(seed)
        self.wave_sequence += 1
        wave_id = f'wave-{self.wave_sequence:08d}'
        self.next_wave_at = at + F(1, 4)
        dealt = {}
        for pool, (n, e) in counts.items():
            dealt[pool] = actual_damage(d * (n + e), 'spiritual', ward=self.ward)
            self.damage[pool] += dealt[pool]
        positive = [pool for pool, damage in dealt.items() if damage > 0]
        feedback = min(F(1), self.feedback_budget / len(positive)) if positive else F(0)
        for pool in positive:
            self.add(pool, feedback, at, d / 5 * self.feedback_energy_factor,
                     external=False, source_id=wave_id,
                     lot_id=f'{wave_id}:{pool}:feedback')
        # All feedback is in the just-completed atomic wave; another emission
        # still needs a later network tick, including an overflow-ready seed.
        for pool in sorted(self.pools):
            self._queue_if_ready(pool, at)
        after, potency_after = self.total_load(), self.total_potency()
        self.wave_trace.append(clean({'at_s': at, 'wave_id': wave_id,
                                      'request_id': request_id, 'seed': seed,
                                      'connected': sorted(reached), 'D': d,
                                      'local_counts': counts, 'damage': dealt,
                                      'feedback_per_hit_pool': feedback,
                                      'charge_before': before, 'charge_after': after,
                                      'charge_decrease': before - after,
                                      'potency_before': potency_before,
                                      'potency_after': potency_after,
                                      'potency_decrease': potency_before - potency_after}))
        return True

    def summary(self):
        return clean({'total_damage': sum(self.damage.values(), F(0)),
                      'damage_by_pool': dict(self.damage), 'primary_damage': self.primary_damage,
                      'ordinary_bounce_damage': self.bounce_damage,
                      'ordinary_bounces': len(self.bounce_trace),
                      'overload_damage': sum(self.damage.values(), F(0)) - self.primary_damage - self.bounce_damage,
                      'waves': len(self.wave_trace), 'external_charge': self.external_charge,
                      'feedback_charge': self.feedback_charge, 'consumed_charge': self.consumed_charge,
                      'expired_charge': self.expired_charge, 'remaining_charge': self.total_load(),
                      'maximum_pool_charge': self.max_charge, 'ready_requests': len(self.ready),
                      'broken_reservation_count': self.broken_reservation_count,
                      'all_waves_strictly_dissipative': all(q(row['charge_decrease']) >= 5 - self.feedback_budget
                                                          for row in self.wave_trace),
                      'all_waves_potency_dissipative': all(row['potency_decrease'] > 0 for row in self.wave_trace),
                      'geometry_scope': 'fixture-supplied legal graph; no map LOS or body navigation inference',
                      'bounce_distance_scope': 'explicit edge distances, or equal-distance stable-ID fixture if absent',
                      'wave_trace': self.wave_trace, 'bounce_trace': self.bounce_trace,
                      'reservation_trace': self.reservation_trace})


def complete_edges(nodes):
    nodes = list(nodes)
    return [(a, b) for i, a in enumerate(nodes) for b in nodes[i + 1:]]


def run_electric(pools, appliances, edges, inputs=(), initial=None, horizon=24,
                 base_d=2.5, powered=True, ward=0, ordinary_bounce=False,
                 feedback_budget=2, feedback_energy_factor=.75, edge_distances=None):
    """Replay paid emissions on a graph; no finite HP/death or movement AI.

    Old (time, pool, damage, charge) tuples remain valid and simultaneous tuples
    form one default source phase. Dictionaries may specify time, pool, damage,
    charge, source_id, phase_id, source_D and pure_charge. Optional fifth/sixth
    tuple fields specify source_id/phase_id. One ordinary arc is allowed per
    explicit source phase when ordinary_bounce=True.
    """
    model = ElectricModel(pools, appliances if powered else [], edges,
                          base_d=base_d, ward=ward, feedback_budget=feedback_budget,
                          feedback_energy_factor=feedback_energy_factor,
                          edge_distances=edge_distances)
    events = defaultdict(list)
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
        if time < q(horizon):
            events[time].append(event)
    for pool, amount in sorted((initial or {}).items()):
        model.add(pool, amount, 0)
    times = set(events)
    times.update(repeat_events(.25, [0], horizon))
    for time in sorted(times):
        model.expire(time)
        phases = defaultdict(list)
        for event in events.get(time, []):
            phases[(str(event['source_id']), str(event['phase_id']))].append(event)
        for phase, emissions in sorted(phases.items()):
            impacts = []
            for event in emissions:
                dealt = model.primary(event['pool'], time, event['damage'], event['charge'],
                                      source_d=event['source_D'], source_id=event['source_id'],
                                      pure_charge=event['pure_charge'])
                if dealt > 0:
                    impacts.append((event['pool'], event['source_D']))
            if ordinary_bounce and impacts:
                model.ordinary_bounce(impacts, time, phase)
        if time % F(1, 4) == 0:
            model.wave(time)
    model.expire(q(horizon))
    return model.summary()


def electric_reservation_fixture():
    """A reserved lot expires while newer overflow still leaves five units.

    Also covers earliest-expiry ordering for an older transferred deadline,
    a partial lot reservation, and unchanged surplus potency/expiry.
    """
    model = ElectricModel(['A', 'B'], [], [('A', 'B')])
    early = model.add('A', 2, 0, expires_at=1, lot_id='A-early')
    late = model.add('A', 3, 0, expires_at=8, lot_id='A-late')
    original_ready = dict(model.requests['A'])
    model.add('A', 4, F(1, 2), expires_at=F(17, 2), lot_id='A-overflow')
    model.add('B', 5, F(1, 2), lot_id='B-ready')
    model.expire(1)
    new_ready = dict(model.requests['A'])
    preserved_surplus = model.load('A')
    model.wave(1)
    first_seed_after_expiry = model.wave_trace[0]['seed']
    ordering = ElectricModel(['P'], [], [])
    ordering.add('P', 3, 0, expires_at=8, lot_id='newer-deadline')
    ordering.add('P', 4, F(1, 2), expires_at=2, applied_at=-6,
                 lot_id='inherited-earlier-deadline')
    chosen = list(ordering.requests['P']['reserved'])
    ordering.consume('P')
    return clean({'old_request_id': original_ready['request_id'],
                  'old_ready_at': original_ready['ready_at'],
                  'new_request_id': new_ready['request_id'],
                  'new_ready_at': new_ready['ready_at'],
                  'broken_reservations': model.broken_reservation_count,
                  'A_load_after_reserved_expiry': preserved_surplus,
                  'first_seed_after_expiry': first_seed_after_expiry,
                  'earliest_expiry_reserved_lots': chosen,
                  'post_consumption_surplus': ordering.load('P'),
                  'post_consumption_lots': ordering.loads['P'],
                  'old_reserved_lot_ids': [early, late]})


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
        metrics['fresh_full_corridor_damage'] = q(p['cell_damage']) * p['cell_count']
        metrics['phase_full_corridor_damage'] = q(p.get('phase_cell_damage', p.get('phase_audit_cell_damage', p['cell_damage']))) * p['cell_count']
        if 'landing_damage' in p:
            metrics['phase_corridor_with_one_valid_reserved_landing'] = metrics['phase_full_corridor_damage'] - q(p.get('phase_cell_damage', p['cell_damage'])) + q(p['landing_damage'])
        note = 'stationary-cell nominal ceiling before downtime; crossing/phase use dedicated traces'
    elif p.get('damage_on_actual_crossing_only'):
        amount = F(0)
        metrics['one_actual_crossing_damage'] = p['damage']
        note = 'stationary target does not cross curtain: zero; each eligible real crossing has its own event'
    elif 'guard_count' in p:
        amount = len(hit_schedule(node, horizon)) * q(p['damage']) * p['guard_count']
        metrics['team_hp'] = p['guard_hp_each'] * p['guard_count']
        metrics['team_ground_block_slots'] = p['guard_block_count_each'] * p['guard_count']
        if 'flank_bonus_damage' in p:
            metrics['damage_with_one_real_flanking_partner'] = amount + len(hit_schedule(node, horizon)) * p['flank_bonus_damage']
        if 'ranged_damage' in p:
            metrics['ranged_team_direct_damage'] = q(p['ranged_damage']) * p['guard_count'] * len(hit_schedule(node, horizon))
        note = 'all guards continuously alive and in melee range; survival/blocking are separate metrics'
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
