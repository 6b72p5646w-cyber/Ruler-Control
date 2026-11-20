#!/usr/bin/env python3
"""BC02 duration, source-budget and actual routed-receipt counterexamples.

Boundary fixtures are identified separately from the BC01 Director's unmodified
real reference routes. No check asserts that production actors/physics exist.
"""
from copy import deepcopy
import hashlib
import inspect
import json
from pathlib import Path

from bc01_campaign_reference import Player, ATTACKS, level_stats
from bc01_director_reference import Director, run_night
from bc01_map_reference import StoreMap, encounter_catalog
from bc01_facility_reference import FacilitiesBC01, stable_choice
from bc02_facility_reference import FacilitiesBC02, load_contract
from check_bc01_facilities import request, propose, accept

ROOT = Path(__file__).resolve().parents[1]
CONTRACT = load_contract()
RESULTS, EVIDENCE = [], {}


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
    m = FacilitiesBC02("night1", attempt, seed, design_simulation=True)
    expect(m.actual_world_tick("initial", at, True)["ok"])
    return m


def use(m, fid="FR01", number=1):
    result = m.customer_use(**request(m, fid, number))
    expect(result["ok"], result)
    return result


def kind(m, name):
    return [e for e in m.active_modifiers() if e["reward"]["kind"] == name]


def owner_commit(m, offer, player):
    """Receipt facts are read from BC01.Player, never a claimed boolean hit."""
    before = player.hp
    player.heal(offer["request_id"], offer["maximum_fraction_of_actual_max_hp"] * player.max_hp)
    receipt = {"request_id": offer["request_id"], "at_world_time": m.state["now"],
               "hp_before": before, "hp_after": player.hp, "actual_max_hp": player.max_hp,
               "alive_before": before > 0,
               "request_recorded_by_hp_owner": offer["request_id"] in player.heal_receipts}
    result = m.hp_regen_ack(offer["request_id"], receipt)
    expect(result["ok"], result)
    return result


def advance(m, to, *, player=None, alive=True, paused=False):
    result = m.actual_world_tick(f"tick:{len(m.state['event_receipts'])}:{to}", to, alive, paused)
    expect(result["ok"], result)
    for offer in result["requests"]:
        if offer["request_type"] == "hp_regen_budgeted_interval":
            expect(player is not None, "an actual reference HP owner is required")
            owner_commit(m, offer, player)
    return result


def lucky_number(m, desired):
    # Select a published test-fixture identity, not a gameplay reroll operation.
    for number in range(100, 300):
        req = request(m, "FR14", number)
        receipt = req["paid_order_receipt"]
        parts = [m.state["seed"], m.state["night_id"], receipt["logical_customer_id"], receipt["logical_order_id"], "FR14"]
        variant = m.roles["FR14"]["reward"]["variants"][stable_choice("BC01_CUSTOMER_LUCKY_RECEIPT", parts, 3)]
        if variant["kind"] == desired:
            return number
    raise AssertionError("no deterministic fixture identity")


def default_closed():
    m = FacilitiesBC02("night1", 1)
    before = m.snapshot()
    expect(not m.raid_started("raid1")["ok"])
    expect(not m.actual_world_tick("t", 10, True)["ok"])
    expect(not m.customer_use(**request(m))["ok"])
    expect(before == m.snapshot())
    expect(CONTRACT["runtime_integrated"] is False and CONTRACT["runtime_enabled"] is False)


