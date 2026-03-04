"""bt_wifi.py — Bluetooth RFCOMM serial interface for Ragnar WiFi control.

Advertises as a common Bluetooth speaker so it blends in on BT scans.
Connect with any Bluetooth serial terminal app and use simple commands
to switch WiFi networks without needing the web interface.

Commands:
  list              — list saved/known WiFi networks
  scan              — list currently visible networks
  status            — show current connection status
  connect <ssid>    — connect to a saved network (no password needed if saved)
  connect <ssid> <password>  — connect with password
  disconnect        — disconnect from current network
  help              — show command list
"""

import logging
import subprocess
import threading

logger = logging.getLogger(__name__)

# Stealth BT device name — common enough to blend in on any BT scan
BT_DEVICE_NAME = "ragnar"

# RFCOMM channel for serial port profile
RFCOMM_CHANNEL = 1


class BluetoothWiFiControl:
    def __init__(self, shared_data):
        self.shared_data = shared_data
        self._thread = None
        self._running = False

    def start(self):
        """Start the BT listener in a background daemon thread."""
        try:
            import bluetooth  # noqa: F401 — fail fast if PyBluez not installed
        except ImportError:
            logger.warning("bt_wifi: PyBluez not installed — Bluetooth WiFi control disabled")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run, name="bt-wifi", daemon=True)
        self._thread.start()
        logger.info(f"bt_wifi: Bluetooth WiFi control started (advertising as '{BT_DEVICE_NAME}')")

    def stop(self):
        self._running = False

    # ------------------------------------------------------------------ #
    #  Internal helpers                                                    #
    # ------------------------------------------------------------------ #

    def _get_wifi_manager(self):
        """Return the WiFiManager instance if available."""
        ragnar = getattr(self.shared_data, 'ragnar_instance', None)
        if ragnar and hasattr(ragnar, 'wifi_manager'):
            return ragnar.wifi_manager
        return None

    def _cmd_status(self):
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'ACTIVE,SSID,SIGNAL,SECURITY', 'dev', 'wifi'],
                capture_output=True, text=True, timeout=5
            )
            active = [line for line in result.stdout.strip().splitlines() if line.startswith('yes:')]
            if active:
                parts = active[0].split(':')
                ssid = parts[1] if len(parts) > 1 else '?'
                signal = parts[2] if len(parts) > 2 else '?'
                return f"Connected: {ssid}  Signal: {signal}%\r\n"
            return "Not connected to any WiFi network\r\n"
        except Exception as e:
            return f"Error: {e}\r\n"

    def _cmd_list(self):
        wm = self._get_wifi_manager()
        if not wm:
            return "WiFi manager not available\r\n"
        try:
            networks = getattr(wm, 'known_networks', []) or []
            if not networks:
                result = subprocess.run(
                    ['nmcli', '-t', '-f', 'NAME', 'con', 'show'],
                    capture_output=True, text=True, timeout=5
                )
                networks = [{'ssid': l.strip()} for l in result.stdout.strip().splitlines() if l.strip()]
            lines = "\r\n".join(f"  {n.get('ssid', n) if isinstance(n, dict) else n}" for n in networks)
            return f"Saved networks:\r\n{lines}\r\n" if lines else "No saved networks found\r\n"
        except Exception as e:
            return f"Error: {e}\r\n"

    def _cmd_scan(self):
        try:
            result = subprocess.run(
                ['nmcli', '-t', '-f', 'SSID,SIGNAL,SECURITY', 'dev', 'wifi', 'list'],
                capture_output=True, text=True, timeout=10
            )
            lines = []
            seen = set()
            for line in result.stdout.strip().splitlines():
                parts = line.split(':')
                ssid = parts[0].strip() if parts else ''
                if ssid and ssid not in seen:
                    seen.add(ssid)
                    signal = parts[1] if len(parts) > 1 else '?'
                    sec = parts[2] if len(parts) > 2 else ''
                    lines.append(f"  {ssid}  ({signal}%) {sec}")
            return ("Visible networks:\r\n" + "\r\n".join(lines) + "\r\n") if lines else "No networks visible\r\n"
        except Exception as e:
            return f"Error: {e}\r\n"

    def _cmd_connect(self, args):
        if not args:
            return "Usage: connect <ssid> [password]\r\n"
        # SSID may contain spaces — everything before the last token if looks like a password
        # Simple heuristic: if 2+ tokens and last has no spaces treat as: ssid=all-but-last, pw=last
        # Better: user can quote or just type ssid exactly
        parts = args.split(' ', 1)
        ssid = parts[0]
        password = parts[1] if len(parts) > 1 else None

        wm = self._get_wifi_manager()
        if not wm:
            return "WiFi manager not available\r\n"
        try:
            logger.info(f"bt_wifi: connecting to '{ssid}' via Bluetooth command")
            success = wm.connect_to_network(ssid, password)
            if success:
                return f"Connected to {ssid}\r\n"
            return f"Failed to connect to {ssid} — check SSID/password\r\n"
        except Exception as e:
            return f"Error: {e}\r\n"

    def _cmd_disconnect(self):
        try:
            result = subprocess.run(
                ['sudo', 'nmcli', 'dev', 'disconnect', 'wlan0'],
                capture_output=True, text=True, timeout=10
            )
            if result.returncode == 0:
                return "Disconnected\r\n"
            return f"Failed to disconnect: {result.stderr.strip()}\r\n"
        except Exception as e:
            return f"Error: {e}\r\n"

    def _handle_command(self, raw):
        line = raw.strip()
        if not line:
            return ""
        cmd, _, args = line.partition(' ')
        cmd = cmd.lower()
        if cmd == 'status':
            return self._cmd_status()
        elif cmd == 'list':
            return self._cmd_list()
        elif cmd == 'scan':
            return self._cmd_scan()
        elif cmd == 'connect':
            return self._cmd_connect(args.strip())
        elif cmd == 'disconnect':
            return self._cmd_disconnect()
        elif cmd in ('help', '?'):
            return (
                "Commands:\r\n"
                "  status                   current WiFi connection\r\n"
                "  list                     saved/known networks\r\n"
                "  scan                     visible networks\r\n"
                "  connect <ssid>           connect to saved network\r\n"
                "  connect <ssid> <pass>    connect with password\r\n"
                "  disconnect               disconnect from WiFi\r\n"
                "  help                     this message\r\n"
            )
        else:
            return f"Unknown command: {cmd}  (type 'help')\r\n"

    # ------------------------------------------------------------------ #
    #  Main BT server loop                                                 #
    # ------------------------------------------------------------------ #

    def _run(self):
        import bluetooth

        # Set the BT device name before advertising
        try:
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'name', BT_DEVICE_NAME],
                           capture_output=True, timeout=5)
            subprocess.run(['sudo', 'hciconfig', 'hci0', 'piscan'],
                           capture_output=True, timeout=5)
        except Exception as e:
            logger.warning(f"bt_wifi: could not set BT name/visibility: {e}")

        server_sock = None
        while self._running:
            try:
                server_sock = bluetooth.BluetoothSocket(bluetooth.RFCOMM)
                server_sock.bind(("", RFCOMM_CHANNEL))
                server_sock.listen(1)

                bluetooth.advertise_service(
                    server_sock,
                    BT_DEVICE_NAME,
                    service_classes=[bluetooth.SERIAL_PORT_CLASS],
                    profiles=[bluetooth.SERIAL_PORT_PROFILE],
                )

                logger.info(f"bt_wifi: listening on RFCOMM channel {RFCOMM_CHANNEL}")

                while self._running:
                    try:
                        server_sock.settimeout(2.0)
                        try:
                            client_sock, client_info = server_sock.accept()
                        except bluetooth.btcommon.BluetoothError:
                            continue  # timeout — loop to check _running

                        logger.info(f"bt_wifi: connection from {client_info}")
                        try:
                            client_sock.send("Ragnar WiFi Control\r\nType 'help' for commands\r\n> ")
                            buf = ""
                            while self._running:
                                try:
                                    client_sock.settimeout(60.0)
                                    data = client_sock.recv(256)
                                    if not data:
                                        break
                                    buf += data.decode('utf-8', errors='replace')
                                    while '\n' in buf or '\r' in buf:
                                        for sep in ('\r\n', '\n', '\r'):
                                            if sep in buf:
                                                line, buf = buf.split(sep, 1)
                                                response = self._handle_command(line)
                                                if response:
                                                    client_sock.send(response)
                                                client_sock.send("> ")
                                                break
                                except bluetooth.btcommon.BluetoothError:
                                    break
                        finally:
                            client_sock.close()
                            logger.info("bt_wifi: client disconnected")

                    except Exception as e:
                        if self._running:
                            logger.warning(f"bt_wifi: client error: {e}")

            except Exception as e:
                if self._running:
                    logger.error(f"bt_wifi: server error: {e}")
            finally:
                if server_sock:
                    try:
                        server_sock.close()
                    except Exception:
                        pass
                    server_sock = None

            if self._running:
                import time
                time.sleep(5)  # wait before retrying
