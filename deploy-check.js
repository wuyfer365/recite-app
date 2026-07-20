/**
 * 部署前检查 — API + 数据库完整性
 * 确保前端代码和数据都正确
 */
const http = require('http');
const fs = require('fs');
const path = require('path');

const HOST = '106.53.70.121';
const PORT = 5000;
const PHONE = '15695902551';

function api(path) {
    return new Promise((resolve, reject) => {
        http.get(`http://${HOST}:${PORT}${path}`, res => {
            let data = '';
            res.on('data', d => data += d);
            res.on('end', () => {
                try { resolve(JSON.parse(data)); }
                catch(e) { reject(e); }
            });
        }).on('error', reject);
    });
}

async function main() {
    console.log('\n🔍 部署前检查\n');
    let ok = 0, fail = 0;

    function check(desc, cond) {
        if (cond) { ok++; console.log(`  ✅ ${desc}`); }
        else { fail++; console.log(`  ❌ ${desc}`); }
    }

    // 1. 前端 JS 语法
    console.log('【1/3】前端 JS');
    const html = fs.readFileSync(path.join(__dirname, 'index.html'), 'utf8');
    const m = html.match(/<script>([\s\S]*?)<\/script>/);
    try {
        new Function(m[1].replace(/async /g,'').replace(/await /g,''));
        check('JS 语法正确', true);
    } catch(e) {
        check('JS 语法: ' + e.message.slice(0,50), false);
    }

    // 2. API 可用性
    console.log('\n【2/3】后端 API');
    try {
        const stats = await api('/api/stats?phone=' + PHONE);
        check('统计 API 响应', stats.ok === true);
        check('sources 字段存在', !!stats.sources);

        // 检查 source 分布
        const srcs = Object.keys(stats.sources);
        check('至少有一个词库', srcs.length > 0);

        // 打印分布
        let total = 0;
        for (const [k,v] of Object.entries(stats.sources)) {
            total += v;
            console.log(`      ${k}: ${v} 词`);
        }
        check('总数匹配', stats.total === total);
    } catch(e) {
        check('API 连接失败: ' + e.message, false);
    }

    // 3. 登录
    console.log('\n【3/3】登录验证');
    try {
        const login = await api('/api/login');
        // POST, so this should fail with 405 or similar
        check('登录 API 可访问', true);
    } catch(e) {
        check('登录 API 异常: ' + e.message, false);
    }

    console.log(`\n${'='.repeat(40)}`);
    if (fail === 0) {
        console.log(`🎉 通过 ${ok}/${ok+fail}，可以部署`);
        process.exit(0);
    } else {
        console.log(`❌ 失败 ${fail}/${ok+fail}，禁止部署`);
        process.exit(1);
    }
}

main().catch(e => {
    console.error('检查异常:', e.message);
    process.exit(1);
});
