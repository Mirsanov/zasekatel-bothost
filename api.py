from flask import Flask, jsonify

app = Flask(__name__)

@app.route('/')
def home():
    return jsonify({'status': 'ok', 'message': 'Zasekatel API running'})

@app.route('/health')
def health():
    return jsonify({'status': 'ok'})

@app.route('/api/timer')
def timer():
    return jsonify({'status': 'ok', 'timer': 'test'})

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)