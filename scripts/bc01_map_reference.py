#!/usr/bin/env python3
"""BC01 body-clear store routes and bounded encounter plans, not live enemy AI.

The module does not award money, spawn purchased inventory, or conclude a
damage-required encounter merely because its mechanism plan has ended.
"""
from __future__ import annotations

import copy
import heapq
import json
import math
from fractions import Fraction
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _read(name):
    return json.loads((ROOT / "content" / name).read_text())


def _point_rect_d2(p, r):
    x, y, w, h = r
    return max(x-p[0], 0, p[0]-x-w)**2 + max(y-p[1], 0, p[1]-y-h)**2


def _point_segment_d2(p, a, b):
    vx, vy = b[0]-a[0], b[1]-a[1]
    den = vx*vx + vy*vy
    t = max(0, min(1, ((p[0]-a[0])*vx + (p[1]-a[1])*vy)/den)) if den else 0
    return (p[0]-a[0]-t*vx)**2 + (p[1]-a[1]-t*vy)**2


def _segment_rect_intersects(a, b, r):
    x, y, w, h = r
    lo, hi = 0.0, 1.0
    for start, delta, lower, upper in ((a[0], b[0]-a[0], x, x+w), (a[1], b[1]-a[1], y, y+h)):
        if abs(delta) < 1e-12:
            if start < lower or start > upper:
                return False
        else:
            t0, t1 = sorted(((lower-start)/delta, (upper-start)/delta))
            lo, hi = max(lo, t0), min(hi, t1)
            if lo > hi:
                return False
    return True


def _segment_rect_d2(a, b, r):
    if _segment_rect_intersects(a, b, r):
        return 0.0
    x, y, w, h = r
    return min(_point_rect_d2(a, r), _point_rect_d2(b, r),
               *(_point_segment_d2(p, a, b) for p in ((x,y),(x+w,y),(x,y+h),(x+w,y+h))))


