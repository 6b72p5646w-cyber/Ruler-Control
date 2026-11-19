/**
 * Finite consumer/benefit reference. Engine adapters provide actual admission,
 * work, observations, delivery and handover facts. Matching those declared facts
 * does not authenticate a physical action or a person. No AI, navigation, RNG,
 * full shop, persistence, daytime engine or global panic controller is supplied.
 */
const clone = x => structuredClone(x);
const yes = x => ({ok: true, ...x});
const no = reason => ({ok: false, reason});
const named = x => typeof x === 'string' && x.length > 0;
const finite = x => typeof x === 'number' && Number.isFinite(x);
const sameIds = (a, b) => Array.isArray(a) && a.length === b.length &&
  new Set(a).size === a.length && [...a].sort().every((x, i) => x === [...b].sort()[i]);
const bindingNames = {
  F23: ['coat', 'claimant', 'gift'], F29: ['porridge', 'butter', 'gift'],
  F33: ['visitor', 'aid'], F35: ['garbage', 'broom', 'work'], F36: ['slot'],
  F47: ['segment1', 'segment2', 'segment3'], F53: ['bottle1', 'bottle2', 'container'],
  F55: ['route', 'player', 'item'],
};
const automaticPredicates = new Set(['full_lease_elapsed', 'lease_revoked_on_time',
  'true_six_reached', 'same_two_bottles_sealed_in_reserved_container', 'verified_handover_completed',
  'same_registered_garbage_point_actually_cleaned']);

function specFor(s, e, rewardKey) {
  return s.contract.friendly_benefits.benefits.find(x => x.monster_id === e.monsterId && x.reward_key === rewardKey);
}
function receipt(s, id, kind, fields = {}) {
  if (!named(id) || s.receipts[id]) return null;
  const r = {id, kind, runId: s.runId, nightId: s.nightId, sequence: ++s.sequence,
    world: s.world, budget: s.budget, ...fields};
  s.receipts[id] = r; return r;
}
function nextReceipt(s, prefix, kind, fields = {}) {
  return receipt(s, `${prefix}:${s.sequence + 1}`, kind, fields);
}
function resource(s, key, amount) {
  const before = s.resources[key];
  s.resources[key] = Math.min(s.resourceCaps[key], Math.max(0, before + amount));
  return s.resources[key] - before;
}
function addFact(s, e, rewardKey, predicate, r) {
  (e.facts[rewardKey] ??= {})[predicate] = r.id;
}
function objectsFor(e, key, predicate) {
  const b = e.bindings;
  const fixed = {
    matched_coat_actually_returned: [b.coat, b.claimant], claimant_departed: [b.claimant],
    declared_gift_actually_claimed: [b.gift], same_porridge_and_visible_butter_delivered: [b.porridge, b.butter],
    visitor_first_aid_actually_delivered: [b.visitor, b.aid], same_visitor_departed: [b.visitor],
    same_broom_returned: [b.broom], actual_lease_granted: [b.slot],
    same_leased_slot_actually_cleared: [b.slot], actual_promise_accepted: [b.bottle1, b.bottle2, b.container],
    actual_escort_accepted: [b.route, b.player, b.item], same_registered_route_completed: [b.route, b.player, b.item],
    player_and_remaining_item_returned_to_store: [b.player, b.item],
  };
  if (predicate.startsWith('same_segment_')) return [b[`segment${key.slice(-1)}`]];
  return fixed[predicate] ?? [];
}

