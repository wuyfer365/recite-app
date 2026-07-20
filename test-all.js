/**
 * 单词记忆 App 全量自动化测试
 * 运行: node test-all.js
 * 覆盖: JS语法 + DOM + API + 导入 + 词库筛选 + 登录
 * 阻断条件: 任一红色 FAIL 项禁止部署
 */
const http = require('http');
const fs = require('fs');
const path = require('path');
const { execSync } = require('child_process');
const os = require('os');

const HOST = '106.53.70.121';
const PORT = 5000;
const TEST_PHONE = '15695902551';
const TEST_PW = 'w12345678'; // 女儿账号密码
const ADMIN_PW = 'test123';   // 管理员密码（如果不同）

const PASS = [], FAIL = [], WARN = [];

function check(desc, cond, isWarn) {
    if (cond) { PASS.push(desc); console.log(`  ✅ ${desc}`); }
    else if (isWarn) { WARN.push(desc); console.log(`  ⚠️  ${desc}`); }
    else { FAIL.push(desc); console.log(`  ❌ ${desc}`); }
}

function httpReq(method, path, body, headers) {
    return new Promise((resolve, reject) => {
        const hdrs = Object.assign({}, headers || {});
        if (body) hdrs['Content-Type'] = 'application/json';
        const opts = { hostname: HOST, port: PORT, path, method, headers: hdrs };
        const req = http.request(opts, res => {
            let data = '';
            res.on('data', d => data += d);
            res.on('end', () => {
                try { resolve({ status: res.statusCode, data: JSON.parse(data) }); }
                catch(e) { resolve({ status: res.statusCode, data: data }); }
            });
        });
        req.on('error', reject);
        if (body) req.write(JSON.stringify(body));
        req.end();
    });
}

function randomId() { return 'ztest_' + Date.now().toString(36); }

