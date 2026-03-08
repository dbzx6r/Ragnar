"""
Captive portal detection and authentication for client WiFi connections.

When Ragnar connects to a network, this module probes known URLs to detect
captive portals and attempts auto-authentication for simple click-through portals.
"""

import logging
import urllib.parse
from html.parser import HTMLParser

logger = logging.getLogger(__name__)

# Probe URLs — these return predictable responses on a free internet connection.
# A redirect or unexpected body indicates a captive portal is intercepting traffic.
PROBE_URLS = [
    "http://connectivitycheck.gstatic.com/generate_204",
    "http://captive.apple.com",
    "http://www.msftconnecttest.com/connecttest.txt",
]

# Expected responses for each probe URL when the network is open
_PROBE_EXPECTED = {
    "http://connectivitycheck.gstatic.com/generate_204": {"status": 204, "body": None},
    "http://captive.apple.com": {"status": 200, "body": "Success"},
    "http://www.msftconnecttest.com/connecttest.txt": {"status": 200, "body": "Microsoft Connect Test"},
}


# ---------------------------------------------------------------------------
# HTML form parser (stdlib only — no BeautifulSoup)
# ---------------------------------------------------------------------------

class _FormParser(HTMLParser):
    """Minimal HTML parser that extracts form metadata and input fields."""

    def __init__(self):
        super().__init__()
        self.forms = []          # list of dicts: {action, method, inputs}
        self._current_form = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "form":
            self._current_form = {
                "action": attrs.get("action", ""),
                "method": attrs.get("method", "get").lower(),
                "inputs": [],
            }
            self.forms.append(self._current_form)
        elif tag == "input" and self._current_form is not None:
            self._current_form["inputs"].append({
                "type": attrs.get("type", "text").lower(),
                "name": attrs.get("name", ""),
                "value": attrs.get("value", ""),
            })

    def handle_endtag(self, tag):
        if tag == "form":
            self._current_form = None


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def detect(timeout: int = 5) -> dict:
    """Probe standard connectivity-check URLs to detect a captive portal.

    Returns a dict with:
        detected  (bool)      – True if a portal was found
        portal_url (str|None) – The URL the portal redirected to, if any
        probe_url  (str|None) – Which probe URL triggered the detection
    """
    try:
        import requests
    except ImportError:
        logger.warning("captive_portal.detect: 'requests' library not available")
        return {"detected": False, "portal_url": None, "probe_url": None}

    for url in PROBE_URLS:
        try:
            resp = requests.get(url, allow_redirects=False, timeout=timeout)
            expected = _PROBE_EXPECTED.get(url, {})
            expected_status = expected.get("status")
            expected_body = expected.get("body")

            # Explicit redirect → portal URL is in Location header
            if resp.status_code in (301, 302, 303, 307, 308):
                portal_url = resp.headers.get("Location", "")
                logger.info(
                    f"Captive portal detected via redirect on {url} → {portal_url}"
                )
                return {"detected": True, "portal_url": portal_url, "probe_url": url}

            # Unexpected status or wrong body → portal is injecting content
            if expected_status and resp.status_code != expected_status:
                logger.info(
                    f"Captive portal detected: {url} returned {resp.status_code} "
                    f"(expected {expected_status})"
                )
                return {"detected": True, "portal_url": url, "probe_url": url}

            if expected_body and expected_body not in resp.text:
                logger.info(
                    f"Captive portal detected: {url} body mismatch "
                    f"(expected '{expected_body}' not found)"
                )
                return {"detected": True, "portal_url": url, "probe_url": url}

            # This probe succeeded — network is open
            logger.debug(f"Captive portal probe OK: {url}")
            return {"detected": False, "portal_url": None, "probe_url": url}

        except requests.exceptions.Timeout:
            logger.debug(f"Captive portal probe timed out: {url}")
            # Timeout on a probe can itself indicate a portal; try next URL
            continue
        except Exception as exc:
            logger.debug(f"Captive portal probe error on {url}: {exc}")
            continue

    # All probes failed (network down or fully blocked)
    logger.warning("All captive portal probes failed — network may be unavailable")
    return {"detected": False, "portal_url": None, "probe_url": None}


