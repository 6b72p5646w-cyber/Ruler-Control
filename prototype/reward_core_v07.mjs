/**
 * Finite reward-transaction reference. No RNG sampler, shop UI, full work engine,
 * spatial checks or payment service. Jobs, build capabilities, quotes and draw
 * candidates are declared adapter inputs; this module validates their downstream
 * ownership, once-only effects, pity result and atomic inventory/currency changes.
 */
const clone = x => JSON.parse(JSON.stringify(x));
const ok = fields => ({ok: true, ...fields});
const fail = reason => ({ok: false, reason});
const key = (s, prefix) => `${prefix}-${++s.sequence}`;
const finiteInt = x => Number.isSafeInteger(x) && x >= 0;

export function createRewardState(itemData, options = {}) {
  const items = Object.fromEntries(itemData.items.map(x => [x.id, clone(x)]));
  const supported = options.supportedItemIds ?? [];
  return {policy: clone(itemData.lottery), catalog: items, supported: [...supported],
    consumers: [...(options.consumerItemIds ?? supported)], sequence: 0,
    tickets: options.initialTickets ?? 1, fragments: 0, coins: options.initialCoins ?? 100,
    pity: {consecutiveCommon: 0, consecutiveNonrare: 0},
    prep: {windowId: options.windowId ?? 'procurement-1', open: true,
      minute: options.minute ?? 1200, remaining: options.preparationMinutes ?? 60},
    jobs: Object.fromEntries((options.jobs ?? []).map(j => [j.id, {...clone(j), state: 'pending'}])),
    quotes: Object.fromEntries((options.quotes ?? []).map(q => [q.id, clone(q)])),
    receipts: {}, sourceHandled: {}, nightQuota: {}, exchanges: {}, inventory: {},
    draws: {}, pendingDraw: null, usedDoubleWindows: {}, purchases: {}, returns: {},
    pendingReturn: null, ledger: []};
}

function prepFits(s, minutes) {
  return s.prep.open && !s.pendingReturn && s.prep.minute >= 1200 &&
    s.prep.minute + minutes <= 1320 && s.prep.remaining >= minutes;
}
function spendPrep(s, minutes) { s.prep.minute += minutes; s.prep.remaining -= minutes; }
function eligible(s, itemId, channel) {
  const item = s.catalog[itemId];
  return item?.acquisition_enabled === true && item[`${channel}_enabled`] === true &&
    s.supported.includes(itemId) && s.consumers.includes(itemId);
}
function grantItem(s, itemId, origin, sourceId) {
  const instanceId = key(s, 'item');
  s.inventory[instanceId] = {id: instanceId, itemId, origin, sourceId, uses: 0,
    owned: true, transferred: false, lockedBy: null};
  return instanceId;
}

export function completeRewardWork(s, jobId) {
  const job = s.jobs[jobId];
  if (!job || job.state !== 'pending' || !['optional_work_completed', 'f47_sealed_reward'].includes(job.kind)) {
    return fail('no_pending_eligible_job');
  }
  job.state = 'completed';
  const receiptId = key(s, 'work-receipt');
  s.receipts[receiptId] = {id: receiptId, jobId, kind: job.kind, nightId: job.nightId,
    rootRewardId: job.rootRewardId ?? job.id, completed: true};
  return ok({receiptId});
}

export function reserveFragmentReward(s, jobId) {
  const job = s.jobs[jobId];
  if (!job || job.state !== 'pending') return fail('no_pending_job');
  const root = job.rootRewardId ?? job.id;
  if (s.sourceHandled[root]) return fail('source_already_handled');
  const old = s.nightQuota[job.nightId];
  if (old && (old.rootRewardId !== root || old.state === 'claimed')) return fail('night_quota_unavailable');
  s.nightQuota[job.nightId] = {state: 'reserved', rootRewardId: root};
  return ok({rootRewardId: root});
}

