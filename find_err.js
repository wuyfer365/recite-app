const fs = require('fs');
const html = fs.readFileSync('d:/code/recite-app/index.html', 'utf8');
const m = html.match(/<script>([\s\S]*?)<\/script>/);
fs.writeFileSync('_tmp.js', m[1], 'utf8');
const { execSync } = require('child_process');
try {
    execSync('node --check _tmp.js', { stdio: 'pipe' });
    console.log('OK');
} catch (e) {
    const st = e.stderr.toString();
    const ln = st.match(/_tmp\.js:(\d+):/);
    if (ln) {
        const lines = m[1].split('\n');
        const idx = parseInt(ln[1]) - 1;
        console.log('Line ' + ln[1] + ': ' + lines[idx].slice(0, 120));
    }
}
fs.unlinkSync('_tmp.js');