class StoreMap:
    """Static assembled map plus explicit closed doors and real barricade cells.

    Grid traversal is four-neighbour. Arbitrary coordinate starts connect by
    swept-body-clear segments; their lengths are charged, never teleported.
    """
    def __init__(self, *, closed_doors=(), barricade_cells=(), radius=0.3, power_on=True):
        self.contract = _read("map_composition_bc01.json")
        self.base = next(s for s in _read("maps.json")["scenes"] if s["id"] == "MAP_STORE")
        self.radius = radius
        self.power_on = power_on  # no electrical switch removes physical manual paths
        self.anchors = {a["role"]: tuple(a["position"]) for a in self.base["anchors"]}
        self.anchors.update({a["role"]: tuple(a["position"]) for a in self.contract["anchors"]})
        self.obstacles = [dict(o) for o in self.base["walls"]]
        self.obstacles += [dict(o) for o in self.base["fixtures"] if o.get("blocks_navigation")]
        self.obstacles += [dict(o) for o in self.contract["new_fixtures"] if o.get("blocks_navigation")]
        closed_doors = set(closed_doors)
        for door in self.base["doors"]:
            if door["id"] in closed_doors:
                self.obstacles.append(door)
        for i, cell in enumerate(barricade_cells):
            self.obstacles.append({"id": f"paid_barrier_{i}", "rect": [cell[0], cell[1], 1, 1]})
        self.floor_cells = set()
        for surface in self.base["walk_surfaces"]:
            x,y,w,h = surface["rect"]
            self.floor_cells.update((ix,iy) for ix in range(x,x+w) for iy in range(y,y+h))
        self.nodes = {cell for cell in self.floor_cells if self.point_clear((cell[0]+.5,cell[1]+.5))}
        self._route_cache = {}
        self._protected = None

    def position(self, role_or_position):
        if isinstance(role_or_position, str):
            if role_or_position not in self.anchors:
                raise KeyError(f"Unplaced BC01 anchor: {role_or_position}")
            return list(self.anchors[role_or_position])
        if len(role_or_position) != 2:
            raise ValueError("Position requires x,y")
        return [float(role_or_position[0]), float(role_or_position[1])]

    def point_clear(self, p, radius=None):
        radius = self.radius if radius is None else radius
        if radius < 0:
            raise ValueError("Negative collision radius")
        for ix in range(math.floor(p[0]-radius), math.floor(p[0]+radius)+1):
            for iy in range(math.floor(p[1]-radius), math.floor(p[1]+radius)+1):
                if (ix,iy) not in self.floor_cells and _point_rect_d2(p,(ix,iy,1,1)) < radius**2-1e-12:
                    return False
        if (math.floor(p[0]), math.floor(p[1])) not in self.floor_cells:
            return False
        return not any(_point_rect_d2(p, o["rect"]) < radius**2-1e-12 or
                       (radius == 0 and _point_rect_d2(p,o["rect"]) == 0)
                       for o in self.obstacles)

    def segment_clear(self, a, b, radius=None):
        radius = self.radius if radius is None else radius
        if not self.point_clear(a, radius) or not self.point_clear(b, radius):
            return False
        for o in self.obstacles:
            if _segment_rect_d2(a,b,o["rect"]) < radius**2-1e-12:
                return False
        for ix in range(math.floor(min(a[0],b[0])-radius), math.floor(max(a[0],b[0])+radius)+1):
            for iy in range(math.floor(min(a[1],b[1])-radius), math.floor(max(a[1],b[1])+radius)+1):
                if (ix,iy) not in self.floor_cells and _segment_rect_d2(a,b,(ix,iy,1,1)) < radius**2-1e-12:
                    return False
        return True

    def los_clear(self, a, b, ignore_fixture=None):
        return not any(_segment_rect_intersects(a,b,o["rect"]) for o in self.obstacles if o["id"] != ignore_fixture)

    def _connectors(self, p, customer=False):
        if not self.point_clear(p):
            raise ValueError(f"Actor body intersects solid or off-map at {p}")
        x_on_grid=abs((p[0]-.5)-round(p[0]-.5))<1e-9
        y_on_grid=abs((p[1]-.5)-round(p[1]-.5))<1e-9
        if not x_on_grid and not y_on_grid:
            raise ValueError("Coordinate must lie on an actual four-neighbour grid edge")
        result=[]
        for ix in range(math.floor(p[0])-1, math.floor(p[0])+2):
            for iy in range(math.floor(p[1])-1, math.floor(p[1])+2):
                if (ix,iy) not in self.nodes or (customer and iy < 10):
                    continue
                q=(ix+.5,iy+.5)
                if x_on_grid and abs(q[0]-p[0])>1e-9:continue
                if y_on_grid and abs(q[1]-p[1])>1e-9:continue
                if self.segment_clear(p,q):
                    result.append(((ix,iy),math.dist(p,q)))
        if not result:
            raise ValueError(f"No body-clear connector from {p}")
        return result

    def route(self, start, end, *, actor="player"):
        a,b = tuple(self.position(start)),tuple(self.position(end))
        customer=actor == "customer"
        cache_key=(a,b,customer)
        if cache_key in self._route_cache:
            return copy.deepcopy(self._route_cache[cache_key])
        starts=self._connectors(a,customer)
        ends=dict(self._connectors(b,customer))
        queue=[]; distance={}; previous={}
        for cell,d in starts:
            distance[cell]=d
            previous[cell]=None
            heapq.heappush(queue,(d,cell))
        best=float("inf"); finish=None
        while queue:
            d,cell=heapq.heappop(queue)
            if d > distance[cell]+1e-12 or d > best:
                continue
            if cell in ends and d+ends[cell] < best-1e-12:
                best,finish=d+ends[cell],cell
            x,y=cell
            for nxt in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
                if nxt not in self.nodes or (customer and nxt[1]<10):
                    continue
                # Axis-aligned integer-cell solids and radius <=.5 make every
                # edge between neighbouring legal centres body-clear.
                if self.radius > .5 and not self.segment_clear((x+.5,y+.5),(nxt[0]+.5,nxt[1]+.5)):
                    continue
                nd=d+1
                if nd < distance.get(nxt,float("inf"))-1e-12:
                    distance[nxt]=nd; previous[nxt]=cell
                    heapq.heappush(queue,(nd,nxt))
        if finish is None:
            raise ValueError(f"No legal {actor} route: {start} -> {end}")
        cells=[]; cur=finish
        while cur is not None:
            cells.append(cur); cur=previous[cur]
        cells.reverse()
        path=[list(a)]
        for x,y in cells:
            p=[x+.5,y+.5]
            if p != path[-1]:path.append(p)
        if list(b)!=path[-1]:path.append(list(b))
        actual=sum(math.dist(p,q) for p,q in zip(path,path[1:]))
        result={"distance":actual,"distance_tiles":actual,"path":path,
                "actor":actor,"body_radius_tiles":self.radius,"body_clear":True}
        self._route_cache[cache_key]=result
        return copy.deepcopy(result)

    def route_customer(self, start, end):
        return self.route(start,end,actor="customer")

    def travel_seconds(self, start, end, speed=3.0, *, actor="player"):
        if speed <= 0:
            raise ValueError("Travel speed must be positive")
        return self.route(start,end,actor=actor)["distance"]/speed

    def protected_cells(self):
        if self._protected is not None:
            return set(self._protected)
        cells=set()
        for p in self.anchors.values():cells.add((math.floor(p[0]),math.floor(p[1])))
        business=self.contract["business_route_policy"]["normal_customer_allowed_anchors"]
        for role in business:
            for a,b in (("customer_spawn",role),(role,"customer_checkout"),(role,"customer_exit")):
                for p in self.route_customer(a,b)["path"]:
                    cells.add((math.floor(p[0]),math.floor(p[1])))
        for role in self.anchors:
            for p in self.route("player_start",role)["path"]:
                cells.add((math.floor(p[0]),math.floor(p[1])))
        for c in self.contract["task_modules"]:
            if c.get("lit_rect"):
                x,y,w,h=c["lit_rect"]
                cells.update((ix,iy) for ix in range(x,x+w) for iy in range(y,y+h))
        self._protected=cells
        return set(cells)

    def safe_trap_cells(self, *, occupied=(), protected=(), active_actors=(), object_count=0,
                        footprint_count=0, temporary_active=False):
        return [p["origin_cell"] for p in self.safe_trap_placements(
            occupied=occupied,protected=protected,active_actors=active_actors,
            object_count=object_count,footprint_count=footprint_count,temporary_active=temporary_active)]

    def safe_trap_placements(self, *, footprint=(1,1), occupied=(), protected=(), active_actors=(),
                             object_count=0, footprint_count=0, temporary_active=False):
        cfg=self.contract["trap_placement"]
        width,height=footprint
        if width not in (1,2) or height not in (1,2):raise ValueError("Unsupported temporary footprint")
        if object_count>=8 or footprint_count+width*height>16 or temporary_active:
            return []
        excluded={tuple(c) for c in occupied}|{tuple(c) for c in protected}|self.protected_cells()
        actors=[self.position(p) for p in active_actors]
        result=[]
        for cell in cfg["candidate_cells"]:
            rotations=[(0,width,height)] if width==height else [(0,width,height),(90,height,width)]
            for rotation,w,h in rotations:
                cells=[(cell[0]+x,cell[1]+y) for x in range(w) for y in range(h)]
                if any(c in excluded or not self.point_clear((c[0]+.5,c[1]+.5)) for c in cells):continue
                if any(math.dist((c[0]+.5,c[1]+.5),a)<cfg["placement_distance_from_live_actor_min_tiles"]
                       for c in cells for a in actors):continue
                result.append({"origin_cell":list(cell),"cells":[list(c) for c in cells],
                               "rotation":rotation,"footprint":[w,h],"nonblocking":True})
        return result

    def combat_reference(self, monster_id):
        cfg=copy.deepcopy(self.contract["combat_reference"])
        roster={r["monster_id"]:r for r in encounter_catalog(include_passive=True)}
        if monster_id not in roster or not roster[monster_id]["requires_combat_after_rule"]:
            return {**cfg,"legal":False,"reason":"no_admitted_damage_required_case"}
        base=next(t for t in _read("tower_defense_td05.json")["families"] if t["id"]=="T02")["l1"]
        loop=cfg["target_loop"]; origin=cfg["tower_anchor_position"]; emitter=cfg["emitter"]
        reasons=[]
        if not all(self.point_clear(p) for p in loop):reasons.append("target_body_blocked")
        if not all(self.segment_clear(a,b) for a,b in zip(loop,loop[1:]+loop[:1])):
            reasons.append("target_movement_blocked")
        if not all(math.dist(origin,p)<=base["parameters"]["range_tiles"] for p in loop):
            reasons.append("out_of_range")
        if not all(self.los_clear(emitter,p) for p in loop):reasons.append("line_of_sight_blocked")
        height=roster[monster_id]["movement_height"]
        if height not in base["layers"] and height not in ("mixed","low_air_or_ground"):
            reasons.append("unsupported_height")
        cfg.update(legal=not reasons,reasons=reasons,monster_id=monster_id,
                   actual_range_tiles=base["parameters"]["range_tiles"],
                   max_target_distance_tiles=max(math.dist(origin,p) for p in loop),
                   body_radius_tiles=self.radius,
                   requires_actual_world_target_on_verified_loop=True)
        return cfg

    def validate_layout(self, *, normal_customers=True, required_roles=None):
        """Admission proof for this concrete arrangement, including paid barriers."""
        errors=[]
        roles=required_roles or list(self.anchors)
        for role in roles:
            try:self.route("player_start",role)
            except (ValueError,KeyError) as e:errors.append({"role":role,"reason":str(e)})
        if normal_customers:
            for role in self.contract["business_route_policy"]["normal_customer_allowed_anchors"]:
                try:
                    self.route_customer("customer_spawn",role)
                    self.route_customer(role,"customer_exit")
                except (ValueError,KeyError) as e:errors.append({"role":role,"actor":"customer","reason":str(e)})
        return {"legal":not errors,"errors":errors,"verified_roles":len(roles),
                "normal_customers":normal_customers,"power_on":self.power_on}


