from flask import Flask, request, jsonify
import os

app = Flask(__name__)

PORT = 5384

@app.route('/')
def home():
    return jsonify({
        'status': 'ok',
        'message': 'Zasekatel test API',
        'port': PORT,
        'host': request.host
    })

@app.route('/health')
def health():
    return jsonify({
        'status': 'ok',
        'service': 'test-api',
        'port': PORT
    })

@app.route('/api/webhook', methods=['POST'])
def webhook():
    data = request.json
    print(f"Webhook: {data}")
    return jsonify({
        'ok': True,
        'response': {
            'text': '✅ Бот работает!',
            'chat_id': data.get('message', {}).get('chat_id') if data else None
        }
    })

@app.route('/api/test')
def test():
    return jsonify({
        'status': 'ok',
        'message': 'Test endpoint works',
        'timestamp': __import__('datetime').datetime.now().isoformat()
    })

@app.route('/miniapp/')
def miniapp():
    return """
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <script src="https://telegram.org/js/telegram-web-app.js?56"></script>
        <title>Засекатель - Тест</title>
        <style>
            body {
                font-family: sans-serif;
                text-align: center;
                padding: 50px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                margin: 0;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .card {
                background: white;
                border-radius: 40px;
                padding: 40px;
                max-width: 500px;
                box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            }
            h1 { font-size: 32px; margin-bottom: 20px; }
            .status { margin: 20px 0; padding: 15px; background: #f0f0f0; border-radius: 30px; }
            a { color: #667eea; text-decoration: none; margin: 0 10px; }
            .btn {
                display: inline-block;
                background: #48bb78;
                color: white;
                padding: 12px 24px;
                border-radius: 40px;
                text-decoration: none;
                margin-top: 20px;
            }
            .api-url {
                background: #f5f5f5;
                padding: 10px;
                border-radius: 20px;
                font-family: monospace;
                font-size: 12px;
                word-break: break-all;
                margin-top: 15px;
            }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>⏱️ Засекатель</h1>
            <p>Тестовый API работает на порту 5384</p>
            <div class="status">
                <strong>Статус:</strong> <span id="status">Проверка...</span>
            </div>
            <div class="api-url" id="api-url"></div>
            <p>
                <a href="/health">/health</a> | 
                <a href="/api/test">/api/test</a>
            </p>
            <a href="/health" class="btn">Проверить API</a>
        </div>
        <script>
            const API_BASE = window.location.origin + '/api';
            document.getElementById('api-url').innerHTML = 'API: ' + API_BASE;
            
            fetch('/health')
                .then(r => r.json())
                .then(data => {
                    document.getElementById('status').innerHTML = '✅ API работает! Порт: ' + data.port;
                })
                .catch(e => {
                    document.getElementById('status').innerHTML = '❌ Ошибка подключения: ' + e.message;
                });
        </script>
    </body>
    </html>
    """

if __name__ == '__main__':
    print(f"🚀 Test API starting on port {PORT}")
    app.run(host='0.0.0.0', port=PORT)