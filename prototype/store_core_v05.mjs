/**
 * V0.5 deterministic contract examples, not a playable store or monster engine.
 * Configuration lives in store_systems_v05.json. No renderer, navigation, actor
 * collision, economic persistence or WeChat integration is supplied here.
 */

const copy = value => structuredClone(value);
function finiteNonnegative(value, name) {
  if (!Number.isFinite(value) || value < 0) throw new RangeError(name);
}

export function createStore(config) {
  return {now: 0, reserve: config.emergency_power.starting_units, mode: 'open',
    greeting: 'voice', braceUntil: null, spentIds: [], rechargeIds: [],
    orders: [], debts: [], retiredDebts: [], debtDeduction: 0,
    encounters: {}, criticalBreach: false};
}

export function buyAssist(previous, config, actionId, commandId, context = {}) {
  const state = copy(previous);
  const action = config.emergency_power.actions.find(a => a.id === actionId);
  if (!action) throw new Error('unknown_assist');
  if (typeof commandId !== 'string' || !commandId) throw new Error('missing_command_id');
  if (state.spentIds.includes(commandId)) return {ok: false, reason: 'already_committed', state};
  if (context.paused) return {ok: false, reason: 'world_paused', state};
  if (actionId === 'brace_door' && context.blocksRequiredExit)
    return {ok: false, reason: 'required_exit', state};
  if (state.reserve < action.units) return {ok: false, reason: 'insufficient_reserve', state};
  state.reserve -= action.units;
  state.spentIds.push(commandId);
  return {ok: true, state, effect: actionId, duration: action.duration_world_seconds ?? 0,
    requiredWorldSeconds: action.world_seconds};
}

export function rechargeReserve(previous, config, batteryInstanceId, context = {}) {
  const state = copy(previous);
  const rule = config.emergency_power.recharge;
  if (!batteryInstanceId || !context.batteryAvailable) return {ok: false, reason: 'missing_battery', state};
  if (context.paused) return {ok: false, reason: 'world_paused', state};
  if (context.usedForLamp || state.rechargeIds.includes(batteryInstanceId))
    return {ok: false, reason: 'battery_already_consumed', state};
  if (rule.once_per_night && state.rechargeIds.length > 0)
    return {ok: false, reason: 'night_recharge_limit', state};
  if (state.reserve >= config.emergency_power.capacity_units)
    return {ok: false, reason: 'already_full', state};
  state.reserve = Math.min(config.emergency_power.capacity_units, state.reserve + rule.units);
  state.rechargeIds.push(batteryInstanceId);
  return {ok: true, state, consumedBatteryId: batteryInstanceId};
}

export function changeServiceMode(previous, config, mode, commandId, context = {}) {
  if (!config.service.modes.includes(mode)) throw new Error('unknown_mode');
  if (context.paused) return {ok: false, reason: 'world_paused', state: copy(previous)};
  if (mode === 'shutter') {
    if (previous.mode === 'shutter') return {ok: false, reason: 'already_braced', state: copy(previous)};
    const bought = buyAssist(previous, config, 'brace_door', commandId, context);
    if (!bought.ok) return bought;
    cancelActiveService(bought.state);
    bought.state.mode = mode;
    bought.state.braceUntil = previous.now + config.service.shutter_duration_world_seconds;
    return bought;
  }
  const state = copy(previous);
  if (state.mode !== mode) cancelActiveService(state);
  state.mode = mode;
  state.braceUntil = null;
  // Neither a door mode nor a sign resolves a monster or changes order arrival time.
  return {ok: true, state, requiredWorldSeconds: config.service.world_seconds_to_toggle};
}

function cancelActiveService(state) {
  for (const order of state.orders) {
    if (order.status !== 'serving') continue;
    order.status = 'waiting';
    delete order.startedAt;
    delete order.finishesAt;
  }
}

export function setGreeting(previous, config, mode, context = {}) {
  if (!config.service.greeting_modes.includes(mode)) throw new Error('unknown_greeting');
  const state = copy(previous);
  if (context.paused) return state;
  if (state.greeting !== mode) cancelActiveService(state);
  state.greeting = mode;
  return state;
}

export function orderDuration(state, config) {
  if (state.mode === 'shutter') return null;
  if (state.mode === 'window') return config.work_contract.service_window_checkout_seconds;
  return config.work_contract.normal_checkout_seconds +
    (state.greeting === 'silent' ? config.work_contract.silent_greeting_extra_seconds_per_order : 0);
}

