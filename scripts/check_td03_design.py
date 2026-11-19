#!/usr/bin/env python3
"""TD03 data checks and small reference counterexamples, not a game runtime."""
from pathlib import Path
from fractions import Fraction as F
import argparse
import hashlib
import json
import math

ROOT = Path(__file__).resolve().parents[1]


def number(value):
    return value if isinstance(value, F) else F(str(value))


def spans_for_segment(a, b, ta, tb):
    """Positive-length intersections of a real segment with fixed half-open cells."""
    a, b = tuple(map(number, a)), tuple(map(number, b))
    ta, tb = number(ta), number(tb)
    cuts = {F(0), F(1)}
    for lo, hi in zip(a, b):
        if lo == hi:
            continue
        for boundary in range(math.floor(min(lo, hi)) + 1, math.ceil(max(lo, hi))):
            u = (boundary - lo) / (hi - lo)
            if 0 < u < 1:
                cuts.add(u)
    cuts = sorted(cuts)
    out = []
    for left, right in zip(cuts, cuts[1:]):
        middle = (left + right) / 2
        point = tuple(x + (y - x) * middle for x, y in zip(a, b))
        out.append((tuple(math.floor(x) for x in point), ta + (tb - ta) * left, ta + (tb - ta) * right))
    return out


def spans_for_samples(samples):
    out = []
    for (ta, a), (tb, b) in zip(samples, samples[1:]):
        for cell, start, end in spans_for_segment(a, b, ta, tb):
            if out and out[-1][0] == cell and out[-1][2] == start:
                out[-1] = (cell, out[-1][1], end)
            else:
                out.append((cell, start, end))
    return out


def settle_tolls(pool, spans, ledger, raw_damage=8, period=2, fields=None):
    """The reference fixture has static legal fields; field/LOS AI is out of scope."""
    hits = []
    for cell, start, end in spans:
        if fields is not None and cell not in fields:
            continue
        key = (pool, "zone_toll", cell)
        due = max(start, ledger.get(key, start))
        while due < end:
            hits.append((cell, due, number(raw_damage)))
            ledger[key] = due + number(period)
            due = ledger[key]
    return hits


def settle_endpoints(pool, endpoints, ledger, raw_damage=8, period=2):
    hits = []
    for t, point in endpoints:
        cell = tuple(math.floor(number(x)) for x in point)
        key = (pool, "zone_toll", cell)
        t = number(t)
        if t >= ledger.get(key, t):
            hits.append((cell, t, number(raw_damage)))
            ledger[key] = t + number(period)
    return hits


def seeded_draw(seed, attack_id):
    digest = hashlib.sha256(f"{seed}|{attack_id}".encode()).digest()
    return F(int.from_bytes(digest[:8], "big"), 2 ** 64)


def sum_damage(hits):
    return sum((hit[2] for hit in hits), F(0))


