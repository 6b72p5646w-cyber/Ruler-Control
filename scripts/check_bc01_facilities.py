#!/usr/bin/env python3
"""Finite BC01 facility counterexamples and a routed reference integration.

This exercises design code, never claims that production NPCs/HP/physics exist.
"""
from copy import deepcopy
import hashlib
import json
from pathlib import Path

from bc01_facility_reference import FacilitiesBC01, load_contract
from bc01_map_reference import StoreMap, encounter_catalog
from bc01_director_reference import run_night

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = load_contract()
RESULTS = []
EVIDENCE = {}


def expect(value, message="unexpected result"):
    if not value:
        raise AssertionError(message)


def check(name, fn):
    try:
        fn()
        RESULTS.append({"name": name, "passed": True})
    except Exception as error:
        RESULTS.append({"name": name, "passed": False, "error": f"{type(error).__name__}: {error}"})


def model(*, attempt=1, seed=3, at=10):
    result = FacilitiesBC01("night1", attempt, seed, design_simulation=True)
    expect(result.actual_world_tick("initial", at, True)["ok"])
    return result


def request(m, fid="FR01", number=1, *, all_products=False):
    """Explicit bounded test facts; the separate Director case derives real ones."""
    night, attempt, now = m.state["night_id"], m.state["attempt_id"], m.state["now"]
    customer = f"bc01:{night}:{attempt}:customer:{number}"
    order = f"bc01:{night}:{attempt}:order:{number}"
    item = f"bc01:{night}:{attempt}:store_item:{number}"
    products = ["FR02", "FR03", "FR04", "FR05"] if all_products else [fid if fid in {"FR02", "FR03", "FR04", "FR05"} else "FR02"]
    used = [{"facility_id": x, "actual_use_at": now - 1, "usage_kind": m.roles[x]["usage_kind"], "source_item_id": item + x} for x in products]
    used.append({"facility_id": "FR01", "actual_use_at": now, "usage_kind": "checkout", "source_item_id": item})
    receipt = {"event_id": order + ":paid", "order_id": order, "customer_id": customer,
               "logical_customer_id": json.dumps(["bc01", night, "customer", number], separators=(",", ":")),
               "logical_order_id": json.dumps(["bc01", night, "order", number], separators=(",", ":")),
               "night_id": night, "attempt_id": attempt, "paid": True, "verified": True,
               "payment_kind": "ordinary_store_sale", "completed_at": now, "normal_customer": True,
               "items": [{"sku": "sku" + x, "facility_id": x, "source_item_id": item + x, "quantity": 1} for x in products],
               "facilities_used": used}
    return {"event_id": order + ":facility:" + fid, "customer_id": customer,
            "facility_id": fid, "paid_order_receipt": receipt, "night_id": night, "attempt_id": attempt,
            "facts": {"actual_use_completed": True, "normal_customer": True, "customer_kind": "normal",
                      "consumer_registered": True, "facility_geometry_bound": True,
                      "same_order_service": True, "source_item_owner_customer": True,
                      "route_service_authorized": True, "progress_complete": True,
                      "usage_kind": m.roles[fid]["usage_kind"], "actual_use_at": now - 1 if fid in products else now,
                      "source_item_id": item + fid if fid in products else item,
                      "use_duration_s": 0 if fid == "FR10" else max(.9, m.roles[fid]["authored_base_use_seconds"]),
                      "exit_boundary_crossed": fid == "FR10"}}


def use(m, fid="FR01", number=1):
    result = m.customer_use(**request(m, fid, number))
    expect(result["ok"], result)
    return result


def advance(m, to, alive=True, **kwargs):
    result = m.actual_world_tick(f"tick:{len(m.state['event_receipts'])}:{to}", to, alive, **kwargs)
    expect(result["ok"], result)
    return result


def active_kind(m, kind):
    return [e for e in m.active_modifiers() if e["reward"]["kind"] == kind]


