import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
  checkHistoricalEvidence, checkRequiredActor, createSpecialOffer,
  commitSpecialAcceptance, settleSpecialOfferExpiry, checkPrecisionBudget,
  checkTimedTransfer, createSeatProtection, prepareSeatSign,
  manifestSeatProtection, seatProtectionWindowElapsed,
} from './admission_core_v07.mjs';

const content = path => JSON.parse(fs.readFileSync(new URL(`../content/${path}`, import.meta.url), 'utf8'));
const cards = new Map(content('encounters_v05.json').encounters.map(row => [row.id, row]));
const store = content('store_systems_v05.json');
const life = content('condition_lifecycle_v06.json');
const passed = [];
const test = (name, fn) => {fn(); passed.push(name);};
const context = {runId: 'night-3', sceneId: 'MAP_STORE', firstOmenBudget: 80};
const actual = (patch = {}) => ({id: 'r1', rootId: 'action-1', producerKind: 'actual_work_receipt',
  committed: true, runId: context.runId, sceneId: context.sceneId, createdAtBudget: 75, ...patch});

test('Actual historical work must complete by the first omen, equality included', () => {
  assert.equal(checkHistoricalEvidence([actual({createdAtBudget: 80})], context).allowed, true);
  assert.equal(checkHistoricalEvidence([actual({createdAtBudget: 80.01})], context).allowed, false);
});
test('A different night or scene cannot supply a current historical prerequisite', () => {
  assert.equal(checkHistoricalEvidence([actual({runId: 'night-2'})], context).allowed, false);
  assert.equal(checkHistoricalEvidence([actual({sceneId: 'MAP_HOME'})], context).allowed, false);
});
test('Declared arrival payload and uncommitted future work cannot masquerade as history', () => {
  assert.equal(checkHistoricalEvidence([actual({producerKind: 'declared_arrival_payload'})], context).allowed, false);
  assert.equal(checkHistoricalEvidence([actual({committed: false})], context).allowed, false);
});
test('Reprinting the same source does not satisfy three distinct historical records', () => {
  const printed = [1, 2, 3].map(n => actual({id: `print-${n}`}));
  assert.equal(checkHistoricalEvidence(printed, {...context, requiredDistinctRoots: 3}).allowed, false);
  const distinct = printed.map((r, i) => ({...r, rootId: `work-${i}`}));
  assert.equal(checkHistoricalEvidence(distinct, {...context, requiredDistinctRoots: 3}).allowed, true);
});
test('An actual pre-shift action may precede an opening omen without forged night work', () => {
  assert.equal(checkHistoricalEvidence([actual({producerKind: 'actual_pre_shift_action', createdAtBudget: -30})],
    {...context, firstOmenBudget: -20}).allowed, true);
});
test('Malformed history timestamps and missing context do not pass admission', () => {
  assert.equal(checkHistoricalEvidence([actual({createdAtBudget: NaN})], context).allowed, false);
  assert.equal(checkHistoricalEvidence([actual()], {...context, runId: ''}).allowed, false);
});

const manager = (patch = {}) => ({id: 'MANAGER', runId: context.runId, sceneId: context.sceneId,
  arrivalCommitted: true, arrivedAtBudget: life.end_of_shift.manager_arrival_budget_seconds,
  verificationCommitted: true, verifiedAtBudget: life.end_of_shift.manager_arrival_budget_seconds,
  departedAtBudget: null, ...patch});
const actorRequest = activationBudget => ({actorId: 'MANAGER', runId: context.runId,
  sceneId: context.sceneId, activationBudget});
test('Real manager at budget700 cannot accompany a variant activated at620', () => {
  assert.equal(checkRequiredActor(manager(), actorRequest(620)).allowed, false);
  assert.equal(checkRequiredActor(manager(), actorRequest(700)).allowed, true);
});
test('A planned or not-yet-verified manager is not actual verified presence', () => {
  assert.equal(checkRequiredActor(manager({arrivalCommitted: false}), actorRequest(700)).allowed, false);
  assert.equal(checkRequiredActor(manager({verifiedAtBudget: 701}), actorRequest(700)).allowed, false);
});
test('A departed, wrong-context or different actor cannot satisfy accompaniment', () => {
  assert.equal(checkRequiredActor(manager({departedAtBudget: 705}), actorRequest(705)).allowed, false);
  assert.equal(checkRequiredActor(manager({runId: 'night-2'}), actorRequest(705)).allowed, false);
  assert.equal(checkRequiredActor(manager({id: 'VISITOR'}), actorRequest(705)).allowed, false);
});

