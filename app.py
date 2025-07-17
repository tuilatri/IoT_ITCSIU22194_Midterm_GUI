import tkinter as tk
from tkinter import ttk
import paho.mqtt.client as mqtt
import random
import time
import threading
from flask import Flask, render_template, request, jsonify
from flask_sockets import Sockets
import json
import logging
import sqlite3

# Flask app setup
app = Flask(__name__)
sockets = Sockets(app)

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# MQTT setup
broker = "iot-dashboard.cloud.shiftr.io"
port = 1883
username = "iot-dashboard"
password = "YBxsZiVmkHljoCId"
client_id = f"iot-gui-08122004-{random.randint(0, 1000)}"
client = mqtt.Client(client_id=client_id)

# WebSocket clients
ws_clients = []

# Database connection
def get_db_connection():
    conn = sqlite3.connect(r'D:\IoT_ITCSIU22194_Midterm\iot_data.db', timeout=10)
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
def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logging.info("Connected to MQTT Broker!")
        client.subscribe("home/sensors", qos=1)
        client.subscribe("home/control", qos=1)
    else:
        logging.error(f"Failed to connect, return code {rc}")

def on_message(client, userdata, msg):
    topic = msg.topic
    payload = msg.payload.decode()
    logging.info(f"Received {payload} from {topic}")

    # Update Tkinter GUI
    if topic == "home/sensors":
        try:
            humidity, temperature, light = map(float, payload.split(","))
            temp_label.config(text=f"Temperature: {temperature:.2f} °C")
            humidity_label.config(text=f"Humidity: {humidity:.2f} %")
            light_label.config(text=f"Light: {light:.2f} lx")
        except Exception as e:
            logging.error(f"Error processing sensor data: {e}")
    elif topic == "home/control":
        if payload in ["led1_on", "led1_off"]:
            light_status_label.config(text=f"LED Status: {'ON' if payload == 'led1_on' else 'OFF'}")
        elif payload in ["fan_on", "fan_off"]:
            fan_status_label.config(text=f"Fan Status: {'ON' if payload == 'fan_on' else 'OFF'}")
        elif payload in ["motor_forward", "motor_backward", "motor_stop"]:
            motor_status_label.config(text=f"Motor Status: {payload.replace('motor_', '').capitalize()}")

    # Fetch latest data from database
    sensor_data = get_latest_sensor_data()
    device_statuses = get_latest_device_statuses()

    # Broadcast to WebSocket clients
    if sensor_data and device_statuses:
        message = {
            'sensors': sensor_data,
            'devices': device_statuses
        }
        for ws in ws_clients[:]:
            try:
                ws.send(json.dumps(message))
            except Exception:
                ws_clients.remove(ws)

# Simulate sensor data (for testing)
def simulate_sensors():
    while True:
        temp = round(random.uniform(20.0, 30.0), 2)
        humidity = round(random.uniform(40.0, 80.0), 2)
        light = round(random.uniform(100, 1000), 2)
        
        payload = f"{humidity},{temp},{light}"
        try:
            client.publish("home/sensors", payload, qos=1)
            logging.info(f"Published sensor data: {payload}")
        except Exception as e:
            logging.error(f"Error publishing sensor data: {e}")
        time.sleep(5)

# Tkinter GUI setup
root = tk.Tk()
root.title("IoT Simulator")
root.geometry("600x400")

# Sensor display
sensor_frame = ttk.LabelFrame(root, text="Sensor Readings", padding=10)
sensor_frame.pack(padx=10, pady=10, fill="x")

temp_label = ttk.Label(sensor_frame, text="Temperature: -- °C")
temp_label.pack(pady=5)
humidity_label = ttk.Label(sensor_frame, text="Humidity: -- %")
humidity_label.pack(pady=5)
light_label = ttk.Label(sensor_frame, text="Light: -- lx")
light_label.pack(pady=5)

# Device control
device_frame = ttk.LabelFrame(root, text="Device Controls", padding=10)
device_frame.pack(padx=10, pady=10, fill="x")

# LED controls
led_frame = ttk.Frame(device_frame)
led_frame.pack(pady=5, fill="x")
ttk.Label(led_frame, text="LED Control").pack(side="left")
light_status_label = ttk.Label(led_frame, text="LED Status: Unknown")
light_status_label.pack(side="right")
ttk.Button(led_frame, text="ON", command=lambda: client.publish("home/control", "led1_on", qos=1)).pack(side="left", padx=5)
ttk.Button(led_frame, text="OFF", command=lambda: client.publish("home/control", "led1_off", qos=1)).pack(side="left", padx=5)

# Fan controls
fan_frame = ttk.Frame(device_frame)
fan_frame.pack(pady=5, fill="x")
ttk.Label(fan_frame, text="Fan Control").pack(side="left")
fan_status_label = ttk.Label(fan_frame, text="Fan Status: Unknown")
fan_status_label.pack(side="right")
ttk.Button(fan_frame, text="ON", command=lambda: client.publish("home/control", "fan_on", qos=1)).pack(side="left", padx=5)
ttk.Button(fan_frame, text="OFF", command=lambda: client.publish("home/control", "fan_off", qos=1)).pack(side="left", padx=5)

# Motor controls
motor_frame = ttk.Frame(device_frame)
motor_frame.pack(pady=5, fill="x")
ttk.Label(motor_frame, text="Motor Control").pack(side="left")
motor_status_label = ttk.Label(motor_frame, text="Motor Status: Unknown")
motor_status_label.pack(side="right")
ttk.Button(motor_frame, text="Forward", command=lambda: client.publish("home/control", "motor_forward", qos=1)).pack(side="left", padx=5)
ttk.Button(motor_frame, text="Stop", command=lambda: client.publish("home/control", "motor_stop", qos=1)).pack(side="left", padx=5)
ttk.Button(motor_frame, text="Backward", command=lambda: client.publish("home/control", "motor_backward", qos=1)).pack(side="left", padx=5)

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

@sockets.route('/ws')
def websocket(ws):
    ws_clients.append(ws)
    while not ws.closed:
        try:
            ws.receive()
        except Exception:
            ws_clients.remove(ws)
            break

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
    from gevent import pywsgi
    from geventwebsocket.handler import WebSocketHandler
    logging.info("Starting Flask server on http://127.0.0.1:5001")
    server = pywsgi.WSGIServer(('', 5001), app, handler_class=WebSocketHandler)
    server.serve_forever()