export function claimFragmentReward(s, receiptId) {
  const r = s.receipts[receiptId];
  if (!r?.completed) return fail('actual_completion_missing');
  if (s.sourceHandled[r.rootRewardId]) return fail('source_already_handled');
  const quota = s.nightQuota[r.nightId];
  if (quota && (quota.state === 'claimed' || quota.rootRewardId !== r.rootRewardId)) return fail('night_quota_unavailable');
  s.sourceHandled[r.rootRewardId] = 'claimed';
  s.nightQuota[r.nightId] = {state: 'claimed', rootRewardId: r.rootRewardId};
  s.fragments += s.policy.fragment_contract.fragments_per_completed_reward;
  s.ledger.push({kind: 'fragment_reward', receiptId, rootRewardId: r.rootRewardId, nightId: r.nightId, amount: 1});
  return ok({fragments: s.fragments});
}

export function declineFragmentReward(s, receiptId) {
  const r = s.receipts[receiptId];
  if (!r?.completed || s.sourceHandled[r.rootRewardId]) return fail('no_unhandled_completion');
  s.sourceHandled[r.rootRewardId] = 'declined';
  const q = s.nightQuota[r.nightId];
  if (q?.state === 'reserved' && q.rootRewardId === r.rootRewardId) delete s.nightQuota[r.nightId];
  return ok({});
}

export function exchangeFragments(s, exchangeId) {
  const p = s.policy.fragment_contract;
  if (!exchangeId || s.exchanges[exchangeId]) return fail('exchange_already_committed_or_invalid');
  if (!prepFits(s, p.exchange_preparation_minutes)) return fail('preparation_unavailable');
  if (s.fragments < p.fragments_required_per_exchange) return fail('not_enough_fragments');
  spendPrep(s, p.exchange_preparation_minutes);
  s.fragments -= p.fragments_required_per_exchange; s.tickets += p.tickets_granted_per_exchange;
  s.exchanges[exchangeId] = {fragmentsDebited: p.fragments_required_per_exchange,
    ticketsGranted: p.tickets_granted_per_exchange, windowId: s.prep.windowId};
  s.ledger.push({kind: 'fragment_exchange', exchangeId, ...s.exchanges[exchangeId]});
  return ok({tickets: s.tickets, fragments: s.fragments});
}

function rarityAllowed(policy, pity, rarity) {
  if (pity.consecutiveNonrare >= policy.rare_pity_after_nonrare_draws) return rarity === 'rare';
  if (pity.consecutiveCommon >= policy.noncommon_pity_after_common_draws) return rarity !== 'common';
  return ['common', 'uncommon', 'rare'].includes(rarity);
}
function applyPity(s, rarity) {
  if (rarity === 'common') { s.pity.consecutiveCommon++; s.pity.consecutiveNonrare++; }
  else if (rarity === 'uncommon') { s.pity.consecutiveCommon = 0; s.pity.consecutiveNonrare++; }
  else { s.pity.consecutiveCommon = 0; s.pity.consecutiveNonrare = 0; }
}