def validation_preserved():
    old = inspect.getsource(FacilitiesBC01.customer_use)
    replacement = ('if (len(self.state["bank"][facility_id]) >= self.contract["bank"]["per_facility_max_tokens"]\n'
                   '                or self._bank_total() >= self.contract["bank"]["whole_store_max_tokens"]):')
    old = old.replace('if len(self.state["bank"][facility_id]) >= 2 or self._bank_total() >= 8:', replacement)
    anchor = '            return self._result(False, "invalid_use_or_payment_time")\n'
    old = old.replace(anchor, anchor +
        '        if any(raid["started_at"] <= at and (raid["ended_at"] is None or at < raid["ended_at"])\n'
        '               for raid in self.state["raid_intervals"] for at in (used_at, paid_at)):\n'
        '            return self._result(False, "normal_customer_service_or_payment_occurred_during_actual_raid")\n')
    old = old.replace('        if not self._powered(facility_id, used_at):\n',
        '        started_at = facts.get("actual_use_started_at", used_at - duration)\n'
        '        if (not isinstance(started_at, (int, float)) or isinstance(started_at, bool) or not math.isfinite(started_at)\n'
        '                or not 0 <= started_at <= used_at or abs(used_at - started_at - duration) > 1e-6):\n'
        '            return self._result(False, "invalid_actual_service_interval")\n'
        '        if any(max(started_at, raid["started_at"]) < min(used_at, raid["ended_at"] if raid["ended_at"] is not None else self.state["now"])\n'
        '               for raid in self.state["raid_intervals"]):\n'
        '            return self._result(False, "normal_customer_service_interval_overlaps_actual_raid")\n'
        '        if not self._service_power_valid(facility_id, started_at, used_at, facts, receipt):\n')
    expect(old.strip() == inspect.getsource(FacilitiesBC02.customer_use).strip(), "customer source validation drift")


def contract_lifetimes():
    expect(CONTRACT["temporary_traps"]["lifetime_world_seconds"] is None)
    for role in CONTRACT["roles"]:
        reward = role["reward"]
        if reward is None:
            continue
        for variant in reward.get("variants", [reward]):
            expect("duration_s" not in variant, role["id"])
            if "group" in variant:
                expect(variant["lifetime"] == "actual_raid", role["id"])
    expect(CONTRACT["bank"]["whole_store_max_tokens"] == 2 * CONTRACT["bank"]["covered_reward_sources"])


def rejects_fact(field, value):
    m = model(); req = request(m, "FR03")
    req["facts"][field] = value
    before = m.snapshot()
    expect(not m.customer_use(**req)["ok"])
    expect(m.snapshot() == before)


def independent_source_storage():
    m = model()
    for index, role in enumerate(CONTRACT["roles"]):
        if role["reward"] is not None:
            use(m, role["id"], 10 * index + 1)
            use(m, role["id"], 10 * index + 2)
    expect(m._bank_total() == 24)
    expect(all(len(m.state["bank"][r["id"]]) == 2 for r in CONTRACT["roles"] if r["reward"] is not None))
    expect(use(m, "FR01", 900)["reason"] == "use_completed_bank_full_no_replacement")
    m.raid_started("raid1"); expect(len(m.state["bank"]["FR01"]) == 1)
    expect(not m.customer_use(**request(m, "FR01", 900))["ok"], "overflow cannot replay after a slot opens")


def two_business_cycles():
    m = model()
    for fid in ("FR01", "FR05", "FR06", "FR09", "FR11", "FR12"):
        use(m, fid, int(fid[2:]) * 10 + 1); use(m, fid, int(fid[2:]) * 10 + 2)
    m.raid_started("raid1")
    first = {e["source_facility_id"]: deepcopy(e) for e in m.state["buffs"]}
    expect(len(first) == 6 and all(len(m.state["bank"][fid]) == 1 for fid in first))
    advance(m, 30)
    expect(len(m.active_modifiers()) == 6)
    expect(m.raid_ended("raid1")["ok"])
    advance(m, 330)
    m.raid_started("raid2"); advance(m, 511)
    second = {e["source_facility_id"]: e for e in m.active_modifiers()}
    expect(len(second) == 6)
    expect(all(second[fid]["tokens"] != first[fid]["tokens"] for fid in first))
    expect(all(second[fid]["reward"] == first[fid]["reward"] for fid in first))
    expect(all(len(m.state["bank"][fid]) == 0 for fid in first))
    expect(m.raid_ended("raid2")["ok"] and not m.active_modifiers())
    EVIDENCE["two_business_cycles"] = {"first_raid_seconds": 20, "safe_business_wait_seconds": 300,
        "second_raid_seconds": 181, "whole_raid_support_sources": sorted(first), "different_original_tokens": True,
        "scenario": "explicit finite lifecycle fixture, not production playthrough"}


