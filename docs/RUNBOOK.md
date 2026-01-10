# Runbook

This runbook provides step‑by‑step instructions for installing, configuring, running and maintaining Quail. It is aimed at a non‑developer operator.

## Installation

1. **Clone the repository** on the target host (a spare laptop running Ubuntu Server as assumed in the context).
2. **Create configuration:** Copy `config/config.example.env` to `/etc/quail/config.env` and adjust the values. By default the service binds to `127.0.0.1`; if external access is required, expose it via a reverse proxy and VPN【819940561035949†L23-L26】.
3. **Run the installer:** Execute `sudo ./install.sh`. The script will:
   - Install necessary OS packages.
   - Create a system user and the `/var/lib/quail/{eml,att}` directories.
   - Create a Python virtual environment and install dependencies.
   - Install Postfix catch‑all configuration snippets.
   - Install and enable systemd units for the service and purge timer【104907567664902†L190-L199】.
4. **Verify installation:** Ensure that the `quail.service` and `quail-purge.timer` units are active using `systemctl status`.

## Upgrade

To upgrade Quail to a newer version:

1. Pull the latest changes into the repository.
2. Run `sudo ./upgrade.sh`. It will update dependencies, restart services and leave stored mail intact【104907567664902†L203-L210】.
3. Check the service and timer status as in the installation step.

## Daily Operation

- **Inbox access:** Access the web UI via the configured address (VPN or localhost). The default view shows plaintext messages; administrators can enable sanitized HTML rendering【819940561035949†L35-L40】.
- **Admin actions:** Click the Unlock button and enter the shared admin PIN to perform privileged actions such as changing settings, deleting messages or modifying retention policies.
- **Retention policy:** The purge timer automatically deletes inbox messages older than the configured retention period (default 30 days) and quarantined/dropped messages older than the quarantine retention period (default 3 days). Admins can optionally set per-domain quarantine overrides in the settings UI.

## Troubleshooting

- **Service fails to start:** Check `/var/log/syslog` for errors. Common issues include invalid configuration values or missing directories. Ensure that Postfix is piping messages to `scripts/quail-ingest` as expected【819940561035949†L14-L16】.
- **Email not ingested:** Verify that Postfix is configured to accept mail for `m.cst.ro` and that the ingest script has execute permission.
- **Admin PIN lost:** Reset the PIN by updating the `admin_pin_hash` in the SQLite settings table. Use a secure Argon2 hash generator.
- **Attachment quarantined unexpectedly:** Check the allowed MIME types in the settings and adjust as necessary【104907567664902†L71-L78】.
