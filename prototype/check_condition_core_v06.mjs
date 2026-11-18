import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {
  createConditionState, setConditionPause, beginRecordedWork, cancelRecordedWork,
  requireHistoricalReceipt, announceGlassHazard, announceStationGlassFault,
  contactGlassHazard, applyOrdinaryMinorContact, beginFirstAid, walkActor,
  announceBloodEncounter, offerOptionalEncounter, declineOptionalEncounter,
  acceptDawnPromise, advanceConditionWorld, beginPrecisionAttempt,
  advancePrecisionLocal, finishPrecisionAttempt,
  applyConditionFear, beginPortableStabilization, interruptPortableStabilization
} from './condition_core_v06.mjs';

const contract = JSON.parse(readFileSync(new URL('../content/condition_lifecycle_v06.json', import.meta.url), 'utf8'));
const balance = JSON.parse(readFileSync(new URL('../content/balance.json', import.meta.url), 'utf8'));
const passed = [];
function test(name, fn) { fn(); passed.push(name); }
function fixture(options = {}) {
  return createConditionState(contract, {balance, objects: [
    ...['glass1', 'glass2', 'glass3', 'glass4'].map(id => ({id, kind: 'returned_glass', broken: true})),
    {id: 'hot_food', kind: 'station'}, {id: 'water', kind: 'reserved_water', sealed: false}
  ], reservedSlots: [0, 1, 2, 3, 4, 5].map(phase => ({id: `slot${phase}`, phase,
    kind: phase === 2 ? 'joint' : 'primary', allowed: ['F26', 'F32']})), ...options});
}
function work(s, kind, objectId, actorId = 'PLAYER') {
  const a = beginRecordedWork(s, {kind, objectId, actorId}); assert.equal(a.ok, true, a.reason);
  advanceConditionWorld(s, s.actions[a.actionId].endAt - s.world);
  assert.equal(s.actions[a.actionId].state, 'completed');
  return s.actions[a.actionId].receiptId;
}
function warning(s, glass = 'glass1', actorId = 'PLAYER') {
  const receipt = work(s, 'receive_return', glass, actorId);
  const h = announceGlassHazard(s, {returnReceiptId: receipt, objectId: glass});
  assert.equal(h.ok, true, h.reason); return h.incidentId;
}
function cut(s, glass = 'glass1', actorId = 'PLAYER') {
  const id = warning(s, glass, actorId);
  advanceConditionWorld(s, 3);
  const result = contactGlassHazard(s, {incidentId: id, actorId, method: 'bare_hand_contact'});
  assert.equal(result.ok, true, result.reason); return id;
}
function blood(s, incidentId, monsterId = 'F32', id = 'blood') {
  const r = announceBloodEncounter(s, {id, monsterId, incidentId, slotId: `slot${Math.floor(s.budget / 120)}`});
  assert.equal(r.ok, true, r.reason); return s.encounters[id];
}

test('Historical evidence requires a completed typed action, not an asserted boolean', () => {
  const s = fixture();
  assert.equal(announceGlassHazard(s, {returnReceiptId: 'asserted-true', objectId: 'glass1'}).ok, false);
  assert.equal(requireHistoricalReceipt(s, {id: true, kind: 'receive_return'}).ok, false);
  const a = beginRecordedWork(s, {kind: 'receive_return', objectId: 'glass1'});
  advanceConditionWorld(s, 1); assert.equal(Object.keys(s.receipts).length, 0);
  advanceConditionWorld(s, 1);
  const id = s.actions[a.actionId].receiptId;
  assert.equal(requireHistoricalReceipt(s, {id, kind: 'receive_return', objectId: 'glass1'}).ok, true);
  assert.equal(requireHistoricalReceipt(s, {id, kind: 'receive_return', objectId: 'glass2'}).ok, false);
});

test('A glass cut requires actual return, warning duration and later bare contact', () => {
  const s = fixture(), id = warning(s);
  assert.equal(contactGlassHazard(s, {incidentId: id, method: 'bare_hand_contact'}).reason, 'warning_not_elapsed');
  advanceConditionWorld(s, 2.99); assert.equal(s.actors.PLAYER.wound, null);
  advanceConditionWorld(s, 0.01);
  assert.equal(contactGlassHazard(s, {incidentId: id, method: 'bare_hand_contact'}).ok, true);
  assert.equal(s.actors.PLAYER.wound.state, 'fresh');
  assert.equal(s.actors.PLAYER.wound.endAt - s.world, 90);
});

