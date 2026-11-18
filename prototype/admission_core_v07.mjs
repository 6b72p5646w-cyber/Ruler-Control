/**
 * Limited V0.7 admission reference, not a director or full encounter engine.
 *
 * Callers must supply truthful, already-committed action/evidence records,
 * world/budget clock readings, and measured navigation distances. This module
 * does not discover collisions, authenticate bodies, plan routes or infer
 * predicates from Chinese prose. Fixed numbers are supplied from current data.
 */

const finite = value => typeof value === 'number' && Number.isFinite(value);
const positive = value => finite(value) && value > 0;
const nonnegative = value => finite(value) && value >= 0;
const nonempty = value => typeof value === 'string' && value.length > 0;
const decision = reasons => ({allowed: reasons.length === 0, reasons});

export const HISTORICAL_PRODUCER_KINDS = Object.freeze([
  'actual_work_receipt', 'real_failure_receipt', 'actual_pre_shift_action',
]);

/** A reserved future payload is not an actual historical fact. */
export function checkHistoricalEvidence(records, {
  runId, sceneId, firstOmenBudget, requiredDistinctRoots = 1,
} = {}) {
  const reasons = [], acceptedRootIds = new Set(), rejectedRecords = [];
  if (!nonempty(runId) || !nonempty(sceneId) || !finite(firstOmenBudget) ||
      !Number.isInteger(requiredDistinctRoots) || requiredDistinctRoots < 1 ||
      !Array.isArray(records)) {
    return {...decision(['invalid_history_request']), acceptedRootIds: [], rejectedRecords};
  }
  for (const record of records) {
    const rejected = [];
    if (!record || !nonempty(record.id) || !nonempty(record.rootId)) rejected.push('missing_receipt_identity');
    if (record?.committed !== true) rejected.push('not_actual_committed_fact');
    if (!HISTORICAL_PRODUCER_KINDS.includes(record?.producerKind)) rejected.push('not_historical_producer');
    if (record?.runId !== runId) rejected.push('different_run');
    if (record?.sceneId !== sceneId) rejected.push('different_scene');
    if (!finite(record?.createdAtBudget) || record.createdAtBudget > firstOmenBudget) rejected.push('not_created_by_first_omen');
    if (rejected.length) rejectedRecords.push({id: record?.id ?? null, reasons: rejected});
    else acceptedRootIds.add(record.rootId);
  }
  if (acceptedRootIds.size < requiredDistinctRoots) reasons.push('insufficient_distinct_actual_history');
  return {...decision(reasons), acceptedRootIds: [...acceptedRootIds], rejectedRecords};
}

/** An announced arrival does not satisfy actual verified presence. */
export function checkRequiredActor(actor, {
  actorId, runId, sceneId, activationBudget, requiresVerified = true,
} = {}) {
  const reasons = [];
  if (!nonempty(actorId) || !nonempty(runId) || !nonempty(sceneId) || !finite(activationBudget)) {
    return decision(['invalid_actor_request']);
  }
  if (!actor || actor.id !== actorId) reasons.push('wrong_actor');
  if (actor?.runId !== runId || actor?.sceneId !== sceneId) reasons.push('wrong_actor_context');
  if (actor?.arrivalCommitted !== true || !finite(actor?.arrivedAtBudget) ||
      actor.arrivedAtBudget > activationBudget) reasons.push('actor_not_actually_arrived_by_activation');
  if (actor?.departedAtBudget != null &&
      (!finite(actor.departedAtBudget) || actor.departedAtBudget <= activationBudget)) reasons.push('actor_has_left');
  if (requiresVerified && (actor?.verificationCommitted !== true ||
      !finite(actor?.verifiedAtBudget) || actor.verifiedAtBudget > activationBudget ||
      (finite(actor?.arrivedAtBudget) && actor.verifiedAtBudget < actor.arrivedAtBudget))) {
    reasons.push('actor_not_verified_in_current_presence');
  }
  return decision(reasons);
}

export function createSpecialOffer({
  id, runId, sceneId, arrivalWorld, arrivalBudget, phaseEndBudget,
  ordinaryPatienceWorldSeconds, reservedDurationWorldSeconds,
}) {
  if (![id, runId, sceneId].every(nonempty) || !nonnegative(arrivalWorld) ||
      !nonnegative(arrivalBudget) || !positive(phaseEndBudget) ||
      !positive(ordinaryPatienceWorldSeconds) || !positive(reservedDurationWorldSeconds) ||
      arrivalBudget > phaseEndBudget) throw new RangeError('Invalid special offer configuration');
  const lastAcceptBudget = phaseEndBudget - reservedDurationWorldSeconds;
  return {
    id, runId, sceneId, arrivalWorld, arrivalBudget, phaseEndBudget,
    worldPatienceDeadline: arrivalWorld + ordinaryPatienceWorldSeconds,
    lastAcceptBudget, reservedDurationWorldSeconds,
    state: arrivalBudget <= lastAcceptBudget ? 'WAITING' : 'CANCELLED_UNAVAILABLE',
    lastWorld: arrivalWorld, lastBudget: arrivalBudget,
    acceptanceReceipt: null, acceptanceCommitCount: 0,
  };
}

function readOfferClock(offer, {world, budget}) {
  if (!nonnegative(world) || !nonnegative(budget) || world < offer.lastWorld ||
      budget < offer.lastBudget) return false;
  offer.lastWorld = world; offer.lastBudget = budget;
  return true;
}

/**
 * Equality is allowed. At a due boundary the caller dispatches a legitimate
 * committed acceptance first, then settles expiry. Later retries never revive
 * an expired offer or produce a second acceptance receipt.
 */
