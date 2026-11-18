/**
 * Finite settlement model for a completed day action. The real day scheduler,
 * UI and trustworthy immutable observation producer are external adapters.
 * This module cannot prove that a caller's world observation actually happened.
 * It accepts record IDs from its declared registry, never a claimed verdict or
 * a hidden identity supplied to a review call. Numeric policy comes from balance.
 */
const clone = value => JSON.parse(JSON.stringify(value));
const fail = reason => ({ok: false, reason});
const nonempty = value => typeof value === 'string' && value.length > 0;

function visibleRecord(raw, policy) {
  if (!raw || !['id','rootSourceId','runId','sceneId','subjectId','evaluationWindow'].every(k => nonempty(raw[k])) ||
      !policy.allowed_record_producer_kinds.includes(raw.producerKind) || raw.completed !== true || raw.visible !== true) return null;
  return Object.fromEntries([
    ...['id','rootSourceId','runId','sceneId','subjectId','evaluationWindow','producerKind'].map(k => [k,raw[k]]),
    ['completed',true],['visible',true],['label',typeof raw.label === 'string' ? raw.label : raw.id],
    ['claimId',nonempty(raw.claimId) ? raw.claimId : null],
    ['observations',(raw.observations ?? []).filter(x => x && nonempty(x.predicateId) &&
      typeof x.value === 'boolean' && nonempty(x.method) && x.visible === true)
      .map(x => ({predicateId:x.predicateId,value:x.value,method:x.method,visible:true}))],
  ]);
}

export function createDayKnowledgeState(balance, options = {}) {
  const policy = clone(balance.knowledge);
  const pages = Object.fromEntries(policy.method_pages.map(x => [x.id,x]));
  const sourceRecords = {};
  for (const raw of options.sourceRecords ?? []) {
    const r = visibleRecord(raw, policy.case_review);
    if (!r) continue;
    if (sourceRecords[r.id] && JSON.stringify(sourceRecords[r.id]) !== JSON.stringify(r)) {
      throw new Error('One record ID cannot describe two source facts');
    }
    sourceRecords[r.id] = r;
  }
  const availableSlots = options.availableSlots ?? balance.day_action_slots;
  if (!Number.isSafeInteger(availableSlots) || availableSlots < 0 || availableSlots > balance.day_action_slots) {
    throw new Error('Invalid declared remaining day slots');
  }
  const unlocked = {};
  for (const id of options.unlockedPageIds ?? []) {
    if (!pages[id]) throw new Error('Unknown unlocked method page');
    unlocked[id] = {origin:'prior_saved_progress'};
  }
  return {dayId:options.dayId ?? 'day-1', policy, pages,
    dayActions:Object.fromEntries(balance.day_actions.map(x => [x.id,clone(x)])),
    claims:Object.fromEntries(policy.case_claim_catalog.map(x => [x.id,x])),
    sourceRecords, remainingSlots:availableSlots,
    energy:Math.max(balance.resources.energy.min,Math.min(balance.resources.energy.max,options.initialEnergy ?? 50)),
    energyMin:balance.resources.energy.min, energyMax:balance.resources.energy.max,
    studyPoints:0, studyPointsEarned:0, studyPointsSpent:0,
    researchProgress:0, researchProgressEarned:0, researchProgressSpent:0,
    unlockedPages:unlocked, cases:{}, reviewedRoots:{}, actionReceipts:{}, ledger:[]};
}

export function canSelectDayAction(s, actionId) {
  const action = s.dayActions[actionId];
  if (!action || action.enabled === false || action.selectable === false) return fail('action_unavailable');
  if (s.remainingSlots < action.slots) return fail('no_day_slot');
  return {ok:true};
}

function actionGuard(s, actionId, kind) {
  if (!nonempty(actionId) || s.actionReceipts[actionId]) return fail('action_already_settled_or_invalid');
  return canSelectDayAction(s,kind);
}

function spendCompletedAction(s, actionId, actionKind, payload) {
  const action = s.dayActions[actionKind];
  s.remainingSlots -= action.slots;
  s.energy = Math.max(s.energyMin,Math.min(s.energyMax,s.energy+(action.energy_delta ?? 0)));
  s.actionReceipts[actionId] = {id:actionId, dayId:s.dayId, actionKind, slots:action.slots,
    energyDelta:action.energy_delta ?? 0, ...clone(payload)};
  s.ledger.push(clone(s.actionReceipts[actionId]));
}

export function settleStudyAction(s, {actionId,pageId}) {
  const p=s.policy.study_action, guard=actionGuard(s,actionId,p.action_id);
  if (!guard.ok) return guard;
  const page=s.pages[pageId];
  if (!page || s.unlockedPages[pageId]) return fail('no_new_method_page');
  if (p.points_per_completed_action < p.page_price) return fail('declared_study_points_insufficient');
  spendCompletedAction(s,actionId,p.action_id,{pageId,pointsEarned:p.points_per_completed_action,pointsSpent:p.page_price});
  s.studyPoints += p.points_per_completed_action-p.page_price;
  s.studyPointsEarned += p.points_per_completed_action; s.studyPointsSpent += p.page_price;
  s.unlockedPages[pageId] = {actionId,dayId:s.dayId};
  return {ok:true,page:clone(page),receipt:clone(s.actionReceipts[actionId])};
}

