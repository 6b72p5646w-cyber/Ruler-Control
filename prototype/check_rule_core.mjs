import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {dirname, resolve} from 'node:path';
import * as rules from './rule_core.mjs';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const load = name => JSON.parse(readFileSync(resolve(root, 'content', name + '.json'), 'utf8'));
const qte = load('qte');
const spatial = load('rule_components');
const blueprints = load('encounter_blueprints');
const f12 = blueprints.encounters.find(e => e.id === 'F12').parameters;
const f13 = blueprints.encounters.find(e => e.id === 'F13').parameters;
const results = [];
const check = (name, run) => {run(); results.push(name);};

check('Low SAN visibly narrows timing, with a 0.6 second floor', () => {
  const normal = rules.timingQte(100, qte);
  const low = rules.timingQte(10, qte);
  assert.ok(Math.abs(normal.windowSeconds - 1.2) < 1e-9);
  assert.ok(Math.abs(low.windowSeconds - 0.66) < 1e-9);
  assert.ok(rules.timingQte(1, qte, {eventMultiplier: 0}).windowSeconds >= 0.6);
  assert.equal(rules.timingQte(0, qte).canStart, false);
  const petHelp = rules.timingQte(10, qte, {targetScaleMultiplier: 1.12});
  assert.ok(petHelp.windowSeconds > low.windowSeconds && petHelp.windowSeconds < normal.windowSeconds);
});
check('All SAN bands keep a usable center and continuous numeric coverage', () => {
  for (let san = 0; san <= 100; san += 0.5) assert.ok(rules.timingQte(san, qte).clearRadius >= 2.6);
  assert.equal(rules.sanProfile(69.9, qte).id, 'uneasy');
});
check('Facing uses the avatar direction and static occlusion', () => {
  const r = spatial.components.find(x => x.id === 'RC01');
  const actor = {x: 0, y: 0, facing: {x: 1, y: 0}};
  assert.equal(rules.facingViolation(actor, {x: 3, y: 0}, r), true);
  assert.equal(rules.facingViolation(actor, {x: -3, y: 0}, r), false);
  assert.equal(rules.facingViolation(actor, {x: 3, y: 0}, r, false), false);
  assert.equal(rules.advanceExposure(0, true, 0.2, 1.5).triggered, false);
  assert.equal(rules.advanceExposure(1.4, true, 0.2, 1.5).triggered, true);
});
check('Distance bounds allow exact boundary and reject too close/far', () => {
  const r = spatial.components.find(x => x.id === 'RC03');
  assert.equal(rules.distanceViolation({x: 0, y: 0}, {x: 2.5, y: 0}, r), false);
  assert.equal(rules.distanceViolation({x: 0, y: 0}, {x: 2, y: 0}, r), true);
  assert.equal(rules.distanceViolation({x: 0, y: 0}, {x: 5, y: 0}, r), true);
});
check('Closeups cannot pause a chase or bypass spatial/budget restrictions', () => {
  const c = {activeChase: false, pendingHit: false, spatialRulesSatisfied: true,
    stationDistance: 1, san: 40, attemptCost: 4, remainingSeconds: 10};
  assert.equal(rules.canStartCloseup(c).ok, true);
  for (const patch of [{activeChase: true}, {pendingHit: true}, {spatialRulesSatisfied: false},
    {remainingSeconds: 3}, {san: 0}]) assert.equal(rules.canStartCloseup({...c, ...patch}).ok, false);
});
check('Started cancellations pay once and do not complete work', () => {
  const ledger = {remainingSeconds: 20, settledAttemptIds: [], workReceipts: []};
  const attempt = {id: 'a1', started: true, cost: 4, outcome: 'cancelled'};
  const paid = rules.settleCloseup(ledger, attempt);
  assert.equal(paid.remainingSeconds, 16);
  assert.equal(paid.workReceipts.length, 0);
  assert.deepEqual(rules.settleCloseup(paid, attempt), paid);
  assert.equal(rules.settleCloseup(ledger, {...attempt, started: false}).remainingSeconds, 20);
});

const bait = (id, x, more = {}) => ({id, x, y: 0, active: true, reachable: true,
  tag: 'paperclip_bait', sourceAction: 'player_scatter', expiresAt: 30, ...more});
