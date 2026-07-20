/**
 * 部署前自测 — 用 node --check 做语法检测
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const os = require('os');

const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
if (!m) { console.log('❌ 未找到 script 标签'); process.exit(1); }

const tmpFile = path.join(os.tmpdir(), 'recite_check.js');
fs.writeFileSync(tmpFile, m[1], 'utf8');

try {
    execSync(`node --check "${tmpFile}"`, { stdio: 'pipe' });
    console.log('✅ JS 语法检查通过');
    fs.unlinkSync(tmpFile);
    process.exit(0);
} catch (e) {
    const msg = e.stderr ? e.stderr.toString() : e.message;
    // Extract the relevant error line
    const lines = m[1].split('\n');
    const match = msg.match(/check_js\.js:(\d+):/);
    if (match) {
        const ln = parseInt(match[1]) - 1;
        console.log(`❌ 语法错误 行 ${match[1]}: ${lines[ln] ? lines[ln].slice(0,120) : '(空)'}`);
    } else {
        console.log(`❌ ${msg.slice(0,100)}`);
    }
    fs.unlinkSync(tmpFile);
    process.exit(1);
}
