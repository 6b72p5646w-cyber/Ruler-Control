/**
 * Bounded, headless causal reference. No renderer, navigation or sixty-monster AI.
 * Concrete adapter calls (receive/hold/contact/move) must come from actual engine
 * interactions. This module cannot establish that a real touch or collision took
 * place; it rejects invented historical receipts and invalid action ordering.
 */
const TERMINAL = new Set(['RESOLVED', 'PREVENTED', 'DECLINED', 'SAFE_RETURNED',
  'FAILED_LOCAL', 'CANCELLED_UNAVAILABLE', 'WITHDRAWN']);
const WORK_SECONDS = {receive_return: 2, station_work: 2, isolate_station: 2,
  wipe_trace: 1.5, seal_waste: 2, seal_water: 2};
const fail = reason => ({ok: false, reason});
const ok = value => ({ok: true, ...value});
const copy = value => JSON.parse(JSON.stringify(value));
const nextId = (s, prefix) => `${prefix}-${++s.sequence}`;
function log(s, type, data = {}) { s.log.push({type, world: s.world, budget: s.budget, ...data}); }
function record(s, kind, actorId, objectId, sourceActionId, extra = {}) {
  const id = nextId(s, 'receipt');
  const receipt = {id, kind, actorId, objectId, sourceActionId, worldAt: s.world,
    shiftAt: s.budget, rootEvidenceId: id, independenceDomain: kind, ...extra};
  s.receipts[id] = receipt;
  return receipt;
}
const fresh = (s, actorId) => s.actors[actorId]?.wound?.state === 'fresh';
const actionAllowed = s => !s.paused && s.mode === 'night' && !s.precision;
const actorBusy = (s, actorId) => Object.values(s.actions).some(a => a.actorId === actorId && a.state === 'running');
const producerPhaseAllowed = (s, type) => s.contract.wounds.producers.find(p => p.id === type)
  ?.phase_options.includes(`N0${Math.floor(s.budget / 120) + 1}`);
function endEncounter(s, e, state, cause) {
  if (TERMINAL.has(e.state)) return false;
  e.state = state; e.endedAt = s.world; e.endCause = cause;
  if (e.slotId) s.slots[e.slotId].state = 'CONSUMED';
  log(s, 'encounter_terminal', {id: e.id, state, cause});
  return true;
}

export function createConditionState(contract, options = {}) {
  if (!contract?.wounds || !contract?.clock_contract) throw new Error('causal contract required');
  const slots = {};
  for (const slot of options.reservedSlots ?? []) {
    if (!['primary', 'joint'].includes(slot.kind)) throw new Error('reserved slot kind');
    slots[slot.id] = {...copy(slot), state: 'RESERVED'};
  }
  const objects = Object.fromEntries((options.objects ?? []).map(x => [x.id, {...copy(x), isolated: false}]));
  const fixedMarkers = [
    ...[1, 2, 3, 4, 5].map(phase => ({id: `phase_end_${phase}`, at: phase * 120})),
    {id: 'manager_arrival', at: contract.end_of_shift.manager_arrival_budget_seconds},
    {id: 'true_06_00', at: contract.end_of_shift.true_six_budget_seconds}
  ];
  const fixedMarkerIds = new Set(fixedMarkers.map(x => x.id));
  // Caller-supplied arrivals/omens may add boundaries, never move or remove the
  // authored phase, manager, or true-06:00 boundaries (including by ID collision).
  const markers = [
    ...(options.markers ?? []).filter(x => !fixedMarkerIds.has(x.id)),
    ...fixedMarkers
  ].map(x => ({...x, dispatched: false}));
  return {contract: copy(contract), world: 0, budget: 0, paused: false, mode: 'night', sequence: 0,
    sanSettings: options.balance?.resources?.san ? copy(options.balance.resources.san) : null,
    san: options.initialSan ?? options.balance?.resources?.san?.max ?? 100,
    panic: {active: false, deadline: null, progress: 0, stabilizing: false, used: false, episode: 0, fearImmuneUntil: null},
    fearSources: {},
    actors: {PLAYER: {wound: null, minorUntil: null, cutCount: 0, station: null, distanceSinceMark: 0},
      COWORKER: {wound: null, minorUntil: null, cutCount: 0, station: null, distanceSinceMark: 0}},
    inventory: {dressings: contract.wounds.first_aid.night_free_dressings,
      bags: contract.supply_catalog.find(x => x.id === 'SUP_SEALING')?.quantity ?? 0},
    objects, slots, markers, receipts: {}, actions: {}, incidents: {}, traces: {}, waste: {},
    encounters: {}, promises: {}, log: [], nightCutCount: 0, precision: null, managerArrived: false};
}

