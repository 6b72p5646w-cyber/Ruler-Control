#!/usr/bin/env python3
"""Run bounded facility counterexamples; never reports a full-world playtest."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

from sa02_facility_reference import FacilityReference, load_contract

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = load_contract()
RESULTS = []


def check(name, fn):
    try:
        fn()
        RESULTS.append({"name": name, "passed": True})
    except Exception as exc:
        RESULTS.append({"name": name, "passed": False, "error": f"{type(exc).__name__}: {exc}"})


def expect(condition, message="unexpected result"):
    if not condition:
        raise AssertionError(message)


def binding(facility="station", suffix="1"):
    return {"campaign_id": "campaign", "week_id": "week1", "logical_night_id": "night1",
            "attempt_id": "attempt1", "facility_instance_id": facility,
            "work_order_id": "order" + suffix, "action_id": "action" + suffix,
            "object_instance_id": "object" + suffix}


def facts(fid="FR01", **overrides):
    # These are deliberately simulated world facts, not inferred real bindings.
    data = {"phase_open": True, "same_current_attempt": True, "actor_action_legal": True,
            "consumer_bound": True, "facility_geometry_bound": True, "source_available": True,
            "actual_object_valid": True, "main_C2_powered": True,
            "work_complete": False, "action_already_started": False,
            "same_target_legal": True}
    if fid in CONTRACT["work_candidates"]:
        data["source_event"] = CONTRACT["work_candidates"][fid]["source_event"]
    data.update(overrides)
    return data


def armed(fid="FR01", *, base=1.5, other=1.0):
    model = FacilityReference(simulated_design=True)
    key = binding()
    result = model.arm_work(fid, "a", key, 0, facts(fid), base_duration=base, other_work_multiplier=other)
    expect(result["ok"], result["reason"])
    return model, key, result


def receipt(fid, key, rid="receipt1"):
    return {"binding": deepcopy(key), "event": CONTRACT["work_candidates"][fid]["source_event"],
            "origin_kind": "actual_world_work", "receipt_id": rid}


def enemy(pool="enemy1", **overrides):
    data = {"pool_id": pool, "legal": True, "manifested": True, "hostile": True,
            "independent_pool": True, "actual_intersection": True, "actual_LOS": True,
            "layer": "ground", "distance": 1.0}
    data.update(overrides)
    return data


def commit(model, fid, key, at=2, **overrides):
    data = {"candidates": [enemy()], "source_available": True, "actual_action_complete": True}
    data.update(overrides)
    return model.commit_work("a", receipt(fid, key), at, **data)


def scan_started(*, reserve=12):
    model = FacilityReference(simulated_design=True, reserve=reserve)
    key = binding("scan_station")
    result = model.start_scan("scan", key, "enemy1", 0, facts("FR06"))
    expect(result["ok"])
    return model, key


def scan_commit(model, key, at=2, **overrides):
    data = {"source_available": True, "same_target_legal": True, "actual_action_complete": True,
            "actor_at_station": True, "receipt_id": "scan_receipt1"}
    data.update(overrides)
    return model.commit_scan("scan", key, "enemy1", at, **data)


def source_pointer(entry):
    value = json.loads((ROOT / entry["path"]).read_text())
    for part in entry["pointer"].strip("/").split("/"):
        part = part.replace("~1", "/").replace("~0", "~")
        value = value[int(part)] if isinstance(value, list) else value[part]
    expect(value is not None)


def admission_rejection(key, value, expected):
    model = FacilityReference(simulated_design=True)
    before = model.snapshot()
    result = model.arm_work("FR01", "a", binding(), 0, facts(**{key: value}), base_duration=1.5)
    expect(not result["ok"] and result["reason"] == expected)
    expect(model.snapshot() == before, "rejected activation changed costs or state")


def run():
    check("all five candidates remain disabled and not integrated", lambda: expect(
        CONTRACT["enabled"] is False and CONTRACT["runtime_integrated"] is False and all(
            s["enabled"] is False and s["runtime_integrated"] is False
            for s in [*CONTRACT["work_candidates"].values(), CONTRACT["scan_candidate"]])))
    for entry in CONTRACT["source_evidence"]:
        check("real source pointer " + entry["path"] + "#" + entry["pointer"], lambda entry=entry: source_pointer(entry))
    store = json.loads((ROOT / "content/store_systems_v05.json").read_text())
    check("checkout timing reads current actual store authority", lambda: expect(
        store["work_contract"]["normal_checkout_seconds"] == 1.5 and
        store["work_contract"]["service_window_checkout_seconds"] == 3.5))
    check("D02 and D03 remain original object work with no invented recipe", lambda: expect(
        store["duties"][1]["normal_actions"] == ["提起一箱货", "沿货架环路搬至空位", "放上货架"] and
        store["duties"][2]["normal_actions"] == ["把一份热食放至交付槽", "将登记生肉入柜", "关柜"]))
    for fid in ("FR02", "FR03", "FR04"):
        check(fid + " removes unbound speed promise without changing original action", lambda fid=fid: expect(
            CONTRACT["work_candidates"][fid]["ordinary_speed_multiplier"] is None and
            armed(fid)[2]["effective_duration"] is None))
    def production_gate():
        model = FacilityReference()
        before = model.snapshot()
        r = model.arm_work("FR01", "a", binding(), 0, facts(), base_duration=1.5)
        expect(r["reason"] == "candidate_disabled" and model.snapshot() == before)
    check("default public entry cannot activate disabled design", production_gate)
    for key, value, expected in (
        ("consumer_bound", False, "consumer_unbound"),
        ("facility_geometry_bound", False, "facility_geometry_unproven"),
        ("phase_open", False, "wrong_phase"),
        ("same_current_attempt", False, "wrong_attempt"),
        ("actual_object_valid", False, "wrong_object"),
        ("source_available", False, "source_unavailable"),
    ):
        check("unproven " + key + " rejects before charging", lambda k=key, v=value, e=expected: admission_rejection(k, v, e))
    def tower_geometry_not_facility():
        m = FacilityReference(simulated_design=True)
        r = m.arm_work("FR03", "a", binding(), 0, facts("FR03", facility_geometry_bound=False, tower_projection_passed=True))
        expect(r["reason"] == "facility_geometry_unproven" and m.state["reserve"] == 12)
    check("passed tower projection is insufficient for facility admission", tower_geometry_not_facility)
    def power_gate():
        for fid in ("FR03", "FR04"):
            m = FacilityReference(simulated_design=True)
            r = m.arm_work(fid, "a", binding(), 0, facts(fid, main_C2_powered=False))
            expect(r["reason"] == "main_power_unavailable" and m.state["reserve"] == 12)
    check("hot-food and freezer require real main power as well as reserve", power_gate)
    check("ordinary checkout 1.5 to 1.275 only once", lambda: expect(math.isclose(armed()[2]["effective_duration"], 1.275)))
    check("window checkout preserves actual 3.5 base", lambda: expect(math.isclose(armed(base=3.5)[2]["effective_duration"], 2.975)))
    check("stronger work modifier wins without multiplication", lambda: expect(math.isclose(armed(other=0.8)[2]["effective_duration"], 1.2)))
    def invented_base():
        m = FacilityReference(simulated_design=True)
        r = m.arm_work("FR01", "a", binding(), 0, facts(), base_duration=2)
        expect(r["reason"] == "not_original_checkout_duration" and m.state["reserve"] == 12)
    check("invented checkout timing cannot justify speed benefit", invented_base)
    def premature():
        m, k, _ = armed()
        expect(commit(m, "FR01", k, at=1)["reason"] == "original_action_not_finished")
        expect(m.state["activations"]["a"]["state"] == "active")
    check("actual checkout must finish before any response", premature)
    def no_actual_completion():
        m, k, _ = armed("FR04")
        expect(commit(m, "FR04", k, actual_action_complete=False)["reason"] == "no_actual_completion")
        expect(not m.state["effects"])
    check("receipt label without real completion is insufficient", no_actual_completion)
    def double_arm():
        m, k, _ = armed()
        r = m.arm_work("FR01", "a", k, 0, facts(), base_duration=1.5)
        expect(r["reason"] == "activation_id_used" and m.state["reserve"] == 11)
    check("retry of paid activation never pays twice", double_arm)
    for field in ("work_order_id", "action_id", "object_instance_id", "facility_instance_id", "attempt_id"):
        def mismatched(field=field):
            m, k, _ = armed("FR04")
            wrong = dict(k, **{field: "different"})
            r = commit(m, "FR04", wrong)
            expect(r["reason"] == "receipt_mismatch" and not m.state["effects"])
            expect(m.state["activations"]["a"]["state"] == "active")
        check("receipt cannot switch " + field, mismatched)
    def canceled_checkout():
        m, k, _ = armed()
        r = m.interrupt_work("a", 0.5, original_producer_preserves_action=True)
        expect(r["reason"] == "canceled" and m.state["reserve"] == 11)
        expect(not commit(m, "FR01", k)["ok"])
        r = m.arm_work("FR01", "new_id", k, 30, facts(), base_duration=1.5)
        expect(r["reason"] == "bound_action_already_paid" and m.state["reserve"] == 11)
    check("checkout cancel loses one opportunity and cannot reboost same action", canceled_checkout)
    def same_resume():
        m, k, _ = armed("FR02")
        expect(m.interrupt_work("a", 2, original_producer_preserves_action=True)["reason"] == "suspended")
        expect(not m.resume_work("a", dict(k, object_instance_id="other"), 3,
                                original_producer_preserves_action=True, source_available=True, actor_action_legal=True)["ok"])
        expect(m.resume_work("a", k, 4, original_producer_preserves_action=True,
                             source_available=True, actor_action_legal=True)["ok"])
        expect(m.state["activations"]["a"]["expires_at"] == 20 and m.state["reserve"] == 11)
    check("only producer-preserved exact action can resume without new time or cost", same_resume)
    def exact_deadline():
        m, k, _ = armed("FR04")
        r = commit(m, "FR04", k, at=20)
        m.finish_tick(20)
        expect(r["ok"] and len(r["effects"]) == 1 and m.state["activations"]["a"]["state"] == "consumed")
        expect(not commit(m, "FR04", k, at=20)["ok"])
    check("already-running completion at exactly 20 seconds wins once", exact_deadline)
    def late_deadline():
        m, k, _ = armed("FR04")
        expect(not commit(m, "FR04", k, at=20.0001)["ok"])
        expect(m.state["reserve"] == 11 and not m.state["effects"])
    check("completion just after deadline yields no effect or refund", late_deadline)
    def resume_deadline():
        m, k, _ = armed("FR03")
        m.interrupt_work("a", 1, original_producer_preserves_action=True)
        expect(m.resume_work("a", k, 20, original_producer_preserves_action=True,
                             source_available=True, actor_action_legal=True)["reason"] == "resume_at_or_after_deadline")
    check("deadline cannot be used as a new resume window", resume_deadline)
    def source_loss():
        m, k, _ = armed("FR03")
        m.lose_source(k["facility_instance_id"], 1)
        expect(not commit(m, "FR03", k, at=2, source_available=True)["ok"])
        expect(m.state["reserve"] == 11 and m.state["next_use"]["station"] == 30)
    check("power cycling cannot restore pending opportunity or reset cooldown", source_loss)
    def no_target():
        m, k, _ = armed("FR03")
        r = commit(m, "FR03", k, candidates=[])
        expect(r["ok"] and not r["effects"] and m.state["reserve"] == 11)
        expect(not commit(m, "FR03", k, at=3)["ok"])
    check("valid completion without a target is consumed without credit bank", no_target)
    def terminal_first():
        m, k, _ = armed("FR04")
        r = commit(m, "FR04", k, candidates=[enemy("F13", distance=0.1), enemy("other")], terminal_pool_ids=["F13"])
        expect([e["target_id"] for e in r["effects"]] == ["other"])
        expect(m.state["journal"][-2:] == ["original_main_rule_terminal_decisions", "facility_legal_target_selection"])
    check("same-action F13 departure precedes selecting cold recipients", terminal_first)
    def recipient_filters():
        m, k, _ = armed("FR03")
        candidates = [enemy("shared", independent_pool=False), enemy("high", layer="high_air"),
                      enemy("hidden", manifested=False), enemy("human", hostile=False), enemy("wall", actual_LOS=False),
                      enemy("one"), enemy("one"), enemy("two", distance=1.2), enemy("three", distance=1.4)]
        r = commit(m, "FR03", k, candidates=candidates)
        expect([e["target_id"] for e in r["effects"]] == ["one", "two"])
    check("real independent legal recipients only; no shared-part multiplication", recipient_filters)
    def identityless_recipient():
        m, k, _ = armed("FR03")
        r = commit(m, "FR03", k, candidates=[enemy(None), enemy(""), enemy("response_actor", hostile=False)])
        expect(r["ok"] and not r["effects"])
    check("missing pool identity and legal nonhostile response actor cannot receive hostile payload", identityless_recipient)
    def secondary_not_work():
        m, k, _ = armed("FR03")
        fake = receipt("FR03", k)
        fake["origin_kind"] = "facility_secondary"
        r = m.commit_work("a", fake, 2, candidates=[enemy()], source_available=True, actual_action_complete=True)
        expect(r["reason"] == "receipt_mismatch")
        real = commit(m, "FR03", k)
        expect(not real["primary_events_emitted"] and all(not e["may_trigger_EQ01_reaction"] for e in real["effects"]))
        expect(all(e["shared_TD05_status_processing"] for e in real["effects"]))
    check("facility responses cannot recursively manufacture work or EQ01 triggers", secondary_not_work)
    def tower(tid, **overrides):
        data = {"tower_instance_id": tid, "fixture_instance_id": "station", "node_id": "T01.A", "enabled": True,
                "loading": True, "base_reload_work": 2.2, "remaining_reload_work": 1.0}
        data.update(overrides)
        return data
    def reload_only():
        m, k, _ = armed("FR02")
        r = commit(m, "FR02", k, candidates=[tower("mag", node_id="T02.A2"), tower("wave", node_id="T03.A2"),
                    tower("other_shelf", fixture_instance_id="elsewhere"), tower("ready", loading=False), tower("right")])
        expect(len(r["effects"]) == 1 and r["effects"][0]["target_id"] == "right")
        expect(math.isclose(r["effects"][0]["advanced_work"], 0.22))
        expect(not r["primary_events_emitted"])
    check("stock response advances one existing whitelisted same-shelf reload only", reload_only)
    def reload_clamp():
        m, k, _ = armed("FR02")
        r = commit(m, "FR02", k, candidates=[tower("ready_soon", remaining_reload_work=0.05)])
        expect(r["effects"][0]["advanced_work"] == 0.05 and r["effects"][0]["remaining_work_after"] == 0)
    check("reload advance clamps at ready without overflow or extra shot", reload_clamp)
    def identityless_tower():
        m, k, _ = armed("FR02")
        r = commit(m, "FR02", k, candidates=[tower(None), tower("")])
        expect(r["ok"] and not r["effects"])
    check("loading tower without stable instance identity cannot receive progress", identityless_tower)
    def source_after_effect():
        m, k, _ = armed("FR03")
        commit(m, "FR03", k, at=2)
        m.lose_source("station", 3)
        expect(len(m.live_effects(7.999)) == 1 and len(m.live_effects(8)) == 0)
    check("applied heat keeps its own deadline after source loss", source_after_effect)
    def restored():
        m, k, _ = armed("FR04")
        commit(m, "FR04", k)
        saved = json.loads(json.dumps(m.snapshot()))
        n = FacilityReference.restore(saved, simulated_design=True)
        expect(n.snapshot() == saved and not commit(n, "FR04", k)["ok"] and n.state["reserve"] == 11)
    check("serialized restoration preserves cost receipt and no replay", restored)
    def scan_reservation():
        m, _ = scan_started(reserve=1)
        expect(m.state["reserve"] == 1 and m.available_reserve() == 0 and not m.state["next_use"])
        r = m.arm_work("FR01", "a", binding("other"), 0, facts(), base_duration=1.5)
        expect(r["reason"] == "insufficient_unreserved_power")
    check("scan reserves spending capacity but consumes no power before success", scan_reservation)
    def parallel_scan_bypass():
        m, k = scan_started()
        other = binding("scan_station", "2")
        r = m.start_scan("other_scan", other, "enemy2", 0.5, facts("FR06"))
        expect(r["reason"] == "same_facility_scan_pending" and m.available_reserve() == 11)
        r = m.arm_work("FR01", "other_work", other, 0.5, facts(), base_duration=1.5)
        expect(r["reason"] == "same_facility_scan_pending")
        expect(scan_commit(m, k)["ok"] and m.state["reserve"] == 11)
    check("parallel activation IDs cannot bypass one station scan or its commit cooldown", parallel_scan_bypass)
    def scan_target_identity():
        m = FacilityReference(simulated_design=True)
        r = m.start_scan("scan", binding("scan_station"), "", 0, facts("FR06"))
        expect(r["reason"] == "target_unavailable" and not m.state["scans"] and m.available_reserve() == 12)
    check("scan cannot reserve against an identityless target", scan_target_identity)
    def scan_early():
        m, k = scan_started()
        expect(scan_commit(m, k, at=1.999)["reason"] == "scan_not_complete" and m.state["reserve"] == 12)
    check("scan cannot skip the actual two-second action", scan_early)
    def scan_cancel():
        m, _ = scan_started()
        m.cancel_scan("scan", 1)
        expect(m.available_reserve() == 12 and not m.state["next_use"])
    check("scan cancel releases reservation without cooldown or cost", scan_cancel)
    for reason in ("source_available", "same_target_legal", "actor_at_station"):
        def invalid_scan(reason=reason):
            m, k = scan_started()
            r = scan_commit(m, k, **{reason: False})
            expect(r["reason"] == "scan_invalidated" and m.available_reserve() == 12 and not m.state["effects"])
        check("scan lost " + reason + " cancels without payment", invalid_scan)
    def no_scan_receipt():
        m, k = scan_started()
        expect(scan_commit(m, k, receipt_id=None)["reason"] == "missing_actual_scan_receipt" and m.state["reserve"] == 12)
    check("scan also requires its real completion receipt", no_scan_receipt)
    def scan_success():
        m, k = scan_started()
        r = scan_commit(m, k)
        expect(r["ok"] and m.state["reserve"] == 11 and m.state["next_use"]["scan_station"] == 32)
        expect(r["effects"][0]["expires_at"] == 5 and not r["primary_events_emitted"])
        expect(not scan_commit(m, k)["ok"])
        new = binding("scan_station", "2")
        expect(m.start_scan("s2", new, "enemy2", 31.999, facts("FR06"))["reason"] == "cooldown")
        expect(m.start_scan("s2", new, "enemy2", 32, facts("FR06"))["ok"])
    check("scan success pays once and cooldown begins at actual commit", scan_success)
    def scan_power_loss():
        m, k = scan_started()
        m.lose_source("scan_station", 1)
        expect(not scan_commit(m, k)["ok"] and m.available_reserve() == 12)
    check("power cycling cannot resurrect canceled scan reservation", scan_power_loss)
    def night_end():
        m, k, _ = armed("FR03")
        commit(m, "FR03", k)
        m.end_night(3)
        expect(not m.live_effects(3) and m.state["reserve"] == 11)
        expect(m.arm_work("FR01", "next", binding("elsewhere"), 3, facts(), base_duration=1.5)["reason"] == "night_ended")
    check("night transition stops temporary promises without minting resources", night_end)
    check("electric feedback explicitly retains shared TD05 semantics", lambda: expect(
        "no electric-charge global cap" in CONTRACT["event_protocol"]["electric_exception"]))


if __name__ == "__main__":
    run()
    paths = {entry["path"] for entry in CONTRACT["source_evidence"]}
    paths.update({"content/facility_contracts_sa02.json", "scripts/sa02_facility_reference.py", "scripts/check_sa02_facility.py"})
    report = {
        "version": "SA02", "scope": "bounded facility receipt/cost/deadline counterexamples plus real-source checks",
        "baseline_commit": CONTRACT["baseline_commit"],
        "passed": sum(r["passed"] for r in RESULTS), "failed": sum(not r["passed"] for r in RESULTS),
        "runtime_integrated": False, "full_gameplay_proven": False, "candidates_enabled": False,
        "explicitly_assumed_simulation_inputs": ["world consumer binding", "facility-specific geometry", "real action legality", "original receipt authentication", "target actual geometry", "original main-rule terminal outcome"],
        "not_proven": CONTRACT["verification_limits"]["not_proven"],
        "input_sha256": {path: hashlib.sha256((ROOT / path).read_bytes()).hexdigest() for path in sorted(paths)},
        "checks": RESULTS,
    }
    (ROOT / "docs/sa02_facility_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"SA02 facility checks: {report['passed']} passed, {report['failed']} failed; runtime remains disabled.")
    for result in RESULTS:
        if not result["passed"]:
            print(result)
    raise SystemExit(1 if report["failed"] else 0)
