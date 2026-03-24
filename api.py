from flask import Flask, request, jsonify
import os

app = Flask(__name__)

PORT = 9000

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
    <head><title>Засекатель - Тест</title></head>
    <body style="font-family: sans-serif; text-align: center; padding: 50px;">
        <h1>⏱️ Засекатель</h1>
        <p>Тестовый API работает на порту 9000</p>
        <p><a href="/health">/health</a> | <a href="/api/test">/api/test</a></p>
    </body>
    </html>
    """

if __name__ == '__main__':
    print(f"🚀 Test API starting on port {PORT}")
    app.run(host='0.0.0.0', port=PORT)