const initial12 = {mode: 'CHASE_PLAYER', baitId: null, exitHold: 0};
const world12 = {monster: {x: 0, y: 0}, player: {x: 3, y: 0}, now: 0,
  baits: [], wholeBodyInExitZone: false, reachedBaitId: null};
check('Paperclip scatter consumes one charge only for a legal world placement', () => {
  const c = {id: 'b1', now: 0, player: {x: 0, y: 0}, point: {x: 1, y: 0},
    legalCell: true, reachable: true, clearThrow: true, handsOccupied: false, activeBaitCount: 0};
  assert.equal(rules.scatterPaperclips({paperclipCharges: 6}, c, f12).inventory.paperclipCharges, 5);
  assert.equal(rules.scatterPaperclips({paperclipCharges: 6}, {...c, point: {x: 9, y: 0}}, f12).inventory.paperclipCharges, 6);
  assert.equal(rules.scatterPaperclips({paperclipCharges: 6}, {...c, activeBaitCount: 3}, f12).ok, false);
});
check('F12 defaults to player and does not clear from an unbaited exit', () => {
  const r = rules.stepF12(initial12, {...world12, wholeBodyInExitZone: true}, f12, 1);
  assert.equal(r.target.kind, 'player'); assert.equal(r.canAttack, true);
  assert.equal(r.navigationScope, 'store_interior_only'); assert.notEqual(r.state.mode, 'CLEARED');
});
check('F12 picks reachable bait, locks target, and ignores arbitrary metal', () => {
  const picked = rules.stepF12(initial12, {...world12, baits: [bait('far', 4), bait('near', 2),
    bait('wall', 1, {reachable: false}), bait('fake', 0.2, {tag: 'metal_shelf'})]}, f12, 0.2);
  assert.equal(picked.target.id, 'near'); assert.equal(picked.canAttack, false);
  const locked = rules.stepF12(picked.state, {...world12, baits: [bait('near', 2), bait('new', 1)]}, f12, 0.2);
  assert.equal(locked.target.id, 'near');
});
check('F12 eating pauses attacks and consumes its bait once before reselecting', () => {
  const seek = {mode: 'SEEK_BAIT', baitId: 'b', exitHold: 0};
  const eating = rules.stepF12(seek, {...world12, baits: [bait('b', 0)], reachedBaitId: 'b'}, f12, 0.2);
  assert.equal(eating.state.mode, 'EAT_BAIT'); assert.equal(eating.canAttack, false);
  const done = rules.stepF12(eating.state, {...world12, baits: [bait('b', 0), bait('next', 2)]}, f12, 2);
  assert.equal(done.events.filter(e => e.type === 'consume_bait').length, 1);
  assert.equal(done.target.id, 'next');
});
check('F12 clears only after the lured body holds beyond the exit, then stays cleared', () => {
  const w = {...world12, baits: [bait('exit', 2)], wholeBodyInExitZone: true};
  const a = rules.stepF12({mode: 'SEEK_BAIT', baitId: 'exit', exitHold: 0}, w, f12, 0.2);
  assert.notEqual(a.state.mode, 'CLEARED');
  const b = rules.stepF12(a.state, w, f12, 0.2);
  assert.equal(b.state.mode, 'CLEARED'); assert.equal(b.events.length, 1);
  assert.equal(rules.stepF12(b.state, world12, f12, 0.2).events.length, 0);
});
check('Expired bait returns F12 to chasing, without adding growth', () => {
  const r = rules.stepF12({mode: 'SEEK_BAIT', baitId: 'b', exitHold: 0},
    {...world12, now: 40, baits: [bait('b', 2)]}, f12, 0.2);
  assert.equal(r.state.mode, 'CHASE_PLAYER'); assert.equal(r.target.kind, 'player');
  assert.equal('growth' in r.state, false);
});
check('P04 extends the current eating pause once and cannot create a second extension', () => {
  const state = {mode: 'EAT_BAIT', baitId: 'b', eatRemaining: 1, exitHold: 0};
  const help = rules.extendPlayerLure(state, bait('b', 0));
  assert.equal(help.ok, true); assert.equal(help.state.eatRemaining, 2);
  const progressed = rules.stepF12(help.state, {...world12, baits: [help.bait]}, f12, 0.2);
  assert.equal(progressed.state.eatRemaining, 1.8);
  assert.equal(rules.extendPlayerLure(progressed.state, help.bait).ok, false);
});

