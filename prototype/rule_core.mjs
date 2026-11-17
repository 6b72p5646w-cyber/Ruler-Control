/**
 * Small, deterministic V0.4 rule reference. No renderer, navigation, input UI,
 * WeChat integration or complete game is implemented here. Positions, reachability,
 * collision facts and completed interaction commands are supplied by a future client.
 */

const clamp = (x, lo, hi) => Math.max(lo, Math.min(hi, x));
export const distance = (a, b) => Math.hypot(a.x - b.x, a.y - b.y);

export function sanProfile(san, config) {
  if (!Number.isFinite(san)) throw new TypeError('SAN must be finite');
  const value = Math.floor(clamp(san, 0, 100));
  const band = config.bands.find(b => value >= b.san_min && value <= b.san_max);
  if (!band) throw new Error('Missing SAN band');
  return {...band};
}

export function timingQte(san, config, {eventMultiplier = 1, targetScaleMultiplier = 1,
  bonusFraction = 0, taskId = null, segmentIndex = 0, taskWindowBonusSeconds = 0} = {}) {
  const band = sanProfile(san, config);
  const template = config.templates.find(t => t.id === 'QT01');
  const policy = config.common_modifier_policy;
  const task = taskId === null ? null : config.task_profiles?.find(t => t.id === taskId);
  if (taskId !== null && !task) throw new Error('Unknown QTE task profile');
  if (task && (!Number.isInteger(segmentIndex) || segmentIndex < 0 ||
    segmentIndex >= task.segment_base_windows_seconds.length)) throw new RangeError('Invalid QTE segment');
  if (!task && taskWindowBonusSeconds !== 0) throw new Error('Task seconds bonus requires a registered task profile');
  // Eight seconds is the song attempt's advertised work cost, not the sweep cycle.
  const baseFraction = task ? task.segment_base_windows_seconds[segmentIndex] / template.cycle_seconds : template.base_target_fraction;
  const event = clamp(eventMultiplier, policy.event_precision_multiplier_min, 1);
  const bonus = clamp(bonusFraction, 0, policy.precision_bonus_fraction_max);
  const rawBase = baseFraction * band.target_multiplier * event;
  const scaled = Math.min(baseFraction, rawBase * clamp(targetScaleMultiplier, 1, policy.target_scale_multiplier_max));
  const unassisted = Math.max(config.timing_window_seconds_min / template.cycle_seconds, rawBase);
  // P03's task-specific +0.4s is exact even when SAN already hits the 0.6s floor.
  // It competes with other increases rather than stacking with them.
  const taskHelp = task ? unassisted + clamp(taskWindowBonusSeconds, 0, task.task_bonus_seconds_max) / template.cycle_seconds : rawBase;
  const raw = Math.max(scaled, rawBase + bonus, taskHelp);
  const fraction = clamp(raw, config.timing_window_seconds_min / template.cycle_seconds,
    template.target_fraction_max);
  return {bandId: band.id, targetFraction: fraction,
    windowSeconds: fraction * template.cycle_seconds,
    clearRadius: Math.max(config.world_clear_radius_tiles_min, band.clear_radius_tiles),
    canStart: band.new_precision_qte_allowed !== false};
}

export function facingViolation(actor, target, rule, hasClearSight = true) {
  const d = distance(actor, target);
  if (!hasClearSight || d > rule.range_tiles) return false;
  if (d === 0) return true;
  const norm = Math.hypot(actor.facing.x, actor.facing.y);
  if (norm === 0) return false;
  const cosine = (actor.facing.x * (target.x - actor.x) + actor.facing.y * (target.y - actor.y)) / (norm * d);
  return cosine + 1e-9 >= Math.cos(rule.cone_degrees * Math.PI / 360);
}

export function distanceViolation(actor, target, rule) {
  const d = distance(actor, target);
  return d < rule.minimum_tiles || (rule.maximum_tiles !== undefined && d > rule.maximum_tiles);
}

export function advanceExposure(previousSeconds, violating, dt, graceSeconds) {
  const seconds = violating ? previousSeconds + dt : 0;
  return {seconds, triggered: previousSeconds < graceSeconds && seconds + 1e-9 >= graceSeconds};
}