test('Safe isolation prevents injury and cannot later be consumed as a blood fact', () => {
  const s = fixture(), id = warning(s);
  assert.equal(contactGlassHazard(s, {incidentId: id, method: 'sweep_and_isolate'}).ok, true);
  advanceConditionWorld(s, 3);
  assert.equal(contactGlassHazard(s, {incidentId: id, method: 'bare_hand_contact'}).ok, false);
  assert.equal(announceBloodEncounter(s, {id: 'b', monsterId: 'F32', incidentId: id, slotId: 'slot0'}).ok, false);
  assert.equal(s.actors.PLAYER.wound, null);
});

test('Repeated contact does not refresh the wound or create repeated injury receipts', () => {
  const s = fixture(), id = cut(s), end = s.actors.PLAYER.wound.endAt;
  advanceConditionWorld(s, 20);
  assert.equal(contactGlassHazard(s, {incidentId: id, method: 'bare_hand_contact'}).ok, false);
  assert.equal(s.actors.PLAYER.wound.endAt, end);
  advanceConditionWorld(s, 70);
  assert.equal(s.actors.PLAYER.wound.state, 'dry');
  assert.equal(s.nightCutCount, 1);
});

test('Ordinary minor contact never manufactures fresh blood', () => {
  const s = fixture(); applyOrdinaryMinorContact(s, 'PLAYER');
  assert.equal(s.actors.PLAYER.wound, null); assert.equal(s.nightCutCount, 0);
  advanceConditionWorld(s, 30); assert.equal(s.actors.PLAYER.minorUntil, null);
});

test('Only one bleeding episode per real actor and two per night can be created', () => {
  const s = fixture(); cut(s, 'glass1', 'PLAYER'); cut(s, 'glass2', 'COWORKER');
  const id = warning(s, 'glass3'); advanceConditionWorld(s, 3);
  assert.equal(contactGlassHazard(s, {incidentId: id, method: 'bare_hand_contact'}).ok, false);
  advanceConditionWorld(s, 90);
  assert.equal(contactGlassHazard(s, {incidentId: id, method: 'bare_hand_contact'}).reason, 'night_cut_cap');
  assert.equal(s.nightCutCount, 2);
});

test('Three-second self treatment reserves once, cancels cleanly and consumes once', () => {
  const s = fixture(); cut(s);
  for (const distanceTiles of [NaN, Infinity, -1]) {
    assert.equal(beginFirstAid(s, {distanceTiles}).reason, 'invalid_distance');
    assert.equal(s.inventory.dressings, 2);
  }
  const first = beginFirstAid(s, {}); assert.equal(first.ok, true); assert.equal(s.inventory.dressings, 1);
  advanceConditionWorld(s, 2); assert.equal(s.actors.PLAYER.wound.state, 'fresh');
  assert.equal(cancelRecordedWork(s, first.actionId).ok, true); assert.equal(s.inventory.dressings, 2);
  assert.equal(cancelRecordedWork(s, first.actionId).ok, false); assert.equal(s.inventory.dressings, 2);
  const second = beginFirstAid(s, {}); advanceConditionWorld(s, 3);
  assert.equal(s.actions[second.actionId].state, 'completed');
  assert.equal(s.actors.PLAYER.wound.state, 'dressed'); assert.equal(s.inventory.dressings, 1);
  assert.equal(s.actors.PLAYER.minorUntil, null);
});

test('Natural expiry during treatment immediately releases its reserved dressing', () => {
  const s = fixture(); cut(s); advanceConditionWorld(s, 89);
  const a = beginFirstAid(s, {}); assert.equal(a.ok, true);
  advanceConditionWorld(s, 1);
  assert.equal(s.actors.PLAYER.wound.state, 'dry');
  assert.equal(s.actions[a.actionId].state, 'cancelled'); assert.equal(s.inventory.dressings, 2);
});

test('Pause freezes wounds, treatment, movement and both clocks', () => {
  const s = fixture(); cut(s); const a = beginFirstAid(s, {});
  const before = {world: s.world, budget: s.budget, end: s.actors.PLAYER.wound.endAt};
  setConditionPause(s, true); advanceConditionWorld(s, 100);
  assert.equal(walkActor(s, {distanceTiles: 6}).ok, false);
  assert.equal(s.world, before.world); assert.equal(s.budget, before.budget);
  assert.equal(s.actors.PLAYER.wound.endAt, before.end); assert.equal(s.actions[a.actionId].state, 'running');
  setConditionPause(s, false); advanceConditionWorld(s, 3); assert.equal(s.actors.PLAYER.wound.state, 'dressed');
});

