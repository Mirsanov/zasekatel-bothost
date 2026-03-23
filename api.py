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

# Конфигурация
PORT = int(os.environ.get('PORT', 8080))
DATABASE = os.environ.get('DATABASE_PATH', '/data/zasekatel.db')
MOSCOW_TZ = pytz.timezone('Europe/Moscow')

def get_db():
    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id TEXT PRIMARY KEY,
            registered_at TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS timers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id TEXT,
            name TEXT,
            icon TEXT,
            interval_minutes INTEGER DEFAULT 0,
            notifications_enabled INTEGER DEFAULT 0,
            quiet_until TEXT,
            last_event TEXT,
            is_active INTEGER DEFAULT 1
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timer_id INTEGER,
            event_time TEXT,
            notes TEXT
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS link_codes (
            user_id TEXT PRIMARY KEY,
            code TEXT,
            expires_at TEXT
        )
    ''')
    
    conn.commit()
    conn.close()
    print("✅ Database initialized")

init_db()

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        'status': 'ok',
        'platform': 'bothost',
        'timestamp': datetime.now(MOSCOW_TZ).isoformat()
    })

@app.route('/api/timer', methods=['GET'])
def get_timer():
    user_id = request.args.get('user_id')
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('INSERT OR IGNORE INTO users (user_id, registered_at) VALUES (?, ?)',
                   (user_id, datetime.now(MOSCOW_TZ).isoformat()))
    
    cursor.execute('''
        SELECT * FROM timers 
        WHERE user_id = ? AND is_active = 1 
        ORDER BY id LIMIT 1
    ''', (user_id,))
    timer = cursor.fetchone()
    
    if not timer:
        cursor.execute('''
            INSERT INTO timers (user_id, name, icon, interval_minutes, notifications_enabled)
            VALUES (?, ?, ?, ?, ?)
        ''', (user_id, 'кормление', '🍼', 0, 0))
        conn.commit()
        
        cursor.execute('''
            SELECT * FROM timers 
            WHERE user_id = ? AND is_active = 1 
            ORDER BY id LIMIT 1
        ''', (user_id,))
        timer = cursor.fetchone()
    
    cursor.execute('''
        SELECT * FROM history 
        WHERE timer_id = ? 
        ORDER BY event_time DESC LIMIT 1
    ''', (timer['id'],))
    last_event = cursor.fetchone()
    
    result = {
        'id': timer['id'],
        'name': timer['name'],
        'icon': timer['icon'],
        'interval': timer['interval_minutes'],
        'notifications': bool(timer['notifications_enabled']),
        'quiet_until': timer['quiet_until'],
        'last_event': last_event['event_time'] if last_event else None
    }
    
    conn.close()
    return jsonify(result)

@app.route('/api/record', methods=['POST'])
def record_event():
    data = request.json
    user_id = data.get('user_id')
    timer_id = data.get('timer_id')
    event_time = data.get('event_time')
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    if not timer_id:
        cursor.execute('''
            SELECT id FROM timers 
            WHERE user_id = ? AND is_active = 1 
            ORDER BY id LIMIT 1
        ''', (user_id,))
        timer = cursor.fetchone()
        if timer:
            timer_id = timer['id']
    
    if not timer_id:
        conn.close()
        return jsonify({'error': 'no timer found'}), 404
    
    if event_time:
        event_dt = datetime.fromisoformat(event_time.replace('Z', '+00:00'))
    else:
        event_dt = datetime.now(MOSCOW_TZ)
    
    cursor.execute('''
        INSERT INTO history (timer_id, event_time)
        VALUES (?, ?)
    ''', (timer_id, event_dt.isoformat()))
    event_id = cursor.lastrowid
    
    cursor.execute('''
        UPDATE timers SET last_event = ? WHERE id = ?
    ''', (event_dt.isoformat(), timer_id))
    
    conn.commit()
    
    cursor.execute('''
        SELECT id, event_time, notes FROM history 
        WHERE timer_id = ? 
        ORDER BY event_time DESC LIMIT 10
    ''', (timer_id,))
    events = cursor.fetchall()
    
    conn.close()
    
    return jsonify({
        'success': True,
        'event_id': event_id,
        'event_time': event_dt.isoformat(),
        'events': [{
            'id': e['id'],
            'timestamp': e['event_time'],
            'note': e['notes']
        } for e in events]
    })

@app.route('/api/note', methods=['POST'])
def add_note():
    data = request.json
    user_id = data.get('user_id')
    note = data.get('note')
    timer_id = data.get('timer_id')
    
    if not user_id or not note:
        return jsonify({'error': 'user_id and note required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    if timer_id:
        cursor.execute('''
            SELECT id FROM history 
            WHERE timer_id = ? 
            ORDER BY event_time DESC LIMIT 1
        ''', (timer_id,))
    else:
        cursor.execute('''
            SELECT t.id FROM timers t
            WHERE t.user_id = ? AND t.is_active = 1
            LIMIT 1
        ''', (user_id,))
        timer = cursor.fetchone()
        if timer:
            cursor.execute('''
                SELECT id FROM history 
                WHERE timer_id = ? 
                ORDER BY event_time DESC LIMIT 1
            ''', (timer['id'],))
    
    event = cursor.fetchone()
    if not event:
        conn.close()
        return jsonify({'error': 'no events found'}), 404
    
    cursor.execute('''
        UPDATE history SET notes = ? WHERE id = ?
    ''', (note, event['id']))
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
    cursor = conn.cursor()
    
    cursor.execute('UPDATE history SET notes = ? WHERE id = ?', (note, event_id))
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/delete_event_by_id', methods=['POST'])
def delete_event_by_id():
    data = request.json
    event_id = data.get('event_id')
    user_id = data.get('user_id')
    
    if not event_id:
        return jsonify({'error': 'event_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM history WHERE id = ? AND timer_id IN (
            SELECT id FROM timers WHERE user_id = ?
        )
    ''', (event_id, user_id))
    
    conn.commit()
    deleted = cursor.rowcount
    conn.close()
    
    if deleted:
        return jsonify({'success': True})
    else:
        return jsonify({'error': 'event not found'}), 404