export function commitSpecialAcceptance(offer, {world, budget, requestId}) {
  if (!nonempty(requestId) || !readOfferClock(offer, {world, budget})) {
    return {committed: false, reason: 'invalid_acceptance_or_clock'};
  }
  if (offer.state === 'ACCEPTED') {
    return {committed: false, idempotent: offer.acceptanceReceipt.requestId === requestId,
      reason: 'already_accepted', receipt: {...offer.acceptanceReceipt}};
  }
  if (offer.state !== 'WAITING') return {committed: false, reason: 'terminal_offer'};
  if (world > offer.worldPatienceDeadline || budget > offer.lastAcceptBudget) {
    offer.state = 'EXPIRED';
    return {committed: false, reason: 'acceptance_window_elapsed'};
  }
  offer.state = 'ACCEPTED'; offer.acceptanceCommitCount += 1;
  offer.acceptanceReceipt = {
    id: `accept:${offer.id}`, offerId: offer.id, requestId,
    runId: offer.runId, sceneId: offer.sceneId, world, budget,
    completionWorldDeadline: world + offer.reservedDurationWorldSeconds,
    phaseEndBudget: offer.phaseEndBudget,
  };
  return {committed: true, idempotent: false, receipt: {...offer.acceptanceReceipt}};
}

/** Called after same-tick action commits; either clock's deadline can expire it. */
export function settleSpecialOfferExpiry(offer, {world, budget}) {
  if (!readOfferClock(offer, {world, budget})) return {expired: false, reason: 'invalid_clock'};
  if (offer.state !== 'WAITING') return {expired: false, reason: 'not_waiting'};
  if (world >= offer.worldPatienceDeadline || budget >= offer.lastAcceptBudget) {
    offer.state = 'EXPIRED';
    return {expired: true, reason: world >= offer.worldPatienceDeadline ? 'world_patience' : 'phase_acceptance_cutoff'};
  }
  return {expired: false, reason: 'within_offer_window'};
}

/** A QTE cost spends budget, not world time, and may not spend reserved work. */
export function checkPrecisionBudget({
  nowBudget, attemptCostBudgetSeconds, phaseEndBudget,
  remainingCriticalWorldSeconds, nextScheduledBoundaryBudget,
}) {
  const reasons = [];
  if (!nonnegative(nowBudget) || !positive(attemptCostBudgetSeconds) ||
      !positive(phaseEndBudget) || !nonnegative(remainingCriticalWorldSeconds) ||
      !finite(nextScheduledBoundaryBudget) || nextScheduledBoundaryBudget <= nowBudget) {
    return decision(['invalid_or_due_budget_boundary']);
  }
  const afterAttemptBudget = nowBudget + attemptCostBudgetSeconds;
  if (afterAttemptBudget > nextScheduledBoundaryBudget) reasons.push('crosses_scheduled_boundary');
  if (afterAttemptBudget > phaseEndBudget) reasons.push('crosses_phase_end');
  if (phaseEndBudget - afterAttemptBudget < remainingCriticalWorldSeconds) reasons.push('spends_reserved_critical_work_budget');
  return {...decision(reasons), afterAttemptBudget};
}

/** Distance must come from the caller's current, declared endpoint route. */
export function checkTimedTransfer({
  measuredDistanceTiles, pathExists, carryTilesPerSecond, walkTilesPerSecond,
  openSeconds, pickupSeconds, placeSeconds, closeSeconds, safeWindowSeconds,
}) {
  if (pathExists !== true || !positive(measuredDistanceTiles) ||
      !positive(carryTilesPerSecond) || !positive(walkTilesPerSecond) ||
      ![openSeconds, pickupSeconds, placeSeconds, closeSeconds].every(nonnegative) ||
      !positive(safeWindowSeconds)) return {...decision(['invalid_or_missing_transfer_path']), totalWorldSeconds: null};
  const totalWorldSeconds = openSeconds + pickupSeconds + measuredDistanceTiles / carryTilesPerSecond +
    placeSeconds + measuredDistanceTiles / walkTilesPerSecond + closeSeconds;
  return {...decision(totalWorldSeconds <= safeWindowSeconds ? [] : ['transfer_exceeds_safe_window']),
    totalWorldSeconds, slackWorldSeconds: safeWindowSeconds - totalWorldSeconds};
}

export function createSeatProtection({id, runId, protectedWorldSeconds}) {
  if (!nonempty(id) || !nonempty(runId) || !positive(protectedWorldSeconds)) throw new RangeError('Invalid seat episode');
  return {id, runId, protectedWorldSeconds, state: 'RESERVED', signPrepared: false,
    manifestationWorld: null, protectionEndsWorld: null};
}

/** Preparatory work neither starts nor resets the encounter-owned timer. */
export function prepareSeatSign(episode) {
  if (!['RESERVED', 'ACTIVE'].includes(episode.state)) return false;
  episode.signPrepared = true;
  return true;
}

export function manifestSeatProtection(episode, {world}) {
  if (!nonnegative(world) || episode.state !== 'RESERVED') return false;
  episode.state = 'ACTIVE'; episode.manifestationWorld = world;
  episode.protectionEndsWorld = world + episode.protectedWorldSeconds;
  return true;
}

/** This is only the timer gate; real occupancy/customer facts remain necessary. */
export function seatProtectionWindowElapsed(episode, {world}) {
  return episode.state === 'ACTIVE' && nonnegative(world) &&
    world >= episode.protectionEndsWorld;
}