test('Reactive arrival takes 12 seconds and treatment before it prevents F32', () => {
  const s = fixture(), incident = cut(s), e = blood(s, incident);
  assert.equal(e.arrivalAt - s.world, 12);
  advanceConditionWorld(s, 2); beginFirstAid(s, {}); advanceConditionWorld(s, 3);
  assert.equal(e.state, 'PREVENTED'); assert.equal(s.slots.slot0.state, 'CONSUMED');
  advanceConditionWorld(s, 20); assert.equal(e.state, 'PREVENTED');
  assert.equal(announceBloodEncounter(s, {id: 'again', monsterId: 'F26', incidentId: incident, slotId: 'slot0'}).ok, false);
  const second = cut(s, 'glass2', 'COWORKER');
  assert.equal(announceBloodEncounter(s, {id: 'replacement', monsterId: 'F32', incidentId: second, slotId: 'slot0'}).reason, 'no_pre_reserved_slot');
});

test('An active F32 leaves after its real wound is treated; decline cannot clear it', () => {
  const s = fixture(), e = blood(s, cut(s));
  advanceConditionWorld(s, 12); assert.equal(e.state, 'ACTIVE');
  assert.equal(declineOptionalEncounter(s, e.id).ok, false);
  beginFirstAid(s, {}); advanceConditionWorld(s, 3); assert.equal(e.state, 'ACTIVE');
  advanceConditionWorld(s, 3); assert.equal(e.state, 'RESOLVED');
});

test('F26 requires actual movement marks; treatment alone leaves the real trace task', () => {
  const s = fixture(), incident = cut(s);
  assert.equal(announceBloodEncounter(s, {id: 'trace', monsterId: 'F26', incidentId: incident, slotId: 'slot0'}).reason, 'no_actual_blood_trace');
  walkActor(s, {distanceTiles: 4}); assert.equal(Object.keys(s.traces).length, 2);
  const e = blood(s, incident, 'F26', 'trace'); beginFirstAid(s, {}); advanceConditionWorld(s, 3);
  assert.equal(e.state, 'ANNOUNCED'); advanceConditionWorld(s, 9); assert.equal(e.state, 'ACTIVE');
  for (const traceId of e.boundTraceIds) work(s, 'wipe_trace', traceId);
  assert.equal(e.state, 'ACTIVE'); assert.equal(Object.values(s.waste).filter(x => !x.sealed).length, 2);
  for (const waste of Object.values(s.waste)) work(s, 'seal_waste', waste.id);
  advanceConditionWorld(s, 3); assert.equal(e.state, 'RESOLVED');
});

test('Actual marks are capped and naturally expire without new blood or free cleanup receipts', () => {
  const s = fixture(); cut(s); walkActor(s, {distanceTiles: 30});
  assert.equal(Object.values(s.traces).filter(t => t.live).length, 6);
  advanceConditionWorld(s, 30);
  assert.equal(Object.values(s.traces).filter(t => t.live).length, 0);
  assert.equal(Object.keys(s.waste).length, 0);
});

test('Natural target expiry produces safe departure, not a fabricated player solution', () => {
  const s = fixture(), incident = cut(s); walkActor(s, {distanceTiles: 2});
  const e = blood(s, incident, 'F26'); advanceConditionWorld(s, 100);
  assert.equal(e.state, 'SAFE_RETURNED'); assert.equal(Object.keys(s.waste).length, 0);
});

test('Reactive scheduling rejects insufficient current-phase budget even with fresh blood', () => {
  const s = fixture(); advanceConditionWorld(s, 80); const id = cut(s);
  assert.equal(announceBloodEncounter(s, {id: 'late', monsterId: 'F32', incidentId: id, slotId: 'slot0'}).reason, 'insufficient_phase_budget');
  assert.equal(s.slots.slot0.state, 'RESERVED');
});

test('A reserved F21 child slot is not a wound; real occupancy and 40-second failure produce it', () => {
  const s = fixture(); advanceConditionWorld(s, 240);
  assert.equal(announceBloodEncounter(s, {id: 'fake', monsterId: 'F32', incidentId: 'future-accident', slotId: 'slot2'}).ok, false);
  const receipt = work(s, 'station_work', 'hot_food', 'COWORKER');
  const hazard = announceStationGlassFault(s, {workReceiptId: receipt, objectId: 'hot_food', actorId: 'COWORKER'});
  assert.equal(hazard.ok, true); advanceConditionWorld(s, 39); assert.equal(s.actors.COWORKER.wound, null);
  advanceConditionWorld(s, 1); assert.equal(s.actors.COWORKER.wound.state, 'fresh');
  assert.equal(blood(s, hazard.incidentId).state, 'ANNOUNCED');
});

