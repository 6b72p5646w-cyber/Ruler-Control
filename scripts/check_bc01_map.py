#!/usr/bin/env python3
"""Meaningful bounded geometry/admission regression; no live AI victory claim."""
from __future__ import annotations

import hashlib
import itertools
import json
import math
from fractions import Fraction
from pathlib import Path

from bc01_map_reference import StoreMap, ParcelResponseReference, encounter_catalog, pair_compatible, _read, _point_rect_d2
from md01_reference import LifeState
from sa02_response_reference import ResponseReference

ROOT=Path(__file__).resolve().parents[1]
checks=[]


def check(name, result):
    checks.append({"name":name,"passed":bool(result)})


def rejects(fn):
    try:fn()
    except (ValueError,KeyError):return True
    return False


nav=StoreMap();cfg=nav.contract
check("assembled map legal for all player and customer stations",nav.validate_layout()["legal"])
check("new public cabinet really occupies four floor cells",
      all(not nav.point_clear((x+.5,y+.5)) for x in (23,24) for y in (21,22)))
check("new counter does not become tower or AP",
      not cfg["new_fixtures"][0]["appliance_network_node"] and not cfg["new_fixtures"][0]["new_tower_anchor"])
check("checkout two actual operation sides stay four tiles apart",
      math.dist(nav.position("cashier"),nav.position("customer_checkout"))==4)
check("paid frozen stock is separate from task meat handoff",
      nav.position("customer_freezer")!=nav.position("freezer_main"))

# Every segment is checked against actual solids, including circular body clearance.
anchor_routes=[]
for role in nav.anchors:
    route=nav.route("player_start",role)
    legal=all(nav.segment_clear(a,b) for a,b in zip(route["path"],route["path"][1:]))
    check("body-clear route to "+role,legal)
    anchor_routes.append({"role":role,"position":nav.position(role),"distance_from_player_start":route["distance"]})
check("route crosses no diagonal grid edges",
      all(a[0]==b[0] or a[1]==b[1] for r in nav._route_cache.values() for a,b in zip(r["path"],r["path"][1:])))
check("actual fractional edge retains its 0.25 tile remainder",
      nav.route([6.75,26.5],[7.5,26.5])["distance"]==.75)
check("invalid free off-graph coordinate is not silently snapped",
      rejects(lambda:nav.route([6.75,26.75],"cashier")))
check("solid fixture start is rejected",rejects(lambda:nav.route([4.5,13.5],"cashier")))
check("unknown task role is rejected",rejects(lambda:nav.route("shipping_cage_control","cashier")))

# Normal customers cannot use private staff/warehouse shortcuts, including evacuation.
customer_routes=[]
public=cfg["business_route_policy"]["normal_customer_allowed_anchors"]
for role in public:
    legs=[nav.route_customer("customer_spawn",role),nav.route_customer(role,"customer_checkout"),
          nav.route_customer("customer_checkout","customer_exit")]
    check("public customer route stays out of staff area "+role,
          all(p[1]>=10.3 for leg in legs for p in leg["path"]))
    distance=sum(leg["distance"] for leg in legs)
    customer_routes.append({"service_role":role,"travel_distance":distance,
                            "travel_seconds_at_2_4":round(distance/2.4,6),
                            "evacuation_distance":nav.route_customer(role,"customer_exit")["distance"]})
check("customer route to staff desk forbidden",rejects(lambda:nav.route_customer("customer_spawn","staff_desk")))
check("customer route to truck forbidden",rejects(lambda:nav.route_customer("customer_spawn","loading_bay")))

work_chains=[
 ("restock",["cashier","storage_shelf","goods_shelf","cashier"],[3,2.4,3]),
 ("truck_unload",["cashier","loading_bay","receiving","storage_shelf","cashier"],[3,2.4,2.4,3]),
 ("water_clean",["cashier","mop_station","clean_water","waste_sort","cashier"],[3,3,3,3]),
 ("mirror_water_clean",["cashier","mop_station","clean_mirror_water","waste_sort","cashier"],[3,3,3,3]),
 ("blood_clean",["cashier","mop_station","clean_blood","waste_sort","cashier"],[3,3,3,3]),
 ("trash_clean",["cashier","mop_station","clean_trash","waste_sort","cashier"],[3,3,3,3]),
 ("breaker_reset",["cashier","power_panel","cashier"],[3,3]),
 ("trash_to_dumpster",["waste_sort","dumpster"],[2.4]),
 ("free_task_meat",["warehouse_meat","freezer_main"],[2.6])]