export function setConditionPause(s, paused) { s.paused = Boolean(paused); }

export function applyConditionFear(s, {amount, sourceId}) {
  if (!actionAllowed(s) || !s.sanSettings || !sourceId || !Number.isFinite(amount) || amount <= 0) return fail('invalid_fear');
  if (s.panic.fearImmuneUntil !== null && s.world < s.panic.fearImmuneUntil) return fail('fear_only_grace');
  const key = `${sourceId}:${Math.floor(s.budget / 120)}`;
  const old = s.fearSources[key] ?? {total: 0, lastAt: -Infinity};
  if (s.world - old.lastAt < s.sanSettings.repeat_fear_cooldown_seconds) return fail('fear_source_cooldown');
  const actual = Math.min(amount, Math.max(0, s.sanSettings.per_entity_per_phase_fear_cap - old.total));
  if (!actual) return fail('fear_source_cap');
  s.fearSources[key] = {total: old.total + actual, lastAt: s.world};
  s.san = Math.max(0, s.san - actual);
  if (s.san === 0 && !s.panic.active) {
    s.panic.active = true; s.panic.episode++; s.panic.progress = 0; s.panic.stabilizing = false;
    s.panic.deadline = s.world + s.sanSettings.panic_window_seconds;
    log(s, 'panic_started', {episode: s.panic.episode, deadline: s.panic.deadline});
  }
  return ok({damage: actual});
}

export function interruptPortableStabilization(s, reason = 'other_action') {
  if (s.paused) return fail('paused');
  if (s.panic.stabilizing) {
    s.panic.stabilizing = false; log(s, 'stabilization_interrupted', {reason, progress: s.panic.progress});
  }
  return ok({});
}

export function beginPortableStabilization(s) {
  if (!actionAllowed(s) || !s.sanSettings || !s.panic.active || s.san > 0) return fail('no_active_panic');
  if (s.panic.used || s.sanSettings.free_stabilizations_per_night < 1) return fail('night_stabilization_spent');
  if (actorBusy(s, 'PLAYER')) return fail('actor_unavailable');
  s.panic.stabilizing = true;
  return ok({remaining: (s.sanSettings.emergency_stabilization_seconds ?? s.sanSettings.safe_zone_stabilization_seconds) - s.panic.progress});
}

export function beginRecordedWork(s, {kind, actorId = 'PLAYER', objectId}) {
  if (!actionAllowed(s)) return fail('world_not_actionable');
  if (!s.actors[actorId] || actorBusy(s, actorId)) return fail('actor_unavailable');
  if (!(kind in WORK_SECONDS)) return fail('unknown_work_kind');
  if (s.budget + WORK_SECONDS[kind] > s.contract.end_of_shift.true_six_budget_seconds) return fail('insufficient_shift_budget');
  const o = s.objects[objectId];
  if (kind === 'receive_return' && (!o || o.kind !== 'returned_glass' || o.received)) return fail('not_pending_return');
  if (['station_work', 'isolate_station'].includes(kind) && (!o || o.kind !== 'station')) return fail('not_station');
  if (kind === 'wipe_trace' && !s.traces[objectId]?.live) return fail('no_live_trace');
  if (kind === 'seal_waste' && (!s.waste[objectId] || s.waste[objectId].sealed || s.inventory.bags < 1)) return fail('no_waste_or_bag');
  if (kind === 'seal_water' && (!o || o.kind !== 'reserved_water' || o.sealed)) return fail('not_unsealed_water');
  const id = nextId(s, 'action');
  if (actorId === 'PLAYER') interruptPortableStabilization(s, 'other_work');
  s.actions[id] = {id, kind, actorId, objectId, startedAt: s.world,
    endAt: s.world + WORK_SECONDS[kind], state: 'running'};
  if (kind === 'station_work') {
    s.actors[actorId].station = objectId;
    s.actors[actorId].stationExitTravel = 0;
  }
  if (kind === 'seal_waste') { s.inventory.bags--; s.actions[id].reservedBag = true; }
  return ok({actionId: id});
}

