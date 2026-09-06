import assert from "node:assert/strict";
import test from "node:test";
import { drawCard } from "./.build/draw.js";

function randomValues(...values) {
  return () => {
    assert.ok(values.length > 0, "unexpected random call");
    return values.shift();
  };
}

test("probability boundaries select the expected rarity", () => {
  for (const [roll, rarity] of [
    [0, "R"],
    [0.799999999, "R"],
    [0.8, "SR"],
    [0.979999999, "SR"],
    [0.98, "SSR"],
    [0.999999999, "SSR"],
  ]) {
    assert.equal(drawCard(0, randomValues(roll, 0)).card.rarity, rarity);
  }
});

test("each rarity has two equally sized card selection intervals", () => {
  for (const roll of [0, 0.8, 0.98]) {
    const first = drawCard(0, randomValues(roll, 0)).card;
    assert.deepEqual(drawCard(0, randomValues(roll, 0.499999999)).card, first);
    const second = drawCard(0, randomValues(roll, 0.5)).card;
    assert.notEqual(first.name, second.name);
    assert.deepEqual(drawCard(0, randomValues(roll, 0.999999999)).card, second);
  }
});

test("49 misses force an SSR on draw 50 and reset the cycle", () => {
  let misses = 0;
  for (let count = 1; count <= 49; count++) {
    const result = drawCard(misses, randomValues(count % 2 ? 0 : 0.8, 0));
    misses = result.misses;
    assert.equal(misses, count);
    assert.equal(result.guaranteed, false);
  }
  const result = drawCard(misses, randomValues(0));
  assert.equal(result.card.rarity, "SSR");
  assert.equal(result.guaranteed, true);
  assert.equal(result.misses, 0);
  assert.equal(drawCard(result.misses, randomValues(0, 0)).misses, 1);
});

test("early SSR resets misses while SR increments them", () => {
  assert.equal(drawCard(12, randomValues(0.8, 0)).misses, 13);
  const result = drawCard(12, randomValues(0.98, 0));
  assert.equal(result.misses, 0);
  assert.equal(result.guaranteed, false);
  assert.equal(drawCard(result.misses, randomValues(0.8, 0)).misses, 1);
});

test("invalid pity counters are rejected", () => {
  for (const misses of [-1, 50, 0.5, NaN]) {
    assert.throws(() => drawCard(misses), RangeError);
  }
});