def try_auto_auth(portal_url: str, timeout: int = 10) -> dict:
    """Attempt automatic authentication for simple click-through captive portals.

    Fetches the portal page, parses any HTML forms, and submits the first form
    that contains no password fields (i.e. a simple "accept terms" click-through).
    After submission, re-probes connectivity to confirm success.

    Returns a dict with:
        success (bool)  – True if connectivity was restored
        method  (str)   – Description of what was attempted
        message (str)   – Human-readable result
    """
    try:
        import requests
    except ImportError:
        return {"success": False, "method": "none", "message": "'requests' not available"}

    # ------------------------------------------------------------------
    # Step 1: Fetch the portal page
    # ------------------------------------------------------------------
    try:
        session = requests.Session()
        resp = session.get(portal_url, allow_redirects=True, timeout=timeout)
        resp.raise_for_status()
    except Exception as exc:
        logger.warning(f"Auto-auth: failed to fetch portal page '{portal_url}': {exc}")
        return {
            "success": False,
            "method": "fetch",
            "message": f"Could not load portal page: {exc}",
        }

    html_content = resp.text
    final_url = resp.url  # may differ from portal_url after redirects

    # ------------------------------------------------------------------
    # Step 2: Parse forms
    # ------------------------------------------------------------------
    parser = _FormParser()
    try:
        parser.feed(html_content)
    except Exception as exc:
        logger.warning(f"Auto-auth: HTML parse error: {exc}")

    # Find a form with no password fields — these are safe to auto-submit
    click_through_form = None
    for form in parser.forms:
        has_password = any(inp["type"] == "password" for inp in form["inputs"])
        if not has_password:
            click_through_form = form
            break

    if click_through_form is None:
        logger.info("Auto-auth: no click-through form found (all forms require a password)")
        return {
            "success": False,
            "method": "parse",
            "message": "Portal requires credentials — manual login needed",
        }

    # ------------------------------------------------------------------
    # Step 3: Build and submit the form
    # ------------------------------------------------------------------
    action = click_through_form["action"].strip()
    method = click_through_form["method"]

    # Resolve relative action URL against the final portal URL
    if action:
        submit_url = urllib.parse.urljoin(final_url, action)
    else:
        submit_url = final_url

    # Collect non-empty named fields (skip submit/image buttons)
    form_data = {
        inp["name"]: inp["value"]
        for inp in click_through_form["inputs"]
        if inp["name"] and inp["type"] not in ("submit", "image", "reset")
    }

    logger.info(
        f"Auto-auth: submitting click-through form to '{submit_url}' "
        f"via {method.upper()} with {len(form_data)} fields"
    )

    try:
        if method == "post":
            session.post(submit_url, data=form_data, allow_redirects=True, timeout=timeout)
        else:
            session.get(submit_url, params=form_data, allow_redirects=True, timeout=timeout)
    except Exception as exc:
        logger.warning(f"Auto-auth: form submission failed: {exc}")
        return {
            "success": False,
            "method": "submit",
            "message": f"Form submission error: {exc}",
        }

    # ------------------------------------------------------------------
    # Step 4: Re-probe to confirm connectivity was restored
    # ------------------------------------------------------------------
    result = detect(timeout=5)
    if not result["detected"]:
        logger.info("Auto-auth: connectivity restored after form submission")
        return {
            "success": True,
            "method": "click-through",
            "message": "Successfully authenticated through captive portal",
        }

    logger.info("Auto-auth: portal still detected after form submission — may need manual login")
    return {
        "success": False,
        "method": "click-through",
        "message": "Form submitted but portal is still active — manual login may be required",
    }


def get_status(shared_data) -> dict:
    """Return current captive portal state from shared runtime data.

    Args:
        shared_data: The SharedData instance from shared.py

    Returns a dict with:
        detected       (bool)      – Whether a portal is currently detected
        portal_url     (str|None)  – URL of the portal page
        authenticated  (bool)      – Whether auto-auth succeeded
        auto_auth      (bool)      – Whether auto-auth is enabled in config
    """
    return {
        "detected": bool(getattr(shared_data, "captive_portal_detected", False)),
        "portal_url": getattr(shared_data, "captive_portal_url", None),
        "authenticated": bool(getattr(shared_data, "captive_portal_authenticated", False)),
        "auto_auth_enabled": bool(
            shared_data.config.get("captive_portal_auto_auth", True)
            if hasattr(shared_data, "config") else True
        ),
    }
