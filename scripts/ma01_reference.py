#!/usr/bin/env python3
"""Finite MA01 attack references; NOT a world, complete AI or playtest.

The caller supplies verified hostility, actor/attack identities, actual path and
floor admission, and independent child identities.  The geometry fixtures below
cover straight 2-D segments/discs/opaque rectangles, not map navigation, height,
reflected beams, articulated ribbons, all 105 handlers or frame-rate validation.
Times/resources use exact fractions.  Euclidean collision calculations use
ordinary double precision with explicit boundary tolerance.
"""
from dataclasses import dataclass, field
from copy import deepcopy
from fractions import Fraction as F
from math import cos, sin, sqrt, hypot, isfinite, radians


def q(value):
    if isinstance(value, bool) or (isinstance(value, float) and not isfinite(value)):
        raise ValueError('expected a finite number')
    return value if isinstance(value, F) else F(str(value))


def clean(value):
    if isinstance(value, F):
        return value.numerator if value.denominator == 1 else float(value)
    if isinstance(value, dict):
        return {str(k): clean(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [clean(v) for v in value]
    return value


def point(value):
    if len(value) != 2 or not all(isfinite(float(x)) for x in value):
        raise ValueError('expected a finite 2-D point')
    return (float(value[0]), float(value[1]))


def swept_discs_time(a0, a1, b0, b1, radius_a=.25, radius_b=.35):
    """First contact fraction on simultaneous linear segments, or None.

    This checks relative swept motion instead of comparing only the last frame;
    it must never be used on the virtual midpoint path of a true teleport.
    """
    a0, a1, b0, b1 = map(point, (a0, a1, b0, b1))
    if radius_a < 0 or radius_b < 0:
        raise ValueError('negative collision radius')
    sx, sy = a0[0] - b0[0], a0[1] - b0[1]
    dx = (a1[0] - a0[0]) - (b1[0] - b0[0])
    dy = (a1[1] - a0[1]) - (b1[1] - b0[1])
    rr = radius_a + radius_b
    c = sx * sx + sy * sy - rr * rr
    if c <= 1e-12:
        return 0.0
    aa, bb = dx * dx + dy * dy, 2 * (sx * dx + sy * dy)
    if aa <= 1e-24:
        return None
    disc = bb * bb - 4 * aa * c
    if disc < -1e-12:
        return None
    t = (-bb - sqrt(max(0, disc))) / (2 * aa)
    return max(0.0, min(1.0, t)) if -1e-12 <= t <= 1 + 1e-12 else None


def segment_rectangle_entry(start, end, rectangle, radius=0):
    """First entry into a solid AABB expanded by a circular sweep radius."""
    start, end = point(start), point(end)
    x0, y0, x1, y1 = map(float, rectangle)
    if x0 > x1 or y0 > y1 or radius < 0:
        raise ValueError('invalid rectangle/radius')
    low, high = (x0-radius, y0-radius), (x1+radius, y1+radius)
    entry, leave = 0.0, 1.0
    for axis in (0, 1):
        delta = end[axis] - start[axis]
        if abs(delta) < 1e-12:
            if not low[axis] <= start[axis] <= high[axis]:
                return None
            continue
        u, v = (low[axis]-start[axis])/delta, (high[axis]-start[axis])/delta
        entry, leave = max(entry, min(u, v)), min(leave, max(u, v))
        if entry > leave + 1e-12:
            return None
    return entry if 0 <= entry <= 1 and leave >= 0 else None


def clipped_segment(start, end, blockers, radius=0):
    start, end = point(start), point(end)
    entries = [t for r in blockers
               if (t := segment_rectangle_entry(start, end, r, radius)) is not None]
    t = min(entries, default=1.0)
    return (start[0]+t*(end[0]-start[0]), start[1]+t*(end[1]-start[1])), t


def fixed_beam_hits(origin, direction, length, width, target, blockers=(), player_radius=.25):
    origin, direction, target = map(point, (origin, direction, target))
    norm = hypot(*direction)
    if norm == 0 or length < 0 or width < 0:
        raise ValueError('invalid beam')
    end = (origin[0]+length*direction[0]/norm, origin[1]+length*direction[1]/norm)
    end, _ = clipped_segment(origin, end, blockers, width/2)
    return swept_discs_time(origin, end, target, target, width/2, player_radius) is not None


def preset_sweep_direction(start_degrees, arc_degrees, elapsed, duration, clockwise=False):
    if duration <= 0 or not 0 <= elapsed <= duration or not 0 <= arc_degrees <= 180:
        raise ValueError('invalid visible sweep')
    angle = radians(start_degrees + (-1 if clockwise else 1)*arc_degrees*elapsed/duration)
    return (cos(angle), sin(angle))


@dataclass
class AttackTimeline:
    attack_id: str
    start: F
    windup: F
    active: F
    recovery: F
    cooldown: F
    requires_live_channel: bool = False
    autonomous_projectile: bool = False
    independent_payload: bool = False
    action_active: F | None = None
    state: str = 'preparing'
    extension: F = F(0)
    extension_sources: set = field(default_factory=set)
    committed_at: F | None = None
    closed_at: F | None = None
    curse_draws: int = 0
    canceled_reason: str | None = None

    def __post_init__(self):
        for key in ('start', 'windup', 'active', 'recovery', 'cooldown', 'extension'):
            setattr(self, key, q(getattr(self, key)))
        self.independent_payload |= self.autonomous_projectile
        self.action_active = self.active if self.action_active is None else q(self.action_active)
        if not self.attack_id or self.windup < F(3,2) or min(self.active,self.recovery,self.cooldown) < 0:
            raise ValueError('invalid attack timeline')
        if not 0 <= self.action_active <= self.active:
            raise ValueError('invalid action-active interval')
        if self.requires_live_channel and self.independent_payload:
            raise ValueError('a payload cannot be both a live channel and autonomous')

    @property
    def deadline(self):
        return self.start+self.windup+self.extension

    @property
    def active_end(self):
        return None if self.committed_at is None else self.committed_at+self.active

    @property
    def action_ready_at(self):
        """Source recovery may finish before its independent residual expires."""
        if self.committed_at is None:
            return None
        return self.committed_at+self.action_active+self.recovery

    def extend(self, now, source='I37', seconds=1):
        now, seconds = q(now), q(seconds)
        if self.state != 'preparing' or now < self.start or now >= self.deadline or source in self.extension_sources or seconds <= 0:
            return F(0)
        amount = min(seconds, F(3)-self.extension)
        if amount <= 0:
            return F(0)
        self.extension += amount
        self.extension_sources.add(source)
        return amount

    def commit(self, now, *, curse_failure=False):
        now = q(now)
        if self.state != 'preparing' or now < self.deadline:
            return False
        self.committed_at = now
        self.curse_draws += 1
        if curse_failure:
            self.state, self.closed_at, self.canceled_reason = 'canceled', now, 'curse_failure'
            return False
        self.state = 'active'
        return True

    def interrupt(self, now, kind):
        now = q(now)
        if now < self.start:
            return False
        if kind == 'root':
            return False
        if kind not in ('freeze','stun','registered_seal','source_pool_terminal','terminal'):
            raise ValueError('unknown interruption')
        if self.state not in ('preparing','active'):
            return False
        # Terminal resolution revokes this encounter's hazardous payloads.
        # Nonterminal controls cannot pull back an already-launched projectile.
        if self.state == 'active' and kind != 'terminal' and not self.requires_live_channel:
            return False
        self.state, self.closed_at, self.canceled_reason = 'canceled', now, kind
        return True

    def complete(self, now):
        now = q(now)
        if self.state != 'active' or now < self.active_end:
            return False
        self.state, self.closed_at = 'complete', now
        return True

    @property
    def next_start(self):
        if self.canceled_reason == 'terminal':
            return None
        if self.independent_payload and self.committed_at is not None and not self.canceled_reason:
            return max(self.start+self.cooldown,self.action_ready_at)
        if self.closed_at is None:
            return None
        return max(self.start+self.cooldown, self.closed_at+self.recovery)


@dataclass
class WholeAttack:
    attack_id: str
    expected_parts: set
    player_in_locked_geometry: bool = True
    committed: bool = True
    resolved_parts: set = field(default_factory=set)
    collided: bool = False
    moved_position: bool = False
    canceled_reason: str | None = None
    receipt_taken: bool = False

    def resolve_part(self, part, *, collision=False, player_moved=False):
        if part not in self.expected_parts:
            raise ValueError('unregistered subordinate hit')
        if part in self.resolved_parts:
            return False
        self.resolved_parts.add(part)
        self.collided |= bool(collision)
        self.moved_position |= bool(player_moved)
        return True

    def take_spatial_miss(self, now, buff_expires, *, attacker_legal=True,
                          attacker_visible=True, attacker_distance=4):
        eligible = (self.attack_id and self.expected_parts and self.committed
                    and not self.canceled_reason and not self.collided
                    and self.player_in_locked_geometry and self.moved_position
                    and self.resolved_parts == self.expected_parts
                    and not self.receipt_taken and q(now) < q(buff_expires)
                    and attacker_legal and attacker_visible and 0 <= attacker_distance <= 4)
        if not eligible:
            return False
        self.receipt_taken = True
        return True


@dataclass
class PlayerHits:
    san: F = F(100)
    grace_until: F = F(0)
    damaged_attack_ids: set = field(default_factory=set)
    collided_attack_ids: set = field(default_factory=set)

    def attempt(self, now, attack_id, san_damage, *, collision=True, legal=True,
                mitigation=0, requests_tether=False):
        now, damage, mitigation = q(now), q(san_damage), q(mitigation)
        if damage < 0 or not 0 <= mitigation <= 1 or not attack_id:
            raise ValueError('invalid damage packet')
        result = {'accepted':False,'san_loss':F(0),'tether_allowed':False,'collision':False}
        if not legal or not collision:
            return result
        self.collided_attack_ids.add(attack_id)
        result['collision'] = True
        if now < self.grace_until or attack_id in self.damaged_attack_ids or damage == 0:
            return result
        amount = min(q(self.san), damage*(1-mitigation))
        self.san -= amount
        self.grace_until = now+2
        self.damaged_attack_ids.add(attack_id)
        result.update(accepted=True,san_loss=amount,tether_allowed=bool(requests_tether))
        return result


@dataclass
class AttackReservations:
    active: dict = field(default_factory=dict)

    def reserve(self, attack_id, actor_id, family, *, player_bound=False,
                complete_route_verified=True, native_move_recovering=False,
                has_independent_residual=False):
        if (attack_id in self.active or len(self.active) >= 2 or player_bound
                or not complete_route_verified or native_move_recovering
                or any(v['actor']==actor_id and v['owns_actor_action'] for v in self.active.values())):
            return False
        high_pressure = family in ('RITUAL','TETHER')
        if high_pressure and any(v['high_pressure'] for v in self.active.values()):
            return False
        self.active[attack_id] = {'actor':actor_id,'family':family,'high_pressure':high_pressure,
                                 'owns_actor_action':True,
                                 'has_independent_residual':bool(has_independent_residual)}
        return True

    def detach_actor(self, attack_id, now, actual_action_recovery_at):
        """Release only the recovered source action, retain its danger slot.

        The recovery timestamp comes from the actual action timeline.  A live
        channel/embodied hitbox cannot be relabelled as an autonomous residual.
        """
        entry=self.active.get(attack_id)
        if (entry is None or not entry['has_independent_residual']
                or not entry['owns_actor_action'] or actual_action_recovery_at is None
                or q(now) < q(actual_action_recovery_at)):
            return False
        entry['owns_actor_action']=False
        return True

    def reserve_many(self, requests, **common_conditions):
        """Atomic pair/compound reservation: no half-launched synchronized pair."""
        shadow=AttackReservations(deepcopy(self.active))
        if not requests:
            return False
        for request in requests:
            parameters=dict(common_conditions)
            parameters.update(request)
            if not shadow.reserve(**parameters):
                return False
        self.active=shadow.active
        return True

    def release(self, attack_id):
        return self.active.pop(attack_id, None) is not None


def ritual_route_budget(walk_segments, flight_distance, *, stone_held=False,
                        hand_preparation=False, actual_stone_available=True,
                        path_valid=True, firing_los_valid=True, mobile_body=True):
    """Time budget for a route already validated by a map/action adapter.

    Each segment is (actual_distance, actual_walk_speed), including carried or
    slowed segments.  A hand preparation is the one required .25s put-down or
    holster; simultaneous hand operations must be represented by the adapter.
    This function does not discover a route or prove that other attacks permit it.
    """
    if not all((actual_stone_available,path_valid,firing_los_valid,mobile_body)):
        return {'eligible':False,'required_seconds':None,'channel_seconds':None}
    distance = q(flight_distance)
    if not 0 < distance <= 6:
        return {'eligible':False,'required_seconds':None,'channel_seconds':None}
    travel = F(0)
    for length, speed in walk_segments:
        length, speed = q(length), q(speed)
        if length < 0 or speed <= 0:
            raise ValueError('invalid admitted route segment')
        travel += length/speed
    needed = F(3,4)+F(1,2)+F(7,20)+distance/10+travel
    if not stone_held:
        needed += F(9,20)
    if hand_preparation:
        needed += F(1,4)
    return {'eligible':needed <= 8,'required_seconds':needed,
            'channel_seconds':max(F(6),needed) if needed <= 8 else None}


@dataclass
class RitualCycle:
    ritual_id: str
    mode: str = 'chase'
    started_at: F | None = None
    pulse_at: F | None = None
    cooldown_until: F = F(0)
    recovery_until: F = F(0)
    forced_chase_until: F = F(0)
    pulses: int = 0
    interruption_receipts: set = field(default_factory=set)
    extension_total: F = F(0)
    extension_sources: set = field(default_factory=set)
    attempt_number: int = 0

    def begin(self, now, duration=6, *, admitted=True, mobile_body=True):
        now, duration = q(now), q(duration)
        if (not admitted or not mobile_body or not 6 <= duration <= 8
                or self.mode in ('chanting','terminal')
                or now < max(self.cooldown_until,self.recovery_until,self.forced_chase_until)):
            return False
        self.mode, self.started_at, self.pulse_at = 'chanting', now, now+duration
        self.cooldown_until = now+16
        self.extension_total, self.extension_sources = F(0), set()
        self.attempt_number += 1
        return True

    def extend(self, now, source='I37', seconds=1):
        now, seconds = q(now), q(seconds)
        if (self.mode != 'chanting' or now < self.started_at or now >= self.pulse_at
                or source in self.extension_sources or seconds <= 0):
            return F(0)
        amount=min(seconds,F(3)-self.extension_total)
        if amount <= 0:
            return F(0)
        self.extension_total += amount
        self.extension_sources.add(source)
        self.pulse_at += amount
        return amount

    def interrupt(self, now, kind, *, receipt, actual_focus_hit=False,
                  existing_sealable=False, control_until=None):
        now = q(now)
        if (self.mode != 'chanting' or now < self.started_at or now > self.pulse_at
                or not receipt or receipt in self.interruption_receipts):
            return False
        if kind == 'root':
            return False
        if kind == 'stone' and not actual_focus_hit:
            return False
        if kind == 'seal' and not existing_sealable:
            return False
        if kind not in ('stone','freeze','stun','seal'):
            return False
        self.interruption_receipts.add(receipt)
        self.mode = 'interrupted'
        self.recovery_until = max(now+F(4,5),q(control_until) if control_until is not None else now)
        self.forced_chase_until = self.recovery_until+8
        return True

    def commit_pulse(self, now, *, curse_failure=False):
        now = q(now)
        if self.mode != 'chanting' or now < self.pulse_at:
            return False
        # Caller dispatches verified same-timestamp stone/control contacts first.
        self.mode = 'recovery'
        self.recovery_until = now+3
        if curse_failure:
            return False
        self.pulses += 1
        return True

    def resolve_timestamp(self, now, *, stone_contacts=(), control=None,
                          control_until=None, curse_failure=False):
        """Verified contacts/control precede the not-yet-committed same-time pulse."""
        interrupted = False
        for receipt, focus_hit in stone_contacts:
            interrupted |= self.interrupt(now,'stone',receipt=receipt,actual_focus_hit=focus_hit)
        if control is not None:
            interrupted |= self.interrupt(now,control,receipt='control:'+str(q(now))+':'+control,
                                          control_until=control_until)
        pulse = self.commit_pulse(now,curse_failure=curse_failure)
        return {'interrupted':bool(interrupted),'pulse':pulse}

    def state_at(self, now):
        now = q(now)
        if self.mode in ('chanting','terminal'):
            return self.mode
        return 'recovery' if now < self.recovery_until else 'chase'

    def terminate(self):
        self.mode = 'terminal'


class StoneLedger:
    """Three preplaced physical stones, one mission-carry slot, no spawner."""
    def __init__(self, positions):
        if len(positions) != 3:
            raise ValueError('the fixture must preplace exactly three stone IDs')
        self.stones = {key:{'state':'ground','position':point(pos)} for key,pos in positions.items()}
        self.held = None
        self.pending = None

    def begin_pickup(self, stone_id, now, player_pos, *, free_hands=1, heavy=False):
        stone = self.stones.get(stone_id)
        if (not stone or self.pending or self.held or stone['state'] != 'ground'
                or free_hands < 1 or heavy or hypot(*(a-b for a,b in zip(point(player_pos),stone['position']))) > .8+1e-12):
            return False
        self.pending = {'kind':'pickup','stone_id':stone_id,'due':q(now)+F(9,20)}
        return True

    def finish_pickup(self, now, player_pos, *, free_hands=1, heavy=False):
        if not self.pending or self.pending['kind'] != 'pickup' or q(now) < self.pending['due']:
            return False
        stone_id, self.pending = self.pending['stone_id'], None
        stone = self.stones[stone_id]
        if (self.held or stone['state'] != 'ground' or free_hands < 1 or heavy
                or hypot(*(a-b for a,b in zip(point(player_pos),stone['position']))) > .8+1e-12):
            return False
        stone['state'], self.held = 'held', stone_id
        return True

    def begin_throw(self, now, origin, aimed_point, *, can_use_stone_hand=True, heavy=False):
        origin, aimed_point = point(origin), point(aimed_point)
        length = hypot(*(a-b for a,b in zip(origin,aimed_point)))
        if self.pending or self.held is None or heavy or not can_use_stone_hand or not 0 < length <= 6:
            return False
        self.pending = {'kind':'throw','stone_id':self.held,'origin':origin,'end':aimed_point,
                        'due':q(now)+F(7,20)}
        return True

    def finish_throw(self, now, player_pos, *, can_use_stone_hand=True, heavy=False):
        if not self.pending or self.pending['kind'] != 'throw' or q(now) < self.pending['due']:
            return False
        action, self.pending = self.pending, None
        if (self.held != action['stone_id'] or heavy or not can_use_stone_hand
                or point(player_pos) != action['origin']):
            return False
        stone = self.stones[self.held]
        stone.update(state='flying',origin=action['origin'],end=action['end'],launched_at=q(now))
        self.held = None
        return True

    def resolve_flight(self, stone_id, blockers=(), *, focus=None, ritual=None,
                       verified_floor=True):
        stone = self.stones[stone_id]
        if stone['state'] != 'flying':
            return None
        if not verified_floor:
            raise ValueError('map adapter must supply an actual reachable landing; no teleport or respawn')
        origin, end = stone['origin'], stone['end']
        wall_end, wall_t = clipped_segment(origin,end,blockers,.1)
        focus_t = None if focus is None else swept_discs_time(origin,end,focus,focus,.1,.35)
        # A wall at the same boundary blocks the focus; no through-wall interrupt.
        any_wall = any(segment_rectangle_entry(origin,end,r,.1) is not None for r in blockers)
        focus_hit = focus_t is not None and (not any_wall or focus_t < wall_t-1e-12)
        t = focus_t if focus_hit else wall_t
        impact = (origin[0]+t*(end[0]-origin[0]),origin[1]+t*(end[1]-origin[1]))
        # Fraction from deterministic fixture output; world implementation supplies
        # its physical contact timestamp, not this 2-D numerical approximation.
        impact_at = stone['launched_at']+q(hypot(*(a-b for a,b in zip(origin,impact)))/10)
        interrupted = bool(focus_hit and ritual is not None and ritual.interrupt(
            impact_at,'stone',receipt=stone_id+':'+str(stone['launched_at']),actual_focus_hit=True))
        stone.update(state='ground',position=impact)
        for key in ('origin','end','launched_at'):
            stone.pop(key,None)
        return {'stone_id':stone_id,'focus_hit':focus_hit,'interrupted':interrupted,
                'impact_at':impact_at,'position':impact,'monster_hp_damage':0}


@dataclass
class TetherEpisode:
    max_length_tiles: F = F(4)
    source: str | None = None
    started_at: F | None = None
    root_until: F = F(0)
    release_at: F = F(0)
    immune_until: F = F(0)
    los_broken_since: F | None = None
    struggle_due: F | None = None
    last_release_reason: str | None = None

    def __post_init__(self):
        self.max_length_tiles=q(self.max_length_tiles)
        if not 0 < self.max_length_tiles <= 4:
            raise ValueError('tether must use its actual declared maximum, at most four tiles')

    def bind(self, now, source, *, accepted_hit):
        now = q(now)
        if not accepted_hit or not source or self.source is not None or now < self.immune_until:
            return False
        self.source, self.started_at = source, now
        self.root_until, self.release_at = now+F(3,5), now+2
        self.los_broken_since, self.struggle_due = None, None
        return True

    def struggle(self, now):
        if self.source is None or self.struggle_due is not None or q(now) < self.started_at:
            return False
        self.struggle_due = q(now)+F(3,5)
        return True

    def release(self, now, reason):
        if self.source is None:
            return False
        self.source = None
        self.immune_until = q(now)+6
        self.los_broken_since, self.struggle_due = None, None
        self.last_release_reason = reason
        return True

    def tick(self, now, *, los_clear=True, distance=4, source_active=True, source_frozen=False):
        now = q(now)
        if self.source is None:
            return None
        deadlines = [(self.release_at,'timeout')]
        if self.struggle_due is not None:
            deadlines.append((self.struggle_due,'struggle'))
        if not source_active or source_frozen or q(distance) > self.max_length_tiles:
            deadlines.append((now,'source_invalid' if not source_active else 'freeze' if source_frozen else 'overlength'))
        if self.los_broken_since is not None and now >= self.los_broken_since+F(1,5):
            deadlines.append((self.los_broken_since+F(1,5),'occlusion'))
        if los_clear:
            self.los_broken_since = None
        elif self.los_broken_since is None:
            self.los_broken_since = now
        if self.los_broken_since is not None:
            deadlines.append((self.los_broken_since+F(1,5),'occlusion'))
        due, reason = min(deadlines,key=lambda x:x[0])
        if due <= now:
            self.release(due,reason)
            return reason
        return None

    def movement_multiplier(self, now):
        now = q(now)
        if self.source is None or now >= self.release_at:
            return F(1)
        return F(0) if now < self.root_until else F(13,20)

