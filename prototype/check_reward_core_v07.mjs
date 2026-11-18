import assert from 'node:assert/strict';
import fs from 'node:fs';
import {
  createRewardState, completeRewardWork, reserveFragmentReward, claimFragmentReward,
  declineFragmentReward, exchangeFragments, openDoubleChoice, readPendingChoice,
  chooseDoubleReward, purchaseQuotedItem, useRewardItem, transferRewardItem,
  beginPurchaseReturn, cancelPurchaseReturn, finishPurchaseReturn, changeProcurementWindow,
  commitWarningBonus
} from './reward_core_v07.mjs';

const catalog = JSON.parse(fs.readFileSync(new URL('../content/items.json', import.meta.url)));
const auxiliary = JSON.parse(fs.readFileSync(new URL('../content/auxiliary_targets_v07.json', import.meta.url)));
const supported = catalog.items.filter(x => x.acquisition_enabled).map(x => x.id);
const passed = [];
const test = (name, fn) => { fn(); passed.push(name); };
const fixture = options => createRewardState(catalog, {supportedItemIds: supported, ...options});
const job = (id, nightId, kind = 'optional_work_completed', rootRewardId = id) => ({id, nightId, kind, rootRewardId});
const finishJob = (s, id) => {
  const result = completeRewardWork(s, id); assert.equal(result.ok, true); return result.receiptId;
};
const draw = (s, id, candidates, selected) => {
  assert.equal(openDoubleChoice(s, {drawId: id, candidateItemIds: candidates}).ok, true);
  return chooseDoubleReward(s, {drawId: id, selectedItemId: selected});
};
function buildNineNonrare(s) {
  for (let i = 0; i < 9; i++) {
    changeProcurementWindow(s, {windowId: `history-${i}`});
    const fifth = i === 4;
    assert.equal(draw(s, `history-draw-${i}`, fifth ? ['I13', 'I14'] : ['I01', 'I02'], fifth ? 'I13' : 'I01').ok, true);
  }
  changeProcurementWindow(s, {windowId: 'after-nine'});
}

test('Disabled historical items cannot enter any new acquisition channel', () => {
  assert.equal(catalog.items.length, 24); assert.equal(supported.length, 22);
  for (const id of ['I22', 'I23']) {
    const row = catalog.items.find(x => x.id === id);
    for (const field of ['acquisition_enabled', 'shop_enabled', 'lottery_enabled', 'reward_enabled', 'crafting_enabled']) assert.equal(row[field], false);
  }
  assert.ok(auxiliary.acquisition.disabled_ids.includes('Q03'));
});

test('An invented completion or repeated completed job cannot generate fragments', () => {
  const s = fixture({jobs: [job('job1', 'night1')]});
  assert.equal(claimFragmentReward(s, 'invented').ok, false);
  const receipt = finishJob(s, 'job1');
  assert.equal(completeRewardWork(s, 'job1').ok, false);
  assert.equal(claimFragmentReward(s, receipt).ok, true);
  assert.equal(claimFragmentReward(s, receipt).ok, false);
  assert.equal(s.fragments, 1);
});

test('F47 and E065 wrappers with one root receipt cannot award twice', () => {
  const s = fixture({jobs: [job('sealed', 'night1', 'f47_sealed_reward', 'shared-root'), job('wrapper', 'night1', 'optional_work_completed', 'shared-root')]});
  const a = finishJob(s, 'sealed'), b = finishJob(s, 'wrapper');
  assert.equal(claimFragmentReward(s, a).ok, true);
  assert.equal(claimFragmentReward(s, b).reason, 'source_already_handled');
  assert.equal(s.fragments, 1);
});

test('One advertised night quota protects its owner from another completed work', () => {
  const s = fixture({jobs: [job('promised', 'night1'), job('other', 'night1')]});
  assert.equal(reserveFragmentReward(s, 'promised').ok, true);
  assert.equal(claimFragmentReward(s, finishJob(s, 'other')).reason, 'night_quota_unavailable');
  assert.equal(claimFragmentReward(s, finishJob(s, 'promised')).ok, true);
  assert.equal(s.fragments, 1);
});