work_routes=[]
for name,roles,speeds in work_chains:
    legs=[]
    for a,b,speed in zip(roles,roles[1:],speeds):
        r=nav.route(a,b);legs.append({"from":a,"to":b,"distance":r["distance"],"speed":speed,"seconds":r["distance"]/speed})
    work_routes.append({"job":name,"legs":legs,"travel_seconds":round(sum(r["seconds"] for r in legs),6),
                        "action_seconds_included":False,"ordinary_job_states":["BUSINESS","RECOVERY"] if name!="free_task_meat" else ["RAID"]})
check("breaker has twenty actual travel seconds not a free remote switch",
      next(w for w in work_routes if w["job"]=="breaker_reset")["travel_seconds"]==20)
check("real route is longer than direct Euclidean crossing shelves",
      nav.route("cashier","power_panel")["distance"]>math.dist(nav.position("cashier"),nav.position("power_panel")))

# Blackout does not erase free rule routes; physical door closure still matters.
dark=StoreMap(power_on=False)
check("blackout keeps every manual route",dark.validate_layout()["legal"])
for a,b in [("warehouse_meat","freezer_main"),("cashier","power_panel"),("receiving","s43_latch")]:
    check("blackout preserves actual route "+a+"->"+b,dark.route(a,b)==nav.route(a,b))
rear_closed=StoreMap(closed_doors=["DOOR_REAR"])
check("rear closed needs real external detour",
      rear_closed.route("waste_sort","dumpster")["distance"]>nav.route("waste_sort","dumpster")["distance"])
sealed=StoreMap(closed_doors=["DOOR_FRONT","DOOR_REAR"])
check("sealing both exits fails concrete admission",not sealed.validate_layout()["legal"])
bad_barrier=StoreMap(barricade_cells=[[6,26]])
check("paid barrier on actual operation point fails admission",not bad_barrier.validate_layout()["legal"])
good_barrier=StoreMap(barricade_cells=[[18,35],[19,35],[20,35]])
check("three legal paid barrier cells coexist with all workpoints",good_barrier.validate_layout()["legal"])

# New physical cabinet leaves all existing 12 paid tower projection regions unchanged.
projection=[]
new_rect=cfg["new_fixtures"][0]["rect"]
for row in _read("traps_facilities_td05.json")["map_constraints"]["side_hung_projection_examples"]:
    dist=math.sqrt(_point_rect_d2(row["field_center"],new_rect))
    unaffected=dist>row["compensated_radius_tiles"]+.3
    check("new fixture outside existing compensated tower field "+row["tower_anchor_id"],unaffected)
    projection.append({"anchor":row["tower_anchor_id"],"distance_to_new_fixture":dist,
                       "existing_effective_radius":row["compensated_radius_tiles"],"unaffected":unaffected})

# Temporary traps are real footprints, not a free inventory/ammunition slot.
one=nav.safe_trap_placements(footprint=(1,1));two=nav.safe_trap_placements(footprint=(1,2))
check("one-cell candidate has store interior and forecourt choices",
      any(p["origin_cell"][1]<29 for p in one) and any(p["origin_cell"][1]>29 for p in one))
check("R01 genuine two-cell rotations exist",{p["rotation"] for p in two}=={0,90})
check("R01 counts both footprint cells",all(len(p["cells"])==2 for p in two))
check("full eight objects refuses a temporary trap",nav.safe_trap_placements(object_count=8)==[])
check("R01 refuses only one remaining floor cell",nav.safe_trap_placements(footprint=(1,2),footprint_count=15)==[])
check("R02 can use last single floor cell",bool(nav.safe_trap_placements(footprint=(1,1),footprint_count=15)))
check("active temporary instance blocks second one",nav.safe_trap_placements(temporary_active=True)==[])
check("every protected or occupied candidate returns none",
      nav.safe_trap_placements(occupied=[c for p in one for c in p["cells"]])==[])
live_actor_positions=[(c[0]+.5,c[1]+.5) for p in one for c in p["cells"]]
check("actual live actors prevent underneath spawning",nav.safe_trap_placements(active_actors=live_actor_positions)==[])
protected=nav.protected_cells()
check("all temporary footprints avoid actual free-rule and customer routes",
      all(tuple(c) not in protected for p in one+two for c in p["cells"]))