def rejects_fact(field, value, fid="FR03"):
    m = model()
    req = request(m, fid)
    req["facts"][field] = value
    before = m.snapshot()
    expect(not m.customer_use(**req)["ok"])
    expect(m.snapshot() == before, "rejected use mutated credit or payment state")


def source_contract():
    original = json.loads((ROOT / "content/traps_facilities_td05.json").read_text())
    by_id = {r["id"]: r for r in original["traps"]}
    for variant in CONTRACT["temporary_traps"]["type_pool"]:
        source = by_id[variant["source_trap"]]
        expect(variant["footprint"] in source["footprint_variants"])
        expect(variant["durability"] == source["durability"])
        expect(all(source["base_parameters"][key] == value for key, value in variant["effect"].items()))
    expect(original["shared_contract"]["placement"]["max_objects"] == 8)
    expect(original["shared_contract"]["placement"]["max_footprint_cells"] == 16)
    store = json.loads((ROOT / "content/store_systems_v05.json").read_text())
    expect(store["work_contract"]["normal_checkout_seconds"] == CONTRACT["roles"][0]["authored_base_use_seconds"])


def mapped_roles():
    world = StoreMap()
    expect(len(CONTRACT["roles"]) == 14 and len({r["id"] for r in CONTRACT["roles"]}) == 14)
    for role in CONTRACT["roles"]:
        expect(len(world.position(role["anchor"])) == 2, role["anchor"])
    expect([r["id"] for r in CONTRACT["roles"] if r["reward"] is None] == ["FR07", "FR08"])
    expect(world.position("public_supplies") == [22.5, 21.5])
    expect(world.position("customer_freezer") != world.position("freezer_main"))


def default_disabled():
    m = FacilitiesBC01("night1", 1)
    before = m.snapshot()
    expect(not m.actual_world_tick("tick", 1, True)["ok"])
    expect(not m.raid_started("raid1")["ok"])
    expect(before == m.snapshot())
    expect(CONTRACT["runtime_enabled"] is False and CONTRACT["runtime_integrated"] is False)


def invalid_attempt():
    for attempt in (True, False, 0, -1, "1"):
        try:
            FacilitiesBC01("night1", attempt)
        except ValueError:
            continue
        raise AssertionError(f"accepted attempt {attempt!r}")


def payment_rejection(kind):
    m = model(); req = request(m, "FR03"); receipt = req["paid_order_receipt"]
    if kind == "unpaid": receipt["paid"] = False
    if kind == "unverified": receipt["verified"] = False
    if kind == "wrong_attempt": receipt["attempt_id"] = 2
    if kind == "bool_attempt": receipt["attempt_id"] = True
    if kind == "wrong_customer": receipt["customer_id"] = "different"
    if kind == "personal_stock": receipt["items"] = []
    if kind == "malformed_stock": receipt["items"] = "items"
    if kind == "missing_logical_identity": del receipt["logical_order_id"]
    if kind == "source_use_mismatch": receipt["facilities_used"][0]["actual_use_at"] -= 1
    before = m.snapshot()
    expect(not m.customer_use(**req)["ok"], kind)
    expect(before == m.snapshot(), kind)


def accelerated_completion():
    m = model(); req = request(m, "FR01"); req["facts"]["use_duration_s"] = .9
    expect(m.customer_use(**req)["ok"], "completed .6x checkout was rejected")


def dedupe():
    m = model(); req = request(m, "FR03")
    expect(m.customer_use(**req)["ok"])
    before = m.snapshot()
    expect(m.customer_use(**req)["reason"] == "event_replay")
    changed = deepcopy(req); changed["facts"]["use_duration_s"] = 3
    expect(m.customer_use(**changed)["reason"] == "event_id_conflict")
    changed = deepcopy(req); changed["event_id"] += ":other"
    expect(m.customer_use(**changed)["reason"] == "same_paid_customer_facility_already_processed")
    expect(before == m.snapshot())


