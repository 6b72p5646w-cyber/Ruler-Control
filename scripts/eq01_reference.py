#!/usr/bin/env python3
"""Bounded EQ01 ledger and timing references, not world/game implementation.

Geometry, actual rule receipts, attacks and handler admission are supplied by
the caller. No test receipt here establishes that a monster AI/map is complete.
"""
from copy import deepcopy
from dataclasses import dataclass, field
from fractions import Fraction as F


def q(x):
    return x if isinstance(x, F) else F(str(x))


TIERS = ('common', 'uncommon', 'rare')


def pity_weights(common, nonrare):
    if type(common) is not int or type(nonrare) is not int or not 0 <= common <= nonrare <= 9 or common > 4:
        raise ValueError('invalid persisted pity counters')
    if nonrare == 9:
        return (F(0), F(0), F(1))
    if common == 4:
        return (F(0), F(3, 4), F(1, 4))
    return (F(3, 5), F(3, 10), F(1, 10))


def next_pity(common, nonrare, tier):
    if tier == 'rare':
        return 0, 0
    if tier == 'uncommon':
        return 0, nonrare + 1
    if tier == 'common':
        return common + 1, nonrare + 1
    raise ValueError('unknown tier')


def weighted_candidates(catalog, owned, common, nonrare, admitted_ids):
    """50/50 classes within each eligible tier; owned gear stays in its pool.

    admitted_ids MUST be real adapter admission in production. Tests pass a
    clearly named design fixture set; absence of handlers does not enable it.
    """
    candidates = []
    for tier, tier_weight in zip(TIERS, pity_weights(common, nonrare)):
        if not tier_weight:
            continue
        for kind in ('equipment', 'consumable'):
            pool = [x for x in catalog if x['tier'] == tier and x['kind'] == kind
                    and x['id'] in admitted_ids]
            if not pool:
                raise ValueError('required tier/class pool is empty; no debit or downgrade')
            for item in pool:
                item = deepcopy(item)
                item['duplicate'] = kind == 'equipment' and item['id'] in owned
                item['effective_key'] = ('duplicate-choice:' + tier) if item['duplicate'] else item['id']
                candidates.append((item, tier_weight * F(1, 2) / len(pool)))
    assert sum(w for _, w in candidates) == 1
    return candidates


def sample_candidate(candidates, unit_roll):
    roll = q(unit_roll)
    if not 0 <= roll < 1:
        raise ValueError('roll must be in [0,1)')
    total = sum(weight for _, weight in candidates)
    if total <= 0:
        raise ValueError('no distinct candidate')
    threshold = roll * total
    cumulative = F(0)
    for item, weight in candidates:
        cumulative += weight
        if threshold < cumulative:
            return deepcopy(item)
    raise AssertionError('exact weighted selection failed')


