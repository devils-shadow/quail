# Runbook

This runbook provides step‑by‑step instructions for installing, configuring, running and maintaining Quail. It is aimed at a non‑developer operator. Forward-looking work for public internet deployment is documented separately in `docs/QUAIL_2_0_SPEC.md`.

## Installation

1. **Clone the repository** on the target host (a spare laptop running Ubuntu Server as assumed in the context).
2. **Create configuration:** Copy `config/config.example.env` to `/etc/quail/config.env` and adjust the values. Replace the example `QUAIL_DOMAINS` with the comma-separated list of domains you want Postfix to accept and set `QUAIL_ADMIN_PIN` to a 4-9 digit numeric PIN. `install.sh` will fail fast if you leave the example domain in place.
3. **Run the installer:** Execute `sudo ./install.sh`. The script will:
   - Install necessary OS packages.
   - Create a system user and the `/var/lib/quail/{eml,att}` directories.
   - Create a Python virtual environment and install dependencies.
   - Install Postfix relay/transport configuration for the Quail domain.
   - Install and enable systemd units for the service and purge timer【104907567664902†L190-L199】.
4. **Verify installation:** Ensure that the `quail.service` and `quail-purge.timer` units are active using `systemctl status`.

### Systemd overrides

- Prefer editing `/etc/quail/config.env` for runtime configuration such as bind
  host/port values.
- If you need a systemd override, use `sudo systemctl edit quail` to create
  `/etc/systemd/system/quail.service.d/override.conf`.
- An example drop-in lives at `systemd/quail.service.d/override.conf.example`
  for common overrides (such as bind host); copy it into
  `/etc/systemd/system/quail.service.d/override.conf` if needed and reload
  systemd afterwards.

## Upgrade

To upgrade Quail to a newer version:

1. Pull the latest changes into the repository.
2. Run `sudo ./upgrade.sh`. It will update dependencies, restart services and leave stored mail intact【104907567664902†L203-L210】.
   To reset the admin PIN during upgrade, set `QUAIL_RESET_PIN=true` and
   `QUAIL_ADMIN_PIN` in `/etc/quail/config.env` before running the script.
3. Check the service and timer status as in the installation step.

## Testing

- Standard suite (mirrors CI): `pytest -m "not slow" -ra`
- Focused subsets: `pytest -m unit -ra`, `pytest -m api -ra`, `pytest -m integration -ra`
- Full guidance lives in `docs/TESTING.md`.

## Daily Operation

- **Inbox access:** Access the web UI via the configured address (VPN or localhost). Message detail pages include HTML, plaintext, and attachments tabs. Admins can enable full HTML rendering in settings; when disabled, only plaintext is shown.
- **Admin actions:** Click the Unlock button and enter the shared admin PIN to perform privileged actions such as changing settings, deleting messages or modifying retention policies. The admin settings page includes ingest visibility metrics (inbox/quarantine/dropped counts, ingest rate, and top sender domains) for the last 24 hours.
- **Retention policy:** The purge timer automatically deletes inbox messages older than the configured retention period (default 30 days) and quarantined/dropped messages older than the quarantine retention period (default 3 days). Admins can optionally set per-domain quarantine overrides in the settings UI.
- **Audit retention:** Admin audit entries are retained for 30 days and are purged alongside the regular retention job.

## Troubleshooting

- **Service fails to start:** Check `/var/log/syslog` for errors. Common issues include invalid configuration values or missing directories. Ensure that Postfix is piping messages to `scripts/quail-ingest` as expected【819940561035949†L14-L16】.
- **Email not ingested:** Verify that Postfix is configured to accept mail for
  configured domains via `relay_domains` and `transport_maps`, and that the ingest
  script has execute permission.
- **Admin PIN lost:** Reset the PIN by updating the `admin_pin_hash` in the SQLite settings table. Use a secure Argon2 hash generator.
- **Attachment quarantined unexpectedly:** Check the allowed MIME types in the settings and adjust as necessary【104907567664902†L71-L78】.