def immutable_payment_and_logical_ids():
    m = model(); req = request(m, "FR03"); expect(m.customer_use(**req)["ok"])
    other = request(m, "FR01")
    other["paid_order_receipt"] = deepcopy(req["paid_order_receipt"])
    other["paid_order_receipt"]["items"][0]["quantity"] = 2
    expect(m.customer_use(**other)["reason"] == "payment_receipt_changed")
    changed = request(m, "FR01", 2)
    changed["paid_order_receipt"]["logical_customer_id"] = req["paid_order_receipt"]["logical_customer_id"]
    expect(m.customer_use(**changed)["reason"] == "logical_identity_binding_changed")


def services_and_natural_events():
    m = model(); paid = request(m, "FR03", all_products=True)["paid_order_receipt"]
    outcomes = []
    for fid in ("FR03", "FR05", "FR06", "FR01", "FR10"):
        req = request(m, fid, all_products=True); req["paid_order_receipt"] = deepcopy(paid)
        outcomes.append(m.customer_use(**req))
    expect([x["ok"] for x in outcomes] == [True, True, False, True, True])
    expect(outcomes[2]["reason"] == "optional_service_limit")


def bank_limits():
    m = model(); use(m, "FR03", 1); use(m, "FR03", 2)
    old = deepcopy(m.state["bank"]["FR03"])
    expect(use(m, "FR03", 3)["reason"] == "use_completed_bank_full_no_replacement")
    expect(m.state["bank"]["FR03"] == old)
    expect(m.raid_started("raid1")["ok"])
    req = request(m, "FR03", 3); req["event_id"] += ":retry"
    expect(not m.customer_use(**req)["ok"], "overflow was reclaimed after space opened")
    m = model()
    for number, fid in enumerate(("FR01", "FR02", "FR03", "FR04", "FR05", "FR06", "FR10", "FR11"), 1):
        use(m, fid, number)
    expect(m._bank_total() == 8)
    expect(use(m, "FR12", 9)["reason"] == "use_completed_bank_full_no_replacement")
    expect(m._bank_total() == 8)


def not_immediate_raid_reward():
    m = model(); m.raid_started("raid1"); use(m, "FR03")
    expect(not active_kind(m, "hp_regen"))
    expect(m.raid_ended("raid1")["ok"])
    m.raid_started("raid2"); expect(active_kind(m, "hp_regen"))


def same_source_two_tokens():
    m = model(); use(m, "FR03", 1); use(m, "FR03", 2); m.raid_started("raid1")
    effects = active_kind(m, "hp_regen")
    expect(len(effects) == 1 and effects[0]["expires_at"] == 30 and effects[0]["reward"]["value"] == .008)
    healed = advance(m, 30)["requests"]
    expect(abs(sum(r["actual_alive_raid_seconds"] * r["fraction_max_hp_per_second"] for r in healed) - .16) < 1e-8)
    expect(not active_kind(m, "hp_regen"))


def same_group_strongest():
    for seed in range(20):
        m = model(seed=seed); chosen = use(m, "FR14")
        if chosen["token"]["reward"]["kind"] == "hp_regen": break
    else: raise AssertionError("deterministic draw sample lacked regen")
    use(m, "FR03", 2); m.raid_started("raid1")
    expect(len(active_kind(m, "hp_regen")) == 1)
    reqs = advance(m, 20)["requests"]
    expect(abs(sum(r["actual_alive_raid_seconds"] * r["fraction_max_hp_per_second"] for r in reqs) - .08) < 1e-8)


def off_before_activation():
    m = model(); use(m, "FR03"); m.power_changed("off", "MAIN", False); m.raid_started("raid1")
    expect(not active_kind(m, "hp_regen") and len(m.state["bank"]["FR03"]) == 1)
    m.power_changed("on", "MAIN", True); expect(not active_kind(m, "hp_regen"))
    m.raid_ended("raid1"); m.raid_started("raid2"); expect(active_kind(m, "hp_regen"))