export function createConsumerState(contract, itemData, options = {}) {
  if (!contract?.food_verification || !contract?.friendly_benefits) throw new Error('consumer_contract_required');
  return {contract: clone(contract), items: Object.fromEntries(itemData.items.map(x => [x.id, clone(x)])),
    runId: options.runId ?? 'night-run', nightId: options.nightId ?? 'night-1',
    world: 0, budget: 0, sequence: 0, resources: {san: 50, energy: 50, satiety: 50, ...options.resources},
    resourceCaps: {san: 100, energy: 100, satiety: 100, ...options.resourceCaps}, coins: options.coins ?? 0,
    transferItemIds: [...(options.transferItemIds ?? [])], foodInspectionImplemented: options.foodInspectionImplemented === true,
    encounters: {}, rootOwners: {}, inventory: {}, receipts: {}, supplierBatches: {}, inspections: {}, activeInspection: null,
    context: {anchor: null, slotItemId: null, activeChase: false}, workReceipts: {}, workCredits: {},
    handover: null, restEpisodes: {}, restReservations: {},
    pet: clone(options.pet ?? {id: 'P08', prepared: false, cared: false, charges: 0})};
}

export function registerBenefitEncounter(s, {id, monsterId, rootRewardId, bindings, saleableBottleIds = [], storageSlots = []}) {
  const names = bindingNames[monsterId];
  if (!names || !named(id) || !named(rootRewardId) || s.encounters[id] || s.rootOwners[rootRewardId] || !bindings ||
      names.some(k => !named(bindings[k])) || new Set(names.map(k => bindings[k])).size !== names.length) return no('invalid_declared_encounter');
  const gift = s.contract.friendly_benefits.benefits.find(x => x.monster_id === monsterId && x.kind === 'item');
  if (gift && (s.inventory[bindings.gift] || !s.transferItemIds.includes(gift.item_id) ||
      !s.items[gift.item_id]?.acquisition_enabled || !s.items[gift.item_id]?.reward_enabled)) return no('gift_handler_or_policy_unavailable');
  if (gift && s.contract.food_verification.edible_item_ids.includes(gift.item_id) && !s.foodInspectionImplemented) return no('food_inspection_handler_unavailable');
  if (monsterId === 'F53') {
    const ids = [bindings.bottle1, bindings.bottle2, ...saleableBottleIds];
    if (saleableBottleIds.length !== s.contract.f53_preserved_stock.fixed_saleable ||
        ids.some(x => !named(x) || s.inventory[x]) || new Set(ids).size !== s.contract.f53_preserved_stock.fixed_total ||
        !storageSlots.includes(bindings.container) || storageSlots.some(x => !named(x))) return no('invalid_f53_finite_stock');
  }
  const e = {id, monsterId, rootRewardId, bindings: clone(bindings), facts: {}, rewards: {}, cancelled: false};
  s.encounters[id] = e; s.rootOwners[rootRewardId] = id;
  if (gift) s.inventory[bindings.gift] = {id: bindings.gift, itemId: gift.item_id, encounterId: id,
    rootRewardId, owned: false, consumed: false, lockedBy: null, source: 'guest_gift',
    foodStatus: s.contract.food_verification.guest_gift_initial_status, presentedAtBudget: null};
  if (monsterId === 'F53') {
    e.storageSlots = [...new Set(storageSlots)]; e.containerSealed = false; e.dawnSnapshot = null;
    for (const itemId of [bindings.bottle1, bindings.bottle2, ...saleableBottleIds]) {
      s.inventory[itemId] = {id: itemId, itemId: 'I20', encounterId: id, rootRewardId,
        owned: true, consumed: false, sold: false, slot: null, source: 'declared_f53_stock',
        foodStatus: 'sealed_unverified', reservedBy: [bindings.bottle1, bindings.bottle2].includes(itemId) ? id : null};
    }
  }
  return yes({encounterId: id});
}

export function presentDeclaredGift(s, {encounterId, itemInstanceId, itemId, batchId, productClass}) {
  const e = s.encounters[encounterId], item = s.inventory[itemInstanceId];
  if (!e || e.cancelled || e.bindings.gift !== itemInstanceId || !item || item.itemId !== itemId || item.presentedAtBudget !== null) return no('not_declared_unpresented_gift');
  item.presentedAtBudget = s.budget; item.productClass = productClass; item.batchId = batchId;
  const r = nextReceipt(s, 'gift-presented', 'actual_gift_presented', {encounterId, rootRewardId: e.rootRewardId, objectIds: [itemInstanceId]});
  return yes({receiptId: r.id});
}