test('Two different jobs in the same night cannot exceed one fragment source', () => {
  const s = fixture({jobs: [job('a', 'night1'), job('b', 'night1')]});
  assert.equal(claimFragmentReward(s, finishJob(s, 'a')).ok, true);
  assert.equal(claimFragmentReward(s, finishJob(s, 'b')).reason, 'night_quota_unavailable');
  assert.equal(s.fragments, 1);
});

test('Declining a source cannot later be undone into a reward', () => {
  const s = fixture({jobs: [job('a', 'night1')]}); const r = finishJob(s, 'a');
  assert.equal(declineFragmentReward(s, r).ok, true);
  assert.equal(claimFragmentReward(s, r).ok, false); assert.equal(s.fragments, 0);
});

test('Three separately earned fragments exchange once for one usable ticket', () => {
  const s = fixture({initialTickets: 0, jobs: [job('a', 'n1'), job('b', 'n2'), job('c', 'n3')]});
  for (const id of ['a', 'b', 'c']) claimFragmentReward(s, finishJob(s, id));
  assert.equal(s.fragments, 3); assert.equal(exchangeFragments(s, 'exchange-1').ok, true);
  assert.equal(s.fragments, 0); assert.equal(s.tickets, 1); assert.equal(s.prep.remaining, 45);
  const snapshot = JSON.stringify(s);
  assert.equal(exchangeFragments(s, 'exchange-1').ok, false); assert.equal(JSON.stringify(s), snapshot);
  assert.equal(draw(s, 'earned-draw', ['I01', 'I13'], 'I13').ok, true);
  assert.equal(s.tickets, 0); assert.equal(Object.keys(s.inventory).length, 1);
});

test('Too few fragments or a closed preparation window cannot consume anything', () => {
  const s = fixture({initialTickets: 0, jobs: [job('a', 'n1'), job('b', 'n2')]});
  for (const id of ['a', 'b']) claimFragmentReward(s, finishJob(s, id));
  let snapshot = JSON.stringify(s); assert.equal(exchangeFragments(s, 'short').ok, false); assert.equal(JSON.stringify(s), snapshot);
  changeProcurementWindow(s, {windowId: 'closed', open: false}); snapshot = JSON.stringify(s);
  assert.equal(exchangeFragments(s, 'closed').ok, false); assert.equal(JSON.stringify(s), snapshot);
});

test('Double choice saves both candidates and one ticket reservation before reveal', () => {
  const s = fixture({initialTickets: 2});
  assert.equal(openDoubleChoice(s, {drawId: 'draw', candidateItemIds: ['I01', 'I13']}).ok, true);
  assert.equal(s.tickets, 1); assert.equal(s.draws.draw.reservedTicket, 1);
  assert.equal(Object.keys(s.inventory).length, 0);
  assert.equal(openDoubleChoice(s, {drawId: 'reroll', candidateItemIds: ['I21', 'I24']}).ok, false);
  const restored = JSON.parse(JSON.stringify(s));
  assert.deepEqual(readPendingChoice(restored).candidates, ['I01', 'I13']);
  assert.equal(restored.tickets, 1);
});

test('Only the selected candidate exists and pity changes once on finalization', () => {
  const s = fixture({initialTickets: 2});
  const r = draw(s, 'one', ['I01', 'I13'], 'I13'); assert.equal(r.ok, true);
  assert.deepEqual(s.pity, {consecutiveCommon: 0, consecutiveNonrare: 1});
  assert.equal(s.tickets, 1); assert.equal(Object.values(s.inventory)[0].itemId, 'I13');
  const snapshot = JSON.stringify(s);
  assert.equal(chooseDoubleReward(s, {drawId: 'one', selectedItemId: 'I01'}).ok, false);
  assert.equal(JSON.stringify(s), snapshot);
});

test('Four real common results require noncommon candidates on the fifth draw', () => {
  const s = fixture({initialTickets: 8});
  for (let i = 0; i < 4; i++) {
    changeProcurementWindow(s, {windowId: `w${i}`}); assert.equal(draw(s, `d${i}`, ['I01', 'I02'], 'I01').ok, true);
  }
  changeProcurementWindow(s, {windowId: 'fifth'}); const snapshot = JSON.stringify(s);
  assert.equal(openDoubleChoice(s, {drawId: 'bad-fifth', candidateItemIds: ['I01', 'I02']}).ok, false);
  assert.equal(JSON.stringify(s), snapshot);
  assert.equal(draw(s, 'good-fifth', ['I13', 'I21'], 'I13').ok, true);
  assert.deepEqual(s.pity, {consecutiveCommon: 0, consecutiveNonrare: 5});
});