export function canStartCloseup(context) {
  if (context.activeChase) return {ok: false, reason: 'active_chase'};
  if (context.pendingHit) return {ok: false, reason: 'pending_hit'};
  if (!context.spatialRulesSatisfied) return {ok: false, reason: 'spatial_rule'};
  if (context.stationDistance > 1) return {ok: false, reason: 'too_far'};
  if (context.san <= 0) return {ok: false, reason: 'panic'};
  if (context.attemptCost > context.remainingSeconds) return {ok: false, reason: 'insufficient_budget'};
  return {ok: true, reservedSeconds: context.attemptCost};
}

export function settleCloseup(ledger, attempt) {
  // Read-only preparation does not create an attempt. Pressing Start does.
  if (!attempt.started || ledger.settledAttemptIds.includes(attempt.id)) return {...ledger};
  if (attempt.cost > ledger.remainingSeconds) throw new Error('Attempt was not properly reserved');
  return {...ledger, remainingSeconds: ledger.remainingSeconds - attempt.cost,
    settledAttemptIds: [...ledger.settledAttemptIds, attempt.id],
    workReceipts: attempt.outcome === 'success' ? [...ledger.workReceipts, attempt.id] : [...ledger.workReceipts]};
}

export function scatterPaperclips(inventory, command, params) {
  const fail = reason => ({ok: false, reason, inventory: {...inventory}});
  if (inventory.paperclipCharges <= 0) return fail('empty');
  if (command.handsOccupied) return fail('hands_occupied');
  if (!command.reachable || !command.clearThrow || !command.legalCell) return fail('illegal_cell');
  if (distance(command.player, command.point) > params.bait_place_distance) return fail('out_of_range');
  if (command.activeBaitCount >= params.max_active_bait_points) return fail('bait_limit');
  return {ok: true, inventory: {...inventory, paperclipCharges: inventory.paperclipCharges - 1},
    bait: {id: command.id, ...command.point, tag: 'paperclip_bait', sourceAction: 'player_scatter',
      active: true, reachable: true, expiresAt: command.now + params.bait_lifetime_seconds}};
}

export function stepF12(previous, world, params, dt) {
  let state = {...previous};
  const events = [];
  if (state.mode === 'CLEARED') return {state, target: null, events, canAttack: false};
  const valid = b => b.active && b.reachable && b.expiresAt > world.now &&
    b.tag === 'paperclip_bait' && b.sourceAction === 'player_scatter';
  let locked = world.baits.find(b => b.id === state.baitId && valid(b));
  const lured = ['SEEK_BAIT', 'EAT_BAIT'].includes(state.mode) && !!locked;
  state.exitHold = lured && world.wholeBodyInExitZone ? (state.exitHold || 0) + dt : 0;
  if (state.exitHold + 1e-9 >= params.exit_full_collider_hold_seconds) {
    state.mode = 'CLEARED';
    events.push({type: 'encounter_cleared', id: 'F12'});
    return {state, target: null, events, canAttack: false};
  }
  let consumedId = null;
  if (state.mode === 'EAT_BAIT' && locked) {
    state.eatRemaining = Math.max(0, state.eatRemaining - dt);
    if (state.eatRemaining > 0) return {state, target: null, events, canAttack: false};
    consumedId = locked.id;
    events.push({type: 'consume_bait', id: consumedId});
    locked = undefined;
    state.mode = 'CHASE_PLAYER';
    state.baitId = null;
  }
  if (state.mode === 'EAT_BAIT' && !locked) state.mode = 'CHASE_PLAYER';
  if (!locked) {
    const candidates = world.baits.filter(b => valid(b) && b.id !== consumedId &&
      distance(world.monster, b) <= params.bait_detection_radius);
    candidates.sort((a, b) => distance(world.monster, a) - distance(world.monster, b) ||
      (a.id < b.id ? -1 : a.id > b.id ? 1 : 0));
    locked = candidates[0];
    state.baitId = locked?.id ?? null;
    state.mode = locked ? 'SEEK_BAIT' : 'CHASE_PLAYER';
  }
  if (locked && state.mode === 'CHASE_PLAYER') state.mode = 'SEEK_BAIT';
  if (locked && state.mode === 'SEEK_BAIT' && world.reachedBaitId === locked.id) {
    state.mode = 'EAT_BAIT';
    state.eatRemaining = params.eat_pause_seconds + (locked.extraEatSeconds || 0);
    return {state, target: null, events, canAttack: false};
  }
  return {state, target: locked ? {kind: 'bait', id: locked.id, x: locked.x, y: locked.y} : {kind: 'player'},
    navigationScope: locked ? 'store_and_marked_exit_pad' : 'store_interior_only',
    canAttack: state.mode === 'CHASE_PLAYER', events};
}

