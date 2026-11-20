"""BC01 bounded customer-service reference; no HP, wallet or world ownership.

The caller supplies authenticated customer use and live world-placement facts.
Default construction is disabled. Explicit design_simulation is for reference
integration only and does not turn on the actual game client.
"""
from __future__ import annotations

from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def load_contract():
    return json.loads((ROOT / "content/facilities_bc01.json").read_text())


def canonical(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def stable_choice(namespace, parts, count):
    """Unbiased bounded draw from a separate deterministic hash stream."""
    limit = (1 << 256) - ((1 << 256) % count)
    for counter in range(100):
        digest = hashlib.sha256(canonical([namespace, *parts, counter]).encode()).digest()
        number = int.from_bytes(digest, "big")
        if number < limit:
            return number % count
    raise RuntimeError("unreachable_hash_rejection_limit")


class FacilitiesBC01:
    def __init__(self, night_id, attempt_id, seed=0, *, design_simulation=False, contract=None):
        if (not isinstance(night_id, str) or not night_id
                or not isinstance(attempt_id, int) or isinstance(attempt_id, bool) or attempt_id < 1):
            raise ValueError("night_and_attempt_required")
        self.contract = deepcopy(contract or load_contract())
        self.roles = {role["id"]: role for role in self.contract["roles"]}
        self.design_simulation = design_simulation
        self.state = {
            "night_id": night_id, "attempt_id": attempt_id, "seed": seed, "now": 0.0,
            "phase": "BUSINESS", "raid_id": None, "completed_raids": [], "started_raids": [],
            "main_on": True, "circuits": {c: True for c in self.contract["power"]["circuits"]},
            "power_history": [{"at": 0.0, "main_on": True, "circuits": {"C1": True, "C2": True, "C3": True}}],
            "bank": {fid: [] for fid in self.roles}, "uses": [], "event_receipts": {},
            "orders": {}, "optional_services": {}, "buffs": [], "outbox": {}, "acknowledged": [],
            "logical_customers": {}, "logical_orders": {},
            "survival_remaining": 0.0, "survival_progress": 0.0, "survival_payouts": 0,
            "active_trap": None, "pending_trap": None, "trap_requests": {},
            "trap_deployments_this_raid": 0, "next_trap_deploy_at": 0.0,
            "next_trap_retry_at": 0.0, "trap_request_sequence": 0, "temporary_instance_ids": [],
        }

    def snapshot(self):
        return deepcopy(self.state)

    @classmethod
    def restore(cls, state, *, design_simulation=False):
        result = cls(state["night_id"], state["attempt_id"], state["seed"], design_simulation=design_simulation)
        result.state = deepcopy(state)
        return result

    def _result(self, ok, reason, **extra):
        return {"ok": ok, "reason": reason, **extra}

    def _gate(self):
        if not self.design_simulation:
            return "actual_game_adapter_disabled"
        if self.state["phase"] == "ENDED":
            return "night_ended"
        return None

    def _emit(self, request_id, request_type, **payload):
        request = {"request_id": request_id, "request_type": request_type,
                   "night_id": self.state["night_id"], "attempt_id": self.state["attempt_id"], **payload}
        old = self.state["outbox"].get(request_id)
        if old is not None and old != request:
            raise ValueError("conflicting_request_id")
        self.state["outbox"][request_id] = request
        return deepcopy(request)

    def pending_requests(self):
        return deepcopy([r for key, r in self.state["outbox"].items()
                         if key not in self.state["acknowledged"]
                         and self.state["trap_requests"].get(key, {}).get("status", "pending") == "pending"])

    def acknowledge(self, request_id):
        if not self.design_simulation:
            return self._result(False, "actual_game_adapter_disabled")
        if request_id not in self.state["outbox"]:
            return self._result(False, "unknown_request")
        if self.state["outbox"][request_id]["request_type"] == "spawn_temporary_trap":
            return self._result(False, "requires_world_placement_ack")
        if request_id not in self.state["acknowledged"]:
            self.state["acknowledged"].append(request_id)
        return self._result(True, "acknowledged")

    def _event_state(self, event_id, data):
        if not isinstance(event_id, str) or not event_id.strip():
            return "missing_event_id"
        fingerprint = canonical(data)
        previous = self.state["event_receipts"].get(event_id)
        if previous is not None:
            return "event_replay" if previous == fingerprint else "event_id_conflict"
        return None

    def _record_event(self, event_id, data):
        self.state["event_receipts"][event_id] = canonical(data)

    def _powered(self, facility_id, at=None):
        role = self.roles[facility_id]
        if not role["powered"]:
            return True
        power = self.state
        if at is not None:
            valid = [p for p in self.state["power_history"] if p["at"] <= at]
            if not valid:
                return False
            power = valid[-1]
        return power["main_on"] and power["circuits"].get(role["circuit"], False)

    def electric_overload_allowed(self):
        return self.state["main_on"] and self.state["circuits"]["C2"]

    def _bank_total(self):
        return sum(len(tokens) for tokens in self.state["bank"].values())

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
        if facts.get("usage_kind") != role["usage_kind"]:
            return self._result(False, "wrong_use_kind")
        duration = facts.get("use_duration_s")
        if (not isinstance(duration, (int, float)) or isinstance(duration, bool) or not math.isfinite(duration)
                or duration < 0 or (facility_id != "FR10" and
                                    (duration <= 0 or facts.get("progress_complete") is not True))):
            return self._result(False, "actual_service_progress_not_completed")
        if not self._powered(facility_id, used_at):
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
        if len(self.state["bank"][facility_id]) >= 2 or self._bank_total() >= 8:
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

    def raid_started(self, raid_id):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        if not isinstance(raid_id, str) or not raid_id:
            return self._result(False, "missing_raid_id")
        if raid_id in self.state["started_raids"] or self.state["phase"] == "RAID":
            return self._result(False, "raid_already_started")
        self.state["phase"] = "RAID"
        self.state["raid_id"] = raid_id
        self.state["started_raids"].append(raid_id)
        self.state["trap_deployments_this_raid"] = 0
        self.state["next_trap_retry_at"] = self.state["now"]
        self.state["next_trap_deploy_at"] = self.state["now"]
        requests = []
        for fid, tokens in self.state["bank"].items():
            if not tokens or not self._powered(fid):
                continue
            if fid == "FR02":
                for token in tokens:
                    token["eligible_raid_id"] = raid_id
                continue
            grouped = {}
            for token in tokens:
                reward = token["reward"]
                grouped.setdefault(canonical(reward), []).append(token)
            for group in grouped.values():
                reward = deepcopy(group[0]["reward"])
                prefix = f"bc01:{self.state['night_id']}:{self.state['attempt_id']}:{raid_id}:{fid}:{reward['kind']}"
                if reward["kind"] == "survival_credit_seconds":
                    self.state["survival_remaining"] = min(120, self.state["survival_remaining"] + 30 * len(group))
                elif reward["kind"] == "stamina_restore_fraction":
                    requests.append(self._emit(prefix, "resource_restore", resource="stamina",
                                               fraction_of_actual_max=min(0.2, 0.1 * len(group)), source_facility_id=fid,
                                               original_customer_tokens=[t["token_id"] for t in group]))
                else:
                    effect = {"effect_id": prefix, "source_facility_id": fid, "raid_id": raid_id,
                              "started_at": self.state["now"], "expires_at": self.state["now"] + reward["duration_s"] * len(group),
                              "reward": reward, "origin_kind": "customer_facility_support",
                              "tokens": [t["token_id"] for t in group], "may_generate_customer_use": False}
                    self.state["buffs"].append(effect)
                    requests.append(self._emit(prefix, "buff_started", effect=deepcopy(effect)))
            tokens.clear()
        return self._result(True, "raid_support_activated", requests=requests)

    def active_modifiers(self):
        if self.state["phase"] != "RAID":
            return []
        active = [effect for effect in self.state["buffs"]
                  if effect["raid_id"] == self.state["raid_id"] and effect["started_at"] <= self.state["now"] < effect["expires_at"]
                  and self._powered(effect["source_facility_id"])]
        groups = {}
        for effect in active:
            groups.setdefault(effect["reward"]["group"], []).append(effect)
        result = []
        for group, effects in sorted(groups.items()):
            is_multiplier = effects[0]["reward"]["kind"] == "manual_interaction_multiplier"
            chosen = sorted(effects, key=lambda e: (e["reward"]["value"] if is_multiplier else -e["reward"]["value"],
                                                   -e["expires_at"], e["effect_id"]))[0]
            result.append(deepcopy(chosen))
        return result

    def actual_world_tick(self, event_id, now, alive, paused=False, *, eligibility_cutoff=720.0):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        data = ["tick", now, alive, paused, eligibility_cutoff]
        reason = self._event_state(event_id, data)
        if reason:
            return self._result(False, reason)
        if (not isinstance(now, (int, float)) or isinstance(now, bool) or not math.isfinite(now) or now < self.state["now"]
                or not isinstance(alive, bool) or not isinstance(paused, bool)
                or not isinstance(eligibility_cutoff, (int, float)) or isinstance(eligibility_cutoff, bool)
                or not math.isfinite(eligibility_cutoff) or not 0 <= eligibility_cutoff <= 720):
            return self._result(False, "invalid_actual_world_interval")
        if paused and now != self.state["now"]:
            return self._result(False, "paused_world_clock_must_not_advance")
        self._record_event(event_id, data)
        before, requests = self.state["now"], []
        if self.state["phase"] == "RAID" and alive and not paused:
            regen = [effect for effect in self.state["buffs"] if effect["reward"]["kind"] == "hp_regen"
                     and effect["raid_id"] == self.state["raid_id"] and self._powered(effect["source_facility_id"])
                     and effect["expires_at"] > before and effect["started_at"] < now]
            boundaries = sorted({before, now, *[max(before, e["started_at"]) for e in regen],
                                 *[min(now, e["expires_at"]) for e in regen]})
            for index, (start, end) in enumerate(zip(boundaries, boundaries[1:])):
                sources = [e for e in regen if e["started_at"] <= start and e["expires_at"] >= end]
                if not sources or end <= start:
                    continue
                strongest = max(e["reward"]["value"] for e in sources)
                requests.append(self._emit(f"bc01:{self.state['night_id']}:{self.state['attempt_id']}:regen:{event_id}:{index}",
                                          "hp_regen_interval", from_world_time=start, to_world_time=end,
                                          actual_alive_raid_seconds=end - start, fraction_max_hp_per_second=strongest,
                                          source_effect_ids=sorted(e["effect_id"] for e in sources if e["reward"]["value"] == strongest)))
            if self.state["survival_payouts"] < 12:
                eligible_seconds = max(0.0, min(now, eligibility_cutoff) - min(before, eligibility_cutoff))
                credit = min(eligible_seconds, self.state["survival_remaining"])
                self.state["survival_remaining"] -= credit
                self.state["survival_progress"] += credit
                while self.state["survival_progress"] + 1e-9 >= 15 and self.state["survival_payouts"] < 12:
                    self.state["survival_progress"] = max(0.0, self.state["survival_progress"] - 15)
                    self.state["survival_payouts"] += 1
                    ordinal = self.state["survival_payouts"]
                    requests.append(self._emit(f"bc01:{self.state['night_id']}:{self.state['attempt_id']}:facility_survival:{ordinal}",
                                              "payout", coin=1, xp=1, reason="actual_alive_raid_credit_consumed", source_facility_id="FR10"))
                if self.state["survival_payouts"] == 12:
                    self.state["survival_remaining"] = self.state["survival_progress"] = 0
                    self.state["bank"]["FR10"].clear()
        self.state["now"] = now
        trap = self.state["active_trap"]
        if trap and now >= trap["expires_at"]:
            requests.append(self._remove_trap("expiry", trap["expires_at"]))
        return self._result(True, "actual_world_advanced", requests=requests)

    def power_changed(self, event_id, circuit_id, powered):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        data = ["power", circuit_id, powered, self.state["now"]]
        reason = self._event_state(event_id, data)
        if reason:
            return self._result(False, reason)
        if circuit_id not in {"MAIN", "C1", "C2", "C3"} or not isinstance(powered, bool):
            return self._result(False, "invalid_power_change")
        previous = {fid: self._powered(fid) for fid in self.roles}
        self._record_event(event_id, data)
        if circuit_id == "MAIN":
            self.state["main_on"] = powered
        else:
            self.state["circuits"][circuit_id] = powered
        self.state["power_history"].append({"at": self.state["now"], "main_on": self.state["main_on"], "circuits": deepcopy(self.state["circuits"])})
        requests = [self._emit(f"bc01:{self.state['night_id']}:{self.state['attempt_id']}:power:{event_id}", "electric_power_gate",
                               circuit_id=circuit_id, powered=powered, overload_allowed=self.electric_overload_allowed(),
                               no_contact_on_restart=True, no_missed_overload_catchup=True)]
        for effect in self.state["buffs"]:
            fid = effect["source_facility_id"]
            if self.state["phase"] == "RAID" and self.state["now"] < effect["expires_at"] and previous[fid] != self._powered(fid):
                requests.append(self._emit(f"{effect['effect_id']}:power:{event_id}", "buff_source_enabled",
                                          effect_id=effect["effect_id"], enabled=self._powered(fid), original_expires_at=effect["expires_at"]))
        return self._result(True, "power_state_changed", requests=requests)

    def propose_trap(self, placement_candidates, *, object_count, footprint_cells, nav_revision, safe_current_world=False):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        if self.state["phase"] != "RAID":
            return self._result(False, "not_in_actual_raid")
        if self.state["pending_trap"]:
            return self._result(True, "existing_pending_request", request=deepcopy(self.state["outbox"][self.state["pending_trap"]]))
        if self.state["active_trap"] or self.state["trap_deployments_this_raid"] >= 2:
            return self._result(False, "temporary_instance_or_raid_limit")
        if self.state["now"] < max(self.state["next_trap_retry_at"], self.state["next_trap_deploy_at"]):
            return self._result(False, "temporary_retry_or_deploy_cooldown")
        self.state["next_trap_retry_at"] = self.state["now"] + 1
        tokens = [t for t in self.state["bank"]["FR02"] if t["eligible_raid_id"] == self.state["raid_id"]]
        if not tokens:
            return self._result(False, "no_prior_raid_gift_token")
        token = tokens[0]
        variant = next(v for v in self.contract["temporary_traps"]["type_pool"] if v["id"] == token["trap_variant"])
        area = math.prod(variant["footprint"])
        if (not isinstance(object_count, int) or isinstance(object_count, bool)
                or not isinstance(footprint_cells, int) or isinstance(footprint_cells, bool) or object_count < 0 or footprint_cells < 0
                or object_count + 1 > 8 or footprint_cells + area > 16):
            return self._result(False, "shared_capacity_unavailable_token_retained")
        if safe_current_world is not True or not isinstance(nav_revision, str) or not nav_revision:
            return self._result(False, "live_geometry_unproven_token_retained")
        valid = []
        for candidate in placement_candidates:
            if not isinstance(candidate, dict):
                continue
            cells = candidate.get("cells", [])
            rotation = candidate.get("rotation")
            expected = list(reversed(variant["footprint"])) if rotation == 90 else variant["footprint"]
            origin = candidate.get("origin_cell")
            if (rotation not in {0, 90} or not isinstance(origin, list) or len(origin) != 2
                    or any(not isinstance(v, int) or isinstance(v, bool) for v in origin)
                    or not isinstance(cells, list) or len(cells) != area
                    or any(not isinstance(cell, list) or len(cell) != 2
                           or any(not isinstance(v, int) or isinstance(v, bool) for v in cell) for cell in cells)):
                continue
            expected_cells = {(origin[0] + x, origin[1] + y) for x in range(expected[0]) for y in range(expected[1])}
            if (set(map(tuple, cells)) == expected_cells and candidate.get("nonblocking") is True
                    and list(candidate.get("footprint", [])) == expected):
                valid.append(candidate)
        if not valid:
            return self._result(False, "no_safe_footprint_token_retained")
        valid.sort(key=lambda c: canonical(c["cells"]))
        chosen = valid[stable_choice("BC01_CUSTOMER_TRAP_SITE", [self.state["seed"], token["stable_source_key"], self.state["raid_id"], nav_revision], len(valid))]
        self.state["trap_request_sequence"] += 1
        request_id = f"{token['token_id']}:spawn:{self.state['raid_id']}:{self.state['trap_request_sequence']}"
        request = self._emit(request_id, "spawn_temporary_trap", token_id=token["token_id"], variant=deepcopy(variant),
                             placement=deepcopy(chosen), nav_revision=nav_revision, raid_id=self.state["raid_id"],
                             lifetime_s=20, arm_warning_s=0.5, charges=1, ownership="temporary_customer_service",
                             sellable=False, inventory_convertible=False, counts_in_shared_8_objects_16_cells=True)
        self.state["pending_trap"] = request_id
        self.state["trap_requests"][request_id] = {"status": "pending", "token_id": token["token_id"]}
        return self._result(True, "placement_proposed_not_consumed", request=request)

    def trap_placement_ack(self, request_id, accepted, *, actual_instance_id=None, current_nav_revision=None,
                           actual_safe_world_placement=False, total_objects_after=None, total_footprint_after=None):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        state = self.state["trap_requests"].get(request_id)
        if not state or state["status"] != "pending" or self.state["pending_trap"] != request_id:
            return self._result(False, "placement_not_pending")
        request = self.state["outbox"][request_id]
        valid = (accepted is True and self.state["phase"] == "RAID" and request["raid_id"] == self.state["raid_id"]
                 and self.state["active_trap"] is None and isinstance(actual_instance_id, str) and bool(actual_instance_id)
                 and actual_instance_id not in self.state["temporary_instance_ids"]
                 and current_nav_revision == request["nav_revision"] and actual_safe_world_placement is True
                 and isinstance(total_objects_after, int) and not isinstance(total_objects_after, bool)
                 and 1 <= total_objects_after <= 8
                 and isinstance(total_footprint_after, int) and not isinstance(total_footprint_after, bool)
                 and math.prod(request["variant"]["footprint"]) <= total_footprint_after <= 16)
        self.state["pending_trap"] = None
        if not valid:
            state["status"] = "rejected"
            return self._result(False, "placement_rejected_token_retained")
        token = next((t for t in self.state["bank"]["FR02"] if t["token_id"] == request["token_id"]), None)
        if token is None:
            state["status"] = "rejected"
            return self._result(False, "original_token_missing")
        self.state["bank"]["FR02"].remove(token)
        state["status"] = "committed"
        self.state["acknowledged"].append(request_id)
        self.state["temporary_instance_ids"].append(actual_instance_id)
        self.state["active_trap"] = {"instance_id": actual_instance_id, "variant": deepcopy(request["variant"]),
                                     "placement": deepcopy(request["placement"]), "raid_id": self.state["raid_id"],
                                     "token_id": token["token_id"], "placed_at": self.state["now"],
                                     "armed_at": self.state["now"] + 0.5, "expires_at": self.state["now"] + 20}
        self.state["trap_deployments_this_raid"] += 1
        self.state["next_trap_deploy_at"] = self.state["now"] + 6
        return self._result(True, "temporary_world_instance_committed", trap=deepcopy(self.state["active_trap"]))

    def _remove_trap(self, reason, at):
        trap = self.state["active_trap"]
        self.state["active_trap"] = None
        return self._emit("bc01:remove:" + trap["instance_id"], "remove_temporary_trap",
                          actual_instance_id=trap["instance_id"], occurred_at=at, reason=reason, refund=0, inventory_items=0)

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
                or not trap["armed_at"] <= self.state["now"] < trap["expires_at"]):
            return self._result(False, "trap_not_armed")
        if not isinstance(pool_id, str) or not pool_id or not all(facts.get(k) is True for k in (
                "actual_new_entry", "actual_collision", "manifested", "hostile", "independent_pool", "ground_layer", "world_consumer_verified")):
            return self._result(False, "not_actual_legal_hostile_entry")
        self._record_event(event_id, data)
        request = self._emit(f"bc01:{instance_id}:trigger", "apply_temporary_trap_effect", pool_id=pool_id,
                             source_instance_id=instance_id, source_trap=trap["variant"]["source_trap"],
                             payload=deepcopy(trap["variant"]["effect"]), origin_kind="facility_secondary",
                             shared_TD05_resistance_control_and_aggregation=True, may_generate_customer_use=False,
                             may_trigger_equipment_procs=False)
        remove = self._remove_trap("single_charge_used", self.state["now"])
        return self._result(True, "one_real_entry_consumed", requests=[request, remove])

    def temporary_inventory_action(self, action, instance_id):
        if instance_id not in self.state["temporary_instance_ids"]:
            return self._result(False, "unknown_temporary_instance")
        return self._result(False, "temporary_service_trap_cannot_" + action, refund=0, inventory_items=0)

    def trap_destroyed(self, event_id, instance_id, *, actual_world_destruction=False):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        data = ["trap_destroyed", instance_id, actual_world_destruction]
        reason = self._event_state(event_id, data)
        if reason:
            return self._result(False, reason)
        trap = self.state["active_trap"]
        if not trap or trap["instance_id"] != instance_id or actual_world_destruction is not True:
            return self._result(False, "actual_instance_destruction_unproven")
        self._record_event(event_id, data)
        return self._result(True, "actual_temporary_instance_destroyed",
                            requests=[self._remove_trap("actual_world_destruction", self.state["now"])])

    def raid_ended(self, raid_id):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        if self.state["phase"] != "RAID" or raid_id != self.state["raid_id"]:
            return self._result(False, "raid_not_active")
        requests = []
        for effect in self.state["buffs"]:
            if effect["raid_id"] == raid_id:
                requests.append(self._emit(effect["effect_id"] + ":raid_end", "buff_ended", effect_id=effect["effect_id"], reason="raid_end"))
        self.state["buffs"] = [e for e in self.state["buffs"] if e["raid_id"] != raid_id]
        if self.state["active_trap"]:
            requests.append(self._remove_trap("raid_end", self.state["now"]))
        if self.state["pending_trap"]:
            self.state["trap_requests"][self.state["pending_trap"]]["status"] = "canceled"
            self.state["pending_trap"] = None
        for token in self.state["bank"]["FR02"]:
            token["eligible_raid_id"] = None
        self.state["completed_raids"].append(raid_id)
        self.state["raid_id"] = None
        self.state["phase"] = "BUSINESS"
        return self._result(True, "raid_support_closed", requests=requests)

    def night_ended(self):
        reason = self._gate()
        if reason:
            return self._result(False, reason)
        requests = self.raid_ended(self.state["raid_id"])["requests"] if self.state["phase"] == "RAID" else []
        for tokens in self.state["bank"].values():
            tokens.clear()
        self.state["survival_remaining"] = self.state["survival_progress"] = 0
        self.state["phase"] = "ENDED"
        return self._result(True, "night_facility_state_closed", requests=requests)
