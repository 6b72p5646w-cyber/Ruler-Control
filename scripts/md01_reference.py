"""MD01 terminal-state reference, not a game runtime or map/AI simulator.

Uses explicit verified-rule receipts supplied by a fixture/adapter. It does not
discover a rule by itself, authenticate a user click, or implement SCP abilities.
ElectricGateFixture covers one fixed lawful graph and same-strength charge lots;
TD05 owns full queue/expiry/source-potency/geometry rules.
"""
from dataclasses import dataclass, field
from fractions import Fraction as F
from math import isfinite


def num(value):
    if isinstance(value, bool):
        raise ValueError('boolean is not a number')
    if isinstance(value, float) and not isfinite(value):
        raise ValueError('non-finite number')
    return value if isinstance(value, F) else F(str(value))


def clean(value):
    if isinstance(value, F):
        return value.numerator if value.denominator == 1 else float(value)
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [clean(v) for v in value]
    return value


@dataclass
class RewardLedger:
    entries: dict = field(default_factory=dict)
    rule_qualified_roots: set = field(default_factory=set)
    coins: int = 0
    spirit: int = 0

    def qualify_rule(self, root):
        if not root or root in self.entries:
            return False
        self.rule_qualified_roots.add(root)
        return True

    def settle(self, root, *, successful, rule_completed):
        if not root or not successful or root in self.entries:
            return {'coins': 0, 'spirit': 0, 'new': False}
        if rule_completed:
            self.qualify_rule(root)
        award = {'coins': 12, 'spirit': 4 + (2 if root in self.rule_qualified_roots else 0), 'new': True}
        self.entries[root] = dict(award)
        self.coins += award['coins']
        self.spirit += award['spirit']
        return award