export function recordBenefitFact(s, {receiptId, encounterId, rootRewardId, rewardKey, predicate, objectIds}) {
  const e = s.encounters[encounterId], spec = e && specFor(s, e, rewardKey);
  if (!e || e.cancelled || e.rootRewardId !== rootRewardId || !spec || e.rewards[rewardKey] ||
      !spec.requires.includes(predicate) || automaticPredicates.has(predicate)) return no('not_a_declared_unsettled_fact');
  if (spec.previous_claim_key && !e.rewards[spec.previous_claim_key]) return no('previous_segment_not_claimed');
  if (!sameIds(objectIds, objectsFor(e, rewardKey, predicate)) || e.facts[rewardKey]?.[predicate]) return no('wrong_object_or_duplicate_predicate');
  if (predicate === 'declared_gift_actually_claimed' && s.inventory[e.bindings.gift]?.presentedAtBudget === null) return no('gift_not_actually_presented');
  if (predicate === 'same_leased_slot_actually_cleared' && e.lease?.state !== 'revoked_on_time') return no('lease_not_fully_elapsed_and_revoked');
  if (predicate === 'actual_promise_accepted' && (s.budget >= 720 || [e.bindings.bottle1, e.bindings.bottle2].some(id => !s.inventory[id]?.owned || s.inventory[id].reservedBy !== e.id))) return no('promised_originals_unavailable');
  const r = receipt(s, receiptId, 'actual_benefit_fact', {encounterId, rootRewardId, rewardKey, predicate, objectIds: [...objectIds]});
  if (!r) return no('receipt_id_already_used');
  addFact(s, e, rewardKey, predicate, r);
  if (predicate === 'actual_lease_granted') e.lease = {state: 'active', startWorld: s.world, endWorld: s.world + spec.lease_world_seconds};
  if (predicate === 'declared_gift_actually_claimed') s.inventory[e.bindings.gift].claimReceiptId = r.id;
  return yes({receiptId: r.id});
}

export function completeExistingCleaningWork(s, {receiptId, encounterId, rootRewardId, workId, garbageId}) {
  const e = s.encounters[encounterId];
  if (!e || e.monsterId !== 'F35' || e.cancelled || rootRewardId !== e.rootRewardId ||
      workId !== e.bindings.work || garbageId !== e.bindings.garbage || s.workCredits[workId]) return no('not_same_pending_cleaning_work');
  const r = receipt(s, receiptId, 'actual_existing_work_completed', {encounterId, rootRewardId, workId, objectIds: [garbageId]});
  if (!r) return no('receipt_id_already_used');
  s.workReceipts[r.id] = r; s.workCredits[workId] = r.id;
  addFact(s, e, 'cleaning', 'same_registered_garbage_point_actually_cleaned', r);
  return yes({receiptId: r.id, addedWorkCredits: 1});
}

export function revokeLeaseEarly(s, encounterId) {
  const e = s.encounters[encounterId];
  if (!e?.lease || e.lease.state !== 'active') return no('no_active_lease');
  e.lease.state = 'revoked_early'; e.lease.revokedAt = s.world;
  return yes({reward: 0});
}

function cancelInspection(s, reason) {
  const a = s.inspections[s.activeInspection];
  if (!a || a.state !== 'running') return false;
  a.state = 'cancelled'; a.reason = reason;
  if (s.inventory[a.itemInstanceId]?.lockedBy === a.id) s.inventory[a.itemInstanceId].lockedBy = null;
  s.activeInspection = null; return true;
}

function inspectionContextValid(s, itemId) {
  return s.contract.food_verification.inspection_anchors.includes(s.context.anchor) &&
    s.context.slotItemId === itemId && !s.context.activeChase;
}

export function updateConsumerContext(s, context) {
  s.context = {...s.context, ...context};
  const a = s.inspections[s.activeInspection];
  if (a && !inspectionContextValid(s, a.itemInstanceId)) cancelInspection(s, 'actual_inspection_context_changed');
}