def power_no_catchup():
    m = model(); use(m, "FR03"); use(m, "FR05", 2); use(m, "FR11", 3); m.raid_started("raid1")
    first = advance(m, 12)["requests"]
    m.power_changed("off", "MAIN", False)
    expect(not active_kind(m, "hp_regen") and not active_kind(m, "move_speed_bonus"))
    expect(active_kind(m, "soft_slow_resistance") and not m.electric_overload_allowed())
    expect(not advance(m, 16)["requests"])
    m.power_changed("on", "MAIN", True)
    expect(active_kind(m, "hp_regen")[0]["expires_at"] == 20)
    last = advance(m, 21)["requests"]
    total = sum(r["actual_alive_raid_seconds"] * r["fraction_max_hp_per_second"] for r in first + last)
    expect(abs(total - .048) < 1e-8, "healed outage seconds or refreshed expiry")
    expect(not active_kind(m, "hp_regen"))


def expired_off_never_revives():
    m = model(); use(m, "FR03"); m.raid_started("raid1"); m.power_changed("off", "C2", False)
    advance(m, 23); m.power_changed("on", "C2", True)
    expect(not m.active_modifiers() and not advance(m, 24)["requests"])


def circuit_locality():
    m = model(); use(m, "FR01"); use(m, "FR03", 2); m.raid_started("raid1")
    m.power_changed("off-c1", "C1", False)
    expect(not active_kind(m, "direct_damage_reduction") and active_kind(m, "hp_regen"))
    expect(m.electric_overload_allowed())
    m.power_changed("off-c2", "C2", False); expect(not m.electric_overload_allowed())


def source_off_when_used():
    m = model(at=7); m.power_changed("off", "C2", False); advance(m, 10)
    req = request(m, "FR03"); m.power_changed("on", "C2", True)
    expect(m.customer_use(**req)["reason"] == "source_was_unpowered_during_use")


def typed_owner_and_ack():
    m = model(); use(m, "FR03"); use(m, "FR13", 2); m.raid_started("raid1")
    requests = advance(m, 11)["requests"]
    expect(requests[0]["request_type"] == "hp_regen_interval")
    expect(not any(k in m.state for k in ("hp", "max_hp", "coin", "wallet", "xp", "stamina")))
    r = requests[0]; expect(m.acknowledge(r["request_id"])["ok"])
    expect(m.acknowledge(r["request_id"])["ok"])
    expect(r["request_id"] not in [q["request_id"] for q in m.pending_requests()])


def survival_boundaries():
    m = model(); use(m, "FR10"); m.raid_started("raid1")
    expect(not advance(m, 24.999)["requests"])
    payout = advance(m, 25)["requests"]
    expect(len(payout) == 1 and payout[0]["coin"] == payout[0]["xp"] == 1)
    expect(m.state["survival_payouts"] == 1)
    m.power_changed("off", "MAIN", False); advance(m, 40)
    expect(m.state["survival_payouts"] == 2 and m.state["survival_remaining"] == 0)


def survival_pause_death_business():
    m = model(); use(m, "FR10"); advance(m, 15)
    expect(m.state["survival_progress"] == 0)
    m.raid_started("raid1")
    expect(not m.actual_world_tick("bad-pause", 20, True, True)["ok"])
    advance(m, 15, paused=True); advance(m, 20, alive=False)
    expect(m.state["survival_remaining"] == 30 and m.state["survival_progress"] == 0)
    advance(m, 25); m.raid_ended("raid1"); advance(m, 100); m.raid_started("raid2"); advance(m, 110)
    expect(m.state["survival_payouts"] == 1 and m.state["survival_remaining"] == 15)


def survival_cap():
    m = model(); number = 1
    for raid in range(3):
        use(m, "FR10", number); use(m, "FR10", number + 1); number += 2
        m.raid_started(f"raid{raid}"); advance(m, m.state["now"] + 60); m.raid_ended(f"raid{raid}")
    expect(m.state["survival_payouts"] == 12)
    expect(use(m, "FR10", number)["reason"] == "use_completed_survival_night_cap")
    expect(m.state["survival_remaining"] == m.state["survival_progress"] == 0)


