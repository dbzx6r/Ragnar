import os
import subprocess
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def run(shared_data):
    """Run nuclei vulnerability templates against discovered hosts."""
    if not getattr(shared_data, 'nuclei_enabled', False):
        return

    if subprocess.call(['which', 'nuclei'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        logger.warning("nuclei not found — skipping")
        return

    hosts = getattr(shared_data, 'discovered_hosts', [])
    if not hosts:
        logger.info("nuclei: no hosts to scan")
        return

    network_name = getattr(shared_data, 'connected_network', 'unknown')
    safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in network_name)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    output_dir = os.path.join(getattr(shared_data, 'data_stolen_dir', 'data_stolen'), 'nuclei')
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.json")

    # Build target list (prefer HTTP hosts; limit to 10 to keep runtime reasonable)
    targets = []
    for h in hosts[:10]:
        ip = h.get('ip') if isinstance(h, dict) else str(h)
        if ip:
            targets.extend([f"http://{ip}", f"https://{ip}"])

    if not targets:
        return

    # Write targets to temp file
    targets_file = f"/tmp/nuclei_targets_{timestamp}.txt"
    with open(targets_file, 'w') as f:
        f.write('\n'.join(targets))

    try:
        shared_data.ragnarstatustext = "nuclei scan"
        shared_data.ragnarstatustext2 = f"{len(hosts[:10])} hosts"
        logger.info(f"Starting nuclei scan against {len(targets)} targets")

        result = subprocess.run(
            [
                'nuclei',
                '-l', targets_file,
                '-t', 'http/technologies/',
                '-t', 'http/exposures/',
                '-t', 'http/default-logins/',
                '-severity', 'low,medium,high,critical',
                '-json-export', out_path,
                '-timeout', '5',
                '-rate-limit', '10',
                '-silent',
            ],
            timeout=300,
            capture_output=True,
            text=True,
            errors='replace'
        )
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            logger.info(f"nuclei results saved: {out_path}")
        else:
            logger.info("nuclei: no findings")
    except subprocess.TimeoutExpired:
        logger.info("nuclei scan completed (timeout)")
    except Exception as e:
        logger.error(f"nuclei error: {e}")
    finally:
        if os.path.exists(targets_file):
            os.remove(targets_file)
