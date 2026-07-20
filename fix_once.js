/**
 * 一次性修复所有 JS 语法错误
 * 直接运行: node fix_once.js
 * 自动: 修复→验证→部署
 */
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');

// 1. 读取 HTML
let html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');

// 2. 修复已知损坏行
const fixes = [
    // login函数中的损坏console.log
    ["            console.log('\\nconst r = await api('POST', '/login', {phone, password: pw}');\n            console.log('\\ndocument.getElementById('loginMsg').textContent = r.msg || (r.ok ? '登录成功' : '登录失败');",
     "    const r = await api('POST', '/login', {phone, password: pw});\n    document.getElementById('loginMsg').textContent = r.msg || '';"],

    // 刷新检测中的损坏行
    ["            console.log('\\nc('词总数='+snap.wordCount+' (当前'+words.length+')', words.length === snap.wordCount');",
     "            c('词总数='+snap.wordCount+' (当前'+words.length+')', words.length === snap.wordCount);"],

    ["            console.log('\\nelse console.log('%c  🎉 数据完整!','color:green');",
     "            console.log('%c  🎉 数据完整!','color:green');"],

    // 其他损坏的调试行 - 直接删除
    ["            console.log('\\n}');", ''],
    ["            console.log('\\nconsole.log('===== 遗忘曲线自测 =====');", "            console.log('===== 遗忘曲线自测 =====');"],
    ["            console.log('\\nif(!fail) console.log('🎉 通过！'); else console.log('失败:',errs');", "            if(!fail) console.log('🎉 通过！'); else console.log('失败:',errs);"],
    ["            console.log('\\nfunction sleep(ms) { return new Promise(function(r){setTimeout(r,ms);}); }');", ''],
];

for (const [oldStr, newStr] of fixes) {
    if (html.includes(oldStr)) {
        html = html.replace(oldStr, newStr);
        console.log('  ✅ 修复: ' + oldStr.slice(0, 40) + '...');
    }
}

// 3. 写回文件
fs.writeFileSync(path.join(__dirname, 'index.html'), html, 'utf8');

// 4. 验证 JS 语法
const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
const tmpFile = path.join(__dirname, '_verify.js');
fs.writeFileSync(tmpFile, scriptMatch[1], 'utf8');
try {
    execSync(`node --check "${tmpFile}"`, { stdio: 'pipe' });
    console.log('\n✅ JS 语法正确');
    fs.unlinkSync(tmpFile);
} catch (e) {
    const stderr = e.stderr.toString();
    const lineMatch = stderr.match(/_verify\.js:(\d+):/);
    if (lineMatch) {
        const lines = scriptMatch[1].split('\n');
        console.log(`❌ 仍有错误，行 ${lineMatch[1]}: ${lines[parseInt(lineMatch[1])-1].slice(0,100)}`);
    } else {
        console.log('❌ JS 语法错误');
    }
    fs.unlinkSync(tmpFile);
    process.exit(1);
}

// 5. 部署
execSync(`scp "${path.join(__dirname, 'index.html')}" root@106.53.70.121:/opt/recite-app/index.html`, { stdio: 'pipe' });
console.log('✅ 已部署到服务器');

// 6. 运行 API 测试
console.log('\n--- 运行 API 测试 ---');
try {
    execSync('node "' + path.join(__dirname, 'test-all.js') + '"', { stdio: 'inherit' });
} catch (e) {
    // test-all.js will report its own results
}