@dataclass
class LotteryLedger:
    tickets: int
    preparation_minutes: int
    owned: set = field(default_factory=set)
    common: int = 0
    nonrare: int = 0
    item_units: dict = field(default_factory=dict)
    records: dict = field(default_factory=dict)
    phase: str = 'preparation'

    def prepare(self, draw_id, catalog, admitted_ids, rolls, double=False,
                double_authorized=False, procurement_window='window-1', pool_version='EQ01'):
        if draw_id in self.records:
            return deepcopy(self.records[draw_id])
        if self.phase != 'preparation' or self.tickets < 1 or self.preparation_minutes < 15:
            raise ValueError('draw is not currently payable/available')
        if any(x['state'] == 'reserved' for x in self.records.values()):
            raise ValueError('resolve existing persisted choice first')
        if double and (not double_authorized or any(x.get('double') and x.get('window') == procurement_window
                                                   for x in self.records.values())):
            raise ValueError('E064 requires its actual one-per-window authorization')
        if len(rolls) != (2 if double else 1):
            raise ValueError('wrong number of persisted random inputs')
        weights = weighted_candidates(catalog, self.owned, self.common, self.nonrare, admitted_ids)
        choices = [sample_candidate(weights, rolls[0])]
        if double:
            # Same pre-draw pity; remove duplicate ID AND equivalent duplicate
            # compensation option, then conditionally renormalize. Never reroll
            # a tier with a new pity state or show two identical compensation menus.
            remaining = [(x, w) for x, w in weights
                         if x['id'] != choices[0]['id'] and x['effective_key'] != choices[0]['effective_key']]
            choices.append(sample_candidate(remaining, rolls[1]))
        record = {'draw_id': draw_id, 'state': 'reserved', 'choices': choices,
                  'pity_before': [self.common, self.nonrare], 'owned_snapshot': sorted(self.owned),
                  'double': bool(double), 'window': procurement_window,
                  'pool_version': pool_version, 'paid_ticket': 1, 'paid_minutes': 15,
                  'compensation_options': {
                      tier: sorted(x['id'] for x in catalog if x['tier'] == tier and x['kind'] == 'consumable'
                                   and x['id'] in admitted_ids) for tier in TIERS}}
        # One atomic reservation, persisted BEFORE the UI reveals choices.
        self.tickets -= 1
        self.preparation_minutes -= 15
        self.records[draw_id] = record
        return deepcopy(record)

    def select(self, draw_id, index=0, compensation_id=None):
        record = self.records[draw_id]
        if record['state'] == 'committed':
            return deepcopy(record['receipt'])
        if self.phase != 'preparation' or not 0 <= index < len(record['choices']):
            raise ValueError('invalid selection')
        if [self.common, self.nonrare] != record['pity_before']:
            raise ValueError('pity mutated during reserved draw')
        if sorted(self.owned) != record['owned_snapshot']:
            raise ValueError('ownership changed during reserved draw')
        selected = record['choices'][index]
        tier = selected['tier']
        units = 2 if tier == 'common' else 1
        if selected['duplicate']:
            if compensation_id not in record['compensation_options'][tier]:
                raise ValueError('select an actual same-tier special reward; no reroll')
            reward_id, kind = compensation_id, 'consumable'
        else:
            reward_id, kind = selected['id'], selected['kind']
            if kind == 'equipment':
                units = 1
        if kind == 'equipment':
            self.owned.add(reward_id)
        else:
            self.item_units[reward_id] = self.item_units.get(reward_id, 0) + units
        self.common, self.nonrare = next_pity(self.common, self.nonrare, tier)
        receipt = {'draw_id': draw_id, 'original_item_id': selected['id'], 'original_tier': tier,
                   'reward_id': reward_id, 'kind': kind, 'units': units,
                   'duplicate_converted': selected['duplicate'], 'pity_after': [self.common, self.nonrare]}
        record['state'], record['receipt'] = 'committed', receipt
        return deepcopy(receipt)


PROFILES = {
    'baseline': (q(4.2), q(2), q(12), q(30)),
    'Q31': (q(4.5), q(2), q(18), q(32)),
    'Q32': (q(4.1), q(.9), F(40, 3), q(28)),
}


@dataclass
class Mobility:
    ready_at: F = F(0)
    second_deadline: F = F(0)
    second_available: bool = False
    active_remaining: F = F(0)
    active_profile: str = 'baseline'

    def start(self, now, stamina, profile='baseline', heavy=False, working=False,
              actual_nonzero_path=True, second=False):
        now, stamina = q(now), q(stamina)
        speed, duration, rate, cooldown = PROFILES[profile]
        if heavy or working or not actual_nonzero_path or self.active_remaining > 0 or stamina < rate / 4:
            raise ValueError('mobility start is not valid or funded')
        if second:
            if profile != 'Q32' or not self.second_available or not now < self.second_deadline:
                raise ValueError('no live second burst')
            self.second_available = False
        else:
            if now < self.ready_at:
                raise ValueError('shared mobility cooldown')
            self.ready_at = now + cooldown
            self.second_available = profile == 'Q32'
            self.second_deadline = now + 5 if profile == 'Q32' else now
        self.active_profile, self.active_remaining = profile, duration

    def move_segment(self, seconds, stamina):
        speed, _, rate, _ = PROFILES[self.active_profile]
        seconds, stamina = q(seconds), q(stamina)
        if seconds < 0 or stamina < 0:
            raise ValueError('negative time or stamina')
        actual = min(seconds, self.active_remaining, stamina / rate)
        self.active_remaining -= actual
        remaining_stamina = stamina - actual * rate
        if remaining_stamina == 0:
            self.active_remaining = F(0)
        return {'seconds': actual, 'distance': actual * speed, 'stamina': remaining_stamina}

    def stop(self):
        self.active_remaining = F(0)


def long_run_speed(walk, profile='baseline'):
    speed, duration, _, cooldown = PROFILES[profile]
    duration *= 2 if profile == 'Q32' else 1
    return (q(walk) * (cooldown - duration) + speed * duration) / cooldown


