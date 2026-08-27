const raw = require('fs').readFileSync(0, 'utf8');
const lines = raw.replace(/\r\n/g, '\n').split('\n');

const n = parseInt(lines[0].trim(), 10);
const words = lines[1].trim().split(/\s+/).slice(0, n);
const k = parseInt(lines[2].trim(), 10);

const counts = new Map();
for (const word of words) {
  counts.set(word, (counts.get(word) || 0) + 1);
}

let reached = 0;
for (const times of counts.values()) {
  if (times >= k) {
    reached += 1;
  }
}

console.log(String(reached));
