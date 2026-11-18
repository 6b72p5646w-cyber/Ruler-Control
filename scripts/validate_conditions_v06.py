#!/usr/bin/env python3
"""Validate V0.6 contracts and finite source-dependency witnesses.

This is not a game engine, a timing simulator, or a proof that an encounter can
be won. Each encounter starts from its own NEW_SHIFT and declared action
instances. The search applies delete effects (``invalidates``), never a
monotone union of all possible facts. An operator is one declared instance;
another order, batch, or receipt requires another explicitly named operator.

Usage: python scripts/validate_conditions_v06.py [--compact]
Writes a JSON report to stdout and exits nonzero on any failed check.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict, deque
import hashlib
import json
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
CORE_FILE = "content/condition_lifecycle_v06.json"
GRAPH_FILE = "content/condition_reachability_v06.json"
BLUEPRINT_FILE = "content/encounter_blueprints.json"
MONSTERS = {f"F{i:02d}" for i in range(1, 61)}
RULES = {f"H{i:02d}" for i in range(1, 21)}
EVENTS = {f"E{i:03d}" for i in range(1, 73)}
PHASE_INDEX = {"D04": -1, **{f"N0{i}": i - 1 for i in range(1, 7)}}
NIGHT_PHASES = set(PHASE_INDEX) - {"D04"}
TIMER_CLOCKS = {"world_simulation", "shift_budget", "local_qte"}
SUPPLY_TYPES = {
    "reusable_shop_tool", "finite_shop_consumable", "visitor_owned_payload",
    "existing_task_instance", "optional_trade_stock",
}
# Canonical JSON object digests, not formatting-dependent whole-file hashes.
# An intentional blueprint revision must explicitly review and update these.
CANONICAL_DIGESTS = {
    "F12": "fcefacb291809f3107045d780126423aa9831320b3180c1b86ff0d5053f8fdd7",
    "F13": "c08cce5345439f83ab999cb24950131961aae1c115bb1e7f5a0ef6380adce426",
}
REQUIRED_NEGATIVES = [
    ({"P_REAL_CUT", "P_F21_REAL_CUT"}, {"F26", "F32"}),
    ({"P_REPAIR"}, {"F10"}),
    ({"P_REFUND"}, {"F19"}),
    ({"P_WORK_TRACE_2"}, {"F38"}),
    ({"P_CHECKOUT_2"}, {"F51"}),
    ({"P_CLAIM_WINDOW_EVIDENCE"}, {"F43"}),
    ({"P_RECEIVE_THREE_MANIFEST"}, {"F54"}),
]


def string_list(value: Any, nonempty: bool = False) -> bool:
    return (isinstance(value, list) and (bool(value) or not nonempty)
            and all(isinstance(x, str) and bool(x.strip()) for x in value))


def number(value: Any) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


class Audit:
    def __init__(self) -> None:
        self.checks = 0
        self.errors: list[dict[str, str]] = []
        self.hashes: dict[str, str] = {}

    def need(self, value: Any, path: str, message: str) -> None:
        self.checks += 1
        if not value:
            self.errors.append({"path": path, "message": message})

    def equal(self, data: dict, key: str, expected: Any, path: str) -> None:
        self.need(data.get(key) == expected and
                  (not isinstance(expected, bool) or data.get(key) is expected),
                  f"{path}/{key}", f"expected {expected!r}; got {data.get(key)!r}")

    def read(self, relative: str) -> dict:
        try:
            raw = (ROOT / relative).read_bytes()
            self.hashes[relative] = hashlib.sha256(raw).hexdigest()
            result = json.loads(raw)
            self.need(isinstance(result, dict), relative, "root must be an object")
            return result if isinstance(result, dict) else {}
        except (OSError, ValueError) as exc:
            self.need(False, relative, f"cannot read JSON: {exc}")
            return {}

    def rows(self, data: dict, key: str, path: str) -> list[dict]:
        value = data.get(key)
        self.need(isinstance(value, list), f"{path}/{key}", "must be an array")
        if not isinstance(value, list):
            return []
        self.need(all(isinstance(x, dict) for x in value), f"{path}/{key}",
                  "all rows must be objects")
        return [x for x in value if isinstance(x, dict)]

    def index(self, rows: list[dict], path: str,
              expected: set[str] | None = None) -> dict[str, dict]:
        ids = [x.get("id") for x in rows]
        self.need(all(isinstance(x, str) and x for x in ids), path, "all IDs required")
        valid_ids = [x for x in ids if isinstance(x, str)]
        duplicates = sorted(k for k, n in Counter(valid_ids).items() if n != 1)
        self.need(not duplicates, path, f"duplicate IDs: {duplicates}")
        if expected is not None:
            self.need(set(valid_ids) == expected and len(rows) == len(expected), path,
                      f"exact coverage required; missing={sorted(expected-set(valid_ids))}; "
                      f"extra={sorted(set(valid_ids)-expected)}; count={len(rows)}")
        return {x["id"]: x for x in rows if isinstance(x.get("id"), str)}

    def strings(self, row: dict, fields: list[str], path: str) -> None:
        for field in fields:
            self.need(isinstance(row.get(field), str) and bool(row[field].strip()),
                      f"{path}/{field}", "nonempty string required")


def validate_catalogs(audit: Audit, files: dict[str, dict]) -> dict[str, dict]:
    core, catalog = files[CORE_FILE], files["content/encounters_v05.json"]
    cards = audit.index(audit.rows(catalog, "encounters", "encounters"), "encounters", MONSTERS)
    rules = audit.index(audit.rows(files["content/rules.json"], "rules", "rules"), "rules", RULES)
    events = audit.index(audit.rows(files["content/events.json"], "events", "events"), "events", EVENTS)
    contracts = audit.index(audit.rows(core, "encounter_contracts", CORE_FILE),
                            "encounter_contracts", MONSTERS)
    conditions = audit.index(audit.rows(core, "condition_definitions", CORE_FILE), "condition_definitions")
    supplies = audit.index(audit.rows(core, "supply_catalog", CORE_FILE), "supply_catalog")
    scenes = audit.index(audit.rows(files["content/maps.json"], "scenes", "maps"), "maps/scenes")
    overlay = files["content/map_mechanics_v05.json"]
    roles_by_scene = {sid: {x.get("role") for x in s.get("anchors", [])}
                      for sid, s in scenes.items()}
    store_roles = roles_by_scene.get("MAP_STORE", set())
    overlay_refs = {
        "object_ids": {x["id"] for x in overlay.get("objects", [])},
        "spatial_group_ids": {x["id"] for x in overlay.get("spatial_groups", [])},
        "wet_region_ids": {x["id"] for x in overlay.get("wet_regions", [])},
        "defense_group_ids": {x["id"] for x in overlay.get("defense_groups", [])},
    }
    entries = {x["id"] for x in overlay.get("entry_profiles", [])}
    audit.equal(core, "client_implemented", False, CORE_FILE)
    audit.equal(core.get("authority", {}), "encounter_cards", "content/encounters_v05.json", "authority")
    audit.equal(core.get("authority", {}), "canonical_f12_f13", BLUEPRINT_FILE, "authority")
    audit.equal(core.get("authority", {}), "never_execute_prose_guards", True, "authority")
    audit.equal(core.get("authority", {}), "all_runtime_candidates_remain_disabled_until_client_adapter_exists", True, "authority")
    audit.need({"FRESH_BLOOD", "MINOR_INJURY", "BLOOD_TRACE", "WORK_RECEIPT", "TRUE_SIX"}
               <= set(conditions), "condition_definitions", "core conditions missing")
    for cid, condition in conditions.items():
        audit.strings(condition, ["scope", "producer_kind", "lifetime_end"], f"condition/{cid}")
        audit.equal(condition, "server_truth_not_auto_revealed_to_player", True, f"condition/{cid}")
    for sid, supply in supplies.items():
        path = f"supply/{sid}"
        audit.need(supply.get("type") in SUPPLY_TYPES, path, "unknown supply type")
        audit.need(supply.get("anchor") in store_roles, path, "missing store anchor")
        audit.need(number(supply.get("quantity")) and supply["quantity"] > 0, path, "positive quantity required")
        audit.need(string_list(supply.get("used_by")) and set(supply["used_by"]) <= MONSTERS,
                   path, "invalid encounter usage reference")
        audit.equal(supply, "cannot_replace_canonical_quest_item", True, path)
    for fid, card in cards.items():
        path = f"encounter/{fid}"
        audit.equal(card, "runtime_enabled", False, path)
        binding = card.get("map_binding", {})
        scene = binding.get("scene")
        audit.need(scene in scenes, path + "/map_binding", "unknown scene")
        audit.need(binding.get("entry_profile") in entries, path + "/map_binding", "unknown entry profile")
        audit.need(string_list(binding.get("base_anchors"), True)
                   and set(binding["base_anchors"]) <= roles_by_scene.get(scene, set()),
                   path + "/map_binding", "unknown or empty base anchor list")
        for field, valid in overlay_refs.items():
            audit.need(string_list(binding.get(field)) and set(binding[field]) <= valid,
                       path + "/map_binding/" + field, "unknown map mechanic reference")
        audit.need(string_list(card.get("allowed_phases"), True)
                   and set(card["allowed_phases"]) <= NIGHT_PHASES, path, "invalid phases")
    if "F14" in cards:
        audit.equal(cards["F14"], "candidate_enabled", False, "encounter/F14")
    for fid, contract in contracts.items():
        path = f"contract/{fid}"
        audit.strings(contract, ["activation_mode", "on_player_prevented", "on_source_expired",
                               "on_refused", "normal_resolution", "recovery"], path)
        for field in ["requires_before_omen", "producer_steps", "source_kinds"]:
            audit.need(string_list(contract.get(field), True), f"{path}/{field}", "nonempty string array required")
        for field in ["supplies_required", "supplies_on_accept", "supplies_arrival_payload"]:
            values = contract.get(field)
            audit.need(string_list(values) and set(values) <= set(supplies),
                       f"{path}/{field}", "all supply IDs must resolve")
            if string_list(values):
                for sid in values:
                    if sid in supplies:
                        audit.need(fid in supplies[sid].get("used_by", []),
                                   f"{path}/{field}/{sid}", "supply usage index must include this encounter")
        audit.equal(contract, "on_missing_inputs", "do_not_admit_no_history_fabrication", path)
        audit.equal(contract, "witness_fact", f"PAYLOAD_{fid}", path)
        audit.equal(contract, "witness_file", GRAPH_FILE, path)
        audit.equal(contract, "actor_policy_file", CORE_FILE, path)
        audit.equal(contract, "client_implemented", False, path)
        timers = audit.rows(contract, "timers", path)
        audit.need(bool(timers), path + "/timers", "at least one explicit timer/deadline contract required")
        audit.index(timers, path + "/timers")
        for timer in timers:
            audit.need(timer.get("clock") in TIMER_CLOCKS, path + "/timers", "unknown timer clock")
            audit.need((number(timer.get("seconds")) and timer["seconds"] > 0)
                       or (isinstance(timer.get("deadline"), str) and bool(timer["deadline"].strip())),
                       path + "/timers", "positive seconds or declared deadline required")
    for hid, rule in rules.items():
        path = f"rule/{hid}"
        audit.equal(rule, "current_contract", CORE_FILE, path)
        contract = rule.get("v06_condition_contract", {})
        audit.strings(contract, ["producer_description", "applies_when", "unlock_milestone", "clear_or_expiry"], path)
        for flag in ["before_first_applicable_danger", "free_instruction", "does_not_require_first_failure_or_paid_study"]:
            audit.equal(contract, flag, True, path)
        audit.equal(contract, "client_implemented", False, path)
    for eid, event in events.items():
        path = f"event/{eid}"
        audit.equal(event, "current_contract", CORE_FILE, path)
        contract = event.get("v06_condition_contract", {})
        audit.strings(contract, ["producer_kind", "required_live_inputs", "producer_policy",
                               "on_player_prevented", "on_external_invalidation", "expiry_policy"], path)
        audit.need(contract.get("scheduled_by") in {"phase_budget_elapsed", "unified_game_clock"},
                   path, "event must use the declared schedule clock")
        audit.equal(contract, "continuous_effect_clock", "world_simulation", path)
        audit.equal(contract, "on_missing_inputs", "do_not_admit_no_history_fabrication", path)
        audit.need({"planning", "before_first_omen", "arrival", "committed_action"}
                   <= set(contract.get("recheck_at", [])), path, "missing source recheck boundary")
        for flag, value in [("handling_budget_is_not_effect_lifetime", True),
                            ("late_materialization_allowed", False),
                            ("same_receipt_settles_once", True), ("client_implemented", False)]:
            audit.equal(contract, flag, value, path)
    blueprints = audit.index(audit.rows(files[BLUEPRINT_FILE], "encounters", BLUEPRINT_FILE), BLUEPRINT_FILE)
    for fid, expected_digest in CANONICAL_DIGESTS.items():
        entry = blueprints.get(fid)
        encoded = json.dumps(entry, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        audit.need(hashlib.sha256(encoded).hexdigest() == expected_digest,
                   f"{BLUEPRINT_FILE}/{fid}", "canonical interaction blueprint changed; explicit review required")
        audit.equal(cards.get(fid, {}), "canonical_override", "fixed_F12_F13", f"encounter/{fid}")
        audit.equal(cards.get(fid, {}), "canonical_blueprint_file", BLUEPRINT_FILE, f"encounter/{fid}")
        audit.equal(contracts.get(fid, {}), "canonical_file", BLUEPRINT_FILE, f"contract/{fid}")
    return {"cards": cards, "rules": rules, "events": events, "contracts": contracts,
            "supplies": supplies, "conditions": conditions, "scenes": scenes}


def validate_world_contract(audit: Audit, files: dict[str, dict], indexes: dict) -> None:
    core = files[CORE_FILE]
    balance = files["content/balance.json"]
    clock = core.get("clock_contract", {})
    budget = balance.get("time_budget_semantics", {})
    audit.equal(clock, "schedule_clock", "shift_budget_clock", "clock")
    audit.need({"orders", "far_omens", "near_omens", "threshold_cues", "scheduled_arrivals",
                "phase_end", "manager_arrival", "true_06_00"}
               <= set(clock.get("scheduled_markers", [])), "clock", "scheduled boundary coverage")
    for flag in ["critical_resolution_budget_reserved_before_optional_precision",
                 "precision_cost_reserved_on_start_committed_once_on_finish_cancel_or_failure",
                 "precision_commit_never_replays_unseen_enemy_or_wound_movement",
                 "pause_advances_no_clock_or_regeneration", "daytime_elapsed_game_hours_settle_energy_satiety_once",
                 "phase_boundary_does_not_delete_world_conditions"]:
        audit.equal(clock, flag, True, "clock")
    for field, value in {"scheduler_clock": "phase_budget_elapsed", "world_effect_clock": "world_simulation",
                         "qte_cannot_cross_pending_scheduled_boundary": True,
                         "dispatch_due_schedule_before_qte_admission": True,
                         "paused_world_generates_stamina_recovery": False,
                         "wall_clock_advances_gameplay_while_paused": False,
                         "no_invisible_movement_or_damage_catchup": True,
                         "energy_and_satiety_use_game_clock_once": True}.items():
        audit.equal(budget, field, value, "balance/time_budget_semantics")
    audit.need(set(budget.get("phase_budget_advances_by", [])) ==
               {"active_world_delta", "committed_precision_attempt_cost_once"}, "clock", "budget must settle each source once")
    audit.equal(balance, "night_seconds_per_hour", 120, "balance")
    audit.equal(balance, "same_phases_every_day", True, "balance")
    audit.equal(balance, "week_length_days", 7, "balance")
    minutes: Counter[int] = Counter()
    phase_ids = set()
    for phase in balance.get("daily_phases", []):
        try:
            start = sum(int(x) * m for x, m in zip(phase["start"].split(":"), [60, 1]))
            end = sum(int(x) * m for x, m in zip(phase["end"].split(":"), [60, 1]))
            audit.need(0 <= start < end <= 1440, "balance/daily_phases", "invalid phase extent")
            minutes.update(range(start, end))
            phase_ids.add(phase["id"])
        except (KeyError, TypeError, ValueError):
            audit.need(False, "balance/daily_phases", "unreadable phase interval")
    audit.need(set(minutes) == set(range(1440)) and all(n == 1 for n in minutes.values()),
               "balance/daily_phases", "24-hour day must be covered once without gaps or overlap")
    audit.need(NIGHT_PHASES <= phase_ids, "balance/daily_phases", "six night phases required")
    resources = balance.get("resources", {})
    audit.need(set(resources) == {"energy", "san", "satiety", "stamina"}, "balance/resources", "exactly four resources")
    audit.equal(resources.get("stamina", {}), "recovery_clock", "world_simulation", "stamina")
    audit.equal(resources.get("satiety", {}), "zero_satiety_additional_energy_drain", 0, "satiety")
    audit.equal(resources.get("energy", {}), "separate_sleep_debt_state_enabled", False, "energy")
    panic, san = core.get("panic_stabilization", {}), resources.get("san", {})
    for field, value in {"portable": True, "panic_window_world_seconds": 20,
                         "stabilization_world_seconds": 8, "free_uses_per_night": 1,
                         "san_on_success": 15, "walking_allowed": True,
                         "sprint_or_parallel_work_allowed": False,
                         "hit_or_other_work_interrupts_without_resetting_progress": True,
                         "world_and_enemy_time_continue": True, "pause_generates_no_progress": True,
                         "first_zero_starts_one_deadline_repeated_zero_does_not_refresh": True,
                         "not_a_physical_damage_shield": True}.items():
        audit.equal(panic, field, value, "panic_stabilization")
    for field, value in {"panic_window_seconds": 20, "emergency_stabilization_seconds": 8,
                         "emergency_stabilization_requires_fixed_safe_zone": False,
                         "portable_stabilization_allowed_while_walking": True,
                         "panic_timer_restarts_on_repeat_zero": False,
                         "emergency_stabilization_consumes_on_success": True,
                         "hidden_correct_input_failure_probability": 0}.items():
        audit.equal(san, field, value, "balance/san")
    wounds = core.get("wounds", {})
    for field, value in {"bleeding_duration_world_seconds": 90, "minor_injury_duration_world_seconds": 30,
                         "minor_injury_is_hp_bar": False, "minor_injury_implies_bleeding": False,
                         "minor_injury_changes_walk_speed_or_core_f12_f13_actions": False,
                         "incident_receipt_required": True, "repeated_same_incident_refreshes_deadline": False}.items():
        audit.equal(wounds, field, value, "wounds")
    audit.need(set(wounds.get("allowed_bleeding_actor_ids", [])) == {"PLAYER", "COWORKER"},
               "wounds", "only the two real employees produce employee blood")
    producers = audit.index(audit.rows(wounds, "producers", "wounds"), "wounds/producers",
                             {"GLASS_RETURN_CONTACT", "F21_GLASS_FAULT"})
    for pid, producer in producers.items():
        audit.need(bool(producer.get("phase_options")) and set(producer["phase_options"]) <= NIGHT_PHASES,
                   f"wounds/{pid}", "producer needs actual phase options")
        audit.strings(producer, ["setup", "cut_requires", "prevention"], f"wounds/{pid}")
        audit.equal(producer, "max_cuts_per_incident", 1, f"wounds/{pid}")
    audit.equal(producers.get("GLASS_RETURN_CONTACT", {}), "event_id", "E003", "wounds/GLASS_RETURN_CONTACT")
    audit.equal(producers.get("GLASS_RETURN_CONTACT", {}), "warning_world_seconds", 3, "wounds/GLASS_RETURN_CONTACT")
    audit.equal(producers.get("F21_GLASS_FAULT", {}), "encounter_id", "F21", "wounds/F21_GLASS_FAULT")
    audit.equal(producers.get("F21_GLASS_FAULT", {}), "warning_world_seconds", 40, "wounds/F21_GLASS_FAULT")
    reactive = wounds.get("reactive_consumers", {})
    audit.need(set(reactive.get("ids", [])) == {"F26", "F32"}, "wounds/reactive", "blood consumers must be explicit")
    for field, value in {"one_consumer_per_incident": True, "may_force_wound_to_fill_slot": False,
                         "announcement_lead_world_seconds": 12,
                         "minimum_remaining_shift_budget_seconds": 45,
                         "minimum_remaining_current_phase_budget_seconds": 45,
                         "minimum_remaining_fresh_blood_world_seconds_at_announcement": 45,
                         "max_base_response_action_and_travel_seconds": 24,
                         "recovery_budget_seconds": 6, "exit_feedback_budget_seconds": 3}.items():
        audit.equal(reactive, field, value, "wounds/reactive")
    demand = sum(reactive.get(k, 0) for k in ["announcement_lead_world_seconds",
                 "max_base_response_action_and_travel_seconds", "recovery_budget_seconds", "exit_feedback_budget_seconds"]
                 if number(reactive.get(k, 0)))
    for field in ["minimum_remaining_shift_budget_seconds", "minimum_remaining_current_phase_budget_seconds",
                  "minimum_remaining_fresh_blood_world_seconds_at_announcement"]:
        audit.need(number(reactive.get(field)) and reactive[field] >= demand,
                   f"wounds/reactive/{field}", "declared 12+24+6+3 response reserve must fit; this is not a route proof")
    traces = wounds.get("blood_trace", {})
    audit.equal(traces, "created_only_by_actual_movement_while_fresh", True, "blood_trace")
    audit.equal(traces, "lifetime_world_seconds", 30, "blood_trace")
    audit.equal(traces, "dressed_actor_does_not_remove_existing_marks", True, "blood_trace")
    audit.equal(traces, "dried_marks_cannot_emit_new_fresh_blood", True, "blood_trace")
    first_aid = wounds.get("first_aid", {})
    audit.need(first_aid.get("supply_id") in indexes["supplies"], "wounds/first_aid", "free dressing supply must exist")
    audit.equal(first_aid, "requires_qte", False, "wounds/first_aid")
    audit.equal(first_aid, "world_action_seconds", 3, "wounds/first_aid")
    audit.equal(first_aid, "allows_self_treatment", True, "wounds/first_aid")
    boundary = wounds.get("f32_invitation", {})
    objects = {x["id"]: x for x in files["content/map_mechanics_v05.json"].get("objects", [])}
    boundary_object = objects.get(boundary.get("employee_boundary_id"), {})
    audit.equal(boundary, "employee_boundary_required_state", "marked", "F32/boundary")
    audit.need(boundary.get("employee_boundary_required_state") in boundary_object.get("states", []),
               "F32/boundary", "required boundary state must exist on the named map object")
    audit.equal(boundary, "greeting_enabled_is_not_already_invited", True, "F32/invitation")
    lifecycle = core.get("lifecycle", {})
    audit.need(set(lifecycle.get("terminal_states", [])) <= set(lifecycle.get("states", [])),
               "lifecycle", "terminal states must be declared")
    for field, value in {"post_announcement_slot_refill": False, "terminal_states_absorbing": True,
                         "completion_receipt_idempotent": True, "root_episode_reward_max": 1,
                         "failure_derived_blood_encounters_grant_no_farmable_bonus": True}.items():
        audit.equal(lifecycle, field, value, "lifecycle")
    actors = core.get("actors", {})
    audit.need(set(actors.get("real_staff_ids", [])) == {"PLAYER", "COWORKER"}, "actors", "two regular employees only")
    audit.equal(actors, "manager_id", "MANAGER", "actors")
    audit.equal(actors, "manager_is_not_third_regular_employee", True, "actors")
    for flag in ["one_live_task_per_actor", "injured_actor_stays_same_instance",
                 "free_critical_actions_do_not_require_assistant", "disguises_copy_appearance_not_true_id_or_authority"]:
        audit.equal(actors, flag, True, "actors")
    end = core.get("end_of_shift", {})
    audit.equal(end, "true_six_budget_seconds", 720, "end_of_shift")
    audit.equal(end, "manager_arrival_budget_seconds", 700, "end_of_shift")
    audit.equal(end, "arrival_is_not_identity_proof", True, "end_of_shift")
    audit.equal(end, "entry_requires_no_active_hostile", True, "end_of_shift")
    order = end.get("order", [])
    sequence = ["commit_already_completed_valid_actions", "settle_contracts_due_at_true_06_00",
                "evaluate_unresolved_critical_threat", "close_service_and_enter_handover_only",
                "verify_manager_and_transfer_receipts_and_keys", "settle_wage_and_unique_rewards"]
    audit.need(all(x in order for x in sequence) and
               [order.index(x) for x in sequence if x in order] == sorted(order.index(x) for x in sequence if x in order),
               "end_of_shift/order", "success/contract settlement must precede threat check, handover, and pay")
    audit.need({"new_orders", "finish_old_duties_for_bonus", "new_monsters", "resource_regeneration", "free_extra_chase_time"}
               <= set(end.get("handover_only_forbids", [])), "end_of_shift", "handover cannot create extra gameplay time")
    audit.need("predeclared_counter_identity_action_generates_only_its_scoped_observation" in end.get("handover_only_allows", []),
               "end_of_shift", "handover needs its limited actual observation action")
    night = balance.get("night_completion", {})
    for field, value in {"planned_base_orders_per_hour": 2, "planned_base_orders_per_night": 12,
                         "minimum_valid_transactions": 0, "ordinary_work_not_safety_gate": True,
                         "handover_actor": "existing_real_manager", "handover_actor_arrival_phase": "N06",
                         "handover_actor_arrival_phase_budget_second": 100,
                         "creates_extra_permanent_employee": False}.items():
        audit.equal(night, field, value, "balance/night_completion")
    stock = core.get("stock_and_instances", {})
    for flag in ["reusable_tools_also_require_nonoverlapping_actor_time_reservations",
                 "release_does_not_teleport_physical_item", "optional_supply_required_only_after_acceptance"]:
        audit.equal(stock, flag, True, "stock_and_instances")
    audit.equal(stock, "future_reservation_may_steal_current_tool", False, "stock_and_instances")
    evidence = core.get("evidence", {})
    for field, value in {"live_presence_snapshot_world_ttl_seconds": 8,
                         "historical_photo_expires_as_history": False,
                         "two_evidence_threshold_grants_identity_automatically": False,
                         "current_identity_requires_bound_continuity_or_current_species_test": True,
                         "schedule_is_presence_proof": False, "claimed_past_event_can_create_receipt": False}.items():
        audit.equal(evidence, field, value, "evidence")
    e001 = indexes["events"].get("E001", {}).get("v06_order_transform", {})
    audit.equal(e001, "maximum_orders", 2, "E001/order_transform")
    audit.equal(e001, "creates_extra_order", False, "E001/order_transform")
    audit.equal(e001, "patience_restarts", False, "E001/order_transform")
    pet = indexes["events"].get("E070", {}).get("v06_charge_policy", {})
    for field, value in {"parent_event": "E014", "independent_random_sampling": False,
                         "restore_active_charges": 0, "bypass_missed_care": False,
                         "duration_world_seconds": 30, "comfort_world_seconds": 6,
                         "max_episodes_per_night": 1, "repeated_pulse_refreshes": False,
                         "committed_effects_continue": True, "only_new_active_commands_blocked": True}.items():
        audit.equal(pet, field, value, "E070/charge_policy")


class SourceGraph:
    """A finite, single-instance STRIPS-style search with actual delete effects."""

    def __init__(self, operators: list[dict]) -> None:
        self.operators = {op["id"]: op for op in operators}

    def search(self, seed: list[str], goals: set[str], removed: set[str] | None = None,
               limit: int = 200_000) -> dict:
        removed = removed or set()
        available = {k: v for k, v in self.operators.items() if k not in removed}
        producers: dict[str, list[dict]] = defaultdict(list)
        for op in available.values():
            for fact in op["produces"]:
                producers[fact].append(op)
        # Backward relevance is only a pruning operation, never the proof.
        pending = list(goals)
        needed_facts = set(goals)
        relevant: set[str] = set()
        while pending:
            fact = pending.pop()
            for op in producers[fact]:
                relevant.add(op["id"])
                for requirement in op["requires"]:
                    if requirement not in needed_facts:
                        needed_facts.add(requirement)
                        pending.append(requirement)
        ops = [available[k] for k in sorted(relevant)]
        prepared = [(frozenset(op["requires"]), frozenset(op["produces"]),
                     frozenset(op.get("invalidates", []))) for op in ops]
        start = (frozenset(seed), 0)
        queue = deque([start])
        parent: dict[tuple, tuple | None] = {start: None}
        found = None
        while queue:
            state = queue.popleft()
            facts, used = state
            if goals <= facts:
                found = state
                break
            for index, (requires, produces, invalidates) in enumerate(prepared):
                bit = 1 << index
                if used & bit or not requires <= facts:
                    continue
                new_facts = (facts - invalidates) | produces
                if new_facts == facts:
                    continue
                new_state = (new_facts, used | bit)
                if new_state in parent:
                    continue
                if len(parent) >= limit:
                    return {"status": "SEARCH_LIMIT", "states_examined": len(parent),
                            "relevant_operators": len(ops), "limit": limit,
                            "reason": "search limit is inconclusive, never evidence of unreachability"}
                parent[new_state] = (state, index)
                queue.append(new_state)
        base = {"states_examined": len(parent), "relevant_operators": len(ops),
                "removed_producers": sorted(removed)}
        if found is None:
            return {**base, "status": "UNREACHABLE", "search_exhausted": True,
                    "goal_facts": sorted(goals)}
        sequence = []
        cursor = found
        while parent[cursor] is not None:
            previous, index = parent[cursor]
            sequence.append(ops[index])
            cursor = previous
        sequence.reverse()
        # Independently replay the path; proof output never relies on union closure.
        facts = set(seed)
        steps = []
        replayed = set()
        for op in sequence:
            if op["id"] in replayed or not set(op["requires"]) <= facts:
                raise AssertionError("BFS witness failed independent precondition replay")
            deleted = facts & set(op.get("invalidates", []))
            facts.difference_update(op.get("invalidates", []))
            added = set(op["produces"]) - facts
            facts.update(op["produces"])
            step = {"operator": op["id"], "kind": op["kind"], "label": op["label"],
                    "requires": op["requires"], "added": sorted(added), "removed": sorted(deleted)}
            for field in ["earliest_phase", "order_instance", "entity_owner"]:
                if field in op:
                    step[field] = op[field]
            steps.append(step)
            replayed.add(op["id"])
        if not goals <= facts:
            raise AssertionError("BFS witness failed independent goal replay")
        return {**base, "status": "REACHABLE", "goal_facts": sorted(goals),
                "steps": steps, "final_facts": sorted(facts), "replay_valid": True}


def validate_graph(audit: Audit, data: dict, indexes: dict) -> dict:
    audit.equal(data, "initial_facts", ["NEW_SHIFT"], "source_graph")
    op_rows = audit.rows(data, "operators", "source_graph")
    ops = audit.index(op_rows, "source_graph/operators")
    cases = audit.index(audit.rows(data, "encounters", "source_graph"), "source_graph/encounters", MONSTERS)
    usable = []
    for oid, op in ops.items():
        path = f"source_graph/{oid}"
        valid_arrays = string_list(op.get("requires")) and string_list(op.get("produces"), True) and string_list(op.get("invalidates", []))
        audit.need(valid_arrays, path, "requires/produces/invalidates must be fact-name arrays")
        audit.strings(op, ["kind", "label"], path)
        valid = valid_arrays and all(isinstance(op.get(k), str) and op[k].strip() for k in ["kind", "label"])
        if not valid:
            continue
        audit.need(not set(op["produces"]) & set(op.get("invalidates", [])), path, "cannot produce and invalidate the same fact")
        if "earliest_phase" in op:
            audit.need(op["earliest_phase"] in PHASE_INDEX, path, "unknown explicit source phase")
        if "entity_owner" in op:
            audit.need(op["entity_owner"] in MONSTERS, path, "unknown bound entity")
        usable.append(op)
    produced = {f for op in usable for f in op["produces"]}
    known_facts = produced | {"NEW_SHIFT"}
    for op in usable:
        audit.need(set(op["requires"]) <= known_facts, f"source_graph/{op['id']}", "orphan prerequisite without any declared source")
    audit.need({op["id"] for op in usable if "FRESH_BLOOD" in op["produces"]}
               == {"P_REAL_CUT", "P_F21_REAL_CUT"}, "source_graph/FRESH_BLOOD", "blood may only come from the two real failure producers")
    for oid in ["P_REAL_CUT", "P_F21_REAL_CUT"]:
        audit.equal(ops.get(oid, {}), "kind", "real_failure_receipt", f"source_graph/{oid}")
    audit.need({"PAYLOAD_F21", "F21_GLASS_VARIANT"} <= set(ops.get("P_F21_REAL_CUT", {}).get("requires", [])),
               "source_graph/P_F21_REAL_CUT", "F21-specific accident requires the actual F21 instance and glass subtype, not any occupied faulty device")
    audit.need("PAYLOAD_F21" in ops.get("P_F21_GLASS_VARIANT", {}).get("requires", []),
               "source_graph/P_F21_GLASS_VARIANT", "glass subtype must belong to the actually active F21")
    audit.need("HOT_FOOD_SALEABLE" in ops.get("P_HOT_WASTE", {}).get("invalidates", []),
               "source_graph/P_HOT_WASTE", "same food batch must lose saleable state on disposal")
    sale_ops = [ops.get(x, {}) for x in ["P_CHECKOUT", "P_CHECKOUT_2", "P_CHECKOUT_3"]]
    order_ids = [x.get("order_instance") for x in sale_ops]
    audit.need(all(order_ids) and len(set(order_ids)) == 3, "source_graph/P_THREE_SALES", "three real distinct order IDs required")
    audit.need(set(ops.get("P_THREE_SALES", {}).get("requires", [])) ==
               {"SALE_RECEIPT_1", "SALE_RECEIPT_2", "SALE_RECEIPT_3"},
               "source_graph/P_THREE_SALES", "one receipt must not be renamed as three receipts")
    audit.equal(ops.get("P_THREE_SALES", {}), "unique_order_receipt_count", 3, "source_graph/P_THREE_SALES")
    current_order = ops.get("P_F51_CURRENT_ORDER", {})
    audit.need(bool(current_order.get("order_instance")) and current_order["order_instance"] not in order_ids,
               "source_graph/P_F51_CURRENT_ORDER", "current order cannot be a previously sold order")
    audit.equal(current_order, "earliest_phase", "N05", "source_graph/P_F51_CURRENT_ORDER")
    for i in [1, 2, 3]:
        audit.equal(ops.get(f"P_WORK_TRACE_{i}", {}), "distinct_station_index", i, f"source_graph/P_WORK_TRACE_{i}")
    audit.need(set(ops.get("P_THREE_WORK_TRACES", {}).get("requires", [])) ==
               {"WORK_TRACE_1", "WORK_TRACE_2", "WORK_TRACE_3"},
               "source_graph/P_THREE_WORK_TRACES", "continuity requires three independent actual station traces")
    audit.equal(ops.get("P_RECEIVE_THREE_MANIFEST", {}), "distinct_item_instances", 3, "source_graph/P_RECEIVE_THREE_MANIFEST")
    audit.need({"PRE_SHIFT_WORK_TRACE", "BASELINE"} <= set(ops.get("P_CLAIM_WINDOW_EVIDENCE", {}).get("requires", [])),
               "source_graph/P_CLAIM_WINDOW_EVIDENCE", "historical claim window needs an actual prior observation source")
    graph = SourceGraph(usable)
    witnesses = []
    phase_checks = []
    for fid, case in sorted(cases.items()):
        path = f"source_case/{fid}"
        audit.equal(case, "scenario_seed", ["NEW_SHIFT"], path)
        audit.equal(case, "activation_fact", f"PAYLOAD_{fid}", path)
        audit.equal(case, "arrival_producer", f"P_ARRIVE_{fid}", path)
        audit.equal(case, "source_may_be_created_by_claim_only", False, path)
        audit.equal(case, "first_applicable_rule_free_before_danger", True, path)
        audit.equal(case, "production_trace_is_abstract_not_engine_playthrough", True, path)
        audit.equal(case, "condition_model_goal", "source_dependency_witness_only", path)
        audit.need(string_list(case.get("required_before_arrival"), True), path, "actual prerequisite list required")
        allowed = case.get("allowed_phases", [])
        audit.need(bool(allowed) and set(allowed) <= NIGHT_PHASES, path, "valid phase windows required")
        audit.need(set(allowed) == set(indexes["cards"].get(fid, {}).get("allowed_phases", [])),
                   path, "source-case phase window differs from current encounter card")
        arrival = ops.get(case.get("arrival_producer"), {})
        requirements = case.get("required_before_arrival", [])
        audit.need({"BASIC_RULES", "SAFE_ROUTE", *requirements} <= set(arrival.get("requires", [])),
                   path, "arrival must require actual sources plus instruction/route admission")
        audit.need(arrival.get("produces") == [f"PAYLOAD_{fid}"], path, "arrival may not fabricate history, blood, or generic shared sources")
        audit.equal(arrival, "creates_new_real_staff", False, path)
        for requirement in requirements:
            if requirement.startswith(("OFFER_F", "CLAIM_F")):
                offer = ops.get(f"P_OFFER_{fid}", {})
                seen = ops.get(f"P_SEE_{fid}", {})
                audit.equal(offer, "entity_owner", fid, path + "/offer")
                audit.equal(seen, "entity_owner", fid, path + "/visible_body")
                audit.equal(arrival, "entity_owner", fid, path + "/arrival")
                audit.need(offer.get("produces") == [requirement] and f"VISITOR_{fid}" in offer.get("requires", []),
                           path, "proposal must come from this visible entity instance")
        window = case.get("historical_window", {})
        earliest = window.get("earliest_possible_source_phase")
        audit.need(earliest in PHASE_INDEX, path + "/historical_window", "explicit earliest source phase required")
        if earliest in PHASE_INDEX and allowed and all(p in PHASE_INDEX for p in allowed):
            possible = [p for p in allowed if PHASE_INDEX[p] >= PHASE_INDEX[earliest]]
            audit.need(len(possible) == len(allowed), path + "/historical_window", "an allowed phase precedes the explicitly known earliest source")
            phase_checks.append({"id": fid, "earliest_declared_source_phase": earliest,
                                 "allowed_phases": allowed,
                                 "scope": "ordinal metadata only; within-phase omen/action/deadline feasibility not proved"})
        if fid in {"F26", "F32"}:
            audit.equal(case, "real_failure_required", True, path)
            audit.need("FRESH_BLOOD" in requirements, path, "real employee fresh blood must gate announcement")
        if fid == "F26":
            audit.need("BLOOD_TRACE" in requirements, path, "F26 also needs an actual trace")
        if fid == "F51":
            audit.equal(case, "allowed_phases", ["N05"], path)
            audit.equal(window, "earliest_possible_source_phase", "N02", path + "/historical_window")
        if fid == "F38":
            audit.equal(window, "earliest_possible_source_phase", "N03", path + "/historical_window")
        if fid in {"F25", "F43"}:
            audit.equal(window, "earliest_possible_source_phase", "D04", path + "/historical_window")
        result = graph.search(case.get("scenario_seed", []), {case.get("activation_fact", "MISSING_GOAL")})
        audit.need(result["status"] == "REACHABLE", path, f"no source witness: {result['status']}")
        if result["status"] == "REACHABLE":
            other_arrivals = {s["operator"] for s in result["steps"]
                              if s["operator"].startswith("P_ARRIVE_")} - {f"P_ARRIVE_{fid}"}
            audit.need(not other_arrivals or (fid in {"F26", "F32"} and other_arrivals <= {"P_ARRIVE_F21"}),
                       path, "witness accidentally depends on unrelated monster instances")
        witnesses.append({"id": fid, "scenario_seed": case.get("scenario_seed", []),
                          "proof_kind": "source_dependency_only", **result})
    declared_negatives = data.get("source_counterexamples", [])
    declared_pairs = {(frozenset(x.get("remove_producers", [])), frozenset(x.get("unreachable", [])))
                      for x in declared_negatives if isinstance(x, dict)}
    for removed, expected in REQUIRED_NEGATIVES:
        audit.need((frozenset(removed), frozenset(expected)) in declared_pairs,
                   "source_counterexamples", f"mandatory negative case removed: {sorted(removed)} -> {sorted(expected)}")
    negatives = []
    for removed, expected in REQUIRED_NEGATIVES:
        audit.need(removed <= set(ops), "source_counterexamples", f"unknown removed producer: {sorted(removed-set(ops))}")
        outcomes = []
        for fid in sorted(expected):
            case = cases.get(fid, {})
            result = graph.search(case.get("scenario_seed", []), {case.get("activation_fact", "MISSING_GOAL")}, removed)
            audit.need(result["status"] == "UNREACHABLE" and result.get("search_exhausted") is True,
                       f"negative/{fid}", f"removing {sorted(removed)} must make source chain unreachable, got {result['status']}")
            outcomes.append({"id": fid, **result})
        negatives.append({"remove_producers": sorted(removed), "expected_unreachable": sorted(expected), "results": outcomes})
    food = graph.search(["NEW_SHIFT"], {"HOT_FOOD_SALEABLE", "HOT_WASTE"})
    audit.need(food["status"] == "UNREACHABLE" and food.get("search_exhausted") is True,
               "nonmonotonic/same_food_batch", "same declared food instance cannot be simultaneously saleable and discarded")
    return {"operator_count": len(ops), "case_count": len(cases), "witnesses": witnesses,
            "negative_source_tests": negatives,
            "nonmonotonic_tests": [{"name": "same_food_instance_not_both_saleable_and_waste", **food}],
            "explicit_phase_metadata_checks": phase_checks}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compact", action="store_true", help="emit compact JSON, preserving all witnesses")
    args = parser.parse_args()
    audit = Audit()
    names = [CORE_FILE, GRAPH_FILE, BLUEPRINT_FILE, "content/encounters_v05.json",
             "content/rules.json", "content/events.json", "content/balance.json",
             "content/maps.json", "content/map_mechanics_v05.json"]
    files = {name: audit.read(name) for name in names}
    indexes = validate_catalogs(audit, files)
    validate_world_contract(audit, files, indexes)
    graph_report = validate_graph(audit, files[GRAPH_FILE], indexes)
    report = {
        "status": "FAIL" if audit.errors else "PASS",
        "checks": audit.checks,
        "scope": "core schema, explicit design invariants, references, and independent finite source-dependency witnesses",
        "proof_level": "source_dependency_witness_only_not_temporal_or_ai_playthrough",
        "client_implemented": False,
        "interpretation": [
            "Each of the 60 witnesses starts independently from NEW_SHIFT; they are not one playable night.",
            "Operators represent declared concrete action/instance sources. A witness is only as truthful as those authored source contracts.",
            "Facts invalidated by an action are removed before its products are added; the witness is replayed from its seed.",
            "Each named operator is used at most once per witness. A second item/order/batch requires its own named instance operator.",
            "Historical phase checks compare only explicit known metadata; they do not simulate elapsed time, observation continuity, or omen scheduling.",
            "SAFE_ROUTE and SUPPLIES are abstract admission claims. This report does not prove collision/navigation, shared inventory quantities, deadlines, all event combinations, complete AI, guaranteed success, or fun.",
            "SEARCH_LIMIT is inconclusive and fails validation; only an exhausted finite search is reported as UNREACHABLE.",
            "F14 is included for design-source coverage while remaining disabled as a runtime candidate.",
        ],
        "counts": {"cards": len(indexes["cards"]), "rules": len(indexes["rules"]),
                   "events": len(indexes["events"]), "encounter_contracts": len(indexes["contracts"]),
                   "supplies": len(indexes["supplies"]), "condition_definitions": len(indexes["conditions"]),
                   "witnesses_reachable": sum(w["status"] == "REACHABLE" for w in graph_report["witnesses"])},
        "inputs_sha256": audit.hashes,
        **graph_report,
        "errors": audit.errors,
    }
    print(json.dumps(report, ensure_ascii=False, indent=None if args.compact else 2))
    return int(bool(audit.errors))


if __name__ == "__main__":
    raise SystemExit(main())
