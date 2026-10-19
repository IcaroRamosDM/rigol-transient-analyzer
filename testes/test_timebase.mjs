import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { configureTimebase, normalizeTime, adjacentTime, timeStep, formatTime } from "../interface/static/modules/timebase.js";

configureTimebase(JSON.parse(readFileSync(0,"utf8").replace(/^\uFEFF/,"")));
for(const [value,next] of [[198e-6,200e-6],[200e-6,205e-6],[205e-6,210e-6],
    [495e-6,500e-6],[500e-6,510e-6],[19.8e-9,20e-9],[5e-9,5.1e-9]]) {
  assert.equal(adjacentTime(value,1),next);
  assert.equal(adjacentTime(next,-1),value);
}
assert.equal(normalizeTime(206e-6),205e-6);
assert.equal(adjacentTime(206e-6,-1),205e-6);
assert.equal(adjacentTime(206e-6,1),210e-6);
assert.equal(timeStep(210e-6),5e-6);
assert.equal(timeStep(198e-6),2e-6);
assert.equal(normalizeTime(.21/1000),210e-6);
assert.equal(formatTime(210e-6,"ms"),"0,21 ms");
assert.equal(adjacentTime(5e-9,-1),5e-9);
assert.equal(adjacentTime(500,1),500);
console.log("Timebase: boundaries, units, rounding, and limits passed.");