test('Actual departure and shutdown prevent the F21 cut and its reactive child', () => {
  const s = fixture(); advanceConditionWorld(s, 240);
  const r = work(s, 'station_work', 'hot_food', 'COWORKER');
  const h = announceStationGlassFault(s, {workReceiptId: r, objectId: 'hot_food', actorId: 'COWORKER'});
  walkActor(s, {actorId: 'COWORKER', distanceTiles: 3}); work(s, 'isolate_station', 'hot_food');
  advanceConditionWorld(s, 40); assert.equal(s.actors.COWORKER.wound, null);
  assert.equal(s.incidents[h.incidentId].stage, 'prevented');
  assert.equal(announceBloodEncounter(s, {id: 'b', monsterId: 'F32', incidentId: h.incidentId, slotId: 'slot2'}).ok, false);
});

test('Precision costs cannot cross a schedule marker and exact-boundary commit comes first', () => {
  const s = fixture({markers: [{id: 'order', at: 10}]}); advanceConditionWorld(s, 3);
  assert.equal(beginPrecisionAttempt(s, {costSeconds: 8}).reason, 'would_cross_schedule_marker');
  const q = beginPrecisionAttempt(s, {costSeconds: 7}); assert.equal(q.ok, true);
  advancePrecisionLocal(s, 20); assert.equal(s.world, 3); assert.equal(s.budget, 3);
  setConditionPause(s, true); assert.equal(advancePrecisionLocal(s, 5).ok, false); setConditionPause(s, false);
  assert.equal(finishPrecisionAttempt(s, {attemptId: q.attemptId, outcome: 'cancelled'}).ok, true);
  assert.equal(s.world, 3); assert.equal(s.budget, 10);
  assert.ok(s.log.findIndex(x => x.type === 'precision_committed') < s.log.findIndex(x => x.type === 'schedule_marker' && x.id === 'order'));
  assert.equal(finishPrecisionAttempt(s, {attemptId: q.attemptId, outcome: 'cancelled'}).ok, false); assert.equal(s.budget, 10);
});

test('Default phase boundaries reject 119-to-121 precision and commit before exact 120 dispatch', () => {
  const s = fixture(); advanceConditionWorld(s, 119);
  assert.equal(beginPrecisionAttempt(s, {costSeconds: 2}).reason, 'would_cross_schedule_marker');
  assert.equal(s.budget, 119); assert.equal(s.precision, null);
  const q = beginPrecisionAttempt(s, {costSeconds: 1}); assert.equal(q.ok, true);
  assert.equal(finishPrecisionAttempt(s, {attemptId: q.attemptId, outcome: 'success'}).ok, true);
  assert.equal(s.world, 119); assert.equal(s.budget, 120);
  const committed = s.log.findIndex(x => x.type === 'precision_committed' && x.attemptId === q.attemptId);
  const dispatched = s.log.findIndex(x => x.type === 'schedule_marker' && x.id === 'phase_end_1');
  assert.ok(committed >= 0 && dispatched > committed);
  assert.equal(s.markers.find(x => x.id === 'phase_end_1').dispatched, true);
});

test('Caller markers cannot replace fixed phase, manager, or true-six boundaries', () => {
  const conflicting = [
    ...[1, 2, 3, 4, 5].map(phase => ({id: `phase_end_${phase}`, at: 900 + phase, dispatched: true})),
    {id: 'manager_arrival', at: 999, dispatched: true},
    {id: 'true_06_00', at: 999, dispatched: true}
  ];
  const s = fixture({markers: [...conflicting, {id: 'custom_order', at: 150}]});
  for (let phase = 1; phase <= 5; phase++) {
    const markers = s.markers.filter(x => x.id === `phase_end_${phase}`);
    assert.equal(markers.length, 1); assert.equal(markers[0].at, phase * 120);
    assert.equal(markers[0].dispatched, false);
  }
  assert.equal(s.markers.find(x => x.id === 'manager_arrival').at, 700);
  assert.equal(s.markers.find(x => x.id === 'true_06_00').at, 720);
  assert.equal(s.markers.find(x => x.id === 'custom_order').at, 150);
  advanceConditionWorld(s, 119);
  assert.equal(beginPrecisionAttempt(s, {costSeconds: 2}).reason, 'would_cross_schedule_marker');
  advanceConditionWorld(s, 601);
  assert.equal(s.budget, 720); assert.equal(s.managerArrived, true);
  assert.equal(s.mode, 'handover_only');
});