def long_raid(duration):
    m = model()
    for n, fid in enumerate(("FR01", "FR04", "FR05", "FR06", "FR09", "FR11", "FR12")):
        use(m, fid, n + 1)
    bank = deepcopy(m.state["bank"])
    advance(m, 310)
    expect(m.state["bank"] == bank)
    m.raid_started("raid1"); advance(m, 310 + duration)
    expect(len(m.active_modifiers()) == 7)
    expect(all(e["lifetime"] == "actual_raid" and "expires_at" not in e for e in m.active_modifiers()))
    m.raid_ended("raid1"); expect(not m.active_modifiers())


def pause_and_ads():
    m = model(); player = Player(hp=20)
    use(m, "FR03"); use(m, "FR10", 2); use(m, "FR02", 3)
    m.raid_started("raid1")
    req = propose(m)["request"]; expect(accept(m, req)["ok"])
    before = m.snapshot(); hp_before = player.hp
    for ad_wall_seconds in (1, 30, 180):
        advance(m, m.state["now"], player=player, paused=True)
    after = m.snapshot()
    before.pop("event_receipts"); after.pop("event_receipts")
    expect(before == after and player.hp == hp_before)
    expect(not m.actual_world_tick("bad-ad-wall-time", m.state["now"] + 180, True, True)["ok"])
    d = Director(seed=3, night_index=7); d.advance(25)
    snapshot = d.snapshot(); d.advance(180, paused=True)
    expect(d.snapshot() == snapshot)


def power_resume():
    m = model(); player = Player(hp=1)
    for n, fid in enumerate(("FR01", "FR03", "FR04", "FR05", "FR06", "FR09", "FR11")):
        use(m, fid, n + 1)
    m.raid_started("raid1"); advance(m, 30, player=player)
    regen = kind(m, "hp_regen")[0]
    expect(abs(player.hp - 5) < 1e-8)
    m.power_changed("off", "MAIN", False)
    expect([e["source_facility_id"] for e in m.active_modifiers()] == ["FR11"])
    expect(not m.electric_overload_allowed())
    advance(m, 210, player=player)
    expect(abs(player.hp - 5) < 1e-8)
    m.power_changed("on", "MAIN", True)
    resumed = kind(m, "hp_regen")[0]
    expect(resumed["effect_id"] == regen["effect_id"] and resumed["tokens"] == regen["tokens"])
    expect(resumed["heal_budget_remaining_fraction"] == regen["heal_budget_remaining_fraction"])
    expect(len(m.active_modifiers()) == 7)
    advance(m, 220, player=player)
    expect(abs(player.hp - 7) < 1e-8, "off interval must never catch up")


def pending_power_reservation():
    m = model(); use(m, "FR05", 1)
    delayed_safe_use = request(m, "FR03", 3)
    fixed = deepcopy(m.state["bank"]["FR05"][0])
    advance(m, 11)
    m.power_changed("off", "MAIN", False); m.raid_started("raid1")
    advance(m, 190); expect(not m.active_modifiers())
    m.raid_ended("raid1")
    expect(m.state["bank"]["FR05"] == [fixed])
    m.raid_started("raid2"); m.power_changed("on", "MAIN", True)
    expect(kind(m, "move_speed_bonus")[0]["tokens"] == [fixed["token_id"]])
    expect(not m.state["bank"]["FR05"])
    advance(m, 191)
    expect(m.customer_use(**delayed_safe_use)["ok"])
    m.power_changed("off2", "MAIN", False); m.power_changed("on2", "MAIN", True)
    expect(not kind(m, "hp_regen"), "late-delivered safe credit must not activate in the current raid")