@app.route('/api/history_with_ids', methods=['GET'])
def get_history_with_ids():
    user_id = request.args.get('user_id')
    limit = request.args.get('limit', 10, type=int)
    timer_id = request.args.get('timer_id', type=int)
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    if timer_id:
        cursor.execute('''
            SELECT h.id, h.event_time, h.notes, t.name as timer_name, t.icon
            FROM history h
            JOIN timers t ON h.timer_id = t.id
            WHERE t.user_id = ? AND h.timer_id = ?
            ORDER BY h.event_time DESC LIMIT ?
        ''', (user_id, timer_id, limit))
    else:
        cursor.execute('''
            SELECT h.id, h.event_time, h.notes, t.name as timer_name, t.icon
            FROM history h
            JOIN timers t ON h.timer_id = t.id
            WHERE t.user_id = ?
            ORDER BY h.event_time DESC LIMIT ?
        ''', (user_id, limit))
    
    events = cursor.fetchall()
    conn.close()
    
    result = [{
        'id': e['id'],
        'timestamp': e['event_time'],
        'note': e['notes'],
        'timer_name': e['timer_name'],
        'timer_icon': e['icon']
    } for e in events]
    
    return jsonify({'events': result})

@app.route('/api/sync', methods=['POST', 'GET'])
def sync():
    if request.method == 'POST':
        data = request.json
        user_id = data.get('user_id')
        timers_data = data.get('timers', [])
        
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('INSERT OR IGNORE INTO users (user_id, registered_at) VALUES (?, ?)',
                       (user_id, datetime.now(MOSCOW_TZ).isoformat()))
        
        for t in timers_data:
            cursor.execute('''
                INSERT INTO timers (user_id, name, icon, interval_minutes, notifications_enabled, is_active)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (user_id, t['name'], t['icon'], t.get('interval', 0),
                  t.get('notifications', False), True))
            
            timer_id = cursor.lastrowid
            
            for e in t.get('events', []):
                cursor.execute('''
                    INSERT INTO history (timer_id, event_time, notes)
                    VALUES (?, ?, ?)
                ''', (timer_id, e['timestamp'], e.get('note')))
        
        conn.commit()
        conn.close()
        
        return jsonify({'success': True})
    
    else:
        user_id = request.args.get('user_id')
        if not user_id:
            return jsonify({'error': 'user_id required'}), 400
        
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT id, name, icon, interval_minutes, notifications_enabled, quiet_until, last_event, is_active
            FROM timers WHERE user_id = ?
        ''', (user_id,))
        timers = cursor.fetchall()
        
        result = []
        for t in timers:
            cursor.execute('''
                SELECT event_time, notes FROM history 
                WHERE timer_id = ? 
                ORDER BY event_time DESC
            ''', (t['id'],))
            events = cursor.fetchall()
            
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

