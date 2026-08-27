const raw = require('fs').readFileSync(0, 'utf8');
const lines = raw.replace(/\r\n/g, '\n').split('\n');

const n = parseInt(lines[0].trim(), 10);
const words = lines[1].trim().split(/\s+/).slice(0, n);
const k = parseInt(lines[2].trim(), 10);

const seen = new Set();
for (const word of words) {
  seen.add(word);
}

const reached = seen.size;
console.log(reached === 0 ? 'NONE' : String(reached));