def advance_maturities(records, now, cast_id, committed_casts, maximum=4):
    """Q33 already-completed cast: advance paid q; never invent or delay it."""
    now = q(now)
    if cast_id in committed_casts:
        return 0
    eligible = sorted((r for r in records if not r.get('paid') and not r.get('eq01_advanced')
                       and q(r['due']) > now + F(1, 4)), key=lambda r: (q(r['due']), r['id']))[:maximum]
    for record in eligible:
        record['due'] = now + F(1, 4)
        record['eq01_advanced'] = True
    if eligible:
        committed_casts.add(cast_id)
    return len(eligible)


def poison_integral(load, start, end, catalyst_windows=(), suppressed_windows=()):
    """Raw damage only; exact segment integration before real defense/HP gates."""
    load, start, end = q(load), q(start), q(end)
    if load < 0 or end < start:
        raise ValueError('invalid poison segment')
    windows = [(q(a), q(b), min(q(2), q(v))) for a, b, v in catalyst_windows]
    suppression = [(q(a), q(b)) for a, b in suppressed_windows]
    boundaries = {start, end}
    for a, b, *_ in windows + suppression:
        boundaries.update(x for x in (a, b) if start < x < end)
    times = sorted(boundaries)
    total = F(0)
    for a, b in zip(times, times[1:]):
        if any(s <= a < e for s, e in suppression):
            continue
        multiplier = max([F(1)] + [v for s, e, v in windows if s <= a < e])
        total += load * F(1, 2) * (b-a) * multiplier
    return total


def electric_snapshot(pools, appliances, reach=None, pair_links=(), blocked_pairs=()):
    """Point-fixture graph reference, NOT shelf footprint geometry or queue time.

    Pools supplied here are already legal manifested/charged independent pools.
    Appliance IDs must be real registered powered fixtures. No AP-AP edges.
    """
    reach = reach or {}
    if set(appliances) - {'AP_HOT_FOOD','AP_FREEZER','AP_COLD_CABINET'}:
        raise ValueError('unregistered appliance fixture')
    blocked = {frozenset(x) for x in blocked_pairs}
    adjacency = {p: set() for p in pools}
    ap_adjacency = {a: set() for a in appliances}
    ids = sorted(pools)
    for i, a in enumerate(ids):
        for b in ids[i+1:]:
            radius = max(q(2.5), q(reach.get(a, 0)), q(reach.get(b, 0)),
                         max([q(0)] + [q(r) for x,y,r in pair_links if {x,y} == {a,b}]))
            distance2 = sum((q(x)-q(y))**2 for x,y in zip(pools[a], pools[b]))
            if frozenset((a,b)) not in blocked and distance2 <= radius**2:
                adjacency[a].add(b); adjacency[b].add(a)
        for ap, xy in appliances.items():
            distance2 = sum((q(x)-q(y))**2 for x,y in zip(pools[a], xy))
            if distance2 <= q(2.5)**2 and frozenset((a,ap)) not in blocked:
                ap_adjacency[ap].add(a)
    def connected(start):
        seen, work = set(), [start]
        while work:
            current = work.pop()
            if current in seen:
                continue
            seen.add(current)
            work.extend(adjacency[current] - seen)
            for members in ap_adjacency.values():
                if current in members:
                    work.extend(members-seen)
        return seen
    return {'pool_adjacency': adjacency, 'appliance_adjacency': ap_adjacency,
            'connected': {x: connected(x) for x in ids},
            'local_coefficients': {x: 1+len(adjacency[x])+sum(x in ps for ps in ap_adjacency.values()) for x in ids}}


def add_paid_parallel_charge(primary, legal_pool_ids):
    ids = set(legal_pool_ids)
    if primary not in ids:
        raise ValueError('invalid primary')
    return {x: 4 if x == primary else 1 for x in ids}


def admitted_extra_proc(event):
    return (event.get('origin') == 'native_primary' and event.get('actual_committed')
            and not event.get('duplicate') and event.get('legal_target'))


def native_electric_feedback(actual_hp_loss):
    return 1 if q(actual_hp_loss) > 0 else 0


def allowed_manifest(ordinary_slots, ordinary_other_units, special_units, specialized_bag=False):
    limit = 6 if specialized_bag else 4
    return (all(type(x) is int and x >= 0 for x in (ordinary_slots, ordinary_other_units, special_units))
            and special_units <= limit and ordinary_other_units+special_units <= ordinary_slots)


def progress_advance(remaining, base_work):
    if q(base_work) < F(3,2) or q(remaining) <= 0:
        return F(0)
    return min(q(remaining), q(base_work)/2)
