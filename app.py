import paho.mqtt.client as mqtt
import random
import time
import threading
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit
import json
import logging
import sqlite3
from datetime import datetime

# Flask app setup
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'  # Required for SocketIO
socketio = SocketIO(app, cors_allowed_origins="*")

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MQTT setup
broker = "iot-dashboard.cloud.shiftr.io"
port = 1883
username = "iot-dashboard"
password = "YBxsZiVmkHljoCId"
client_id = f"iot-gui-08122004-{random.randint(0, 1000)}"  # Unique client ID
client = mqtt.Client(client_id=client_id, protocol=mqtt.MQTTv311)  # Explicitly use MQTTv3.1.1

# Database connection
def get_db_connection():
    conn = sqlite3.connect(r'D:\IoT_ITCSIU22194_Midterm\iot_data.db', timeout=20)
    conn.row_factory = sqlite3.Row
    return conn

# Database query functions
def get_latest_sensor_data():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT humidity, temperature FROM temperature_humidity_data ORDER BY id DESC LIMIT 1")
        temp_hum = cursor.fetchone()
        cursor.execute("SELECT light_level FROM light_sensor_data ORDER BY id DESC LIMIT 1")
        light = cursor.fetchone()
        conn.close()
        return {
            'humidity': temp_hum['humidity'] if temp_hum else None,
            'temperature': temp_hum['temperature'] if temp_hum else None,
            'light': light['light_level'] if light else None
        }
    except Exception as e:
        logging.error(f"Error fetching sensor data: {e}")
        return None

def get_latest_device_statuses():
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM relay_lights_status WHERE device_id = 1 ORDER BY id DESC LIMIT 1")
        led_status = cursor.fetchone()
        cursor.execute("SELECT status FROM relay_fans_status WHERE device_id = 6 ORDER BY id DESC LIMIT 1")
        fan_status = cursor.fetchone()
        cursor.execute("SELECT direction FROM dc_motor_status WHERE device_id = 3 ORDER BY id DESC LIMIT 1")
        motor_status = cursor.fetchone()
        conn.close()
        return {
            'led_status': 'ON' if led_status and led_status['status'] == 1 else 'OFF',
            'fan_status': 'ON' if fan_status and fan_status['status'] == 1 else 'OFF',
            'motor_status': motor_status['direction'].capitalize() if motor_status else 'Unknown'
        }
    except Exception as e:
        logging.error(f"Error fetching device statuses: {e}")
        return None

# MQTT callbacks
def on_connect(client, userdata, flags, reason_code, properties=None):
    if reason_code == 0:
        logging.info("Connected to MQTT Broker!")
        client.subscribe("home/sensors", qos=1)
        client.subscribe("home/control", qos=1)
    else:
        logging.error(f"Failed to connect, return code {reason_code}")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    logging.info(f"Received {payload} from {topic}")

    message = {}
    if topic == "home/sensors":
        try:
            humidity, temperature, light = map(float, payload.split(","))
            store_sensor_data(humidity, temperature, light)
            message['sensors'] = {
                'humidity': humidity,
                'temperature': temperature,
                'light': light
            }
        except Exception as e:
            logging.error(f"Error parsing sensor data: {e}")
            return
    elif topic == "home/control":
        try:
            if payload in ["led1_on", "led1_off"]:
                status = "ON" if payload == "led1_on" else "OFF"
                store_light_status(payload, 1)
                message['devices'] = {'led_status': status}
            elif payload in ["fan_on", "fan_off"]:
                status = "ON" if payload == "fan_on" else "OFF"
                store_fan_status(payload.replace("fan_", ""))
                message['devices'] = {'fan_status': status}
            elif payload in ["motor_forward", "motor_backward", "motor_stop"]:
                status = payload.replace("motor_", "").capitalize()
                store_motor_status(status.lower())
                message['devices'] = {'motor_status': status}
        except Exception as e:
            logging.error(f"Error parsing control data: {e}")
            return

    # Broadcast to SocketIO clients
    if message:
        socketio.emit('update', message)

# Simulate sensor data
def simulate_sensors():
    while True:
        temp = round(random.uniform(20.0, 30.0), 2)
        humidity = round(random.uniform(40.0, 80.0), 2)
        light = round(random.uniform(100, 1000), 2)
        
        payload = f"{humidity},{temp},{light}"
        try:
            client.publish("home/sensors", payload, qos=1)
            logging.info(f"Published sensor data: {payload}")
            socketio.emit('notification', {'notification': 'New sensor data generated'})
        except Exception as e:
            logging.error(f"Error publishing sensor data: {e}")
        time.sleep(2)

# Flask routes
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/initial_data')
def initial_data():
    sensor_data = get_latest_sensor_data()
    device_statuses = get_latest_device_statuses()
    if sensor_data and device_statuses:
        return jsonify({
            'sensors': sensor_data,
            'devices': device_statuses
        })
    return jsonify({'status': 'error', 'message': 'Failed to fetch data'}), 500

@app.route('/control', methods=['POST'])
def control():
    data = request.get_json()
    topic = data.get('topic')
    command = data.get('command')
    if topic == "home/control" and command in ["led1_on", "led1_off", "fan_on", "fan_off", "motor_forward", "motor_stop", "motor_backward"]:
        try:
            client.publish(topic, command, qos=1)
            logging.info(f"Published control command: {command}")
            return jsonify({"status": "success"})
        except Exception as e:
            logging.error(f"Error publishing control command: {e}")
            return jsonify({"status": "error", "message": str(e)}), 500
    return jsonify({"status": "error", "message": "Invalid command or topic"}), 400

# SocketIO event handlers
@socketio.on('connect')
def handle_connect():
    logging.info("SocketIO client connected")
    emit('notification', {'notification': 'WebSocket connected'})

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

# Start sensor simulation in a separate thread
threading.Thread(target=simulate_sensors, daemon=True).start()

# Run Flask app
if __name__ == '__main__':
    logging.info("Starting Flask server on http://127.0.0.1:5001")
    socketio.run(app, host='0.0.0.0', port=5001, debug=False)