export function cancelRecordedWork(s, actionId) {
  const a = s.actions[actionId];
  if (!a || a.state !== 'running') return fail('no_running_action');
  if (s.paused) return fail('paused');
  a.state = 'cancelled';
  if (a.reservedDressing) { s.inventory.dressings++; a.reservedDressing = false; }
  if (a.reservedBag) { s.inventory.bags++; a.reservedBag = false; }
  log(s, 'action_cancelled', {actionId});
  return ok({});
}

export function requireHistoricalReceipt(s, {id, kind, actorId, objectId}) {
  const r = s.receipts[id];
  return r && r.kind === kind && (!actorId || r.actorId === actorId) && (!objectId || r.objectId === objectId)
    ? ok({receipt: copy(r)}) : fail('actual_matching_receipt_missing');
}

export function announceGlassHazard(s, {returnReceiptId, objectId}) {
  if (!actionAllowed(s)) return fail('world_not_actionable');
  if (!producerPhaseAllowed(s, 'GLASS_RETURN_CONTACT')) return fail('producer_phase_not_allowed');
  const r = requireHistoricalReceipt(s, {id: returnReceiptId, kind: 'receive_return', objectId});
  const o = s.objects[objectId];
  if (!r.ok || !o?.broken || o.isolated) return fail('actual_broken_return_missing');
  if (Object.values(s.incidents).some(i => i.objectId === objectId)) return fail('hazard_already_registered');
  const id = nextId(s, 'incident');
  s.incidents[id] = {id, type: 'GLASS_RETURN_CONTACT', objectId, sourceReceiptId: returnReceiptId,
    warningAt: s.world, readyAt: s.world + s.contract.wounds.minimum_visible_hazard_warning_world_seconds,
    stage: 'warning', cut: false, consumerId: null};
  log(s, 'hazard_announced', {id});
  return ok({incidentId: id});
}

export function announceStationGlassFault(s, {workReceiptId, objectId, actorId}) {
  if (!actionAllowed(s)) return fail('world_not_actionable');
  if (!producerPhaseAllowed(s, 'F21_GLASS_FAULT')) return fail('producer_phase_not_allowed');
  const r = requireHistoricalReceipt(s, {id: workReceiptId, kind: 'station_work', actorId, objectId});
  if (!r.ok || s.actors[actorId]?.station !== objectId || s.objects[objectId]?.isolated) return fail('actual_occupied_station_missing');
  if (Object.values(s.incidents).some(i => i.objectId === objectId)) return fail('hazard_already_registered');
  const id = nextId(s, 'incident');
  s.incidents[id] = {id, type: 'F21_GLASS_FAULT', objectId, sourceReceiptId: workReceiptId,
    actorId, warningAt: s.world, readyAt: s.world +
      (s.contract.wounds.producers.find(p => p.id === 'F21_GLASS_FAULT').warning_world_seconds ?? 40),
    stage: 'warning', cut: false, consumerId: null};
  log(s, 'hazard_announced', {id});
  return ok({incidentId: id});
}