def actual_raid_service_gate():
    m = model(); safe = request(m, "FR03", 1)
    advance(m, 20); m.raid_started("raid1"); advance(m, 30)
    expect(m.customer_use(**safe)["ok"], "late delivery of a genuinely old safe use is allowed")
    expect(not kind(m, "hp_regen") and len(m.state["bank"]["FR03"]) == 1)
    for fid in ("FR01", "FR03", "FR10"):
        bad = request(m, fid, int(fid[2:]) + 20)
        before = m.snapshot()
        result = m.customer_use(**bad)
        expect(not result["ok"] and result["reason"] == "normal_customer_service_or_payment_occurred_during_actual_raid")
        expect(m.snapshot() == before)
    historical_bad = request(m, "FR03", 99)
    m.raid_ended("raid1"); advance(m, 40)
    expect(not m.customer_use(**historical_bad)["ok"], "a raid-time service cannot be laundered after raid end")
    m.raid_started("raid2")
    expect(kind(m, "hp_regen"), "the delayed safe receipt is next-raid support")


def service_interval_crosses_closed_raid():
    m = model(at=19); advance(m, 20); m.raid_started("short-raid")
    advance(m, 21); m.raid_ended("short-raid"); advance(m, 22)
    req = request(m, "FR03")
    req["facts"].update(actual_use_at=22, actual_use_started_at=19, use_duration_s=3)
    for use_row in req["paid_order_receipt"]["facilities_used"]:
        if use_row["facility_id"] == "FR03":
            use_row["actual_use_at"] = 22
    before = m.snapshot()
    result = m.customer_use(**req)
    expect(result["reason"] == "normal_customer_service_interval_overlaps_actual_raid")
    expect(m.snapshot() == before)


def heal_cap(level):
    m = model(); use(m, "FR03"); player = Player(level=level, hp=1)
    m.raid_started("raid1")
    advance(m, 30, player=player)
    expect(abs(player.hp - (1 + player.max_hp * .04)) < 1e-8)
    advance(m, 90, player=player)
    expect(abs(player.hp - (1 + player.max_hp * .16)) < 1e-8)
    advance(m, 191, player=player)
    expect(abs(player.hp - (1 + player.max_hp * .20)) < 1e-8)
    expect(not kind(m, "hp_regen"))
    advance(m, 400, player=player)
    expect(abs(player.hp - (1 + player.max_hp * .20)) < 1e-8)


def healing_group_budget():
    m = model(); use(m, "FR03"); use(m, "FR14", lucky_number(m, "hp_regen"))
    player = Player(hp=1); m.raid_started("raid1")
    expect(len(kind(m, "hp_regen")) == 1)
    result = advance(m, 190, player=player)
    offer = next(r for r in result["requests"] if r["request_type"] == "hp_regen_budgeted_interval")
    expect(abs(player.hp - 31) < 1e-8)
    expect([a["source_facility_id"] for a in offer["allocations"]] == ["FR03", "FR14"])
    expect(offer["allocations"][0]["to_world_time"] <= offer["allocations"][1]["from_world_time"])
    expect(all(abs(e["heal_budget_remaining_fraction"]) < 1e-9 for e in m.state["buffs"]))
    EVIDENCE["healing_owner"] = {"owner_class": "bc01_campaign_reference.Player", "combined_rate": .002,
        "source_budgets": {"FR03": .2, "FR14_if_heal_variant": .1}, "single_interval_seconds": 180,
        "level_1_actual_restored_hp": player.hp - 1, "nonoverlapping_source_allocations": offer["allocations"],
        "level_20_max_hp": level_stats(20)["max_hp"], "level_20_combined_max_hp_restoration": 75.6,
        "production_hp_owner": False}


