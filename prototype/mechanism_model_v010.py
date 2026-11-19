"""Finite design-contract interpreter, not a moving-enemy or client implementation.

The fixtures and four-neighbour routes come from the authored store map.  A trace
must execute guarded, timed operations on finite object/state values; reaching an
encounter's arrival fact is deliberately not treated as completing it.
"""
from __future__ import annotations

from collections import deque
from copy import deepcopy
from dataclasses import dataclass, field
from math import floor, isfinite, hypot

EPS = 1e-8
RESOURCE_BOUNDS = {"san": (0, 100), "energy": (0, 100), "satiety": (0, 100)}


def predicate(state, condition):
    key, op, value = condition["key"], condition["op"], condition["value"]
    if key not in state:
        return False
    current = state[key]
    if op == "eq":
        return current == value
    if op == "ne":
        return current != value
    if op == "ge":
        return isinstance(current, (int, float)) and current + EPS >= value
    if op == "le":
        return isinstance(current, (int, float)) and current <= value + EPS
    raise ValueError(f"Unknown predicate operator {op}")


def all_of(state, conditions):
    return all(predicate(state, condition) for condition in conditions)


def clock_condition(trace, condition):
    value=trace.world if condition['clock']=='world' else trace.budget
    target=condition['value'];op=condition['op']
    if op=='lt':return value<target-EPS
    if op=='gt':return value>target+EPS
    if op=='eq':return abs(value-target)<=EPS
    if op=='ne':return abs(value-target)>EPS
    if op=='le':return value<=target+EPS
    if op=='ge':return value+EPS>=target
    raise ValueError('Unknown clock predicate '+op)


def mutate(state, effect):
    """Atomic effects; insufficient inventory never consumes a partial amount."""
    for key, quantity in effect.get("consumes", {}).items():
        if quantity < 0 or key not in state or state[key] + EPS < quantity:
            raise ValueError(f"Insufficient or invalid consume {key}: {quantity}")
    out = deepcopy(state)
    for key, value in effect.get("sets", {}).items():
        out[key] = deepcopy(value)
    for key, quantity in effect.get("consumes", {}).items():
        out[key] -= quantity
    for key, amount in effect.get("adds", {}).items():
        out[key] += amount
        if key in RESOURCE_BOUNDS:
            low, high = RESOURCE_BOUNDS[key]
            out[key] = min(high, max(low, out[key]))
    return out


def rect_cells(rect):
    x, y, width, height = rect
    return {(i, j) for i in range(x, x + width) for j in range(y, y + height)}


def tile(position):
    return tuple(floor(v) for v in position)


def segments_intersect(a, b, c, d):
    def cross(p,q,r):return (q[0]-p[0])*(r[1]-p[1])-(q[1]-p[1])*(r[0]-p[0])
    def on(p,q,r):return min(p[0],q[0])-EPS<=r[0]<=max(p[0],q[0])+EPS and min(p[1],q[1])-EPS<=r[1]<=max(p[1],q[1])+EPS
    x,y,u,v=cross(a,b,c),cross(a,b,d),cross(c,d,a),cross(c,d,b)
    return ((x*y < -EPS and u*v < -EPS) or
            (abs(x)<=EPS and on(a,b,c)) or (abs(y)<=EPS and on(a,b,d)) or
            (abs(u)<=EPS and on(c,d,a)) or (abs(v)<=EPS and on(c,d,b)))


