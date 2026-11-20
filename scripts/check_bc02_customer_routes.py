#!/usr/bin/env python3
"""Actual public route/object-chain checks, never a claim of production NPC AI."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from bc01_map_reference import StoreMap
from bc02_customer_reference import CustomerRoutesBC02, CustomerStoreMapBC02, reference_employer_manifest, load_contract
from bc02_facility_reference import FacilitiesBC02

ROOT = Path(__file__).resolve().parents[1]
RESULTS, EVIDENCE = [], {"profiles": [], "actual_client_runtime": False, "full_arrival_director": False}


def expect(value, message="unexpected result"):
    if not value:
        raise AssertionError(message)


def check(name, fn):
    try:
        fn(); RESULTS.append({"name": name, "passed": True})
    except Exception as error:
        RESULTS.append({"name": name, "passed": False, "error": f"{type(error).__name__}: {error}"})


def make(profile="drink_return", *, night="n1", units=None, navigation=None, open_now=True):
    r = CustomerRoutesBC02(night, 1, reference_employer_manifest(night, units),
                          navigation=navigation, design_simulation=True)
    if profile == "parcel_verified":
        expect(r.prepare_parcel(f"employer:{night}:goods:1", f"employer:{night}:parcel_bag:1")["ok"])
    expect(r.choose_preferences([profile])["ok"])
    if open_now:
        expect(r.open_business()["ok"])
    return r


def finish(r):
    for _ in range(2000):
        if r.state["current"] is None:
            return
        result = r.advance(.25)
        expect(result["ok"], result)
    raise AssertionError("bounded customer route did not finish")


def until_action(r, action):
    for _ in range(8000):
        c = r.state["current"]
        if c and c["plan"][c["index"]].get("name") == action:
            return
        expect(c is not None, "route ended before target action")
        expect(r.advance(.01)["ok"])
    raise AssertionError("action not reached")


def publish(r, owner=None):
    owner = owner or FacilitiesBC02(r.state["night_id"], 1, design_simulation=True)
    result = r.publish_to_facilities(owner)
    expect(result["ok"], result)
    return owner, result


def actual_profile(profile):
    r = make(profile["id"])
    result = r.run_customer(profile["id"]); expect(result["ok"], result)
    f, receipt = publish(r)
    c = r.state["completed"][-1]
    paths = c["walk_receipts"]
    expect(paths and all(p["body_clear"] and p["public_access"] for p in paths))
    expect(all(r.navigation.public_point(point) for path in paths for point in path["path"]))
    expect(all(r.navigation.segment_clear(a, b) for path in paths for a, b in zip(path["path"], path["path"][1:])))
    measured = sum(p["distance"] for p in paths)
    expect(abs(measured - c["travel_distance"]) < 1e-7)
    manual = sum(a["actual_seconds"] for a in c["action_receipts"])
    expect(abs((c["finished_at"] - c["started_at"]) - measured/2.4 - manual) < 1e-6)
    source_ids = [x["facility_id"] for x in receipt["accepted"]]
    expect(set(source_ids) == set(profile["optional_services"]) | {"FR01", "FR10"})
    expect(len(set(source_ids) - {"FR01", "FR10"}) <= 2)
    expect(all(x["proof_facts"]["actual_action_receipt_id"] in {a["event_id"] for a in c["action_receipts"]}
               for x in receipt["accepted"]))
    EVIDENCE["profiles"].append({"profile_id": profile["id"], "actual_world_seconds": round(c["finished_at"]-c["started_at"], 9),
        "actual_path_tiles": measured, "actual_service_seconds": manual, "accepted_facilities": source_ids,
        "actual_optional_count": len(set(source_ids)-{"FR01", "FR10"}),
        "original_paid_item_id": c["item_id"], "no_actor_proof_flags_injected_by_test": True,
        "geometry_owner": "CustomerStoreMapBC02 extending actual StoreMap", "consumer_owner": "FacilitiesBC02"})


def public_geometry():
    old, new = StoreMap(), CustomerStoreMapBC02()
    expect(old.route("customer_spawn", "verification_desk", actor="customer")["distance"] == 20)
    try:
        new.route("customer_spawn", "verification_desk", actor="customer")
    except ValueError:
        pass
    else:
        raise AssertionError("legacy employee face must not be a customer face")
    for fid, role in load_contract()["service_registry"].items():
        path = new.route("customer_spawn", role["anchor"], actor="customer")
        expect(path["body_clear"] and path["public_access"], fid)
    expect(new.position("bc02_customer_verification") == [25.5, 24.5])
    expect(new.route("player_start", "verification_desk")["distance"] > 0)
    protected = new.protected_cells()
    for point in new.route("customer_spawn", "bc02_customer_verification", actor="customer")["path"]:
        expect((math.floor(point[0]), math.floor(point[1])) in protected)
    expect(len(new.safe_trap_placements(footprint=(1, 1))) == 10)
    expect(len(new.safe_trap_placements(footprint=(1, 2))) == 16)
    EVIDENCE["public_fr06"] = {"old_employee_face": [25.5, 27.5], "new_public_face": [25.5, 24.5],
        "fixture": "FX23 north face", "old_customer_graph_was_overpermissive": True,
        "new_customer_graph_rejects_employee_face": True, "player_employee_control_preserved": True,
        "protected_against_temporary_trap_placement": True}


def source_chain_return():
    r = make(); expect(r.run_customer("drink_return")["ok"])
    c = r.state["completed"][-1]
    consume, returned = r.state["consume_receipts"][0], r.state["recycle_receipts"][0]
    original, empty = r.state["items"][c["item_id"]], r.state["items"][c["empty_id"]]
    expect(consume["actual_seconds"] == 2 and consume["reward_facility"] is None)
    expect(empty["parent_item_id"] == original["item_id"] and empty["material_unit_id"] == original["material_unit_id"])
    expect(original["state"] == "consumed" and empty["state"] == "recycled_non_sale")
    expect(returned["restocked_sale_units"] == returned["refund"] == 0)
    expect(not any(o["facility_id"] == "FR13" for o in c["operations"]))


def missing_empty():
    r = make(); r.start_customer("drink_return"); until_action(r, "consume_same_drink")
    expect(r.validate_action_source("return_same_empty")["reason"] == "same_order_derived_empty_container_required")


def missing_consumption():
    r = make(); r.start_customer("drink_return")
    r.state["current"]["plan"] = [s for s in r.state["current"]["plan"] if s.get("name") != "consume_same_drink"]
    until_action(r, "return_same_empty")
    result = r.advance(2)
    expect(not result["ok"] and result["reason"] == "same_order_derived_empty_container_required")
    expect(not any(o["facility_id"] == "FR11" for o in r.state["current"]["operations"]))


def unpaid_consumption():
    r = make(); r.start_customer("drink_return"); until_action(r, "pay")
    expect(r.validate_action_source("consume_same_drink")["reason"] == "actual_paid_ownership_required")


def wrong_original_or_root(which):
    r = make(); r.start_customer("drink_return"); until_action(r, "consume_same_drink")
    if which == "item":
        result = r.validate_action_source("consume_same_drink", "employer:n1:cold_drink:2")
        expect(result["reason"] == "not_same_reserved_original_item")
    else:
        r.state["items"][r.state["current"]["item_id"]]["source_root_id"] = "another-order-root"
        result = r.validate_action_source("consume_same_drink")
        expect(result["reason"] == "original_item_cross_root_or_customer")


def powered_action_rejects():
    r = make("hot_called"); r.start_customer("hot_called"); until_action(r, "respond_to_actual_call")
    r.advance(.2); r.set_power("C1", False)
    expect(r.state["current"]["elapsed"] == 0)
    result = r.advance(1)
    expect(not result["ok"] and result["reason"] == "actual_service_source_unpowered")
    expect(not any(o["facility_id"] == "FR09" for o in r.state["current"]["operations"]))
    r.set_power("C1", True); finish(r); publish(r)
    op = next(o for o in r.state["completed"][-1]["operations"] if o["facility_id"] == "FR09")
    expect(op["duration_s"] == 1)


def manual_checkout_off():
    r = make("goods_basic"); r.set_power("MAIN", False)
    expect(r.run_customer("goods_basic")["ok"])
    _, result = publish(r)
    expect([p["facility_id"] for p in result["accepted"]] == ["FR02", "FR10"])
    expect(r.state["completed"][-1]["paid_receipt"]["paid"] is True)


def completed_use_precedes_same_tick_outage():
    r = make("hot_called"); r.start_customer("hot_called"); until_action(r, "collect_product")
    c = r.state["current"]
    r.advance(c["plan"][c["index"]]["seconds"] - c["elapsed"])
    completed = next(a for a in c["action_receipts"] if a["action"] == "collect_product")
    r.set_power("C2", False)
    outage = r.state["power_history"][-1]
    expect(outage["at"] == completed["at"] and outage["sequence"] > completed["sequence"])
    finish(r)
    _, result = publish(r)
    expect("FR03" in [p["facility_id"] for p in result["accepted"]])


def mixed_manual_powered_checkout():
    r = make("goods_basic"); r.set_power("C1", False); r.start_customer("goods_basic"); until_action(r, "pay")
    c = r.state["current"]
    r.advance(.75 - c["elapsed"]); r.set_power("C1", True)
    finish(r)
    c = r.state["completed"][-1]
    payment = next(a for a in c["action_receipts"] if a["action"] == "pay")
    expect(payment["actual_seconds"] == 1.5)
    _, result = publish(r)
    expect([p["facility_id"] for p in result["accepted"]] == ["FR02", "FR10"])
    expect(c["paid_receipt"]["paid"] is True)


def two_service_limit():
    r = make(open_now=False)
    r.profiles["drink_return"]["optional_services"].append("FR13")
    expect(not r.choose_preferences(["drink_return"])["ok"])
    r.open_business()
    expect(r.start_customer("drink_return")["reason"] == "at_most_two_optional_services")


def exhausted_stock():
    r = make("drink_return", units={"cold_drink": 1})
    expect(r.run_customer("drink_return")["ok"])
    expect(r.start_customer("drink_return")["reason"] == "actual_employer_stock_exhausted")
    expect(len(r.state["consume_receipts"]) == 1 and len(r.state["recycle_receipts"]) == 1)


def misplaced_original_stock():
    r = make("goods_basic"); r.start_customer("goods_basic")
    r.state["items"][r.state["current"]["item_id"]]["location"] = "employee_warehouse"
    result = r.validate_action_source("collect_product")
    expect(result["reason"] == "original_stock_not_at_actual_service_slot")


def parcel_inputs_and_verification():
    r = make("parcel_verified", open_now=False)
    expect(not r.prepare_parcel("employer:n1:goods:1", "employer:n1:parcel_bag:1")["ok"])
    expect(not r.prepare_parcel("missing-goods", "employer:n1:parcel_bag:2")["ok"])
    r.open_business(); r.start_customer("parcel_verified"); until_action(r, "verify_same_parcel")
    expect(r.validate_action_source("collect_same_parcel")["reason"] == "actual_same_parcel_verification_required")
    item = r.state["items"][r.state["current"]["item_id"]]
    child = r.state["items"][item["contained_source_ids"][0]]
    child["source_root_id"] = "wrong-parcel-root"
    expect(r.validate_action_source("verify_same_parcel")["reason"] == "parcel_content_cross_root_or_missing")


def geometry_failure():
    r = make("goods_basic", navigation=CustomerStoreMapBC02(closed_doors=["DOOR_FRONT"]))
    before = r.snapshot()
    expect(r.start_customer("goods_basic")["reason"] == "actual_public_route_unavailable")
    expect(r.snapshot() == before)
    live = make("goods_basic"); live.start_customer("goods_basic"); live.advance(.1)
    live.navigation = CustomerStoreMapBC02(closed_doors=["DOOR_FRONT"])
    expect(live.advance(.25)["reason"] == "live_navigation_changed_requires_replan")


def pause_snapshot_preferences():
    r = make("drink_return"); r.start_customer("drink_return"); r.advance(12.25)
    before = r.snapshot(); expect(r.advance(180, paused=True)["ok"]); expect(before == r.snapshot())
    expect(not r.choose_preferences(["drink_public"])["ok"])
    clone = CustomerRoutesBC02.restore(r.snapshot(), design_simulation=True)
    finish(r); finish(clone)
    expect(r.snapshot() == clone.snapshot())
    f, first = publish(r)
    _, second = publish(r, f)
    expect(first["accepted"] and not second["accepted"])


def fake_completed_receipt():
    r = make("goods_basic"); r.run_customer("goods_basic")
    invented = deepcopy(r.state["completed"][0]); invented["operations"][0]["duration_s"] = 0
    try:
        r.build_use_requests(invented)
    except ValueError:
        return
    raise AssertionError("external replacement of actual completed action was accepted")


def default_closed():
    r = CustomerRoutesBC02("n1", 1, reference_employer_manifest("n1"))
    before = r.snapshot()
    expect(not r.choose_preferences(["goods_basic"])["ok"])
    expect(not r.advance(100)["ok"])
    expect(r.snapshot() == before)


def paid_evacuation(profile, *, cross_night=False):
    r = make(profile); r.start_customer(profile)
    until_action(r, "verify_same_parcel" if profile == "parcel_verified" else "respond_to_actual_call")
    c = r.state["current"]; original_id, order_id = c["item_id"], c["order_id"]
    original_paid = deepcopy(c["paid_receipt"])
    evac = r.evacuate_paid_uncollected(); expect(evac["ok"], evac)
    claim_id = evac["claim_id"]
    before_exit_position = deepcopy(r.state["current"]["position"])
    finish(r)
    expect(before_exit_position != r.state["completed"][-1]["position"])
    expect(r.state["items"][original_id]["state"] == "reserved")
    expect(r.state["pickup_claims"][claim_id]["status"] == "awaiting_pickup")
    f, partial = publish(r)
    expect([p["facility_id"] for p in partial["accepted"]] == ["FR01"])
    expect(not f.state["bank"]["FR10"])
    r = CustomerRoutesBC02.restore(r.snapshot(), design_simulation=True)
    if cross_night:
        saved = r.export_pickup_claims()
        next_night = make("goods_basic", night="n2", open_now=False)
        expect(next_night.import_pickup_claims(saved)["ok"])
        next_night.open_business(); r = next_night
        f = FacilitiesBC02("n2", 1, design_simulation=True)
    else:
        expect(r.resume_safe_business()["ok"])
    result = r.resume_pickup(claim_id); expect(result["ok"] and result["charged_again"] == 0)
    expect(r.state["current"]["item_id"] == original_id and r.state["current"]["order_id"] == order_id)
    expect(r.state["current"]["paid_receipt"] == original_paid)
    finish(r)
    _, fulfilled = publish(r, f)
    expected = [] if cross_night else (["FR06", "FR12", "FR10"] if profile == "parcel_verified" else ["FR09", "FR03", "FR10"])
    expect([p["facility_id"] for p in fulfilled["accepted"]] == expected)
    expect(r.state["pickup_claims"][claim_id]["status"] == "collected")
    expect(not r.resume_pickup(claim_id)["ok"])
    expect(not any(e["kind"] == "order_paid" for e in r.state["events"] if e["at"] > original_paid["completed_at"]))
    EVIDENCE.setdefault("paid_uncollected", []).append({"profile": profile, "cross_night": cross_night,
        "original_item_id_preserved": original_id, "original_order_id_preserved": order_id,
        "partial_accepted_sources": [p["facility_id"] for p in partial["accepted"]],
        "after_actual_collection_accepted_sources": [p["facility_id"] for p in fulfilled["accepted"]],
        "charged_again": 0, "durable_claim_closed_after_actual_exit": True,
        "uncollected_did_not_emit_fr10": True, "old_night_support_not_minted_in_new_night": cross_night})


def repeated_pickup_interruptions(cross_night):
    r = make("hot_called"); r.start_customer("hot_called"); until_action(r, "respond_to_actual_call")
    claim_id = r.evacuate_paid_uncollected()["claim_id"]; finish(r)
    if cross_night:
        new = make("goods_basic", night="n2", open_now=False)
        expect(new.import_pickup_claims(r.export_pickup_claims())["ok"])
        new.open_business(); r = new
    else:
        r.resume_safe_business()
    expect(r.resume_pickup(claim_id)["ok"])
    until_action(r, "collect_product")
    expect(r.evacuate_paid_uncollected()["claim_id"] == claim_id); finish(r)
    r.resume_safe_business(); expect(r.resume_pickup(claim_id)["ok"]); finish(r)
    journeys = [c["journey_id"] for c in r.state["completed"]]
    expect(len(journeys) == len(set(journeys)) and journeys[-1].endswith(":visit:3"))
    expect(r.state["pickup_claims"][claim_id]["resume_count"] == 2)
    expect(r.state["pickup_claims"][claim_id]["status"] == "collected")
    _, result = publish(r)
    sources = [p["facility_id"] for p in result["accepted"]]
    expect(sources == ([] if cross_night else ["FR01", "FR09", "FR03", "FR10"]))


def run():
    check("default production customer adapter stays closed", default_closed)
    check("new public FR06 face excludes old employee control and has protected actual paths", public_geometry)
    for profile in load_contract()["profiles"]:
        check("actual path/time/original-object/FacilitiesBC02 profile: " + profile["id"], lambda p=profile: actual_profile(p))
    for name, fn in (("FR05 plus FR11 consumes the same paid drink without a third FR13 reward", source_chain_return),
                     ("FR11 rejects a missing derived empty container", missing_empty),
                     ("skipping the actual drinking action cannot produce FR11 use", missing_consumption),
                     ("unpaid original drink cannot be consumed for service credit", unpaid_consumption),
                     ("wrong physical original object is rejected", lambda: wrong_original_or_root("item")),
                     ("cross-root original object is rejected", lambda: wrong_original_or_root("root")),
                     ("power loss interrupts actual call progress; restore needs a full real response", powered_action_rejects),
                     ("manual checkout remains possible without powered cashier support", manual_checkout_off),
                     ("actual completed hot-food use precedes a later same-tick outage by event sequence", completed_use_precedes_same_tick_outage),
                     ("half manual and half powered checkout pays once without FR01 support", mixed_manual_powered_checkout),
                     ("a profile with three optional reward services cannot start", two_service_limit),
                     ("consumption and recycling cannot replenish original sale stock", exhausted_stock),
                     ("a reserved item in the wrong physical slot cannot be collected at the public face", misplaced_original_stock),
                     ("parcel prepack inputs and same-root completed verification are required", parcel_inputs_and_verification),
                     ("closed doors and changed live navigation cannot be bypassed", geometry_failure),
                     ("pause freezes movement; snapshots resume exactly and use publication is once-only", pause_snapshot_preferences),
                     ("external fabricated completed-action receipt is not authoritative", fake_completed_receipt)):
        check(name, fn)
    for profile in ("parcel_verified", "hot_called"):
        for cross_night in (False, True):
            check(f"paid {profile} evacuates with original entitlement then fulfils {'next night without new rewards' if cross_night else 'same night once'}",
                  lambda p=profile, n=cross_night: paid_evacuation(p, cross_night=n))
    for cross_night in (False, True):
        check("two paid-pickup interruptions preserve visit ordinals " + ("across nights" if cross_night else "within the night"),
              lambda n=cross_night: repeated_pickup_interruptions(n))


if __name__ == "__main__":
    run()
    covered = sorted({fid for p in EVIDENCE["profiles"] for fid in p["accepted_facilities"]})
    EVIDENCE["covered_reward_sources"] = covered
    sources = ["content/customer_routes_bc02.json", "scripts/bc02_customer_reference.py",
               "scripts/check_bc02_customer_routes.py", "docs/101_bc02_customer_routes.md", "content/facilities_bc02.json"]
    report = {"version": "BC02", "scope": "actual public-path and source-object reference with real FacilitiesBC02 consumer",
              "passed": sum(r["passed"] for r in RESULTS), "failed": sum(not r["passed"] for r in RESULTS),
              "actual_client_runtime": False, "checks": RESULTS, "evidence": EVIDENCE,
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources if (ROOT / p).exists()}}
    (ROOT / "docs/bc02_customer_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "failed": report["failed"], "covered_reward_sources": covered,
                      "failures": [r for r in RESULTS if not r["passed"]], "actual_client_runtime": False}, ensure_ascii=False))
    raise SystemExit(bool(report["failed"]))