export function openDoubleChoice(s, {drawId, candidateItemIds}) {
  const p = s.policy.double_choice_contract;
  if (!drawId || s.draws[drawId] || s.pendingDraw) return fail('draw_already_exists_or_pending');
  if (s.usedDoubleWindows[s.prep.windowId]) return fail('window_offer_used');
  if (!prepFits(s, p.preparation_minutes) || s.tickets < p.cost) return fail('ticket_or_preparation_unavailable');
  const pool = Object.values(s.catalog).filter(x => eligible(s, x.id, 'lottery'));
  const requiredWeights = s.pity.consecutiveNonrare >= s.policy.rare_pity_after_nonrare_draws
    ? {rare: 1} : s.pity.consecutiveCommon >= s.policy.noncommon_pity_after_common_draws
      ? s.policy.noncommon_pity_weights : s.policy.base_tier_probabilities;
  if (Object.entries(requiredWeights).some(([tier, weight]) => weight > 0 && !pool.some(x => x.rarity === tier))) {
    return fail('weighted_tier_pool_unavailable');
  }
  const pityPool = pool.filter(x => rarityAllowed(s.policy, s.pity, x.rarity));
  if (pityPool.length < p.candidate_count) return fail('required_pool_unavailable');
  if (!Array.isArray(candidateItemIds) || candidateItemIds.length !== p.candidate_count ||
      new Set(candidateItemIds).size !== p.candidate_count ||
      candidateItemIds.some(id => !pityPool.some(x => x.id === id))) return fail('invalid_adapter_candidates');
  // Move one available ticket into this persisted pending transaction before
  // reveal. Finalization consumes its reservation, never debits it a second time.
  spendPrep(s, p.preparation_minutes); s.tickets -= p.cost;
  s.draws[drawId] = {id: drawId, state: 'pending', windowId: s.prep.windowId,
    reservedTicket: p.cost, candidates: [...candidateItemIds], pitySnapshot: clone(s.pity)};
  s.pendingDraw = drawId; s.usedDoubleWindows[s.prep.windowId] = true;
  s.ledger.push({kind: 'ticket_reserved_and_candidates_saved', drawId, amount: p.cost});
  return ok({drawId, candidates: [...candidateItemIds]});
}

export function readPendingChoice(s) {
  const d = s.draws[s.pendingDraw];
  return d?.state === 'pending' ? ok({drawId: d.id, candidates: [...d.candidates]}) : fail('no_pending_draw');
}

export function chooseDoubleReward(s, {drawId, selectedItemId}) {
  const d = s.draws[drawId];
  if (!d || d.state !== 'pending' || s.pendingDraw !== drawId) return fail('no_pending_draw');
  if (!s.prep.open || s.pendingReturn || s.prep.minute > 1320) return fail('preparation_unavailable');
  if (!d.candidates.includes(selectedItemId)) return fail('not_a_saved_candidate');
  if (!eligible(s, selectedItemId, 'lottery')) return fail('saved_candidate_currently_unavailable');
  if (JSON.stringify(s.pity) !== JSON.stringify(d.pitySnapshot)) return fail('pity_changed_during_pending_choice');
  const itemId = grantItem(s, selectedItemId, 'lottery', drawId);
  applyPity(s, s.catalog[selectedItemId].rarity);
  d.state = 'resolved'; d.selectedItemId = selectedItemId; d.grantedInstanceId = itemId; d.reservedTicket = 0;
  s.pendingDraw = null; s.ledger.push({kind: 'draw_finalized_once', drawId, itemId, pity: clone(s.pity)});
  return ok({instanceId: itemId});
}

export function purchaseQuotedItem(s, quoteId) {
  const q = s.quotes[quoteId];
  if (!prepFits(s, 0) || !q || q.windowId !== s.prep.windowId || q.used || !finiteInt(q.price) || q.price <= 0) return fail('quote_unavailable');
  if (!eligible(s, q.itemId, 'shop') || s.coins < q.price) return fail('item_or_money_unavailable');
  const purchaseId = key(s, 'purchase');
  const instanceId = grantItem(s, q.itemId, 'paid_shop', purchaseId);
  q.used = true; s.coins -= q.price;
  s.purchases[purchaseId] = {id: purchaseId, quoteId, instanceId, amountPaid: q.price,
    windowId: s.prep.windowId, refunded: false};
  s.ledger.push({kind: 'paid_purchase', purchaseId, instanceId, actualPaid: q.price});
  return ok({purchaseId, instanceId});
}

export function useRewardItem(s, instanceId) {
  const item = s.inventory[instanceId];
  if (!item?.owned || item.lockedBy) return fail('item_unavailable');
  item.uses++; return ok({});
}
export function transferRewardItem(s, instanceId) {
  const item = s.inventory[instanceId];
  if (!item?.owned || item.lockedBy) return fail('item_unavailable');
  item.owned = false; item.transferred = true; return ok({});
}

