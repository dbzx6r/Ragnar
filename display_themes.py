"""
display_themes.py — E-ink display theme definitions for Ragnar.

Each theme controls the complete visual rendering of PAGE_MAIN on the e-ink display:
  - title:            text shown in PAGE_MAIN header
  - page_titles:      titles for sub-pages (network, vuln, discovered, advanced, traffic)
  - corner_char:      character drawn at top corners of PAGE_MAIN border (None = skip)
  - status_labels:    maps orchestrator status keys to themed display strings
  - comments:         themed ragnarsays phrase pool keyed by orchestrator status
  - render_main_page: callable(loop, draw, image, sx, sy, ys) — renders full PAGE_MAIN

Viking theme preserves the original BMP-based layout exactly.
All other themes render entirely with PIL (no BMP file dependencies for mascots/icons).
"""

import math
import random
import time
from PIL import ImageDraw


def _get_anim_frame(n_frames=4, fps=1.5):
    """Return current animation frame index based on wall clock."""
    return int(time.time() * fps) % n_frames


def _status_class(status):
    """Classify orchestrator status into idle/scanning/attacking for animation intensity."""
    if status in ("IDLE", "LogStandalone", "LogStandalone2"):
        return "idle"
    if status in ("NetworkScanner", "NmapVulnScanner"):
        return "scanning"
    return "attacking"


# ---------------------------------------------------------------------------
# Shared header/footer helpers (used by all themes)
# ---------------------------------------------------------------------------

def _draw_header(loop, draw, image, sx, sy, theme_title):
    """Draw the header bar: title, wifi/AP indicator, PAN/USB icons, battery, portal."""
    sd = loop.shared_data
    pisugar_avail = getattr(loop, '_pisugar_available', False)
    ps = getattr(loop, '_ps', None)

    if pisugar_avail:
        draw.text((int(40 * sx), int(6 * sy)), theme_title, font=sd.font_viking_sm, fill=0)
    else:
        draw.text((int(37 * sx), int(5 * sy)), theme_title, font=sd.font_viking, fill=0)

    draw.text((int(110 * sx), int(170 * sy)), loop.manual_mode_txt, font=sd.font_arial14, fill=0)

    if getattr(sd, 'ap_mode_active', False):
        ap_text = "AP"
        if getattr(sd, 'ap_client_count', 0) > 0:
            ap_text = f"AP:{sd.ap_client_count}"
        draw.text((int(3 * sx), int(3 * sy)), ap_text, font=sd.font_arial9, fill=0)
    elif sd.wifi_connected:
        loop.render_wifi_wave_indicator(image, draw)

    if getattr(sd, 'pan_connected', False):
        image.paste(sd.connected, (int(104 * sx), int(3 * sy)))
    if getattr(sd, 'usb_active', False):
        image.paste(sd.usb, (int(90 * sx), int(4 * sy)))
    if (getattr(sd, 'captive_portal_detected', False)
            and not getattr(sd, 'captive_portal_authenticated', False)):
        draw.text((int(3 * sx), int(14 * sy)), "PORTAL", font=sd.font_arial9, fill=0)

    if pisugar_avail and ps:
        try:
            bat_level = ps.get_battery_level()
            if bat_level is not None:
                bat_level = int(round(bat_level))
                charging = ps.is_charging()
                bat_text = f"{bat_level}%+" if charging else f"{bat_level}%"
                bbox = sd.font_arial9.getbbox(bat_text)
                text_w = bbox[2] - bbox[0]
                draw.text((sd.width - text_w - 1, int(10 * sy)), bat_text, font=sd.font_arial9, fill=0)
        except Exception:
            pass


def _draw_borders_dividers(draw, sx, sy, ys, sd):
    """Draw outer border + 3 horizontal dividers."""
    draw.rectangle((1, 1, sd.width - 1, sd.height - 1), outline=0)
    draw.line((1, int(20 * sy), sd.width - 1, int(20 * sy)), fill=0)
    draw.line((1, int(59 * sy * ys), sd.width - 1, int(59 * sy * ys)), fill=0)
    draw.line((1, int(87 * sy * ys), sd.width - 1, int(87 * sy * ys)), fill=0)


def _draw_comment_lines(draw, sx, sy, ys, sd):
    """Draw the ragnarsays comment text block below the status divider."""
    lines = sd.wrap_text(sd.ragnarsays, sd.font_arialbold, sd.width - 4)
    y_text = int(90 * sy * ys)
    for line in lines:
        draw.text((int(4 * sx), y_text), line, font=sd.font_arialbold, fill=0)
        y_text += (sd.font_arialbold.getbbox(line)[3] - sd.font_arialbold.getbbox(line)[1]) + 3


def _draw_stat_label_value(draw, x, y, label, value, font):
    """Draw a themed stat as two stacked lines: label (top) + value (bottom)."""
    draw.text((x, y), label, font=font, fill=0)
    draw.text((x, y + 8), value, font=font, fill=0)


def _draw_corner_chars(draw, sd, corner_char, font):
    """Draw corner decoration characters inside the border."""
    if corner_char:
        draw.text((3, 3), corner_char, font=font, fill=0)
        draw.text((sd.width - 9, 3), corner_char, font=font, fill=0)


# ---------------------------------------------------------------------------
# Viking theme render (preserves original BMP-based logic)
# ---------------------------------------------------------------------------

def _render_viking_main(loop, draw, image, sx, sy, ys):
    """Viking theme: exact original PAGE_MAIN rendering (BMP sprites + font_viking)."""
    sd = loop.shared_data
    _draw_header(loop, draw, image, sx, sy, "RAGNAR")

    # Stats row 1 (icons: target, port, vuln)
    stats = [
        (sd.target,   (int(8 * sx),   int(22 * sy)), (int(28 * sx),  int(22 * sy)),  str(sd.targetnbr)),
        (sd.port,     (int(47 * sx),  int(22 * sy)), (int(67 * sx),  int(22 * sy)),  str(sd.portnbr)),
        (sd.vuln,     (int(86 * sx),  int(22 * sy)), (int(106 * sx), int(22 * sy)),  str(sd.vulnnbr)),
        (sd.cred,     (int(8 * sx),   int(41 * sy)), (int(28 * sx),  int(41 * sy)),  str(sd.crednbr)),
        (sd.zombie,   (int(47 * sx),  int(41 * sy)), (int(67 * sx),  int(41 * sy)),  str(sd.zombiesnbr)),
        (sd.data,     (int(86 * sx),  int(41 * sy)), (int(106 * sx), int(41 * sy)),  str(sd.datanbr)),
        (sd.money,    (int(3 * sx),   int(172 * sy)),(int(3 * sx),   int(192 * sy)), str(sd.coinnbr)),
        (sd.level,    (int(2 * sx),   int(217 * sy)),(int(4 * sx),   int(237 * sy)), str(sd.levelnbr)),
        (sd.networkkb,(int(102 * sx), int(190 * sy)),(int(102 * sx), int(208 * sy)), str(sd.networkkbnbr)),
        (sd.attacks,  (int(100 * sx), int(218 * sy)),(int(102 * sx), int(237 * sy)), str(sd.attacksnbr)),
    ]
    for img, img_pos, text_pos, text in stats:
        image.paste(img, img_pos)
        draw.text(text_pos, text, font=sd.font_arial9, fill=0)

    # Status zone
    sd.update_ragnarstatus()
    status_img = sd.ragnarstatusimage
    if sd.config.get('incognito_mode_enabled', False):
        status_img = loop._apply_incognito_mask(status_img)
    image.paste(status_img, (int(3 * sx), int(60 * sy * ys)))
    draw.text((int(35 * sx), int(65 * sy * ys)), sd.ragnarstatustext, font=sd.font_arial9, fill=0)
    draw.text((int(35 * sx), int(75 * sy * ys)), sd.ragnarstatustext2, font=sd.font_arial9, fill=0)

    # Frise ribbon
    if ys == 1.0:
        frise_x, frise_y = loop.get_frise_position()
        image.paste(sd.frise, (frise_x, frise_y))

    _draw_borders_dividers(draw, sx, sy, ys, sd)
    _draw_comment_lines(draw, sx, sy, ys, sd)

    # Main viking sprite
    if loop.main_image is not None:
        main_img = loop.main_image
        if sd.config.get('incognito_mode_enabled', False):
            main_img = loop._apply_incognito_mask(main_img)
        image.paste(main_img, (sd.x_center1, sd.y_bottom1))


