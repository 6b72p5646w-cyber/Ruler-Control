"""Bounded SA02 facility transaction reference, deliberately not a world adapter.

Simulated consumer/geometry facts are explicit inputs. Production candidates stay
disabled; this class never authenticates a receipt, path, emitter or real scan.
"""
from __future__ import annotations

from copy import deepcopy
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_contract():
    return json.loads((ROOT / "content/facility_contracts_sa02.json").read_text())


class FacilityReference:
    def __init__(self, *, simulated_design=False, reserve=12, contract=None):
        self.contract = deepcopy(contract or load_contract())
        self.simulated_design = simulated_design
        self.state = {
            "now": 0.0, "reserve": reserve, "activations": {}, "scans": {},
            "used_ids": [], "paid_work_actions": [], "consumed_work_receipts": [],
            "next_use": {}, "effects": [], "journal": [], "ended_at": None,
        }

    def snapshot(self):
        return deepcopy(self.state)

    @classmethod
    def restore(cls, state, *, simulated_design=False):
        model = cls(simulated_design=simulated_design)
        model.state = deepcopy(state)
        return model

    def _result(self, ok, reason, **extra):
        return {"ok": ok, "reason": reason, **extra}

    def advance(self, now):
        if not isinstance(now, (int, float)) or not math.isfinite(now) or now < self.state["now"]:
            raise ValueError("non_monotonic_or_nonfinite_time")
        self.state["now"] = now
        for activation in self.state["activations"].values():
            if activation["state"] in {"active", "suspended"} and now > activation["expires_at"]:
                activation["state"] = "expired"
        return self

    def finish_tick(self, now):
        """Run after actual action commits at this timestamp, including equality."""
        self.advance(now)
        for activation in self.state["activations"].values():
            if activation["state"] in {"active", "suspended"} and now >= activation["expires_at"]:
                activation["state"] = "expired"

    def available_reserve(self):
        return self.state["reserve"] - sum(s["state"] == "reserved" for s in self.state["scans"].values())

    def _valid_binding(self, binding):
        return isinstance(binding, dict) and all(
            isinstance(binding.get(field), str) and bool(binding[field].strip())
            for field in self.contract["identity_fields"])

    def _action_key(self, binding):
        return tuple(binding[field] for field in self.contract["identity_fields"])

    def _receipt_key(self, binding, receipt_id):
        return tuple(binding[field] for field in ("campaign_id", "week_id", "logical_night_id", "attempt_id")) + (receipt_id,)

    def _preflight(self, activation_id, binding, facts):
        if not self.simulated_design:
            return "candidate_disabled"
        if self.state["ended_at"] is not None:
            return "night_ended"
        if not isinstance(activation_id, str) or not activation_id.strip():
            return "missing_activation_id"
        if activation_id in self.state["used_ids"]:
            return "activation_id_used"
        if not self._valid_binding(binding):
            return "missing_identity"
        if any(s["state"] == "reserved" and self._action_key(s["binding"]) == self._action_key(binding)
               for s in self.state["scans"].values()):
            return "action_already_reserved"
        if any(s["state"] == "reserved" and s["binding"]["facility_instance_id"] == binding["facility_instance_id"]
               for s in self.state["scans"].values()):
            return "same_facility_scan_pending"
        for key, reason in [
            ("phase_open", "wrong_phase"), ("same_current_attempt", "wrong_attempt"),
            ("actor_action_legal", "action_unavailable"), ("consumer_bound", "consumer_unbound"),
            ("facility_geometry_bound", "facility_geometry_unproven"),
            ("source_available", "source_unavailable"), ("actual_object_valid", "wrong_object"),
        ]:
            if facts.get(key) is not True:
                return reason
        if self.state["now"] < self.state["next_use"].get(binding["facility_instance_id"], 0):
            return "cooldown"
        if self.available_reserve() < 1:
            return "insufficient_unreserved_power"
        return None

    def arm_work(self, facility_id, activation_id, binding, now, facts, *, base_duration=None,
                 other_work_multiplier=1.0):
        self.advance(now)
        spec = self.contract["work_candidates"].get(facility_id)
        if spec is None:
            return self._result(False, "unknown_work_candidate")
        reason = self._preflight(activation_id, binding, facts)
        if reason:
            return self._result(False, reason)
        if facts.get("source_event") != spec["source_event"]:
            return self._result(False, "wrong_action_source")
        if facts.get("work_complete") is not False or facts.get("action_already_started") is not False:
            return self._result(False, "not_new_bound_action")
        if list(self._action_key(binding)) in self.state["paid_work_actions"]:
            return self._result(False, "bound_action_already_paid")
        if spec["requires_main_C2_power"] and facts.get("main_C2_powered") is not True:
            return self._result(False, "main_power_unavailable")
        duration = None
        multiplier = spec["ordinary_speed_multiplier"]
        if multiplier is not None:
            if base_duration not in {1.5, 3.5}:
                return self._result(False, "not_original_checkout_duration")
            if not isinstance(other_work_multiplier, (int, float)) or not math.isfinite(other_work_multiplier) or other_work_multiplier <= 0:
                return self._result(False, "invalid_work_modifier")
            multiplier = max(spec["speed_floor"], min(multiplier, other_work_multiplier))
            duration = base_duration * multiplier
        # Successful start and payment are one bounded transaction.
        self.state["reserve"] -= 1
        self.state["used_ids"].append(activation_id)
        self.state["paid_work_actions"].append(list(self._action_key(binding)))
        self.state["next_use"][binding["facility_instance_id"]] = now + 30
        self.state["activations"][activation_id] = {
            "facility_id": facility_id, "binding": deepcopy(binding), "armed_at": now,
            "expires_at": now + 20, "state": "active", "receipt_id": None,
            "speed_multiplier": multiplier, "speed_snapshot_action_id": binding["action_id"] if multiplier is not None else None,
            "effective_duration": duration,
            "earliest_complete_at": now + duration if duration is not None else None,
        }
        return self._result(True, "armed", effective_duration=duration, speed_multiplier=multiplier)

    def interrupt_work(self, activation_id, now, *, original_producer_preserves_action=False):
        self.advance(now)
        activation = self.state["activations"].get(activation_id)
        if not activation or activation["state"] != "active":
            return self._result(False, "not_active")
        spec = self.contract["work_candidates"][activation["facility_id"]]
        activation["state"] = "suspended" if (
            spec["resume_original_action"] and original_producer_preserves_action) else "canceled"
        return self._result(True, activation["state"])

    def resume_work(self, activation_id, binding, now, *, original_producer_preserves_action=False,
                    source_available=False, actor_action_legal=False):
        self.advance(now)
        activation = self.state["activations"].get(activation_id)
        if not activation or activation["state"] != "suspended":
            return self._result(False, "not_suspended")
        if binding != activation["binding"]:
            return self._result(False, "binding_mismatch")
        if now >= activation["expires_at"]:
            return self._result(False, "resume_at_or_after_deadline")
        if not (original_producer_preserves_action and source_available and actor_action_legal):
            return self._result(False, "resume_unproven")
        activation["state"] = "active"
        return self._result(True, "same_action_resumed")

    def lose_source(self, facility_instance_id, now):
        self.advance(now)
        for activation in self.state["activations"].values():
            if activation["binding"]["facility_instance_id"] == facility_instance_id and activation["state"] in {"active", "suspended"}:
                activation["state"] = "source_lost"
        for scan in self.state["scans"].values():
            if scan["binding"]["facility_instance_id"] == facility_instance_id and scan["state"] == "reserved":
                scan["state"] = "source_lost"

    def _effect(self, activation_id, binding, receipt_id, response, target_id, now):
        return {
            "origin_kind": "facility_secondary", "activation_id": activation_id,
            "source_instance_id": binding["facility_instance_id"], "action_id": binding["action_id"],
            "primary_receipt_id": receipt_id, "target_id": target_id, "applied_at": now,
            "expires_at": now + response["duration_s"] if "duration_s" in response else None,
            "payload": deepcopy(response), "emits_primary_event": False,
            "may_trigger_EQ01_reaction": False, "shared_TD05_status_processing": True,
        }

    def commit_work(self, activation_id, receipt, now, *, candidates=(), terminal_pool_ids=(),
                    source_available=False, actual_action_complete=False):
        self.advance(now)
        activation = self.state["activations"].get(activation_id)
        if not activation or activation["state"] != "active":
            return self._result(False, "not_active")
        spec = self.contract["work_candidates"][activation["facility_id"]]
        if (receipt.get("binding") != activation["binding"] or receipt.get("event") != spec["source_event"]
                or receipt.get("origin_kind") != "actual_world_work"
                or not isinstance(receipt.get("receipt_id"), str) or not receipt["receipt_id"].strip()):
            return self._result(False, "receipt_mismatch")
        if not actual_action_complete:
            return self._result(False, "no_actual_completion")
        if activation["earliest_complete_at"] is not None and now < activation["earliest_complete_at"]:
            return self._result(False, "original_action_not_finished")
        receipt_key = list(self._receipt_key(activation["binding"], receipt["receipt_id"]))
        if receipt_key in self.state["consumed_work_receipts"]:
            return self._result(False, "original_receipt_already_consumed")
        if not source_available:
            activation["state"] = "source_lost"
            return self._result(False, "source_unavailable")
        activation["state"] = "consumed"
        activation["receipt_id"] = receipt["receipt_id"]
        self.state["consumed_work_receipts"].append(receipt_key)
        self.state["journal"].extend(["original_work_commit", "original_main_rule_terminal_decisions", "facility_legal_target_selection"])
        payload, effects = spec["response"], []
        if payload["kind"] == "reload_work":
            equipment = json.loads((ROOT / "content/equipment_contracts_eq01.json").read_text())
            eligible_nodes = set(equipment["ordinary_attack_progress"]["eligible_nodes"])
            valid = [c for c in candidates if c.get("enabled") is True
                     and isinstance(c.get("tower_instance_id"), str) and c["tower_instance_id"].strip()
                     and c.get("fixture_instance_id") == activation["binding"]["facility_instance_id"]
                     and c.get("node_id") in eligible_nodes and c.get("loading") is True
                     and c.get("base_reload_work", 0) >= 1.5 and c.get("remaining_reload_work", 0) > 0]
            valid.sort(key=lambda c: (-c["remaining_reload_work"], c["tower_instance_id"]))
            if valid:
                tower = valid[0]
                effect = self._effect(activation_id, activation["binding"], receipt["receipt_id"], payload, tower["tower_instance_id"], now)
                effect["advanced_work"] = min(0.1 * tower["base_reload_work"], tower["remaining_reload_work"])
                effect["remaining_work_after"] = tower["remaining_reload_work"] - effect["advanced_work"]
                effects.append(effect)
        else:
            terminal = set(terminal_pool_ids)
            valid = [c for c in candidates if isinstance(c.get("pool_id"), str) and c["pool_id"].strip()
                     and c.get("pool_id") not in terminal and c.get("legal") is True
                     and c.get("manifested") is True and c.get("hostile") is True and c.get("independent_pool") is True
                     and c.get("actual_intersection") is True and c.get("actual_LOS") is True
                     and c.get("layer") in {"ground", "low_air"} and isinstance(c.get("distance"), (int, float))
                     and math.isfinite(c["distance"]) and c["distance"] >= 0]
            valid.sort(key=lambda c: (c["distance"], c["pool_id"]))
            seen = set()
            for candidate in valid:
                if candidate["pool_id"] in seen:
                    continue
                seen.add(candidate["pool_id"])
                effects.append(self._effect(activation_id, activation["binding"], receipt["receipt_id"], payload, candidate["pool_id"], now))
                if len(effects) == payload["max_recipients"]:
                    break
        self.state["effects"].extend(effects)
        return self._result(True, "work_consumed", effects=deepcopy(effects), primary_events_emitted=[])

    def start_scan(self, activation_id, binding, target_id, now, facts):
        self.advance(now)
        reason = self._preflight(activation_id, binding, facts)
        if reason:
            return self._result(False, reason)
        if not isinstance(target_id, str) or not target_id.strip() or facts.get("same_target_legal") is not True:
            return self._result(False, "target_unavailable")
        self.state["used_ids"].append(activation_id)
        self.state["scans"][activation_id] = {
            "binding": deepcopy(binding), "target_id": target_id, "started_at": now,
            "ready_at": now + 2, "state": "reserved",
        }
        return self._result(True, "scan_reserved")

    def cancel_scan(self, activation_id, now):
        self.advance(now)
        scan = self.state["scans"].get(activation_id)
        if not scan or scan["state"] != "reserved":
            return self._result(False, "scan_not_reserved")
        scan["state"] = "canceled"
        return self._result(True, "scan_canceled")

    def commit_scan(self, activation_id, binding, target_id, now, *, source_available=False,
                    same_target_legal=False, actual_action_complete=False, actor_at_station=False,
                    receipt_id=None):
        self.advance(now)
        scan = self.state["scans"].get(activation_id)
        if not scan or scan["state"] != "reserved":
            return self._result(False, "scan_not_reserved")
        if binding != scan["binding"] or target_id != scan["target_id"]:
            return self._result(False, "binding_mismatch")
        if not (source_available and same_target_legal and actor_at_station):
            scan["state"] = "canceled"
            return self._result(False, "scan_invalidated")
        if now < scan["ready_at"] or not actual_action_complete:
            return self._result(False, "scan_not_complete")
        if not isinstance(receipt_id, str) or not receipt_id.strip():
            return self._result(False, "missing_actual_scan_receipt")
        scan["state"] = "committed"
        self.state["reserve"] -= 1
        self.state["next_use"][binding["facility_instance_id"]] = now + 30
        response = self.contract["scan_candidate"]["response"]
        effect = self._effect(activation_id, binding, receipt_id, response, target_id, now)
        self.state["effects"].append(effect)
        return self._result(True, "scan_committed", effects=[deepcopy(effect)], primary_events_emitted=[])

    def end_night(self, now):
        self.advance(now)
        self.state["ended_at"] = now
        for activation in self.state["activations"].values():
            if activation["state"] in {"active", "suspended"}:
                activation["state"] = "night_ended"
        for scan in self.state["scans"].values():
            if scan["state"] == "reserved":
                scan["state"] = "night_ended"

    def live_effects(self, now):
        self.advance(now)
        if self.state["ended_at"] is not None:
            return []
        return deepcopy([e for e in self.state["effects"] if e["expires_at"] is not None and now < e["expires_at"]])