# Finite plans compute travel and action durations separately, never automatic HP0.
catalog=encounter_catalog(include_passive=True);plans=[]
for case in catalog:
    position={"player":"player_start",**case["initial_actor_positions"]};time=0;travel=0;manual=0;wait=0
    path_rows=[]
    for step in case["steps"]:
        actor=step.get("actor","player")
        if step["kind"]=="travel":
            start=step.get("from",position.get(actor,"player_start"))
            route=nav.route(start,step["to"])
            speed=step.get("speed",3 if actor=="player" else 3.3)
            seconds=route["distance"]/speed
            position[actor]=step["to"];travel+=seconds
            path_rows.append({"actor":actor,"from":start,"to":step["to"],"distance":route["distance"],"seconds":seconds})
        elif step["kind"]=="action":
            check(case["id"]+" action in actual operation position "+step["action_id"],
                  nav.position(position[actor])==nav.position(step["role"]))
            seconds=step["seconds"];manual+=seconds
        else:
            seconds=step["seconds"];wait+=seconds
            check(case["id"]+" wait immune to interaction proficiency "+step["reason"],
                  step["duration_class"]=="true_world_wait")
        time+=seconds
    check(case["id"]+" real bounded route fits 120 reference seconds",time<120)
    if case["requires_combat_after_rule"]:
        proof=nav.combat_reference(case["id"])
        check(case["id"]+" actual T02 range and LOS",proof["legal"])
        check(case["id"]+" mechanism does not automatically end damage required root",
              case["terminal_requirements"]==["same_root_actual_hp_zero_after_legal_damage"])
    else:
        check(case["id"]+" rule leave includes actual exit or containment observation",
              any(step.get("real_exit_observed") for step in case["steps"]))
    plans.append({"monster_id":case["id"],"first_night":case["first_night"],"terminal_kind":case["terminal_kind"],
                  "travel_seconds":round(travel,6),"manual_seconds":round(manual,6),"true_wait_seconds":round(wait,6),
                  "minimum_serial_reference_seconds_before_combat":round(time,6),"travel_legs":path_rows,
                  "combat_required":case["requires_combat_after_rule"],"runtime_ai_verified":False})
check("S38 passive storage has no success income",not next(c for c in catalog if c["id"]=="S38")["reward_eligible"])
check("first night pool cannot access late SCP entries",{c["id"] for c in encounter_catalog(1)}=={"F01","F05","F17"})
check("every admitted initial actor is at least five tiles from actual safe-counter staging",
      all(math.dist(nav.position("safe_counter"),p)>=5 for c in catalog for p in c["initial_actor_positions"].values()))
check("cashier is not silently treated as a safe F12 spawn distance",
      math.dist(nav.position("cashier"),[8.5,22.5])<5)
for c in catalog:
    if c["requires_combat_after_rule"]:
        check(c["id"]+" actually moves same monster into fire lane before damage resolver",
              c["steps"][-1].get("actor")=="monster" and c["steps"][-1].get("to")=="combat_target"
              and c["steps"][-1].get("actual_fire_lane_arrival_required") is True)
check("F13 low air is never silently converted into ground",
      next(c for c in catalog if c["id"]=="F13")["movement_height"]=="low_air")
check("F05 cut action is physically within 1.5 tiles",
      math.dist(nav.position("cold_cut"),(24.5,10.5))<=1.5)
check("old general valve anchor cannot remotely wipe the cut",
      math.dist(nav.position("water_valve"),(24.5,10.5))>1.5)
check("F17 retreat charges actual four tiles instead of one-second shortcut",
      nav.travel_seconds("pickup_shelf","parcel_retreat")>1)
check("S09 real trajectory crosses fixed detection plane",
      any(a[1]<20<=b[1] and 6<=a[0]<=10 for a,b in zip(
          nav.route([9.5,18.5],"infrared_lure")["path"],nav.route([9.5,18.5],"infrared_lure")["path"][1:])))
check("S29 complete four seconds fit native 4.5 second attack window",4<=2+2.5)
for role in ("s29_target","s29_dodge"):
    x,y=nav.position(role)
    check("S29 light contains full body "+role,6+.3<=x<=10-.3 and 13+.3<=y<=18-.3)