export function extendPlayerLure(state, bait, extraSeconds = 1) {
  if (!bait.active || bait.tag !== 'paperclip_bait' || bait.sourceAction !== 'player_scatter' || bait.petExtensionUsed) {
    return {ok: false, state: {...state}, bait: {...bait}};
  }
  const updatedBait = {...bait, petExtensionUsed: true, extraEatSeconds: (bait.extraEatSeconds || 0) + extraSeconds};
  const updatedState = state.mode === 'EAT_BAIT' && state.baitId === bait.id ?
    {...state, eatRemaining: state.eatRemaining + extraSeconds} : {...state};
  return {ok: true, state: updatedState, bait: updatedBait};
}

export function storeTaskMeat(world, requiredMeatId, registeredFreezerId) {
  const fail = reason => ({ok: false, reason, world});
  if (world.meat.id !== requiredMeatId || world.meat.carrierId !== 'player') return fail('wrong_or_uncarried_item');
  if (world.freezer.id !== registeredFreezerId) return fail('wrong_freezer');
  if (!world.freezer.functional || !world.freezer.operable || !world.freezer.reservedSpace) return fail('freezer_unavailable');
  if (distance(world.player, world.freezer) > 1) return fail('too_far');
  if (!world.encounterInstanceId) return fail('missing_encounter_instance');
  const receipt = {encounterInstanceId: world.encounterInstanceId, itemId: requiredMeatId,
    containerId: registeredFreezerId, closedAtCommit: true, functionalAtCommit: true, committed: true};
  return {ok: true, world: {...world,
    meat: {...world.meat, carrierId: null, storedIn: registeredFreezerId},
    freezer: {...world.freezer, closed: true, reservedSpace: false},
    deliveryReceipts: [...(world.deliveryReceipts || []), receipt]}};
}

export function stepF13(previous, world, params, dt) {
  const state = {...previous};
  const events = [];
  if (state.mode === 'CLEARED') return {state, target: null, events, canAttack: false};
  // Caller commits completed inventory commands first. Valid delivery wins a simultaneous touch.
  const secured = (world.deliveryReceipts || []).some(r => r.encounterInstanceId === state.instanceId &&
    r.itemId === state.requiredMeatId && r.containerId === state.registeredFreezerId &&
    r.committed && r.closedAtCommit && r.functionalAtCommit);
  if (secured) {
    state.mode = 'CLEARED';
    events.push({type: 'encounter_cleared', id: 'F13'});
    return {state, target: null, events, canAttack: false};
  }
  if (state.mode === 'SEEK_MEAT' && world.touchingMeat && world.meat.id === state.requiredMeatId) {
    state.mode = 'RAGE_WINDUP';
    state.windupRemaining = params.rage_windup_seconds;
    return {state, target: null, events: [{type: 'rage_telegraph'}], canAttack: false};
  }
  if (state.mode === 'RAGE_WINDUP') {
    state.windupRemaining = Math.max(0, state.windupRemaining - dt);
    if (state.windupRemaining <= 1e-9) state.mode = 'CHASE_PLAYER';
  }
  const target = state.mode === 'SEEK_MEAT' ? {kind: 'meat', id: state.requiredMeatId} :
    state.mode === 'CHASE_PLAYER' ? {kind: 'player'} : null;
  return {state, target, events, canAttack: state.mode === 'CHASE_PLAYER'};
}

export function applySharedHit(actor, now, attack) {
  if (now < (actor.collisionGraceUntil || 0)) return {actor: {...actor}, applied: false};
  return {applied: true, actor: {...actor, san: Math.max(0, actor.san - attack.san_damage),
    injury: 'minor', collisionGraceUntil: now + attack.collision_grace_seconds}};
}