def deadline_keeps_actual_buff_clock():
    m = model(at=715); use(m, "FR10"); use(m, "FR03", 2); m.raid_started("late")
    first = advance(m, 720, eligibility_cutoff=720)["requests"]
    last = advance(m, 725, eligibility_cutoff=720)["requests"]
    expect(m.state["survival_progress"] == 5 and m.state["survival_remaining"] == 25)
    expect(m.state["survival_payouts"] == 0 and not active_kind(m, "hp_regen"))
    expect(abs(sum(r["actual_alive_raid_seconds"] * r["fraction_max_hp_per_second"] for r in first + last) - .08) < 1e-8)
    expect(not m.actual_world_tick("extend-credit-cutoff", 730, True, eligibility_cutoff=800)["ok"])


def saved_model_replay():
    m = model(); use(m, "FR03"); use(m, "FR10", 2); m.raid_started("raid1"); advance(m, 16)
    restored = FacilitiesBC01.restore(json.loads(json.dumps(m.snapshot())), design_simulation=True)
    expect(advance(m, 25) == advance(restored, 25))
    expect(m.snapshot() == restored.snapshot())
    expect(not restored.raid_started("raid1")["ok"])


def trap_model(*, attempt=1, desired=None, tokens=1):
    for seed in range(30):
        m = model(attempt=attempt, seed=seed)
        use(m, "FR02")
        if desired is None or m.state["bank"]["FR02"][0]["trap_variant"] == desired:
            if tokens == 2: use(m, "FR02", 2)
            m.raid_started("bc01:night1:raid:1")
            return m
    raise AssertionError("no fixed seed for variant")


def propose(m, *, only_rotation=None, **overrides):
    token = m.state["bank"]["FR02"][0]
    variant = next(v for v in CONTRACT["temporary_traps"]["type_pool"] if v["id"] == token["trap_variant"])
    values = {"object_count": 0, "footprint_cells": 0, "nav_revision": "geometry:same-v1", "safe_current_world": True}
    values.update(overrides)
    places = StoreMap().safe_trap_placements(footprint=variant["footprint"], object_count=values["object_count"], footprint_count=values["footprint_cells"])
    if only_rotation is not None: places = [p for p in places if p["rotation"] == only_rotation]
    return m.propose_trap(places, **values)


def accept(m, request, iid="temp1", **overrides):
    values = {"actual_instance_id": iid, "current_nav_revision": request["nav_revision"],
              "actual_safe_world_placement": True, "total_objects_after": 1,
              "total_footprint_after": len(request["placement"]["cells"])}
    values.update(overrides)
    return m.trap_placement_ack(request["request_id"], True, **values)


def trap_safe_rotation():
    m = trap_model(desired="BC_GIFT_R01")
    result = propose(m, only_rotation=90, object_count=7, footprint_cells=14)
    expect(result["ok"], result)
    req = result["request"]
    expect(req["placement"]["footprint"] == [2, 1] and len(req["placement"]["cells"]) == 2)
    expect(len(m.state["bank"]["FR02"]) == 1)
    expect(accept(m, req, total_objects_after=8, total_footprint_after=16)["ok"])
    expect(not m.state["bank"]["FR02"] and m.state["active_trap"])


def trap_bad_shape():
    m = trap_model(desired="BC_GIFT_R01")
    place = StoreMap().safe_trap_placements(footprint=(1, 2))[0]
    place["cells"] = [place["origin_cell"], [place["origin_cell"][0] + 3, place["origin_cell"][1]]]
    r = m.propose_trap([place], object_count=0, footprint_cells=0, nav_revision="g1", safe_current_world=True)
    expect(not r["ok"] and len(m.state["bank"]["FR02"]) == 1)