# ---------------------------------------------------------------------------
# Penguin theme helpers
# ---------------------------------------------------------------------------

def _draw_penguin_large(draw, cx, cy, scale=1):
    """Draw a large PIL penguin centered at (cx, cy). scale=1 → ~55px tall."""
    s = scale
    # Body (black rectangle + ellipse)
    draw.ellipse([cx - int(15*s), cy - int(25*s), cx + int(15*s), cy + int(30*s)], fill=0)
    # White belly
    draw.ellipse([cx - int(10*s), cy - int(18*s), cx + int(10*s), cy + int(24*s)], fill=255)
    # Head
    draw.ellipse([cx - int(12*s), cy - int(40*s), cx + int(12*s), cy - int(18*s)], fill=0)
    # Eyes
    draw.ellipse([cx - int(6*s), cy - int(36*s), cx - int(3*s), cy - int(33*s)], fill=255)
    draw.ellipse([cx + int(3*s), cy - int(36*s), cx + int(6*s), cy - int(33*s)], fill=255)
    draw.point((cx - int(5*s), cy - int(35*s)), fill=0)
    draw.point((cx + int(4*s), cy - int(35*s)), fill=0)
    # Beak (inverted triangle)
    draw.polygon([
        (cx, cy - int(28*s)),
        (cx - int(4*s), cy - int(24*s)),
        (cx + int(4*s), cy - int(24*s)),
    ], fill=0)
    # Wings
    draw.polygon([
        (cx - int(15*s), cy - int(14*s)),
        (cx - int(24*s), cy + int(5*s)),
        (cx - int(15*s), cy + int(10*s)),
    ], fill=0)
    draw.polygon([
        (cx + int(15*s), cy - int(14*s)),
        (cx + int(24*s), cy + int(5*s)),
        (cx + int(15*s), cy + int(10*s)),
    ], fill=0)
    # Feet
    draw.line([(cx - int(8*s), cy + int(30*s)), (cx - int(14*s), cy + int(36*s))], fill=0, width=2)
    draw.line([(cx - int(8*s), cy + int(30*s)), (cx - int(2*s), cy + int(36*s))], fill=0, width=2)
    draw.line([(cx + int(8*s), cy + int(30*s)), (cx + int(2*s), cy + int(36*s))], fill=0, width=2)
    draw.line([(cx + int(8*s), cy + int(30*s)), (cx + int(14*s), cy + int(36*s))], fill=0, width=2)


def _draw_penguin_small(draw, x, y):
    """Draw a small ~20px penguin at (x,y) top-left. Used in status zone."""
    cx, cy = x + 10, y + 12
    draw.ellipse([cx-7, cy-4, cx+7, cy+10], fill=0)
    draw.ellipse([cx-5, cy-1, cx+5, cy+8], fill=255)
    draw.ellipse([cx-6, cy-14, cx+6, cy-3], fill=0)
    draw.point((cx-3, cy-11), fill=255)
    draw.point((cx+2, cy-11), fill=255)
    draw.polygon([(cx, cy-6), (cx-2, cy-4), (cx+2, cy-4)], fill=0)
    draw.line([(cx-3, cy+10), (cx-6, cy+14)], fill=0, width=1)
    draw.line([(cx+3, cy+10), (cx+6, cy+14)], fill=0, width=1)


def _draw_snow_scene(draw, zone_x, zone_y, zone_w, zone_h, status, frame):
    """Animated snow scene for penguin main zone.

    Draws a snowdrift hill at bottom + falling snowflakes that shift per frame.
    Flake count and speed depend on status class.
    """
    sc = _status_class(status)
    n_flakes = {"idle": 10, "scanning": 16, "attacking": 24}[sc]
    # Snowdrift hill at bottom: two overlapping filled ellipses
    bx = zone_x + zone_w // 2
    by = zone_y + zone_h - 5
    draw.ellipse([bx - 28, by - 14, bx + 28, by + 10], fill=255, outline=0)
    draw.ellipse([bx - 18, by - 20, bx + 18, by + 8], fill=255, outline=0)
    # Draw snowflakes using seeded RNG shifted by frame
    rng = random.Random(frame * 97 + 11)
    for _ in range(n_flakes):
        fx = rng.randint(zone_x + 2, zone_x + zone_w - 4)
        fy = rng.randint(zone_y + 2, zone_y + zone_h - 18)
        # diagonal offset for blizzard effect
        if sc == "attacking":
            fx = min(zone_x + zone_w - 4, fx + frame * 3)
        arm = 3 if sc == "idle" else 4
        draw.line([(fx - arm, fy), (fx + arm, fy)], fill=0, width=1)
        draw.line([(fx, fy - arm), (fx, fy + arm)], fill=0, width=1)
        if sc != "idle":
            draw.line([(fx - arm + 1, fy - arm + 1), (fx + arm - 1, fy + arm - 1)], fill=0, width=1)
            draw.line([(fx + arm - 1, fy - arm + 1), (fx - arm + 1, fy + arm - 1)], fill=0, width=1)



    """Draw a dotted ice-crystal decorative band (replaces frise for penguin theme)."""
    if ys != 1.0:
        return
    y = sd.height - 85
    for x in range(3, sd.width - 3, 5):
        draw.point((x, y), fill=0)
        draw.point((x, y - 1), fill=0)
    # Snowflake accents every 15px
    for x in range(8, sd.width - 8, 15):
        draw.line([(x - 3, y - 4), (x + 3, y - 4)], fill=0, width=1)
        draw.line([(x, y - 7), (x, y - 1)], fill=0, width=1)
        draw.line([(x - 2, y - 6), (x + 2, y - 2)], fill=0, width=1)
        draw.line([(x + 2, y - 6), (x - 2, y - 2)], fill=0, width=1)


