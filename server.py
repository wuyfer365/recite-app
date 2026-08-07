#!/usr/bin/env python3
"""单词记忆 H5 后端 — Flask + SQLite"""
import sqlite3, hashlib, secrets, json, os, re
from pathlib import Path
from flask import Flask, request, jsonify, g

app = Flask(__name__, static_folder='.', static_url_path='')
DB = Path(__file__).parent / 'recite.db'

# ============ 数据库 ============
def get_db():
    if 'db' not in g:
        g.db = sqlite3.connect(str(DB))
        g.db.row_factory = sqlite3.Row
        g.db.execute('''CREATE TABLE IF NOT EXISTS users (
            phone TEXT PRIMARY KEY, pw TEXT, is_admin INTEGER DEFAULT 0, curve TEXT,
            daily_limit INTEGER DEFAULT 100, mode TEXT DEFAULT 'mix', review_deduct INTEGER DEFAULT 0,
            today_date TEXT DEFAULT '', today_studied INTEGER DEFAULT 0, today_reviewed INTEGER DEFAULT 0)''')
        # 老库迁移：补缺失列
        cols = {r[1] for r in g.db.execute('PRAGMA table_info(users)')}
        for col, ddl in [
            ('daily_limit', 'ALTER TABLE users ADD COLUMN daily_limit INTEGER DEFAULT 100'),
            ('mode', "ALTER TABLE users ADD COLUMN mode TEXT DEFAULT 'mix'"),
            ('review_deduct', 'ALTER TABLE users ADD COLUMN review_deduct INTEGER DEFAULT 0'),
            ('today_date', "ALTER TABLE users ADD COLUMN today_date TEXT DEFAULT ''"),
            ('today_studied', 'ALTER TABLE users ADD COLUMN today_studied INTEGER DEFAULT 0'),
            ('today_reviewed', 'ALTER TABLE users ADD COLUMN today_reviewed INTEGER DEFAULT 0'),
        ]:
            if col not in cols:
                g.db.execute(ddl)
        g.db.execute('''CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT, word TEXT, meaning TEXT, phonetic TEXT,
            example TEXT, example_cn TEXT, stage INTEGER DEFAULT 0,
            next_time REAL, last_time REAL, status TEXT DEFAULT 'new',
            fail_count INTEGER DEFAULT 0,
            hard_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'import',
            UNIQUE(phone, word))''')
        # 迁移：words 补 hard_count（点模糊/忘记都累计的难词次数）
        wcols = {r[1] for r in g.db.execute('PRAGMA table_info(words)')}
        if 'hard_count' not in wcols:
            g.db.execute('ALTER TABLE words ADD COLUMN hard_count INTEGER DEFAULT 0')
        g.db.commit()
    return g.db

@app.teardown_appcontext
def close_db(exception):
    if 'db' in g: g.db.close()

# ============ 工具 ============
def hash_pw(pw):
    return hashlib.sha256((pw + 'recite_salt').encode()).hexdigest()

def make_token(phone):
    raw = f'{phone}:{secrets.token_hex(16)}'
    return hashlib.sha256(raw.encode()).hexdigest()

# ============ API ============

@app.route('/')
def index():
    resp = app.send_static_file('index.html')
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    resp.headers['Pragma'] = 'no-cache'
    resp.headers['Expires'] = '0'
    return resp

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    phone, pw = data.get('phone',''), data.get('password','')
    if not phone.isdigit() or len(phone) != 11: return jsonify({'ok':False,'msg':'手机号需11位数字'})
    if len(pw) < 8: return jsonify({'ok':False,'msg':'密码至少8位'})
    if not re.search(r'[a-zA-Z]', pw) or not re.search(r'[0-9]', pw): return jsonify({'ok':False,'msg':'密码需包含字母和数字'})
    db = get_db()
    try:
        is_admin = 1 if phone == '15695902551' else 0
        db.execute('INSERT INTO users (phone, pw, is_admin) VALUES (?,?,?)', (phone, hash_pw(pw), is_admin))
        db.commit()
        return jsonify({'ok':True, 'token': make_token(phone), 'phone': phone, 'is_admin': bool(is_admin)})
    except sqlite3.IntegrityError:
        return jsonify({'ok':False,'msg':'该手机号已注册'})

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    phone, pw = data.get('phone',''), data.get('password','')
    db = get_db()
    row = db.execute('SELECT pw, is_admin FROM users WHERE phone=?', (phone,)).fetchone()
    if not row: return jsonify({'ok':False,'msg':'账号不存在'})
    if row['pw'] != hash_pw(pw): return jsonify({'ok':False,'msg':'密码错误'})
    return jsonify({'ok':True, 'token': make_token(phone), 'phone': phone, 'is_admin': bool(row['is_admin'])})

