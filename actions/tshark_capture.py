import os
import subprocess
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

def run(shared_data):
    """Capture 30s of packets with tshark and save a pcap to Data Stolen."""
    if not getattr(shared_data, 'tshark_enabled', False):
        return

    # Check tool is available
    if subprocess.call(['which', 'tshark'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
        logger.warning("tshark not found — skipping capture")
        return

    iface = getattr(shared_data, 'wlan_interface', 'wlan0')
    network_name = getattr(shared_data, 'connected_network', 'unknown')
    safe_name = "".join(c if c.isalnum() or c in ('-', '_') else '_' for c in network_name)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')

    output_dir = os.path.join(getattr(shared_data, 'data_stolen_dir', 'data_stolen'), 'tshark')
    os.makedirs(output_dir, exist_ok=True)
    pcap_path = os.path.join(output_dir, f"{safe_name}_{timestamp}.pcap")

    try:
        shared_data.ragnarstatustext = "tshark capture"
        shared_data.ragnarstatustext2 = network_name[:16]
        logger.info(f"Starting 30s tshark capture on {iface} -> {pcap_path}")
        subprocess.run(
            ['tshark', '-i', iface, '-a', 'duration:30', '-w', pcap_path],
            timeout=45,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        if os.path.exists(pcap_path) and os.path.getsize(pcap_path) > 0:
            logger.info(f"tshark capture saved: {pcap_path}")
        else:
            logger.warning("tshark produced no output")
    except subprocess.TimeoutExpired:
        logger.warning("tshark capture timed out")
    except Exception as e:
        logger.error(f"tshark capture error: {e}")