def facing_geometry(state, contract, scene):
    p=tuple(state[k] for k in contract['player_position_keys'])
    e=tuple(state[k] for k in contract['entity_position_keys'])
    blocked=False
    if state[contract['curtain_closed_key']]:
        blocked=segments_intersect(p,e,*contract['curtain_segment'])
    if contract.get('use_map_fixture_blocks_rule_sight'):
        for obj in scene['walls']+scene['fixtures']:
            if obj in scene['fixtures'] and not obj.get('blocks_rule_sight',False):continue
            x,y,w,h=obj['rect'];corners=[(x,y),(x+w,y),(x+w,y+h),(x,y+h)]
            if any(segments_intersect(p,e,a,b) for a,b in zip(corners,corners[1:]+corners[:1])):
                blocked=True;break
    dx,dy=e[0]-p[0],e[1]-p[1];distance=hypot(dx,dy)
    direct=False
    if state[contract['entity_present_key']] and not blocked and EPS<distance<=contract['maximum_distance_tiles']+EPS:
        pf=contract['face_vectors'][state[contract['player_facing_key']]]
        ef=contract['face_vectors'][state[contract['entity_facing_key']]]
        direct=(pf[0]*dx+pf[1]*dy)/distance+EPS>=contract['minimum_dot'] and (-ef[0]*dx-ef[1]*dy)/distance+EPS>=contract['minimum_dot']
    return {contract['derived_line_blocked_key']:blocked,contract['derived_direct_gaze_key']:direct}


class MapRoutes:
    def __init__(self, scene):
        self.scene = scene
        self.anchors = {a["role"]: a["position"] for a in scene["anchors"]}
        self.walkable = set().union(*(rect_cells(x["rect"]) for x in scene["walk_surfaces"]))
        for obstacle in scene["walls"] + scene["fixtures"]:
            if obstacle.get("blocks_navigation", True):
                self.walkable -= rect_cells(obstacle["rect"])
        self.cache = {}

    def point(self, action):
        if action.get("anchor") not in self.anchors:
            raise ValueError(f"Unknown anchor {action.get('anchor')}")
        return action.get("position", self.anchors[action["anchor"]])

    def distance(self, start, finish, closed=()):
        start, finish = tile(start), tile(finish)
        cache_key = (start, finish, tuple(sorted(closed)))
        if cache_key in self.cache:
            return self.cache[cache_key]
        walkable = self.walkable.copy()
        for door in self.scene["doors"]:
            if door["id"] in closed:
                walkable -= rect_cells(door["rect"])
        if start not in walkable or finish not in walkable:
            raise ValueError(f"Control position is blocked: {start} -> {finish}")
        queue, seen = deque([(start, 0)]), {start}
        while queue:
            node, steps = queue.popleft()
            if node == finish:
                self.cache[cache_key] = steps
                return steps
            for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                other = (node[0] + dx, node[1] + dy)
                if other in walkable and other not in seen:
                    seen.add(other)
                    queue.append((other, steps + 1))
        raise ValueError(f"Unreachable control: {start} -> {finish}, closed={closed}")


@dataclass
class Trace:
    state: dict
    position: list
    world: float = 0
    budget: float = 0
    travel: float = 0
    records: list = field(default_factory=list)
    fired_deadline: bool = False
    closed: bool = False
    timers: dict = field(default_factory=dict)
    timer_events: list = field(default_factory=list)
    expiry_status: str | None = None
    phase_start_budget: float = 0
    phase_start_world: float = 0
    dawn_budget: float = 720