export function arriveOrder(previous, config, orderId, {requiresEntry = false} = {}) {
  const state = copy(previous);
  if (!orderId || state.orders.some(o => o.id === orderId)) throw new Error('duplicate_or_missing_order');
  const waiting = state.orders.filter(o => ['waiting', 'serving'].includes(o.status)).length;
  state.orders.push({id: orderId, arrivedAt: state.now,
    expiresAt: state.now + config.service.normal_order_patience_world_seconds,
    requiresEntry, entered: false,
    status: waiting < config.service.queue_capacity ? 'waiting' : 'lost',
    lossReason: waiting < config.service.queue_capacity ? null : 'queue_full'});
  return state;
}

export function customerEntered(previous, orderId, {paused = false, crossedDoor = false} = {}) {
  const state = copy(previous);
  const order = state.orders.find(o => o.id === orderId);
  if (paused || state.mode !== 'open' || !crossedDoor || !order ||
      order.status !== 'waiting' || state.now >= order.expiresAt)
    return {ok: false, reason: 'entry_not_observed', state};
  order.entered = true;
  order.enteredAt = state.now;
  return {ok: true, state};
}

export function beginService(previous, config, orderId, context = {}) {
  const state = copy(previous);
  const duration = orderDuration(state, config);
  const order = state.orders.find(o => o.id === orderId);
  if (context.paused) return {ok: false, reason: 'world_paused', state};
  if (duration === null) return {ok: false, reason: 'shutter_closed', state};
  if (!order || order.status !== 'waiting' || state.now >= order.expiresAt)
    return {ok: false, reason: 'order_unavailable', state};
  if (order.requiresEntry && !order.entered) return {ok: false, reason: 'needs_physical_entry', state};
  if (state.orders.some(o => o.status === 'serving')) return {ok: false, reason: 'counter_busy', state};
  if (state.now + duration > order.expiresAt) return {ok: false, reason: 'insufficient_patience', state};
  order.status = 'serving';
  order.startedAt = state.now;
  order.finishesAt = state.now + duration;
  return {ok: true, state, duration};
}

export function finishService(previous, orderId, context = {}) {
  const state = copy(previous);
  const order = state.orders.find(o => o.id === orderId);
  if (context.paused) return {ok: false, reason: 'world_paused', state};
  if (state.mode === 'shutter') return {ok: false, reason: 'shutter_closed', state};
  if (!order || order.status !== 'serving' || state.now < order.finishesAt || state.now > order.expiresAt)
    return {ok: false, reason: 'not_ready', state};
  order.status = 'complete';
  order.completedAt = state.now;
  return {ok: true, state, receiptId: 'order:' + orderId};
}

export function advanceStore(previous, config, dt, {paused = false} = {}) {
  finiteNonnegative(dt, 'dt');
  const state = copy(previous);
  if (paused) return state;
  state.now += dt;
  if (state.braceUntil !== null && state.now >= state.braceUntil) {
    state.mode = config.service.shutter_revert_mode;
    state.braceUntil = null;
  }
  for (const order of state.orders) {
    if (['waiting','serving'].includes(order.status) && state.now > order.expiresAt) {
      order.status = 'lost';
      order.lossReason = 'patience';
    }
  }
  return state;
}

export function recordLocalBreach(previous, encounterInstanceId, violationActive) {
  const state = copy(previous);
  const record = state.encounters[encounterInstanceId] ?? {episodes: 0, active: false};
  if (!violationActive) {
    state.encounters[encounterInstanceId] = {...record, active: false};
    return {state, reaction: null};
  }
  if (record.active) return {state, reaction: null};
  const episodes = record.episodes + 1;
  state.encounters[encounterInstanceId] = {episodes, active: true};
  // It is a local signal. Species adapters decide their actual consequence.
  // No new pursuer, forced shift end or universal damage is generated here.
  const reaction = episodes === 1 ? 'first_warning' : episodes === 2 ?
    'local_consequence' : 'escalated_local_consequence';
  return {state, reaction};
}

function chargeDebt(state, config, debt) {
  state.debtDeduction = Math.min(config.work_debt.wage_deduction_night_cap,
    state.debtDeduction + config.work_debt.wage_deduction_per_expired_task);
  state.retiredDebts.push(debt.id);
}