def full_health_no_budget_loss():
    m = model(); use(m, "FR03"); player = Player(hp=100); m.raid_started("raid1")
    advance(m, 90, player=player)
    expect(kind(m, "hp_regen")[0]["heal_budget_remaining_fraction"] == .2)
    attack = next(key for key, value in ATTACKS.items() if 1 <= value["hp_damage"] <= 30)
    player.attack(attack, ["root", "pool", "actor", "first-hit"], 90, collision=True, hostile=True)
    hp_after_damage = player.hp
    advance(m, 100, player=player)
    expect(abs(player.hp - hp_after_damage - 2) < 1e-8)
    expect(abs(kind(m, "hp_regen")[0]["heal_budget_remaining_fraction"] - .18) < 1e-8)


def partial_heal_allocation_and_circuits():
    m = model(); use(m, "FR03"); use(m, "FR14", lucky_number(m, "hp_regen"))
    player = Player(hp=90); m.raid_started("raid1")
    advance(m, 190, player=player)
    by_source = {e["source_facility_id"]: e for e in m.state["buffs"]}
    expect(player.hp == 100)
    expect(abs(by_source["FR03"]["heal_budget_remaining_fraction"] - .1) < 1e-8)
    expect(by_source["FR14"]["heal_budget_remaining_fraction"] == .1)
    m.power_changed("c2-off", "C2", False)
    expect(kind(m, "hp_regen")[0]["source_facility_id"] == "FR14")
    attack = next(key for key, value in ATTACKS.items() if 1 <= value["hp_damage"] <= 30)
    player.attack(attack, ["root", "pool", "actor", "second-hit"], 190, collision=True, hostile=True)
    before = player.hp; advance(m, 200, player=player)
    expect(abs(player.hp - before - 2) < 1e-8)
    expect(abs(by_source["FR14"]["heal_budget_remaining_fraction"] - .08) < 1e-8)
    expect(abs(by_source["FR03"]["heal_budget_remaining_fraction"] - .1) < 1e-8)
    m.power_changed("c2-on", "C2", True)
    expect(kind(m, "hp_regen")[0]["source_facility_id"] == "FR03")


def invalid_heal_receipt():
    m = model(); use(m, "FR03"); m.raid_started("raid1")
    offer = m.actual_world_tick("offer", 20, True)["requests"][0]
    before = m.snapshot()
    bad = {"request_id": offer["request_id"], "at_world_time": 20,
           "hp_before": 50, "hp_after": 99, "actual_max_hp": 100,
           "alive_before": True, "request_recorded_by_hp_owner": True}
    expect(not m.hp_regen_ack(offer["request_id"], bad)["ok"])
    expect(m.snapshot() == before)


def pending_hp_transaction():
    m = model(); use(m, "FR03"); m.raid_started("raid1")
    result = m.actual_world_tick("offer", 20, True)
    offer = result["requests"][0]; before = m.snapshot()
    expect(not m.actual_world_tick("later", 21, True)["ok"])
    expect(not m.power_changed("off", "MAIN", False)["ok"])
    expect(not m.raid_ended("raid1")["ok"])
    expect(not m.night_ended()["ok"])
    expect(not m.acknowledge(offer["request_id"])["ok"])
    expect(m.snapshot() == before)
    restored = FacilitiesBC02.restore(m.snapshot(), design_simulation=True)
    expect(restored.state["heal_pending"] == offer["request_id"])
    player = Player(hp=50); owner_commit(restored, offer, player)
    receipt = restored.state["heal_commits"][offer["request_id"]]
    budget = deepcopy(restored.state["buffs"])
    expect(restored.hp_regen_ack(offer["request_id"], receipt)["reason"] == "hp_ack_replay")
    expect(budget == restored.state["buffs"])
    bad = deepcopy(receipt); bad["hp_after"] += 1
    expect(not restored.hp_regen_ack(offer["request_id"], bad)["ok"])


def no_revive_or_business_heal():
    m = model(); use(m, "FR03"); player = Player(hp=0)
    advance(m, 100, player=player, alive=False)
    m.raid_started("raid1"); advance(m, 180, player=player, alive=False)
    expect(player.hp == 0 and not m.state["heal_commits"])
    # Death between the producer's interval and atomic HP owner application.
    result = m.actual_world_tick("last-boundary", 190, True)
    owner_commit(m, result["requests"][0], player)
    expect(player.hp == 0 and kind(m, "hp_regen")[0]["heal_budget_remaining_fraction"] == .2)


