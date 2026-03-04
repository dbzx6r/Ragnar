"""
display_themes.py — E-ink display theme definitions for Ragnar.

Each theme controls:
  - title:        text shown in PAGE_MAIN header
  - page_titles:  titles for sub-pages (network, vuln, discovered, advanced, traffic)
  - corner_char:  character drawn at top corners of PAGE_MAIN border (None = skip)
  - draw_accent:  callable(draw, image, sx, sy, ys, shared_data) — optional extra art
  - description:  human-readable label for the web UI
  - emoji:        emoji for the web UI dropdown
"""

from PIL import ImageDraw

# ---------------------------------------------------------------------------
# Accent drawers
# ---------------------------------------------------------------------------

def _draw_penguin_accent(draw, image, sx, sy, ys, sd):
    """Tiny pixel penguin next to the status area."""
    try:
        px = int(118 * sx)
        py = int(62 * sy * ys)
        draw.ellipse([px+2, py+6, px+13, py+19], fill=255, outline=0)  # white belly
        draw.rectangle([px, py+3, px+15, py+18], fill=0)               # black body
        draw.ellipse([px+2, py+6, px+13, py+17], fill=255, outline=0)  # white belly
        draw.ellipse([px+2, py, px+13, py+9], fill=0)                  # black head
        draw.point((px+5, py+3), fill=255)   # left eye
        draw.point((px+10, py+3), fill=255)  # right eye
        draw.line([px+4, py+19, px+2, py+21], fill=0, width=1)   # left foot
        draw.line([px+11, py+19, px+13, py+21], fill=0, width=1) # right foot
    except Exception:
        pass


def _draw_car_accent(draw, image, sx, sy, ys, sd):
    """Tiny pixel car next to the status area."""
    try:
        px = int(112 * sx)
        py = int(65 * sy * ys)
        # Body
        draw.rectangle([px, py+5, px+20, py+13], fill=0)
        draw.rectangle([px+3, py+1, px+17, py+6], fill=0)
        # Windows (white)
        draw.rectangle([px+4, py+2, px+9, py+5], fill=255)
        draw.rectangle([px+11, py+2, px+16, py+5], fill=255)
        # Wheels
        draw.ellipse([px+1, py+11, px+7, py+17], fill=0)
        draw.ellipse([px+3, py+13, px+5, py+15], fill=255)
        draw.ellipse([px+13, py+11, px+19, py+17], fill=0)
        draw.ellipse([px+15, py+13, px+17, py+15], fill=255)
    except Exception:
        pass


def _draw_matrix_accent(draw, image, sx, sy, ys, sd):
    """Matrix rain column next to the status area."""
    try:
        font = sd.font_arial9
        chars = ['1', '0', '1', '1', '0', '0', '1']
        px = int(118 * sx)
        py = int(60 * sy * ys)
        for i, ch in enumerate(chars):
            draw.text((px, py + i * 9), ch, font=font, fill=0)
    except Exception:
        pass


def _draw_space_accent(draw, image, sx, sy, ys, sd):
    """Tiny rocket ship next to the status area."""
    try:
        px = int(115 * sx)
        py = int(62 * sy * ys)
        # Rocket body
        draw.polygon([(px+5, py), (px+9, py+6), (px+9, py+16), (px+1, py+16), (px+1, py+6)], fill=0)
        # Window
        draw.ellipse([px+3, py+7, px+7, py+11], fill=255, outline=0)
        # Flame
        draw.polygon([(px+1, py+16), (px+5, py+21), (px+9, py+16)], fill=0)
        # Fins
        draw.polygon([(px+9, py+12), (px+12, py+16), (px+9, py+16)], fill=0)
        draw.polygon([(px+1, py+12), (px-2, py+16), (px+1, py+16)], fill=0)
    except Exception:
        pass


def _draw_ghost_accent(draw, image, sx, sy, ys, sd):
    """Tiny ghost / Pac-Man ghost next to the status area."""
    try:
        px = int(114 * sx)
        py = int(62 * sy * ys)
        # Body
        draw.ellipse([px, py, px+14, py+12], fill=0)
        draw.rectangle([px, py+6, px+14, py+18], fill=0)
        # Wavy bottom
        draw.polygon([(px, py+18), (px+3, py+15), (px+7, py+18), (px+11, py+15), (px+14, py+18)], fill=255)
        # Eyes
        draw.ellipse([px+2, py+3, px+6, py+8], fill=255)
        draw.ellipse([px+8, py+3, px+12, py+8], fill=255)
        draw.ellipse([px+3, py+4, px+5, py+7], fill=0)
        draw.ellipse([px+9, py+4, px+11, py+7], fill=0)
    except Exception:
        pass


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
        "corner_char": None,
        "draw_accent": None,
    },
    "penguin": {
        "description": "Penguin (Antarctica)",
        "emoji": "🐧",
        "title": "TUXNET",
        "page_titles": {
            "network":    "ICE SCAN",
            "vuln":       "BLIZZARD",
            "discovered": "GLACIER",
            "advanced":   "DEEP ICE",
            "traffic":    "CURRENT",
        },
        "corner_char": "*",
        "draw_accent": _draw_penguin_accent,
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
        "corner_char": "o",
        "draw_accent": _draw_car_accent,
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
        "corner_char": "1",
        "draw_accent": _draw_matrix_accent,
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
        "corner_char": ".",
        "draw_accent": _draw_space_accent,
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
        "corner_char": "~",
        "draw_accent": _draw_ghost_accent,
    },
}

DEFAULT_THEME = "viking"


def get_theme(config):
    """Return the active theme dict from the shared config."""
    name = config.get("display_theme", DEFAULT_THEME)
    return THEMES.get(name, THEMES[DEFAULT_THEME])
