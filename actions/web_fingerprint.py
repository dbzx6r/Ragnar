"""
web_fingerprint.py - Web service fingerprinting module.

Triggered when port 80 is open on a host. Probes common HTTP ports for page title,
Server header, and X-Powered-By to identify routers, NAS, printers, admin panels, etc.
Saves a fingerprint.json to Data Stolen and logs to the activity feed.
"""

import os
import json
import re
import logging
from datetime import datetime

try:
    import requests
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

from shared import SharedData
from logger import Logger

logger = Logger(name="web_fingerprint.py", level=logging.INFO)

b_class  = "WebFingerprint"
b_module = "web_fingerprint"
b_status = "web_fingerprint"
b_port   = 80
b_parent = None

HTTP_PORTS = [80, 8080, 8000, 8081, 8888, 443, 8443]
REQUEST_TIMEOUT = 5


class WebFingerprint:
    def __init__(self, shared_data):
        self.shared_data = shared_data
        logger.info("WebFingerprint initialized")

    def execute(self, ip, port, row, status_key):
        """Called by orchestrator when port 80 is open."""
        if not HAS_REQUESTS:
            return 'failed'

        self.shared_data.ragnarorch_status = b_status

        mac = row.get("MAC", "unknown").replace(":", "").lower()
        open_ports = self._extract_ports(row)
        http_ports = [p for p in HTTP_PORTS if p in open_ports]
        if not http_ports:
            http_ports = [80]

        out_dir = os.path.join(self.shared_data.datastolendir, "web", f"{mac}_{ip}")
        out_file = os.path.join(out_dir, "fingerprint.json")

        # Skip if already fingerprinted
        if os.path.exists(out_file):
            return 'success'

        results = []
        for p in http_ports:
            fp = self._probe(ip, p)
            if fp:
                results.append(fp)

        if not results:
            return 'failed'

        os.makedirs(out_dir, exist_ok=True)
        payload = {
            "ip": ip,
            "mac": mac,
            "scanned_at": datetime.now().isoformat(),
            "services": results,
        }
        with open(out_file, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2)

        # Pick the most informative result for the activity log
        best = max(results, key=lambda r: len(r.get("title", "") + r.get("server", "")))
        title = best.get("title") or best.get("server") or "Unknown"
        try:
            self.shared_data.log_activity(
                "web", f"Web service: {ip} — {title}",
                f"Port {best['port']} | Server: {best.get('server', '?')}",
                "web"
            )
        except Exception:
            pass

        logger.info(f"Web fingerprint saved for {ip}: {title}")
        return 'success'

    # ------------------------------------------------------------------

    def _probe(self, ip, port):
        scheme = "https" if port in (443, 8443) else "http"
        url = f"{scheme}://{ip}:{port}/"
        try:
            resp = requests.get(
                url, timeout=REQUEST_TIMEOUT, verify=False,
                allow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0"},
            )
            title = self._extract_title(resp.text)
            server = resp.headers.get("Server", "")
            powered_by = resp.headers.get("X-Powered-By", "")
            content_type = resp.headers.get("Content-Type", "")

            if resp.status_code in (200, 401, 403) and (title or server):
                return {
                    "port": port,
                    "scheme": scheme,
                    "status": resp.status_code,
                    "title": title,
                    "server": server,
                    "powered_by": powered_by,
                    "content_type": content_type,
                }
        except Exception:
            pass
        return None

    @staticmethod
    def _extract_title(html):
        m = re.search(r"<title[^>]*>([^<]{1,120})</title>", html, re.IGNORECASE)
        return m.group(1).strip() if m else ""

    @staticmethod
    def _extract_ports(row):
        raw = row.get("Ports", "") or ""
        ports = []
        for p in str(raw).split(","):
            p = p.strip().split("/")[0]
            try:
                ports.append(int(p))
            except ValueError:
                continue
        return ports