def survival_finite():
    m = model()
    for raid in range(4):
        use(m, "FR10", 2 * raid + 1); use(m, "FR10", 2 * raid + 2)
        m.raid_started(f"raid{raid}")
        advance(m, m.state["now"] + 60)
        m.raid_ended(f"raid{raid}")
    expect(m.state["survival_payouts"] == 12)
    expect(m.state["survival_remaining"] == 0 and not m.state["bank"]["FR10"])
    payouts = [r for r in m.pending_requests() if r["request_type"] == "payout"]
    expect(sum(r["coin"] for r in payouts) == sum(r["xp"] for r in payouts) == 12)


def overtime_clock():
    m = model(at=715); use(m, "FR10"); use(m, "FR03", 2); use(m, "FR05", 3)
    player = Player(hp=1); m.raid_started("raid1"); advance(m, 800, player=player)
    expect(m.state["survival_progress"] == 5 and m.state["survival_payouts"] == 0)
    expect(kind(m, "move_speed_bonus") and abs(player.hp - 18) < 1e-8)


def trap_whole_raid():
    m = model(); use(m, "FR02"); use(m, "FR02", 2); m.raid_started("raid1")
    offer = propose(m)["request"]
    expect(offer["lifetime_s"] is None)
    expect(accept(m, offer)["ok"])
    advance(m, 191)
    expect(m.state["active_trap"] is not None and "expires_at" not in m.state["active_trap"])
    expect(not propose(m)["ok"])
    expect(not m.temporary_inventory_action("sell", "temp1")["ok"])
    facts = {k: True for k in ("actual_new_entry", "actual_collision", "manifested", "hostile",
                               "independent_pool", "ground_layer", "world_consumer_verified")}
    expect(m.trap_triggered("fixture-entry", "temp1", "fixture-hostile-pool", facts)["ok"])
    expect(not m.trap_triggered("fixture-entry-again", "temp1", "fixture-hostile-pool", facts)["ok"])
    second = propose(m)["request"]; expect(accept(m, second, iid="temp2")["ok"])
    expect(m.state["trap_deployments_this_raid"] == 2)
    expect(m.raid_ended("raid1")["ok"] and m.state["active_trap"] is None)
    expect(not m.state["bank"]["FR02"])


def trap_reject_retains_rng():
    m = model(); use(m, "FR02"); m.raid_started("bc01:night1:raid:1")
    fixed = deepcopy(m.state["bank"]["FR02"][0]); first = propose(m)["request"]
    expect(not accept(m, first, current_nav_revision="changed")["ok"])
    advance(m, 310)
    again = propose(m)["request"]
    expect(m.state["bank"]["FR02"][0] == fixed)
    expect(again["variant"] == first["variant"] and again["placement"] == first["placement"])
    m.raid_ended("bc01:night1:raid:1")
    expect(m.state["bank"]["FR02"][0]["eligible_raid_id"] is None)


def retry_no_reroll():
    results = []
    for attempt in (1, 2):
        m = model(attempt=attempt)
        trap = use(m, "FR02")["token"]
        lucky = use(m, "FR14", 2)["token"]
        advance(m, 310)
        clone = FacilitiesBC02.restore(m.snapshot(), design_simulation=True)
        expect(clone.snapshot() == m.snapshot())
        m.raid_started("bc01:night1:raid:1")
        site = propose(m)["request"]["placement"]
        results.append((trap, lucky, site))
    for index in (0, 1):
        expect(results[0][index]["stable_source_key"] == results[1][index]["stable_source_key"])
        expect(results[0][index]["reward"] == results[1][index]["reward"])
        expect(results[0][index]["trap_variant"] == results[1][index]["trap_variant"])
        expect(results[0][index]["token_id"] != results[1][index]["token_id"])
    expect(results[0][2] == results[1][2])