@app.route('/api/interval', methods=['POST'])
def set_interval():
    data = request.json
    user_id = data.get('user_id')
    interval_minutes = data.get('interval_minutes', 0)
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE timers SET interval_minutes = ? 
        WHERE user_id = ? AND is_active = 1
    ''', (interval_minutes, user_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/notifications', methods=['POST'])
def set_notifications():
    data = request.json
    user_id = data.get('user_id')
    enabled = data.get('enabled', False)
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE timers SET notifications_enabled = ? 
        WHERE user_id = ? AND is_active = 1
    ''', (1 if enabled else 0, user_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/quiet', methods=['POST'])
def set_quiet():
    data = request.json
    user_id = data.get('user_id')
    minutes = data.get('minutes')
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    quiet_until = None
    if minutes is not None:
        quiet_until = (datetime.now(MOSCOW_TZ) + timedelta(minutes=minutes)).isoformat()
    
    cursor.execute('''
        UPDATE timers SET quiet_until = ? 
        WHERE user_id = ? AND is_active = 1
    ''', (quiet_until, user_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True, 'quiet_until': quiet_until})

@app.route('/api/reset', methods=['POST'])
def reset_timer():
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        DELETE FROM history WHERE timer_id IN (
            SELECT id FROM timers WHERE user_id = ? AND is_active = 1
        )
    ''', (user_id,))
    
    cursor.execute('''
        UPDATE timers SET last_event = NULL 
        WHERE user_id = ? AND is_active = 1
    ''', (user_id,))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/name', methods=['POST'])
def set_timer_name():
    data = request.json
    user_id = data.get('user_id')
    name = data.get('name')
    icon = data.get('icon')
    
    if not user_id or not name:
        return jsonify({'error': 'user_id and name required'}), 400
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        UPDATE timers SET name = ?, icon = ? 
        WHERE user_id = ? AND is_active = 1
    ''', (name, icon or '⏱️', user_id))
    
    conn.commit()
    conn.close()
    
    return jsonify({'success': True})

@app.route('/api/link/generate', methods=['POST'])
def generate_link_code():
    data = request.json
    user_id = data.get('user_id')
    
    if not user_id:
        return jsonify({'error': 'user_id required'}), 400
    
    code = ''.join(secrets.choice('0123456789') for _ in range(4))
    expires_at = (datetime.now(MOSCOW_TZ) + timedelta(minutes=10)).isoformat()
    
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        INSERT INTO link_codes (user_id, code, expires_at)
        VALUES (?, ?, ?)
        ON CONFLICT(user_id) DO UPDATE SET
            code = excluded.code,
            expires_at = excluded.expires_at
    ''', (user_id, code, expires_at))
    
    conn.commit()
    conn.close()
    
    return jsonify({'code': code, 'expires_at': expires_at})

@app.route('/miniapp/')
@app.route('/miniapp/<path:path>')
def serve_miniapp(path='index.html'):
    return send_from_directory('frontend', path)

if __name__ == '__main__':
    print(f"🚀 Starting Zasekatel API on port {PORT}")
    app.run(host='0.0.0.0', port=PORT)
