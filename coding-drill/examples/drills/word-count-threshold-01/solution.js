const raw = require('fs').readFileSync(0, 'utf8');
const lines = raw.replace(/\r\n/g, '\n').split('\n');

const n = parseInt(lines[0].trim(), 10);
const words = lines[1].trim().split(/\s+/).slice(0, n);
const k = parseInt(lines[2].trim(), 10);

// TODO: 数出「出现次数达到 k 次」的不同单词有多少个；
//       一个都没有时输出 NONE。下面这行是占位，请替换掉。
console.log(-1);