def night_cleanup():
    m = model(); use(m, "FR01"); use(m, "FR05", 2); use(m, "FR02", 3)
    m.power_changed("off", "MAIN", False); m.raid_started("raid1")
    ended = m.night_ended()
    expect(ended["ok"] and ended["expired_bank_counts"] == {"FR01": 1, "FR02": 1, "FR05": 1})
    expect(m._bank_total() == 0 and not m.state["reserved_power"] and not m.active_modifiers())
    expect(not m.raid_started("raid2")["ok"])


def actual_director_receipts():
    report = run_night(3, StoreMap(), night_index=7, attempt_id=1, action_duration_factor=.6,
                       encounter_pool=[p for p in encounter_catalog(7) if not p["requires_combat_after_rule"]])
    m = FacilitiesBC02(report["summary"]["night_id"], 1, 3, design_simulation=True)
    player = Player(hp=20)
    counts, actual_raids, outages = {}, [], []
    starts = {}
    for index, event in enumerate(report["events"]):
        if event["time"] > m.state["now"]:
            advance(m, event["time"], player=player, alive=player.alive)
        event_kind = event["kind"]
        if event_kind == "facility_use_committed":
            req = event["request"]
            expect(m.customer_use(**req)["ok"])
            counts[req["facility_id"]] = counts.get(req["facility_id"], 0) + 1
        elif event_kind == "raid_started":
            expect(m.raid_started(event["raid_id"])["ok"])
            starts[event["raid_id"]] = event["time"]
        elif event_kind == "raid_ended":
            actual_raids.append({"raid_id": event["raid_id"], "duration_s": event["time"] - starts[event["raid_id"]],
                                 "active_sources_at_real_end": [e["source_facility_id"] for e in m.active_modifiers()]})
            expect(m.raid_ended(event["raid_id"])["ok"])
        elif event_kind == "power_changed":
            expect(m.power_changed(f"power:{index}", "MAIN", event["power_on"])["ok"])
            outages.append({"at": event["time"], "power_on": event["power_on"]})
    expect(counts == {"FR03": 2, "FR01": 5, "FR10": 5, "FR02": 1, "FR05": 2})
    expect(report["summary"]["ordinary_work_during_raid_seconds"] == 0)
    # Extend only the waiting lifecycle after genuinely routed first-order use.
    delayed = FacilitiesBC02(report["summary"]["night_id"], 1, 3, design_simulation=True)
    first_uses = [e for e in report["events"] if e["kind"] == "facility_use_committed"][:3]
    for event in first_uses:
        advance(delayed, event["time"], player=player)
        expect(delayed.customer_use(**event["request"])["ok"])
    bank = deepcopy(delayed.state["bank"])
    advance(delayed, delayed.state["now"] + 300, player=player)
    expect(delayed.state["bank"] == bank)
    delayed.raid_started("delayed-first-order-fixture")
    expect(kind(delayed, "hp_regen") and kind(delayed, "direct_damage_reduction"))
    EVIDENCE["actual_bc01_director"] = {"seed": 3, "night_index": 7, "attempt_id": 1,
        "manual_action_factor": .6, "paid_orders": report["summary"]["paid_orders"], "accepted_source_counts": counts,
        "all_customer_receipts_forwarded_without_modification": True, "actual_route_geometry": "bc01_map_reference.StoreMap",
        "actual_reference_raid_durations": actual_raids, "actual_outage_boundaries": outages,
        "ordinary_work_during_raid_seconds": 0, "actual_reference_hp_restored": player.hp - 20,
        "survival_payouts": m.state["survival_payouts"], "delayed_first_paid_order_300_seconds_retained": True,
        "additional_delay_is_lifecycle_counterexample_not_director_schedule": True,
        "optional_sources_without_real_director_routes": ["FR06", "FR09", "FR11", "FR12", "FR13", "FR14"],
        "production_npc_or_world_adapter": False, "actual_client_runtime": False}