const initial13 = {mode: 'SEEK_MEAT', instanceId: 'enc-F13-1', requiredMeatId: 'meat1', registeredFreezerId: 'freezer1'};
const world13 = {encounterInstanceId: 'enc-F13-1', player: {x: 0, y: 0}, meat: {id: 'meat1', carrierId: 'player', storedIn: null},
  freezer: {id: 'freezer1', x: 1, y: 0, functional: true, operable: true, reservedSpace: true, closed: false}, touchingMeat: false};
check('F13 seeks meat, telegraphs touch, then persists in chase after the meat is dropped', () => {
  assert.equal(rules.stepF13(initial13, world13, f13, 0.2).target.kind, 'meat');
  const angry = rules.stepF13(initial13, {...world13, touchingMeat: true}, f13, 0.2);
  assert.equal(angry.state.mode, 'RAGE_WINDUP'); assert.equal(angry.canAttack, false);
  const chasing = rules.stepF13(angry.state, world13, f13, 1.5);
  assert.equal(chasing.state.mode, 'CHASE_PLAYER');
  const dropped = {...world13, meat: {...world13.meat, carrierId: null}};
  assert.equal(rules.stepF13(chasing.state, dropped, f13, 0.2).target.kind, 'player');
});
check('F13 can be prevented by early delivery; success wins simultaneous touch', () => {
  const stored = rules.storeTaskMeat(world13, 'meat1', 'freezer1');
  assert.equal(stored.ok, true); assert.equal(stored.world.meat.carrierId, null);
  const r = rules.stepF13(initial13, {...stored.world, touchingMeat: true}, f13, 0.2);
  assert.equal(r.state.mode, 'CLEARED'); assert.equal(r.canAttack, false);
});
check('Touching unrelated food cannot trigger the registered meat encounter', () => {
  const unrelated = {...world13, meat: {...world13.meat, id: 'other'}, touchingMeat: true};
  assert.equal(rules.stepF13(initial13, unrelated, f13, 0.2).state.mode, 'SEEK_MEAT');
});
check('Committed delivery survives same-frame power loss before enemy evaluation', () => {
  const stored = rules.storeTaskMeat(world13, 'meat1', 'freezer1').world;
  const powerLoss = {...stored, freezer: {...stored.freezer, functional: false, closed: false}, touchingMeat: true};
  assert.equal(rules.stepF13(initial13, powerLoss, f13, 0.2).state.mode, 'CLEARED');
  assert.notEqual(rules.stepF13({...initial13, instanceId: 'another-encounter'}, powerLoss, f13, 0.2).state.mode, 'CLEARED');
});
check('Unavailable, distant and wrong freezers cannot lose the meat or clear the encounter', () => {
  for (const patch of [{functional: false}, {reservedSpace: false}, {operable: false}, {x: 5}, {id: 'other'}]) {
    const w = {...world13, freezer: {...world13.freezer, ...patch}};
    const r = rules.storeTaskMeat(w, 'meat1', 'freezer1');
    assert.equal(r.ok, false); assert.equal(r.world.meat.carrierId, 'player');
    assert.notEqual(rules.stepF13(initial13, r.world, f13, 0.2).state.mode, 'CLEARED');
  }
});
check('F13 remains terminal after later freezer opening or power loss', () => {
  const stored = rules.storeTaskMeat(world13, 'meat1', 'freezer1').world;
  const cleared = rules.stepF13(initial13, stored, f13, 0.2).state;
  const later = {...stored, freezer: {...stored.freezer, closed: false, functional: false}};
  const r = rules.stepF13(cleared, later, f13, 1);
  assert.equal(r.state.mode, 'CLEARED'); assert.equal(r.events.length, 0);
});
check('First contact applies a discrete injury and shared grace, not instant failure', () => {
  const first = rules.applySharedHit({san: 50}, 10, blueprints.shared_attack_proposal);
  assert.equal(first.actor.san, 40); assert.equal(first.actor.injury, 'minor');
  const sameFrameOtherMonster = rules.applySharedHit(first.actor, 10, blueprints.shared_attack_proposal);
  assert.equal(sameFrameOtherMonster.applied, false); assert.equal(sameFrameOtherMonster.actor.san, 40);
});

console.log(JSON.stringify({status: 'PASS', scenarioCount: results.length, scenarios: results,
  scope: 'Pure rule transitions and configuration only. No navigation, rendering, touch UI, performance or WeChat runtime verified.'}, null, 2));