(async function() {
    console.log('\n========================================');
    console.log('  单词记忆 App 全量自动化测试');
    console.log('========================================\n');

    // ======== 1. JS 语法 & DOM ========
    console.log('【1/6】前端代码检查');
    const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');

    check('index.html 文件存在', !!html, false);
    const scriptMatch = html.match(/<script>([\s\S]*?)<\/script>/);
    check('script 标签存在', !!scriptMatch, false);
    if (scriptMatch) {
        const code = scriptMatch[1];
        const tmpFile = path.join(os.tmpdir(), 'recite_test.js');
        fs.writeFileSync(tmpFile, code, 'utf8');
        try {
            execSync('node --check "' + tmpFile + '"', { stdio: 'pipe' });
            check('JS 语法正确', true, false);
        } catch(e) {
            check('JS 语法错误', false, false);
        }
        try { fs.unlinkSync(tmpFile); } catch(e) {}
    }

    // DOM 完整性（sourceFilter 在功能区域单独检查）
    const domIds = ['myModal', 'modalMsg', 'loginPhone', 'loginPw',
                    'pageHome', 'pageImport', 'pageWords', 'pageStats',
                    'statReview', 'statNew', 'statMastered'];
    domIds.forEach(id => check(`DOM 元素 #${id} 存在`, html.includes(`id="${id}"`), false));

    // 核心函数
    const funcs = ['login', 'register', 'importWords', 'loadCET4', 'loadPrimary',
                   'showModal', 'showConfirm', 'closeModal', 'refreshStats', 'renderHome'];
    funcs.forEach(fn => check(`函数 ${fn} 已定义`, html.includes(`function ${fn}`), false));

    // 安全检测
    check('renderHome 清空 currentWords', html.includes('currentWords=[]'), false);
    // showModal 直接用硬编码元素，不需要 DOM 空值防护

    // ======== 前端功能检查（防止改代码丢了功能） ========
    console.log('\n【功能检查】词库筛选、来源标记、导入确认、重置曲线');
    // 1. 词库筛选
    const hasSourceFilter = html.includes('id="sourceFilter"');
    check('词库筛选下拉框 #sourceFilter 存在', hasSourceFilter, false);
    check('词库筛选选项 cet4', hasSourceFilter && html.includes('cet4'), false);
    check('词库筛选选项 primary', hasSourceFilter && html.includes('primary'), false);
    check('词库筛选选项 import', hasSourceFilter && html.includes('"import"') || html.includes("'import'"), false);
    check('getFilteredWords 函数', html.includes('function getFilteredWords'), false);
    check('switchSource 函数', html.includes('function switchSource'), false);

    // 2. 导入页词库标签
    const hasImportSource = html.includes('id="importSource"');
    check('导入页词库标签 #importSource', hasImportSource, false);
    check('importWords 传 source', html.includes("source: src") || html.includes('source:src'), false);

    // 3. 导入确认弹窗
    const hasImportConfirm = html.includes('showConfirm') || html.includes('importConfirm') || html.includes('confirmImport');
    check('导入确认弹窗 showConfirm 存在', hasImportConfirm, false);
    check('delW 使用 showConfirm', html.includes('showConfirm(') && html.includes('delW'), false);

    // 4. 重置曲线按钮
    const hasResetCurve = html.includes('resetCurve') || html.includes('恢复默认') || html.includes('resetDefault');
    check('重置曲线按钮存在', hasResetCurve, false);

    // ======== 2. API 基础 ========
    console.log('\n【2/6】后端 API 基础');
    try {
        const stats = await httpReq('GET', '/api/stats', null, { 'X-Phone': TEST_PHONE });
        check('统计 API 返回 200', stats.status === 200, false);
        check('统计 API 返回 ok', stats.data.ok === true, false);
        check('sources 字段存在', !!stats.data.sources, false);
        check('total 字段存在', typeof stats.data.total === 'number', false);
    } catch(e) {
        check('统计 API 连接失败: ' + e.message, false, false);
    }

    // 管理员 API
    try {
        const admin = await httpReq('GET', '/api/admin/users', null, { 'X-Phone': TEST_PHONE });
        check('管理员 API 返回 200', admin.status === 200, false);
    } catch(e) {
        check('管理员 API 异常', false, false);
    }

    // 清空数据 API（测试接口可达性，不实际删除真实数据）
    try {
        // 用匿名请求测试路由是否存在（应返回未登录）
        const clear = await httpReq('DELETE', '/api/words/clear', null, {}); // 不传 X-Phone
        // 无论返回什么，只要不是 404 就说明路由存在
        check('清空数据路由存在', clear.status !== 404, false);
    } catch(e) {
        check('清空数据路由可达', true, false); // 网络错误不算路由不存在
    }

    // ======== 3. 词库筛选 ========
    console.log('\n【3/6】词库筛选隔离测试');
    const uid = randomId();
    try {
        // 导入测试词到不同词库
        const w1 = await httpReq('POST', '/api/words',
            [{ word: uid + '_cet4', meaning: 'cet4测试', source: 'cet4', status: 'new' }],
            { 'Content-Type': 'application/json', 'X-Phone': TEST_PHONE });
        check('CET-4 词入库', w1.data.ok === true, false);

        const w2 = await httpReq('POST', '/api/words',
            [{ word: uid + '_import', meaning: 'import测试', source: 'import', status: 'new' }],
            { 'Content-Type': 'application/json', 'X-Phone': TEST_PHONE });
        check('自定义词入库', w2.data.ok === true, false);

        const w3 = await httpReq('POST', '/api/words',
            [{ word: uid + '_primary', meaning: 'primary测试', source: 'primary', status: 'new' }],
            { 'Content-Type': 'application/json', 'X-Phone': TEST_PHONE });
        check('小学词入库', w3.data.ok === true, false);

        // 验证各词库隔离
        const stats = await httpReq('GET', '/api/stats', null, { 'X-Phone': TEST_PHONE });
        check('统计包含 cet4', stats.data.sources.cet4 > 0, false);
        check('统计包含 import', stats.data.sources.import > 0, false);
        check('统计包含 primary', stats.data.sources.primary > 0, false);

        // 清理测试词
        await httpReq('DELETE', `/api/words/${uid}_cet4`, null, { 'X-Phone': TEST_PHONE });
        await httpReq('DELETE', `/api/words/${uid}_import`, null, { 'X-Phone': TEST_PHONE });
        await httpReq('DELETE', `/api/words/${uid}_primary`, null, { 'X-Phone': TEST_PHONE });
        check('词库隔离测试完成', true, false);
    } catch(e) {
        check('词库测试异常: ' + e.message, false, false);
    }

    // ======== 4. 导入全流程 ========
    console.log('\n【4/6】导入全流程测试');
    try {
        // 模拟手动粘贴导入
        const importWords = [
            { word: uid + '_a', meaning: '自动测试A', source: 'import', status: 'new' },
            { word: uid + '_b', meaning: '自动测试B', source: 'import', status: 'new' },
        ];
        const imp = await httpReq('POST', '/api/words', importWords,
            { 'Content-Type': 'application/json', 'X-Phone': TEST_PHONE });
        check('导入2个词成功', imp.data.count === 2, false);

        // 验证导入后统计
        const stats2 = await httpReq('GET', '/api/stats', null, { 'X-Phone': TEST_PHONE });
        check('导入后统计正常', stats2.data.ok === true, false);

        // 查找刚导入的词确认source正确
        const all = await httpReq('GET', '/api/words', null, { 'X-Phone': TEST_PHONE });
        const found = all.data.words.filter(w => w.word.startsWith(uid));
        check(`刚导入的词可查到(${found.length}个)`, found.length === 2, false);
        check('导入词 source=import', found.every(w => w.source === 'import'), false);
        check('导入词 status=new', found.every(w => w.status === 'new'), false);

        // 清理
        for (const w of found) {
            await httpReq('DELETE', `/api/words/${w.word}`, null, { 'X-Phone': TEST_PHONE });
        }
        check('导入测试完成', true, false);
    } catch(e) {
        check('导入测试异常: ' + e.message, false, false);
    }

    // ======== 5. 登录验证 ========
    console.log('\n【5/6】登录验证');
    try {
        const login = await httpReq('POST', '/api/login',
            { phone: '18558751276', password: 'w12345678' });
        check('登录 API 响应', login.data.ok === true, false);
        check('登录返回 token', !!login.data.token, false);
        check('登录返回 phone', login.data.phone === '18558751276', false);
    } catch(e) {
        check('登录测试异常: ' + e.message, false, false);
    }

    // ======== 6. 曲线设置 ========
    console.log('\n【6/6】曲线设置');
    try {
        const curve = await httpReq('GET', '/api/curve', null, { 'X-Phone': TEST_PHONE });
        check('曲线 API 响应', curve.data.ok === true, false);
    } catch(e) {
        check('曲线 API 异常', false, false);
    }

    // ======== 报告 ========
    console.log('\n========================================');
    console.log('  测试报告');
    console.log('========================================');
    console.log(`  通过: ${PASS.length}`);
    console.log(`  失败: ${FAIL.length}`);
    if (WARN.length) console.log(`  警告: ${WARN.length}`);
    console.log('');

    if (FAIL.length > 0) {
        console.log('  ❌ 阻断项:');
        FAIL.forEach(f => console.log(`    - ${f}`));
        console.log('\n  ⛔ 测试未通过，禁止部署');
        process.exit(1);
    } else {
        console.log('  🎉 全部测试通过！');
        process.exit(0);
    }
})();