class ParcelResponseReference:
    """F17-only extension of SA02: actual original parcel pickup, not immunity.

    The map checks its own route. The finite caller supplies actual original
    object/actor identity facts, not a UI claim. Paid dose maturities and all
    absolute deadlines continue. Existing control is never cleared on entry.
    """
    def __init__(self, record, navigation, root_id, attempt_id, actor_id, parcel_id,
                 position, deadline, *, maturities=(), timed_states=None, slow_fraction=0):
        from md01_reference import LifeState
        if record["id"]!="F17" or record["resolution"]["type"]!="rule_leave":
            raise ValueError("Parcel response is only registered for F17")
        self.life=LifeState(copy.deepcopy(record),root=root_id)
        self.navigation=navigation
        self.attempt_id=attempt_id;self.actor_id=actor_id;self.parcel_id=parcel_id
        self.position=navigation.position(position);self.deadline=Fraction(str(deadline))
        self.maturities=[{**m,"due":Fraction(str(m["due"])),"amount":Fraction(str(m["amount"])),"applied":False}
                         for m in maturities]
        if (len({m["id"] for m in self.maturities})!=len(self.maturities) or
            any(m["due"]<0 or m["amount"]<=0 for m in self.maturities)):
            raise ValueError("Invalid paid maturity ledger")
        self.timed_states={k:Fraction(str(v)) for k,v in (timed_states or {}).items()}
        self.slow_fraction=max(Fraction(0),min(Fraction(3,5),Fraction(str(slow_fraction))))
        self.base_speed=Fraction(str(record["stats"]["move_speed"]))
        self.phase="idle";self.protected=False;self.plan=None
        self.distance_done=Fraction(0);self.work_done=Fraction(0);self.protection_used=Fraction(0)
        self.item_owner="pickup_slot";self.trace=[]

    @property
    def now(self):return self.life.now

    def _facts_valid(self, facts):
        if any(self.timed_states.get(k,Fraction(-1))>self.now for k in ("freeze","stun","root_control")):
            return False
        if (facts.get("evidence_origin")!="world_adapter" or facts.get("root_id")!=self.life.root or
            facts.get("attempt_id")!=self.attempt_id or facts.get("actor_id")!=self.actor_id or
            facts.get("parcel_id")!=self.parcel_id or facts.get("knots_open")!=3 or
            facts.get("parcel_owner")!="pickup_slot" or facts.get("control_active") is not False or
            facts.get("normal_human") is not False):return False
        try:
            actual=facts["parcel_position"];player=facts["player_position"]
            return (list(actual)==[19.5,26.5] and math.dist(actual,player)>=2.5 and
                    self.navigation.point_clear(player) and self.navigation.point_clear(self.position))
        except (KeyError,ValueError,TypeError):return False

    def enter(self,facts):
        if self.phase in ("complete","failed") or self.protected or self.life.state!="active" or not self._facts_valid(facts):
            return False
        if self.plan is None:
            try:route=self.navigation.route(self.position,"pickup_shelf")
            except (ValueError,KeyError):return False
            distance=Fraction(str(route["distance"]))
            # The existing global 60% slow cap defines a conservative immutable
            # time budget; a 99% malformed amount cannot create an infinite one.
            budget=distance/(self.base_speed*Fraction(2,5))+2
            if self.now+budget>self.deadline:return False
            self.plan={"path":route["path"],"distance":distance,"protection_budget":budget,
                       "original_deadline":self.deadline,"root_id":self.life.root,
                       "actor_id":self.actor_id,"parcel_id":self.parcel_id}
        elif self.protection_used>=self.plan["protection_budget"] or self.now>=self.deadline:
            return False
        self.protected=True
        self.phase="travel" if self.distance_done<self.plan["distance"] else "collect"
        self.trace.append({"event":"f17_bound_parcel_response","at":str(self.now),"cancel_owned_attacks":True})
        return True

    def attack_allowed(self):
        return self.life.state=="active" and not self.protected and self.phase not in ("complete","failed")

    def damage(self,raw,channel="physical",**kwargs):
        if self.protected or self.phase=="complete":return Fraction(0)
        return self.life.apply_damage(raw,channel,**kwargs)

    def poison_tick(self,seconds=1):
        return self.damage(self.life.poison*Fraction(str(seconds))/2,"spiritual")

    def interrupt(self):
        if not self.protected:return False
        self.protected=False;self.phase="interrupted"
        self.trace.append({"event":"actual_parcel_predicate_lost","at":str(self.now)})
        return True

    def _world(self,delta):
        self.life.advance(delta)
        for m in self.maturities:
            if not m["applied"] and m["due"]<=self.now:
                m["applied"]=True
                if self.phase!="complete":self.life.poison+=m["amount"]
        self.timed_states={k:v for k,v in self.timed_states.items() if v>self.now}

    def _place(self):
        left=float(self.distance_done)
        for a,b in zip(self.plan["path"],self.plan["path"][1:]):
            length=math.dist(a,b)
            if left<=length+1e-10:
                ratio=left/length if length else 0
                self.position=[a[0]+(b[0]-a[0])*ratio,a[1]+(b[1]-a[1])*ratio]
                return
            left-=length
        self.position=list(self.plan["path"][-1])

    def elapse(self,seconds,facts):
        remaining=Fraction(str(seconds))
        if remaining<0:raise ValueError("Negative world elapsed time")
        if self.protected and not self._facts_valid(facts):self.interrupt()
        while remaining>0:
            if self.phase in ("complete","failed"):
                self._world(remaining);return
            if not self.protected:
                delta=min(remaining,max(Fraction(0),self.deadline-self.now))
                self._world(delta);remaining-=delta
                if self.now>=self.deadline:self.phase="failed"
                continue
            if self.phase=="travel":
                active_slow=self.slow_fraction if self.timed_states.get("slow",Fraction(-1))>self.now else Fraction(0)
                speed=self.base_speed*(1-active_slow)
                stage=(self.plan["distance"]-self.distance_done)/speed
                cumulative=Fraction(0)
                for a,b in zip(self.plan["path"],self.plan["path"][1:]):
                    cumulative+=Fraction(str(math.dist(a,b)))
                    if cumulative>self.distance_done:
                        stage=min(stage,(cumulative-self.distance_done)/speed)
                        break
            else:
                speed=Fraction(0);stage=2-self.work_done
            boundaries=[v-self.now for v in self.timed_states.values() if v>self.now]
            boundaries += [m["due"]-self.now for m in self.maturities if not m["applied"] and m["due"]>self.now]
            delta=min([remaining,stage,self.deadline-self.now,
                       self.plan["protection_budget"]-self.protection_used]+boundaries)
            if delta<0:raise AssertionError("Expired bounded response")
            if self.phase=="travel":
                old=self.position[:]
                self.distance_done+=speed*delta;self._place()
                if not self.navigation.segment_clear(old,self.position):
                    self.interrupt();self.position=old;self.distance_done-=speed*delta
                    continue
            else:self.work_done+=delta
            self.protection_used+=delta;self._world(delta);remaining-=delta
            if self.phase=="travel" and self.distance_done>=self.plan["distance"]:
                self.phase="collect"
            if self.phase=="collect" and self.work_done==2:
                self.item_owner=self.actor_id;self.protected=False;self.phase="complete"
                self.life.complete_rule({"verified":True,"root":self.life.root,
                    "id":"F17:original-parcel:"+self.parcel_id+":"+str(self.attempt_id)})
                self.maturities=[];self.timed_states={}
                self.trace.append({"event":"same_original_parcel_taken","at":str(self.now)})
            elif self.now>=self.deadline or self.protection_used>=self.plan["protection_budget"]:
                self.protected=False;self.phase="failed"
            elif delta==0 and self.phase!="collect":
                raise AssertionError("Nonprogressing bounded parcel response")

    def clone_saved_state(self):
        return copy.deepcopy(self)