@app.route('/api/me', methods=['GET'])
def get_me():
    """当前用户信息（含每日设置与今日进度）"""
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    row = db.execute('SELECT phone, is_admin, daily_limit, mode, review_deduct, today_date, today_studied, today_reviewed FROM users WHERE phone=?', (phone,)).fetchone()
    if not row: return jsonify({'ok':False,'msg':'用户不存在'})
    return jsonify({'ok':True, 'phone': row['phone'], 'is_admin': bool(row['is_admin']),
        'daily_limit': row['daily_limit'] or 100, 'mode': row['mode'] or 'mix',
        'review_deduct': bool(row['review_deduct']), 'today_date': row['today_date'] or '',
        'today_studied': row['today_studied'] or 0, 'today_reviewed': row['today_reviewed'] or 0})

@app.route('/api/settings', methods=['PUT'])
def save_settings():
    """保存每日设置与今日进度（账号绑定）"""
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    data = request.json or {}
    db = get_db()
    db.execute('''UPDATE users SET daily_limit=?, mode=?, review_deduct=?, today_date=?, today_studied=?, today_reviewed=? WHERE phone=?''',
        (int(data.get('daily_limit',100) or 100), data.get('mode','mix') or 'mix',
         1 if data.get('review_deduct') else 0,
         data.get('today_date','') or '', int(data.get('today_studied',0) or 0), int(data.get('today_reviewed',0) or 0), phone))
    db.commit()
    return jsonify({'ok':True})

@app.route('/api/words', methods=['GET','POST','PUT'])
def words():
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()

    if request.method == 'GET':
        rows = db.execute('SELECT * FROM words WHERE phone=?', (phone,)).fetchall()
        return jsonify({'ok':True, 'words': [dict(r) for r in rows]})

    if request.method == 'POST':
        data = request.json  # list of words
        count = 0
        for w in (data if isinstance(data, list) else [data]):
            db.execute('''INSERT OR REPLACE INTO words
                (phone, word, meaning, phonetic, example, example_cn, stage, next_time, last_time, status, fail_count, source)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?)''',
                (phone, w['word'], w.get('meaning',''), w.get('phonetic',''),
                 w.get('example',''), w.get('example_cn',''),
                 w.get('stage',0), w.get('next_time'), w.get('last_time'),
                 w.get('status','new'), w.get('fail_count',0),
                 w.get('source','import')))
            count += 1
        db.commit()
        return jsonify({'ok':True, 'count': count})

    if request.method == 'PUT':
        w = request.json
        db.execute('''UPDATE words SET stage=?, next_time=?, last_time=?, status=?, fail_count=?, hard_count=? WHERE phone=? AND word=?''',
            (w['stage'], w.get('next_time'), w.get('last_time'), w['status'],
             w.get('fail_count',0), w.get('hard_count',0), phone, w['word']))
        db.commit()
        return jsonify({'ok':True})

@app.route('/api/words/hard', methods=['GET'])
def hard_words():
    """难词列表：点过模糊/忘记的单词，按难词次数排序"""
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    # 难词阈值：点满 5 次模糊/记不住自动进难词本
    rows = db.execute('''SELECT word, meaning, hard_count, fail_count, stage FROM words
        WHERE phone=? AND hard_count >= 5
        ORDER BY hard_count DESC, word LIMIT 50''', (phone,)).fetchall()
    return jsonify({'ok':True, 'words': [dict(r) for r in rows]})