function cutActor(s, incident, actorId) {
  const a = s.actors[actorId], c = s.contract.wounds;
  if (!a || incident.cut || a.wound?.state === 'fresh') return fail('duplicate_or_existing_cut');
  if (a.cutCount >= c.max_bleeding_episodes_per_actor_per_night || s.nightCutCount >= c.max_bleeding_episodes_per_night) return fail('night_cut_cap');
  incident.cut = true; incident.actorId = actorId; incident.stage = 'consequence';
  if (actorId === 'PLAYER') interruptPortableStabilization(s, 'cut_contact');
  a.cutCount++; s.nightCutCount++;
  a.wound = {incidentId: incident.id, state: 'fresh', startedAt: s.world,
    endAt: s.world + c.bleeding_duration_world_seconds, endedByPlayer: false};
  a.minorUntil = s.world + c.minor_injury_duration_world_seconds;
  incident.cutReceiptId = record(s, 'actual_cut', actorId, incident.objectId, incident.id,
    {producer: incident.type}).id;
  log(s, 'cut_committed', {incidentId: incident.id, actorId});
  return ok({receiptId: incident.cutReceiptId});
}

export function contactGlassHazard(s, {incidentId, actorId = 'PLAYER', method}) {
  if (!actionAllowed(s)) return fail('world_not_actionable');
  const i = s.incidents[incidentId];
  if (!i || i.type !== 'GLASS_RETURN_CONTACT' || i.stage === 'isolated') return fail('no_glass_hazard');
  if (!s.actors[actorId]) return fail('unknown_actor');
  if (method === 'sweep_and_isolate') {
    if (actorId === 'PLAYER') interruptPortableStabilization(s, 'glass_cleanup');
    i.stage = 'isolated'; s.objects[i.objectId].isolated = true;
    return ok({receiptId: record(s, 'glass_isolated', actorId, i.objectId, i.id).id});
  }
  if (method !== 'bare_hand_contact') return fail('unknown_contact_method');
  if (s.world < i.readyAt) return fail('warning_not_elapsed');
  return cutActor(s, i, actorId);
}

export function applyOrdinaryMinorContact(s, actorId) {
  if (!actionAllowed(s) || !s.actors[actorId]) return fail('actor_unavailable');
  if (actorId === 'PLAYER') interruptPortableStabilization(s, 'physical_contact');
  s.actors[actorId].minorUntil = s.world + s.contract.wounds.minor_injury_duration_world_seconds;
  return ok({}); // F12/F13 SAN and shared hit protection remain in their original core.
}

export function beginFirstAid(s, {actorId = 'PLAYER', targetId = actorId, distanceTiles = 0}) {
  if (!actionAllowed(s) || actorBusy(s, actorId) || !s.actors[actorId]) return fail('actor_unavailable');
  if (!fresh(s, targetId)) return fail('no_fresh_wound');
  if (!Number.isFinite(distanceTiles) || distanceTiles < 0) return fail('invalid_distance');
  if (distanceTiles > s.contract.wounds.first_aid.requires_target_distance_tiles_max) return fail('out_of_reach');
  if (s.inventory.dressings < 1) return fail('no_dressing');
  if (s.budget + s.contract.wounds.first_aid.world_action_seconds > s.contract.end_of_shift.true_six_budget_seconds) return fail('insufficient_shift_budget');
  s.inventory.dressings--;
  if (actorId === 'PLAYER') interruptPortableStabilization(s, 'first_aid');
  const id = nextId(s, 'action');
  s.actions[id] = {id, kind: 'first_aid', actorId, targetId, objectId: s.actors[targetId].wound.incidentId,
    startedAt: s.world, endAt: s.world + s.contract.wounds.first_aid.world_action_seconds,
    state: 'running', reservedDressing: true};
  return ok({actionId: id});
}

