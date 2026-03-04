"""Lightweight device type classifier using MAC OUI vendor strings and open ports.

Zero external dependencies — pure Python dict lookups.
Designed for Pi Zero W2: classification takes <1ms per host.
"""


# ---------------------------------------------------------------------------
# Vendor keyword → device_type  (lowercase substring match against vendor)
# ---------------------------------------------------------------------------
_VENDOR_RULES = {
    # Networking equipment
    "router": [
        "cisco", "ubiquiti", "unifi", "mikrotik", "netgear", "tp-link",
        "tplink", "tp link", "asus", "linksys", "d-link", "dlink",
        "zyxel", "aruba", "ruckus", "meraki", "juniper", "fortinet",
        "sonicwall", "pfsense", "opnsense", "edgerouter", "synology router",
        "huawei technolog",  # Huawei networking gear
    ],
    # Access points (often same vendors but specific product lines)
    "access_point": [
        "ubiquiti networks", "aruba networks", "ruckus wireless",
        "engenius", "cambium",
    ],
    # Phones / tablets
    "phone": [
        "apple", "samsung electro", "google", "oneplus", "xiaomi",
        "huawei device", "oppo", "vivo", "realme", "motorola",
        "nokia", "sony mobile", "lg electronics", "honor",
    ],
    # Printers
    "printer": [
        "hewlett packard", "hp inc", "canon", "brother", "epson",
        "lexmark", "xerox", "kyocera", "ricoh", "konica",
    ],
    # IoT / embedded
    "iot": [
        "espressif", "tuya", "shelly", "sonoff", "tasmota",
        "philips lighting", "signify", "ikea of sweden",
        "nest", "ring", "wyze", "ecobee", "meross",
        "broadlink", "yeelight", "wemo", "smart",
        "amazon technologies",  # Echo devices
    ],
    # Servers / NAS
    "server": [
        "synology", "qnap", "asustor", "drobo", "buffalo",
        "vmware", "supermicro", "dell emc",
    ],
    # Workstations / desktops / laptops
    "workstation": [
        "dell", "lenovo", "intel corporate", "hewlett", "acer",
        "msi", "gigabyte", "asrock", "asus",
        "microsoft", "surface",
    ],
    # Raspberry Pi / SBCs
    "iot": [
        "raspberry", "pi foundation",
    ],
    # Media / entertainment
    "media": [
        "roku", "sonos", "bose", "harman", "bang & olufsen",
        "denon", "marantz", "yamaha",
        "nvidia",  # Shield TV
        "apple tv",
    ],
    # Game consoles
    "gaming": [
        "nintendo", "sony interactive", "playstation",
        "microsoft xbox", "valve",
    ],
}

# Flatten: build list of (substring, device_type) sorted longest-first
# so more specific matches win (e.g. "ubiquiti networks" before "ubiquiti")
_VENDOR_LOOKUP = []
for _dtype, _keywords in _VENDOR_RULES.items():
    for _kw in _keywords:
        _VENDOR_LOOKUP.append((_kw, _dtype))
_VENDOR_LOOKUP.sort(key=lambda x: -len(x[0]))


# ---------------------------------------------------------------------------
# Port-based classification rules (applied when vendor is inconclusive)
# ---------------------------------------------------------------------------
def _classify_by_ports(ports):
    """Classify device type from a set of open port numbers."""
    if not ports:
        return None

    port_set = set()
    for p in ports:
        try:
            port_set.add(int(str(p).split("/")[0]))
        except (ValueError, IndexError):
            continue

    # Router: serves DNS + HTTP (typical home router)
    if 53 in port_set and (80 in port_set or 443 in port_set):
        return "router"
    # DHCP server → router
    if 67 in port_set:
        return "router"
    # Printer protocols
    if 9100 in port_set or 631 in port_set or 515 in port_set:
        return "printer"
    # RDP → Windows workstation
    if 3389 in port_set:
        return "workstation"
    # SMB/CIFS without other indicators → workstation or NAS
    if 445 in port_set and 22 not in port_set:
        return "workstation"
    # MQTT → IoT hub
    if 1883 in port_set or 8883 in port_set:
        return "iot"
    # Media streaming ports
    if 8009 in port_set or 5353 in port_set:
        return "media"
    # SSH + HTTP but nothing else → server
    if 22 in port_set and (80 in port_set or 443 in port_set) and len(port_set) <= 4:
        return "server"
    # Many open ports → likely a server
    if len(port_set) >= 6:
        return "server"

    return None