export function phaseEnd(previous, config, phaseIndex, unfinishedDutyId = null) {
  if (!Number.isInteger(phaseIndex) || phaseIndex < 0 || phaseIndex > 5) throw new Error('bad_phase');
  const state = copy(previous);
  const kept = [];
  for (const debt of state.debts) {
    if (debt.expiresAfterPhase <= phaseIndex) chargeDebt(state, config, debt);
    else kept.push(debt);
  }
  state.debts = kept;
  if (!unfinishedDutyId || state.retiredDebts.includes(unfinishedDutyId) ||
      state.debts.some(d => d.id === unfinishedDutyId)) return state;
  const debt = {id: unfinishedDutyId, expiresAfterPhase: phaseIndex + 1};
  if (phaseIndex === 5) chargeDebt(state, config, debt);
  else if (state.debts.length < config.work_debt.max_carryover_tasks) state.debts.push(debt);
  else chargeDebt(state, config, debt);
  return state;
}

export function clearDebt(previous, dutyId) {
  const state = copy(previous);
  if (!state.debts.some(d => d.id === dutyId)) return state;
  state.debts = state.debts.filter(d => d.id !== dutyId);
  state.retiredDebts.push(dutyId);
  return state;
}

export function gradeShift(state, config, outcome) {
  const complete = outcome.trueGameMinutes >= 360 && outcome.verifiedHandover &&
    !state.criticalBreach && !outcome.unresolvedCriticalThreat && !outcome.panicExpired && !outcome.withdrawn;
  if (!complete) return {complete: false, grade: null, wage: 0, ticket: false};
  const orders = new Set(state.orders.filter(o => o.status === 'complete').map(o => o.id)).size;
  const duties = Math.min(6, Math.max(0, outcome.completedDuties));
  const grade = orders >= config.completion.order_target_for_top_grade && duties === 6 ? 'A' :
    orders >= 6 && duties >= 4 ? 'B' : 'C';
  // Initial transparent scoring proposal; does not claim calibrated balance.
  const bonus = Math.min(config.completion.bonus_max, duties * 4 + Math.min(8, orders) * 2);
  return {complete: true, grade, orders, duties,
    wage: config.completion.base_wage + bonus - state.debtDeduction,
    ticket: duties >= 4 && orders >= 6};
}

export function publicEvidence(observation) {
  const keys = ['id','kind','source','capturedAt','area','description','rootEvidenceId'];
  return Object.fromEntries(keys.filter(k => Object.hasOwn(observation, k)).map(k => [k, observation[k]]));
}

export function independentFactCount(facts) {
  // The client authors independence domains (e.g. physical_trace vs work_action).
  // More crops or frames from one observational domain are not a second source.
  const roots = new Map();
  for (const fact of facts) {
    if (!fact.directlyObserved || !fact.rootEvidenceId || !fact.independenceDomain) continue;
    if (!roots.has(fact.rootEvidenceId)) roots.set(fact.rootEvidenceId, new Set());
    roots.get(fact.rootEvidenceId).add(fact.independenceDomain);
  }
  const matched = new Map();
  function assign(root, visited) {
    for (const domain of roots.get(root)) {
      if (visited.has(domain)) continue;
      visited.add(domain);
      if (!matched.has(domain) || assign(matched.get(domain), visited)) {
        matched.set(domain, root); return true;
      }
    }
    return false;
  }
  for (const root of roots.keys()) assign(root, new Set());
  return matched.size;
}

export function admitEncounter(profile, context) {
  if (!profile.implementation.client_implemented) return {ok: false, reason: 'client_not_implemented'};
  const required = [...profile.implementation.required_components,
    ...(profile.implementation.new_discrete_features ?? [])];
  if (required.some(id => context.features[id] !== true)) return {ok: false, reason: 'missing_feature'};
  if (!profile.allowed_phases.includes(context.phase)) return {ok: false, reason: 'wrong_phase'};
  if ((profile.admission_requirements ?? []).some(key => context.facts?.[key] !== true))
    return {ok: false, reason: 'missing_world_fact'};
  if (!context.requiredCuesReachable || !context.criticalRouteReachable || !context.spawnSafe)
    return {ok: false, reason: 'unsafe_layout'};
  if (context.requiredSeconds > context.remainingSeconds) return {ok: false, reason: 'insufficient_budget'};
  if (context.conflictingReservation) return {ok: false, reason: 'exclusive_resource'};
  return {ok: true};
}