function completeWorldAction(s, a) {
  if (a.state !== 'running') return;
  if (a.kind === 'first_aid') {
    const w = s.actors[a.targetId]?.wound;
    if (!w || w.state !== 'fresh' || w.incidentId !== a.objectId) {
      a.state = 'cancelled';
      if (a.reservedDressing) { s.inventory.dressings++; a.reservedDressing = false; }
      return;
    }
    w.state = 'dressed'; w.endedAt = s.world; w.endedByPlayer = true;
    s.actors[a.targetId].minorUntil = null;
    a.reservedDressing = false;
  } else if (a.kind === 'receive_return') {
    s.objects[a.objectId].received = true;
  } else if (a.kind === 'isolate_station') {
    s.objects[a.objectId].isolated = true;
  } else if (a.kind === 'wipe_trace') {
    const t = s.traces[a.objectId];
    if (t?.live) {
      t.live = false; t.removedByPlayer = true;
      const id = nextId(s, 'waste');
      s.waste[id] = {id, incidentId: t.incidentId, sealed: false, sourceTraceId: t.id};
    }
  } else if (a.kind === 'seal_waste') {
    s.waste[a.objectId].sealed = true; a.reservedBag = false;
  } else if (a.kind === 'seal_water') {
    s.objects[a.objectId].sealed = true;
  }
  a.state = 'completed';
  a.receiptId = record(s, a.kind, a.actorId, a.objectId, a.id).id;
  log(s, 'action_committed', {actionId: a.id, kind: a.kind});
}

export function walkActor(s, {actorId = 'PLAYER', distanceTiles, gait = 'walk'}) {
  if (!actionAllowed(s) || !s.actors[actorId] || distanceTiles <= 0 || !Number.isFinite(distanceTiles)) return fail('invalid_walk');
  if (actorBusy(s, actorId)) return fail('cancel_station_action_before_walking');
  if (gait !== 'walk') return fail(s.panic.stabilizing ? 'stabilization_forbids_sprint' : 'only_normal_walk_in_reference');
  if (actorId === 'PLAYER' && s.panic.stabilizing && !s.sanSettings.portable_stabilization_allowed_while_walking) {
    interruptPortableStabilization(s, 'walking_disabled_in_configuration');
  }
  const a = s.actors[actorId];
  // A straight exit is committed at its actual crossing time, before a same-time
  // fault. Merely requesting movement cannot clear occupancy early.
  if (a.station && distanceTiles >= 1 - (a.stationExitTravel ?? 0)) {
    a.pendingStationExitAt = s.world + (1 - (a.stationExitTravel ?? 0)) / 3;
  }
  const interval = s.contract.wounds.blood_trace.min_travel_tiles_between_marks;
  let remaining = distanceTiles;
  while (remaining > 0 && s.mode === 'night') {
    const step = Math.min(remaining, interval - a.distanceSinceMark);
    advanceConditionWorld(s, step / 3);
    // This bounded reference models a straight one-tile station exit. The client
    // must use its actual exit/collision facts, not total distance walked in a loop.
    if (a.station) {
      a.stationExitTravel = (a.stationExitTravel ?? 0) + step;
    }
    a.distanceSinceMark += step; remaining -= step;
    if (a.distanceSinceMark + 1e-9 >= interval) {
      a.distanceSinceMark = 0;
      if (fresh(s, actorId)) {
        const current = Object.values(s.traces).filter(t => t.live && t.actorId === actorId);
        if (current.length < s.contract.wounds.blood_trace.max_live_marks_per_actor) {
          const id = nextId(s, 'trace');
          s.traces[id] = {id, actorId, incidentId: a.wound.incidentId, live: true,
            bornAt: s.world, expiresAt: s.world + s.contract.wounds.blood_trace.lifetime_world_seconds,
            actualWalkReceiptId: record(s, 'actual_walk_mark', actorId, id, nextId(s, 'walk')).id};
        }
      }
    }
  }
  return ok({});
}