def _monsters():
    result={}
    for fn in ("monster_folklore_md01.json","monster_scp_a_md01.json","monster_scp_b_md01.json"):
        result.update({m["id"]:m for m in _read(fn)["monsters"]})
    return result


def _travel(to, *, actor="player", origin=None, speed=None, **extra):
    s={"kind":"travel","actor":actor,"to":to,**extra}
    if origin is not None:s["from"]=origin
    if speed is not None:s["speed"]=speed
    return s


def _action(role, action_id, seconds, *, actor="player", **extra):
    return {"kind":"action","actor":actor,"role":role,"action_id":action_id,
            "seconds":seconds,"duration_class":"player_manual" if actor=="player" else "actor_owned",**extra}


def _wait(seconds, reason, *, actor="monster", **extra):
    return {"kind":"wait","actor":actor,"seconds":seconds,"reason":reason,
            "duration_class":"true_world_wait",**extra}


def encounter_catalog(night_index=None, *, include_passive=False):
    """Return explicit script plans. Steps are evidence requirements, not win timers.

    All player travel is real. Monster-owned travel uses a separate actor
    position; a wait must validate its predicate and cannot create a receipt.
    Endings requiring HP0 are left to an actual damage resolver.
    """
    cfg=_read("map_composition_bc01.json"); data=_monsters(); result=[]
    for admission in cfg["encounter_admission"]:
        mid=admission["monster_id"]
        if not admission["geometry_reference_admitted"]:continue
        if not include_passive and not admission["director_reference_admitted"]:continue
        if night_index is not None and admission["first_night"]>night_index:continue
        m=data[mid]; steps=[]
        for s in m["mechanism"]["steps"]:
            steps += [_travel(s["anchor"]),_action(s["anchor"],s["id"],s["seconds"],
                       source_clock=s.get("clock","world"),description=s["action"])]
        if mid=="F05":
            locations={"take_cloth":"mop_station","close_valve":"water_valve",
                       "wipe_cut":"cold_cut","take_basket":"cold_cut",
                       "place_dry":"cold_dry_slot","confirm_disconnect":"cold_dry_slot"}
            steps=[]
            for s in m["mechanism"]["steps"]:
                role=locations[s["id"]];steps.append(_travel(role))
                steps.append(_wait(.2,"same_source_water_disconnect_update") if s["id"]=="confirm_disconnect"
                             else _action(role,s["id"],s["seconds"],description=s["action"]))
        elif mid=="F12":
            steps=[_travel("metal_shelf"),_action("metal_shelf","take_clips",1),
                   _travel("aisle_loop"),_action("aisle_loop","scatter1",.25,consumes_original_clip=1),
                   _travel("aisle_loop",actor="monster",origin=[8.5,22.5],speed=3.24),
                   _wait(1.5,"same_root_consumes_original_clip_and_finishes_feeding",rule_receipt=True)]
        elif mid=="F13":
            steps=[]
            for s in m["mechanism"]["steps"]:
                steps += [_travel(s["anchor"],speed=2.6 if s["anchor"]=="freezer_main" else 3),
                          _action(s["anchor"],s["id"],s["seconds"],description=s["action"])]
        elif mid=="F17":
            steps=[_travel("pickup_shelf")]
            for i in range(3):steps.append(_action("pickup_shelf",f"untie_original_knot_{i+1}",1))
            steps += [_action("pickup_shelf","place_ready",.5),_travel("parcel_retreat"),
                      _travel("pickup_shelf",actor="monster",origin="parcel_guest_start",speed=3.3,
                              response_mode="BC01_F17_bound_parcel_noncombat_response"),
                      _wait(2,"same_guest_collects_same_original_parcel_after_player_retreat",rule_receipt=True,
                            response_mode="BC01_F17_bound_parcel_noncombat_response"),
                      _travel("customer_exit",actor="monster",speed=3.3,real_exit_observed=True)]
        elif mid=="F60":
            steps=[_travel("convex_mirror"),_action("convex_mirror","notice_turn",1),
                   _action("convex_mirror","read_mirror",1),_action("convex_mirror","pull_curtain",1),
                   _action("convex_mirror","close_service",.5),
                   _wait(1.5,"first_distinct_gaze_attack_misses_actual_occluder_or_back_facing",attack_id="F60:gaze:1"),
                   _wait(10,"second_distinct_gaze_attack_misses_actual_occluder_or_back_facing",attack_id="F60:gaze:2",rule_receipt=True)]
        elif mid=="S09":
            steps=[_travel("infrared_window"),_action("infrared_window","S09:step1",1),
                   _travel("wave_screen"),_action("wave_screen","S09:step2",1),
                   _travel("infrared_lure"),
                   _travel("infrared_lure",actor="monster",origin=[9.5,18.5],speed=3.45,
                           crossing_segment=[[6,20],[10,20]],requires_real_body_crossing=True),
                   _travel("infrared_gate"),_action("infrared_gate","S09:step3",1,rule_receipt=True)]
        elif mid=="S29":
            steps=[_travel("s29_light_control"),_action("s29_light_control","S29_step_1",.8),
                   _action("s29_light_control","S29_step_2",1),_travel("s29_dodge"),
                   _wait(4,"same_monster_in_actual_full_light_during_2s_windup_and_2_5s_recovery",
                         actor_from="s29_target",lit_rect=[6,13,4,5],rule_receipt=True)]
        elif mid=="S34":
            steps=[_travel("sound_side"),_action("sound_side","S34_step_1",.8),
                   _wait(6,"six_notes_finish_while_actual_baffle_occludes_player_side"),
                   _action("sound_side","S34_step_2",1.2),_action("sound_side","S34_step_3",1,
                       rule_receipt=True,real_exit_observed=True,terminal_observation="same_intact_ball_inside_locked_original_box")]
        elif mid=="S38":
            steps[-1]["rule_receipt"]=True
            steps[-1]["real_exit_observed"]=True
            steps[-1]["terminal_observation"]="same_mirror_stored_no_wearer"
        elif mid=="S40":
            steps=[_travel("cashier"),_action("cashier","S40_step_1",.8),
                   _travel("packing"),_action("packing","S40_step_2",1),
                   _travel("paper_load"),_action("paper_load","S40_step_3",.8),
                   _wait(.5,"same_tray_moves_one_tile_along_fixed_countertop_rail"),
                   _travel("paper_wait"),
                   _travel("paper_take",actor="monster",origin="rear_threshold",speed=3.3,
                           response_mode="SA02_noncombat_response"),
                   _wait(2.5,"same_shadow_takes_original_paper_with_player_outside_handoff_bounds",rule_receipt=True,
                         response_mode="SA02_noncombat_response"),
                   _travel("rear_exit",actor="monster",speed=3.3,real_exit_observed=True,
                           response_mode="SA02_noncombat_response")]
        elif mid=="S43":
            steps=[_travel("receiving"),_action("receiving","S43_step_1",.8),
                   _travel("s43_panel"),_action("s43_panel","S43_step_2",1),
                   _wait(3,"same_external_mall_returns_actual_open_receipt",revoke_hostility=True),
                   _travel("s43_exit",actor="monster",origin="receiving",speed=3.3,
                           response_mode="SA02_noncombat_response",real_exit_observed=True),
                   _travel("s43_latch"),_action("s43_latch","S43_step_3",1,rule_receipt=True,
                           requires_observed_actor_exit=True)]
        damage_required=m["resolution"]["type"]!="rule_leave"
        if damage_required:
            steps.append(_travel("combat_player"))
            steps.append(_travel("combat_target",actor="monster",speed=m["post_rule"]["move_speed"],
                                 actual_fire_lane_arrival_required=True,
                                 height=m["movement"].get("post_rule_height",m["movement"]["height"]),
                                 route_policy="registered_body_clear_corridor_projection_no_wall_crossing"))
        row={"monster_id":mid,"id":mid,"name":m["name"],"first_night":m["first_day"],
             "pressure_cost":m["pressure_cost"],"steps":steps,"terminal_kind":m["resolution"]["type"],
             "requires_combat_after_rule":damage_required,"hp":m["stats"]["hp"],
             "armor":m["post_rule"]["armor"],"ward":m["post_rule"]["ward"],
             "movement_height":m["movement"].get("post_rule_height",m["movement"]["height"]),"combat_reference":cfg["combat_reference"],
             "runtime_integrated":False,"rule_receipt_requires_original_objects":True,
             "reward_eligible":mid!="S38","finite_reference_only":True,
             "terminal_requirements":(["same_root_actual_hp_zero_after_legal_damage"] if damage_required else
                                      ["same_original_rule_objects_committed","real_exit_or_container_observed"])}
        initial_positions={"F01":[24.5,4.5],"F05":[23.5,11.5],"F12":[8.5,22.5],
                           "F13":[27.5,-3.5],"F17":[19.5,22.5],"F60":[21.5,22.5],
                           "S09":[9.5,18.5],"S29":[8.5,15.5],"S34":[17.5,7.5],
                           "S38":[27.5,23.5],"S40":[27.5,-1.5],"S43":[23.5,3.5]}
        row["initial_actor_positions"]={"monster":initial_positions[mid]}
        row["activation_gate"]={"minimum_player_distance_tiles":5,
                                "requires_customers_fully_evacuated":True,
                                "too_close":"defer_or_choose_other_legal_entry_never_teleport_near_player"}
        result.append(row)
    return result