def trap_capacity_geometry(which):
    m = trap_model(desired="BC_GIFT_R01")
    kwargs = {"object_count": 8} if which == "object" else {"footprint_cells": 15} if which == "footprint" else {"safe_current_world": False}
    expect(not propose(m, **kwargs)["ok"])
    expect(len(m.state["bank"]["FR02"]) == 1)


def trap_failed_ack_no_reroll():
    m = trap_model(); req = propose(m)["request"]
    expect(not accept(m, req, current_nav_revision="changed-world")["ok"])
    expect(len(m.state["bank"]["FR02"]) == 1)
    advance(m, 11); again = propose(m)["request"]
    expect(req["variant"] == again["variant"] and req["placement"] == again["placement"])
    expect(not m.acknowledge(again["request_id"])["ok"])
    expect(accept(m, again)["ok"])
    expect(not accept(m, again)["ok"])


def trap_pending_reservation():
    m = trap_model(tokens=2); first = propose(m)["request"]; second = propose(m)["request"]
    expect(first == second and len(m.state["bank"]["FR02"]) == 2)
    expect(accept(m, first)["ok"])
    expect(not propose(m)["ok"], "second temporary instance overlapped first")


def legal_entry():
    return {k: True for k in ("actual_new_entry", "actual_collision", "manifested", "hostile", "independent_pool", "ground_layer", "world_consumer_verified")}


def trap_arming_and_target():
    m = trap_model(); accept(m, propose(m)["request"])
    expect(not m.trap_triggered("early", "temp1", "pool1", legal_entry())["ok"])
    advance(m, 10.5)
    for bad in ("hostile", "manifested", "independent_pool", "ground_layer", "actual_new_entry"):
        facts = legal_entry(); facts[bad] = False
        expect(not m.trap_triggered("bad:" + bad, "temp1", "pool1", facts)["ok"])
    expect(not m.trap_triggered("missing-pool", "temp1", "", legal_entry())["ok"])
    result = m.trap_triggered("good", "temp1", "pool1", legal_entry())
    expect(result["ok"] and m.state["active_trap"] is None)
    effect = result["requests"][0]
    expect(effect["origin_kind"] == "facility_secondary" and effect["may_trigger_equipment_procs"] is False)
    expect(not m.trap_triggered("replay", "temp1", "pool1", legal_entry())["ok"])


def trap_no_inventory_conversion():
    m = trap_model(); accept(m, propose(m)["request"])
    for action in ("sell", "pack", "refill", "repair", "upgrade", "drop", "refund"):
        r = m.temporary_inventory_action(action, "temp1")
        expect(not r["ok"] and r["refund"] == r["inventory_items"] == 0)


def trap_destroy_expire_and_cooldown():
    m = trap_model(tokens=2); accept(m, propose(m)["request"])
    expect(not m.trap_destroyed("fake", "temp1")["ok"])
    expect(m.trap_destroyed("actual", "temp1", actual_world_destruction=True)["ok"])
    expect(not propose(m)["ok"])
    advance(m, 16); accept(m, propose(m)["request"], "temp2")
    advance(m, 36); expect(m.state["active_trap"] is None)
    removes = [r for r in m.pending_requests() if r["request_type"] == "remove_temporary_trap"]
    expect([r["reason"] for r in removes] == ["actual_world_destruction", "expiry"])


def trap_rng_retry_and_snapshot():
    first, second = trap_model(attempt=1), trap_model(attempt=2)
    t1, t2 = first.state["bank"]["FR02"][0], second.state["bank"]["FR02"][0]
    expect(t1["token_id"] != t2["token_id"] and t1["stable_source_key"] == t2["stable_source_key"])
    p1, p2 = propose(first)["request"], propose(second)["request"]
    expect(p1["variant"] == p2["variant"] and p1["placement"] == p2["placement"])
    saved = FacilitiesBC01.restore(json.loads(json.dumps(first.snapshot())), design_simulation=True)
    expect(propose(saved)["request"] == p1)