@app.route('/api/story', methods=['POST'])
def gen_story():
    """用难词生成新概念二风格双语小故事"""
    import urllib.request
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    data = request.json or {}
    words = data.get('words') or []
    if not words:
        db = get_db()
        rows = db.execute('''SELECT word, meaning FROM words
            WHERE phone=? AND hard_count >= 5
            ORDER BY hard_count DESC, word LIMIT 20''', (phone,)).fetchall()
        words = [dict(r) for r in rows]
    if not words:
        return jsonify({'ok':False,'msg':'还没有难词，同一个单词点满5次「模糊」或「忘记」会自动收集'})
    wordlist = '\n'.join(f'- {w["word"]}: {w.get("meaning","")}' for w in words)
    prompt = (f'''请用下面这些英语单词写一篇类似《新概念英语第二册》的英语小故事（8-15句话，日常情景，语言简单地道），
尽量自然地把这些词都用上。然后给出全文中文翻译。
输出格式（严格）：
【英语原文】
（英语故事）
【中文翻译】
（中文翻译）
【单词注释】
（每个难词的音标+中文，一行一个）

需要使用的单词：
{wordlist}''')
    payload = json.dumps({
        'model': 'deepseek-chat',
        'messages': [
            {'role': 'system', 'content': '你是新概念英语风格的英语故事作者，擅长用指定单词写简洁地道的双语小故事。'},
            {'role': 'user', 'content': prompt},
        ],
        'stream': False,
    }).encode('utf-8')
    req = urllib.request.Request(
        'https://api.deepseek.com/chat/completions',
        data=payload,
        headers={
            'Content-Type': 'application/json',
            'Authorization': 'Bearer sk-5a07e5fd73644403b044fe60b19d1006',
        })
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            result = json.loads(resp.read().decode('utf-8'))
        reply = result['choices'][0]['message']['content'].strip()
        return jsonify({'ok': True, 'story': reply})
    except Exception as e:
        return jsonify({'ok': False, 'msg': f'故事生成失败: {e}'})

@app.route('/api/words/clear', methods=['DELETE'])
def clear_words():
    """清空当前用户所有单词数据（必须在 /api/words/<word> 之前定义）"""
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    db.execute('DELETE FROM words WHERE phone=?', (phone,))
    db.commit()
    return jsonify({'ok':True, 'msg':'已清空'})

@app.route('/api/admin/clear-user', methods=['DELETE'])
def admin_clear_user():
    """管理员清空指定用户的单词数据"""
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    admin = db.execute('SELECT is_admin FROM users WHERE phone=?', (phone,)).fetchone()
    if not admin or not admin['is_admin']: return jsonify({'ok':False,'msg':'无权限'})
    target = request.args.get('phone', '')
    if not target: return jsonify({'ok':False,'msg':'参数不全'})
    db.execute('DELETE FROM words WHERE phone=?', (target,))
    db.commit()
    return jsonify({'ok':True, 'msg':f'已清空 {target} 的单词数据'})

@app.route('/api/words/source/<source_name>', methods=['DELETE'])
def delete_words_by_source(source_name):
    """按词库清空单词"""
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    db.execute('DELETE FROM words WHERE phone=? AND source=?', (phone, source_name))
    db.commit()
    return jsonify({'ok':True, 'msg':'已清空词库 '+source_name})

@app.route('/api/words/<word>', methods=['DELETE'])
def delete_word(word):
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    db.execute('DELETE FROM words WHERE phone=? AND word=?', (phone, word))
    db.commit()
    return jsonify({'ok':True})

# ============ 词库统计 ============

@app.route('/api/stats', methods=['GET'])
def word_stats():
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    rows = db.execute('SELECT source, COUNT(*) as cnt FROM words WHERE phone=? GROUP BY source', (phone,)).fetchall()
    total = db.execute('SELECT COUNT(*) as cnt FROM words WHERE phone=?', (phone,)).fetchone()['cnt']
    return jsonify({'ok':True, 'total': total, 'sources': {r['source']:r['cnt'] for r in rows}})

# ============ 遗忘曲线设置 ============

