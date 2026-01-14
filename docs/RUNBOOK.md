# Runbook

This runbook provides step‑by‑step instructions for installing, configuring, running and maintaining Quail. It is aimed at a non‑developer operator. Forward-looking work for public internet deployment is documented separately in `docs/QUAIL_2_0_SPEC.md`.

## Installation

1. **Clone the repository** on the target host (a dedicated VM or server running Ubuntu Server).
2. **Create configuration:** Copy `config/config.example.env` to `/etc/quail/config.env` and adjust the values. Replace the example `QUAIL_DOMAINS` with the comma-separated list of domains you want Postfix to accept and set `QUAIL_ADMIN_PIN` to a 4-9 digit numeric PIN. `install.sh` will fail fast if you leave the example domain in place.
3. **Run the installer:** Execute `sudo ./install.sh`. The script will:
   - Install necessary OS packages.
   - Create a system user and the `/var/lib/quail/{eml,att}` directories.
   - Create a Python virtual environment and install dependencies.
   - Install Postfix relay/transport configuration for the Quail domain.
   - Install and enable systemd units for the service and purge timer.
   - Optional: add `--smoke-test` to perform a basic end-to-end ingest check.
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

### Deployment modes

See `docs/MODES.md` for VPN VM mode vs reverse-proxy mode guidance and the
`scripts/quail-mode` helper for switching bind hosts safely.

### WebSocket inbox

WebSocket inbox updates are enabled by default. To opt out, set
`QUAIL_ENABLE_WS=false` in `/etc/quail/config.env`. When disabled, the inbox
uses the existing polling behavior.

For WebSocket origin checks, Quail allows the current host origin by default.
To override, set `QUAIL_ALLOWED_ORIGINS` (comma-separated origins).

### Nginx HTTPS + WebSocket support

Quail runs plain HTTP on port 8000. If you terminate TLS with nginx, you must
enable WebSocket upgrades or the inbox will not receive live updates. If you
are accessing Quail directly (no nginx, local testing), you can skip this
section entirely.

Follow these steps:

1. **Locate your nginx site file.** On Ubuntu, this is usually
   `/etc/nginx/sites-available/<site>` with a symlink in
   `/etc/nginx/sites-enabled/`. If you are unsure, run:
   `sudo nginx -T | rg "server_name"` and find the block for your hostname.
2. **Edit the site file** and find or create the `location /` block that proxies
   to Quail. It must include `proxy_pass http://127.0.0.1:8000;` so nginx
   forwards requests to the Quail service.
3. **Add the WebSocket headers** inside that `location /` block:

```
proxy_http_version 1.1;
proxy_set_header Upgrade $http_upgrade;
proxy_set_header Connection "upgrade";
proxy_set_header Host $host;
proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
proxy_set_header X-Forwarded-Proto $scheme;
```

4. **Validate and reload nginx:**

```
sudo nginx -t
sudo systemctl reload nginx
```

## Upgrade

To upgrade Quail to a newer version:

1. Pull the latest changes into the repository.
2. Run `sudo ./upgrade.sh`. It will update dependencies, restart services and leave stored mail intact.
   To reset the admin PIN during upgrade, set `QUAIL_RESET_PIN=true` and
   `QUAIL_ADMIN_PIN` in `/etc/quail/config.env` before running the script.
3. Check the service and timer status as in the installation step.

## Testing

- Standard suite (mirrors CI): `pytest -m "not slow" -ra`
- Focused subsets: `pytest -m unit -ra`, `pytest -m api -ra`, `pytest -m integration -ra`
- Full guidance lives in `docs/TESTING.md`.

## Daily Operation

- **Inbox access:** Access the web UI via the configured address (VPN or internal network). Message detail pages include HTML, plaintext, and attachments tabs. Admins can enable full HTML rendering in settings; when disabled, only plaintext is shown.
- **Admin actions:** Use the Unlock workflow and enter the shared admin PIN to perform privileged actions such as changing settings, deleting messages or modifying retention policies. The admin settings page includes ingest visibility metrics (inbox/quarantine/dropped counts, ingest rate, and top sender domains) for the last 24 hours.
- **Retention policy:** The purge timer automatically deletes inbox messages older than the configured retention period (default 30 days) and quarantined/dropped messages older than the quarantine retention period (default 3 days). Admins can optionally set per-domain quarantine overrides in the settings UI.
- **Audit retention:** Admin audit entries are retained for 30 days and are purged alongside the regular retention job.

## Troubleshooting

- **Service fails to start:** Check `journalctl -u quail -f` and `/var/log/syslog` for errors. Common issues include invalid configuration values or missing directories. Ensure that Postfix is piping messages to `scripts/quail-ingest` as expected.
- **Email not ingested:** Verify that Postfix is configured to accept mail for
  configured domains via `relay_domains` and `transport_maps`, and that the ingest
  script has execute permission.
- **Admin PIN lost:** Reset the PIN by updating the `admin_pin_hash` in the SQLite settings table. Use a secure Argon2 hash generator.
- **Attachment quarantined unexpectedly:** Check the allowed MIME types in the settings and adjust as necessary.