export function beginPurchaseReturn(s, purchaseId) {
  const p = s.purchases[purchaseId], c = s.policy.refund_contract;
  if (!prepFits(s, c.preparation_minutes) || !p || p.refunded || p.windowId !== s.prep.windowId) return fail('return_window_or_purchase_unavailable');
  const item = s.inventory[p.instanceId];
  if (!item?.owned || item.origin !== 'paid_shop' || item.sourceId !== purchaseId || item.uses || item.transferred || item.lockedBy) return fail('original_unused_item_unavailable');
  spendPrep(s, c.preparation_minutes);
  const returnId = key(s, 'return');
  s.returns[returnId] = {id: returnId, purchaseId, instanceId: item.id,
    windowId: s.prep.windowId, amount: p.amountPaid, state: 'pending'};
  item.lockedBy = returnId; s.pendingReturn = returnId;
  return ok({returnId});
}

export function cancelPurchaseReturn(s, returnId) {
  const r = s.returns[returnId];
  if (!r || r.state !== 'pending') return fail('no_pending_return');
  const item = s.inventory[r.instanceId];
  if (item?.lockedBy === returnId) item.lockedBy = null;
  r.state = 'cancelled'; if (s.pendingReturn === returnId) s.pendingReturn = null;
  return ok({});
}

export function finishPurchaseReturn(s, returnId) {
  const r = s.returns[returnId];
  if (!r || r.state !== 'pending' || s.pendingReturn !== returnId) return fail('no_pending_return');
  const p = s.purchases[r.purchaseId], item = s.inventory[r.instanceId];
  if (!s.prep.open || s.prep.minute > 1320 || s.prep.windowId !== r.windowId ||
      p.refunded || !item?.owned || item.uses || item.transferred || item.lockedBy !== returnId) return fail('return_inputs_changed');
  item.owned = false; item.lockedBy = null; p.refunded = true;
  s.coins += p.amountPaid; r.state = 'resolved'; s.pendingReturn = null;
  s.ledger.push({kind: 'original_item_returned_and_purchase_refunded', returnId,
    purchaseId: p.id, amount: p.amountPaid, instanceId: item.id});
  return ok({amount: p.amountPaid});
}

export function changeProcurementWindow(s, {windowId, minute = 1200, remaining = 60, open = true}) {
  if (s.pendingReturn) cancelPurchaseReturn(s, s.pendingReturn);
  s.prep = {windowId, minute, remaining, open};
  return ok({}); // Existing paid double-choice escrow is preserved, not rerolled.
}

export function commitWarningBonus(state, {sourceId, attackId, monsterId, requestedTotal,
  warningRemaining, phaseBudgetRemaining, shiftBudgetRemaining}) {
  // A finite arithmetic adapter for the shared max-total ledger. I21 has an
  // explicit consumer list; other sources must be resolved by their own adapter.
  const permitted = {I21: {F50: [3], F60: [3]}, P05_special: {F50: [2]},
    P07_special: {F60: [2]}, B04: {F50: [1, 0.5]}};
  if (!permitted[sourceId]?.[monsterId]?.includes(requestedTotal)) return fail('unsupported_consumer_or_bonus');
  if (!attackId || !Number.isFinite(warningRemaining) || warningRemaining <= 0 ||
      !Number.isFinite(requestedTotal) || requestedTotal <= 0) return fail('inactive_or_invalid_warning');
  const old = state[attackId] ?? {total: 0, committedSources: []};
  if (old.monsterId && old.monsterId !== monsterId) return fail('attack_identity_changed');
  if (old.committedSources.includes(sourceId)) return fail('source_already_committed');
  const increment = Math.max(0, requestedTotal - old.total);
  if (!increment) return fail('no_positive_increment');
  if (![phaseBudgetRemaining, shiftBudgetRemaining].every(Number.isFinite) ||
      warningRemaining + increment > Math.min(phaseBudgetRemaining, shiftBudgetRemaining)) return fail('warning_would_cross_budget_boundary');
  state[attackId] = {monsterId, total: requestedTotal, committedSources: [...old.committedSources, sourceId]};
  return ok({increment, total: requestedTotal});
}
