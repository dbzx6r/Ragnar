"""
device_disguise.py - Incognito Mode: disguise Ragnar as an iPhone on the network.

When incognito_mode_enabled is True:
  - Spoofs wlan0 MAC address to a random Apple OUI + random last 3 octets
  - Sets hostname to 'iPhone' via hostnamectl
  - Restarts avahi-daemon so the device broadcasts as iPhone.local
  - Stores original MAC in shared_data.original_mac
  - Updates shared_data.mac_scan_blacklist with the spoofed MAC

When incognito_mode_enabled is False (and original_mac is set):
  - Restores original MAC address
  - Restores hostname to 'ragnar'
  - Restarts avahi-daemon

Safe to run repeatedly (idempotent).
"""

import logging
import os
import random
import subprocess

from shared import SharedData
from logger import Logger

logger = Logger(name="device_disguise.py", level=logging.INFO)

b_class  = "DeviceDisguise"
b_module = "device_disguise"
b_status = "device_disguise"
b_port   = None
b_parent = None

APPLE_OUIS = [
    "F4:F1:5A",
    "A8:66:7F",
    "3C:E0:72",
    "8C:85:90",
    "DC:2B:2A",
    "60:F8:1D",
    "AC:DE:48",
    "A4:C3:F0",
    "BC:D0:74",
    "F0:DB:E2",
]


def _run(cmd):
    """Run a shell command as root. Returns (returncode, stdout, stderr)."""
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def _get_current_mac(iface):
    """Read the current MAC address from sysfs."""
    try:
        with open(f"/sys/class/net/{iface}/address", "r") as f:
            return f.read().strip()
    except Exception:
        return ""


def _random_apple_mac():
    """Generate a random MAC address using an Apple OUI."""
    oui = random.choice(APPLE_OUIS)
    last_three = ":".join(f"{random.randint(0, 255):02X}" for _ in range(3))
    return f"{oui}:{last_three}"


def _set_mac(iface, mac):
    """Bring interface down, set MAC, bring back up."""
    rc1, _, err1 = _run(["ip", "link", "set", iface, "down"])
    if rc1 != 0:
        logger.warning(f"  Failed to bring {iface} down: {err1}")
    rc2, _, err2 = _run(["ip", "link", "set", iface, "address", mac])
    if rc2 != 0:
        logger.warning(f"  Failed to set MAC on {iface}: {err2}")
    rc3, _, err3 = _run(["ip", "link", "set", iface, "up"])
    if rc3 != 0:
        logger.warning(f"  Failed to bring {iface} up: {err3}")
    return rc2 == 0


def _set_hostname(hostname):
    rc, _, err = _run(["hostnamectl", "set-hostname", hostname])
    if rc != 0:
        logger.warning(f"  hostnamectl failed: {err}")
    return rc == 0


def _restart_avahi():
    rc, _, err = _run(["systemctl", "restart", "avahi-daemon"])
    if rc != 0:
        logger.warning(f"  Failed to restart avahi-daemon: {err}")
    return rc == 0


def _renew_dhcp(iface):
    """Renew DHCP lease so the router receives the updated hostname."""
    rc, _, err = _run(["dhcpcd", "-n", iface])
    if rc != 0:
        logger.warning(f"  dhcpcd renewal failed on {iface}: {err}")
    return rc == 0


