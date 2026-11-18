import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {
  createConditionState, setConditionPause, beginRecordedWork, cancelRecordedWork,
  requireHistoricalReceipt, announceGlassHazard, activateStationFaultEncounter, announceStationGlassFault,
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
  ], reservedSlots: [...[0, 1, 2, 3, 4, 5].map(phase => ({id: `slot${phase}`, phase,
    kind: phase === 2 ? 'joint' : 'primary', allowed: ['F26', 'F32'],
    ...(phase === 2 ? {parentSlotId: 'f21-slot2'} : {})})),
    {id: 'f21-slot2', phase: 2, kind: 'primary', allowed: ['F21']}], ...options});
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
  assert.equal(activateStationFaultEncounter(s, {id: 'f21', objectId: 'hot_food', slotId: 'f21-slot2'}).ok, true);
  assert.equal(beginPrecisionAttempt(s, {costSeconds: 1}).reason, 'critical_resolution_reserved');
  const hazard = announceStationGlassFault(s, {workReceiptId: receipt, objectId: 'hot_food', actorId: 'COWORKER', sourceEncounterId: 'f21'});
  assert.equal(hazard.ok, true); advanceConditionWorld(s, 39); assert.equal(s.actors.COWORKER.wound, null);
  advanceConditionWorld(s, 1); assert.equal(s.actors.COWORKER.wound.state, 'fresh');
  assert.equal(blood(s, hazard.incidentId).state, 'ANNOUNCED');
});

