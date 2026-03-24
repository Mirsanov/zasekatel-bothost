import os
import sqlite3
import json
import secrets
from datetime import datetime, timedelta
from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import pytz

app = Flask(__name__, static_folder='frontend')
CORS(app)

PORT = int(os.environ.get('PORT', 3000))
DATABASE = 'zasekatel.db'
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        registered_at TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS timers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        name TEXT,
        icon TEXT,
        interval_minutes INTEGER DEFAULT 0,
        notifications_enabled INTEGER DEFAULT 0,
        quiet_until TEXT,
        last_event TEXT,
        is_active INTEGER DEFAULT 1
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timer_id INTEGER,
        event_time TEXT,
        notes TEXT
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS link_codes (
        user_id TEXT PRIMARY KEY,
        code TEXT,
        expires_at TEXT
    )''')
    conn.commit()
    conn.close()
    print("✅ Database initialized")

init_db()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok', 'platform': 'bothost'})

@app.route('/api/timer', methods=['GET'])
def get_timer():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT OR IGNORE INTO users (user_id, registered_at) VALUES (?, ?)',
              (user_id, datetime.now(MOSCOW_TZ).isoformat()))
    c.execute('SELECT * FROM timers WHERE user_id = ? AND is_active = 1 ORDER BY id LIMIT 1', (user_id,))
    timer = c.fetchone()
    if not timer:
        c.execute('INSERT INTO timers (user_id, name, icon, interval_minutes, notifications_enabled) VALUES (?, ?, ?, ?, ?)',
                  (user_id, 'кормление', '🍼', 0, 0))
        conn.commit()
        c.execute('SELECT * FROM timers WHERE user_id = ? AND is_active = 1 ORDER BY id LIMIT 1', (user_id,))
        timer = c.fetchone()
    c.execute('SELECT * FROM history WHERE timer_id = ? ORDER BY event_time DESC LIMIT 1', (timer['id'],))
    last = c.fetchone()
    conn.close()
    return jsonify({
        'id': timer['id'],
        'name': timer['name'],
        'icon': timer['icon'],
        'interval': timer['interval_minutes'],
        'notifications': bool(timer['notifications_enabled']),
        'quiet_until': timer['quiet_until'],
        'last_event': last['event_time'] if last else None
    })

@app.route('/api/timers', methods=['GET'])
def get_timers():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT * FROM timers WHERE user_id = ? AND is_active = 1 ORDER BY id', (user_id,))
    timers = c.fetchall()
    result = []
    for t in timers:
        c.execute('SELECT COUNT(*) FROM history WHERE timer_id = ?', (t['id'],))
        count = c.fetchone()[0]
        c.execute('SELECT event_time FROM history WHERE timer_id = ? ORDER BY event_time DESC LIMIT 1', (t['id'],))
        last = c.fetchone()
        result.append({
            'id': t['id'],
            'name': t['name'],
            'icon': t['icon'],
            'interval': t['interval_minutes'],
            'notifications': bool(t['notifications_enabled']),
            'quiet_until': t['quiet_until'],
            'last_event': last['event_time'] if last else None,
            'events_count': count
        })
    conn.close()
    return jsonify({'timers': result})

@app.route('/api/timer/create', methods=['POST'])
def create_timer():
    data = request.json
    user_id = data.get('user_id')
    name = data.get('name', 'Новый режим')
    icon = data.get('icon', '⏱️')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT INTO timers (user_id, name, icon, interval_minutes, notifications_enabled) VALUES (?, ?, ?, ?, ?)',
              (user_id, name, icon, 0, 0))
    timer_id = c.lastrowid
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'timer_id': timer_id})

@app.route('/api/timer/delete', methods=['POST'])
def delete_timer():
    data = request.json
    user_id = data.get('user_id')
    timer_id = data.get('timer_id')
    if not user_id or not timer_id:
        return jsonify({'error': 'user_id and timer_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT COUNT(*) FROM timers WHERE user_id = ? AND is_active = 1', (user_id,))
    count = c.fetchone()[0]
    if count <= 1:
        conn.close()
        return jsonify({'error': 'cannot delete last timer'}), 400
    c.execute('UPDATE timers SET is_active = 0 WHERE id = ? AND user_id = ?', (timer_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/timer/rename', methods=['POST'])
def rename_timer():
    data = request.json
    user_id = data.get('user_id')
    timer_id = data.get('timer_id')
    name = data.get('name')
    icon = data.get('icon')
    if not user_id or not timer_id or not name:
        return jsonify({'error': 'user_id, timer_id and name required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE timers SET name = ?, icon = COALESCE(?, icon) WHERE id = ? AND user_id = ?',
              (name, icon, timer_id, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/record', methods=['POST'])
def record_event():
    data = request.json
    user_id = data.get('user_id')
    timer_id = data.get('timer_id')
    event_time = data.get('event_time')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    if not timer_id:
        c.execute('SELECT id FROM timers WHERE user_id = ? AND is_active = 1 ORDER BY id LIMIT 1', (user_id,))
        t = c.fetchone()
        if t:
            timer_id = t['id']
    if not timer_id:
        conn.close()
        return jsonify({'error': 'no timer found'}), 404
    event_dt = datetime.fromisoformat(event_time.replace('Z', '+00:00')) if event_time else datetime.now(MOSCOW_TZ)
    c.execute('INSERT INTO history (timer_id, event_time) VALUES (?, ?)', (timer_id, event_dt.isoformat()))
    event_id = c.lastrowid
    c.execute('UPDATE timers SET last_event = ? WHERE id = ?', (event_dt.isoformat(), timer_id))
    conn.commit()
    c.execute('SELECT id, event_time, notes FROM history WHERE timer_id = ? ORDER BY event_time DESC LIMIT 10', (timer_id,))
    events = c.fetchall()
    conn.close()
    return jsonify({
        'success': True,
        'event_id': event_id,
        'event_time': event_dt.isoformat(),
        'events': [{'id': e['id'], 'timestamp': e['event_time'], 'note': e['notes']} for e in events]
    })

@app.route('/api/history', methods=['GET'])
def get_history():
    user_id = request.args.get('user_id')
    timer_id = request.args.get('timer_id', type=int)
    limit = request.args.get('limit', 50, type=int)
    offset = request.args.get('offset', 0, type=int)
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    if timer_id:
        c.execute('''SELECT h.id, h.event_time, h.notes, t.name as timer_name, t.icon
                     FROM history h JOIN timers t ON h.timer_id = t.id
                     WHERE t.user_id = ? AND h.timer_id = ?
                     ORDER BY h.event_time DESC LIMIT ? OFFSET ?''', (user_id, timer_id, limit, offset))
        c.execute('SELECT COUNT(*) FROM history h JOIN timers t ON h.timer_id = t.id WHERE t.user_id = ? AND h.timer_id = ?', (user_id, timer_id))
    else:
        c.execute('''SELECT h.id, h.event_time, h.notes, t.name as timer_name, t.icon
                     FROM history h JOIN timers t ON h.timer_id = t.id
                     WHERE t.user_id = ?
                     ORDER BY h.event_time DESC LIMIT ? OFFSET ?''', (user_id, limit, offset))
        c.execute('SELECT COUNT(*) FROM history h JOIN timers t ON h.timer_id = t.id WHERE t.user_id = ?', (user_id,))
    events = c.fetchall()
    total = c.fetchone()[0]
    conn.close()
    return jsonify({
        'events': [{'id': e['id'], 'timestamp': e['event_time'], 'note': e['notes'], 'timer_name': e['timer_name'], 'timer_icon': e['icon']} for e in events],
        'total': total,
        'limit': limit,
        'offset': offset
    })

@app.route('/api/history_with_ids', methods=['GET'])
def get_history_with_ids():
    user_id = request.args.get('user_id')
    limit = request.args.get('limit', 10, type=int)
    timer_id = request.args.get('timer_id', type=int)
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    if timer_id:
        c.execute('''SELECT h.id, h.event_time, h.notes, t.name as timer_name, t.icon
                     FROM history h JOIN timers t ON h.timer_id = t.id
                     WHERE t.user_id = ? AND h.timer_id = ?
                     ORDER BY h.event_time DESC LIMIT ?''', (user_id, timer_id, limit))
    else:
        c.execute('''SELECT h.id, h.event_time, h.notes, t.name as timer_name, t.icon
                     FROM history h JOIN timers t ON h.timer_id = t.id
                     WHERE t.user_id = ?
                     ORDER BY h.event_time DESC LIMIT ?''', (user_id, limit))
    events = c.fetchall()
    conn.close()
    return jsonify({'events': [{'id': e['id'], 'timestamp': e['event_time'], 'note': e['notes'], 'timer_name': e['timer_name'], 'timer_icon': e['icon']} for e in events]})

@app.route('/api/delete_event_by_id', methods=['POST'])
def delete_event_by_id():
    data = request.json
    event_id = data.get('event_id')
    user_id = data.get('user_id')
    if not event_id:
        return jsonify({'error': 'event_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM history WHERE id = ? AND timer_id IN (SELECT id FROM timers WHERE user_id = ?)', (event_id, user_id))
    conn.commit()
    deleted = c.rowcount
    conn.close()
    return jsonify({'success': True}) if deleted else jsonify({'error': 'event not found'}), 404

@app.route('/api/note', methods=['POST'])
def add_note():
    data = request.json
    user_id = data.get('user_id')
    note = data.get('note')
    timer_id = data.get('timer_id')
    if not user_id or not note:
        return jsonify({'error': 'user_id and note required'}), 400
    conn = get_db()
    c = conn.cursor()
    if timer_id:
        c.execute('SELECT id FROM history WHERE timer_id = ? ORDER BY event_time DESC LIMIT 1', (timer_id,))
    else:
        c.execute('SELECT id FROM timers WHERE user_id = ? AND is_active = 1 LIMIT 1', (user_id,))
        t = c.fetchone()
        if t:
            c.execute('SELECT id FROM history WHERE timer_id = ? ORDER BY event_time DESC LIMIT 1', (t['id'],))
    event = c.fetchone()
    if not event:
        conn.close()
        return jsonify({'error': 'no events found'}), 404
    c.execute('UPDATE history SET notes = ? WHERE id = ?', (note, event['id']))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'event_id': event['id']})

@app.route('/api/update_note', methods=['POST'])
def update_note():
    data = request.json
    event_id = data.get('event_id')
    note = data.get('note')
    if not event_id:
        return jsonify({'error': 'event_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('UPDATE history SET notes = ? WHERE id = ?', (note, event_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/reset', methods=['POST'])
def reset_timer():
    data = request.json
    user_id = data.get('user_id')
    timer_id = data.get('timer_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    if timer_id:
        c.execute('DELETE FROM history WHERE timer_id = ? AND timer_id IN (SELECT id FROM timers WHERE user_id = ?)', (timer_id, user_id))
        c.execute('UPDATE timers SET last_event = NULL WHERE id = ? AND user_id = ?', (timer_id, user_id))
    else:
        c.execute('DELETE FROM history WHERE timer_id IN (SELECT id FROM timers WHERE user_id = ? AND is_active = 1)', (user_id,))
        c.execute('UPDATE timers SET last_event = NULL WHERE user_id = ? AND is_active = 1', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/reset_all', methods=['POST'])
def reset_all():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('DELETE FROM history WHERE timer_id IN (SELECT id FROM timers WHERE user_id = ?)', (user_id,))
    c.execute('DELETE FROM timers WHERE user_id = ?', (user_id,))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/interval', methods=['POST'])
def set_interval():
    data = request.json
    user_id = data.get('user_id')
    timer_id = data.get('timer_id')
    minutes = data.get('interval_minutes', 0)
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    if timer_id:
        c.execute('UPDATE timers SET interval_minutes = ? WHERE id = ? AND user_id = ?', (minutes, timer_id, user_id))
    else:
        c.execute('UPDATE timers SET interval_minutes = ? WHERE user_id = ? AND is_active = 1', (minutes, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/notifications', methods=['POST'])
def set_notifications():
    data = request.json
    user_id = data.get('user_id')
    timer_id = data.get('timer_id')
    enabled = data.get('enabled', False)
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    if timer_id:
        c.execute('UPDATE timers SET notifications_enabled = ? WHERE id = ? AND user_id = ?', (1 if enabled else 0, timer_id, user_id))
    else:
        c.execute('UPDATE timers SET notifications_enabled = ? WHERE user_id = ? AND is_active = 1', (1 if enabled else 0, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/quiet', methods=['POST'])
def set_quiet():
    data = request.json
    user_id = data.get('user_id')
    timer_id = data.get('timer_id')
    minutes = data.get('minutes')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    conn = get_db()
    c = conn.cursor()
    quiet_until = (datetime.now(MOSCOW_TZ) + timedelta(minutes=minutes)).isoformat() if minutes is not None else None
    if timer_id:
        c.execute('UPDATE timers SET quiet_until = ? WHERE id = ? AND user_id = ?', (quiet_until, timer_id, user_id))
    else:
        c.execute('UPDATE timers SET quiet_until = ? WHERE user_id = ? AND is_active = 1', (quiet_until, user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True, 'quiet_until': quiet_until})

@app.route('/api/name', methods=['POST'])
def set_timer_name():
    data = request.json
    user_id = data.get('user_id')
    timer_id = data.get('timer_id')
    name = data.get('name')
    icon = data.get('icon')
    if not user_id or not name:
        return jsonify({'error': 'user_id and name required'}), 400
    conn = get_db()
    c = conn.cursor()
    if timer_id:
        c.execute('UPDATE timers SET name = ?, icon = ? WHERE id = ? AND user_id = ?', (name, icon or '⏱️', timer_id, user_id))
    else:
        c.execute('UPDATE timers SET name = ?, icon = ? WHERE user_id = ? AND is_active = 1', (name, icon or '⏱️', user_id))
    conn.commit()
    conn.close()
    return jsonify({'success': True})

@app.route('/api/sync', methods=['POST', 'GET'])
def sync():
    if request.method == 'POST':
        data = request.json
        user_id = data.get('user_id')
        timers_data = data.get('timers', [])
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
        conn = get_db()
        c = conn.cursor()
        c.execute('INSERT OR IGNORE INTO users (user_id, registered_at) VALUES (?, ?)',
                  (user_id, datetime.now(MOSCOW_TZ).isoformat()))
        for t in timers_data:
            c.execute('''INSERT INTO timers (user_id, name, icon, interval_minutes, notifications_enabled, is_active)
                         VALUES (?, ?, ?, ?, ?, ?)''',
                      (user_id, t['name'], t['icon'], t.get('interval', 0), 1 if t.get('notifications', False) else 0, 1))
            tid = c.lastrowid
            for e in t.get('events', []):
                c.execute('INSERT INTO history (timer_id, event_time, notes) VALUES (?, ?, ?)',
                          (tid, e['timestamp'], e.get('note')))
        conn.commit()
        conn.close()
        return jsonify({'success': True})
    else:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
        conn = get_db()
        c = conn.cursor()
        c.execute('SELECT * FROM timers WHERE user_id = ?', (user_id,))
        timers = c.fetchall()
        result = []
        for t in timers:
            c.execute('SELECT event_time, notes FROM history WHERE timer_id = ? ORDER BY event_time DESC', (t['id'],))
            events = c.fetchall()
            result.append({
                'id': t['id'],
                'name': t['name'],
                'icon': t['icon'],
                'interval': t['interval_minutes'],
                'notifications': bool(t['notifications_enabled']),
                'quiet_until': t['quiet_until'],
                'last_event': t['last_event'],
                'events': [{'timestamp': e['event_time'], 'note': e['notes']} for e in events]
            })
        conn.close()
        return jsonify({'timers': result})

@app.route('/api/link/generate', methods=['POST'])
def generate_link_code():
    data = request.json
    user_id = data.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    code = ''.join(secrets.choice('0123456789') for _ in range(4))
    expires_at = (datetime.now(MOSCOW_TZ) + timedelta(minutes=10)).isoformat()
    conn = get_db()
    c = conn.cursor()
    c.execute('INSERT OR REPLACE INTO link_codes (user_id, code, expires_at) VALUES (?, ?, ?)', (user_id, code, expires_at))
    conn.commit()
    conn.close()
    return jsonify({'code': code, 'expires_at': expires_at})

@app.route('/api/link/verify', methods=['POST'])
def verify_link_code():
    data = request.json
    code = data.get('code')
    if not code:
        return jsonify({'error': 'code required'}), 400
    conn = get_db()
    c = conn.cursor()
    c.execute('SELECT user_id FROM link_codes WHERE code = ? AND expires_at > ?', (code, datetime.now(MOSCOW_TZ).isoformat()))
    result = c.fetchone()
    conn.close()
    if result:
        return jsonify({'success': True, 'user_id': result['user_id']})
    else:
        return jsonify({'error': 'invalid or expired code'}), 404

@app.route('/miniapp/')
@app.route('/miniapp/<path:path>')
def serve_miniapp(path='index.html'):
    return send_from_directory('frontend', path)

if __name__ == '__main__':
    print(f"🚀 Starting Zasekatel API on port {PORT}")
    app.run(host='0.0.0.0', port=PORT)