def _render_penguin_main(loop, draw, image, sx, sy, ys):
    """Penguin / TUXNET theme: full PIL-rendered e-ink layout."""
    sd = loop.shared_data
    font = sd.font_arial9
    _draw_header(loop, draw, image, sx, sy, "TUXNET")

    # Stats row 1: Penguins / Cracks / Fish
    row1 = [
        ("Pngs", int(8*sx),  int(22*sy), str(sd.targetnbr)),
        ("Crak", int(47*sx), int(22*sy), str(sd.portnbr)),
        ("Fish", int(86*sx), int(22*sy), str(sd.vulnnbr)),
    ]
    row2 = [
        ("Eggs", int(8*sx),  int(40*sy), str(sd.crednbr)),
        ("Coln", int(47*sx), int(40*sy), str(sd.zombiesnbr)),
        ("Intl", int(86*sx), int(40*sy), str(sd.datanbr)),
    ]
    for label, x, y, val in row1 + row2:
        _draw_stat_label_value(draw, x, y, label, val, font)

    # Bottom corner stats
    draw.text((int(3*sx), int(174*sy*ys)), "Fish", font=font, fill=0)
    draw.text((int(3*sx), int(183*sy*ys)), str(sd.coinnbr), font=font, fill=0)
    draw.text((int(3*sx), int(219*sy*ys)), "Rank", font=font, fill=0)
    draw.text((int(3*sx), int(228*sy*ys)), str(sd.levelnbr), font=font, fill=0)
    draw.text((int(102*sx), int(192*sy*ys)), "Ice", font=font, fill=0)
    draw.text((int(102*sx), int(201*sy*ys)), str(sd.networkkbnbr), font=font, fill=0)
    draw.text((int(100*sx), int(220*sy*ys)), "Hunt", font=font, fill=0)
    draw.text((int(100*sx), int(229*sy*ys)), str(sd.attacksnbr), font=font, fill=0)

    # Status zone: small penguin + themed status text
    sd.update_ragnarstatus()
    status_map = {
        "IDLE": "WADDLING...", "NetworkScanner": "ICE SCAN",
        "NmapVulnScanner": "BLIZZARD!", "SSHBruteforce": "PECKING SSH",
        "FTPBruteforce": "PECKING FTP", "SMBBruteforce": "PECKING SMB",
        "RDPBruteforce": "PECKING RDP", "TelnetBruteforce": "PECKING TEL",
        "SQLBruteforce": "PECKING SQL", "StealFilesSSH": "FISH THEFT",
        "StealFilesFTP": "FISH HAUL", "StealFilesSMB": "FISH SMB",
        "StealFilesRDP": "FISH RDP", "StealFilesTelnet": "FISH TEL",
        "StealDataSQL": "SQL FISH", "LogStandalone": "WATCHING",
        "LogStandalone2": "STAKING OUT", "ZombifySSH": "ZOMBIFYING",
        "LynisPentestSSH": "DIVING DEEP",
    }
    status_text = status_map.get(sd.ragnarorch_status, sd.ragnarorch_status)
    _draw_penguin_small(draw, int(3*sx), int(60*sy*ys))
    draw.text((int(26*sx), int(62*sy*ys)), status_text, font=font, fill=0)
    draw.text((int(26*sx), int(72*sy*ys)), sd.ragnarstatustext2, font=font, fill=0)

    # Frise-style ice band
    _draw_ice_band(draw, sx, sy, ys, sd)
    _draw_borders_dividers(draw, sx, sy, ys, sd)
    _draw_corner_chars(draw, sd, "*", font)
    _draw_comment_lines(draw, sx, sy, ys, sd)

    # Snow scene in main zone (animated)
    sc = _status_class(sd.ragnarorch_status)
    fps_map = {"idle": 1.0, "scanning": 2.0, "attacking": 3.0}
    frame = _get_anim_frame(8, fps_map[sc])
    zone_x = int(sd.x_center1)
    zone_y = int(sd.y_bottom1)
    zone_w = 78
    zone_h = sd.height - zone_y - 2
    _draw_snow_scene(draw, zone_x, zone_y, zone_w, zone_h, sd.ragnarorch_status, frame)


# ---------------------------------------------------------------------------
# Car theme helpers
# ---------------------------------------------------------------------------

def _draw_car_large(draw, cx, cy):
    """Draw a large pixel car (side view) centered at (cx, cy). ~70px wide, 35px tall."""
    # Car body
    draw.rectangle([cx - 35, cy - 10, cx + 35, cy + 12], fill=0)
    # Cabin (raised roof)
    draw.polygon([
        (cx - 20, cy - 10),
        (cx - 30, cy - 24),
        (cx + 22, cy - 24),
        (cx + 35, cy - 10),
    ], fill=0)
    # Windows
    draw.rectangle([cx - 25, cy - 22, cx - 3, cy - 12], fill=255)
    draw.rectangle([cx + 1,  cy - 22, cx + 20, cy - 12], fill=255)
    # Windshield divider
    draw.line([(cx - 2, cy - 22), (cx - 2, cy - 12)], fill=0, width=1)
    # Headlight
    draw.rectangle([cx + 28, cy - 6, cx + 34, cy + 2], fill=255, outline=0)
    # Taillight
    draw.rectangle([cx - 34, cy - 6, cx - 28, cy + 2], fill=0)
    # Wheels
    draw.ellipse([cx - 28, cy + 7, cx - 12, cy + 23], fill=255, outline=0)
    draw.ellipse([cx - 23, cy + 12, cx - 17, cy + 18], fill=0)
    draw.ellipse([cx + 12, cy + 7, cx + 28, cy + 23], fill=255, outline=0)
    draw.ellipse([cx + 17, cy + 12, cx + 23, cy + 18], fill=0)
    # Door handle
    draw.rectangle([cx - 8, cy - 2, cx + 8, cy + 1], fill=255, outline=0)


def _draw_car_small(draw, x, y):
    """Draw a small ~20px car at (x, y). Used in status zone."""
    cx, cy = x + 13, y + 10
    draw.rectangle([cx - 12, cy - 2, cx + 12, cy + 5], fill=0)
    draw.polygon([(cx-8, cy-2), (cx-10, cy-8), (cx+8, cy-8), (cx+12, cy-2)], fill=0)
    draw.rectangle([cx-7, cy-7, cx-1, cy-3], fill=255)
    draw.rectangle([cx+1, cy-7, cx+7, cy-3], fill=255)
    draw.ellipse([cx-11, cy+3, cx-5, cy+9], fill=255, outline=0)
    draw.ellipse([cx+5,  cy+3, cx+11, cy+9], fill=255, outline=0)