export function advanceConsumerClock(s, {worldSeconds = 0, budgetCost = 0, paused = false} = {}) {
  if (![worldSeconds, budgetCost].every(x => finite(x) && x >= 0) || (worldSeconds > 0 && budgetCost > 0)) return no('invalid_clock_step');
  if (paused || s.budget >= 720) return yes({advancedWorld: 0});
  if (budgetCost > 720 - s.budget) return no('budget_cost_crosses_true_six');
  const beforeWorld = s.world, beforeBudget = s.budget;
  const advancedWorld = Math.min(worldSeconds, 720 - s.budget);
  s.world += advancedWorld; s.budget += advancedWorld + budgetCost;
  for (const e of Object.values(s.encounters)) {
    if (e.lease?.state === 'active' && s.world >= e.lease.endWorld) {
      e.lease.state = 'revoked_on_time'; e.lease.revokedAt = e.lease.endWorld;
      for (const predicate of ['full_lease_elapsed', 'lease_revoked_on_time']) {
        const r = nextReceipt(s, predicate, 'actual_lease_timer_transition', {encounterId: e.id,
          rootRewardId: e.rootRewardId, world: e.lease.endWorld,
          budget: beforeBudget + (e.lease.endWorld - beforeWorld), objectIds: [e.bindings.slot]});
        addFact(s, e, 'rent', predicate, r);
      }
    }
    if (e.monsterId === 'F53' && e.dawnSnapshot === null && beforeBudget < 720 && s.budget === 720) {
      const b = e.bindings, originals = [b.bottle1, b.bottle2];
      const qualified = !e.cancelled && Boolean(e.facts.dawn?.actual_promise_accepted) && e.containerSealed &&
        originals.every(id => s.inventory[id]?.owned && !s.inventory[id].consumed && s.inventory[id].reservedBy === e.id && s.inventory[id].slot === b.container);
      e.dawnSnapshot = {budget: 720, qualified, promisedBottleIds: originals, containerId: b.container};
      const r = nextReceipt(s, 'true-six', 'true_six_qualification_snapshot', {encounterId: e.id, rootRewardId: e.rootRewardId, snapshot: clone(e.dawnSnapshot)});
      addFact(s, e, 'dawn', 'true_six_reached', r);
      if (qualified) addFact(s, e, 'dawn', 'same_two_bottles_sealed_in_reserved_container', r);
      for (const id of originals) if (s.inventory[id].reservedBy === e.id) s.inventory[id].reservedBy = null;
    }
  }
  if (s.budget === 720) cancelInspection(s, 'night_world_closed');
  return yes({advancedWorld});
}

export function registerSupplierBatch(s, {id, runId, itemId, batchId, createdAtBudget, producerKind, committed}) {
  if (!named(id) || s.supplierBatches[id] || runId !== s.runId || !named(batchId) || !s.items[itemId] ||
      !finite(createdAtBudget) || createdAtBudget > Math.min(0, s.budget) || producerKind !== 'actual_pre_shift_supplier_record' || committed !== true) return no('not_actual_current_supplier_record');
  s.supplierBatches[id] = {id, runId, itemId, batchId, createdAtBudget, producerKind};
  return yes({recordId: id});
}

export function beginFoodInspection(s, {inspectionId, itemInstanceId}) {
  const item = s.inventory[itemInstanceId], c = s.contract.food_verification;
  if (!named(inspectionId) || s.inspections[inspectionId] || s.activeInspection || !s.foodInspectionImplemented ||
      !item?.owned || item.consumed || item.lockedBy || item.reservedBy || !(c.inspectable_item_ids ?? c.edible_item_ids).includes(item.itemId) ||
      item.foodStatus !== c.guest_gift_initial_status || !inspectionContextValid(s, itemInstanceId) ||
      s.budget + c.inspection_world_seconds > 720) return no('inspection_unavailable');
  s.inspections[inspectionId] = {id: inspectionId, itemInstanceId, startedWorld: s.world,
    endWorld: s.world + c.inspection_world_seconds, state: 'running'};
  s.activeInspection = inspectionId; item.lockedBy = inspectionId;
  return yes({inspectionId});
}

