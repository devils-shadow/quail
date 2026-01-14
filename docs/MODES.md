# Deployment Modes

This document describes the two supported deployment modes for Quail and how to
switch between them safely.

## VPN VM Mode

Use this mode when Quail is reachable only over a private network or VPN.

- Bind host: `0.0.0.0`
- Access: VPN or internal network only
- Reverse proxy: optional

## Reverse-Proxy Mode

Use this mode when Quail is placed behind a reverse proxy (for example, nginx
with OAuth2 or other access controls).

- Bind host: `127.0.0.1`
- Access: proxy only
- Reverse proxy: required
- WebSockets: proxy must allow Upgrade/Connection headers

## Switching Modes

Use the helper script to switch modes. This edits `/etc/quail/config.env` and
restarts the service.

```bash
sudo /opt/quail/scripts/quail-mode vpn
sudo /opt/quail/scripts/quail-mode proxy
```

## Notes

- The default install remains proxy-safe (`127.0.0.1`).
- Avoid exposing Quail directly to the public internet without additional
  access controls.