test('Nine real nonrare results enforce rare priority and do not count discarded candidates', () => {
  const s = fixture({initialTickets: 12}); buildNineNonrare(s);
  assert.deepEqual(s.pity, {consecutiveCommon: 4, consecutiveNonrare: 9});
  assert.equal(openDoubleChoice(s, {drawId: 'bad-tenth', candidateItemIds: ['I13', 'I21']}).ok, false);
  assert.equal(draw(s, 'tenth', ['I21', 'I24'], 'I24').ok, true);
  assert.deepEqual(s.pity, {consecutiveCommon: 0, consecutiveNonrare: 0});
});

test('Missing handlers, consumers or weighted rarity pools do not debit or weaken pity', () => {
  for (const options of [{supportedItemIds: []}, {consumerItemIds: []}, {supportedItemIds: ['I01', 'I02']}]) {
    const s = fixture(options), snapshot = JSON.stringify(s);
    assert.equal(openDoubleChoice(s, {drawId: 'blocked', candidateItemIds: ['I01', 'I02']}).ok, false);
    assert.equal(JSON.stringify(s), snapshot);
  }
  const s = fixture({initialTickets: 12}); buildNineNonrare(s);
  s.supported = s.supported.filter(x => !['I21', 'I24'].includes(x));
  const snapshot = JSON.stringify(s);
  assert.equal(openDoubleChoice(s, {drawId: 'no-rare', candidateItemIds: ['I01', 'I02']}).ok, false);
  assert.equal(JSON.stringify(s), snapshot);
});

test('A disabled rare result cannot be injected by the candidate adapter', () => {
  const s = fixture(), snapshot = JSON.stringify(s);
  assert.equal(openDoubleChoice(s, {drawId: 'disabled', candidateItemIds: ['I21', 'I22']}).ok, false);
  assert.equal(JSON.stringify(s), snapshot);
});

test('Pending double choice survives window close and cannot silently reroll next day', () => {
  const s = fixture({initialTickets: 2}); openDoubleChoice(s, {drawId: 'pending', candidateItemIds: ['I01', 'I13']});
  changeProcurementWindow(s, {windowId: 'night', open: false});
  assert.equal(chooseDoubleReward(s, {drawId: 'pending', selectedItemId: 'I13'}).ok, false);
  changeProcurementWindow(s, {windowId: 'next-day'});
  assert.equal(openDoubleChoice(s, {drawId: 'new', candidateItemIds: ['I21', 'I24']}).ok, false);
  assert.equal(chooseDoubleReward(s, {drawId: 'pending', selectedItemId: 'I13'}).ok, true);
  assert.equal(s.tickets, 1);
});

test('An original discounted purchase refunds its actual paid amount exactly once', () => {
  const s = fixture({quotes: [{id: 'q', itemId: 'I01', price: 9, windowId: 'procurement-1'}]});
  const buy = purchaseQuotedItem(s, 'q'); assert.equal(buy.ok, true); assert.equal(s.coins, 91);
  const begin = beginPurchaseReturn(s, buy.purchaseId); assert.equal(begin.ok, true);
  assert.equal(useRewardItem(s, buy.instanceId).ok, false); assert.equal(transferRewardItem(s, buy.instanceId).ok, false);
  assert.equal(finishPurchaseReturn(s, begin.returnId).amount, 9); assert.equal(s.coins, 100);
  assert.equal(s.inventory[buy.instanceId].owned, false);
  assert.equal(finishPurchaseReturn(s, begin.returnId).ok, false); assert.equal(beginPurchaseReturn(s, buy.purchaseId).ok, false);
  assert.equal(s.coins, 100);
});

test('Cancelling a pending return releases the original object without refund or time reset', () => {
  const s = fixture({quotes: [{id: 'q', itemId: 'I01', price: 9, windowId: 'procurement-1'}]});
  const buy = purchaseQuotedItem(s, 'q'), r = beginPurchaseReturn(s, buy.purchaseId);
  assert.equal(cancelPurchaseReturn(s, r.returnId).ok, true);
  assert.equal(s.inventory[buy.instanceId].lockedBy, null); assert.equal(s.coins, 91); assert.equal(s.prep.remaining, 55);
  assert.equal(finishPurchaseReturn(s, r.returnId).ok, false); assert.equal(useRewardItem(s, buy.instanceId).ok, true);
});