export function cancelFoodInspection(s, inspectionId) {
  if (s.activeInspection !== inspectionId) return no('inspection_not_running');
  cancelInspection(s, 'player_cancelled'); return yes({});
}

export function finishFoodInspection(s, {inspectionId, observedItemId, observedSealIntact, observedBatchId, supplierRecordId}) {
  const a = s.inspections[inspectionId], item = a && s.inventory[a.itemInstanceId];
  if (!a || a.state !== 'running' || s.activeInspection !== inspectionId || !item?.owned || item.lockedBy !== inspectionId) return no('inspection_not_running');
  if (s.world < a.endWorld) return no('three_world_seconds_not_completed');
  const batch = s.supplierBatches[supplierRecordId], claim = s.receipts[item.claimReceiptId];
  const valid = inspectionContextValid(s, item.id) && observedItemId === item.id && observedSealIntact === true &&
    item.productClass === 'factory_sealed_known_catalog_product' && named(item.batchId) && observedBatchId === item.batchId &&
    batch?.runId === s.runId && batch.itemId === item.itemId && batch.batchId === item.batchId &&
    batch.createdAtBudget < item.presentedAtBudget && claim?.predicate === 'declared_gift_actually_claimed' &&
    claim.encounterId === item.encounterId && claim.rootRewardId === item.rootRewardId && sameIds(claim.objectIds, [item.id]);
  if (!valid) { cancelInspection(s, 'provenance_or_same_item_mismatch'); return no('provenance_or_same_item_mismatch'); }
  item.foodStatus = s.contract.food_verification.success_status; item.lockedBy = null;
  a.state = 'completed'; s.activeInspection = null;
  const r = nextReceipt(s, 'food-verified', 'actual_food_inspection_completed', {objectIds: [item.id], claimReceiptId: claim.id, supplierRecordId});
  return yes({receiptId: r.id, foodStatus: item.foodStatus});
}

export function consumeVerifiedFood(s, itemInstanceId) {
  const item = s.inventory[itemInstanceId], c = s.contract.food_verification, definition = item && s.items[item.itemId];
  if (!item?.owned || item.consumed || item.lockedBy || item.reservedBy) return no('item_not_available');
  if (!c.edible_item_ids.includes(item.itemId) || item.foodStatus !== c.success_status) return no('personal_food_verification_required');
  const deltas = definition?.resource_deltas;
  if (!deltas || Object.entries(deltas).some(([key, value]) => !Object.hasOwn(s.resources, key) || !finite(value))) return no('item_effect_adapter_not_in_this_reference');
  item.consumed = true; item.owned = false;
  const actualDeltas = Object.fromEntries(Object.entries(deltas).map(([key, value]) => [key, resource(s, key, value)]));
  const r = nextReceipt(s, 'food-consumed', 'same_food_instance_consumed', {objectIds: [item.id], actualDeltas});
  return yes({receiptId: r.id, actualDeltas});
}

export function movePromisedBottle(s, {encounterId, bottleId, slotId}) {
  const e = s.encounters[encounterId], item = s.inventory[bottleId];
  if (!e || e.monsterId !== 'F53' || e.cancelled || s.budget >= 720 || ![e.bindings.bottle1, e.bindings.bottle2].includes(bottleId) ||
      item?.reservedBy !== encounterId || !item.owned || !e.storageSlots.includes(slotId) || (slotId === e.bindings.container && e.containerSealed)) return no('promised_bottle_move_unavailable');
  item.slot = slotId; return yes({});
}
export function setPromiseContainerSeal(s, encounterId, sealed) {
  const e = s.encounters[encounterId];
  if (!e || e.monsterId !== 'F53' || e.cancelled || s.budget >= 720 || typeof sealed !== 'boolean') return no('promise_container_unavailable');
  e.containerSealed = sealed; return yes({});
}
export function sellUnreservedBottle(s, itemInstanceId) {
  const item = s.inventory[itemInstanceId];
  if (!item?.owned || item.consumed || item.reservedBy || item.source !== 'declared_f53_stock' || s.budget >= 720) return no('bottle_reserved_or_unavailable');
  item.owned = false; item.sold = true;
  return yes({itemInstanceId, orderCreditAndPaymentHandledByStoreAdapter: true});
}