@app.route('/api/curve', methods=['GET', 'PUT'])
def curve():
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    if request.method == 'GET':
        row = db.execute('SELECT curve FROM users WHERE phone=?', (phone,)).fetchone()
        curve_data = json.loads(row['curve']) if row and row['curve'] else None
        return jsonify({'ok':True, 'curve': curve_data})
    # PUT
    data = request.json
    if not data or not isinstance(data, list) or len(data) != 5:
        return jsonify({'ok':False,'msg':'数据格式错误'})
    db.execute('UPDATE users SET curve=? WHERE phone=?', (json.dumps(data, ensure_ascii=False), phone))
    db.commit()
    return jsonify({'ok':True})

# ============ 管理员 ============

@app.route('/api/admin/users', methods=['GET'])
def admin_users():
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    admin = db.execute('SELECT is_admin FROM users WHERE phone=?', (phone,)).fetchone()
    if not admin or not admin['is_admin']: return jsonify({'ok':False,'msg':'无权限'})
    rows = db.execute('''SELECT u.phone, u.is_admin,
        COUNT(w.id) as total,
        SUM(CASE WHEN w.status='mastered' THEN 1 ELSE 0 END) as mastered
        FROM users u LEFT JOIN words w ON u.phone=w.phone
        GROUP BY u.phone ORDER BY mastered DESC, total DESC''').fetchall()
    result = [{'phone': r['phone'], 'is_admin': bool(r['is_admin']),
               'word_count': r['total'], 'mastered': r['mastered']} for r in rows]
    return jsonify({'ok':True, 'users': result})

@app.route('/api/admin/reset-password', methods=['POST'])
def admin_reset_password():
    """管理员重置用户密码"""
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    admin = db.execute('SELECT is_admin FROM users WHERE phone=?', (phone,)).fetchone()
    if not admin or not admin['is_admin']: return jsonify({'ok':False,'msg':'无权限'})
    data = request.json
    target = data.get('phone','')
    new_pw = data.get('password','')
    if not target or not new_pw: return jsonify({'ok':False,'msg':'参数不全'})
    if len(new_pw) < 8: return jsonify({'ok':False,'msg':'密码至少8位'})
    if not re.search(r'[a-zA-Z]', new_pw) or not re.search(r'[0-9]', new_pw):
        return jsonify({'ok':False,'msg':'密码需包含字母和数字'})
    db.execute('UPDATE users SET pw=? WHERE phone=?', (hash_pw(new_pw), target))
    db.commit()
    return jsonify({'ok':True, 'msg':f'已重置{target}的密码'})

# ============ 公共 ============

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    """公开排行榜（所有用户可见）"""
    db = get_db()
    rows = db.execute('''SELECT u.phone,
        COUNT(w.id) as total,
        SUM(CASE WHEN w.status='mastered' THEN 1 ELSE 0 END) as mastered
        FROM users u LEFT JOIN words w ON u.phone=w.phone
        GROUP BY u.phone ORDER BY mastered DESC, total DESC''').fetchall()
    result = [{'phone': r['phone'], 'word_count': r['total'], 'mastered': r['mastered']} for r in rows]
    return jsonify({'ok':True, 'users': result})

@app.route('/api/change-password', methods=['POST'])
def change_password():
    """用户自行修改密码"""
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    data = request.json
    old_pw = data.get('old_password','')
    new_pw = data.get('new_password','')
    if not old_pw or not new_pw: return jsonify({'ok':False,'msg':'参数不全'})
    db = get_db()
    row = db.execute('SELECT pw FROM users WHERE phone=?', (phone,)).fetchone()
    if not row: return jsonify({'ok':False,'msg':'用户不存在'})
    if row['pw'] != hash_pw(old_pw): return jsonify({'ok':False,'msg':'旧密码错误'})
    if len(new_pw) < 8: return jsonify({'ok':False,'msg':'密码至少8位'})
    if not re.search(r'[a-zA-Z]', new_pw) or not re.search(r'[0-9]', new_pw):
        return jsonify({'ok':False,'msg':'密码需包含字母和数字'})
    db.execute('UPDATE users SET pw=? WHERE phone=?', (hash_pw(new_pw), phone))
    db.commit()
    return jsonify({'ok':True, 'msg':'密码已修改'})

if __name__ == '__main__':
    print(f'启动: http://localhost:5000')
    app.run(host='0.0.0.0', port=5000, debug=True)