check("S34 two finishing actions fit actual quiet window",1.2+1<=3)
blocked_fire=StoreMap(barricade_cells=[[7,23]])
check("actual barricade obstruction invalidates combat reference",not blocked_fire.combat_reference("F01")["legal"])
check("unplaced monster never gets generic combat proof",not nav.combat_reference("S06")["legal"])

# Full 105-entry routing is explicit, but only 12 geometry cases are admitted.
all_ids=[r["monster_id"] for r in cfg["encounter_admission"]]
check("all 105 original IDs appear once",len(all_ids)==len(set(all_ids))==105)
check("all unadapted cases carry an explicit block reason",
      all(r["blocked_reasons"] for r in cfg["encounter_admission"] if not r["geometry_reference_admitted"]))
check("no map proof silently opens a live client AI",
      all(not r["client_runtime_admitted"] for r in cfg["encounter_admission"]))
all_facts={f:True for p in cfg["composition"]["explicit_pairs"] for f in p["state_predicates"]}
accepted=[];evaluated=0
for a,b in itertools.combinations(all_ids,2):
    evaluated+=1
    ab=pair_compatible(a,b,facts=all_facts)
    ba=pair_compatible(b,a,facts=all_facts)
    if ab:accepted.append([a,b])
    if ab!=ba:check("pair symmetry "+a+"+"+b,False)
check("all 5460 unordered pairs pass through admission guard",evaluated==5460)
check("only two explicit compatible contexts can pass",{tuple(p) for p in accepted}=={("F17","S34"),("F17","S38")})
for p in cfg["composition"]["explicit_pairs"]:
    check("missing context rejects "+"+".join(p["ids"]),not pair_compatible(*p["ids"]))
    for fact in p["state_predicates"]:
        incomplete=dict(all_facts);incomplete[fact]=False
        check("actual predicate lost rejects "+fact,not pair_compatible(*p["ids"],facts=incomplete))
check("two independent pursuers are refused",not pair_compatible("F01","F05",facts=all_facts))
check("high-pressure paper encounter is exclusive",not pair_compatible("S40","F17",facts=all_facts))

# Re-use SA02's real state machine with the newly assembled actual map paths.
# Truth about IDs/objects is a declared finite fixture; geometry is computed.
scp={m["id"]:m for m in _read("monster_scp_b_md01.json")["monsters"]}
response_results=[]
for mid,start,end in (("S40","rear_threshold","paper_take"),("S43","receiving","s43_exit")):
    route=nav.route(start,end)
    r=ResponseReference(scp[mid],"bc01-map-root:"+mid,"attempt:1","actor:"+mid,
                        nav.position(start),60,expected_source_id="original-source:"+mid)
    r.life.hp=Fraction(50);r.life.add_poison(125)
    if mid=="S43":r.elapse(3)
    proof={"monster_id":mid,"root_id":r.life.root,"attempt_id":r.attempt_id,"actor_id":r.actor_id,
           "evidence_origin":"world_adapter","physical_verified":True,"route_verified":all(
               nav.segment_clear(a,b) for a,b in zip(route["path"],route["path"][1:])),
           "position_verified":route["path"][0]==list(r.position),"deadline_verified":True,
           "hostility_verified":True,"player_outside":nav.position("paper_wait")[0]<26,
           "original_deadline":"60","actual_actor_position":r.position,"plan_id":"bc01-map-plan:"+mid,
           "route_id":"actual-grid-route:"+mid,"destination_id":end,"bound_source_id":"original-source:"+mid,
           "path":route["path"],"sound_muted":True,"original_paper_in_tray":True,
           "external_mall_open":True,"exit_boundary_verified":end=="s43_exit" or mid=="S40",
           "external_ack_elapsed_s":3,"source_receipt_verified":True,"observed_world_time":str(r.now)}
    check(mid+" computed map route enters existing no-damage response",r.enter(proof))
    total=r.plan["route_seconds"]+r.plan["work_seconds"]
    while total>0:
        delta=min(Fraction(1,10),total);r.elapse(delta);total-=delta
        if r.phase!="complete":
            check(mid+" q125 does not re-suppress protected real path at "+str(r.now),r.poison_tick(delta)==0)
    if mid=="S43":
        check("S43 real exit alone cannot pay root reward",r.phase=="awaiting_latch" and r.life.ledger.coins==0)
        check("S43 same manual latch accepted only after actual exit",r.start_latch({
            "evidence_origin":"world_adapter","root_id":r.life.root,"attempt_id":r.attempt_id,
            "door_id":"s43_exit","actual_control_position":True,"held_input":True,"door_binding_verified":True}))
        r.elapse(1)
    check(mid+" mapped response settles once",r.phase=="complete" and r.life.ledger.coins==12 and r.life.ledger.spirit==6)
    response_results.append({"monster_id":mid,"actual_path":route["path"],"distance":route["distance"],
                             "response_seconds":str(r.plan["route_seconds"]+r.plan["work_seconds"]),
                             "final_phase":r.phase,"coins":r.life.ledger.coins,"spirit":r.life.ledger.spirit,
                             "q125_is_counterexample_state_not_claimed_live_acquisition":True})

