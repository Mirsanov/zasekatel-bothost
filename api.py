from flask import Flask, request, jsonify
import os

app = Flask(__name__)

PORT = 8080

# Корневой эндпоинт для проверки
@app.route('/')
def home():
    return jsonify({
        'status': 'ok',
        'message': 'Test API for Max Bot SDK',
        'port': PORT
    })

# Health check
@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'test-api',
        'port': PORT
    })

# Webhook для Max Bot SDK (обязательный эндпоинт)
@app.route('/api/webhook', methods=['POST'])
def webhook():
    data = request.json
    print(f"Webhook received: {data}")
    
    # Простой ответ для Max Bot SDK
    return jsonify({
        'ok': True,
        'response': {
            'text': '✅ Бот работает! Используй /start для начала.',
            'chat_id': data.get('message', {}).get('chat_id') if data else None
        }
    })

# Тестовый API эндпоинт
@app.route('/api/test')
def test():
    return jsonify({
        'status': 'ok',
        'message': 'Test endpoint works!',
        'timestamp': __import__('datetime').datetime.now().isoformat()
    })

# Мини-приложение (заглушка)
@app.route('/miniapp/')
@app.route('/miniapp/<path:path>')
def miniapp(path='index.html'):
    return f"""
    <!DOCTYPE html>
    <html>
    <head><title>Засекатель - Тест</title></head>
    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
        <h1>⏱️ Засекатель</h1>
        <p>Тестовый API работает!</p>
        <p>Порт: {PORT}</p>
        <p><a href="/health">/health</a> | <a href="/api/test">/api/test</a></p>
    </body>
    </html>
    """

if __name__ == '__main__':
    print(f"🚀 Test API starting on port {PORT}")
    app.run(host='0.0.0.0', port=PORT)