test('Precision budget cost does not secretly advance wound or movement time', () => {
  const s = fixture(), incident = cut(s), until = s.actors.PLAYER.wound.endAt;
  const beforeWorld = s.world, beforeBudget = s.budget;
  const q = beginPrecisionAttempt(s, {costSeconds: 8}); assert.equal(q.ok, true);
  advancePrecisionLocal(s, 5); finishPrecisionAttempt(s, {attemptId: q.attemptId, outcome: 'failed'});
  assert.equal(s.world, beforeWorld); assert.equal(s.budget, beforeBudget + 8);
  assert.equal(s.actors.PLAYER.wound.endAt, until); assert.equal(s.incidents[incident].cut, true);
});

test('Due-at-six promises settle before critical check and handover grants no extra work time', () => {
  const s = fixture(); assert.equal(acceptDawnPromise(s, {id: 'F53-water', objectId: 'water'}).ok, true);
  work(s, 'seal_water', 'water'); offerOptionalEncounter(s, 'unaccepted-F11');
  advanceConditionWorld(s, 718);
  assert.equal(s.budget, 720); assert.equal(s.promises['F53-water'].state, 'RESOLVED');
  assert.equal(s.encounters['unaccepted-F11'].state, 'DECLINED'); assert.equal(s.mode, 'handover_only');
  assert.equal(s.managerArrived, true);
  assert.ok(s.log.findIndex(x => x.type === 'dawn_promise_settled') < s.log.findIndex(x => x.type === 'critical_threat_check'));
  assert.equal(advanceConditionWorld(s, 100).advanced, 0); assert.equal(s.budget, 720);
  assert.equal(beginRecordedWork(s, {kind: 'receive_return', objectId: 'glass1'}).ok, false);
  const p = fixture({initialSan: 1}); acceptDawnPromise(p, {id: 'F53-water', objectId: 'water'});
  work(p, 'seal_water', 'water'); advanceConditionWorld(p, 698);
  applyConditionFear(p, {amount: 1, sourceId: 'late-observed-threat'}); advanceConditionWorld(p, 20);
  assert.equal(p.mode, 'failed_shift'); assert.equal(p.promises['F53-water'].state, 'RESOLVED');
  assert.ok(p.log.findIndex(x => x.type === 'dawn_promise_settled') < p.log.findIndex(x => x.type === 'panic_timeout'));
  const future = fixture({initialSan: 1}); acceptDawnPromise(future, {id: 'F53-water', objectId: 'water'});
  work(future, 'seal_water', 'water'); advanceConditionWorld(future, 708);
  assert.equal(applyConditionFear(future, {amount: 1, sourceId: 'pre-dawn-observed-threat'}).ok, true);
  advanceConditionWorld(future, 10);
  assert.equal(future.budget, 720); assert.ok(future.panic.deadline > future.world);
  assert.equal(future.panic.active, true); assert.equal(future.mode, 'failed_shift');
  assert.equal(future.promises['F53-water'].state, 'RESOLVED');
  assert.ok(future.log.findIndex(x => x.type === 'dawn_promise_settled') < future.log.findIndex(x => x.type === 'critical_threat_check'));
  assert.equal(advanceConditionWorld(future, 100).advanced, 0);
});

test('Unresolved actual contaminated waste leaves a critical encounter at six', () => {
  const s = fixture(); advanceConditionWorld(s, 480);
  const incident = cut(s); walkActor(s, {distanceTiles: 2});
  const e = blood(s, incident, 'F26'); advanceConditionWorld(s, 12);
  beginFirstAid(s, {}); advanceConditionWorld(s, 3); work(s, 'wipe_trace', e.boundTraceIds[0]);
  advanceConditionWorld(s, 720 - s.budget);
  assert.equal(e.state, 'ACTIVE'); assert.equal(s.mode, 'failed_shift');
  assert.equal(advanceConditionWorld(s, 100).advanced, 0);
});