def raid_and_night_cleanup():
    m = trap_model(tokens=2); use(m, "FR03", 3); accept(m, propose(m)["request"])
    expect(m.raid_ended(m.state["raid_id"])["ok"])
    expect(m.state["active_trap"] is None and len(m.state["bank"]["FR02"]) == 1)
    m.raid_started("raid2"); expect(active_kind(m, "hp_regen"))
    expect(m.night_ended()["ok"])
    expect(m._bank_total() == 0 and not m.active_modifiers() and not m.actual_world_tick("after-night", 99, True)["ok"])


def actual_director_receipts():
    report = run_night(3, StoreMap(), night_index=7, attempt_id=1, action_duration_factor=.6,
                       encounter_pool=[p for p in encounter_catalog(7) if not p["requires_combat_after_rule"]])
    m = FacilitiesBC01(report["summary"]["night_id"], 1, seed=3, design_simulation=True)
    counts, rejections, minimum_checkout = {}, [], 2
    for index, event in enumerate(report["events"]):
        if event["time"] > m.state["now"]:
            advance(m, event["time"], eligibility_cutoff=720)
        kind = event["kind"]
        if kind == "facility_use_committed":
            req = event["request"]; result = m.customer_use(**req)
            counts[req["facility_id"]] = counts.get(req["facility_id"], 0) + 1
            if not result["ok"]: rejections.append(result)
            if req["facility_id"] == "FR01": minimum_checkout = min(minimum_checkout, req["facts"]["use_duration_s"])
        elif kind == "raid_started": expect(m.raid_started(event["raid_id"])["ok"])
        elif kind == "raid_ended": expect(m.raid_ended(event["raid_id"])["ok"])
        elif kind == "power_changed": expect(m.power_changed("power:" + str(index), "MAIN", event["power_on"])["ok"])
    expect(not rejections, rejections)
    expect(report["summary"]["paid_orders"] > 0 and counts.get("FR10") == report["summary"]["paid_orders"])
    expect(minimum_checkout < 1.5 and counts.get("FR01") == counts.get("FR10"))
    expect(not any(fid in counts for fid in ("FR06", "FR07", "FR08", "FR09", "FR11", "FR12", "FR13", "FR14")))
    EVIDENCE["routed_director_slice"] = {"seed": 3, "night_index": 7, "attempt_id": 1,
        "manual_action_factor": .6, "paid_orders": report["summary"]["paid_orders"], "accepted_use_counts": counts,
        "rejected_use_count": len(rejections), "minimum_actual_checkout_seconds": minimum_checkout,
        "facility_survival_payout_requests": m.state["survival_payouts"],
        "geometry_from_bc01_map": True, "production_npc_or_world_adapter": False}


