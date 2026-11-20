"""Executable BC02 public customer routes; not a complete arrival/raid NPC AI.

All positive facility facts come from this reference's actual path, timed action,
immutable payment and original-object ledgers. The production adapter is closed.
"""
from __future__ import annotations
from copy import deepcopy
import hashlib
import heapq
import json
import math
from pathlib import Path

from bc01_map_reference import StoreMap
from bc02_facility_reference import FacilitiesBC02

ROOT = Path(__file__).resolve().parents[1]


def load_contract():
    return json.loads((ROOT / "content/customer_routes_bc02.json").read_text())


def canonical(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


class CustomerStoreMapBC02(StoreMap):
    """New public faces, with actual customer exclusion of employee counter sides."""
    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.customer_contract = load_contract()
        self.staff_faces = [r["rect"] for r in self.customer_contract["geometry"]["employee_faces_forbidden_to_customers"]]
        for entry in self.customer_contract["geometry"]["new_anchors"]:
            self.anchors[entry["role"]] = tuple(entry["position"])
            if not self.point_clear(entry["position"]):
                raise ValueError("new_public_face_intersects_actual_solid")
        allowed = self.contract["business_route_policy"]["normal_customer_allowed_anchors"]
        self.contract["business_route_policy"]["normal_customer_allowed_anchors"] = [
            "bc02_customer_verification" if a == "verification_desk" else a for a in allowed] + ["bc02_customer_drink_spot"]
        self.customer_nodes = {c for c in self.nodes if self.public_point((c[0] + .5, c[1] + .5))}
        self.customer_cache = {}
        self.nav_revision = "bc02-public:" + hashlib.sha256(canonical({
            "obstacles": self.obstacles, "radius": self.radius, "nodes": sorted(self.customer_nodes),
            "public_anchors": self.customer_contract["geometry"]["new_anchors"]}).encode()).hexdigest()[:20]

    def public_point(self, p):
        if p[1] < 10 or not self.point_clear(p):
            return False
        for x, y, w, h in self.staff_faces:
            distance2 = max(x-p[0], 0, p[0]-x-w)**2 + max(y-p[1], 0, p[1]-y-h)**2
            if distance2 < self.radius**2 - 1e-12:
                return False
        return True

    def route(self, start, end, *, actor="player"):
        if actor != "customer":
            return super().route(start, end, actor=actor)
        a, b = tuple(self.position(start)), tuple(self.position(end))
        if not self.public_point(a) or not self.public_point(b):
            raise ValueError("customer_cannot_use_employee_or_solid_face")
        key = (a, b)
        if key in self.customer_cache:
            return deepcopy(self.customer_cache[key])
        starts = [(c, d) for c, d in self._connectors(a, True) if c in self.customer_nodes]
        ends = {c: d for c, d in self._connectors(b, True) if c in self.customer_nodes}
        queue, distance, previous = [], {}, {}
        for cell, d in starts:
            distance[cell], previous[cell] = d, None
            heapq.heappush(queue, (d, cell))
        best, finish = float("inf"), None
        while queue:
            d, cell = heapq.heappop(queue)
            if d > distance[cell] + 1e-12 or d > best:
                continue
            if cell in ends and d + ends[cell] < best - 1e-12:
                best, finish = d + ends[cell], cell
            x, y = cell
            for nxt in ((x-1, y), (x+1, y), (x, y-1), (x, y+1)):
                if nxt not in self.customer_nodes:
                    continue
                if self.radius > .5 and not self.segment_clear((x+.5, y+.5), (nxt[0]+.5, nxt[1]+.5)):
                    continue
                if d + 1 < distance.get(nxt, float("inf")) - 1e-12:
                    distance[nxt], previous[nxt] = d + 1, cell
                    heapq.heappush(queue, (d+1, nxt))
        if finish is None:
            raise ValueError("no_actual_public_customer_path")
        cells, current = [], finish
        while current is not None:
            cells.append(current); current = previous[current]
        path = [list(a)]
        for x, y in reversed(cells):
            point = [x+.5, y+.5]
            if point != path[-1]:
                path.append(point)
        if list(b) != path[-1]:
            path.append(list(b))
        length = sum(math.dist(p, q) for p, q in zip(path, path[1:]))
        result = {"path": path, "distance": length, "distance_tiles": length, "actor": "customer",
                  "body_radius_tiles": self.radius, "body_clear": all(self.segment_clear(p, q) for p, q in zip(path, path[1:])),
                  "public_access": all(self.public_point(p) for p in path), "nav_revision": self.nav_revision}
        self.customer_cache[key] = deepcopy(result)
        return result


def reference_employer_manifest(night_id, units=None):
    """Explicit bounded initial-stock fixture, loaded once before opening."""
    quantities = units if units is not None else load_contract()["inventory"]["default_reference_units"]
    locations = {"goods": "goods_shelf", "hot_food": "hot_food", "frozen_goods": "customer_freezer",
                 "cold_drink": "cold_cabinet", "parcel_bag": "employer_preparation"}
    items = []
    for sku, count in quantities.items():
        if sku not in locations or not isinstance(count, int) or isinstance(count, bool) or count < 0:
            raise ValueError("invalid_employer_stock_fixture")
        for index in range(count):
            iid = f"employer:{night_id}:{sku}:{index+1}"
            items.append({"item_id": iid, "material_unit_id": iid, "sku": sku, "quantity": 1,
                          "owner": "employer", "state": "stock", "location": locations[sku],
                          "origin_manifest_id": f"employer:{night_id}:manifest", "source_root_id": None})
    return {"manifest_id": f"employer:{night_id}:manifest", "night_id": night_id,
            "owner": "employer", "items": items, "source": "explicit_reference_initial_stock"}


class CustomerRoutesBC02:
    def __init__(self, night_id, attempt_id, manifest, *, navigation=None, design_simulation=False):
        if (not isinstance(night_id, str) or not night_id or not isinstance(attempt_id, int)
                or isinstance(attempt_id, bool) or attempt_id < 1):
            raise ValueError("invalid_night_or_attempt")
        self.contract = load_contract()
        self.profiles = {p["id"]: p for p in self.contract["profiles"]}
        self.navigation = navigation or CustomerStoreMapBC02()
        self.design_simulation = design_simulation
        if manifest.get("night_id") != night_id or manifest.get("owner") != "employer":
            raise ValueError("wrong_actual_employer_manifest")
        items = {r["item_id"]: deepcopy(r) for r in manifest["items"]}
        if len(items) != len(manifest["items"]) or any(
                r.get("owner") != "employer" or r.get("quantity") != 1 or r.get("state") != "stock"
                or r.get("origin_manifest_id") != manifest["manifest_id"] or r.get("source_root_id") is not None
                for r in items.values()):
            raise ValueError("manifest_identity_or_ownership_invalid")
        self.state = {"night_id": night_id, "attempt_id": attempt_id, "phase": "PREP", "now": 0.,
                      "manifest_id": manifest["manifest_id"], "items": items, "preferences": [], "customer_count": 0,
                      "current": None, "completed": [], "events": [], "prepack_receipts": [],
                      "consume_receipts": [], "recycle_receipts": [], "scan_receipts": [], "verification_receipts": [],
                      "call_receipts": [], "power": {"MAIN": True, "C1": True, "C2": True, "C3": True},
                      "power_history": [], "published_use_ids": [], "prep_work_seconds": 0.,
                      "pickup_claims": {},
                      "cashier_position": self.navigation.position("cashier")}

    def _result(self, ok, reason, **extra):
        return {"ok": ok, "reason": reason, **extra}

    def _gate(self):
        return None if self.design_simulation else "actual_customer_adapter_disabled"

    def snapshot(self):
        return deepcopy(self.state)

    @classmethod
    def restore(cls, snapshot, *, navigation=None, design_simulation=False):
        empty = {"manifest_id": snapshot["manifest_id"], "night_id": snapshot["night_id"], "owner": "employer", "items": []}
        result = cls(snapshot["night_id"], snapshot["attempt_id"], empty, navigation=navigation,
                     design_simulation=design_simulation)
        result.state = deepcopy(snapshot)
        return result

    def _event(self, kind, **payload):
        sequence = len(self.state["events"]) + 1
        stream = f"bc02:{self.state['night_id']}:{self.state['attempt_id']}:route_event"
        event = {"event_id": f"bc02:{self.state['night_id']}:{self.state['attempt_id']}:route_event:{len(self.state['events'])+1}",
                 "source_event_stream_id": stream, "sequence": sequence,
                 "kind": kind, "at": self.state["now"], **deepcopy(payload)}
        self.state["events"].append(event)
        return event

    def prepare_parcel(self, goods_id, bag_id):
        if self._gate():
            return self._result(False, self._gate())
        goods, bag = (self.state["items"].get(i) for i in (goods_id, bag_id))
        if self.state["phase"] != "PREP" or not goods or not bag:
            return self._result(False, "prepack_requires_actual_prep_inputs")
        if (goods["sku"] != "goods" or bag["sku"] != "parcel_bag" or
                any(r["owner"] != "employer" or r["state"] != "stock" or r.get("source_root_id") is not None
                    for r in (goods, bag))):
            return self._result(False, "prepack_cannot_mint_or_reuse_input")
        goods.update(state="inside_parcel", parent_item_id=bag_id, location=bag_id)
        bag.update(sku="sealed_parcel", contained_source_ids=[goods_id], location="pickup_shelf")
        self.state["prep_work_seconds"] += 1.5
        receipt = self._event("employer_prepacked", input_item_ids=[goods_id, bag_id], output_existing_bag_id=bag_id,
                              actual_prep_seconds=1.5, goods_units_created=0)
        self.state["prepack_receipts"].append(receipt)
        bag["prepack_receipt_id"] = receipt["event_id"]
        return self._result(True, "original_inputs_prepacked", receipt=receipt)

    def choose_preferences(self, profile_ids):
        if self._gate():
            return self._result(False, self._gate())
        if self.state["phase"] != "PREP":
            return self._result(False, "preferences_are_pre_shift_only")
        if (not isinstance(profile_ids, list) or not profile_ids or len(set(profile_ids)) != len(profile_ids)
                or any(p not in self.profiles for p in profile_ids)):
            return self._result(False, "unregistered_profile")
        if any(len(self.profiles[p]["optional_services"]) > 2 for p in profile_ids):
            return self._result(False, "at_most_two_optional_services")
        self.state["preferences"] = list(profile_ids)
        return self._result(True, "preferences_frozen_for_opening")

    def open_business(self):
        if self._gate():
            return self._result(False, self._gate())
        if self.state["phase"] != "PREP" or not self.state["preferences"]:
            return self._result(False, "prepared_preferences_required")
        self.state["phase"] = "BUSINESS"
        return self._result(True, "business_open")

    def _powered(self, fid):
        role = self.contract["service_registry"][fid]
        return not role["powered"] or (self.state["power"]["MAIN"] and self.state["power"][role["circuit"]])

    def _power_epoch(self):
        return self.state["power_history"][-1]["event_id"] if self.state["power_history"] else "initial"

    def _continuous_action_power(self, fid, started, completed):
        role = self.contract["service_registry"][fid]
        if not role["powered"]:
            return True
        def on(power): return power["MAIN"] and power[role["circuit"]]
        return on(started["power_state"]) and all(on(p["power_state"]) for p in self.state["power_history"]
            if p["source_event_stream_id"] == started["source_event_stream_id"]
            and started["sequence"] < p["sequence"] < completed["sequence"])

    def set_power(self, circuit, on):
        if self._gate():
            return self._result(False, self._gate())
        if circuit not in self.state["power"] or not isinstance(on, bool):
            return self._result(False, "invalid_power")
        self.state["power"][circuit] = on
        event = self._event("power_changed", circuit=circuit, powered=on, power_state=self.state["power"])
        self.state["power_history"].append(event)
        customer = self.state["current"]
        if customer and customer["index"] < len(customer["plan"]):
            step = customer["plan"][customer["index"]]
            if step.get("fid") and step["fid"] != "FR01" and not self._powered(step["fid"]):
                customer["elapsed"] = 0.
                customer["action_started"] = None
                customer["action_start_event"] = None
        return self._result(True, "source_power_changed")

    def _plan(self, profile):
        plan = []
        def walk(anchor): plan.append({"kind": "walk", "anchor": anchor})
        def action(name, seconds, fid=None): plan.append({"kind": "action", "name": name, "seconds": seconds, "fid": fid})
        def service(fid, name):
            walk(self.contract["service_registry"][fid]["anchor"])
            action(name, self.contract["service_registry"][fid]["duration_s"], fid)
        walk("front_door"); action("entered", 0)
        if profile["flow"] == "product_then_pay":
            service(profile["source_facility"], "collect_product")
        walk("customer_checkout"); action("pay", 1.5, "FR01")
        if profile["flow"] == "preorder_pay_then_call_collect":
            service("FR09", "respond_to_actual_call")
            service("FR03", "collect_product")
        elif profile["flow"] == "preorder_pay_then_verify_collect":
            service("FR06", "verify_same_parcel")
            service("FR12", "collect_same_parcel")
        elif profile["extra"] == "lucky_receipt":
            service("FR14", "scan_same_receipt")
        elif profile["extra"] == "consume_here_then_return":
            walk("bc02_customer_drink_spot"); action("consume_same_drink", 2)
            service("FR11", "return_same_empty")
        elif profile["extra"] == "consume_at_public_supplies":
            service("FR13", "consume_same_drink")
        walk("customer_exit"); action("paid_exit", 0, "FR10")
        return plan

    def start_customer(self, profile_id):
        if self._gate():
            return self._result(False, self._gate())
        if self.state["phase"] != "BUSINESS" or self.state["current"]:
            return self._result(False, "ordinary_service_requires_free_business_slot")
        if profile_id not in self.state["preferences"]:
            return self._result(False, "profile_not_selected_before_shift")
        profile = self.profiles[profile_id]
        services = profile["optional_services"]
        if len(services) > 2 or len(set(services)) != len(services):
            return self._result(False, "at_most_two_optional_services")
        available = sorted(r["item_id"] for r in self.state["items"].values()
                           if r["sku"] == profile["sku"] and r["state"] == "stock" and r["owner"] == "employer")
        if not available:
            return self._result(False, "actual_employer_stock_exhausted")
        plan = self._plan(profile)
        position = "customer_spawn"
        try:
            for step in plan:
                if step["kind"] == "walk":
                    self.navigation.route(position, step["anchor"], actor="customer")
                    position = step["anchor"]
        except (KeyError, ValueError) as error:
            return self._result(False, "actual_public_route_unavailable", detail=str(error))
        self.state["customer_count"] += 1
        n = self.state["customer_count"]
        logical = json.dumps(["bc02", self.state["night_id"], "order", n], separators=(",", ":"))
        prefix = f"bc02:{self.state['night_id']}:{self.state['attempt_id']}"
        cid, oid = f"{prefix}:customer:{n}", f"{prefix}:order:{n}"
        item = self.state["items"][available[0]]
        for entry in [item, *[self.state["items"][i] for i in item.get("contained_source_ids", [])]]:
            entry.update(source_root_id=logical, reserved_by=cid)
        item["state"] = "reserved"
        self.state["current"] = {"customer_id": cid, "order_id": oid, "logical_order_id": logical,
            "logical_customer_id": json.dumps(["bc02", self.state["night_id"], "customer", n], separators=(",", ":")),
            "kind": "normal", "profile_id": profile_id, "item_id": item["item_id"], "empty_id": None,
            "position": self.navigation.position("customer_spawn"), "plan": plan, "index": 0, "path": None,
            "path_index": 0, "elapsed": 0., "action_started": None, "action_start_event": None, "walk_started": None,
            "paid_receipt": None, "operations": [], "action_receipts": [], "walk_receipts": [],
            "entry_at": None, "exit_at": None, "travel_distance": 0., "started_at": self.state["now"]}
        self.state["current"]["journey_id"] = cid + ":visit:1"
        return self._result(True, "actual_customer_reserved_original_item", customer_id=cid, item_id=item["item_id"])

    def evacuate_paid_uncollected(self):
        """OMEN callback: preserve paid original stock; physically evacuate first."""
        if self._gate():
            return self._result(False, self._gate())
        c = self.state["current"]
        if not c or not c["paid_receipt"] or self.state["phase"] != "BUSINESS":
            return self._result(False, "active_paid_customer_required")
        item = self.state["items"][c["item_id"]]
        if item["state"] != "reserved" or item["owner"] != c["customer_id"]:
            return self._result(False, "paid_uncollected_original_required")
        claim_id = c["paid_receipt"]["event_id"] + ":pickup_entitlement"
        previous_claim = self.state["pickup_claims"].get(claim_id, {})
        self.state["pickup_claims"][claim_id] = {**deepcopy(previous_claim), "claim_id": claim_id, "status": "evacuating",
            "origin_night_id": c["paid_receipt"]["night_id"], "origin_attempt_id": c["paid_receipt"]["attempt_id"],
            "customer_snapshot": deepcopy(c), "item_ids": [item["item_id"], *item.get("contained_source_ids", [])],
            "original_pickup_slot": item["location"], "second_charge": 0, "fr10_completed": False}
        item["pickup_claim_id"] = claim_id
        c.update(claim_id=claim_id, evacuation_mode=True,
                 plan=[{"kind": "walk", "anchor": "customer_exit"},
                       {"kind": "action", "name": "evacuated_unfulfilled", "seconds": 0, "fid": None, "anchor": "customer_exit"}],
                 index=0, path=None, path_index=0, elapsed=0., action_started=None, action_start_event=None)
        self.state["phase"] = "OMEN"
        return self._result(True, "paid_original_locked_for_safe_pickup", claim_id=claim_id,
                            original_item_id=item["item_id"], original_pickup_slot=item["location"])

    def resume_safe_business(self):
        if self._gate():
            return self._result(False, self._gate())
        if self.state["current"]:
            return self._result(False, "actual_evacuation_must_finish")
        self.state["phase"] = "BUSINESS"
        return self._result(True, "safe_business_resumed")

    def resume_pickup(self, claim_id):
        if self._gate():
            return self._result(False, self._gate())
        claim = self.state["pickup_claims"].get(claim_id)
        if self.state["phase"] != "BUSINESS" or self.state["current"] or not claim or claim["status"] != "awaiting_pickup":
            return self._result(False, "safe_pending_pickup_claim_required")
        c = deepcopy(claim["customer_snapshot"])
        completed = {op["facility_id"] for op in c["operations"]}
        plan = [{"kind": "walk", "anchor": "front_door"},
                {"kind": "action", "name": "entered", "seconds": 0, "fid": None}]
        services = [("FR06", "verify_same_parcel"), ("FR12", "collect_same_parcel")] if self.profiles[c["profile_id"]]["sku"] == "sealed_parcel" else [
            ("FR09", "respond_to_actual_call"), ("FR03", "collect_product")]
        for fid, action in services:
            if fid not in completed:
                role = self.contract["service_registry"][fid]
                plan += [{"kind": "walk", "anchor": role["anchor"]},
                         {"kind": "action", "name": action, "seconds": role["duration_s"], "fid": fid}]
        plan += [{"kind": "walk", "anchor": "customer_exit"},
                 {"kind": "action", "name": "paid_exit", "seconds": 0, "fid": "FR10"}]
        c.update(plan=plan, index=0, path=None, path_index=0, elapsed=0., action_started=None, action_start_event=None,
                 position=self.navigation.position("customer_spawn"), entry_at=None, exit_at=None,
                 started_at=self.state["now"], claim_id=claim_id, evacuation_mode=False,
                 journey_id=c["customer_id"] + ":visit:" + str(2 + claim.get("resume_count", 0)))
        claim["resume_count"] = claim.get("resume_count", 0) + 1
        claim["status"] = "collecting"
        self.state["current"] = c
        return self._result(True, "same_paid_order_pickup_resumed", charged_again=0,
                            reward_eligible_origin_night=claim["origin_night_id"] == self.state["night_id"])

    def export_pickup_claims(self):
        result = []
        for claim in self.state["pickup_claims"].values():
            if claim["status"] != "awaiting_pickup":
                continue
            saved = deepcopy(claim)
            saved["original_items"] = [deepcopy(self.state["items"][i]) for i in claim["item_ids"]]
            saved["prepack_receipts"] = [deepcopy(r) for r in self.state["prepack_receipts"]
                                         if r["output_existing_bag_id"] in claim["item_ids"]]
            saved["verification_receipts"] = [deepcopy(r) for r in self.state["verification_receipts"]
                                              if r["order_id"] == claim["customer_snapshot"]["order_id"]]
            result.append(saved)
        return result

    def import_pickup_claims(self, claims):
        """Load authenticated durable claim records; never creates a new sale."""
        if self._gate():
            return self._result(False, self._gate())
        if self.state["phase"] != "PREP":
            return self._result(False, "durable_claims_load_in_prep_only")
        for claim in claims:
            c = claim["customer_snapshot"]
            if (claim["status"] != "awaiting_pickup" or claim["origin_night_id"] != c["paid_receipt"]["night_id"]
                    or claim["claim_id"] != c["paid_receipt"]["event_id"] + ":pickup_entitlement"
                    or set(claim["item_ids"]) != {r["item_id"] for r in claim["original_items"]}
                    or any(r["owner"] != c["customer_id"] or r["source_root_id"] != c["logical_order_id"]
                           for r in claim["original_items"])):
                return self._result(False, "invalid_durable_original_pickup_claim")
            if any(r["item_id"] in self.state["items"] and self.state["items"][r["item_id"]] != r
                   for r in claim["original_items"]):
                return self._result(False, "durable_original_item_collision")
        for claim in claims:
            self.state["pickup_claims"][claim["claim_id"]] = deepcopy(claim)
            for item in claim["original_items"]:
                self.state["items"][item["item_id"]] = deepcopy(item)
            for key in ("prepack_receipts", "verification_receipts"):
                known = {r["event_id"] for r in self.state[key]}
                self.state[key].extend(deepcopy(r) for r in claim[key] if r["event_id"] not in known)
        return self._result(True, "original_pickup_entitlements_restored", new_sale_count=0)

    def _original(self, item_id):
        c = self.state["current"]
        item = self.state["items"].get(item_id)
        if not item or item_id != c["item_id"]:
            raise ValueError("not_same_reserved_original_item")
        if item.get("source_root_id") != c["logical_order_id"] or item.get("reserved_by") != c["customer_id"]:
            raise ValueError("original_item_cross_root_or_customer")
        return item

    def validate_action_source(self, name, item_id=None):
        c = self.state["current"]
        if not c:
            return self._result(False, "no_actual_customer")
        try:
            item = self._original(item_id if item_id is not None else c["item_id"])
            needs_paid = name in {"consume_same_drink", "return_same_empty", "verify_same_parcel", "collect_same_parcel",
                                  "respond_to_actual_call", "scan_same_receipt", "paid_exit"}
            if needs_paid and (not c["paid_receipt"] or item["owner"] != c["customer_id"]):
                raise ValueError("actual_paid_ownership_required")
            if needs_paid:
                recorded_payment = any(e["kind"] == "order_paid" and e["receipt"] == c["paid_receipt"]
                                       for e in self.state["events"])
                claim = self.state["pickup_claims"].get(c.get("claim_id"), {})
                durable_payment = claim.get("customer_snapshot", {}).get("paid_receipt") == c["paid_receipt"]
                if not recorded_payment and not durable_payment:
                    raise ValueError("actual_recorded_payment_required")
            if name == "pay" and (c["entry_at"] is None or c["paid_receipt"] or item["owner"] != "employer"):
                raise ValueError("invalid_original_payment_state")
            if name == "collect_product" and (item["state"] != "reserved" or item["sku"] == "sealed_parcel"):
                raise ValueError("original_product_not_in_pickup_slot")
            if name == "collect_product":
                fid = self.profiles[c["profile_id"]]["source_facility"]
                if item["location"] != self.contract["service_registry"][fid]["anchor"]:
                    raise ValueError("original_stock_not_at_actual_service_slot")
            if name == "consume_same_drink" and (item["sku"] != "cold_drink" or item["state"] != "held"
                                                  or item["location"] != c["customer_id"]):
                raise ValueError("same_paid_full_drink_required")
            if name == "return_same_empty":
                empty = self.state["items"].get(c.get("empty_id"))
                if (not empty or empty["state"] != "held_empty" or empty["owner"] != c["customer_id"]
                        or empty["location"] != c["customer_id"]
                        or empty.get("source_root_id") != c["logical_order_id"] or empty.get("parent_item_id") != item["item_id"]
                        or empty.get("material_unit_id") != item["material_unit_id"]):
                    raise ValueError("same_order_derived_empty_container_required")
                if not any(r["event_id"] == empty["consume_receipt_id"] and r["actual_seconds"] >= 2
                           and r["source_item_id"] == item["item_id"] and r["customer_id"] == c["customer_id"]
                           for r in self.state["consume_receipts"]):
                    raise ValueError("actual_completed_consumption_required")
            if name in {"verify_same_parcel", "collect_same_parcel"}:
                if item["sku"] != "sealed_parcel" or item["state"] != "reserved":
                    raise ValueError("original_prepacked_parcel_required")
                if item["location"] != "pickup_shelf":
                    raise ValueError("original_parcel_not_at_public_pickup_slot")
                if not any(r["event_id"] == item.get("prepack_receipt_id") and r["output_existing_bag_id"] == item["item_id"]
                           for r in self.state["prepack_receipts"]):
                    raise ValueError("employer_prepack_receipt_required")
                for child_id in item["contained_source_ids"]:
                    child = self.state["items"][child_id]
                    if (child["state"] != "inside_parcel" or child["parent_item_id"] != item["item_id"]
                            or child["source_root_id"] != c["logical_order_id"] or child["owner"] != c["customer_id"]):
                        raise ValueError("parcel_content_cross_root_or_missing")
            if name == "collect_same_parcel" and not any(
                    r["source_item_id"] == item["item_id"] and r["order_id"] == c["order_id"]
                    and r["customer_id"] == c["customer_id"] for r in self.state["verification_receipts"]):
                raise ValueError("actual_same_parcel_verification_required")
            if name == "scan_same_receipt" and any(r["paid_receipt_id"] == c["paid_receipt"]["event_id"]
                                                   for r in self.state["scan_receipts"]):
                raise ValueError("same_receipt_already_scanned")
            return self._result(True, "original_source_verified")
        except (ValueError, KeyError) as error:
            return self._result(False, str(error))

    def _finish_action(self, step):
        c = self.state["current"]
        name, fid = step["name"], step.get("fid")
        checked = self.validate_action_source(name)
        if not checked["ok"]:
            return checked
        item = self.state["items"][c["item_id"]]
        action = self._event("customer_action_completed", action=name, customer_id=c["customer_id"], order_id=c["order_id"],
                             logical_root_id=c["logical_order_id"], position=c["position"], actual_seconds=c["elapsed"],
                             source_item_id=item["item_id"], nav_revision=self.navigation.nav_revision,
                             started_event=c["action_start_event"], power_epoch_at_completion=self._power_epoch())
        c["action_receipts"].append(action)
        if name == "entered":
            c["entry_at"] = self.state["now"]
        elif name in {"collect_product", "collect_same_parcel"}:
            item.update(state="held", location=c["customer_id"])
        elif name == "pay":
            if c["entry_at"] is None or c["paid_receipt"] or item["owner"] != "employer":
                return self._result(False, "invalid_original_payment_state")
            for entry in [item, *[self.state["items"][i] for i in item.get("contained_source_ids", [])]]:
                entry["owner"] = c["customer_id"]
            c["paid_receipt"] = {"event_id": c["order_id"] + ":paid", "order_id": c["order_id"],
                "customer_id": c["customer_id"], "logical_order_id": c["logical_order_id"],
                "logical_customer_id": c["logical_customer_id"], "night_id": self.state["night_id"],
                "attempt_id": self.state["attempt_id"], "paid": True, "verified": True,
                "normal_customer": c["kind"] == "normal", "payment_kind": "ordinary_store_sale",
                "completed_at": self.state["now"], "coin": 6, "xp": 8,
                "items": [{"sku": item["sku"], "source_item_id": item["item_id"], "quantity": 1,
                           "facility_id": self.profiles[c["profile_id"]]["source_facility"],
                           "contained_source_ids": deepcopy(item.get("contained_source_ids", []))}],
                "physical_entry_at": c["entry_at"], "facilities_used": [], "actual_action_receipts": []}
            self._event("order_paid", receipt=c["paid_receipt"])
        elif name == "consume_same_drink":
            empty_id = item["item_id"] + ":empty:1"
            if empty_id in self.state["items"]:
                return self._result(False, "same_material_container_already_derived")
            item.update(state="consumed", derived_empty_id=empty_id)
            receipt = self._event("same_drink_consumed", source_item_id=item["item_id"], derived_empty_id=empty_id,
                                  customer_id=c["customer_id"], order_id=c["order_id"], actual_seconds=c["elapsed"],
                                  logical_root_id=c["logical_order_id"], reward_facility=fid)
            self.state["consume_receipts"].append(receipt)
            self.state["items"][empty_id] = {"item_id": empty_id, "sku": "empty_container", "quantity": 1,
                "material_unit_id": item["material_unit_id"], "parent_item_id": item["item_id"],
                "owner": c["customer_id"], "state": "held_empty", "location": c["customer_id"],
                "source_root_id": c["logical_order_id"], "consume_receipt_id": receipt["event_id"],
                "origin_manifest_id": item["origin_manifest_id"]}
            c["empty_id"] = empty_id
        elif name == "return_same_empty":
            empty = self.state["items"][c["empty_id"]]
            receipt = self._event("same_empty_recycled", source_item_id=empty["item_id"], parent_item_id=item["item_id"],
                                  customer_id=c["customer_id"], order_id=c["order_id"], owner_before=empty["owner"],
                                  logical_root_id=c["logical_order_id"], refund=0, restocked_sale_units=0)
            self.state["recycle_receipts"].append(receipt)
            empty.update(state="recycled_non_sale", owner="employer_waste", location="customer_return")
        elif name == "verify_same_parcel":
            self.state["verification_receipts"].append(deepcopy(action))
        elif name == "scan_same_receipt":
            receipt = self._event("paid_receipt_scanned", paid_receipt_id=c["paid_receipt"]["event_id"],
                                  customer_id=c["customer_id"], order_id=c["order_id"], logical_root_id=c["logical_order_id"])
            self.state["scan_receipts"].append(receipt)
        elif name == "respond_to_actual_call":
            call = next((r for r in reversed(self.state["call_receipts"]) if r["order_id"] == c["order_id"]
                         and r["customer_id"] == c["customer_id"]), None)
            if call is None or call["at"] > self.state["now"] - c["elapsed"] + 1e-8:
                return self._result(False, "actual_owned_order_call_required")
        elif name == "paid_exit":
            if (c["position"] != self.navigation.position("customer_exit") or not c["walk_receipts"]
                    or c["walk_receipts"][-1]["distance"] <= 0 or c["walk_receipts"][-1]["to"] != "customer_exit"):
                return self._result(False, "actual_paid_exit_crossing_required")
            c["exit_at"] = self.state["now"]
            if c.get("claim_id"):
                self.state["pickup_claims"][c["claim_id"]].update(status="collected", fr10_completed=True)
        elif name == "evacuated_unfulfilled":
            if c["position"] != self.navigation.position("customer_exit"):
                return self._result(False, "actual_evacuation_exit_required")
            c["exit_at"] = self.state["now"]
            claim = self.state["pickup_claims"][c["claim_id"]]
            claim.update(status="awaiting_pickup", customer_snapshot=deepcopy(c))
        if fid and self._continuous_action_power(fid, c["action_start_event"], action):
            source = c["empty_id"] if fid == "FR11" else item["item_id"]
            c["operations"].append({"facility_id": fid, "usage_kind": self.contract["service_registry"][fid]["usage_kind"],
                "source_item_id": source, "actual_use_at": self.state["now"], "duration_s": c["elapsed"],
                "position": deepcopy(c["position"]), "action_receipt_id": action["event_id"],
                "nav_revision": self.navigation.nav_revision, "source_root_id": c["logical_order_id"]})
        return self._result(True, "actual_action_completed")

    def advance(self, seconds, *, paused=False):
        if self._gate():
            return self._result(False, self._gate())
        if (not isinstance(seconds, (float, int)) or isinstance(seconds, bool) or not math.isfinite(seconds)
                or seconds < 0 or not isinstance(paused, bool)):
            return self._result(False, "invalid_world_step")
        if paused:
            return self._result(True, "actual_world_paused")
        if self.state["phase"] != "BUSINESS" and not (
                self.state["phase"] == "OMEN" and self.state["current"] and self.state["current"].get("evacuation_mode")):
            return self._result(False, "ordinary_plan_requires_business_phase")
        remaining = seconds
        while self.state["current"] is not None and remaining > 1e-10:
            c = self.state["current"]
            step = c["plan"][c["index"]]
            if step["kind"] == "walk":
                if c["path"] is not None and c["path"]["nav_revision"] != self.navigation.nav_revision:
                    return self._result(False, "live_navigation_changed_requires_replan")
                if c["path"] is None:
                    try:
                        route = self.navigation.route(c["position"], step["anchor"], actor="customer")
                    except ValueError as error:
                        return self._result(False, str(error))
                    c["path"], c["path_index"], c["walk_started"] = route, 1, self.state["now"]
                path = c["path"]["path"]
                if c["path_index"] < len(path):
                    target = path[c["path_index"]]
                    length = math.dist(c["position"], target)
                    distance = min(length, 2.4 * remaining)
                    if distance > 0:
                        previous = list(c["position"])
                        c["position"] = [a+(b-a)*distance/length for a, b in zip(previous, target)]
                        spent = distance/2.4
                        remaining -= spent; self.state["now"] += spent; c["travel_distance"] += distance
                    if distance < length - 1e-9:
                        continue
                    c["position"] = list(target); c["path_index"] += 1
                    if c["path_index"] < len(path):
                        continue
                receipt = {"to": step["anchor"], "started_at": c["walk_started"], "completed_at": self.state["now"],
                           **deepcopy(c["path"])}
                c["walk_receipts"].append(receipt)
                c["path"] = None
            else:
                fid = step.get("fid")
                if fid and fid != "FR01" and not self._powered(fid):
                    c["elapsed"], c["action_started"] = 0., None
                    c["action_start_event"] = None
                    self.state["now"] += remaining
                    return self._result(False, "actual_service_source_unpowered")
                checked = self.validate_action_source(step["name"])
                if not checked["ok"]:
                    return checked
                expected = self.contract["service_registry"][fid]["anchor"] if fid else step.get("anchor", (
                    "front_door" if step["name"] == "entered" else "bc02_customer_drink_spot"))
                if c["position"] != self.navigation.position(expected) or not self.navigation.public_point(c["position"]):
                    return self._result(False, "actual_service_public_geometry_mismatch")
                if step["name"] == "pay" and self.state["cashier_position"] != self.navigation.position("cashier"):
                    return self._result(False, "actual_cashier_not_at_own_control")
                if c["action_started"] is None:
                    c["action_started"] = self.state["now"]
                    c["action_start_event"] = self._event("customer_action_started", action=step["name"],
                        customer_id=c["customer_id"], order_id=c["order_id"], source_item_id=c["item_id"],
                        position=c["position"], power_epoch_id=self._power_epoch(), power_state=self.state["power"])
                    if step["name"] == "respond_to_actual_call":
                        self.state["call_receipts"].append(self._event("actual_order_called", order_id=c["order_id"],
                            customer_id=c["customer_id"], paid_receipt_id=c["paid_receipt"]["event_id"],
                            source_position=self.navigation.position("customer_wait"), listener_position=c["position"]))
                spent = min(remaining, step["seconds"] - c["elapsed"])
                c["elapsed"] += spent; remaining -= spent; self.state["now"] += spent
                if c["elapsed"] < step["seconds"] - 1e-9:
                    continue
                result = self._finish_action(step)
                if not result["ok"]:
                    return result
            c["index"] += 1; c["elapsed"] = 0.; c["action_started"] = None; c["action_start_event"] = None
            if c["index"] == len(c["plan"]):
                c["finished_at"] = self.state["now"]
                self.state["completed"].append(deepcopy(c)); self.state["current"] = None
        self.state["now"] += remaining
        return self._result(True, "actual_customer_world_advanced")

    def run_customer(self, profile_id, *, max_seconds=240):
        started = self.start_customer(profile_id)
        if not started["ok"]:
            return started
        until = self.state["now"] + max_seconds
        while self.state["current"] is not None and self.state["now"] < until:
            result = self.advance(.25)
            if not result["ok"]:
                return result
        return self._result(self.state["current"] is None, "actual_route_completed" if self.state["current"] is None else "route_time_budget_exceeded")

    def build_use_requests(self, completed_customer):
        c = completed_customer
        recorded = next((r for r in self.state["completed"] if r["journey_id"] == c.get("journey_id")), None)
        if recorded is None or recorded != c:
            raise ValueError("only_own_recorded_completed_journey_is_authoritative")
        paid = deepcopy(c["paid_receipt"])
        if not paid or c["exit_at"] is None:
            raise ValueError("completed_paid_route_required")
        if paid["night_id"] != self.state["night_id"] or paid["attempt_id"] != self.state["attempt_id"]:
            return []  # Free old-order fulfilment never mints current-night support.
        paid["facilities_used"] = [{k: op[k] for k in ("facility_id", "actual_use_at", "usage_kind", "source_item_id")}
                                  for op in c["operations"]]
        paid["actual_action_receipts"] = deepcopy(c["action_receipts"])
        result = []
        for op in c["operations"]:
            fid = op["facility_id"]
            role = self.contract["service_registry"].get(fid)
            action = next((r for r in c["action_receipts"] if r["event_id"] == op["action_receipt_id"]), None)
            item = self.state["items"].get(op["source_item_id"])
            correct_root = bool(item and item.get("source_root_id") == c["logical_order_id"] == op["source_root_id"])
            owned = bool(item and item["owner"] == c["customer_id"])
            if fid == "FR11":
                owned = any(r["source_item_id"] == op["source_item_id"] and r["owner_before"] == c["customer_id"]
                            and r["logical_root_id"] == c["logical_order_id"] for r in self.state["recycle_receipts"])
            geometry = bool(role and action and op["nav_revision"] == self.navigation.nav_revision
                            and op["position"] == self.navigation.position(role["anchor"])
                            and self.navigation.public_point(op["position"]))
            progress = bool(action and action["actual_seconds"] >= role["duration_s"] - 1e-9
                            and action["position"] == op["position"] and action["at"] == op["actual_use_at"])
            authorized = fid in {"FR01", "FR10"} or fid in self.profiles[c["profile_id"]]["optional_services"]
            if not all((correct_root, owned, geometry, progress, authorized, c["kind"] == "normal")):
                raise ValueError("actual_route_source_proof_failed:" + fid)
            result.append({"event_id": paid["event_id"] + ":facility:" + fid, "customer_id": c["customer_id"],
                "facility_id": fid, "paid_order_receipt": deepcopy(paid), "night_id": self.state["night_id"],
                "attempt_id": self.state["attempt_id"], "facts": {
                    "normal_customer": c["kind"] == "normal", "customer_kind": c["kind"],
                    "actual_use_completed": progress, "consumer_registered": fid in self.contract["service_registry"],
                    "facility_geometry_bound": geometry, "same_order_service": correct_root,
                    "source_item_owner_customer": owned, "route_service_authorized": authorized,
                    "progress_complete": progress, "usage_kind": role["usage_kind"],
                    "actual_use_at": op["actual_use_at"], "use_duration_s": op["duration_s"],
                    "actual_use_started_at": action["started_event"]["at"],
                    "source_event_stream_id": action["source_event_stream_id"],
                    "action_started_sequence": action["started_event"]["sequence"],
                    "action_completed_sequence": action["sequence"],
                    "power_epoch_at_start": action["started_event"]["power_epoch_id"],
                    "power_epoch_at_completion": action["power_epoch_at_completion"],
                    "source_item_id": op["source_item_id"], "origin_kind": "actual_customer_use",
                    "exit_boundary_crossed": fid == "FR10" and c["exit_at"] == op["actual_use_at"],
                    "actual_action_receipt_id": op["action_receipt_id"], "source_root_id": op["source_root_id"],
                    "actual_public_anchor": role["anchor"], "nav_revision": op["nav_revision"]}})
        return result

    def publish_to_facilities(self, facilities):
        if self._gate():
            return self._result(False, self._gate())
        if (facilities.state["night_id"] != self.state["night_id"] or facilities.state["attempt_id"] != self.state["attempt_id"]
                or facilities.state["now"] > self.state["now"]):
            return self._result(False, "facility_owner_scope_or_clock_mismatch")
        for power in self.state["power_history"]:
            if power["at"] < facilities.state["now"]:
                continue
            facilities.actual_world_tick("route-sync:" + power["event_id"], power["at"], True)
            result = facilities.power_changed(power["event_id"], power["circuit"], power["powered"],
                source_event_stream_id=power["source_event_stream_id"], source_sequence=power["sequence"])
            if not result["ok"] and result["reason"] != "event_replay":
                return result
        facilities.actual_world_tick("route-sync-final:" + str(self.state["now"]), self.state["now"], True)
        accepted = []
        for c in self.state["completed"]:
            for request in self.build_use_requests(c):
                if request["event_id"] in self.state["published_use_ids"]:
                    continue
                result = facilities.customer_use(**request)
                if not result["ok"]:
                    return self._result(False, "actual_facility_consumer_rejected", result=result, facility_id=request["facility_id"])
                self.state["published_use_ids"].append(request["event_id"])
                accepted.append({"facility_id": request["facility_id"], "result": result["reason"],
                                 "event_id": request["event_id"], "proof_facts": request["facts"]})
        return self._result(True, "actual_completed_routes_published", accepted=accepted)