class LifeState:
    """One necessary health pool, with root completion controlled by caller.

    Set auto_finish=False for a member of a multi-pool root; the adapter must
    resolve all required members/declared recall before finish_root().
    """
    def __init__(self, record, root='fixture:week1:night1:root1', ledger=None,
                 auto_finish=True):
        self.record = record
        self.root = root
        self.ledger = ledger if ledger is not None else RewardLedger()
        self.auto_finish = auto_finish
        self.hp_max = num(record['stats']['hp'])
        if self.hp_max < 0:
            raise ValueError('negative hp')
        self.hp = self.hp_max
        self.kind = record['resolution']['type']
        if self.kind not in ('kill_unlocked', 'rule_leave', 'rule_weaken'):
            raise ValueError('unknown resolution')
        self.rule_done = False
        self.state = 'active'
        self.now = F(0)
        self.recover_at = None
        self.poison = F(0)
        self.charge = 0
        self.rule_receipts = set()
        self.damage_receipts = set()
        self.trace = []
        self.root_finished = False
        self.terminal_reason = None

    @property
    def targetable(self):
        return self.hp_max > 0 and self.state == 'active'

    @property
    def floor(self):
        return F(1) if self.kind == 'rule_leave' or (self.kind == 'kill_unlocked' and not self.rule_done) else F(0)

    @property
    def parameters(self):
        return self.record['post_rule'] if self.rule_done else self.record['stats']

    def finish_root(self):
        if self.root_finished:
            return {'coins': 0, 'spirit': 0, 'new': False}
        self.root_finished = True
        return self.ledger.settle(self.root, successful=True, rule_completed=self.rule_done)

    def _terminal(self, state):
        self.state = state
        self.terminal_reason = 'true_combat_defeat' if state == 'defeated' else 'withdrawal'
        self.recover_at = None
        self.poison = F(0)
        self.charge = 0
        if self.auto_finish:
            self.finish_root()

    def complete_rule(self, receipt):
        """Receipt is issued by an external mechanism verifier, never a click."""
        valid = (isinstance(receipt, dict) and receipt.get('verified') is True
                 and receipt.get('root') == self.root and receipt.get('id'))
        if not valid or self.state in ('defeated', 'left') or self.rule_done or self.root in self.ledger.entries:
            return False
        if receipt['id'] in self.rule_receipts:
            return False
        self.rule_receipts.add(receipt['id'])
        self.rule_done = True
        self.ledger.qualify_rule(self.root)
        self.trace.append({'at': self.now, 'event': 'rule_completed', 'hp_preserved': self.hp})
        if self.kind == 'rule_leave':
            self._terminal('left')
        return True

    def apply_damage(self, raw, channel='physical', *, penetration=0,
                     vulnerability=0, electric_charge=0, receipt=None):
        raw, penetration, vulnerability = map(num, (raw, penetration, vulnerability))
        if raw < 0 or penetration < 0 or vulnerability < 0:
            raise ValueError('negative damage argument')
        if channel not in ('physical', 'spiritual'):
            raise ValueError('unknown channel')
        if not isinstance(electric_charge, int) or isinstance(electric_charge, bool) or electric_charge < 0:
            raise ValueError('invalid charge count')
        if receipt is not None:
            if receipt in self.damage_receipts:
                return F(0)
            self.damage_receipts.add(receipt)
        if not self.targetable:
            return F(0)
        defense = num(self.parameters['armor' if channel == 'physical' else 'ward'])
        defense = min(F(3, 4), max(F(0), defense - penetration))
        settled = raw * (1 - defense) * (1 + min(F(2, 5), vulnerability))
        loss = min(settled, max(F(0), self.hp - self.floor))
        before = self.hp
        self.hp -= loss
        if loss > 0 and electric_charge:
            self.charge += max(1, electric_charge)
        self.trace.append({'at': self.now, 'event': 'damage', 'raw': raw,
                           'settled': settled, 'actual_hp_loss': loss,
                           'blocked_or_overkill': settled - loss, 'hp': self.hp})
        if self.kind == 'rule_leave' and before > 1 and self.hp == 1:
            self.state = 'suppressed'
            self.recover_at = self.now + F(9, 2)
            self.trace.append({'at': self.now, 'event': 'suppressed', 'recover_at': self.recover_at})
        elif self.hp == 0:
            self._terminal('defeated')
        return loss

    def add_poison(self, amount):
        amount = num(amount)
        if amount <= 0 or not self.targetable:
            return False
        self.poison += amount
        return True

    def advance(self, seconds):
        """World clock only. No damage implied; real ticks are explicit calls."""
        seconds = num(seconds)
        if seconds < 0:
            raise ValueError('negative time')
        self.now += seconds
        if self.state == 'suppressed' and self.now >= self.recover_at:
            self.state = 'active'
            self.hp = max(F(1), self.hp_max / 4)
            self.trace.append({'at': self.recover_at, 'event': 'manifestation_reformed', 'hp': self.hp})
            self.recover_at = None

    def poison_tick(self, seconds=1):
        seconds = num(seconds)
        if seconds <= 0:
            raise ValueError('invalid poison tick')
        return self.apply_damage(self.poison * seconds / 2, 'spiritual') if self.targetable else F(0)


class EncounterGroup:
    """Required pools plus an explicit producer gate, not spawn/path AI."""
    def __init__(self, root, ledger=None):
        self.root = root
        self.ledger = ledger if ledger is not None else RewardLedger()
        self.pools = {}
        self.production_closed = False

    def add_pool(self, identity, record):
        if self.production_closed or self.root in self.ledger.entries or identity in self.pools:
            raise ValueError('closed producer or duplicate pool')
        state = LifeState(record, self.root, self.ledger, auto_finish=False)
        self.pools[identity] = state
        return state

    def close_production(self):
        # The real adapter must verify the species-specific stop/budget fact.
        self.production_closed = True

    def try_finish(self):
        if (not self.production_closed or not self.pools or
                any(s.state not in ('defeated', 'left') for s in self.pools.values())):
            return {'coins': 0, 'spirit': 0, 'new': False}
        return self.ledger.settle(self.root, successful=True, rule_completed=False)