# Newly discovered F17 NPC pickup starvation is closed only for its original parcel.
f17=next(m for m in _read("monster_folklore_md01.json")["monsters"] if m["id"]=="F17")
legacy=LifeState(f17,root="f17-unprotected-counterexample")
legacy.add_poison(125);legacy.apply_damage(10000,"physical");legacy.advance(Fraction(9,2))
restored_hp=legacy.hp
for _ in range(2):legacy.advance(1);legacy.poison_tick(1)
required_pickup=nav.travel_seconds("parcel_guest_start","pickup_shelf",speed=3.3)+2
check("F17 q125 unprotected activity is shorter than real pickup path and work",
      restored_hp==Fraction(115,2) and legacy.state=="suppressed" and required_pickup>2)


def parcel_fixture(**kwargs):
    return ParcelResponseReference(f17,nav,"root:f17","attempt:1","actor:f17","original:parcel:1",
                                   "parcel_guest_start",kwargs.pop("deadline",60),**kwargs)


def parcel_facts(r):
    return {"evidence_origin":"world_adapter","root_id":r.life.root,"attempt_id":r.attempt_id,
            "actor_id":r.actor_id,"parcel_id":r.parcel_id,"knots_open":3,"parcel_owner":"pickup_slot",
            "parcel_position":[19.5,26.5],"player_position":nav.position("parcel_retreat"),
            "control_active":False,"normal_human":False}


for key,value in [("evidence_origin","ui"),("root_id","other"),("attempt_id","stale"),
                  ("actor_id","other_actor"),("parcel_id","clone"),("knots_open",2),
                  ("parcel_owner","player"),("parcel_position",[18.5,26.5]),
                  ("player_position",[19.5,25.5]),("control_active",True),("normal_human",True)]:
    r=parcel_fixture();p=parcel_facts(r);p[key]=value
    check("F17 rejects unsupported actual predicate "+key,not r.enter(p))
r=parcel_fixture();r.life.apply_damage(10000)
check("F17 cannot clear existing suppression to start pickup",not r.enter(parcel_facts(r)))
r=parcel_fixture(timed_states={"freeze":2})
check("F17 actual saved freeze overrides an incorrect clear UI flag",not r.enter(parcel_facts(r)))
r.elapse(2,parcel_facts(r))
check("F17 can start after original freeze naturally expires",r.enter(parcel_facts(r)))
r=parcel_fixture(deadline=3)
check("F17 cannot extend short original deadline",not r.enter(parcel_facts(r)))
r=parcel_fixture(slow_fraction=.99,timed_states={"slow":1,"old_chill":.5},
                 maturities=[{"id":"prepaid-dose","due":1,"amount":1}])
r.life.hp=Fraction(115,2);r.life.add_poison(125);p=parcel_facts(r)
check("F17 original parcel enters limited response",r.enter(p))
check("F17 rejects duplicate protection entry",not r.enter(p))
check("F17 malformed 99 percent slow still obeys existing global 60 percent cap",r.slow_fraction==Fraction(3,5))
check("F17 response stops only own attacks",not r.attack_allowed())
check("F17 protected poison and electric feedback cannot pay damage",
      r.poison_tick(1)==0 and r.damage(100,"spiritual",electric_charge=1)==0 and r.life.hp==Fraction(115,2) and r.life.charge==0)
