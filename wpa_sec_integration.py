#!/usr/bin/env python3
"""
wpa-sec Integration for Ragnar.

Polls wpa-sec.stanev.org for cracked WPA passwords and automatically
adds them to Ragnar's known WiFi networks list so Ragnar can connect
to those networks when it encounters them.

Configuration keys (set via the Ragnar web Config tab):
  wpasec_enabled        - bool:  enable/disable the integration (default False)
  wpasec_api_key        - str:   your wpa-sec account key from wpa-sec.stanev.org
  wpasec_poll_interval  - int:   seconds between polls (default 3600)
  wpasec_auto_connect   - bool:  add cracked networks to known list (default True)
  wpasec_priority       - int:   priority assigned to auto-added networks (default 5)
"""

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from logger import Logger

WPA_SEC_URL = "https://wpa-sec.stanev.org/?api&dl=1"
CACHE_FILENAME = "wpa_sec_imported.json"


class WpaSecIntegration:
    """Background poller that imports wpa-sec cracked passwords into Ragnar."""

    def __init__(self, shared_data):
        self.shared_data = shared_data
        self.logger = Logger(name="WpaSecIntegration", level=logging.INFO)
        self._thread = None
        self._stop_event = threading.Event()

        data_dir = getattr(shared_data, 'datadir', os.path.join(os.path.dirname(__file__), 'data'))
        self._cache_path = os.path.join(data_dir, CACHE_FILENAME)

        # Cache: set of BSSIDs already imported, to avoid duplicates across restarts
        self._imported_bssids: set
        # Cache: set of "ssid|password" already imported, to skip same-network multi-AP entries
        self._imported_ssid_keys: set
        self._imported_bssids, self._imported_ssid_keys = self._load_cache()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def start(self):
        """Start the background polling thread (no-op if disabled or already running)."""
        if not self._is_enabled():
            self.logger.info("wpa-sec integration disabled — set wpasec_enabled=True to activate")
            return
        if not HAS_REQUESTS:
            self.logger.warning("wpa-sec integration requires the 'requests' library — skipping")
            return
        if self._thread and self._thread.is_alive():
            return

        self._stop_event.clear()
        self._thread = threading.Thread(target=self._poll_loop, daemon=True, name="WpaSecPoller")
        self._thread.start()
        self.logger.info("wpa-sec poller started")

    def stop(self):
        """Signal the polling thread to exit."""
        self._stop_event.set()
        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=5)
        self.logger.info("wpa-sec poller stopped")

    def poll_now(self) -> dict:
        """
        Trigger an immediate poll outside the background thread.
        Returns a summary dict: {'added': int, 'total_cracked': int, 'error': str|None}
        """
        return self._poll()

    # ------------------------------------------------------------------
    # Background loop
    # ------------------------------------------------------------------

    def _poll_loop(self):
        # Poll once immediately on start, then sleep between subsequent polls
        self._poll()
        while not self._stop_event.is_set():
            interval = self._get_config('wpasec_poll_interval', 3600)
            self._stop_event.wait(timeout=interval)
            if not self._stop_event.is_set():
                self._poll()

    # ------------------------------------------------------------------
    # Core poll logic
    # ------------------------------------------------------------------

    def _poll(self) -> dict:
        result = {'added': 0, 'total_cracked': 0, 'error': None}

        api_key = self._get_config('wpasec_api_key', '').strip()
        if not api_key:
            self.logger.warning("wpasec_api_key not set — skipping poll")
            result['error'] = 'api_key_missing'
            return result

        auto_connect = self._get_config('wpasec_auto_connect', True)
        priority = self._get_config('wpasec_priority', 5)

        try:
            resp = requests.get(
                WPA_SEC_URL,
                cookies={'key': api_key},
                timeout=30,
            )
        except requests.RequestException as exc:
            self.logger.error(f"wpa-sec request failed: {exc}")
            result['error'] = str(exc)
            return result

        if resp.status_code == 403:
            self.logger.error("wpa-sec returned 403 — check your wpasec_api_key")
            result['error'] = 'invalid_api_key'
            return result

        if resp.status_code != 200:
            self.logger.error(f"wpa-sec returned HTTP {resp.status_code}")
            result['error'] = f'http_{resp.status_code}'
            return result

        entries = self._parse_netlist(resp.text)
        result['total_cracked'] = len(entries)

        new_entries = []
        for e in entries:
            ssid_key = f"{e['ssid']}|{e['password']}"
            if e['bssid'] not in self._imported_bssids and ssid_key not in self._imported_ssid_keys:
                new_entries.append(e)

        if not new_entries:
            self.logger.debug(f"wpa-sec poll: {len(entries)} cracked total, 0 new")
            return result

        wifi_manager = self._get_wifi_manager()

        for entry in new_entries:
            ssid = entry['ssid']
            password = entry['password']
            bssid = entry['bssid']

            if auto_connect and wifi_manager:
                try:
                    wifi_manager.add_known_network(ssid, password, priority)
                    self.logger.info(f"Added cracked network to known list: SSID='{ssid}' BSSID={bssid}")
                    result['added'] += 1
                except Exception as exc:
                    self.logger.error(f"Failed to add network '{ssid}': {exc}")
                    continue
            else:
                self.logger.info(f"wpa-sec cracked: SSID='{ssid}' BSSID={bssid} (auto_connect disabled)")
                result['added'] += 1

            self._imported_bssids.add(bssid)
            self._imported_ssid_keys.add(f"{ssid}|{password}")

        self._save_cache(new_entries)
        self.logger.info(f"wpa-sec poll complete: {result['added']} new network(s) added ({len(entries)} total cracked)")
        return result

    # ------------------------------------------------------------------
    # TSV parser
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_netlist(text: str) -> list:
        """
        Parse wpa-sec download response (?api&dl=1).
        Each line: <BSSID>:<StationMAC>:<SSID>:<Password>
        BSSID and StationMAC are 12-char hex strings (no colons within them).
        Returns list of dicts with keys: bssid, ssid, password
        """
        entries = []
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            # Split on ':' with maxsplit=3 so passwords containing colons are preserved.
            # BSSID and station_mac are always 12-char hex strings with no embedded colons.
            parts = line.split(':', 3)
            if len(parts) < 4:
                continue
            bssid = parts[0].strip().lower()
            # parts[1] is station_mac — skip it
            ssid = parts[2].strip()
            password = parts[3].strip()
            if not bssid or not ssid or not password:
                continue
            entries.append({'bssid': bssid, 'ssid': ssid, 'password': password})
        return entries

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _load_cache(self) -> tuple:
        """Returns (imported_bssids: set, imported_ssid_keys: set)."""
        try:
            if os.path.exists(self._cache_path):
                with open(self._cache_path, 'r', encoding='utf-8') as fh:
                    data = json.load(fh)
                    imported = data.get('imported', [])
                    bssids = {entry['bssid'] for entry in imported}
                    ssid_keys = {f"{entry['ssid']}|{entry.get('password', '')}" for entry in imported if entry.get('password')}
                    return bssids, ssid_keys
        except (OSError, json.JSONDecodeError, KeyError) as exc:
            self.logger.warning(f"Could not load wpa-sec cache: {exc}")
        return set(), set()

    def _save_cache(self, new_entries: list):
        try:
            existing = []
            if os.path.exists(self._cache_path):
                with open(self._cache_path, 'r', encoding='utf-8') as fh:
                    existing = json.load(fh).get('imported', [])
        except (OSError, json.JSONDecodeError):
            existing = []

        now = datetime.now(timezone.utc).isoformat()
        for entry in new_entries:
            existing.append({
                'bssid': entry['bssid'],
                'ssid': entry['ssid'],
                'password': entry['password'],
                'imported_at': now,
            })

        try:
            os.makedirs(os.path.dirname(self._cache_path), exist_ok=True)
            with open(self._cache_path, 'w', encoding='utf-8') as fh:
                json.dump({'imported': existing}, fh, indent=2)
        except OSError as exc:
            self.logger.error(f"Could not save wpa-sec cache: {exc}")

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _is_enabled(self) -> bool:
        return bool(self._get_config('wpasec_enabled', False))

    def _get_config(self, key: str, default=None):
        return self.shared_data.config.get(key, default)

    def _get_wifi_manager(self):
        """Retrieve the live WiFiManager from the Ragnar instance."""
        ragnar = getattr(self.shared_data, 'ragnar_instance', None)
        if ragnar and hasattr(ragnar, 'wifi_manager'):
            return ragnar.wifi_manager
        return None