test('Actual departure and shutdown prevent the F21 cut and its reactive child', () => {
  const s = fixture(); advanceConditionWorld(s, 240);
  const r = work(s, 'station_work', 'hot_food', 'COWORKER');
  activateStationFaultEncounter(s, {id: 'f21', objectId: 'hot_food', slotId: 'f21-slot2'});
  const h = announceStationGlassFault(s, {workReceiptId: r, objectId: 'hot_food', actorId: 'COWORKER', sourceEncounterId: 'f21'});
  walkActor(s, {actorId: 'COWORKER', distanceTiles: 3}); work(s, 'isolate_station', 'hot_food');
  advanceConditionWorld(s, 40); assert.equal(s.actors.COWORKER.wound, null);
  assert.equal(s.incidents[h.incidentId].stage, 'prevented');
  assert.equal(s.encounters.f21.state, 'PREVENTED'); assert.equal(s.slots.slot2.state, 'RELEASED');
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
  assert.equal(s.encounters['F53-water'].deadlinePolicy, 'true_six_promise');
  const ordinaryPrecision = beginPrecisionAttempt(s, {costSeconds: 1}); assert.equal(ordinaryPrecision.ok, true);
  finishPrecisionAttempt(s, {attemptId: ordinaryPrecision.attemptId, outcome: 'success'});
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

test('F26 cannot arrive after every real trace expired during its existing warning', () => {
  const s = fixture(); advanceConditionWorld(s, 360);
  const incident = cut(s); walkActor(s, {distanceTiles: 2});
  const trace = Object.values(s.traces)[0]; advanceConditionWorld(s, 20);
  assert.ok(Math.abs(trace.expiresAt - s.world - 10) < 1e-8);
  const e = blood(s, incident, 'F26', 'expired-redcap'); advanceConditionWorld(s, 12);
  assert.equal(trace.live, false); assert.equal(s.actors.PLAYER.wound.state, 'fresh');
  assert.equal(e.state, 'SAFE_RETURNED'); assert.equal(e.endCause, 'no_actual_trace_at_arrival');
  assert.equal(s.slots.slot3.state, 'CONSUMED');
  walkActor(s, {distanceTiles: 2}); advanceConditionWorld(s, 1);
  assert.equal(e.state, 'SAFE_RETURNED');
  assert.equal(announceBloodEncounter(s, {id: 'replacement', monsterId: 'F26', incidentId: incident, slotId: 'slot3'}).ok, false);
});

test('F26 may bind an actual later mark without renewing the warning or any mark lifetime', () => {
  const s = fixture(); advanceConditionWorld(s, 360);
  const incident = cut(s); walkActor(s, {distanceTiles: 2});
  const old = Object.values(s.traces)[0]; advanceConditionWorld(s, 20);
  const e = blood(s, incident, 'F26', 'new-real-trace'), arrivalAt = e.arrivalAt;
  advanceConditionWorld(s, 11); assert.equal(old.live, false);
  walkActor(s, {distanceTiles: 2});
  const added = Object.values(s.traces).find(t => t.id !== old.id), expiry = added.expiresAt;
  advanceConditionWorld(s, arrivalAt - s.world);
  assert.equal(e.state, 'ACTIVE'); assert.deepEqual(e.boundTraceIds, [added.id]);
  assert.equal(e.arrivalAt, arrivalAt); assert.equal(added.expiresAt, expiry);
});

test('One return cannot produce duplicate roots while two different returns can proceed together', () => {
  const s = fixture(); const first = beginRecordedWork(s, {kind: 'receive_return', objectId: 'glass1'});
  assert.equal(first.ok, true);
  assert.equal(beginRecordedWork(s, {kind: 'receive_return', actorId: 'COWORKER', objectId: 'glass1'}).reason, 'object_reserved_by_action');
  assert.equal(beginRecordedWork(s, {kind: 'receive_return', actorId: 'COWORKER', objectId: 'glass2'}).ok, true);
  advanceConditionWorld(s, 2);
  for (const objectId of ['glass1', 'glass2']) assert.equal(Object.values(s.receipts).filter(r => r.kind === 'receive_return' && r.objectId === objectId).length, 1);
  assert.equal(beginRecordedWork(s, {kind: 'receive_return', actorId: 'COWORKER', objectId: 'glass1'}).reason, 'not_pending_return');
});

test('One waste object consumes one bag and cancellation transfers the same operation cleanly', () => {
  const s = fixture(); cut(s); walkActor(s, {distanceTiles: 2});
  work(s, 'wipe_trace', Object.keys(s.traces)[0]); const wasteId = Object.keys(s.waste)[0], bags = s.inventory.bags;
  const a = beginRecordedWork(s, {kind: 'seal_waste', objectId: wasteId});
  assert.equal(beginRecordedWork(s, {kind: 'seal_waste', actorId: 'COWORKER', objectId: wasteId}).reason, 'object_reserved_by_action');
  assert.equal(s.inventory.bags, bags - 1); cancelRecordedWork(s, a.actionId);
  assert.equal(s.inventory.bags, bags);
  assert.equal(beginRecordedWork(s, {kind: 'seal_waste', actorId: 'COWORKER', objectId: wasteId}).ok, true);
  advanceConditionWorld(s, 2); assert.equal(s.inventory.bags, bags - 1);
  assert.equal(Object.values(s.receipts).filter(r => r.kind === 'seal_waste' && r.objectId === wasteId).length, 1);
});

test('A trace expiring during a wipe releases the worker without a fictitious cleanup receipt', () => {
  const s = fixture(); cut(s); walkActor(s, {distanceTiles: 2});
  const trace = Object.values(s.traces)[0]; advanceConditionWorld(s, 29.5);
  const wipe = beginRecordedWork(s, {kind: 'wipe_trace', objectId: trace.id}); assert.equal(wipe.ok, true);
  assert.equal(beginRecordedWork(s, {kind: 'wipe_trace', actorId: 'COWORKER', objectId: trace.id}).reason, 'object_reserved_by_action');
  advanceConditionWorld(s, 0.5);
  assert.equal(s.actions[wipe.actionId].state, 'cancelled'); assert.equal(s.actions[wipe.actionId].receiptId, undefined);
  assert.equal(Object.keys(s.waste).length, 0);
  assert.equal(beginRecordedWork(s, {kind: 'receive_return', objectId: 'glass2'}).ok, true);
});

test('Two healers cannot reserve the same wound and expiry or cancellation releases its reservation', () => {
  const s = fixture(); cut(s);
  const a = beginFirstAid(s, {}); assert.equal(a.ok, true);
  assert.equal(beginFirstAid(s, {actorId: 'COWORKER', targetId: 'PLAYER'}).reason, 'wound_reserved_by_action');
  assert.equal(s.inventory.dressings, 1); cancelRecordedWork(s, a.actionId);
  const b = beginFirstAid(s, {actorId: 'COWORKER', targetId: 'PLAYER'}); assert.equal(b.ok, true);
  cancelRecordedWork(s, b.actionId); advanceConditionWorld(s, 89);
  const atExpiry = beginFirstAid(s, {}); assert.equal(atExpiry.ok, true); advanceConditionWorld(s, 1);
  assert.equal(s.actions[atExpiry.actionId].state, 'cancelled'); assert.equal(s.inventory.dressings, 2);
  assert.equal(Object.keys(s.actionLocks).length, 0);
});

test('Dawn acceptance cannot overwrite a live instance or revive an already declined offer', () => {
  const s = fixture(); offerOptionalEncounter(s, 'same-offer');
  assert.equal(acceptDawnPromise(s, {id: 'same-offer', objectId: 'water'}).reason, 'invalid_promise');
  assert.equal(s.encounters['same-offer'].state, 'ANNOUNCED');
  declineOptionalEncounter(s, 'same-offer');
  assert.equal(acceptDawnPromise(s, {id: 'same-offer', objectId: 'water'}).reason, 'invalid_promise');
  assert.equal(s.encounters['same-offer'].state, 'DECLINED'); assert.equal(s.promises['same-offer'], undefined);
  assert.equal(acceptDawnPromise(s, {id: 'new-declared-contract', objectId: 'water'}).ok, true);
});

test('An interrupted final movement counts only advanced distance and cannot write post-failure blood marks', () => {
  const s = fixture({initialSan: 1}); cut(s);
  applyConditionFear(s, {amount: 1, sourceId: 'visible-threat'}); advanceConditionWorld(s, 19.9);
  const before = s.world, receipts = Object.keys(s.receipts).length;
  const result = walkActor(s, {distanceTiles: 2});
  assert.equal(s.mode, 'failed_shift'); assert.ok(Math.abs(s.world - before - 0.1) < 1e-8);
  assert.ok(Math.abs(result.distanceTravelled - 0.3) < 1e-8);
  assert.equal(Object.keys(s.traces).length, 0); assert.equal(Object.keys(s.receipts).length, receipts);
  assert.equal(walkActor(s, {distanceTiles: 2}).ok, false);
});

test('Pre-injury travel cannot shorten the first two-tile bleeding movement interval', () => {
  const s = fixture(); walkActor(s, {distanceTiles: 1.5}); cut(s);
  walkActor(s, {distanceTiles: 0.5}); assert.equal(Object.keys(s.traces).length, 0);
  walkActor(s, {distanceTiles: 1.5}); assert.equal(Object.keys(s.traces).length, 1);
});

test('Movement crossing an actual cut or natural expiry counts only its fresh-wound interval', () => {
  const s = fixture(); advanceConditionWorld(s, 240);
  const receipt = work(s, 'station_work', 'hot_food');
  activateStationFaultEncounter(s, {id: 'f21', objectId: 'hot_food', slotId: 'f21-slot2'});
  const h = announceStationGlassFault(s, {workReceiptId: receipt, objectId: 'hot_food', actorId: 'PLAYER', sourceEncounterId: 'f21'});
  const cutAt = s.incidents[h.incidentId].readyAt;
  advanceConditionWorld(s, 39.9); // Leaving the cell needs 1/3 second, so the real cut occurs first.
  walkActor(s, {distanceTiles: 2});
  assert.equal(s.actors.PLAYER.wound.startedAt, cutAt);
  assert.ok(Math.abs(s.actors.PLAYER.distanceSinceMark - 1.7) < 1e-8);
  assert.equal(Object.keys(s.traces).length, 0); // The first 0.3 tiles preceded the cut.
  walkActor(s, {distanceTiles: 0.3}); assert.equal(Object.keys(s.traces).length, 1);

  const expiring = fixture(); cut(expiring); walkActor(expiring, {distanceTiles: 1.5});
  advanceConditionWorld(expiring, 89.4); // Only 0.1 world second of fresh blood remains.
  walkActor(expiring, {distanceTiles: 2});
  assert.equal(expiring.actors.PLAYER.wound.state, 'dry');
  assert.equal(Object.keys(expiring.traces).length, 0); // 1.5 + 0.3 bleeding tiles never reached two.
  assert.equal(expiring.actors.PLAYER.distanceSinceMark, 0);
});

test('A panic ending the shift mid-seal refunds its uncommitted bag and clears the object reservation', () => {
  const s = fixture({initialSan: 1}); cut(s); walkActor(s, {distanceTiles: 2});
  work(s, 'wipe_trace', Object.keys(s.traces)[0]); const wasteId = Object.keys(s.waste)[0], bags = s.inventory.bags;
  applyConditionFear(s, {amount: 1, sourceId: 'visible-threat'}); advanceConditionWorld(s, 19);
  const seal = beginRecordedWork(s, {kind: 'seal_waste', objectId: wasteId}); assert.equal(seal.ok, true);
  assert.equal(s.inventory.bags, bags - 1); advanceConditionWorld(s, 2);
  assert.equal(s.mode, 'failed_shift'); assert.equal(s.actions[seal.actionId].state, 'cancelled');
  assert.equal(s.waste[wasteId].sealed, false); assert.equal(s.inventory.bags, bags);
  assert.equal(s.actions[seal.actionId].receiptId, undefined); assert.equal(Object.keys(s.actionLocks).length, 0);
});

test('A work receipt cannot impersonate the reserved and actually activated F21 glass variant', () => {
  const s = fixture(); advanceConditionWorld(s, 240);
  const receipt = work(s, 'station_work', 'hot_food');
  assert.equal(announceStationGlassFault(s, {workReceiptId: receipt, objectId: 'hot_food', actorId: 'PLAYER', sourceEncounterId: 'invented', f21Active: true}).reason, 'actual_active_f21_glass_variant_missing');
  assert.equal(activateStationFaultEncounter(s, {id: 'invalid-slot', objectId: 'hot_food', slotId: 'slot2'}).reason, 'no_pre_reserved_f21_slot');
  advanceConditionWorld(s, 40); assert.equal(s.actors.PLAYER.wound, null); assert.equal(Object.keys(s.incidents).length, 0);
  const activation = activateStationFaultEncounter(s, {id: 'actual-f21', objectId: 'hot_food', slotId: 'f21-slot2'});
  assert.equal(activation.ok, true); assert.equal(s.receipts[activation.receiptId].kind, 'station_fault_activation');
  const hazard = announceStationGlassFault(s, {workReceiptId: receipt, objectId: 'hot_food', actorId: 'PLAYER', sourceEncounterId: 'actual-f21'});
  assert.equal(hazard.ok, true); assert.equal(s.incidents[hazard.incidentId].sourceActivationReceiptId, activation.receiptId);
  advanceConditionWorld(s, 40); assert.equal(s.actors.PLAYER.wound.state, 'fresh');
});

test('Resolving F21 after its real accident retains the pre-reserved child and the actual wound', () => {
  const s = fixture(); advanceConditionWorld(s, 240);
  const receipt = work(s, 'station_work', 'hot_food', 'COWORKER');
  activateStationFaultEncounter(s, {id: 'f21', objectId: 'hot_food', slotId: 'f21-slot2'});
  const h = announceStationGlassFault(s, {workReceiptId: receipt, objectId: 'hot_food', actorId: 'COWORKER', sourceEncounterId: 'f21'});
  advanceConditionWorld(s, 40); walkActor(s, {actorId: 'COWORKER', distanceTiles: 3});
  work(s, 'isolate_station', 'hot_food');
  assert.equal(s.encounters.f21.state, 'RESOLVED'); assert.equal(s.slots.slot2.state, 'RESERVED');
  assert.equal(s.actors.COWORKER.wound.state, 'fresh');
  assert.equal(blood(s, h.incidentId, 'F32', 'real-child').state, 'ANNOUNCED');
});

test('N04 carryover expires at budget600 from its origin slot and stops unfinished movement', () => {
  const s = fixture();
  const q = beginPrecisionAttempt(s, {costSeconds: 8}); assert.equal(q.ok, true);
  finishPrecisionAttempt(s, {attemptId: q.attemptId, outcome: 'success'});
  advanceConditionWorld(s, 352); // Actual world352, phase budget360; N04 is allowed for F26.
  const incident = cut(s); walkActor(s, {distanceTiles: 2});
  const e = blood(s, incident, 'F26', 'bounded-redcap'); advanceConditionWorld(s, 12);
  work(s, 'wipe_trace', Object.keys(s.traces)[0]);
  assert.equal(e.originPhaseIndex, 3); assert.equal(e.carryoverDeadlineBudget, 600);
  advanceConditionWorld(s, 480 - s.budget);
  assert.equal(s.mode, 'night'); assert.equal(e.state, 'ACTIVE'); assert.equal(e.carryoverDeadlineBudget, 600);
  advanceConditionWorld(s, 599 - s.budget);
  const beforeWorld = s.world, moved = walkActor(s, {distanceTiles: 60});
  assert.equal(s.mode, 'failed_shift'); assert.equal(s.budget, 600);
  assert.ok(Math.abs(s.world - 592) < 1e-8); assert.ok(Math.abs(s.world - beforeWorld - 1) < 1e-8);
  assert.ok(Math.abs(moved.distanceTravelled - 3) < 1e-8);
  assert.equal(e.state, 'ACTIVE'); // Failure does not pretend the unsealed waste was resolved.
  assert.deepEqual(s.log.find(x => x.type === 'carryover_deadline_exceeded').encounterIds, ['bounded-redcap']);
  assert.equal(advanceConditionWorld(s, 120).advanced, 0);
});

test('A genuine F21 resolution at its carryover boundary commits before the expiry check', () => {
  const s = fixture({reservedSlots: [{id: 'f21-slot2', phase: 2, kind: 'primary', allowed: ['F21']}]});
  advanceConditionWorld(s, 240); const receipt = work(s, 'station_work', 'hot_food');
  activateStationFaultEncounter(s, {id: 'f21-last-tick', objectId: 'hot_food', slotId: 'f21-slot2'});
  announceStationGlassFault(s, {workReceiptId: receipt, objectId: 'hot_food', actorId: 'PLAYER', sourceEncounterId: 'f21-last-tick'});
  advanceConditionWorld(s, 40); walkActor(s, {distanceTiles: 1});
  advanceConditionWorld(s, 478 - s.budget);
  const isolate = beginRecordedWork(s, {kind: 'isolate_station', objectId: 'hot_food'}); assert.equal(isolate.ok, true);
  advanceConditionWorld(s, 2);
  assert.equal(s.budget, 480); assert.equal(s.actions[isolate.actionId].state, 'completed');
  assert.equal(s.encounters['f21-last-tick'].state, 'RESOLVED'); assert.equal(s.mode, 'night');
  assert.equal(s.log.some(x => x.type === 'carryover_deadline_exceeded'), false);
});

test('Actual night entry at SAN zero starts one panic and permits the existing free stabilization', () => {
  const s = fixture({initialSan: 0, mode: 'night'});
  assert.equal(s.panic.active, true); assert.equal(s.panic.episode, 1); assert.equal(s.panic.deadline, 20);
  assert.equal(s.log.find(x => x.type === 'panic_started').trigger, 'night_entry');
  setConditionPause(s, true); advanceConditionWorld(s, 60);
  assert.equal(s.world, 0); assert.equal(s.panic.progress, 0); setConditionPause(s, false);
  assert.equal(beginPortableStabilization(s).ok, true); advanceConditionWorld(s, 8);
  assert.equal(s.san, 15); assert.equal(s.panic.active, false); assert.equal(s.panic.used, true);
});

test('Ignoring an actual zero-SAN night entry expires at world20 without another fear event', () => {
  const s = fixture({initialSan: 0}); advanceConditionWorld(s, 720);
  assert.equal(s.world, 20); assert.equal(s.budget, 20); assert.equal(s.mode, 'failed_shift');
  assert.equal(s.panic.episode, 1); assert.equal(s.san, 0);
});

test('The night factory rejects a daytime mode and invalid initial SAN instead of ticking a day panic', () => {
  assert.throws(() => fixture({mode: 'day', initialSan: 0}), /condition_reference_requires_night_mode/);
  for (const initialSan of [-1, 101, NaN, Infinity]) assert.throws(() => fixture({initialSan}), /invalid_initial_san/);
});

test('A real two-tile mark at F26 arrival is committed before its same-time trace recheck', () => {
  const s = fixture(); advanceConditionWorld(s, 360);
  const incident = cut(s); walkActor(s, {distanceTiles: 2}); const old = Object.values(s.traces)[0];
  advanceConditionWorld(s, 20); const e = blood(s, incident, 'F26', 'same-tick-mark');
  advanceConditionWorld(s, e.arrivalAt - s.world - 2 / 3);
  walkActor(s, {distanceTiles: 2});
  const added = Object.values(s.traces).find(t => t.id !== old.id);
  assert.equal(old.live, false); assert.ok(Math.abs(added.bornAt - e.arrivalAt) < 1e-8);
  assert.equal(e.state, 'ACTIVE'); assert.deepEqual(e.boundTraceIds, [added.id]);
});

test('A requested mark created after F26 arrival cannot be used early or revive its safe return', () => {
  const s = fixture(); advanceConditionWorld(s, 360);
  const incident = cut(s); walkActor(s, {distanceTiles: 2}); const old = Object.values(s.traces)[0];
  advanceConditionWorld(s, 20); const e = blood(s, incident, 'F26', 'future-requested-mark');
  advanceConditionWorld(s, e.arrivalAt - s.world - 0.5);
  walkActor(s, {distanceTiles: 2});
  const added = Object.values(s.traces).find(t => t.id !== old.id);
  assert.ok(added.bornAt > e.arrivalAt); assert.equal(e.state, 'SAFE_RETURNED');
  assert.equal(e.endCause, 'no_actual_trace_at_arrival'); advanceConditionWorld(s, 1);
  assert.equal(e.state, 'SAFE_RETURNED');
});

test('A trace expiring at the movement endpoint frees one live-mark slot without refreshing it', () => {
  const s = fixture(); advanceConditionWorld(s, 360); cut(s); walkActor(s, {distanceTiles: 12});
  const old = Object.values(s.traces).sort((a, b) => a.bornAt - b.bornAt)[0], expiry = old.expiresAt;
  assert.equal(Object.values(s.traces).filter(t => t.live).length, 6);
  advanceConditionWorld(s, expiry - s.world - 2 / 3); walkActor(s, {distanceTiles: 2});
  assert.equal(old.live, false); assert.equal(old.expiresAt, expiry);
  assert.equal(Object.values(s.traces).filter(t => t.live).length, 6);
  assert.equal(Object.values(s.traces).filter(t => Math.abs(t.bornAt - expiry) < 1e-8).length, 1);
});

console.log(JSON.stringify({status: 'PASS', scenarioCount: passed.length, scenarios: passed,
  scope: 'Bounded headless causal/action chains, origin-slot carryover limits, night-only panic initialization, object reservations, and narrow F21 activation. No real collision, daytime engine, touch, full actor AI, F32 invitation/geometry, physical pickup/carrying, full identity or all sixty encounter adapters verified.'}, null, 2));