export function announceBloodEncounter(s, {id, monsterId, incidentId, slotId}) {
  if (!actionAllowed(s) || !['F26', 'F32'].includes(monsterId)) return fail('invalid_reactive_request');
  const i = s.incidents[incidentId], slot = s.slots[slotId];
  if (!i?.cutReceiptId || !s.receipts[i.cutReceiptId] || i.consumerId) return fail('missing_or_consumed_incident');
  if (s.encounters[id]) return fail('duplicate_encounter');
  if (!slot || slot.state !== 'RESERVED' || !slot.allowed.includes(monsterId)) return fail('no_pre_reserved_slot');
  if (slot.phase !== Math.floor(s.budget / 120)) return fail('wrong_phase_slot');
  const c = s.contract.wounds.reactive_consumers, a = s.actors[i.actorId];
  if (!fresh(s, i.actorId) || a.wound.endAt - s.world < c.minimum_remaining_fresh_blood_world_seconds_at_announcement) return fail('fresh_source_window_missing');
  if (s.contract.end_of_shift.true_six_budget_seconds - s.budget < c.minimum_remaining_shift_budget_seconds) return fail('insufficient_shift_budget');
  if (120 - (s.budget % 120) < c.minimum_remaining_current_phase_budget_seconds) return fail('insufficient_phase_budget');
  const traces = Object.values(s.traces).filter(t => t.live && t.incidentId === incidentId).slice(0, 3);
  if (monsterId === 'F26' && traces.length === 0) return fail('no_actual_blood_trace');
  i.consumerId = id; slot.state = 'ANNOUNCED'; slot.encounterId = id;
  s.encounters[id] = {id, monsterId, incidentId, slotId, state: 'ANNOUNCED', critical: true,
    announcedAt: s.world, arrivalAt: s.world + c.announcement_lead_world_seconds,
    boundTraceIds: traces.map(t => t.id), sourceActorId: i.actorId};
  log(s, 'encounter_announced', {id, monsterId});
  return ok({});
}

function updateBloodEncounter(s, e) {
  if (TERMINAL.has(e.state)) return;
  const a = s.actors[e.sourceActorId], w = a?.wound;
  const liveSource = w?.incidentId === e.incidentId && w.state === 'fresh';
  const liveTraces = e.boundTraceIds.some(id => s.traces[id]?.live);
  const openWaste = Object.values(s.waste).some(x => x.incidentId === e.incidentId && !x.sealed);
  const noTarget = e.monsterId === 'F32' ? !liveSource : !liveSource && !liveTraces && !openWaste;
  if (noTarget) {
    const playerCaused = w?.endedByPlayer || e.boundTraceIds.some(id => s.traces[id]?.removedByPlayer);
    if (e.state === 'ANNOUNCED') endEncounter(s, e, playerCaused ? 'PREVENTED' : 'SAFE_RETURNED', 'source_removed_before_arrival');
    else if (e.leaveAt === undefined) {
      e.leaveAt = s.world + 3; e.leaveState = playerCaused ? 'RESOLVED' : 'SAFE_RETURNED';
    }
  }
  if (e.state === 'ANNOUNCED' && s.world >= e.arrivalAt) {
    e.state = 'ACTIVE'; log(s, 'encounter_arrived', {id: e.id});
  }
  if (e.leaveAt !== undefined && s.world >= e.leaveAt) endEncounter(s, e, e.leaveState, 'targetless_exit');
}

export function offerOptionalEncounter(s, id) {
  if (!actionAllowed(s) || s.encounters[id]) return fail('invalid_offer');
  s.encounters[id] = {id, state: 'ANNOUNCED', optional: true, accepted: false, critical: false};
  return ok({});
}
export function declineOptionalEncounter(s, id) {
  const e = s.encounters[id];
  if (s.paused || !e?.optional || e.accepted || TERMINAL.has(e.state)) return fail('not_unaccepted_optional');
  interruptPortableStabilization(s, 'request_response');
  endEncounter(s, e, 'DECLINED', 'player_declined'); return ok({});
}

export function acceptDawnPromise(s, {id, objectId}) {
  if (!actionAllowed(s) || s.promises[id] || s.objects[objectId]?.kind !== 'reserved_water') return fail('invalid_promise');
  if (Object.values(s.promises).some(p => p.objectId === objectId && p.state === 'ACTIVE')) return fail('already_reserved');
  interruptPortableStabilization(s, 'promise_acceptance');
  s.promises[id] = {id, objectId, state: 'ACTIVE', deadline: s.contract.end_of_shift.true_six_budget_seconds};
  s.encounters[id] = {id, monsterId: 'F53', state: 'ACTIVE', critical: true};
  return ok({});
}