export function recordVerifiedHandover(s, {receiptId, runId, managerId, settlementMode, panicActive}) {
  if (s.budget !== 720 || s.handover || runId !== s.runId || managerId !== 'MANAGER' ||
      settlementMode !== 'handover_only' || panicActive !== false) return no('eligible_actual_handover_missing');
  const r = receipt(s, receiptId, 'verified_handover_completed', {managerId});
  if (!r) return no('receipt_id_already_used');
  s.handover = r.id;
  for (const e of Object.values(s.encounters)) if (e.monsterId === 'F53') addFact(s, e, 'dawn', 'verified_handover_completed', r);
  return yes({receiptId: r.id}); // Adapter truth is required; this is not identity authentication.
}

function factsOrdered(s, e, key, names) {
  return names.every((name, i) => i === 0 ||
    s.receipts[e.facts[key][names[i - 1]]].sequence < s.receipts[e.facts[key][name]].sequence);
}
export function settleFriendlyBenefit(s, {encounterId, rootRewardId, rewardKey}) {
  const e = s.encounters[encounterId], spec = e && specFor(s, e, rewardKey);
  if (!e || e.cancelled || rootRewardId !== e.rootRewardId || !spec || e.rewards[rewardKey]) return no('unavailable_or_settled_reward_key');
  if (spec.previous_claim_key && !e.rewards[spec.previous_claim_key]) return no('previous_segment_not_claimed');
  if (spec.requires.some(p => !e.facts[rewardKey]?.[p])) return no('actual_required_fact_missing');
  const ordered = {F23: ['matched_coat_actually_returned', 'claimant_departed', 'declared_gift_actually_claimed'],
    F29: ['same_porridge_and_visible_butter_delivered', 'declared_gift_actually_claimed'],
    F33: ['visitor_first_aid_actually_delivered', 'same_visitor_departed'],
    F35: ['same_registered_garbage_point_actually_cleaned', 'same_broom_returned'],
    F47: ['same_segment_actually_completed', 'same_segment_sealed_and_claimed'],
    F55: ['actual_escort_accepted', 'same_registered_route_completed', 'player_and_remaining_item_returned_to_store']};
  if (ordered[e.monsterId] && !factsOrdered(s, e, rewardKey, ordered[e.monsterId])) return no('actual_fact_order_mismatch');
  if (e.monsterId === 'F53' && (!e.dawnSnapshot?.qualified || !s.handover)) return no('dawn_qualification_or_handover_missing');
  let result = {kind: spec.kind};
  if (spec.kind === 'item') {
    const item = s.inventory[e.bindings.gift];
    if (!item || item.owned || item.itemId !== spec.item_id || !s.items[item.itemId].acquisition_enabled || !s.items[item.itemId].reward_enabled) return no('same_declared_gift_unavailable');
    item.owned = true; result = {...result, itemInstanceId: item.id, itemId: item.itemId, foodStatus: item.foodStatus};
  } else if (spec.kind === 'san') result.actualDelta = resource(s, 'san', spec.amount);
  else if (spec.kind === 'coins') { s.coins += spec.amount; result.amount = spec.amount; }
  else if (spec.kind === 'existing_work_credit') {
    const id = e.facts[rewardKey].same_registered_garbage_point_actually_cleaned;
    if (s.workCredits[e.bindings.work] !== id) return no('original_work_credit_missing');
    result = {...result, receiptId: id, addedWorkCredits: 0, addedCoins: 0};
  }
  const r = nextReceipt(s, 'benefit', 'declared_benefit_settled', {encounterId, rootRewardId, rewardKey, result: clone(result)});
  e.rewards[rewardKey] = r.id;
  // E065 consumes this same root in its existing shared fragment ledger. This
  // module emits no fragments and never invents independent roots for segments.
  if (e.monsterId === 'F47' && rewardKey === 'segment_1') result.fragmentSource = {
    receiptId: r.id, rootRewardId, nightId: s.nightId, kind: 'f47_sealed_reward'};
  return yes({...result, rewardReceiptId: r.id});
}