test('Used, transferred and lottery items cannot be presented as an unused paid purchase', () => {
  for (const action of [useRewardItem, transferRewardItem]) {
    const s = fixture({quotes: [{id: 'q', itemId: 'I01', price: 9, windowId: 'procurement-1'}]});
    const buy = purchaseQuotedItem(s, 'q'); action(s, buy.instanceId);
    assert.equal(beginPurchaseReturn(s, buy.purchaseId).ok, false); assert.equal(s.coins, 91);
  }
  const s = fixture(); const awarded = draw(s, 'lottery', ['I01', 'I13'], 'I01');
  assert.equal(beginPurchaseReturn(s, awarded.instanceId).ok, false); assert.equal(s.coins, 100);
});

test('Returning in another window or with less than five minutes left is rejected atomically', () => {
  const s = fixture({quotes: [{id: 'q', itemId: 'I01', price: 9, windowId: 'procurement-1'}]});
  const buy = purchaseQuotedItem(s, 'q');
  changeProcurementWindow(s, {windowId: 'procurement-2'}); let snapshot = JSON.stringify(s);
  assert.equal(beginPurchaseReturn(s, buy.purchaseId).ok, false); assert.equal(JSON.stringify(s), snapshot);
  changeProcurementWindow(s, {windowId: 'procurement-1', minute: 1318}); snapshot = JSON.stringify(s);
  assert.equal(beginPurchaseReturn(s, buy.purchaseId).ok, false); assert.equal(JSON.stringify(s), snapshot);
});

test('Closing a window cancels its pending return and preserves the item without money creation', () => {
  const s = fixture({quotes: [{id: 'q', itemId: 'I01', price: 9, windowId: 'procurement-1'}]});
  const buy = purchaseQuotedItem(s, 'q'), r = beginPurchaseReturn(s, buy.purchaseId);
  changeProcurementWindow(s, {windowId: 'closed', open: false});
  assert.equal(s.returns[r.returnId].state, 'cancelled'); assert.equal(s.inventory[buy.instanceId].owned, true);
  assert.equal(s.inventory[buy.instanceId].lockedBy, null); assert.equal(s.coins, 91);
});

test('One attack receives the strongest warning total, so two then three adds only one', () => {
  const ledger = {};
  const base = {attackId: 'dive', monsterId: 'F50', warningRemaining: 8, phaseBudgetRemaining: 20, shiftBudgetRemaining: 100};
  assert.equal(commitWarningBonus(ledger, {...base, sourceId: 'B04', requestedTotal: 1}).increment, 1);
  assert.equal(commitWarningBonus(ledger, {...base, sourceId: 'P05_special', requestedTotal: 2, warningRemaining: 9}).increment, 1);
  assert.equal(commitWarningBonus(ledger, {...base, sourceId: 'I21', requestedTotal: 3, warningRemaining: 10}).increment, 1);
  assert.equal(ledger.dive.total, 3);
  assert.equal(commitWarningBonus(ledger, {...base, sourceId: 'I21', requestedTotal: 3}).ok, false);
});

test('I21 rejects unsupported, expired, invented bonus and over-budget warnings without ledger change', () => {
  const base = {sourceId: 'I21', attackId: 'turn', monsterId: 'F60', requestedTotal: 3,
    warningRemaining: 8, phaseBudgetRemaining: 20, shiftBudgetRemaining: 50};
  for (const change of [{monsterId: 'F13'}, {warningRemaining: 0}, {requestedTotal: 8}, {phaseBudgetRemaining: 10}, {shiftBudgetRemaining: 10}]) {
    const ledger = {}; assert.equal(commitWarningBonus(ledger, {...base, ...change}).ok, false); assert.deepEqual(ledger, {});
  }
});

console.log(JSON.stringify({status: 'PASS', scenarioCount: passed.length, scenarios: passed,
  scope: 'Finite currency/item/source/pity transactions and warning-bonus arithmetic only. Fixed candidate and quote adapters; no RNG-distribution validation, real player work, full 60-monster AI, engine timing, touch or production storage crash test.'}, null, 2));