def run():
    check("default actual-client adapter stays closed", default_closed)
    check("strict BC01 source validation is preserved with capacity and actual raid-history gate", validation_preserved)
    check("machine-readable lifetime fields contain no old short support deadlines", contract_lifetimes)
    for field, value in (("normal_customer", False), ("customer_kind", "monster"), ("actual_use_completed", False),
                         ("consumer_registered", False), ("facility_geometry_bound", False), ("same_order_service", False),
                         ("source_item_owner_customer", False), ("route_service_authorized", False),
                         ("progress_complete", False), ("origin_kind", "player_chore")):
        check("reject unsupported real-use proof: " + field, lambda f=field, v=value: rejects_fact(f, v))
    check("two tokens per source provide 24 independent slots without checkout crowding", independent_source_storage)
    check("different 20 and 181 second raids consume different reserves across business cycles", two_business_cycles)
    for duration in (20, 80, 181, 300):
        check(f"300 second bank wait then {duration} second raid keeps maintained support", lambda d=duration: long_raid(d))
    for name, fn in (("menu or ad pause cannot advance the actual Director or facility clocks", pause_and_ads),
                     ("180 second outage stops power effects and restores same budget without catchup", power_resume),
                     ("never-powered reservation carries but late-delivered safe credit cannot activate this raid", pending_power_reservation),
                     ("real raid intervals reject current or delayed raid-time service but allow old safe receipts for next raid", actual_raid_service_gate),
                     ("a service from 19 to 22 cannot cross the closed raid from 20 to 21", service_interval_crosses_closed_raid),
                     ("FR03 and FR14 allocate nonoverlapping healing time and finite actual budgets", healing_group_budget),
                     ("full-health seconds consume no budget and cannot be replayed after damage", full_health_no_budget_loss),
                     ("partial actual heal only debits its source and circuit loss selects the remaining source", partial_heal_allocation_and_circuits),
                     ("HP owner cannot acknowledge more healing than the offered live interval", invalid_heal_receipt),
                     ("unresolved actual HP transaction blocks time/power/close and survives snapshot", pending_hp_transaction),
                     ("business, dead intervals and a late dead owner never heal or revive", no_revive_or_business_heal),
                     ("survival support remains finite at 12 coins and 12 XP per night", survival_finite),
                     ("720 cutoff stops payouts while unresolved raid support continues", overtime_clock),
                     ("one-charge safe-map trap waits 181 seconds but never duplicates or refunds", trap_whole_raid),
                     ("rejected placement preserves fixed type/site and the unplaced credit", trap_reject_retains_rng),
                     ("attempt rollback and snapshot keep committed random variants and sites", retry_no_reroll),
                     ("night close clears unused reserves and reports their expiry", night_cleanup),
                     ("actual BC01 Director routes feed unmodified paid-use receipts through real power/raid events", actual_director_receipts)):
        check(name, fn)
    for level in (1, 20):
        check(f"actual level {level} HP owner respects 0.2% rate and 20% source budget", lambda l=level: heal_cap(l))


if __name__ == "__main__":
    run()
    sources = ["content/facilities_bc02.json", "scripts/bc02_facility_reference.py", "scripts/check_bc02_facilities.py",
               "docs/95_bc02_facility_duration.md"]
    report = {"version": "BC02", "scope": "bounded facility design reference and actual BC01 reference-route slice",
              "actual_client_runtime": False, "production_ad_sdk": False,
              "passed": sum(r["passed"] for r in RESULTS), "failed": sum(not r["passed"] for r in RESULTS),
              "checks": RESULTS, "evidence": EVIDENCE,
              "source_sha256": {p: hashlib.sha256((ROOT / p).read_bytes()).hexdigest() for p in sources if (ROOT / p).exists()}}
    (ROOT / "docs/bc02_facility_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "failed": report["failed"],
                      "failures": [r for r in RESULTS if not r["passed"]], "actual_client_runtime": False}, ensure_ascii=False))
    raise SystemExit(bool(report["failed"]))