def _draw_steering_wheel(draw, cx, cy, radius, angle_deg):
    """Draw a steering wheel centered at (cx,cy) with spokes rotated by angle_deg."""
    # Outer ring
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], outline=0, width=2)
    # 3 spokes at 0°, 120°, 240° offset by angle_deg
    hub_r = max(4, radius // 5)
    for spoke_off in (0, 120, 240):
        a = math.radians(angle_deg + spoke_off)
        x1 = cx + int(hub_r * math.cos(a))
        y1 = cy + int(hub_r * math.sin(a))
        x2 = cx + int((radius - 2) * math.cos(a))
        y2 = cy + int((radius - 2) * math.sin(a))
        draw.line([(x1, y1), (x2, y2)], fill=0, width=2)
    # Hub
    draw.ellipse([cx - hub_r, cy - hub_r, cx + hub_r, cy + hub_r], fill=0)


def _draw_traffic_cone(draw, x, y):
    """Draw a small traffic cone (triangle + base) top-left at (x,y), ~14px wide, 20px tall."""
    # Cone body
    draw.polygon([(x + 7, y), (x, y + 16), (x + 14, y + 16)], fill=0)
    # White stripe near top (drawn as lighter lines)
    draw.line([(x + 4, y + 6), (x + 10, y + 6)], fill=255, width=1)
    draw.line([(x + 3, y + 9), (x + 11, y + 9)], fill=255, width=1)
    # Base
    draw.rectangle([x - 2, y + 16, x + 16, y + 20], fill=0)



    """Draw a dashed road-line decoration band."""
    if ys != 1.0:
        return
    y = sd.height - 85
    draw.line([(2, y), (sd.width - 2, y)], fill=0, width=2)
    # Centre dashes
    for x in range(5, sd.width - 5, 10):
        draw.line([(x, y - 4), (x + 6, y - 4)], fill=0, width=1)


def _render_car_main(loop, draw, image, sx, sy, ys):
    """Car / ROADBOT theme."""
    sd = loop.shared_data
    font = sd.font_arial9
    _draw_header(loop, draw, image, sx, sy, "ROADBOT")

    row1 = [
        ("Cars", int(8*sx),  int(22*sy), str(sd.targetnbr)),
        ("Spd",  int(47*sx), int(22*sy), str(sd.portnbr)),
        ("Dent", int(86*sx), int(22*sy), str(sd.vulnnbr)),
    ]
    row2 = [
        ("Fuel", int(8*sx),  int(40*sy), str(sd.crednbr)),
        ("Gear", int(47*sx), int(40*sy), str(sd.zombiesnbr)),
        ("Rute", int(86*sx), int(40*sy), str(sd.datanbr)),
    ]
    for label, x, y, val in row1 + row2:
        _draw_stat_label_value(draw, x, y, label, val, font)

    draw.text((int(3*sx), int(174*sy*ys)), "Gold", font=font, fill=0)
    draw.text((int(3*sx), int(183*sy*ys)), str(sd.coinnbr), font=font, fill=0)
    draw.text((int(3*sx), int(219*sy*ys)), "Gear", font=font, fill=0)
    draw.text((int(3*sx), int(228*sy*ys)), str(sd.levelnbr), font=font, fill=0)
    draw.text((int(102*sx), int(192*sy*ys)), "KB", font=font, fill=0)
    draw.text((int(102*sx), int(201*sy*ys)), str(sd.networkkbnbr), font=font, fill=0)
    draw.text((int(100*sx), int(220*sy*ys)), "Runs", font=font, fill=0)
    draw.text((int(100*sx), int(229*sy*ys)), str(sd.attacksnbr), font=font, fill=0)

    sd.update_ragnarstatus()
    status_map = {
        "IDLE": "PARKED", "NetworkScanner": "ROAD SCAN",
        "NmapVulnScanner": "DENT CHECK", "SSHBruteforce": "SSH DRIFT",
        "FTPBruteforce": "FTP DRIFT", "SMBBruteforce": "SMB DRIFT",
        "RDPBruteforce": "RDP DRIFT", "TelnetBruteforce": "TEL DRIFT",
        "SQLBruteforce": "SQL DRIFT", "StealFilesSSH": "SSH HAUL",
        "StealFilesFTP": "FTP HAUL", "StealFilesSMB": "SMB HAUL",
        "StealFilesRDP": "RDP HAUL", "StealFilesTelnet": "TEL HAUL",
        "StealDataSQL": "SQL HAUL", "LogStandalone": "IDLING",
        "LogStandalone2": "CRUISING", "ZombifySSH": "HOT WIRE",
        "LynisPentestSSH": "FULL SEND",
    }
    status_text = status_map.get(sd.ragnarorch_status, sd.ragnarorch_status)
    _draw_car_small(draw, int(3*sx), int(60*sy*ys))
    draw.text((int(26*sx), int(62*sy*ys)), status_text, font=font, fill=0)
    draw.text((int(26*sx), int(72*sy*ys)), sd.ragnarstatustext2, font=font, fill=0)

    _draw_road_band(draw, sx, sy, ys, sd)
    _draw_borders_dividers(draw, sx, sy, ys, sd)
    _draw_corner_chars(draw, sd, "o", font)
    _draw_comment_lines(draw, sx, sy, ys, sd)

    # Steering wheel in main zone (animated by status)
    sc = _status_class(sd.ragnarorch_status)
    fps_map = {"idle": 0.5, "scanning": 1.5, "attacking": 3.0}
    max_angle_map = {"idle": 10, "scanning": 22, "attacking": 38}
    n_frames = 16
    frame = _get_anim_frame(n_frames, fps_map[sc])
    # Swing angle: triangle wave over frames
    half = n_frames // 2
    t = frame if frame < half else n_frames - frame
    angle = int(max_angle_map[sc] * (t / half)) - 90  # -90 puts top spoke pointing up
    cx = int(sd.x_center1 + 39)
    cy = int(sd.y_bottom1 + 33)
    _draw_steering_wheel(draw, cx, cy, 26, angle)
    # Traffic cone lower-right of the wheel
    _draw_traffic_cone(draw, cx + 22, cy + 18)


# ---------------------------------------------------------------------------
# Matrix theme helpers
# ---------------------------------------------------------------------------

MATRIX_CHARS = ['0', '1', 'N', 'I', 'L', '/', '\\', '|', '>', '<', '!', '?', '#']


def _draw_matrix_rain(draw, x, y, w, h, font, seed=42):
    """Draw a matrix digital-rain column block in zone (x,y)-(x+w,y+h)."""
    rng = random.Random(seed)
    col_w = 8
    for col_x in range(x, x + w, col_w):
        drop_len = rng.randint(4, 12)
        max_start = max(y, y + h - drop_len * 9)
        start_y = rng.randint(y, max_start)
        for i in range(drop_len):
            ch = rng.choice(MATRIX_CHARS)
            cy2 = start_y + i * 9
            if cy2 + 9 < y + h:
                # Leading char: bold (inverted look)
                if i == drop_len - 1:
                    draw.rectangle([col_x, cy2, col_x + 7, cy2 + 8], fill=0)
                    draw.text((col_x + 1, cy2), ch, font=font, fill=255)
                else:
                    draw.text((col_x + 1, cy2), ch, font=font, fill=0)


def _draw_matrix_status_icon(draw, x, y, font):
    """Small matrix icon for status zone: binary columns."""
    chars = ['1', '0', '1', '1', '0', '0', '1']
    for i, ch in enumerate(chars):
        draw.text((x + 1, y + i * 9), ch, font=font, fill=0)


def _draw_binary_band(draw, sx, sy, ys, sd):
    """Binary string decorative band."""
    if ys != 1.0:
        return
    y = sd.height - 85
    pattern = "10110010101001101"
    for i, ch in enumerate(pattern):
        x = 3 + i * 7
        if x < sd.width - 5:
            if ch == '1':
                draw.rectangle([x, y - 5, x + 5, y], fill=0)
            else:
                draw.rectangle([x, y - 5, x + 5, y], outline=0)


def _render_matrix_main(loop, draw, image, sx, sy, ys):
    """Matrix / [R4GN4R] theme."""
    sd = loop.shared_data
    font = sd.font_arial9
    _draw_header(loop, draw, image, sx, sy, "[R4GN4R]")

    # Stats: all bracketed labels
    row1 = [
        ("[TGT]", int(8*sx),  int(22*sy), str(sd.targetnbr)),
        ("[PRT]", int(47*sx), int(22*sy), str(sd.portnbr)),
        ("[VLN]", int(86*sx), int(22*sy), str(sd.vulnnbr)),
    ]
    row2 = [
        ("[CRD]", int(8*sx),  int(40*sy), str(sd.crednbr)),
        ("[ZMB]", int(47*sx), int(40*sy), str(sd.zombiesnbr)),
        ("[DAT]", int(86*sx), int(40*sy), str(sd.datanbr)),
    ]
    for label, x, y, val in row1 + row2:
        _draw_stat_label_value(draw, x, y, label, val, font)

    draw.text((int(3*sx), int(174*sy*ys)), "[AU]", font=font, fill=0)
    draw.text((int(3*sx), int(183*sy*ys)), str(sd.coinnbr), font=font, fill=0)
    draw.text((int(3*sx), int(219*sy*ys)), "[LV]", font=font, fill=0)
    draw.text((int(3*sx), int(228*sy*ys)), str(sd.levelnbr), font=font, fill=0)
    draw.text((int(102*sx), int(192*sy*ys)), "[KB]", font=font, fill=0)
    draw.text((int(102*sx), int(201*sy*ys)), str(sd.networkkbnbr), font=font, fill=0)
    draw.text((int(100*sx), int(220*sy*ys)), "[AT]", font=font, fill=0)
    draw.text((int(100*sx), int(229*sy*ys)), str(sd.attacksnbr), font=font, fill=0)

    sd.update_ragnarstatus()
    status_map = {
        "IDLE": "[IDLE]", "NetworkScanner": "[SCANNING]",
        "NmapVulnScanner": "[PROBING]", "SSHBruteforce": "[SSH PWN]",
        "FTPBruteforce": "[FTP PWN]", "SMBBruteforce": "[SMB PWN]",
        "RDPBruteforce": "[RDP PWN]", "TelnetBruteforce": "[TEL PWN]",
        "SQLBruteforce": "[SQL PWN]", "StealFilesSSH": "[EXFIL SSH]",
        "StealFilesFTP": "[EXFIL FTP]", "StealFilesSMB": "[EXFIL SMB]",
        "StealFilesRDP": "[EXFIL RDP]", "StealFilesTelnet": "[EXFIL TEL]",
        "StealDataSQL": "[EXFIL SQL]", "LogStandalone": "[LOGGING]",
        "LogStandalone2": "[DEEP LOG]", "ZombifySSH": "[ZOMBIFY]",
        "LynisPentestSSH": "[PENTEST]",
    }
    status_text = status_map.get(sd.ragnarorch_status, f"[{sd.ragnarorch_status}]")
    # Matrix-style status indicator: single binary column on left of status zone
    for row in range(3):
        ch = MATRIX_CHARS[row % len(MATRIX_CHARS)]
        draw.text((int(3 * sx), int((61 + row * 8) * sy * ys)), ch, font=font, fill=0)
    draw.text((int(26*sx), int(62*sy*ys)), status_text, font=font, fill=0)
    draw.text((int(26*sx), int(72*sy*ys)), sd.ragnarstatustext2, font=font, fill=0)

    _draw_binary_band(draw, sx, sy, ys, sd)
    _draw_borders_dividers(draw, sx, sy, ys, sd)
    _draw_corner_chars(draw, sd, "1", font)
    _draw_comment_lines(draw, sx, sy, ys, sd)

    # Large matrix rain block in main zone (time-based seed for animation)
    mx = sd.x_center1 + 2
    my = sd.y_bottom1 + 2
    _draw_matrix_rain(draw, mx, my, 74, 74, font, seed=int(time.time() * 2) % 100)


# ---------------------------------------------------------------------------
# Space theme helpers
# ---------------------------------------------------------------------------

def _draw_rocket_large(draw, cx, cy, frame=0):
    """Draw a large PIL rocket centered at (cx, cy). ~65px tall.
    frame 0=small flame, 1=medium, 2=large, 3=medium (loops for animation).
    """
    # Nose cone (triangle)
    draw.polygon([(cx, cy - 32), (cx - 11, cy - 6), (cx + 11, cy - 6)], fill=0)
    # Body
    draw.rectangle([cx - 11, cy - 8, cx + 11, cy + 20], fill=0)
    # Porthole
    draw.ellipse([cx - 6, cy - 3, cx + 6, cy + 9], fill=255, outline=0)
    draw.ellipse([cx - 3, cy, cx + 3, cy + 6], fill=0)
    # Left fin
    draw.polygon([(cx - 11, cy + 8), (cx - 20, cy + 22), (cx - 11, cy + 20)], fill=0)
    # Right fin
    draw.polygon([(cx + 11, cy + 8), (cx + 20, cy + 22), (cx + 11, cy + 20)], fill=0)
    # Bottom nozzle
    draw.rectangle([cx - 6, cy + 20, cx + 6, cy + 25], fill=0)
    # Animated flame: 3 sizes cycling by frame
    flame_ext = [8, 13, 20, 13][frame % 4]
    draw.polygon([(cx - 6, cy + 25), (cx, cy + 25 + flame_ext), (cx + 6, cy + 25)], fill=0)
    # Inner lighter flame
    inner_ext = max(2, flame_ext - 6)
    draw.polygon([(cx - 3, cy + 25), (cx, cy + 25 + inner_ext), (cx + 3, cy + 25)], fill=255)
    # Stars around
    for sx2, sy2 in [(-28, -25), (22, -18), (28, 5), (-24, 10), (18, 22)]:
        draw.point((cx + sx2, cy + sy2), fill=0)
        draw.point((cx + sx2 + 1, cy + sy2), fill=0)
        draw.point((cx + sx2, cy + sy2 + 1), fill=0)


def _draw_rocket_small(draw, x, y):
    """Small rocket ~18px for status zone."""
    cx, cy = x + 9, y + 11
    draw.polygon([(cx, cy - 10), (cx - 5, cy - 2), (cx + 5, cy - 2)], fill=0)
    draw.rectangle([cx - 5, cy - 3, cx + 5, cy + 7], fill=0)
    draw.ellipse([cx - 3, cy, cx + 3, cy + 5], fill=255, outline=0)
    draw.polygon([(cx - 5, cy + 3), (cx - 9, cy + 8), (cx - 5, cy + 7)], fill=0)
    draw.polygon([(cx + 5, cy + 3), (cx + 9, cy + 8), (cx + 5, cy + 7)], fill=0)
    draw.polygon([(cx - 3, cy + 7), (cx, cy + 13), (cx + 3, cy + 7)], fill=0)


def _draw_star_band(draw, sx, sy, ys, sd):
    """Star field decorative band."""
    if ys != 1.0:
        return
    y = sd.height - 85
    positions = [5, 13, 21, 30, 42, 55, 67, 80, 95, 108, 119]
    for x in positions:
        draw.point((x, y - 3), fill=0)
        draw.line([(x - 2, y - 3), (x + 2, y - 3)], fill=0, width=1)
        draw.line([(x, y - 5), (x, y - 1)], fill=0, width=1)


def _render_space_main(loop, draw, image, sx, sy, ys):
    """Space / STAR-NET theme."""
    sd = loop.shared_data
    font = sd.font_arial9
    _draw_header(loop, draw, image, sx, sy, "STAR-NET")

    row1 = [
        ("Plnt", int(8*sx),  int(22*sy), str(sd.targetnbr)),
        ("Sgnl", int(47*sx), int(22*sy), str(sd.portnbr)),
        ("Thrt", int(86*sx), int(22*sy), str(sd.vulnnbr)),
    ]
    row2 = [
        ("Life", int(8*sx),  int(40*sy), str(sd.crednbr)),
        ("Moon", int(47*sx), int(40*sy), str(sd.zombiesnbr)),
        ("Prbe", int(86*sx), int(40*sy), str(sd.datanbr)),
    ]
    for label, x, y, val in row1 + row2:
        _draw_stat_label_value(draw, x, y, label, val, font)

    draw.text((int(3*sx), int(174*sy*ys)), "Ore", font=font, fill=0)
    draw.text((int(3*sx), int(183*sy*ys)), str(sd.coinnbr), font=font, fill=0)
    draw.text((int(3*sx), int(219*sy*ys)), "Rank", font=font, fill=0)
    draw.text((int(3*sx), int(228*sy*ys)), str(sd.levelnbr), font=font, fill=0)
    draw.text((int(102*sx), int(192*sy*ys)), "KB", font=font, fill=0)
    draw.text((int(102*sx), int(201*sy*ys)), str(sd.networkkbnbr), font=font, fill=0)
    draw.text((int(100*sx), int(220*sy*ys)), "Warp", font=font, fill=0)
    draw.text((int(100*sx), int(229*sy*ys)), str(sd.attacksnbr), font=font, fill=0)

    sd.update_ragnarstatus()
    status_map = {
        "IDLE": "DRIFTING", "NetworkScanner": "STAR MAP",
        "NmapVulnScanner": "ASTEROID!", "SSHBruteforce": "SSH WARP",
        "FTPBruteforce": "FTP WARP", "SMBBruteforce": "SMB WARP",
        "RDPBruteforce": "RDP WARP", "TelnetBruteforce": "TEL WARP",
        "SQLBruteforce": "SQL WARP", "StealFilesSSH": "BEAM SSH",
        "StealFilesFTP": "BEAM FTP", "StealFilesSMB": "BEAM SMB",
        "StealFilesRDP": "BEAM RDP", "StealFilesTelnet": "BEAM TEL",
        "StealDataSQL": "BEAM SQL", "LogStandalone": "ORBIT",
        "LogStandalone2": "DEEP ORBIT", "ZombifySSH": "COLONIZE",
        "LynisPentestSSH": "PROBE",
    }
    status_text = status_map.get(sd.ragnarorch_status, sd.ragnarorch_status)
    _draw_rocket_small(draw, int(3*sx), int(60*sy*ys))
    draw.text((int(26*sx), int(62*sy*ys)), status_text, font=font, fill=0)
    draw.text((int(26*sx), int(72*sy*ys)), sd.ragnarstatustext2, font=font, fill=0)

    _draw_star_band(draw, sx, sy, ys, sd)
    _draw_borders_dividers(draw, sx, sy, ys, sd)
    _draw_corner_chars(draw, sd, ".", font)
    _draw_comment_lines(draw, sx, sy, ys, sd)

    # Animated rocket in main zone
    sc = _status_class(sd.ragnarorch_status)
    fps_map = {"idle": 0.8, "scanning": 1.5, "attacking": 2.5}
    frame = _get_anim_frame(4, fps_map[sc])
    cx = int((sd.x_center1 + sd.x_center1 + 78) // 2)
    cy = int(sd.y_bottom1 + 30)
    _draw_rocket_large(draw, cx, cy, frame=frame)


# ---------------------------------------------------------------------------
# Ghost theme helpers
# ---------------------------------------------------------------------------

def _draw_ghost_large(draw, cx, cy, frame=0, attacking=False):
    """Draw a Snapchat-style ghost centered at (cx, cy). ~60px tall.

    White rounded oval body, 4 scalloped bottom bumps, solid dot eyes, gentle smile.
    Bobs ±3px by frame. Attacking: angry slanted brows.
    """
    # Bob offset
    bob = 3 if (frame % 2 == 1) else 0
    cy = cy + bob

    # Body: filled white oval with black outline
    bw, bh = 38, 44
    draw.ellipse([cx - bw, cy - bh, cx + bw, cy + 10], fill=255, outline=0, width=2)

    # Cover bottom of ellipse to attach scallops cleanly
    draw.rectangle([cx - bw, cy, cx + bw, cy + 12], fill=255)
    draw.line([(cx - bw, cy), (cx + bw, cy)], fill=0, width=2)  # waist line

    # 4 scalloped bumps at bottom (white semi-circles over black baseline)
    bump_r = 9
    bump_y_top = cy + 4
    bump_centers_x = [cx - 27, cx - 9, cx + 9, cx + 27]
    # Black baseline rectangle to give scallops their background
    draw.rectangle([cx - bw - 1, bump_y_top, cx + bw + 1, cy + 14], fill=0)
    for bcx in bump_centers_x:
        draw.ellipse([bcx - bump_r, bump_y_top, bcx + bump_r, bump_y_top + bump_r * 2],
                     fill=255, outline=0, width=2)
    # Redraw outline arcs to clean up
    draw.line([(cx - bw, bump_y_top), (cx - bw, cy)], fill=0, width=2)
    draw.line([(cx + bw, bump_y_top), (cx + bw, cy)], fill=0, width=2)

    # Solid dot eyes (Snapchat style — no whites, just dark dots)
    eye_y = cy - bh + 22
    draw.ellipse([cx - 16, eye_y - 7, cx - 6, eye_y + 3], fill=0)
    draw.ellipse([cx + 6,  eye_y - 7, cx + 16, eye_y + 3], fill=0)
    # Tiny white glint on each eye
    draw.point((cx - 13, eye_y - 5), fill=255)
    draw.point((cx + 9, eye_y - 5), fill=255)

    # Angry brows when attacking
    if attacking:
        draw.line([(cx - 17, eye_y - 11), (cx - 5, eye_y - 8)], fill=0, width=2)
        draw.line([(cx + 5, eye_y - 8), (cx + 17, eye_y - 11)], fill=0, width=2)

    # Gentle smile arc (3 segments)
    smile_y = cy - bh + 35
    draw.arc([cx - 12, smile_y - 4, cx + 12, smile_y + 4], start=10, end=170, fill=0, width=2)


def _draw_ghost_small(draw, x, y):
    """Small Snapchat-style ghost ~20px for status zone."""
    cx, cy = x + 10, y + 11
    # Body
    draw.ellipse([cx - 8, cy - 12, cx + 8, cy + 2], fill=255, outline=0)
    draw.rectangle([cx - 8, cy - 2, cx + 8, cy + 5], fill=255)
    draw.line([(cx - 8, cy - 2), (cx + 8, cy - 2)], fill=0, width=1)
    # Scallop bumps (2 bumps for small size)
    for bx in (cx - 4, cx + 4):
        draw.ellipse([bx - 4, cy + 2, bx + 4, cy + 10], fill=255, outline=0)
    draw.rectangle([cx - 8, cy + 2, cx + 8, cy + 6], fill=0)
    for bx in (cx - 4, cx + 4):
        draw.ellipse([bx - 4, cy + 2, bx + 4, cy + 10], fill=255, outline=0)
    # Eyes
    draw.ellipse([cx - 6, cy - 9, cx - 2, cy - 5], fill=0)
    draw.ellipse([cx + 2, cy - 9, cx + 6, cy - 5], fill=0)




def _draw_wavy_band(draw, sx, sy, ys, sd):
    """Wavy squiggle decorative band."""
    if ys != 1.0:
        return
    y = sd.height - 85
    pts = []
    for x in range(2, sd.width - 2, 2):
        offset = 3 if (x // 6) % 2 == 0 else 0
        pts.append((x, y - offset))
    if len(pts) > 1:
        draw.line(pts, fill=0, width=1)


def _render_ghost_main(loop, draw, image, sx, sy, ys):
    """Ghost / B00NET theme."""
    sd = loop.shared_data
    font = sd.font_arial9
    _draw_header(loop, draw, image, sx, sy, "B00NET")

    row1 = [
        ("Sprt", int(8*sx),  int(22*sy), str(sd.targetnbr)),
        ("Hant", int(47*sx), int(22*sy), str(sd.portnbr)),
        ("Curs", int(86*sx), int(22*sy), str(sd.vulnnbr)),
    ]
    row2 = [
        ("Skll", int(8*sx),  int(40*sy), str(sd.crednbr)),
        ("Eyes", int(47*sx), int(40*sy), str(sd.zombiesnbr)),
        ("Bats", int(86*sx), int(40*sy), str(sd.datanbr)),
    ]
    for label, x, y, val in row1 + row2:
        _draw_stat_label_value(draw, x, y, label, val, font)

    draw.text((int(3*sx), int(174*sy*ys)), "Gld", font=font, fill=0)
    draw.text((int(3*sx), int(183*sy*ys)), str(sd.coinnbr), font=font, fill=0)
    draw.text((int(3*sx), int(219*sy*ys)), "Rank", font=font, fill=0)
    draw.text((int(3*sx), int(228*sy*ys)), str(sd.levelnbr), font=font, fill=0)
    draw.text((int(102*sx), int(192*sy*ys)), "KB", font=font, fill=0)
    draw.text((int(102*sx), int(201*sy*ys)), str(sd.networkkbnbr), font=font, fill=0)
    draw.text((int(100*sx), int(220*sy*ys)), "Boos", font=font, fill=0)
    draw.text((int(100*sx), int(229*sy*ys)), str(sd.attacksnbr), font=font, fill=0)

    sd.update_ragnarstatus()
    status_map = {
        "IDLE": "HAUNTING", "NetworkScanner": "SPIRIT SCAN",
        "NmapVulnScanner": "POSSESSING!", "SSHBruteforce": "BOO SSH",
        "FTPBruteforce": "BOO FTP", "SMBBruteforce": "BOO SMB",
        "RDPBruteforce": "BOO RDP", "TelnetBruteforce": "BOO TEL",
        "SQLBruteforce": "BOO SQL", "StealFilesSSH": "SOUL SSH",
        "StealFilesFTP": "SOUL FTP", "StealFilesSMB": "SOUL SMB",
        "StealFilesRDP": "SOUL RDP", "StealFilesTelnet": "SOUL TEL",
        "StealDataSQL": "SOUL SQL", "LogStandalone": "LURKING",
        "LogStandalone2": "DEEP LURK", "ZombifySSH": "ZOMBIFY",
        "LynisPentestSSH": "CREEPING",
    }
    status_text = status_map.get(sd.ragnarorch_status, sd.ragnarorch_status)
    _draw_ghost_small(draw, int(3*sx), int(60*sy*ys))
    draw.text((int(26*sx), int(62*sy*ys)), status_text, font=font, fill=0)
    draw.text((int(26*sx), int(72*sy*ys)), sd.ragnarstatustext2, font=font, fill=0)

    _draw_wavy_band(draw, sx, sy, ys, sd)
    _draw_borders_dividers(draw, sx, sy, ys, sd)
    _draw_corner_chars(draw, sd, "~", font)
    _draw_comment_lines(draw, sx, sy, ys, sd)

    # Animated Snapchat-style ghost in main zone
    sc = _status_class(sd.ragnarorch_status)
    fps_map = {"idle": 1.0, "scanning": 1.5, "attacking": 2.5}
    frame = _get_anim_frame(4, fps_map[sc])
    attacking = (sc == "attacking")
    cx = int((sd.x_center1 + sd.x_center1 + 78) // 2)
    cy = int(sd.y_bottom1 + 33)
    _draw_ghost_large(draw, cx, cy, frame=frame, attacking=attacking)


# ---------------------------------------------------------------------------
# Themed comment pools (ragnarsays phrases per orchestrator status)
# ---------------------------------------------------------------------------

_PENGUIN_COMMENTS = {
    "IDLE":             ["Sliding on ice...", "Waiting for fish...", "Just waddling around...", "Preening feathers..."],
    "NetworkScanner":   ["Mapping the ice sheet...", "Scanning the glacier...", "Tracking penguin colonies...", "Ice recon in progress..."],
    "NmapVulnScanner":  ["Checking for cracks in the ice...", "Blizzard of port data...", "Probing deep ice...", "Ice weakness detected!"],
    "SSHBruteforce":    ["Pecking at SSH...", "Flipper assault on SSH...", "Cracking the ice door..."],
    "FTPBruteforce":    ["Pecking at FTP...", "Waddling through FTP creds..."],
    "SMBBruteforce":    ["Pecking at SMB...", "Flipper on the SMB server..."],
    "RDPBruteforce":    ["RDP under the flippers...", "Pecking at the remote window..."],
    "TelnetBruteforce": ["Old ice, easy pickings...", "Telnet is so last century..."],
    "SQLBruteforce":    ["Probing the frozen database...", "SQL ice crack attempt..."],
    "StealFilesSSH":    ["Fish heist via SSH!", "Stealing from the ice cave...", "Carrying fish back to colony..."],
    "StealFilesFTP":    ["FTP fish haul in progress...", "Loading up on FTP data..."],
    "StealFilesSMB":    ["SMB fish heist!", "Waddling out with the data..."],
    "StealFilesRDP":    ["RDP data catch...", "Remote fish theft!"],
    "StealFilesTelnet": ["Telnet fish grab...", "Ancient protocol, easy loot..."],
    "StealDataSQL":     ["SQL data catch!", "Diving deep into the database..."],
    "LogStandalone":    ["Watching from the ice shelf...", "Logging quietly..."],
    "LogStandalone2":   ["Deep colony surveillance...", "Long-haul ice watch..."],
    "ZombifySSH":       ["Adding to the colony...", "Creating a penguin zombie army..."],
    "LynisPentestSSH":  ["Full deep-dive pentest!", "Emperor-level assessment..."],
}

_CAR_COMMENTS = {
    "IDLE":             ["Engine idling...", "Waiting at the red light...", "Full tank, ready to go...", "Radio on, parked..."],
    "NetworkScanner":   ["Scouting the road ahead...", "GPS mapping the network...", "Recon drive in progress...", "Checking all on-ramps..."],
    "NmapVulnScanner":  ["Running a full diagnostic...", "Checking for dents and cracks...", "Engine fault scan active...", "Road hazard detected!"],
    "SSHBruteforce":    ["Brute-forcing the ignition...", "Hammering the SSH pedal...", "Full throttle on SSH..."],
    "FTPBruteforce":    ["FTP hit and run...", "Flooring it on FTP..."],
    "SMBBruteforce":    ["SMB off-road attack...", "Drifting through SMB..."],
    "RDPBruteforce":    ["Remote control hijack...", "Hot-wiring the RDP..."],
    "TelnetBruteforce": ["Old banger, easy start...", "Telnet is low-hanging fruit..."],
    "SQLBruteforce":    ["SQL database drag race...", "Crashing the SQL gate..."],
    "StealFilesSSH":    ["SSH data haul in progress!", "Loading up the trunk via SSH...", "Speeding away with the goods..."],
    "StealFilesFTP":    ["FTP cargo loaded...", "Driving off with FTP files..."],
    "StealFilesSMB":    ["SMB smash and grab!", "Tires squealing on SMB..."],
    "StealFilesRDP":    ["Remote data pickup...", "RDP drive-by complete..."],
    "StealFilesTelnet": ["Telnet drive-by...", "Old road, easy loot..."],
    "StealDataSQL":     ["SQL database heist!", "Trunk full of SQL data..."],
    "LogStandalone":    ["Parked and watching...", "Surveillance from the lot..."],
    "LogStandalone2":   ["Long-haul surveillance...", "Miles of log data..."],
    "ZombifySSH":       ["Fleet expansion in progress...", "Adding another car to the convoy..."],
    "LynisPentestSSH":  ["Full track inspection!", "Pedal to the metal pentest..."],
}

_MATRIX_COMMENTS = {
    "IDLE":             ["AWAITING INPUT...", "> SYSTEM READY", "01001001 01000100 01001100 01000101", "THE MATRIX HAS YOU..."],
    "NetworkScanner":   ["SCANNING GRID...", "> NODES FOUND", "JACKING INTO THE MATRIX...", "NETWORK TOPOLOGY MAPPED"],
    "NmapVulnScanner":  ["BUFFER OVERFLOW DETECTED", "> PROBING PORTS", "VULNERABILITY MATRIX ACTIVE", "CRACK THE SYSTEM..."],
    "SSHBruteforce":    ["> SSH BRUTE FORCE", "DICTIONARY ATTACK INITIATED", "THE DOOR IS CRACKING..."],
    "FTPBruteforce":    ["> FTP BRUTEFORCE", "CREDENTIAL STORM..."],
    "SMBBruteforce":    ["> SMB BRUTEFORCE", "LATERAL MOVE INITIATED..."],
    "RDPBruteforce":    ["> RDP BRUTEFORCE", "REMOTE SHELL INCOMING..."],
    "TelnetBruteforce": ["> TELNET BRUTEFORCE", "LEGACY PROTOCOL EXPLOITED"],
    "SQLBruteforce":    ["> SQL INJECTION", "DATABASE ACCESS IMMINENT"],
    "StealFilesSSH":    ["> EXFIL VIA SSH", "DATA EXTRACTED FROM MATRIX", "UPLOAD TO ZION COMPLETE"],
    "StealFilesFTP":    ["> EXFIL VIA FTP", "FILES EXTRACTED..."],
    "StealFilesSMB":    ["> EXFIL VIA SMB", "LATERAL DATA MOVE..."],
    "StealFilesRDP":    ["> EXFIL VIA RDP", "REMOTE DATA GRAB..."],
    "StealFilesTelnet": ["> EXFIL VIA TELNET", "ANCIENT PROTOCOL EXPLOITED"],
    "StealDataSQL":     ["> SQL DATA DUMP", "DATABASE CONTENTS EXFILTRATED"],
    "LogStandalone":    ["MONITORING FEED...", "> PASSIVE RECON"],
    "LogStandalone2":   ["DEEP PACKET INSPECTION...", "> FULL MATRIX AUDIT"],
    "ZombifySSH":       ["> ZOMBIE CREATED", "ADDING NODE TO BOTNET..."],
    "LynisPentestSSH":  ["> FULL PENTEST", "RED TEAM ASSESSMENT ACTIVE"],
}

_SPACE_COMMENTS = {
    "IDLE":             ["Orbiting in silence...", "Awaiting mission briefing...", "Drifting through the cosmos...", "Star charts loading..."],
    "NetworkScanner":   ["Mapping star systems...", "Stellar reconnaissance active...", "Deep space network scan...", "Charting unknown planets..."],
    "NmapVulnScanner":  ["Asteroid field detected!", "Scanning for hull breaches...", "Threat analysis: hostile system...", "Weapons lock confirmed..."],
    "SSHBruteforce":    ["SSH landing sequence initiated...", "Docking clamps on SSH...", "Boarding via SSH airlock..."],
    "FTPBruteforce":    ["FTP tractor beam active...", "Pulling in FTP signals..."],
    "SMBBruteforce":    ["SMB warp gate breached...", "Jumping to SMB coordinates..."],
    "RDPBruteforce":    ["Remote warp drive initiated...", "Capturing RDP beacon..."],
    "TelnetBruteforce": ["Ancient signal detected...", "Telnet: a relic of the old universe..."],
    "SQLBruteforce":    ["SQL asteroid mining...", "Drilling into the database core..."],
    "StealFilesSSH":    ["Beaming up files via SSH!", "SSH teleportation complete...", "Cargo bay full!"],
    "StealFilesFTP":    ["FTP data beamed aboard...", "Cargo: FTP files acquired..."],
    "StealFilesSMB":    ["SMB cargo secured...", "Warp speed with the data..."],
    "StealFilesRDP":    ["Remote cargo lift active...", "Data pulled from remote orbit..."],
    "StealFilesTelnet": ["Telnet signal captured...", "Old frequency, easy intercept..."],
    "StealDataSQL":     ["Database core extracted!", "SQL asteroid mined successfully..."],
    "LogStandalone":    ["Monitoring deep space...", "Observing from orbit..."],
    "LogStandalone2":   ["Long-range sensor sweep...", "Full spectrum analysis..."],
    "ZombifySSH":       ["Adding to the fleet...", "New drone ship activated..."],
    "LynisPentestSSH":  ["Full system sweep!", "Mission: complete penetration..."],
}

_GHOST_COMMENTS = {
    "IDLE":             ["Floating in silence...", "Waiting to haunt...", "The shadows are mine...", "BOO. Just practicing..."],
    "NetworkScanner":   ["Haunting the network...", "Ghost scan in progress...", "Spirits map the network...", "The network fears me..."],
    "NmapVulnScanner":  ["Curse detected on port...", "Possessing the vulnerability...", "The spirits are angry...", "Dark magic revealed!"],
    "SSHBruteforce":    ["Possessing the SSH daemon...", "Ghost key insertion...", "The door has no lock for spirits..."],
    "FTPBruteforce":    ["FTP spirits summoned...", "Haunting the file server..."],
    "SMBBruteforce":    ["SMB poltergeist active...", "Throwing files around SMB..."],
    "RDPBruteforce":    ["Remote possession attempt...", "The cursor moves on its own..."],
    "TelnetBruteforce": ["Ancient ghost protocol...", "Telnet: haunted since 1969..."],
    "SQLBruteforce":    ["Database exorcism failed...", "SQL curse applied..."],
    "StealFilesSSH":    ["Ghostly SSH file heist!", "Ectoplasm covers the loot...", "Data stolen by spectral hands..."],
    "StealFilesFTP":    ["FTP poltergeist grab...", "Files float away mysteriously..."],
    "StealFilesSMB":    ["SMB haunting complete...", "Data vanished into the ether..."],
    "StealFilesRDP":    ["Remote soul extraction...", "RDP possession successful..."],
    "StealFilesTelnet": ["Telnet spirit tap...", "Haunting the ancient terminal..."],
    "StealDataSQL":     ["SQL soul steal!", "Database cursed and drained..."],
    "LogStandalone":    ["Lurking in the shadows...", "Watching, always watching..."],
    "LogStandalone2":   ["Deep haunt in progress...", "Permanent spectral presence..."],
    "ZombifySSH":       ["Raising an undead host...", "Another soul joins my army..."],
    "LynisPentestSSH":  ["Full exorcism... of security!", "Haunting every service..."],
}


# ---------------------------------------------------------------------------
# Theme registry
# ---------------------------------------------------------------------------

THEMES = {
    "viking": {
        "description": "Viking (Classic)",
        "emoji": "⚔️",
        "title": "RAGNAR",
        "page_titles": {
            "network":    "NETWORK SCAN",
            "vuln":       "VULN INTEL",
            "discovered": "DISCOVERED",
            "advanced":   "ADV SCANNER",
            "traffic":    "TRAFFIC",
        },
        "corner_char":       None,
        "draw_accent":       None,
        "status_labels":     {},  # identity mapping (show raw status)
        "comments":          {},  # use original commentaire_ia
        "render_main_page":  _render_viking_main,
    },
    "penguin": {
        "description": "Penguin (Antarctica)",
        "emoji": "��",
        "title": "TUXNET",
        "page_titles": {
            "network":    "ICE SCAN",
            "vuln":       "BLIZZARD",
            "discovered": "GLACIER",
            "advanced":   "DEEP ICE",
            "traffic":    "CURRENT",
        },
        "corner_char":       "*",
        "draw_accent":       None,
        "status_labels":     {},
        "comments":          _PENGUIN_COMMENTS,
        "render_main_page":  _render_penguin_main,
    },
    "car": {
        "description": "Car (Road Trip)",
        "emoji": "🚗",
        "title": "ROADBOT",
        "page_titles": {
            "network":    "ROAD SCAN",
            "vuln":       "ENGINE CHK",
            "discovered": "VEHICLES",
            "advanced":   "DIAGNOSTICS",
            "traffic":    "TRAFFIC JAM",
        },
        "corner_char":       "o",
        "draw_accent":       None,
        "status_labels":     {},
        "comments":          _CAR_COMMENTS,
        "render_main_page":  _render_car_main,
    },
    "matrix": {
        "description": "Matrix (Hacker)",
        "emoji": "💊",
        "title": "[R4GN4R]",
        "page_titles": {
            "network":    "[SCAN]",
            "vuln":       "[VULN]",
            "discovered": "[NODES]",
            "advanced":   "[DEEP]",
            "traffic":    "[FLOW]",
        },
        "corner_char":       "1",
        "draw_accent":       None,
        "status_labels":     {},
        "comments":          _MATRIX_COMMENTS,
        "render_main_page":  _render_matrix_main,
    },
    "space": {
        "description": "Space (Cosmic)",
        "emoji": "🚀",
        "title": "STAR-NET",
        "page_titles": {
            "network":    "STAR MAP",
            "vuln":       "ASTEROID",
            "discovered": "PLANETS",
            "advanced":   "DEEP SPACE",
            "traffic":    "WARP FLOW",
        },
        "corner_char":       ".",
        "draw_accent":       None,
        "status_labels":     {},
        "comments":          _SPACE_COMMENTS,
        "render_main_page":  _render_space_main,
    },
    "ghost": {
        "description": "Ghost (Spooky)",
        "emoji": "👻",
        "title": "B00NET",
        "page_titles": {
            "network":    "HAUNTED",
            "vuln":       "CURSED",
            "discovered": "SPIRITS",
            "advanced":   "DARK ARTS",
            "traffic":    "ECTOPLASM",
        },
        "corner_char":       "~",
        "draw_accent":       None,
        "status_labels":     {},
        "comments":          _GHOST_COMMENTS,
        "render_main_page":  _render_ghost_main,
    },
}

DEFAULT_THEME = "viking"


def get_theme(config):
    """Return the active theme dict from the shared config."""
    name = config.get("display_theme", DEFAULT_THEME)
    return THEMES.get(name, THEMES[DEFAULT_THEME])
