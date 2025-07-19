import paho.mqtt.client as mqtt
import random
import time
import threading
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import logging

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = '2AHJXumAL6LljeqHZsJM_2GNrZduTwyMZexMaFNzyHo'  # Required for SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MQTT setup
broker = "iot-dashboard.cloud.shiftr.io"
port = 1883
username = "iot-dashboard"
password = "YBxsZiVmkHljoCId"
client_id = f"iot-gui-08122004-{random.randint(0, 1000)}"
client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)

# Mock data simulation control
is_simulating = False
simulation_event = threading.Event()
simulation_thread = None

# MQTT callbacks
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        logging.info("Connected to MQTT Broker!")
        client.subscribe("home/sensors/temperature", qos=1)
        client.subscribe("home/sensors/humidity", qos=1)
        client.subscribe("home/sensors/light", qos=1)
        client.subscribe("home/control/light", qos=1)
        client.subscribe("home/control/fan", qos=1)
        client.subscribe("home/control/motor", qos=1)
    else:
        logging.error(f"Failed to connect, return code {reason_code}")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    logging.info(f"Received {payload} from {topic}")

    message = {}
    try:
        if topic == "home/sensors/temperature":
            message['sensors'] = {'temperature': float(payload)}
        elif topic == "home/sensors/humidity":
            message['sensors'] = {'humidity': float(payload)}
        elif topic == "home/sensors/light":
            message['sensors'] = {'light': float(payload)}
        elif topic == "home/control/light":
            status = payload.upper()
            message['devices'] = {'led_status': status}
        elif topic == "home/control/fan":
            status = payload.upper()
            message['devices'] = {'fan_status': status}
        elif topic == "home/control/motor":
            status = payload.capitalize()
            message['devices'] = {'motor_status': status}

        if message:
            socketio.emit('update', message)
    except Exception as e:
        logging.error(f"Error processing message from {topic}: {e}")

# Simulate sensor data
def simulate_sensors():
    while simulation_event.is_set():
        temp = round(random.uniform(20.0, 30.0), 2)
        humidity = round(random.uniform(40.0, 80.0), 2)
        light = round(random.uniform(100, 1000), 2)
        
        try:
            client.publish("home/sensors/temperature", str(temp), qos=1)
            client.publish("home/sensors/humidity", str(humidity), qos=1)
            client.publish("home/sensors/light", str(light), qos=1)
            logging.info(f"Published sensor data: T={temp}, H={humidity}, L={light}")
            socketio.emit('notification', {'notification': 'New sensor data generated'})
        except Exception as e:
            logging.error(f"Error publishing sensor data: {e}")
        time.sleep(2)

# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/control', methods=['POST'])
def control():
    data = request.get_json()
    topic = data.get('topic')
    command = data.get('command')
    valid_commands = {
        'home/control/light': ['ON', 'OFF'],
        'home/control/fan': ['ON', 'OFF'],
        'home/control/motor': ['FORWARD', 'BACKWARD', 'STOP']
    }
    if topic in valid_commands and command in valid_commands[topic]:
        try:
            client.publish(topic, command, qos=1)
            logging.info(f"Published control command: {command} to {topic}")
            return jsonify({"status": "success"})
        except Exception as e:
            logging.error(f"Error publishing control command: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "error", "message": "Invalid command or topic"}), 400

@app.route('/toggle_mock_data', methods=['POST'])
def toggle_mock_data():
    global is_simulating, simulation_thread
    try:
        if is_simulating:
            simulation_event.clear()
            is_simulating = False
            socketio.emit('mock_data_status', {'is_running': False})
            logging.info("Mock data simulation stopped")
            return jsonify({"status": "success", "is_running": False})
        else:
            simulation_event.set()
            simulation_thread = threading.Thread(target=simulate_sensors, daemon=True)
            simulation_thread.start()
            is_simulating = True
            socketio.emit('mock_data_status', {'is_running': True})
            logging.info("Mock data simulation started")
            return jsonify({"status": "success", "is_running": True})
    except Exception as e:
        logging.error(f"Error toggling mock data: {e}")
        return jsonify({"status": "error", "message": str(e)}), 500

# SocketIO event handlers
@socketio.on('connect')
def handle_connect():
    logging.info("SocketIO client connected")
    emit('notification', {'notification': 'WebSocket connected'})
    emit('mock_data_status', {'is_running': is_simulating})

@socketio.on('disconnect')
def handle_disconnect():
    logging.info("SocketIO client disconnected")

# Start MQTT client
client.on_connect = on_connect
client.on_message = on_message
client.username_pw_set(username, password)
try:
    client.connect(broker, port, 60)
    client.loop_start()
    logging.info("MQTT client started")
except Exception as e:
    logging.error(f"MQTT connection failed: {e}")

# Run Flask app
if __name__ == '__main__':
    logging.info("Starting Flask server on http://127.0.0.1:5001")
    socketio.run(app, host='0.0.0.0', port=5001, debug=False)