function settleSix(s) {
  for (const p of Object.values(s.promises)) if (p.state === 'ACTIVE') {
    p.state = s.objects[p.objectId]?.sealed ? 'RESOLVED' : 'FAILED_LOCAL';
    endEncounter(s, s.encounters[p.id], p.state, 'due_at_six');
    log(s, 'dawn_promise_settled', {id: p.id, state: p.state});
  }
  for (const e of Object.values(s.encounters)) if (e.optional && !e.accepted && !TERMINAL.has(e.state)) {
    endEncounter(s, e, 'DECLINED', 'unaccepted_offer_at_six');
  }
  const unresolved = Object.values(s.encounters).some(e => e.critical && !TERMINAL.has(e.state)) ||
    s.panic.active;
  log(s, 'critical_threat_check', {unresolved});
  s.mode = unresolved ? 'failed_shift' : 'handover_only';
  log(s, s.mode);
}

function processDue(s) {
  if (s.panic.active && s.panic.stabilizing) {
    const target = s.sanSettings.emergency_stabilization_seconds ?? s.sanSettings.safe_zone_stabilization_seconds;
    if (s.panic.progress >= target) {
      s.panic.progress = target; s.panic.active = false; s.panic.stabilizing = false; s.panic.used = true;
      s.san = Math.max(s.san, s.sanSettings.emergency_stabilization_target_san ?? s.sanSettings.safe_zone_stabilization_target_san);
      s.panic.fearImmuneUntil = s.world + s.sanSettings.post_stabilization_fear_immunity_seconds;
      log(s, 'portable_stabilization_completed', {san: s.san});
    }
  }
  const panicTimedOut = s.panic.active && s.world >= s.panic.deadline;
  for (const a of Object.values(s.actors)) {
    if (a.wound?.state === 'fresh' && s.world >= a.wound.endAt) {
      a.wound.state = 'dry'; a.wound.endedAt = s.world; a.wound.endedByPlayer = false;
    }
    if (a.minorUntil !== null && s.world >= a.minorUntil) a.minorUntil = null;
  }
  for (const t of Object.values(s.traces)) if (t.live && s.world >= t.expiresAt) t.live = false;
  for (const a of Object.values(s.actions)) if (a.state === 'running' &&
    (s.world >= a.endAt || (a.kind === 'first_aid' && !fresh(s, a.targetId)))) completeWorldAction(s, a);
  for (const a of Object.values(s.actors)) if (a.pendingStationExitAt !== undefined && s.world >= a.pendingStationExitAt) {
    a.station = null; delete a.pendingStationExitAt;
  }
  for (const i of Object.values(s.incidents)) if (i.type === 'F21_GLASS_FAULT' && i.stage === 'warning' && s.world >= i.readyAt) {
    if (s.actors[i.actorId]?.station === i.objectId && !s.objects[i.objectId].isolated) {
      if (!cutActor(s, i, i.actorId).ok) i.stage = 'suppressed_by_cut_cap';
    }
    else i.stage = 'prevented';
  }
  for (const e of Object.values(s.encounters)) if (['F26', 'F32'].includes(e.monsterId)) updateBloodEncounter(s, e);
  for (const m of [...s.markers].sort((a, b) => a.at - b.at)) if (!m.dispatched && s.budget >= m.at) {
    m.dispatched = true; log(s, 'schedule_marker', {id: m.id});
    if (m.id === 'manager_arrival') s.managerArrived = true;
    if (m.id === 'true_06_00') settleSix(s);
  }
  if (panicTimedOut) {
    s.mode = 'failed_shift'; s.panic.stabilizing = false;
    log(s, 'panic_timeout');
  }
}