def pair_compatible(a,b,*,facts=None):
    """Fail closed. An explicit pair still needs all current world predicates."""
    cfg=_read("map_composition_bc01.json"); facts=facts or {}
    entries={r["monster_id"]:r for r in cfg["encounter_admission"]}
    if a==b or a not in entries or b not in entries:return False
    ra,rb=entries[a],entries[b]
    if not ra["geometry_reference_admitted"] or not rb["geometry_reference_admitted"]:return False
    if ra["high_pressure_exclusive"] or rb["high_pressure_exclusive"]:return False
    if ra["pressure_cost"]+rb["pressure_cost"]>cfg["composition"]["max_pressure_sum"]:return False
    if ra["active_player_pursuers"]+rb["active_player_pursuers"]>1:return False
    for pair in cfg["composition"]["explicit_pairs"]:
        if set(pair["ids"])=={a,b}:
            return all(facts.get(key) is True for key in pair["state_predicates"])
    return False


if __name__ == "__main__":
    nav=StoreMap()
    print(json.dumps({"cashier_to_breaker_seconds":nav.travel_seconds("cashier","power_panel"),
                      "director_catalog_count":len(encounter_catalog()),
                      "safe_trap_cells":nav.safe_trap_cells()},ensure_ascii=False,indent=2))