class DeviceDisguise:

    def __init__(self, shared_data):
        self.shared_data = shared_data
        logger.info("DeviceDisguise initialized")

    def execute(self):
        """
        Called by the Ragnar orchestrator. Acts on incognito_mode_enabled flag.
        This module is stateless per-call — it applies or reverts disguise each run.
        """
        incognito = getattr(self.shared_data, 'incognito_mode_enabled', False)
        iface = getattr(self.shared_data, 'default_wifi_interface', 'wlan0')

        if incognito:
            self._enable_disguise(iface)
        else:
            self._disable_disguise(iface)

        return 'success'

    def _enable_disguise(self, iface):
        """Spoof MAC, set hostname to iPhone, restart avahi."""
        logger.info("🕵️  Incognito Mode: enabling iPhone disguise")

        # Save original MAC before first spoof
        current_mac = _get_current_mac(iface)
        original_mac = getattr(self.shared_data, 'original_mac', '')
        if not original_mac and current_mac:
            self.shared_data.original_mac = current_mac
            logger.info(f"  Saved original MAC: {current_mac}")

        # Generate and apply spoofed Apple MAC
        spoofed_mac = _random_apple_mac()
        logger.info(f"  Spoofing {iface} MAC → {spoofed_mac}")
        mac_ok = _set_mac(iface, spoofed_mac)

        if mac_ok:
            # Update shared blacklist with spoofed MAC
            blacklist = getattr(self.shared_data, 'mac_scan_blacklist', [])
            if not isinstance(blacklist, list):
                blacklist = []
            spoofed_lower = spoofed_mac.lower()
            if spoofed_lower not in [m.lower() for m in blacklist]:
                blacklist.append(spoofed_lower)
                self.shared_data.mac_scan_blacklist = blacklist
                logger.info(f"  Added {spoofed_lower} to mac_scan_blacklist")

        # Set hostname
        logger.info("  Setting hostname → iPhone")
        _set_hostname("iPhone")

        # Renew DHCP lease so router sees new hostname
        logger.info("  Renewing DHCP lease")
        _renew_dhcp(iface)

        # Restart avahi to broadcast iPhone.local
        logger.info("  Restarting avahi-daemon")
        _restart_avahi()

        logger.info("✅ Incognito Mode active — broadcasting as iPhone.local")

    def _disable_disguise(self, iface):
        """Restore original MAC and hostname, restart avahi."""
        original_mac = getattr(self.shared_data, 'original_mac', '')
        if not original_mac:
            logger.info("Incognito Mode: no original MAC stored — nothing to restore")
            return

        logger.info("🔓 Incognito Mode: restoring original identity")
        logger.info(f"  Restoring MAC → {original_mac}")
        _set_mac(iface, original_mac)

        logger.info("  Restoring hostname → ragnar")
        _set_hostname("ragnar")

        # Renew DHCP lease so router sees restored hostname
        logger.info("  Renewing DHCP lease")
        _renew_dhcp(iface)

        logger.info("  Restarting avahi-daemon")
        _restart_avahi()

        # Clear stored original MAC
        self.shared_data.original_mac = ""
        logger.info("✅ Incognito Mode disabled — identity restored")


def restore_on_startup(shared_data):
    """
    Called once at Ragnar startup to repair any hostname/MAC state left over
    from a previous run where incognito was active but the device was powered off
    before incognito could be cleanly disabled.

    Checks if the current hostname is 'iPhone' or the current MAC matches an Apple
    OUI, while config says incognito_mode_enabled=False. If so, restores hostname
    to 'ragnar' and attempts MAC restore from original_mac (if stored in config).
    """
    try:
        cfg = getattr(shared_data, 'config', {})
        if cfg.get('incognito_mode_enabled', False):
            # Incognito is intentionally on — do not restore
            return

        iface = getattr(shared_data, 'default_wifi_interface', 'wlan0')

        # Check hostname
        rc, hostname, _ = _run(["hostname"])
        hostname_dirty = rc == 0 and hostname.strip().lower() in ('iphone', 'iphone.local')

        # Check if current MAC is an Apple OUI
        current_mac = _get_current_mac(iface)
        apple_ouis_lower = [oui.lower() for oui in APPLE_OUIS]
        mac_dirty = current_mac and any(current_mac.lower().startswith(oui.lower()) for oui in apple_ouis_lower)

        if not hostname_dirty and not mac_dirty:
            return  # Nothing to restore

        logger.info("⚠️  Detected stale incognito state from previous run — restoring identity")

        # Restore MAC if possible
        original_mac = cfg.get('original_mac', '') or getattr(shared_data, 'original_mac', '')
        if mac_dirty and original_mac:
            logger.info(f"  Restoring MAC → {original_mac}")
            _set_mac(iface, original_mac)
            shared_data.original_mac = ''

        # Restore hostname
        if hostname_dirty:
            logger.info("  Restoring hostname → ragnar")
            _set_hostname("ragnar")
            _restart_avahi()

        logger.info("✅ Stale incognito state cleaned up")

    except Exception as exc:
        logger.warning(f"restore_on_startup: failed ({exc})")