export function advanceConditionWorld(s, seconds) {
  if (!Number.isFinite(seconds) || seconds < 0) return fail('invalid_delta');
  if (s.paused || s.precision || s.mode !== 'night') return ok({advanced: 0});
  processDue(s);
  let remaining = seconds, advanced = 0;
  while (remaining > 1e-9 && s.mode === 'night') {
    const deadlines = [remaining];
    if (s.panic.active) {
      if (s.panic.deadline > s.world) deadlines.push(s.panic.deadline - s.world);
      if (s.panic.stabilizing) {
        const target = s.sanSettings.emergency_stabilization_seconds ?? s.sanSettings.safe_zone_stabilization_seconds;
        if (target > s.panic.progress) deadlines.push(target - s.panic.progress);
      }
    }
    for (const m of s.markers) if (!m.dispatched && m.at > s.budget) deadlines.push(m.at - s.budget);
    for (const a of Object.values(s.actions)) if (a.state === 'running' && a.endAt > s.world) deadlines.push(a.endAt - s.world);
    for (const a of Object.values(s.actors)) {
      if (a.wound?.state === 'fresh' && a.wound.endAt > s.world) deadlines.push(a.wound.endAt - s.world);
      if (a.minorUntil !== null && a.minorUntil > s.world) deadlines.push(a.minorUntil - s.world);
      if (a.pendingStationExitAt !== undefined && a.pendingStationExitAt > s.world) deadlines.push(a.pendingStationExitAt - s.world);
    }
    for (const t of Object.values(s.traces)) if (t.live && t.expiresAt > s.world) deadlines.push(t.expiresAt - s.world);
    for (const i of Object.values(s.incidents)) if (i.type === 'F21_GLASS_FAULT' && i.stage === 'warning' && i.readyAt > s.world) deadlines.push(i.readyAt - s.world);
    for (const e of Object.values(s.encounters)) if (!TERMINAL.has(e.state)) {
      if (e.state === 'ANNOUNCED' && e.arrivalAt > s.world) deadlines.push(e.arrivalAt - s.world);
      if (e.leaveAt !== undefined && e.leaveAt > s.world) deadlines.push(e.leaveAt - s.world);
    }
    const dt = Math.min(...deadlines);
    if (s.panic.active && s.panic.stabilizing) s.panic.progress += dt;
    s.world += dt; s.budget += dt; advanced += dt; remaining -= dt;
    processDue(s);
  }
  return ok({advanced});
}

export function beginPrecisionAttempt(s, {costSeconds}) {
  if (!actionAllowed(s) || !Number.isFinite(costSeconds) || costSeconds <= 0) return fail('invalid_precision');
  processDue(s); // Same-time scheduled facts dispatch before a new attempt.
  if (s.mode !== 'night') return fail('shift_already_ended');
  if (s.san <= 0) return fail('panic_disallows_new_precision');
  if (Object.values(s.actions).some(a => a.state === 'running')) return fail('running_world_action');
  if (Object.values(s.encounters).some(e => ['F26', 'F32'].includes(e.monsterId) && e.critical && !TERMINAL.has(e.state))) return fail('critical_resolution_reserved');
  const nextMarker = s.markers.filter(m => !m.dispatched).reduce((n, m) => Math.min(n, m.at), Infinity);
  if (s.budget + costSeconds > nextMarker) return fail('would_cross_schedule_marker');
  const id = nextId(s, 'precision');
  s.precision = {id, costSeconds, localSeconds: 0};
  return ok({attemptId: id});
}
export function advancePrecisionLocal(s, seconds) {
  if (!s.precision || s.paused || !Number.isFinite(seconds) || seconds < 0) return fail('no_running_precision');
  s.precision.localSeconds += seconds; return ok({});
}
export function finishPrecisionAttempt(s, {attemptId, outcome}) {
  const p = s.precision;
  if (s.paused || !p || p.id !== attemptId || !['success', 'cancelled', 'failed'].includes(outcome)) return fail('invalid_precision_finish');
  s.precision = null; s.budget += p.costSeconds;
  const receiptId = record(s, 'precision_attempt', 'PLAYER', attemptId, attemptId, {outcome}).id;
  log(s, 'precision_committed', {attemptId, outcome});
  processDue(s); // Commit first, then dispatch exactly reached schedule marker.
  return ok({receiptId});
}