r.elapse(.5,p)
check("F17 actual slowed path travels 0.66 tiles in first half second",r.distance_done==Fraction(33,50))
check("F17 finite chill expires against absolute world time","old_chill" not in r.timed_states)
clone=r.clone_saved_state()
r.elapse(.5,p);clone.elapse(.5,p)
check("F17 paid dose matures once without clearing original q",r.life.poison==126 and r.maturities[0]["applied"])
check("F17 actual slow expires without resetting original response clock","slow" not in r.timed_states and r.now==1)
check("F17 finite saved response retains route/progress/maturity",r.position==clone.position and r.life.poison==clone.life.poison and r.protection_used==clone.protection_used)
while r.phase!="complete" and r.now<10:
    r.elapse(Fraction(1,10),p);clone.elapse(Fraction(1,10),p)
    if r.phase!="complete":check("F17 protected q125 path at "+str(r.now),r.poison_tick(Fraction(1,10))==0)
check("F17 actual original pickup completes once despite high q",
      r.phase=="complete" and r.work_done==2 and r.item_owner==r.actor_id and r.life.ledger.coins==12)
check("F17 pickup terminal clears pool poison only at actual terminal",r.life.poison==0)
check("F17 response save branch yields identical actual result",r.trace==clone.trace and r.position==clone.position and r.life.ledger.coins==clone.life.ledger.coins)
check("F17 terminal replay cannot pay again",not r.enter(p) and r.life.ledger.coins==12)
r=parcel_fixture();p=parcel_facts(r);r.enter(p);r.elapse(.25,p)
spent=r.protection_used;plan=r.plan.copy();bad=dict(p);bad["player_position"]=[19.5,25.5]
r.elapse(.1,bad)
check("F17 losing actual retreat ends protection immediately",not r.protected and r.phase=="interrupted")
check("F17 interrupted work cannot rebind original parcel",not r.enter({**p,"parcel_id":"new"}))
check("F17 correct original object may resume spent immutable plan",r.enter(p) and r.protection_used==spent and r.plan==plan)
other=LifeState(f17,root="independent-other-root")
check("F17 response grants no blanket enemy immunity",other.apply_damage(10)>0)
response_results.append({"monster_id":"F17","actual_path":nav.route("parcel_guest_start","pickup_shelf")["path"],
                         "distance":3,"baseline_travel_and_collect_seconds":required_pickup,
                         "legacy_q125_active_seconds_before_suppression":2,
                         "protected_response_slow_cap":.6,"maturities_and_absolute_timers_tested":True,
                         "same_root_only":True,"q125_is_counterexample_state_not_claimed_live_acquisition":True})

report={"version":"BC01","status":"passed" if all(c["passed"] for c in checks) else "failed",
        "scope":"actual assembled grid/body/LOS, serial mechanism scheduling, fail-closed admission, SA02 response regressions; not full enemy AI or victory rate",
        "counts":{"passed":sum(c["passed"] for c in checks),"failed":sum(not c["passed"] for c in checks),
                  "placed_operation_roles":len(nav.anchors),"admission_catalog":len(all_ids),"geometry_reference_cases":len(catalog),
                  "director_reference_cases":len(encounter_catalog()),"blocked_cases":sum(not r["geometry_reference_admitted"] for r in cfg["encounter_admission"]),
                  "unordered_pair_guard_cases":evaluated,"conditional_pairs_allowed":len(accepted),
                  "one_cell_temporary_placements":len(one),"two_cell_rotated_placements":len(two)},
        "anchor_routes":anchor_routes,"customer_routes":customer_routes,"work_routes":work_routes,
        "finite_encounter_plans":plans,"existing_tower_projection_noninterference":projection,
        "temporary_trap_placements":{"one_cell":one,"two_cell":two},"conditional_pairs":accepted,
        "mapped_response_regressions":response_results,"checks":checks,
        "source_sha256":{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (
            ROOT/'content/maps.json',ROOT/'content/map_mechanics_v05.json',ROOT/'content/map_composition_bc01.json',
            ROOT/'scripts/bc01_map_reference.py')},
        "open_runtime_work":["production adapters for real original-object predicates and hostile AI",
                             "moving enemy attack/dodge timing and all larger collision bodies",
                             "93 unadapted catalog entries stay closed until placed and verified"]}
(ROOT/'docs/bc01_map_report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({"status":report["status"],**report["counts"]},ensure_ascii=False))
for row in checks:
    if not row["passed"]:print("FAIL",row["name"])
raise SystemExit(0 if report["status"]=="passed" else 1)
