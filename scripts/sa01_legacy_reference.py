"""Finite SA01 legacy deployment boundaries, not a map/game implementation.

The caller supplies purchased identities and verified authored mount geometry.
This model tests the management boundary, intersecting capacities, same-item
conversion, finite activation lifetime and the two explicitly migrated hit guards.
It neither invents physical footprints nor implements all nine device effects.
"""
from dataclasses import dataclass, field
from fractions import Fraction as F


MANAGEMENT = {'buy', 'install', 'move', 'recover', 'pack', 'upgrade', 'refill',
              'reload', 'repair', 'replace', 'sell'}


def management_allowed(phase, action):
    return phase == 'pre_shift' and action in MANAGEMENT


def capacity_allowed(legacy_mounts, r_traps, floor_cells, barricade_cells=0):
    values = (legacy_mounts, r_traps, floor_cells, barricade_cells)
    return (all(type(x) is int and x >= 0 for x in values)
            and legacy_mounts <= 3 and legacy_mounts+r_traps <= 8
            and floor_cells <= 16 and barricade_cells <= 6
            and barricade_cells <= floor_cells)


def geometry_admitted(kind, cells, *, verified=False):
    if not verified or cells is None or kind not in ('floor', 'wall', 'table'):
        return False
    if any(not isinstance(c, (list, tuple)) or len(c) != 2
           or any(type(n) is not int for n in c) for c in cells):
        return False
    if len({tuple(c) for c in cells}) != len(cells):
        return False
    return bool(cells) if kind == 'floor' else len(cells) == 0


@dataclass
class TimedInstallation:
    instance_id: str
    definition_id: str
    week_id: str
    duration: F
    installed: bool = True
    activation_spent: bool = False
    started_at: F | None = None
    deadline: F | None = None
    active_night_id: str | None = None

    def activate(self, now, night_id, *, phase='open', target_valid=True):
        now = F(str(now))
        if (now < 0 or phase != 'open' or not target_valid or not self.installed
                or self.activation_spent or not night_id):
            return False
        self.started_at, self.deadline = now, now+F(str(self.duration))
        self.activation_spent, self.active_night_id = True, night_id
        return True

    def live(self, now, night_id):
        now = F(str(now))
        return (self.installed and self.deadline is not None
                and self.active_night_id == night_id
                and self.started_at <= now < self.deadline)

    def finish_night(self):
        self.active_night_id = None
        # Keep the spent budget and the original deadline for audit/save replay.


def install_i16(personal, defense, source_id, week_id, *, phase,
                geometry_valid, capacity_valid):
    source = personal.get(source_id)
    target_id = 'installed:'+source_id
    if (not management_allowed(phase, 'install') or not geometry_valid
            or not capacity_valid or source != 'I16'
            or target_id in defense or not week_id):
        return None
    device = TimedInstallation(target_id, 'I16', week_id, F(20))
    del personal[source_id]
    defense[target_id] = device
    return device


@dataclass
class PreparedLauncher:
    instance_id: str
    capacity: int = 3
    loaded: list = field(default_factory=list)
    spent_portions: set = field(default_factory=set)
    receipts: set = field(default_factory=set)
    installed: bool = True

    def load(self, phase, actual_fetched_inventory, portion_id, receipt):
        if (not management_allowed(phase, 'reload') or not receipt
                or receipt in self.receipts or portion_id not in actual_fetched_inventory
                or portion_id in self.spent_portions or portion_id in self.loaded
                or len(self.loaded) >= self.capacity):
            return False
        actual_fetched_inventory.remove(portion_id)
        self.loaded.append(portion_id)
        self.receipts.add(receipt)
        return True

    def fire(self, phase, receipt, *, real_point_and_path=True):
        if (phase != 'open' or not self.installed or not self.loaded
                or not real_point_and_path or not receipt or receipt in self.receipts):
            return None
        portion = self.loaded.pop(0)
        self.spent_portions.add(portion)
        self.receipts.add(receipt)
        return portion  # Consumer creates one original player_scatter bait.


@dataclass
class GuardPad:
    tier: int = 1
    charges: int = 1
    installed: bool = True
    broken: bool = False
    intercepted: set = field(default_factory=set)

    def intercept(self, now, attack_id, definition_id, *, committed=True,
                  geometry_hit=True, player_in_guard=True, curse_failed=False,
                  pending_positive_damage=True, grace_until=0):
        now, grace_until = F(str(now)), F(str(grace_until))
        if (definition_id not in ('F12:BASIC', 'F13:BASIC') or not attack_id
                or not committed or not geometry_hit or not player_in_guard
                or curse_failed or not pending_positive_damage or now < grace_until
                or not self.installed or self.broken or self.charges <= 0
                or attack_id in self.intercepted):
            return None
        if self.tier not in (1, 2):
            raise ValueError('unknown guard tier')
        self.charges -= 1
        self.broken = True
        self.intercepted.add(attack_id)
        return {'cancel_san_and_same_hit_injury': True, 'collision_recorded': True,
                'spatial_miss_reward': False, 'new_blood': False,
                'grace_until': max(grace_until, now+(3 if self.tier == 1 else 2))}