class ContractModel:
    def __init__(self, case, routes):
        self.case, self.routes = case, routes
        self.actions = {action["id"]: action for action in case["actions"]}

    def begin(self, scenario=None):
        scenario = scenario or {}
        state = deepcopy(self.case["initial_state"])
        state.update(deepcopy(scenario.get("initial_overrides", {})))
        position = scenario.get('start_position', self.case.get('start_position', self.routes.anchors[self.case['start_anchor']]))
        geometry=self.case.get('geometry_contract')
        if geometry:
            position=[state[k] for k in geometry['player_position_keys']]
            state.update(facing_geometry(state,geometry,self.routes.scene))
        trace = Trace(state=state, position=deepcopy(position),
                      world=scenario.get('world', 0), budget=scenario.get('budget', 0),
                      phase_start_budget=scenario.get('phase_start_budget', 0),
                      phase_start_world=scenario.get('phase_start_world', 0),
                      dawn_budget=scenario.get('dawn_budget', 720))
        for timer in self._timer_definitions():
            if timer.get('start_on_begin') and all_of(state, timer.get('begin_when', [])):
                clock = trace.world if timer.get('clock', 'world') == 'world' else trace.budget
                trace.timers[timer['id']] = clock + state.get(timer.get('remaining_key'), timer['seconds'])
        return trace

    def _derive_geometry(self, trace):
        contract=self.case.get('geometry_contract')
        if contract:
            for key,value in zip(contract['player_position_keys'],trace.position):trace.state[key]=value
            trace.state.update(facing_geometry(trace.state,contract,self.routes.scene))

    def terminal(self, trace):
        if trace.fired_deadline:
            return trace.expiry_status or self.case["deadline"]["terminal_status"]
        if all_of(trace.state, self.case.get("success_when", [])) and self.case.get("success_when"):
            return "resolved"
        if any(all_of(trace.state, group) for group in self.case.get("success_any", [])):
            return "resolved"
        for terminal in self.case.get("alternate_terminals", []):
            if all_of(trace.state, terminal["when"]):
                return terminal["status"]
        return "active"

    def can_start(self, trace, action):
        if (trace.closed and action.get('reward_scope') is not True) or trace.fired_deadline or not all_of(trace.state, action.get("requires", [])):
            return False
        if not all(clock_condition(trace,c) for c in action.get('clock_requires',[])):
            return False
        return all(trace.state.get(k, -1) + EPS >= value and value >= 0
                   for k, value in action.get("consumes", {}).items())

    def deadline(self, trace):
        """Resolve the current branch against the containing phase, never arrival."""
        definition = self.case['deadline']
        for branch in definition.get('branches', []):
            if all_of(trace.state, branch['when']):
                definition = {**definition, **branch}
                break
        clock = definition['clock']
        due = definition['seconds']
        if clock == 'budget':
            due = min(trace.phase_start_budget + due, trace.dawn_budget)
        elif clock == 'world':
            due += trace.phase_start_world
        else:
            due = trace.dawn_budget
        return definition, ('world' if clock == 'world' else 'budget'), due

    def _settle_deadline(self, trace, *, include_equal):
        if self.terminal(trace) != 'active':
            return False
        _, clock, due = self.deadline(trace)
        now = getattr(trace, clock)
        due_now = now + EPS >= due if include_equal else now > due + EPS
        if trace.budget > trace.dawn_budget + EPS or due_now:
            return self.expire(trace, advance=False)
        return False

    def _timer_definitions(self):
        timers = self.case.get('timers', [])
        return list(timers.values()) if isinstance(timers, dict) else timers

    def _sync_timer_values(self, trace):
        for definition in self._timer_definitions():
            key = definition.get('remaining_key')
            if key and definition['id'] in trace.timers:
                clock = trace.world if definition.get('clock', 'world') == 'world' else trace.budget
                trace.state[key] = max(0, trace.timers[definition['id']] - clock)

    def _expire_timers(self, trace, *, exclude=(), include_equal=True):
        for definition in self._timer_definitions():
            timer_id = definition['id']
            if timer_id not in trace.timers or timer_id in exclude:
                continue
            clock = trace.world if definition.get('clock', 'world') == 'world' else trace.budget
            due = trace.timers[timer_id]
            passed = clock + EPS >= due if include_equal else clock > due + EPS
            if passed:
                effect = definition.get('expires_as', definition.get('expires_effect', {}))
                for branch in definition.get('expiry_branches', []):
                    if all_of(trace.state, branch['when']):
                        effect = branch['effect']
                        break
                if not isinstance(effect, dict):
                    raise ValueError('Timer expiry must be an executable effect: '+timer_id)
                trace.state = mutate(trace.state, effect)
                del trace.timers[timer_id]
                trace.timer_events.append({'id':timer_id, 'event':'expired', 'at':due, 'effect':deepcopy(effect)})

    def _advance(self, trace, world_seconds, budget_seconds, *, finishing_action=None):
        """Visit real timer/deadline boundaries in chronological order.

        Movement and work share budget; frozen-world precision work advances only
        budget. A deadline crossed partway through a leg stops before its commit.
        """
        if world_seconds < 0 or budget_seconds < 0:
            raise ValueError('Time cannot run backwards')
        remaining_world, remaining_budget = world_seconds, budget_seconds
        while remaining_world > EPS or remaining_budget > EPS:
            ratio = 1.0
            definitions = {t['id']: t for t in self._timer_definitions()}
            for timer_id, due in trace.timers.items():
                definition = definitions[timer_id]
                clock = definition.get('clock', 'world')
                delta = remaining_world if clock == 'world' else remaining_budget
                if delta > EPS:
                    ratio = min(ratio, max(0.0, (due - getattr(trace, clock)) / delta))
            _, deadline_clock, due = self.deadline(trace)
            delta = remaining_world if deadline_clock == 'world' else remaining_budget
            if self.terminal(trace) == 'active' and delta > EPS:
                ratio = min(ratio, max(0.0, (due - getattr(trace, deadline_clock)) / delta))
            if self.terminal(trace) == 'active' and remaining_budget > EPS:
                ratio = min(ratio, max(0.0, (trace.dawn_budget - trace.budget) / remaining_budget))
            trace.world += remaining_world * ratio
            trace.budget += remaining_budget * ratio
            self._sync_timer_values(trace)
            remaining_world *= 1-ratio
            remaining_budget *= 1-ratio
            at_end = remaining_world <= EPS and remaining_budget <= EPS
            finishing = [t['id'] for t in self._timer_definitions()
                         if at_end and finishing_action in (t.get('stop_actions', []) +
                             t.get('refresh_actions', []) + t.get('after_commit_actions', []))]
            self._expire_timers(trace, exclude=finishing, include_equal=True)
            self._derive_geometry(trace)
            # A just-completed legal action wins only at the final exact instant.
            self._settle_deadline(trace, include_equal=not at_end)
            if trace.fired_deadline:
                return False
        self._derive_geometry(trace)
        self._settle_deadline(trace, include_equal=False)
        return not trace.fired_deadline

    def perform(self, trace, action_id, *, cancel=False, include_route=True):
        action = self.actions[action_id]
        before = deepcopy(trace.state)
        self._settle_deadline(trace, include_equal=False)
        if not self.can_start(trace, action):
            return {"accepted": False, "reason": "precondition_or_inventory", "state_unchanged": before == trace.state}
        target = trace.position if action.get('global_event') else self.routes.point(action)
        distance = self.routes.distance(trace.position, target, action.get("closed_doors", [])) if include_route else 0
        speed = action.get("travel_speed", 2.4 if action.get("carry") == "heavy" else 3.0)
        if speed <= 0:
            raise ValueError("Movement speed must be positive")
        travel = distance / speed
        seconds = action["seconds"]
        if not isinstance(seconds, (int, float)) or not isfinite(seconds) or seconds < 0:
            raise ValueError("Invalid action duration")
        # A cancelled in-world hold can spend progress time without transferring the
        # object.  This model exercises half of an operation, not client input timing.
        route_start_world = trace.world
        route_complete = self._advance(trace, travel, travel)
        trace.travel += trace.world - route_start_world
        if not route_complete:
            return {'accepted':False, 'reason':'encounter_deadline_during_route', 'state_unchanged':before == trace.state}
        trace.position = deepcopy(target)
        self._derive_geometry(trace)
        if not self.can_start(trace, action):
            return {'accepted':False, 'reason':'condition_expired_during_real_route', 'state_unchanged':before == trace.state}
        if 'wait_until' in action:
            wait = action['wait_until']
            clock = trace.world if wait['clock'] == 'world' else trace.budget
            due = trace.timers.get(wait.get('timer_id')) if 'timer_id' in wait else wait['seconds']
            if due is None:
                return {'accepted':False,'reason':'missing_actual_timer','state_unchanged':before==trace.state}
            seconds = max(seconds, due-clock, 0)
        operation_time = seconds / 2 if cancel else seconds
        operation_complete = self._advance(trace, operation_time if action.get('clock','world') == 'world' or 'wait_until' in action else 0,
                                           operation_time, finishing_action=None if cancel else action_id)
        if not operation_complete:
            return {'accepted':False, 'reason':'encounter_deadline_before_action_commit', 'state_unchanged':before == trace.state}
        if not cancel:
            if not self.can_start(trace, action):
                return {'accepted':False,'reason':'condition_expired_before_action_commit','state_unchanged':before==trace.state}
            trace.state = mutate(trace.state, action)
            trace.position = deepcopy(action.get('end_position', target))
            self._derive_geometry(trace)
            for timer in self._timer_definitions():
                timer_id = timer['id']
                if action_id in timer.get('stop_actions', []):
                    trace.timers.pop(timer_id, None)
                if action_id in timer.get('start_actions', [timer.get('start_action')]):
                    clock = trace.world if timer.get('clock','world') == 'world' else trace.budget
                    if timer_id not in trace.timers or action_id in timer.get('refresh_actions', []):
                        trace.timers[timer_id] = clock + timer['seconds']
                        trace.timer_events.append({'id':timer_id,'event':'started','at':clock})
            self._expire_timers(trace, include_equal=True)
        self._settle_deadline(trace, include_equal=True)
        result = {"action": action_id, "accepted": True, "cancelled": cancel,
                  "route_tiles": distance, "travel_seconds": round(travel, 6),
                  "operation_seconds": operation_time,
                  "world_elapsed": round(trace.world, 6), "budget_elapsed": round(trace.budget, 6),
                  "state_unchanged": before == trace.state}
        trace.records.append(result)
        return result

    def advance_time(self, trace, world_seconds, budget_seconds):
        """Idle/other work cannot prevent already-running hazards from expiring."""
        self._advance(trace, world_seconds, budget_seconds)
        self._settle_deadline(trace, include_equal=True)
        return self.terminal(trace)

    def expire(self, trace, *, advance=True):
        deadline, clock, due = self.deadline(trace)
        if self.terminal(trace) != "active":
            return False
        trace.state = mutate(trace.state, deadline.get("on_expiry", {}))
        trace.fired_deadline = True
        trace.expiry_status = deadline['terminal_status']
        if advance and clock == "world":
            trace.world = max(trace.world, due)
            trace.budget = max(trace.budget, trace.world)
        elif advance:
            trace.budget = max(trace.budget, due)
        return True

    def finish(self, trace):
        """Close encounter operations; a declared unclaimed physical gift is separate.

        A full backpack may delay collection without keeping the danger alive.
        The gift's own object/receipt/quantity guard still applies.
        """
        if self.terminal(trace) == "active":
            raise ValueError("Cannot close a still-active encounter")
        trace.closed = True

    def run(self, scenario):
        trace = self.begin(scenario)
        for action_id in scenario["steps"]:
            result = self.perform(trace, action_id)
            expected_rejection=scenario.get('expected_rejections',{}).get(action_id)
            if expected_rejection:
                if result['accepted'] or result.get('reason')!=expected_rejection:
                    raise ValueError('Expected timer expiry did not occur '+action_id)
            elif not result["accepted"]:
                raise ValueError(f"{self.case['id']}/{scenario['id']}: blocked action {action_id}")
        actual = self.terminal(trace)
        if actual != scenario["expected"]:
            raise ValueError(f"{self.case['id']}/{scenario['id']}: expected {scenario['expected']}, got {actual}")
        self.finish(trace)
        for action_id in scenario.get('post_terminal_steps', []):
            if self.actions[action_id].get('reward_scope') is not True:
                raise ValueError('Only registered separate rewards may run after closure')
            if not self.perform(trace, action_id)['accepted']:
                raise ValueError('Invalid post-terminal gift claim '+action_id)
        if not all_of(trace.state, scenario.get("assert", [])):
            raise ValueError(f"{self.case['id']}/{scenario['id']}: final assertion failed")
        return trace