test('Optional refusal is terminal and cannot regenerate the same offer', () => {
  const s = fixture(); offerOptionalEncounter(s, 'F11');
  assert.equal(declineOptionalEncounter(s, 'F11').ok, true);
  assert.equal(offerOptionalEncounter(s, 'F11').ok, false);
  advanceConditionWorld(s, 120); assert.equal(s.encounters.F11.state, 'DECLINED');
});

test('Portable emergency stabilization succeeds while walking before an 18-second station trip could finish', () => {
  const s = fixture({initialSan: 1});
  assert.equal(applyConditionFear(s, {amount: 1, sourceId: 'observed-threat'}).ok, true);
  assert.equal(s.panic.deadline - s.world, 20);
  assert.equal(beginPortableStabilization(s).ok, true);
  assert.equal(walkActor(s, {distanceTiles: 1, gait: 'sprint'}).reason, 'stabilization_forbids_sprint');
  walkActor(s, {distanceTiles: 24}); // 8 seconds, still short of a 54-tile/18-second station route.
  assert.equal(s.world, 8); assert.equal(s.san, 15); assert.equal(s.panic.active, false);
  assert.equal(s.panic.used, true);
  assert.equal(applyOrdinaryMinorContact(s, 'PLAYER').ok, true);
  assert.notEqual(s.actors.PLAYER.minorUntil, null); // Fear-only grace is not physical invulnerability.
});

test('Interrupted stabilization preserves only completed world progress and pays once', () => {
  const s = fixture({initialSan: 1}); applyConditionFear(s, {amount: 1, sourceId: 'observed-threat'});
  beginPortableStabilization(s); walkActor(s, {distanceTiles: 9});
  assert.equal(s.panic.progress, 3);
  applyOrdinaryMinorContact(s, 'PLAYER'); advanceConditionWorld(s, 2);
  assert.equal(s.panic.progress, 3); assert.equal(s.panic.stabilizing, false);
  assert.equal(beginPortableStabilization(s).remaining, 5); walkActor(s, {distanceTiles: 15});
  assert.equal(s.san, 15); assert.equal(s.log.filter(x => x.type === 'portable_stabilization_completed').length, 1);
  assert.equal(beginPortableStabilization(s).ok, false);
  advanceConditionWorld(s, 6); applyConditionFear(s, {amount: 15, sourceId: 'new-observed-threat'});
  assert.equal(s.panic.active, true); assert.equal(beginPortableStabilization(s).reason, 'night_stabilization_spent');
});

test('Repeated zero SAN cannot reset the same 20-second episode and pause grants no progress', () => {
  const s = fixture({initialSan: 1}); applyConditionFear(s, {amount: 1, sourceId: 'first-threat'});
  beginPortableStabilization(s); advanceConditionWorld(s, 2); interruptPortableStabilization(s, 'player_action');
  const deadline = s.panic.deadline;
  advanceConditionWorld(s, 2); applyConditionFear(s, {amount: 1, sourceId: 'second-threat'});
  assert.equal(s.panic.deadline, deadline); assert.equal(s.panic.episode, 1);
  setConditionPause(s, true); advanceConditionWorld(s, 100);
  assert.equal(s.world, 4); assert.equal(s.panic.progress, 2);
  setConditionPause(s, false); advanceConditionWorld(s, 16);
  assert.equal(s.mode, 'failed_shift'); assert.equal(s.world, 20);
});

test('Walking configuration is honored and portable stabilization never freezes an approaching encounter', () => {
  const disabled = structuredClone(balance); disabled.resources.san.portable_stabilization_allowed_while_walking = false;
  const d = fixture({initialSan: 1, balance: disabled}); applyConditionFear(d, {amount: 1, sourceId: 'threat'});
  beginPortableStabilization(d); walkActor(d, {distanceTiles: 6});
  assert.equal(d.panic.progress, 0); assert.equal(d.panic.stabilizing, false);
  const s = fixture({initialSan: 1}), e = blood(s, cut(s)); advanceConditionWorld(s, 5);
  applyConditionFear(s, {amount: 1, sourceId: 'observed-blood-visitor'}); beginPortableStabilization(s);
  walkActor(s, {distanceTiles: 24});
  assert.equal(s.san, 15); assert.equal(e.state, 'ACTIVE'); assert.equal(s.actors.PLAYER.wound.state, 'fresh');
});

console.log(JSON.stringify({status: 'PASS', scenarioCount: passed.length, scenarios: passed,
  scope: 'Bounded headless causal/action chains only. No real collision, touch, full actor AI, F32 invitation/geometry, full identity or all sixty encounter adapters verified.'}, null, 2));