export function cancelConsumerEncounter(s, encounterId) {
  const e = s.encounters[encounterId];
  if (!e || e.cancelled || (e.monsterId === 'F53' && s.budget >= 720)) return no('encounter_cannot_cancel');
  e.cancelled = true;
  if (e.lease?.state === 'active') e.lease.state = 'revoked_early';
  for (const item of Object.values(s.inventory)) if (item.reservedBy === encounterId) item.reservedBy = null;
  return yes({newReward: 0});
}

export function registerRestEpisode(s, {encounterId, rootRewardId}) {
  if (!named(encounterId) || !named(rootRewardId) || s.restEpisodes[encounterId] || s.encounters[encounterId] || s.rootOwners[rootRewardId]) return no('rest_episode_already_declared_or_invalid');
  s.rootOwners[rootRewardId] = encounterId;
  s.restEpisodes[encounterId] = {encounterId, rootRewardId, state: 'OPEN', failedOnce: false,
    rewardTotalCommitted: 0, attempts: [], petSpent: false, retryGranted: false, lastSettledBudget: s.budget};
  return yes({});
}
function scopedRestReceipt(s, e, r, attemptNumber) {
  return r && named(r.id) && r.runId === s.runId && r.nightId === s.nightId &&
    r.encounterId === e.encounterId && r.rootRewardId === e.rootRewardId && r.attemptNumber === attemptNumber;
}

/**
 * The precision controller separately admits each attempt, reserves and charges
 * eight budget seconds, then supplies the two scoped receipts below. This checks
 * the supplied facts and their unique use; it does not execute or authenticate a
 * QTE, admission, or budget debit. World/local timing remains with that adapter.
 */
