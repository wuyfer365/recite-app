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
        g.db.execute('CREATE TABLE IF NOT EXISTS users (phone TEXT PRIMARY KEY, pw TEXT, is_admin INTEGER DEFAULT 0, curve TEXT)')
        g.db.execute('''CREATE TABLE IF NOT EXISTS words (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            phone TEXT, word TEXT, meaning TEXT, phonetic TEXT,
            example TEXT, example_cn TEXT, stage INTEGER DEFAULT 0,
            next_time REAL, last_time REAL, status TEXT DEFAULT 'new',
            fail_count INTEGER DEFAULT 0,
            source TEXT DEFAULT 'import',
            UNIQUE(phone, word))''')
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
    return app.send_static_file('index.html')

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
            db.execute('''INSERT OR IGNORE INTO words
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
        db.execute('''UPDATE words SET stage=?, next_time=?, last_time=?, status=?, fail_count=? WHERE phone=? AND word=?''',
            (w['stage'], w.get('next_time'), w.get('last_time'), w['status'], w.get('fail_count',0), phone, w['word']))
        db.commit()
        return jsonify({'ok':True})

@app.route('/api/words/clear', methods=['DELETE'])
def clear_words():
    """清空当前用户所有单词数据（必须在 /api/words/<word> 之前定义）"""
    phone = request.headers.get('X-Phone','')
    if not phone: return jsonify({'ok':False,'msg':'未登录'})
    db = get_db()
    db.execute('DELETE FROM words WHERE phone=?', (phone,))
    db.commit()
    return jsonify({'ok':True, 'msg':'已清空'})

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

if __name__ == '__main__':
    print(f'启动: http://localhost:5000')
    app.run(host='0.0.0.0', port=5000, debug=True)