function evaluateClaim(s, claimId, records) {
  const claim=s.claims[claimId];
  if (!claim) return {status:'HYPOTHESIS',recognizedRoots:[],reason:'no_registered_claim'};
  const values=new Map(), recognizedRoots=new Set();
  const predicates=new Map(claim.predicates.map(p=>[p.id,p]));
  for (const r of records) {
    if (r.claimId!==claimId || r.evaluationWindow!==claim.evaluation_window) continue;
    for (const observation of r.observations) {
      const p=predicates.get(observation.predicateId);
      if (!p || !p.allowed_methods.includes(observation.method)) continue;
      const key=observation.predicateId+'|'+observation.value;
      if (!values.has(key)) values.set(key,new Set());
      values.get(key).add(r.rootSourceId); recognizedRoots.add(r.rootSourceId);
    }
  }
  const roots=[...recognizedRoots];
  for (const p of claim.predicates) {
    if (values.has(p.id+'|true') && values.has(p.id+'|false')) {
      return {status:'CONFLICTED',recognizedRoots:roots,reason:'contradictory_actual_observations'};
    }
  }
  const enough=roots.length>=s.policy.case_review.minimum_independent_roots_for_claim_verdict;
  const matches=criteria=>criteria.length>0 && criteria.every(c=>values.has(c.predicate_id+'|'+c.value));
  const confirmed=matches(claim.confirmation), refuted=matches(claim.refutation);
  if (confirmed && refuted) return {status:'CONFLICTED',recognizedRoots:roots,reason:'overlapping_claim_criteria'};
  if (enough && confirmed) return {status:'VERIFIED',recognizedRoots:roots,reason:'registered_confirmation_met'};
  if (enough && refuted) return {status:'REFUTED',recognizedRoots:roots,reason:'registered_refutation_met'};
  return {status:'HYPOTHESIS',recognizedRoots:roots,reason:'insufficient_relevant_independent_evidence'};
}

export function settleCaseReview(s,{actionId,claimId=null,sourceRecordIds}) {
  const p=s.policy.case_review,guard=actionGuard(s,actionId,p.action_id);
  if (!guard.ok) return guard;
  if (!Array.isArray(sourceRecordIds) || !sourceRecordIds.length ||
      new Set(sourceRecordIds).size!==sourceRecordIds.length || sourceRecordIds.some(id=>!s.sourceRecords[id])) {
    return fail('actual_record_ids_required');
  }
  if (claimId!==null && !s.claims[claimId]) return fail('unknown_claim_use_unverified_notes');
  const selected=sourceRecordIds.map(id=>s.sourceRecords[id]);
  const first=selected[0];
  if (selected.some(r=>r.runId!==first.runId || r.sceneId!==first.sceneId ||
      r.subjectId!==first.subjectId || r.evaluationWindow!==first.evaluationWindow)) {
    return fail('records_do_not_describe_same_bound_case');
  }
  const roots=[...new Set(selected.map(r=>r.rootSourceId))];
  const newRoots=roots.filter(root=>!s.reviewedRoots[root]);
  if (!newRoots.length) return fail('no_new_root_source');
  const key=JSON.stringify([claimId,first.runId,first.sceneId,first.subjectId,first.evaluationWindow]);
  const old=s.cases[key];
  const mergedIds=[...new Set([...(old?.sourceRecordIds ?? []),...sourceRecordIds])];
  const records=mergedIds.map(id=>s.sourceRecords[id]);
  const verdict=evaluateClaim(s,claimId,records);
  spendCompletedAction(s,actionId,p.action_id,{caseKey:key,rootSourceIds:newRoots,
    progressEarned:p.progress_per_completed_action,progressSpent:p.progress_consumed_per_case_revision});
  s.researchProgress += p.progress_per_completed_action-p.progress_consumed_per_case_revision;
  s.researchProgressEarned += p.progress_per_completed_action;
  s.researchProgressSpent += p.progress_consumed_per_case_revision;
  for (const root of newRoots) s.reviewedRoots[root]=actionId;
  s.cases[key]={key,claimId,runId:first.runId,sceneId:first.sceneId,subjectId:first.subjectId,
    evaluationWindow:first.evaluationWindow,revision:(old?.revision ?? 0)+1,sourceRecordIds:mergedIds,
    sourceRecords:records.map(clone),...verdict,
    authenticatesCurrentIdentity:false,changesCurrentPermissions:false};
  return {ok:true,casePage:clone(s.cases[key]),receipt:clone(s.actionReceipts[actionId])};
}