def run():
    check("default adapter remains disabled without state mutation", default_disabled)
    check("attempt is an exact positive integer, never bool or coerced string", invalid_attempt)
    check("14 mapped responsibilities preserve control-only facilities and public areas", mapped_roles)
    check("gift shape, base effects, durability and shared capacity read real TD05 sources", source_contract)
    for key, value in (("normal_customer", False), ("customer_kind", "monster"), ("actual_use_completed", False),
                       ("consumer_registered", False), ("facility_geometry_bound", False), ("same_order_service", False),
                       ("source_item_owner_customer", False), ("route_service_authorized", False),
                       ("progress_complete", False), ("origin_kind", "facility_secondary")):
        check("reject unproven or recursive actual use: " + key, lambda key=key, value=value: rejects_fact(key, value))
    for kind in ("unpaid", "unverified", "wrong_attempt", "bool_attempt", "wrong_customer", "personal_stock", "malformed_stock", "missing_logical_identity", "source_use_mismatch"):
        check("reject invalid paid source: " + kind, lambda kind=kind: payment_rejection(kind))
    for name, fn in [
        ("completed accelerated checkout uses real progress rather than fixed 1.5 seconds", accelerated_completion),
        ("event replay, payload conflict and changed event ID cannot duplicate a use", dedupe),
        ("immutable payment and unique logical identities prevent rebinding", immutable_payment_and_logical_ids),
        ("two optional services permit natural checkout and actual exit separately", services_and_natural_events),
        ("per-source two and total eight overflow never replaces, refreshes or defers", bank_limits),
        ("customer use during raid waits for the subsequent actual raid", not_immediate_raid_reward),
        ("two same-source credits extend time without doubling regen magnitude", same_source_two_tokens),
        ("lucky and hot-food regeneration take strongest live source", same_group_strongest),
        ("powered-off source bank waits for a later raid, not restart midraid", off_before_activation),
        ("outage stops powered buffs and overload with no missed healing or expiry refresh", power_no_catchup),
        ("restoring power after original expiry never revives a buff", expired_off_never_revives),
        ("local circuit loss disables its sources and respects actual C2 overload", circuit_locality),
        ("delayed payment cannot turn an unpowered historical use into credit", source_off_when_used),
        ("typed HP and stamina requests leave actual resource ownership to root", typed_owner_and_ack),
        ("survival credit grants exactly one coin and XP per fifteen alive seconds", survival_boundaries),
        ("pause, death and business earn nothing; partial raid credit persists", survival_pause_death_business),
        ("survival facility payout stops at twelve per logical night", survival_cap),
        ("720-second eligibility cutoff preserves overtime buff deadlines and healing", deadline_keeps_actual_buff_clock),
        ("snapshot continuation is identical and raid restart cannot duplicate effects", saved_model_replay),
        ("actual map permits the full rotated 1x2 footprint within shared 8/16 caps", trap_safe_rotation),
        ("two separated cells cannot masquerade as a 1x2 footprint", trap_bad_shape),
        ("failed actual placement keeps fixed type and consumes no charge", trap_failed_ack_no_reroll),
        ("one pending reservation and one live temporary object prevent parallel bypass", trap_pending_reservation),
        ("warning boundary and real hostile ground-pool entry gate one trap effect", trap_arming_and_target),
        ("temporary trap cannot become money, inventory, repair or refill", trap_no_inventory_conversion),
        ("destruction, six-second interval and twenty-second expiry have no refund", trap_destroy_expire_and_cooldown),
        ("same logical source across attempts keeps gift type and legal site; reload does not reroll", trap_rng_retry_and_snapshot),
        ("raid and night cleanup remove actual temporary support without refunds", raid_and_night_cleanup),
        ("real routed Director paid and exited customers feed unmodified receipts", actual_director_receipts),
    ]:
        check(name, fn)
    for kind in ("object", "footprint", "geometry"):
        check("unavailable actual trap " + kind + " retains original charge", lambda kind=kind: trap_capacity_geometry(kind))


if __name__ == "__main__":
    run()
    paths = ["content/facilities_bc01.json", "scripts/bc01_facility_reference.py",
             "scripts/check_bc01_facilities.py", "content/traps_facilities_td05.json",
             "content/store_systems_v05.json", "content/map_composition_bc01.json",
             "scripts/bc01_map_reference.py", "content/director_bc01.json", "scripts/bc01_director_reference.py"]
    passed = sum(r["passed"] for r in RESULTS)
    report = {"version": "BC01", "scope": "finite executable customer-service design reference",
              "status": "pass" if passed == len(RESULTS) else "fail", "passed": passed, "total": len(RESULTS),
              "runtime_enabled": False, "runtime_integrated": False, "actual_game_adapter": False,
              "evidence": EVIDENCE, "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in paths},
              "checks": RESULTS,
              "not_proven": ["production game NPC/physics/HP/wallet integration", "remaining public-service NPC consumers",
                             "full game balance or first-week difficulty", "all monster interactions", "save migration in production"]}
    (ROOT / "docs/bc01_facility_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": passed, "total": len(RESULTS), "status": report["status"],
                      "failures": [r for r in RESULTS if not r["passed"]], "evidence": EVIDENCE}, ensure_ascii=False, indent=2))
    raise SystemExit(0 if passed == len(RESULTS) else 1)