class ElectricGateFixture:
    """A fixed graph fixture; counts all eligible charged pools, no feedback cap.

    This isolated terminal-boundary test has homogeneous D and no advancing
    clock. It deliberately does NOT claim to replace TD05's .25s FIFO, expiry,
    susceptible reservations, source-lot mixing, or dynamic map/LOS model.
    """
    def __init__(self, pools, appliance_ids=(), edges=(), d=6, threshold=5):
        self.pools = dict(pools)
        self.appliances = set(appliance_ids)
        self.edges = {frozenset(edge) for edge in edges}
        self.d = num(d)
        self.threshold = threshold
        self.waves = []
        self.feedback_total = 0

    def eligible(self):
        return {p for p, s in self.pools.items() if s.targetable and s.charge > 0}

    def adjacent(self, node, eligible):
        return {next(iter(edge - {node})) for edge in self.edges
                if node in edge and len(edge) == 2 and (edge - {node}) <= eligible}

    def wave(self, seed):
        charged = self.eligible()
        if seed not in charged or self.pools[seed].charge < self.threshold:
            return None
        legal = charged | self.appliances
        component, frontier = set(), {seed}
        while frontier:
            point = frontier.pop()
            if point in component:
                continue
            component.add(point)
            frontier |= self.adjacent(point, legal) - component
        recipients = sorted(component & charged)
        coefficients = {}
        for point in recipients:
            one_hop = self.adjacent(point, legal)
            coefficients[point] = 1 + len(one_hop & charged) + len(one_hop & self.appliances)
        self.pools[seed].charge -= self.threshold
        losses = {}
        # Snapshot coefficients/recipient membership above; no target cap.
        for point in recipients:
            losses[point] = self.pools[point].apply_damage(self.d * coefficients[point], 'spiritual')
        feedback = 0
        for point, loss in losses.items():
            if loss > 0:
                feedback += 1
                if self.pools[point].state not in ('defeated', 'left'):
                    self.pools[point].charge += 1
        self.feedback_total += feedback
        trace = clean({'seed': seed, 'coefficients': coefficients, 'losses': losses,
                       'feedback': feedback, 'remaining_charge': {p: s.charge for p, s in self.pools.items()}})
        self.waves.append(trace)
        return trace

    def drain(self, safety_iterations=10000):
        # Guard only for this diagnostic; never a gameplay charge/wave cap.
        for _ in range(safety_iterations):
            ready = sorted(p for p in self.eligible() if self.pools[p].charge >= self.threshold)
            if not ready:
                return self.waves
            self.wave(ready[0])
        raise AssertionError('fixture did not terminate within diagnostic guard')


def split_conserved(hp, poison, charge, weights, child_hp_floor=0):
    hp, poison, charge = map(num, (hp, poison, charge))
    weights = list(map(num, weights))
    if hp <= 0 or poison < 0 or charge < 0 or not weights or any(w <= 0 for w in weights):
        raise ValueError('invalid split input')
    total = sum(weights)
    result = [{'hp': hp*w/total, 'poison': poison*w/total, 'charge': charge*w/total} for w in weights]
    if num(child_hp_floor) < 0 or any(p['hp'] < num(child_hp_floor) for p in result):
        raise ValueError('split would place a child below its actual health floor')
    return result


@dataclass
class ShiftTicketLedger:
    tickets: int = 0
    awards: set = field(default_factory=set)
    pity_common: int = 0
    pity_nonrare: int = 0

    def complete_shift(self, campaign, week, night, *, handover_verified, practice=False, grade='C'):
        if grade not in ('A', 'B', 'C') or not 1 <= night <= 7 or not campaign or week < 1:
            raise ValueError('invalid shift identity')
        key = (campaign, week, night)
        if practice or not handover_verified or key in self.awards:
            return 0
        self.awards.add(key)
        self.tickets += 1
        return 1

    def week_clear(self):
        # Personal ticket ledger is not a TD05 tower/trap inventory.
        return self.tickets