# ---------------------------------------------------------------------------
# SVG icon paths per device type (simple, lightweight)
# ---------------------------------------------------------------------------
DEVICE_ICONS = {
    "router":       "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z",
    "access_point": "M12 6c-1.1 0-2 .9-2 2s.9 2 2 2 2-.9 2-2-.9-2-2-2zm0-4C8.69 2 5.78 3.56 3.93 6l1.41 1.41C6.89 5.56 9.3 4.5 12 4.5s5.11 1.06 6.66 2.91L20.07 6C18.22 3.56 15.31 2 12 2zm0 4c-2.21 0-4.21.9-5.66 2.34l1.41 1.41C8.86 8.64 10.35 8 12 8s3.14.64 4.24 1.76l1.41-1.41C16.21 6.9 14.21 6 12 6zm0 10c.55 0 1 .45 1 1v3h-2v-3c0-.55.45-1 1-1z",
    "phone":        "M16 1H8C6.34 1 5 2.34 5 4v16c0 1.66 1.34 3 3 3h8c1.66 0 3-1.34 3-3V4c0-1.66-1.34-3-3-3zm-2 20h-4v-1h4v1zm3.25-3H6.75V4h10.5v14z",
    "printer":      "M19 8H5c-1.66 0-3 1.34-3 3v6h4v4h12v-4h4v-6c0-1.66-1.34-3-3-3zm-3 11H8v-5h8v5zm3-7c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm-1-9H6v4h12V3z",
    "iot":          "M7.5 5.6L10 7 8.6 4.5 10 2 7.5 3.4 5 2l1.4 2.5L5 7zm12 9.8L17 14l1.4 2.5L17 19l2.5-1.4L22 19l-1.4-2.5L22 14zM22 2l-2.5 1.4L17 2l1.4 2.5L17 7l2.5-1.4L22 7l-1.4-2.5zm-7.63 5.29a1 1 0 00-1.41 0L1.29 18.96a1 1 0 000 1.41l2.34 2.34a1 1 0 001.41 0L16.71 11.04a1 1 0 000-1.41l-2.34-2.34z",
    "workstation":  "M21 2H3c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h7l-2 3v1h8v-1l-2-3h7c1.1 0 2-.9 2-2V4c0-1.1-.9-2-2-2zm0 12H3V4h18v10z",
    "server":       "M20 13H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1v-6c0-.55-.45-1-1-1zM7 19c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2zM20 3H4c-.55 0-1 .45-1 1v6c0 .55.45 1 1 1h16c.55 0 1-.45 1-1V4c0-.55-.45-1-1-1zM7 9c-1.1 0-2-.9-2-2s.9-2 2-2 2 .9 2 2-.9 2-2 2z",
    "media":        "M21 3H3c-1.1 0-2 .9-2 2v14c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V5c0-1.1-.9-2-2-2zm0 16H3V5h18v14zM10 8v8l6-4z",
    "gaming":       "M21 6H3c-1.1 0-2 .9-2 2v8c0 1.1.9 2 2 2h18c1.1 0 2-.9 2-2V8c0-1.1-.9-2-2-2zm-10 7H8v3H6v-3H3v-2h3V8h2v3h3v2zm4.5 2c-.83 0-1.5-.67-1.5-1.5s.67-1.5 1.5-1.5 1.5.67 1.5 1.5-.67 1.5-1.5 1.5zm4-3c-.83 0-1.5-.67-1.5-1.5S18.67 9 19.5 9s1.5.67 1.5 1.5-.67 1.5-1.5 1.5z",
    "ragnar":       "M12 1L3 5v6c0 5.55 3.84 10.74 9 12 5.16-1.26 9-6.45 9-12V5l-9-4zm0 10.99h7c-.53 4.12-3.28 7.79-7 8.94V12H5V6.3l7-3.11v8.8z",
    "unknown":      "M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 17h-2v-2h2v2zm2.07-7.75l-.9.92C13.45 12.9 13 13.5 13 15h-2v-.5c0-1.1.45-2.1 1.17-2.83l1.24-1.26c.37-.36.59-.86.59-1.41 0-1.1-.9-2-2-2s-2 .9-2 2H8c0-2.21 1.79-4 4-4s4 1.79 4 4c0 .88-.36 1.68-.93 2.25z",
}

# Display labels for UI
DEVICE_TYPE_LABELS = {
    "router": "Router/Gateway",
    "access_point": "Access Point",
    "phone": "Phone/Tablet",
    "printer": "Printer",
    "iot": "IoT Device",
    "workstation": "Workstation",
    "server": "Server/NAS",
    "media": "Media Device",
    "gaming": "Game Console",
    "ragnar": "Ragnar",
    "unknown": "Unknown",
}

# Colors per device type (for map legend)
DEVICE_TYPE_COLORS = {
    "router": "#f59e0b",       # amber
    "access_point": "#8b5cf6", # purple
    "phone": "#3b82f6",        # blue
    "printer": "#6b7280",      # gray
    "iot": "#10b981",          # emerald
    "workstation": "#06b6d4",  # cyan
    "server": "#ef4444",       # red
    "media": "#ec4899",        # pink
    "gaming": "#a855f7",       # violet
    "ragnar": "#0ea5e9",       # sky (Ragnar brand)
    "unknown": "#64748b",      # slate
}


def classify_device(vendor, ports, gateway_ip=None, device_ip=None):
    """Classify a network device by its MAC vendor string and open ports.

    Args:
        vendor: MAC OUI vendor string (e.g. "TP-Link Technologies")
        ports: list of port strings or ints (e.g. ["22", "80", "443"])
        gateway_ip: the network's default gateway IP (if known)
        device_ip: this device's IP address

    Returns:
        dict with keys: device_type, label, confidence (0.0-1.0)
    """
    # Gateway always wins
    if gateway_ip and device_ip and device_ip == gateway_ip:
        return {
            "device_type": "router",
            "label": DEVICE_TYPE_LABELS["router"],
            "confidence": 1.0,
        }

    device_type = None
    confidence = 0.3  # base confidence for unknown

    # Pass 1: vendor keyword match
    if vendor:
        vendor_lower = vendor.lower()
        for keyword, dtype in _VENDOR_LOOKUP:
            if keyword in vendor_lower:
                device_type = dtype
                confidence = 0.8
                break

    # Pass 2: port-based classification (refine or override)
    port_type = _classify_by_ports(ports)
    if port_type:
        if device_type is None:
            device_type = port_type
            confidence = 0.6
        elif device_type == "workstation" and port_type == "server":
            device_type = "server"
            confidence = 0.7
        elif device_type == port_type:
            confidence = 0.9  # vendor + ports agree

    if device_type is None:
        device_type = "unknown"

    return {
        "device_type": device_type,
        "label": DEVICE_TYPE_LABELS.get(device_type, "Unknown"),
        "confidence": confidence,
    }