export function settleRestAttempt(s, {receiptId, encounterId, rootRewardId, outcome,
  actualAttemptCommitted, precisionAdmissionReceipt, budgetCostReceipt}) {
  const e = s.restEpisodes[encounterId], c = s.contract.f31_p08_rest;
  if (!e || e.rootRewardId !== rootRewardId || !['OPEN', 'RETRY_AVAILABLE'].includes(e.state) ||
      !['success', 'failed', 'cancelled'].includes(outcome) || actualAttemptCommitted !== true) return no('actual_rest_attempt_unavailable');
  const attemptNumber = e.attempts.length + 1;
  const maxAttempts = e.retryGranted ? c.max_attempts_with_prepared_pet : c.max_attempts_without_pet;
  if (attemptNumber > maxAttempts || (attemptNumber > 1 && !e.retryGranted)) return no('rest_attempt_limit_reached');
  const a = precisionAdmissionReceipt, cost = budgetCostReceipt, seconds = c.attempt_cost_budget_seconds;
  if (!(s.resources.san > 0) || !scopedRestReceipt(s, e, a, attemptNumber) ||
      a.admitted !== true || !named(a.reservationId) || a.reservedBudgetSeconds !== seconds ||
      a.sanAtAdmission !== s.resources.san || !(a.sanAtAdmission > 0) ||
      !finite(a.admittedAtBudget) || a.admittedAtBudget < e.lastSettledBudget) return no('positive_san_and_actual_precision_admission_required');
  if (!scopedRestReceipt(s, e, cost, attemptNumber) || cost.committed !== true ||
      cost.precisionAdmissionReceiptId !== a.id || cost.reservationId !== a.reservationId ||
      cost.budgetSeconds !== seconds || !finite(cost.budgetBefore) || !finite(cost.budgetAfter) ||
      cost.budgetBefore !== a.admittedAtBudget || Math.abs(cost.budgetAfter - cost.budgetBefore - seconds) > 1e-9 ||
      Math.abs(cost.budgetAfter - s.budget) > 1e-9 || cost.budgetAfter > 720) return no('same_attempt_eight_budget_seconds_required');
  const receiptIds = [receiptId, a.id, cost.id];
  if (receiptIds.some(id => !named(id) || s.receipts[id]) || new Set(receiptIds).size !== receiptIds.length ||
      s.restReservations[a.reservationId]) return no('attempt_receipt_or_reservation_replayed');
  receipt(s, a.id, 'actual_rest_precision_admission', {encounterId, rootRewardId, attemptNumber,
    reservationId: a.reservationId, admitted: true, reservedBudgetSeconds: seconds,
    admittedAtBudget: a.admittedAtBudget, sanAtAdmission: a.sanAtAdmission});
  receipt(s, cost.id, 'actual_rest_budget_cost', {encounterId, rootRewardId, attemptNumber,
    precisionAdmissionReceiptId: a.id, reservationId: a.reservationId, committed: true,
    budgetSeconds: seconds, budgetBefore: cost.budgetBefore, budgetAfter: cost.budgetAfter});
  const r = receipt(s, receiptId, 'actual_rest_attempt_settled', {encounterId, rootRewardId, outcome,
    attemptNumber, precisionAdmissionReceiptId: a.id, budgetCostReceiptId: cost.id});
  s.restReservations[a.reservationId] = r.id;
  e.attempts.push(r.id); e.lastSettledBudget = s.budget;
  let energyDelta = 0, sanDelta = 0, retry = null, petChargeSpent = false;
  if (outcome === 'cancelled') e.state = 'CANCELLED';
  else if (outcome === 'success') {
    energyDelta = resource(s, 'energy', Math.max(0, c.successful_rest_total_energy - e.rewardTotalCommitted));
    e.rewardTotalCommitted = c.successful_rest_total_energy; e.state = 'RESOLVED';
  } else {
    if (!e.failedOnce) {
      sanDelta = resource(s, 'san', c.first_failure_san_delta);
      if (s.pet.id === 'P08' && s.pet.prepared && s.pet.cared && s.pet.charges > 0) {
        s.pet.charges--; e.petSpent = true; petChargeSpent = true;
        energyDelta = resource(s, 'energy', c.pet_first_real_failure_compensation_energy);
        e.rewardTotalCommitted = c.pet_first_real_failure_compensation_energy;
        if (s.resources.san > 0 && attemptNumber < c.max_attempts_with_prepared_pet) {
          e.retryGranted = true;
          retry = {localWindowSeconds: c.pet_retry_local_window_seconds, clock: 'local_qte',
            targetScale: c.pet_retry_target_scale, existingPrecisionAdmissionStillRequired: true};
        }
      }
    }
    e.failedOnce = true; e.state = retry ? 'RETRY_AVAILABLE' : 'FAILED';
  }
  return yes({receiptId: r.id, attemptNumber, chargedBudgetSeconds: seconds, energyDelta, sanDelta,
    petChargeSpent, retry, normalPanicRequired: s.resources.san === 0});
}

// Leaving a prepared view or declining an unstarted retry is not a new attempt.
// Once an attempt has actually started, cancellation uses settleRestAttempt and
// its already charged eight-second receipt instead.
export function exitUnstartedRest(s, {encounterId, rootRewardId}) {
  const e = s.restEpisodes[encounterId];
  if (!e || e.rootRewardId !== rootRewardId || !['OPEN', 'RETRY_AVAILABLE'].includes(e.state)) return no('unstarted_rest_exit_unavailable');
  e.state = 'CANCELLED';
  return yes({energyDelta: 0, sanDelta: 0, petChargeSpent: false, chargedBudgetSeconds: 0});
}
