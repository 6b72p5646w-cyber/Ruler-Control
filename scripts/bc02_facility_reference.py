"""BC02 whole-raid facility design reference; the real client remains disabled.

Inherit BC01 identity/event/RNG/placement primitives. Its customer_use validation
is retained with a configurable bank cap, full raid-interval exclusion and
actual electrical interval/epoch proofs. This module owns no real HP, stock or wallet.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
from bc01_facility_reference import FacilitiesBC01, canonical, stable_choice

ROOT = Path(__file__).resolve().parents[1]


def load_contract():
    return json.loads((ROOT / "content/facilities_bc02.json").read_text())


class FacilitiesBC02(FacilitiesBC01):
    def __init__(self, night_id, attempt_id, seed=0, *, design_simulation=False, contract=None):
        super().__init__(night_id, attempt_id, seed, design_simulation=design_simulation,
                         contract=contract or load_contract())
        self.state.update(version="BC02", reserved_power={}, heal_pending=None,
                          heal_commits={}, discarded_at_night_end={}, raid_intervals=[])
        self.state["power_history"][0].update(epoch_id="initial", source_event_stream_id=None, source_sequence=0)

    def _emit(self, request_id, request_type, **payload):
        if request_type == "spawn_temporary_trap":
            payload.update(lifetime_s=None, lifetime_policy="actual_raid_until_trigger_or_destroyed")
        return super()._emit(request_id, request_type, **payload)

    def acknowledge(self, request_id):
        if self.state["outbox"].get(request_id, {}).get("request_type") == "hp_regen_budgeted_interval":
            return self._result(False, "requires_actual_hp_owner_ack")
        return super().acknowledge(request_id)

    def _service_power_valid(self, fid, start, end, facts, receipt):
        """Join real action sequence/epochs to this owner's actual power history.

        Old timestamp-only receipts remain supported away from an ambiguous
        boundary; they must be powered for their whole action interval.
        """
        role = self.roles[fid]
        if not role["powered"]:
            return True
        def on(state): return state["main_on"] and state["circuits"].get(role["circuit"], False)
        keys = ("source_event_stream_id", "action_started_sequence", "action_completed_sequence",
                "power_epoch_at_start", "power_epoch_at_completion")
        if not any(k in facts for k in keys):
            unambiguous = not any(p["epoch_id"] != "initial" and p["at"] in (start, end)
                                  for p in self.state["power_history"])
            return unambiguous and self._powered(fid, start) and self._powered(fid, end) and all(
                on(p) for p in self.state["power_history"] if start <= p["at"] <= end)
        if not all(k in facts for k in keys):
            return False
        stream, begin_seq, end_seq = (facts[k] for k in keys[:3])
        if (not isinstance(stream, str) or not stream or not isinstance(begin_seq, int) or isinstance(begin_seq, bool)
                or not isinstance(end_seq, int) or isinstance(end_seq, bool) or not 0 < begin_seq < end_seq):
            return False
        action = next((a for a in receipt.get("actual_action_receipts", []) if isinstance(a, dict)
                       and a.get("event_id") == facts.get("actual_action_receipt_id")), None)
        started = action.get("started_event", {}) if action else {}
        if (not action or action.get("source_event_stream_id") != stream or started.get("source_event_stream_id") != stream
                or action.get("sequence") != end_seq or started.get("sequence") != begin_seq
                or action.get("at") != end or started.get("at") != start
                or action.get("customer_id") != receipt["customer_id"] or started.get("customer_id") != receipt["customer_id"]
                or action.get("order_id") != receipt["order_id"] or started.get("order_id") != receipt["order_id"]
                or action.get("power_epoch_at_completion") != facts["power_epoch_at_completion"]
                or started.get("power_epoch_id") != facts["power_epoch_at_start"]):
            return False
        def history_at(at, sequence):
            candidates = []
            for state in self.state["power_history"]:
                if state["at"] < at or state["epoch_id"] == "initial":
                    candidates.append(state)
                elif state["at"] == at:
                    if state.get("source_event_stream_id") != stream or state.get("source_sequence") is None:
                        return None  # No common event ordering: do not trust a boolean override.
                    if state["source_sequence"] < sequence:
                        candidates.append(state)
            return candidates[-1] if candidates else None
        first, last = history_at(start, begin_seq), history_at(end, end_seq)
        if (not first or not last or first["epoch_id"] != facts["power_epoch_at_start"]
                or last["epoch_id"] != facts["power_epoch_at_completion"] or not on(first) or not on(last)):
            return False
        for state in self.state["power_history"]:
            inside = start < state["at"] < end
            if state["at"] in (start, end) and state["epoch_id"] != "initial":
                if state.get("source_event_stream_id") != stream or state.get("source_sequence") is None:
                    return False
                inside = begin_seq < state["source_sequence"] < end_seq
            if inside and not on(state):
                return False
        return True

    def customer_use(self, event_id, customer_id, facility_id, paid_order_receipt, night_id, attempt_id, facts):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        if not isinstance(facts, dict):
            return self._result(False, "invalid_actual_use_facts")
        data = [customer_id, facility_id, paid_order_receipt, night_id, attempt_id, facts]
        reason = self._event_state(event_id, data)
        if reason:
            return self._result(False, reason)
        role = self.roles.get(facility_id)
        if role is None or role["reward"] is None:
            return self._result(False, "facility_has_no_customer_reward")
        receipt = paid_order_receipt
        if not isinstance(receipt, dict) or any(k not in receipt for k in self.contract["customer_use_contract"]["paid_receipt_fields"]):
            return self._result(False, "incomplete_paid_receipt")
        if (not isinstance(receipt["event_id"], str) or not receipt["event_id"]
                or not isinstance(receipt["items"], list) or not isinstance(receipt["facilities_used"], list)
                or any(not isinstance(item, dict) for item in receipt["items"] + receipt["facilities_used"])):
            return self._result(False, "invalid_paid_receipt_shape")
        if (night_id != self.state["night_id"] or attempt_id != self.state["attempt_id"]
                or not isinstance(attempt_id, int) or isinstance(attempt_id, bool)
                or not isinstance(receipt["attempt_id"], int) or isinstance(receipt["attempt_id"], bool)
                or receipt["night_id"] != night_id or receipt["attempt_id"] != attempt_id):
            return self._result(False, "wrong_night_or_attempt")
        if (not isinstance(customer_id, str) or not customer_id.strip() or receipt["customer_id"] != customer_id
                or not isinstance(receipt["order_id"], str) or not receipt["order_id"]):
            return self._result(False, "wrong_customer_or_order")
        if (receipt["paid"] is not True or receipt["normal_customer"] is not True
                or receipt["payment_kind"] != "ordinary_store_sale" or receipt.get("verified") is not True):
            return self._result(False, "not_verified_normal_paid_sale")
        for key in ("logical_customer_id", "logical_order_id"):
            if not isinstance(receipt.get(key), str) or not receipt[key].strip():
                return self._result(False, "missing_stable_logical_identity")
        for table, real, logical in (("logical_customers", customer_id, receipt["logical_customer_id"]),
                                      ("logical_orders", receipt["order_id"], receipt["logical_order_id"])):
            bindings = self.state[table]
            if (real in bindings and bindings[real] != logical
                    or any(k != real and v == logical for k, v in bindings.items())):
                return self._result(False, "logical_identity_binding_changed")
        if (facts.get("normal_customer") is not True or facts.get("customer_kind") != "normal"
                or facts.get("actual_use_completed") is not True or facts.get("origin_kind", "actual_customer_use") != "actual_customer_use"):
            return self._result(False, "not_real_normal_customer_use")
        for flag in ("consumer_registered", "facility_geometry_bound", "same_order_service", "source_item_owner_customer"):
            if facts.get(flag) is not True:
                return self._result(False, "unproven_" + flag)
        used_at, paid_at = facts.get("actual_use_at"), receipt["completed_at"]
        if not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                   and 0 <= v <= self.state["now"] + 1e-8 for v in (used_at, paid_at)):
            return self._result(False, "invalid_use_or_payment_time")
        if any(raid["started_at"] <= at and (raid["ended_at"] is None or at < raid["ended_at"])
               for raid in self.state["raid_intervals"] for at in (used_at, paid_at)):
            return self._result(False, "normal_customer_service_or_payment_occurred_during_actual_raid")
        if facts.get("usage_kind") != role["usage_kind"]:
            return self._result(False, "wrong_use_kind")
        duration = facts.get("use_duration_s")
        if (not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration)
                or duration < 0 or (facility_id != "FR10" and
                                    (duration <= 0 or facts.get("progress_complete") is not True))):
            return self._result(False, "actual_service_progress_not_completed")
        started_at = facts.get("actual_use_started_at", used_at - duration)
        if (not isinstance(started_at, (int, float)) or isinstance(started_at, bool) or not math.isfinite(started_at)
                or not 0 <= started_at <= used_at or abs(used_at - started_at - duration) > 1e-6):
            return self._result(False, "invalid_actual_service_interval")
        if any(max(started_at, raid["started_at"]) < min(used_at, raid["ended_at"] if raid["ended_at"] is not None else self.state["now"])
               for raid in self.state["raid_intervals"]):
            return self._result(False, "normal_customer_service_interval_overlaps_actual_raid")
        if not self._service_power_valid(facility_id, started_at, used_at, facts, receipt):
            return self._result(False, "source_was_unpowered_during_use")
        if facility_id == "FR01" and abs(used_at - paid_at) > 1e-8:
            return self._result(False, "checkout_must_match_payment_commit")
        if facility_id == "FR10" and (used_at < paid_at or facts.get("exit_boundary_crossed") is not True):
            return self._result(False, "paid_exit_not_observed")
        if not role["natural_event"] and facts.get("route_service_authorized") is not True:
            return self._result(False, "service_not_on_authorized_route")
        if facility_id in {"FR02", "FR03", "FR04", "FR05"}:
            source_item = facts.get("source_item_id")
            if not isinstance(source_item, str) or not source_item or not any(
                    item.get("source_item_id") == source_item and item.get("facility_id") == facility_id
                    and isinstance(item.get("quantity"), (int, float)) and item["quantity"] > 0
                    for item in receipt["items"]):
                return self._result(False, "product_not_in_original_paid_stock")
            if not any(use.get("facility_id") == facility_id and use.get("source_item_id") == source_item
                       and use.get("usage_kind") == role["usage_kind"] and use.get("actual_use_at") == used_at
                       for use in receipt["facilities_used"]):
                return self._result(False, "product_use_not_in_original_payment")
        immutable_payment = {key: receipt[key] for key in ("event_id", "order_id", "customer_id", "logical_customer_id", "logical_order_id", "night_id", "attempt_id", "paid", "payment_kind", "completed_at", "normal_customer", "items")}
        order_id = receipt["order_id"]
        if order_id in self.state["orders"] and self.state["orders"][order_id] != immutable_payment:
            return self._result(False, "payment_receipt_changed")
        use_key = [night_id, attempt_id, customer_id, order_id, facility_id]
        if use_key in self.state["uses"]:
            return self._result(False, "same_paid_customer_facility_already_processed")
        services = self.state["optional_services"].get(order_id, [])
        if not role["natural_event"] and len(services) >= 2:
            return self._result(False, "optional_service_limit")
        # A genuine completed use is recorded even when its reward bank is full.
        self._record_event(event_id, data)
        self.state["orders"][order_id] = deepcopy(immutable_payment)
        self.state["logical_customers"][customer_id] = receipt["logical_customer_id"]
        self.state["logical_orders"][order_id] = receipt["logical_order_id"]
        self.state["uses"].append(use_key)
        if not role["natural_event"]:
            self.state["optional_services"].setdefault(order_id, []).append(facility_id)
        if (len(self.state["bank"][facility_id]) >= self.contract["bank"]["per_facility_max_tokens"]
                or self._bank_total() >= self.contract["bank"]["whole_store_max_tokens"]):
            return self._result(True, "use_completed_bank_full_no_replacement")
        if facility_id == "FR10":
            if self.state["survival_payouts"] >= 12:
                return self._result(True, "use_completed_survival_night_cap")
            held = self.state["survival_remaining"] + 30 * len(self.state["bank"]["FR10"])
            if held + 30 > 120:
                return self._result(True, "use_completed_survival_storage_full")
        reward = deepcopy(role["reward"])
        stable_parts = [self.state["seed"], night_id, receipt["logical_customer_id"], receipt["logical_order_id"], facility_id]
        if reward["kind"] == "lucky_buff":
            reward = deepcopy(reward["variants"][stable_choice("BC01_CUSTOMER_LUCKY_RECEIPT", stable_parts, 3)])
        variant = None
        if reward["kind"] == "temporary_trap_token":
            variant = self.contract["temporary_traps"]["type_pool"][stable_choice("BC01_CUSTOMER_TRAP", stable_parts, 3)]["id"]
        token = {"token_id": f"bc01:{night_id}:{attempt_id}:service:" + hashlib.sha256(canonical(use_key).encode()).hexdigest()[:20],
                 "facility_id": facility_id, "origin_event_id": event_id, "paid_receipt_id": receipt["event_id"],
                 "stable_source_key": hashlib.sha256(canonical(stable_parts).encode()).hexdigest(),
                 "earned_at": self.state["now"], "reward": reward, "trap_variant": variant, "eligible_raid_id": None}
        self.state["bank"][facility_id].append(token)
        return self._result(True, "customer_credit_banked", token=deepcopy(token))

    def _activate(self, fid, token):
        """Activate one fixed, prior-raid token; never draw a new reward here."""
        self.state["bank"][fid].remove(token)
        reward = deepcopy(token["reward"])
        prefix = f"bc02:{self.state['night_id']}:{self.state['attempt_id']}:{self.state['raid_id']}:{fid}"
        if reward["kind"] == "stamina_restore_fraction":
            return [self._emit(prefix, "resource_restore", resource="stamina",
                               fraction_of_actual_max=reward["value"], source_facility_id=fid,
                               original_customer_tokens=[token["token_id"]])]
        effect = {"effect_id": prefix, "source_facility_id": fid,
                  "raid_id": self.state["raid_id"], "started_at": self.state["now"],
                  "lifetime": "actual_raid", "reward": reward,
                  "origin_kind": "customer_facility_support", "tokens": [token["token_id"]],
                  "may_generate_customer_use": False}
        if reward["kind"] == "hp_regen":
            effect["heal_budget_remaining_fraction"] = reward["actual_restore_budget_fraction"]
            effect["heal_actual_restored_fraction"] = 0.0
        self.state["buffs"].append(effect)
        return [self._emit(prefix, "buff_started", effect=deepcopy(effect))]

    def raid_started(self, raid_id):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        if not isinstance(raid_id, str) or not raid_id:
            return self._result(False, "missing_raid_id")
        if raid_id in self.state["started_raids"] or self.state["phase"] == "RAID":
            return self._result(False, "raid_already_started")
        self.state.update(phase="RAID", raid_id=raid_id, reserved_power={},
                          trap_deployments_this_raid=0, next_trap_retry_at=self.state["now"],
                          next_trap_deploy_at=self.state["now"])
        self.state["started_raids"].append(raid_id)
        self.state["raid_intervals"].append({"raid_id": raid_id, "started_at": self.state["now"], "ended_at": None})
        requests = []
        for fid, tokens in self.state["bank"].items():
            if not tokens:
                continue
            if fid == "FR02":
                for token in tokens:
                    token["eligible_raid_id"] = raid_id
            elif fid == "FR10":
                self.state["survival_remaining"] = min(120, self.state["survival_remaining"] + 30 * len(tokens))
                tokens.clear()
            elif self._powered(fid):
                requests.extend(self._activate(fid, tokens[0]))
            else:
                self.state["reserved_power"][fid] = tokens[0]["token_id"]
        return self._result(True, "whole_raid_support_reserved", requests=requests)

    def _enabled_effects(self):
        if self.state["phase"] != "RAID":
            return []
        return [e for e in self.state["buffs"] if e["raid_id"] == self.state["raid_id"]
                and e["started_at"] <= self.state["now"] and self._powered(e["source_facility_id"])]

    def active_modifiers(self):
        groups = {}
        for effect in self._enabled_effects():
            if effect["reward"]["kind"] == "hp_regen" and effect["heal_budget_remaining_fraction"] <= 1e-12:
                continue
            groups.setdefault(effect["reward"]["group"], []).append(effect)
        result = []
        for _, effects in sorted(groups.items()):
            multiplier = effects[0]["reward"]["kind"] == "manual_interaction_multiplier"
            result.append(deepcopy(sorted(effects, key=lambda e: (
                e["reward"]["value"] if multiplier else -e["reward"]["value"], e["source_facility_id"]))[0]))
        return result

    def actual_world_tick(self, event_id, now, alive, paused=False, *, eligibility_cutoff=720.0):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        data = ["tick", now, alive, paused, eligibility_cutoff]
        reason = self._event_state(event_id, data)
        if reason:
            return self._result(False, reason)
        if (not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now)
                or now < self.state["now"] or not isinstance(alive, bool) or not isinstance(paused, bool)
                or not isinstance(eligibility_cutoff, (int, float)) or isinstance(eligibility_cutoff, bool)
                or not math.isfinite(eligibility_cutoff) or not 0 <= eligibility_cutoff <= 720):
            return self._result(False, "invalid_actual_world_interval")
        if paused and now != self.state["now"]:
            return self._result(False, "paused_world_clock_must_not_advance")
        if self.state["heal_pending"] and now > self.state["now"]:
            return self._result(False, "actual_hp_owner_ack_required_before_advance")
        self._record_event(event_id, data)
        before, requests = self.state["now"], []
        if self.state["phase"] == "RAID" and alive and not paused and now > before:
            sources = sorted([e for e in self._enabled_effects() if e["reward"]["kind"] == "hp_regen"
                              and e["heal_budget_remaining_fraction"] > 1e-12],
                             key=lambda e: (-e["reward"]["value"], e["source_facility_id"]))
            cursor, allocations = before, []
            for effect in sources:
                rate = effect["reward"]["value"]
                seconds = min(now - cursor, effect["heal_budget_remaining_fraction"] / rate)
                if seconds <= 1e-12:
                    break
                allocations.append({"effect_id": effect["effect_id"],
                                    "source_facility_id": effect["source_facility_id"],
                                    "from_world_time": cursor, "to_world_time": cursor + seconds,
                                    "fraction_max_hp_per_second": rate, "offered_fraction": seconds * rate})
                cursor += seconds
            if allocations:
                request = self._emit(f"bc02:{self.state['night_id']}:{self.state['attempt_id']}:regen:{event_id}",
                                     "hp_regen_budgeted_interval", raid_id=self.state["raid_id"],
                                     from_world_time=before, to_world_time=now, allocations=allocations,
                                     maximum_fraction_of_actual_max_hp=sum(a["offered_fraction"] for a in allocations),
                                     root_hp_owner_ack_required=True, may_revive=False, no_catchup=True)
                self.state["heal_pending"] = request["request_id"]
                requests.append(request)
            if self.state["survival_payouts"] < 12:
                eligible = max(0., min(now, eligibility_cutoff) - min(before, eligibility_cutoff))
                credit = min(eligible, self.state["survival_remaining"])
                self.state["survival_remaining"] -= credit
                self.state["survival_progress"] += credit
                while self.state["survival_progress"] + 1e-9 >= 15 and self.state["survival_payouts"] < 12:
                    self.state["survival_progress"] = max(0., self.state["survival_progress"] - 15)
                    self.state["survival_payouts"] += 1
                    ordinal = self.state["survival_payouts"]
                    requests.append(self._emit(f"bc01:{self.state['night_id']}:{self.state['attempt_id']}:facility_survival:{ordinal}",
                                               "payout", coin=1, xp=1, reason="actual_alive_raid_credit_consumed", source_facility_id="FR10"))
                if self.state["survival_payouts"] == 12:
                    self.state["survival_remaining"] = self.state["survival_progress"] = 0
                    self.state["bank"]["FR10"].clear()
        self.state["now"] = now
        return self._result(True, "actual_world_advanced", requests=requests)

    def hp_regen_ack(self, request_id, receipt):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        if request_id in self.state["heal_commits"]:
            old = self.state["heal_commits"][request_id]
            return self._result(old == receipt, "hp_ack_replay" if old == receipt else "hp_ack_conflict")
        if self.state["heal_pending"] != request_id or not isinstance(receipt, dict):
            return self._result(False, "hp_request_not_pending")
        request = self.state["outbox"][request_id]
        if (receipt.get("request_id") != request_id or receipt.get("at_world_time") != self.state["now"]
                or request["raid_id"] != self.state["raid_id"]):
            return self._result(False, "hp_owner_receipt_wrong_boundary")
        before, after, maximum = (receipt.get(k) for k in ("hp_before", "hp_after", "actual_max_hp"))
        if (not all(isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)
                    for v in (before, after, maximum)) or not 0 <= before <= after <= maximum or maximum <= 0
                or receipt.get("alive_before") is not (before > 0)
                or not isinstance(receipt.get("request_recorded_by_hp_owner"), bool)
                or (before > 0 and receipt["request_recorded_by_hp_owner"] is not True)
                or (before == 0 and after != 0)):
            return self._result(False, "invalid_actual_hp_owner_receipt")
        restored = (after - before) / maximum
        if restored > request["maximum_fraction_of_actual_max_hp"] + 1e-9:
            return self._result(False, "actual_hp_exceeds_offered_interval")
        remaining, consumed = restored, []
        for allocation in request["allocations"]:
            effect = next(e for e in self.state["buffs"] if e["effect_id"] == allocation["effect_id"])
            amount = min(remaining, allocation["offered_fraction"])
            effect["heal_budget_remaining_fraction"] = max(0., effect["heal_budget_remaining_fraction"] - amount)
            effect["heal_actual_restored_fraction"] += amount
            remaining = max(0., remaining - amount)
            consumed.append({"effect_id": effect["effect_id"], "actual_restored_fraction": amount})
        self.state["heal_commits"][request_id] = deepcopy(receipt)
        self.state["heal_pending"] = None
        self.state["acknowledged"].append(request_id)
        return self._result(True, "actual_hp_budget_committed", restored_fraction=restored, consumed=consumed)

    def power_changed(self, event_id, circuit_id, powered, *, source_event_stream_id=None, source_sequence=None):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        data = ["power", circuit_id, powered, self.state["now"], source_event_stream_id, source_sequence]
        reason = self._event_state(event_id, data)
        if reason:
            return self._result(False, reason)
        if circuit_id not in {"MAIN", "C1", "C2", "C3"} or not isinstance(powered, bool):
            return self._result(False, "invalid_power_change")
        if (source_event_stream_id is not None or source_sequence is not None) and (
                not isinstance(source_event_stream_id, str) or not source_event_stream_id
                or not isinstance(source_sequence, int) or isinstance(source_sequence, bool) or source_sequence < 1):
            return self._result(False, "invalid_power_source_order")
        if source_event_stream_id is not None and any(
                p.get("source_event_stream_id") == source_event_stream_id and p["source_sequence"] >= source_sequence
                for p in self.state["power_history"]):
            return self._result(False, "power_source_sequence_not_monotonic")
        if self.state["heal_pending"]:
            return self._result(False, "actual_hp_owner_ack_required_before_power_change")
        previous = {fid: self._powered(fid) for fid in self.roles}
        self._record_event(event_id, data)
        if circuit_id == "MAIN":
            self.state["main_on"] = powered
        else:
            self.state["circuits"][circuit_id] = powered
        self.state["power_history"].append({"at": self.state["now"], "main_on": self.state["main_on"],
                                            "circuits": deepcopy(self.state["circuits"]), "epoch_id": event_id,
                                            "source_event_stream_id": source_event_stream_id, "source_sequence": source_sequence})
        requests = [self._emit(f"bc02:{self.state['night_id']}:{self.state['attempt_id']}:power:{event_id}", "electric_power_gate",
                               circuit_id=circuit_id, powered=powered, overload_allowed=self.electric_overload_allowed(),
                               no_contact_on_restart=True, no_missed_overload_catchup=True)]
        for effect in self.state["buffs"]:
            fid = effect["source_facility_id"]
            if self.state["phase"] == "RAID" and previous[fid] != self._powered(fid):
                requests.append(self._emit(effect["effect_id"] + ":power:" + event_id, "buff_source_enabled",
                                          effect_id=effect["effect_id"], enabled=self._powered(fid), lifetime="actual_raid",
                                          heal_budget_remaining_fraction=effect.get("heal_budget_remaining_fraction")))
        if self.state["phase"] == "RAID":
            for fid, token_id in list(self.state["reserved_power"].items()):
                if self._powered(fid):
                    token = next(t for t in self.state["bank"][fid] if t["token_id"] == token_id)
                    requests.extend(self._activate(fid, token))
                    del self.state["reserved_power"][fid]
        return self._result(True, "power_state_changed", requests=requests)

    def trap_placement_ack(self, request_id, accepted, **kwargs):
        result = super().trap_placement_ack(request_id, accepted, **kwargs)
        if result["ok"]:
            self.state["active_trap"].pop("expires_at")
            self.state["active_trap"]["lifetime"] = "actual_raid"
            result["trap"] = deepcopy(self.state["active_trap"])
        return result

    def trap_triggered(self, event_id, instance_id, pool_id, facts):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        data = ["trap_trigger", instance_id, pool_id, facts]
        reason = self._event_state(event_id, data)
        if reason:
            return self._result(False, reason)
        trap = self.state["active_trap"]
        if (self.state["phase"] != "RAID" or not trap or trap["instance_id"] != instance_id
                or trap["raid_id"] != self.state["raid_id"] or self.state["now"] < trap["armed_at"]):
            return self._result(False, "trap_not_armed")
        if (not isinstance(facts, dict) or not isinstance(pool_id, str) or not pool_id
                or not all(facts.get(k) is True for k in ("actual_new_entry", "actual_collision", "manifested", "hostile",
                                                       "independent_pool", "ground_layer", "world_consumer_verified"))):
            return self._result(False, "not_actual_legal_hostile_entry")
        self._record_event(event_id, data)
        request = self._emit(f"bc01:{instance_id}:trigger", "apply_temporary_trap_effect", pool_id=pool_id,
                             source_instance_id=instance_id, source_trap=trap["variant"]["source_trap"],
                             payload=deepcopy(trap["variant"]["effect"]), origin_kind="facility_secondary",
                             shared_TD05_resistance_control_and_aggregation=True, may_generate_customer_use=False,
                             may_trigger_equipment_procs=False)
        return self._result(True, "one_real_entry_consumed", requests=[request, self._remove_trap("single_charge_used", self.state["now"])])

    def raid_ended(self, raid_id):
        if self.state["heal_pending"]:
            return self._result(False, "actual_hp_owner_ack_required_before_raid_end")
        result = super().raid_ended(raid_id)
        if result["ok"]:
            self.state["reserved_power"].clear()
            next(r for r in self.state["raid_intervals"] if r["raid_id"] == raid_id)["ended_at"] = self.state["now"]
        return result

    def night_ended(self):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        if self.state["heal_pending"]:
            return self._result(False, "actual_hp_owner_ack_required_before_night_end")
        expired = {fid: len(tokens) for fid, tokens in self.state["bank"].items() if tokens}
        result = super().night_ended()
        if result["ok"]:
            self.state["reserved_power"].clear()
            self.state["discarded_at_night_end"] = expired
            result["expired_bank_counts"] = deepcopy(expired)
        return result
