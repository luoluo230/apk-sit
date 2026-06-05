const fs = require('fs');
const content = fs.readFileSync('C:\\Users\\Administrator\\.openclaw\\workspace\\apk-site\\codexmarkdown.txt', 'utf8');
const idx = content.indexOf('data:image/png;base64,');
const start = idx + 'data:image/png;base64,'.length;
let end = start;
// Find end - look for ) or newline, whichever comes first after sufficient base64 chars
const suffix = content.substring(start);
// Base64 only contains A-Za-z0-9+/=
const base64Chars = new Set('ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=');
let b64End = 0;
for (let i = 0; i < suffix.length; i++) {
  if (!base64Chars.has(suffix[i])) {
    b64End = i;
    break;
  }
}
if (b64End === 0) b64End = suffix.length;
const b64 = suffix.substring(0, b64End);
console.log('Base64 segment length:', b64.length);
const buf = Buffer.from(b64, 'base64');
fs.writeFileSync('E:\\web\\apk-site\\docs\\design_assets\\agent-design-original.png', buf);
console.log('Written:', buf.length, 'bytes');