const offer = (patch = {}) => createSpecialOffer({id: 'F27-order', runId: context.runId,
  sceneId: context.sceneId, arrivalWorld: 20, arrivalBudget: store.omens.arrival_second_in_phase,
  phaseEndBudget: store.omens.phase_seconds,
  ordinaryPatienceWorldSeconds: store.service.normal_order_patience_world_seconds,
  reservedDurationWorldSeconds: cards.get('F27').runtime_parameters.accepted_special_order_deadline_world_seconds,
  ...patch});
test('F27 has a budget30 acceptance cutoff despite ordinary world patience until44', () => {
  const s = offer(); assert.equal(s.lastAcceptBudget, 30); assert.equal(s.worldPatienceDeadline, 44);
  assert.equal(settleSpecialOfferExpiry(s, {world: 30, budget: 30}).expired, true);
  assert.equal(s.state, 'EXPIRED');
});
test('Exact acceptance boundary commits once before expiry, with an idempotent receipt', () => {
  const s = offer(); const first = commitSpecialAcceptance(s, {world: 30, budget: 30, requestId: 'tap-1'});
  assert.equal(first.committed, true); assert.equal(first.receipt.completionWorldDeadline, 120);
  assert.equal(settleSpecialOfferExpiry(s, {world: 30, budget: 30}).expired, false);
  const retry = commitSpecialAcceptance(s, {world: 30, budget: 30, requestId: 'tap-1'});
  assert.equal(retry.committed, false); assert.equal(retry.idempotent, true);
  assert.equal(s.acceptanceCommitCount, 1);
});
test('Late acceptance and later retries cannot revive an expired offer', () => {
  const s = offer(); assert.equal(commitSpecialAcceptance(s, {world: 30.01, budget: 30.01, requestId: 'late'}).committed, false);
  assert.equal(s.state, 'EXPIRED');
  assert.equal(commitSpecialAcceptance(s, {world: 31, budget: 31, requestId: 'again'}).committed, false);
  assert.equal(s.acceptanceCommitCount, 0);
});
test('The world patience deadline can expire before the budget acceptance cutoff', () => {
  const s = offer({reservedDurationWorldSeconds: 30});
  assert.equal(s.lastAcceptBudget, 90);
  assert.equal(settleSpecialOfferExpiry(s, {world: 44, budget: 44}).reason, 'world_patience');
});
test('QTE clock offset cannot keep a phase-expired offer alive on world patience alone', () => {
  const s = offer({arrivalWorld: 10});
  assert.equal(s.worldPatienceDeadline, 34);
  assert.equal(settleSpecialOfferExpiry(s, {world: 15, budget: 30}).reason, 'phase_acceptance_cutoff');
});
test('An impossible initial reservation is unavailable and its clocks cannot go backwards', () => {
  const unavailable = offer({arrivalBudget: 31}); assert.equal(unavailable.state, 'CANCELLED_UNAVAILABLE');
  const s = offer(); settleSpecialOfferExpiry(s, {world: 25, budget: 25});
  assert.equal(commitSpecialAcceptance(s, {world: 24, budget: 24, requestId: 'rewind'}).committed, false);
});

const precision = patch => checkPrecisionBudget({nowBudget: 20, attemptCostBudgetSeconds: 10,
  phaseEndBudget: 120, remainingCriticalWorldSeconds: 90, nextScheduledBoundaryBudget: 55, ...patch});
