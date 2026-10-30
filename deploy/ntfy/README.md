# Study Chat relay on a Raspberry Pi 5

Study Chat already reads `STUDYCHAT_RELAY` and `STUDYCHAT_TOKEN`.
It publishes over HTTP and subscribes through a long-lived `/json` HTTP
stream, not a WebSocket. Images and fonts use ntfy attachments. All clients
must use the same relay, online mode, and room name.

## Deploy

1. Install 64-bit Raspberry Pi OS, apply updates, and install Docker Engine
   with the Compose plugin using https://docs.docker.com/engine/install/debian/.
   Use Ethernet and reserve the Pi's LAN address in your router.
2. Copy this directory to the Pi. Replace `chat.example.com` in BOTH
   `server.yml` and `Caddyfile` with your domain. Create its DNS A record
   pointing to your home's public IPv4 address. Publish AAAA only if IPv6
   routing and firewall rules also work.
3. Forward TCP 80 and 443 from your router to the Pi. Caddy obtains and
   renews a trusted TLS certificate. Do not forward 8080 or expose ntfy
   directly. Confirm the Pi firewall allows 80 and 443.
4. From this directory run:

   ```sh
   docker compose up -d
   docker compose exec ntfy ntfy user add studychat
   docker compose exec ntfy ntfy access studychat 'sc-*' rw
   docker compose exec ntfy ntfy token add studychat
   ```

   Enter a strong password when prompted. Save the generated token privately.
   Prefer a separate user/token per participant so access can be revoked
   individually. The `sc-*` grant covers all Study Chat rooms; use an exact
   topic for room isolation. Its value is `sc-` followed by the first 32 hex
   characters of SHA-256 of `studychat:` plus the room name.

5. Check `docker compose logs --tail=100` and test from a different internet
   connection, such as a phone hotspot. Anonymous topic reads should fail.

The images use moving tags for initial setup. After successful deployment,
pin tested image versions or digests and update deliberately. Back up the
`ntfy-data` volume (stop ntfy during a file-level SQLite backup). Attachments
expire after three hours; this is not permanent chat storage.

## Point Study Chat at it

macOS/Linux, in the terminal that starts the app:

```sh
export STUDYCHAT_RELAY='https://chat.example.com'
read -rs STUDYCHAT_TOKEN
export STUDYCHAT_TOKEN
python3 studychat.py --online --room 'your-room' --name 'Andy'
```

Paste the token at the hidden input, then press Enter. In PowerShell:

```powershell
$env:STUDYCHAT_RELAY = 'https://chat.example.com'
$secret = Read-Host 'ntfy token' -AsSecureString
$env:STUDYCHAT_TOKEN = [System.Net.NetworkCredential]::new('', $secret).Password
python studychat.py --online --room 'your-room' --name 'Andy'
```

Alternatively set **Network → Online relay address** in the app settings;
the environment variable overrides the saved address on startup. Tokens
currently come from the environment only. Restart the app after changing
these values. Never commit tokens. Keep the URL at the origin with no topic
or path suffix: attachment URLs must start with that same origin.

## Restricted networks and home connectivity

Use a public hostname with a trusted certificate on HTTPS port 443. LAN
broadcast mode and private Pi addresses commonly cannot connect across
isolated Wi-Fi clients. A VPN requires client installation and may itself
be blocked. HTTPS improves compatibility but cannot guarantee access:
domain filtering, TLS inspection, required authenticated proxies, and
stream buffering can still prevent delivery. Ask the network administrator
to allow your hostname, HTTPS GET/POST/PUT, Authorization headers, and
long-lived streaming responses. Do not disable certificate verification.
If an approved inspection CA is needed, have IT configure the client trust
store; this app uses certifi when installed.

If your ISP uses CGNAT or blocks inbound ports, router forwarding will not
work. Options are an ISP public address, a public VPS proxy linked to the Pi,
or a managed outbound tunnel with a stable custom HTTPS hostname. For a
tunnel, route that hostname to `http://localhost:8080`, keep ntfy `base-url`
set to the public HTTPS origin, and omit Caddy/port forwarding. Check the
provider's streaming and upload limits. Browser login challenges in front
of ntfy are incompatible with the app's bearer-token requests; use ntfy's
own authentication. A tunnel adds a third party to the traffic path.

Two clients sharing a school NAT can still hit ntfy's per-IP limits. The
app already backs off on 429s; size server limits for your actual group
instead of disabling protection. This bundle leaves forwarded-IP trust off
so clients cannot forge rate-limit identities. Monitor disk usage and logs.

Verify text in both directions, reconnect after a brief Wi-Fi interruption,
and send an image and font from the actual restricted network. If text works
but attachments fail, check `base-url`, upload limits, and disk space. If
messages appear only after reconnecting, investigate proxy stream buffering.
The server operator can read chat content; TLS and token authentication do
not provide end-to-end encryption.

References: https://docs.ntfy.sh/config/ and
https://docs.ntfy.sh/install/ and https://caddyserver.com/docs/quick-starts/reverse-proxy