def first_threshold_time(effect, horizon=30):
    """A stationary legal-target fixture; external actions remain explicit conditions."""
    threshold = int(effect["threshold"])
    duration = number(effect["stack_duration_s"])
    amount = int(effect["amount"])
    if effect.get("trigger") == "target_attack_payload_committed":
        return None
    if effect.get("trigger") == "actual_curtain_crossing":
        return F(0) if amount >= threshold else None
    offsets = effect.get("schedule_offsets_s")
    events = []
    if offsets is not None:
        cycle = number(effect["cycle_s"])
        for k in range(math.ceil(horizon / cycle) + 1):
            for offset in offsets:
                if "active_duration_s" in effect and number(offset) >= number(effect["active_duration_s"]):
                    continue
                events.append(k * cycle + number(offset))
    else:
        interval = number(effect["application_interval_s"])
        start = number(effect.get("first_application_s", 0))
        events = [start + k * interval for k in range(math.ceil(horizon / interval) + 1)]
    marks = []
    for time in sorted(t for t in events if t <= horizon):
        marks = [expiry for expiry in marks if expiry > time]
        marks.extend([time + duration] * amount)
        if len(marks) >= threshold:
            return time
    return None


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--report", default="docs/td03_design_check_report.json")
    args = parser.parse_args()
    names = ["tower_defense_td03.json", "combat_contracts_td03.json", "traps_facilities_td03.json", "monster_matchups_td03.json"]
    paths = [ROOT / "content" / name for name in names]
    towers, contracts, traps, monsters = [json.loads(path.read_text()) for path in paths]
    checks, evidence = [], {}

    def check(name, condition, detail=None):
        if not condition:
            raise AssertionError(f"{name}: {detail}")
        checks.append({"name": name, "result": "pass", **({"detail": detail} if detail is not None else {})})

    check("version_and_design_boundary", all(d["version"] == "TD03" and d["runtime_integrated"] is False for d in (towers, contracts, traps, monsters)))
    families = towers["families"]
    l2 = [node for family in families for node in family["l2"]]
    l3 = [node for parent in l2 for node in parent["l3"]]
    all_nodes = [family["l1"] for family in families] + l2 + l3
    ids = {node["id"] for node in all_nodes}
    check("ten_twenty_forty_tree", len(families) == 10 and len(l2) == 20 and len(l3) == 40)
    check("seventy_unique_tower_nodes", len(ids) == len(all_nodes) == 70)
    check("two_real_choices_at_each_tier", all(len(f["l2"]) == 2 and all(len(n["l3"]) == 2 for n in f["l2"]) for f in families))
    check("parent_links", all(n["parent"] == f["l1"]["id"] for f in families for n in f["l2"]) and all(n["parent"] == p["id"] for p in l2 for n in p["l3"]))
    check("paid_stage_prices", all(n["cost"] == {"coin": 25, "spirit": 4} for n in l2) and all(n["cost"] == {"coin": 40, "spirit": 10} for n in l3))
    check("leaf_tradeoffs_and_parameters", all(n.get("parameters") and n.get("mechanic") and n.get("favorable") and n.get("weakness") and n.get("layers") for n in l3))
    check("absolute_parameters_not_double_upgrade", all(n["parameters"]["parameters_are_absolute"] is True for n in all_nodes))
    check("ten_distinct_delivery_modes", len({n["mode"] for n in l3}) >= 10)
    threshold_evidence = []
    status_lookup = {"heat": contracts["statuses"]["burn"]["heat"], **{key: contracts["statuses"][key] for key in ("frost", "curse", "electric")}}
    for node in all_nodes:
        for effect in node.get("effects", []):
            if effect.get("status") not in status_lookup or "threshold" not in effect:
                continue
            shared = status_lookup[effect["status"]]
            check("shared_threshold_" + node["id"] + "_" + effect["trigger"], effect["threshold"] == shared["threshold"] and effect["stack_duration_s"] == shared["stack_duration_s"])
            if effect.get("independent_trigger") and effect["trigger"] != "target_attack_payload_committed":
                first = first_threshold_time(effect)
                check("reachable_threshold_" + node["id"] + "_" + effect["trigger"], first is not None)
                threshold_evidence.append({"node": node["id"], "status": effect["status"], "first_threshold_s": float(first), "condition": effect["requires"]})

    ts = traps["traps"]
    tl2 = [n for trap in ts for n in trap["l2"]]
    tl3 = [n["l3"] for n in tl2]
    check("sixteen_trap_families_two_paths", len(ts) == 16 and len(tl2) == 32 and len(tl3) == 32 and {t["id"] for t in ts} == {f"R{i:02}" for i in range(1, 17)})
    check("trap_parent_links", all(n["parent"] == t["id"] for t in ts for n in t["l2"]) and all(n["l3"]["parent"] == n["id"] for n in tl2))
    check("integer_trap_footprints", all(len(shape) == 2 and all(isinstance(v, int) and v > 0 for v in shape) for t in ts for shape in t["footprint_variants"]))

    roster = monsters["monsters"]
    check("sixty_original_monster_ids", len(roster) == 60 and {m["id"] for m in roster} == {f"F{i:02}" for i in range(1, 61)})
    check("f14_disabled", next(m for m in roster if m["id"] == "F14")["default_enabled"] is False)
    leaf_ids = {n["id"] for n in l3}
    for key in ("favorable", "conditional", "weak"):
        check("monster_" + key + "_references", all(set(m[key]) <= leaf_ids for m in roster))

    burn, poison, frost, curse, electric = [contracts["statuses"][key] for key in ("burn", "poison", "frost", "curse", "electric")]
    check("persistent_poison_is_uncapped", poison["max_load"] is None and poison["duration_s"] is None and poison["natural_decay_per_second"] == 0 and poison["damage_per_second_per_load"] == 0.5)
    q = F(100) + 1
    check("poison_101st_unit_not_lost", q * number(poison["damage_per_second_per_load"]) == F(101, 2))
    parent_q, pending = F(101), F(1)
    parts = [F(1, 4), F(1, 4), F(1, 2)]
    check("fission_conserves_poison_and_pending_maturity", sum(parent_q * p for p in parts) == parent_q and sum(pending * p for p in parts) == pending)
    dose_q, pending_q, maturity_paid = F(2), F(1), False
    for t in (F(7), F(8), F(8), F(80)):
        if t >= 8 and not maturity_paid:
            dose_q += pending_q
            maturity_paid = True
    check("maturity_paid_exactly_once", dose_q == 3)
    known = set()
    source_q, receiver_q = F(20), F(0)
    source_q += 1
    for dose in ("new-dose/receiver", "new-dose/receiver"):
        if dose not in known:
            known.add(dose)
            receiver_q += 1
    check("infection_does_not_copy_history_or_repeat_ticket", source_q == 21 and receiver_q == 1)
    estate = F(20)
    shares = [estate * F(1, 2) / 2] * 2
    check("death_bequest_total_half_not_half_each", shares == [5, 5] and sum(shares) == estate / 2)

    mixed_heat_vulnerability = 4 * F(15, 100) / 8 + 4 * F(25, 100) / 8
    check("mixed_heat_uses_paid_contributions", mixed_heat_vulnerability == F(1, 5))
    combined = 100 * (1 + mixed_heat_vulnerability + F(15, 100))
    check("burn_and_rule_exposure_both_contribute", combined == 135 and contracts["damage"]["vulnerability"]["total_max"] == 0.4)
    weak_and_strong = [{"dps": 2, "vulnerability": .25, "end": 2}, {"dps": 3, "vulnerability": .15, "end": 5}]
    at1 = [d for d in weak_and_strong if d["end"] > 1]
    at3 = [d for d in weak_and_strong if d["end"] > 3]
    check("burn_axes_and_expiries_independent", max(d["dps"] for d in at1) == 3 and max(d["vulnerability"] for d in at1) == .25 and max(d["vulnerability"] for d in at3) == .15)
    check("freeze_preserves_height_and_fire_coexists", frost["changes_height"] is False and frost["freezes_height"] is True and burn["melts_friendly_freeze"] is False)
    check("cold_waves_not_suppressed_by_global_sampler", frost["per_pool_stack_add_min_interval_s"] == 0)
    cold_times = [F(0), F(7, 10), F(3), F(37, 10)]
    check("two_cold_waves_reach_freeze_before_expiry", len([t for t in cold_times if cold_times[-1] - t < frost["stack_duration_s"]]) == frost["threshold"])
    check("curse_threshold_keeps_attack_reduction", curse["threshold_consumes_base_curse"] is False and F(4) * number(curse["outgoing_attack_reduction_per_stack"]) == F(16, 100))
    draw1, draw2 = seeded_draw("saved-encounter", "attack-17"), seeded_draw("saved-encounter", "attack-17")
    check("curse_save_reload_does_not_reroll", draw1 == draw2 and curse["random_draws_per_attack"] == 1)
    expected_attack = 100 * (1 - F(16, 100)) * (1 - F(30, 100))
    check("curse_expected_damage_example", expected_attack == F(294, 5))

    path = [(F(0), (F(1, 4), F(1, 4))), (F(1), (F(15, 4), F(1, 4)))]
    ledger = {}
    crossing = settle_tolls("A", spans_for_samples(path), ledger)
    back = [(F(1), path[-1][1]), (F(2), path[0][1])]
    returning = settle_tolls("A", spans_for_samples(back), ledger)
    check("four_real_cells_charge_four_times", sum_damage(crossing) == 32 and len(crossing) == 4)
    check("immediate_return_keeps_cell_deadlines", sum_damage(returning) == 0)
    second_monster = settle_tolls("B", spans_for_samples(path), ledger)
    check("cell_deadline_is_per_health_pool", sum_damage(second_monster) == 32)
    cooldown_start = {("A", "zone_toll", (0, 0)): F(2)}
    check("start_cell_already_paid_not_paid_again", sum_damage(settle_tolls("A", spans_for_samples(path), cooldown_start)) == 24)
    teleport = settle_endpoints("A", path, {})
    check("teleport_only_pays_actual_endpoints", sum_damage(teleport) == 16)
    diagonal = spans_for_segment((F(1, 4), F(1, 4)), (F(11, 4), F(11, 4)), 0, 1)
    check("corner_touch_does_not_create_extra_cells", [s[0] for s in diagonal] == [(0, 0), (1, 1), (2, 2)])
    sampled = [(F(i, 120), (F(1, 4) + F(7, 2) * F(i, 120), F(1, 4))) for i in range(121)]
    sampled_hits = settle_tolls("A", spans_for_samples(sampled), {})
    check("same_trajectory_frame_partition_invariant", sampled_hits == crossing)
    stationary = settle_tolls("A", [((0, 0), F(0), F(5))], {})
    check("stationary_zone_period_not_per_frame", sum_damage(stationary) == 24 and len(stationary) == 3)
    overlap = settle_tolls("A", spans_for_samples(path), {}, raw_damage=max(2, 8))
    check("overlap_same_family_selects_one_strongest", sum_damage(overlap) == 32)
    inherited = {("child", family, cell): due for (pool, family, cell), due in ledger.items() if pool == "A"}
    check("fission_inherits_unexpired_cell_deadline", sum_damage(settle_endpoints("child", [(F(1), path[-1][1])], inherited)) == 0)
    field_dps, actual_residence = F(16), F(9, 4)
    partitions = [F(1, 4)] * 9
    check("continuous_field_integrates_paid_residence", sum(field_dps * dt for dt in partitions) == field_dps * actual_residence == 36)

    grid = contracts["electric_network"]
    check("one_bounce_no_secondary_charge", grid["bounce"]["max_hops"] == 1 and grid["bounce"]["adds_charge"] is False and grid["bounce"]["triggers_another_bounce"] is False)
    active = ["AP_HOT_FOOD", "AP_HOT_FOOD", "AP_FREEZER", "AP_COLD_CABINET"]
    check("appliance_parts_deduplicate", len(set(active)) == 3 and set(grid["appliances"]["active_verified_fixture_ids"]) == {"FX14", "FX15", "FX16"})
    enabled_appliances = [a for a in traps["appliances"] if a["design_enabled"]]
    check("shared_appliance_registry_identity", {a["id"] for a in enabled_appliances} == set(grid["appliances"]["active_appliance_ids"]) and {a["fixture_id"] for a in enabled_appliances} == set(grid["appliances"]["active_verified_fixture_ids"]))
    check("pos_has_no_invented_power_source", next(a for a in traps["appliances"] if a["id"] == "AP_POS")["circuit_id"] is None)
    local_examples = [(3, 2), (2, 1), (2, 0)]
    local_damage = [electric["default_overload_base_damage"] * (n + e) for n, e in local_examples]
    check("overload_uses_each_recipient_local_counts", local_damage == [30, 18, 12])
    mixed_D = 3 * F(6, 5) + 2 * F(9, 5)
    check("mixed_charge_contributions_not_last_source", mixed_D == F(36, 5))
    pools = {"A": 5, "B": 5}
    ready, waves = ["A", "B"], []
    for tick in (F(0), F(1, 4)):
        seed = ready.pop(0)
        recipients = [pool for pool, charge in pools.items() if charge > 0]
        raw = 6 * len(recipients)
        pools[seed] -= 5
        waves.append({"time": float(tick), "seed": seed, "targets": recipients, "raw_per_target": raw})
    check("two_full_meters_keep_two_paid_waves", len(waves) == 2 and waves[0]["raw_per_target"] == 12 and waves[1]["raw_per_target"] == 6 and not ready)
    check("queue_bounded_and_no_damage_recursion", grid["max_ready_requests_per_health_pool"] == 1 and grid["pulse_interval_s"] == .25 and contracts["damage"]["secondary_can_proc"] is False)
    oldest = {"expires_at": 7, "contribution": F(6, 5)}
    donor, receiver = [oldest, {"expires_at": 8, "contribution": F(6, 5)}], []
    original_total = len(donor) + len(receiver)
    receiver.append(donor.pop(0))
    check("outer_ring_transfer_preserves_charge_budget_and_deadline", len(donor) + len(receiver) == original_total and receiver[0]["expires_at"] == 7 and receiver[0]["contribution"] == F(6, 5))

    physical = F(2) * (1 - F(0))
    spiritual = F(3) * (1 - F(3, 4))
    check("cross_channel_overlap_never_reduces_existing_toll", max(physical, spiritual) == 2 and max(F(2), F(3)) * F(1, 4) < physical)
    heat_after = 6 + 3
    ignitions, remainder = divmod(heat_after, burn["heat"]["threshold"])
    check("multi_heat_application_keeps_remainder", ignitions == 1 and remainder == 1)
    by_id = {n["id"]: n for n in all_nodes}
    heat15 = next(e for e in by_id["T01.B1"]["effects"] if e["status"] == "heat")
    heat25 = next(e for e in by_id["T07.A1"]["effects"] if e["status"] == "heat")
    check("vulnerability_ceiling_has_real_sources", heat15["burn_vulnerability"] == .15 and heat25["burn_vulnerability"] == .25 and any(e["status"] == "rule_cooperation_vulnerability" for e in by_id["T06.B1"]["effects"]))
    q_node = next(e for e in by_id["T02.A1"]["effects"] if e["status"] == "poison")
    check("poison_expiry_is_actual_pool_terminal", q_node["expires_at"] == "health_pool_terminal")
    sniper = by_id["T01.A1"]["parameters"]
    rapid = by_id["T01.B1"]["parameters"]
    sniper_dps = number(sniper["damage"]) / number(sniper["interval_s"])
    rapid_dps = number(rapid["damage"]) / number(rapid["interval_s"])
    pen = number(sniper["armor_penetration_pp"]) / 100
    rapid_burn_dps = number(heat15["burn_dps"])
    burn_amp = 1 + number(heat15["burn_vulnerability"])
    check("sniper_and_rapid_have_distinct_single_target_niches", (rapid_dps + rapid_burn_dps) * burn_amp > sniper_dps and sniper_dps * (1 - max(F(0), F(3, 4) - pen)) > (rapid_dps * F(1, 4) + rapid_burn_dps) * burn_amp)

    evidence.update({
        "zone_example": {"four_fresh_cells": 32, "start_prepaid": 24, "immediate_return": 0, "true_teleport_endpoints": 16},
        "poison_example": {"load": 101, "raw_dps": 50.5, "single_matured_dose_load": 3},
        "vulnerability_example": {"after_defense_damage": 100, "burn": .20, "rule": .15, "result": 135},
        "curse_expected_damage_example": {"base": 100, "outgoing_reduction": .16, "failure_probability": .30, "expected_not_guaranteed_damage": float(expected_attack)},
        "electric_local_example": local_damage,
        "electric_two_ready_example": waves,
        "threshold_reachability": threshold_evidence,
        "single_target_example": {"assumptions": "Sustained legal hit, armor stated, ward zero, burn already established, no other towers; not a combat simulation.", "armor_zero_sniper_dps": float(sniper_dps), "armor_zero_rapid_with_burn_dps": float((rapid_dps + rapid_burn_dps) * burn_amp), "armor_75_sniper_dps": float(sniper_dps * (1 - max(F(0), F(3, 4) - pen))), "armor_75_rapid_with_burn_dps": float((rapid_dps * F(1, 4) + rapid_burn_dps) * burn_amp)},
        "scope": "These small deterministic fixtures exercise disclosed rules. They do not execute the game client or measure actual encounter balance."
    })
    report = {"version": "TD03", "status": "static_and_reference_checks_passed", "runtime_tested": False,
              "input_sha256": {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in paths},
              "counts": {"families": 10, "l2": 20, "l3": 40, "trap_families": 16, "trap_l2": 32, "trap_l3": 32, "monsters": 60, "checks": len(checks)},
              "checks": checks, "reference_examples": evidence,
              "not_verified": ["full combat runtime", "real navigation/LOS/heights", "touch input and frame performance", "all sixty AI", "seven-night economy and fun balance"]}
    target = ROOT / args.report
    target.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "counts": report["counts"], "report": str(target)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