test('A QTE may use exact slack but may not consume one second of reserved critical work', () => {
  assert.equal(precision({}).allowed, true);
  assert.equal(precision({attemptCostBudgetSeconds: 11}).allowed, false);
  assert.equal(precision({nowBudget: 30, attemptCostBudgetSeconds: 1}).allowed, false);
});
test('Sufficient phase slack does not allow a QTE to cross an undelivered schedule marker', () => {
  assert.equal(precision({nowBudget: 50, attemptCostBudgetSeconds: 6, remainingCriticalWorldSeconds: 20}).allowed, false);
  assert.equal(precision({nowBudget: 50, attemptCostBudgetSeconds: 5, remainingCriticalWorldSeconds: 20}).allowed, true);
});
test('Due markers and invalid critical-budget claims are rejected before precision entry', () => {
  assert.equal(precision({nextScheduledBoundaryBudget: 20}).allowed, false);
  assert.equal(precision({remainingCriticalWorldSeconds: -1}).allowed, false);
});

const f42 = cards.get('F42').runtime_parameters;
const transfer = patch => checkTimedTransfer({measuredDistanceTiles: 3, pathExists: true,
  carryTilesPerSecond: 2.4, walkTilesPerSecond: 3,
  openSeconds: f42.manual_gate_open_world_seconds, closeSeconds: f42.manual_gate_close_world_seconds,
  pickupSeconds: 1.5, placeSeconds: 1.5, safeWindowSeconds: f42.safe_low_pressure_world_seconds, ...patch});
test('F42 declared short crossing fits at7.25s with0.75s slack', () => {
  const r = transfer({}); assert.equal(r.totalWorldSeconds, 7.25); assert.equal(r.slackWorldSeconds, 0.75);
  assert.equal(r.allowed, true);
});
test('Full loading-bay and dumpster paths cannot be squeezed into the8s crossing window', () => {
  assert.equal(transfer({measuredDistanceTiles: 8}).totalWorldSeconds, 11);
  assert.ok(Math.abs(transfer({measuredDistanceTiles: 10}).totalWorldSeconds - 12.5) < 1e-9);
  assert.equal(transfer({measuredDistanceTiles: 8}).allowed, false);
  assert.equal(transfer({measuredDistanceTiles: 10}).allowed, false);
});
test('Missing routes, zero speed and NaN distances never pass transfer admission', () => {
  assert.equal(transfer({pathExists: false}).allowed, false);
  assert.equal(transfer({carryTilesPerSecond: 0}).allowed, false);
  assert.equal(transfer({measuredDistanceTiles: NaN}).allowed, false);
});

const seat = () => createSeatProtection({id: 'F07-seat', runId: context.runId,
  protectedWorldSeconds: cards.get('F07').runtime_parameters.reserved_world_seconds});
test('Preparing the F07 sign before arrival does not start its protection timer', () => {
  const s = seat(); assert.equal(prepareSeatSign(s), true);
  assert.equal(s.manifestationWorld, null); assert.equal(s.protectionEndsWorld, null);
  assert.equal(seatProtectionWindowElapsed(s, {world: 100}), false);
});
test('F07 starts at actual manifestation and covers the normal55-second customer', () => {
  const s = seat(); prepareSeatSign(s); manifestSeatProtection(s, {world: 20});
  assert.equal(s.protectionEndsWorld, 65);
  assert.equal(seatProtectionWindowElapsed(s, {world: 55}), false);
  assert.equal(seatProtectionWindowElapsed(s, {world: 65}), true);
});
test('Rehanging the F07 sign or replaying manifestation cannot reset its timer', () => {
  const s = seat(); manifestSeatProtection(s, {world: 20}); prepareSeatSign(s);
  assert.equal(manifestSeatProtection(s, {world: 40}), false);
  assert.equal(s.protectionEndsWorld, 65);
});
test('Frozen world time does not finish the F07 protection timer through budget changes', () => {
  const s = seat(); manifestSeatProtection(s, {world: 20});
  assert.equal(seatProtectionWindowElapsed(s, {world: 25, budget: 90}), false);
  assert.equal(seatProtectionWindowElapsed(s, {world: 25, budget: 120}), false);
});

console.log(JSON.stringify({status: 'PASS', scenarioCount: passed.length, scenarios: passed,
  scope: 'Finite source/time/admission arithmetic only. Requires truthful caller records and measured route distances; no full director, identity engine, collision, AI or mobile playthrough.'}, null, 2));
