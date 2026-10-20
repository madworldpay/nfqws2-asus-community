# Diagnostic mail relay

Separate operator service; it is never included in the router IPK. The router
defaults to mail disabled. A fixed HTTPS endpoint and a fixed mailbox must be
configured privately by the operator before mail can be offered to users.

The service accepts only the closed `support/report.schema.json` collector
format and a filename matching its model and timestamp. It mails the original
bytes as one JSON attachment. The separately consented DPI bundle adds one
closed `nfqws2_dpi` attachment: schema1 remains accepted for older clients;
schema2 uses `support/dpi-analysis-v2.schema.json`. Full native detector JSON
is local-only and is rejected by the relay. It cannot choose a recipient from a request.
It does not retain report bodies or raw client addresses. SQLite contains only
submission IDs, digests, states, timestamps and daily source HMACs.

Each SMTP operation runs in one short-lived Linux child. The parent enforces
one 10-second wall-clock budget, including native DNS and TLS stalls; killing
the parent also kills that child. Only safe phase markers cross the pipe.
A timeout after beginning DATA is unknown; a confirmed DATA 250 stays accepted
if cleanup stalls. No report, address or credential is written to a child argv,
environment or temporary file.

SMTP acceptance means a 250 reply after DATA; it does not promise Inbox delivery.
An ambiguous disconnect is terminal `unknown`, with no automatic resend. A
safe failure needs an explicit new user action and a new UUID. Quotas count
reserved attempts, including failures: 3/source/day, 20 globally/day, one active
SMTP operation. Reservations are atomic across both workers; stale 30-second
leases become unknown. Hourly expiry uses a 6-day-23-hour cutoff, keeping a
margin below seven days while the service and timer are running. An offline
machine cannot run cleanup; startup/request cleanup catches up on resumption.

## Operator prerequisites

Use a supported Linux host with Python 3.10+, systemd encrypted credentials,
an existing valid TLS certificate, an unused TCP 443 and outbound SMTP access.
Verify DNS, TCP, TLS and SMTP AUTH first. A TCP timeout precedes authentication;
changing mailbox passwords cannot fix that timeout. Do not deploy this service
until the SMTP check succeeds. A Gmail account needs 2-Step Verification and a
valid app password; an ordinary account password or passkey is not a substitute.

No test email is sent by health checks, credential loading, installation or
restart. Get explicit operator permission before sending a concrete test report.

## Installation after SMTP preflight succeeds

1. Save the original service, listener, firewall and certificate state privately.
   Do not alter an existing Hysteria listener or its configuration. HTTPS uses
   TCP 443 only; it does not take UDP 443. Keep standalone certificate renewal's
   TCP 80 free. If another HTTPS server owns TCP 443, integrate a dedicated
   server block through that operator's normal process instead of replacing it.
2. Privately render `deploy/nginx.conf.example` first, changing only the hostname
   and certificate paths. On a **fresh Debian/Ubuntu host**, run as root:
   `python3 support-relay/deploy/install-nginx.py /private/rendered-site.conf`.
   The helper refuses existing Nginx/operator policy, masks only the new Nginx
   service, and temporarily denies package autostart before installing Nginx
   and Python venv support. It disables only the newly packaged default site,
   checks the complete configuration has only `listen 443 ssl`, and starts
   Nginx only after validation. Failure keeps the new service masked; inspect
   privately and revalidate before unmasking. The temporary package policy is
   removed without replacing an operator policy. For an **existing** Nginx,
   do not run this helper: integrate the server block manually, preserve all
   operator sites, inspect `nginx -T`, validate, and reload through its owner.
   Verify `ss -ltnp 'sport = :80'` remains empty outside standalone renewal.
   Never install/start the packaged default port-80 site as an intermediate step.
   Copy the
   `support-relay` and sibling `support` directories under a root-owned
   `/usr/local/lib/nfqws-support/`. Keep their relative layout. Create `venv`
   there and run `venv/bin/python -m pip install --require-hashes -r
   support-relay/requirements.lock`. Do not install unpinned runtime packages.
   For a DPI schema upgrade, deploy the receiver code and both sibling DPI
   schemas before the router client. Preserve private deployed config/ACL policy;
   use fake SMTP for verification before restarting the receiver.
3. Install `deploy/nfqws-support.sysusers` as
   `/etc/sysusers.d/nfqws-support.conf`, then run `systemd-sysusers`. The account
   has no login shell. Install the service and cleanup service/timer into
   `/etc/systemd/system/`. Source and venv remain root-owned and read-only to
   the service account. StateDirectory owns the only writable application path.
4. Build the configuration in a private operator process using prompts and
   `getpass`, keeping it only in memory. The example JSON shows its shape;
   its placeholders must be replaced. Use a random 32-byte HMAC key, the full
   sender address and the same address as `sender`. Strip spaces from the
   16-character app password. Send the JSON over anonymous stdin directly to
   `systemd-creds encrypt --name=relay-config -
   /etc/credstore.encrypted/nfqws-support.cred`. Run the process as root and
   set the encrypted file mode to 0600. Never put the plaintext in a file,
   command argument, environment variable, shell history or diagnostic log.
   The encrypted file is machine-bound; preserve recovery access separately.
5. Keep the privately rendered `deploy/nginx.conf.example` from step 2.
   The file is a server block, for the operator's `http` context. No address or
   mailbox is substituted into public source or packages. Leave request logging
   off (including the server-scoped `/dev/null` error log) and request buffering on; the body buffer fits the full allowed 1 MiB.
   Validate with `nginx -t` before reloading. Install `renew-nginx.sh` only as a
   certificate renewal deploy hook: it validates and reloads Nginx alone.
6. Run `systemd-analyze verify` for the installed units. Enable/start
   `nfqws-support.service` and `nfqws-support-cleanup.timer`. Verify HTTPS
   `/health` returns only `{"state":"ready"}`. Health does not authenticate
   to SMTP, so a successful health response is not proof of working mail.
7. The router operator may separately configure its private, root-owned 0600
   `/opt/etc/nfqws-asus-web/support-relay.json` with `enabled: true` and the
   HTTPS `/nfqws-support/v1/reports` URL. Do not distribute a personal deployment
   address through the public package. Router installation is a separate step.

## Verification and rollback

Use fake SMTP for routine tests. Set `NFQWS_MAIL_TEST_PYTHON` to a private
hash-locked venv and `PHP_TEST_BINARY` to a matching Entware test runtime;
run `python -m unittest discover -s tests -p 'test_support_relay_*.py' -v`
from the repository root. `NGINX_TEST_BINARY` enables the isolated real Nginx
TLS/body-cap integration fixture. There are no calls to the real mail service.

For rollback, disable router mail first (local preview/save still work), stop
and disable only the new service and cleanup timer, remove only this server
block and validate Nginx before reload. Restore saved original configuration.
Do not restart unrelated services or replace their listeners. Delete this
service's encrypted credential and metadata only after an explicit operator
decision; downloaded reports and already delivered mailbox attachments have
independent retention. A service restart never automatically resends a report.

## Unified Share v3

The fixed `/nfqws-support/v3/reports` route accepts one to three independently
selected attachments: diagnostics, a safe DPI projection, strategy. The original
TXT/native DPI export is local-only. Closed schemas, canonical base64, byte counts,
SHA256, ordering, UUID and source metadata are validated before the existing
quota/dedup/SMTP path. v1/v2 remain accepted. Collector 1.1.0 adds passive router
DNS context; collector 1.0.0 remains valid without that section.

Deploy receiver code and all sibling schemas before enabling the private router
`sharing_v3_enabled` option. `/health` keeps its old body and advertises the
capability only in `X-NFQWS2-Sharing: 3`. Do not distribute a mailbox or SMTP secret
to routers. No test mail is needed for readiness.

Subjects use fixed category markers: `NFQWS2 community [diagnostics]`,
`NFQWS2 community [strategies]`, or both markers for a mixed submission. Keep two
Gmail labels, «Диагностика» and «Стратегии»: match each marker independently, so
mixed mail gets both. Preserve the old diagnostic subject filter. No per-model,
per-person or per-ID labels are needed. Plaintext message JSON carries the
submission ID and safe model/firmware/kernel/package metadata. A random installation
ID appears only after separate consent and is included in the reviewed proof.
It links an installation, not a verified person or physical router; backups can
clone it. A future table must distinguish self-reported success from verification
and must not count repeated installation IDs as independent votes.

## Optional coarse location

Install pinned `maxminddb` through `requirements.lock`. The receiver reads only
`/var/lib/nfqws-support/geo/dbip-city-lite.mmdb`: root-owned, non-writable by the
service, no symlink, at most 192 MiB. Use the official monthly DB-IP City Lite
MMDB, verify its published digest before atomic replacement, and retain one
active database. Check free space for the download, decompression and staging
beforehand. Database refresh is an operator action; an unavailable database never
triggers an external IP lookup. The current database must be no older than 62 days.

`GET /nfqws-support/v3/location` accepts no query or body and trusts only the
loopback proxy's source address. It returns country, region, city and database
age, never an IP or coordinates. The local reader uses mmap and bounded ephemeral
HMAC-keyed caching and request limits. It stores no location requests in SQLite.
The router bounds the entire lookup, including native DNS/TLS, with a short child
process; failure leaves manual entry available. The result can reflect a VPN exit.
Sending the edited location requires a separate, initially unchecked checkbox.

DB-IP City Lite is provided under CC BY 4.0. Preserve attribution
[IP Geolocation by DB-IP](https://db-ip.com/) in the location form and documentation.

### Extended contributions (v4)

`/nfqws-support/v4/reports` accepts an ordered subset of report, DPI, strategy, resources and DNS attachments (at most five, envelope at most 4 MiB). Legacy v1–v3 routes and file schemas remain available. Strategy schema2 includes shared BASE/EXTRA/IPSET declarations for selected blocks. The resources attachment carries explicit copies, source and outgoing hashes, aliases and a bounded static dependency audit. DNS separates active, draft and legacy sources, including deliberate standalone nondefault cards. Neither validator executes submitted files. URL credentials and authentication query parameters are rejected.

Deploy the compatible relay and 4 MiB in-memory nginx route before enabling optional boolean `sharing_v4_enabled` in the router’s root-only operator config. Its default is false; `sharestates` exposes the local capability without contacting the relay. This flag is independent of `sharing_v3_enabled`. Local preparation/download remain available without mail. SMTP sends the exact reviewed JSON bytes; resources/DNS contributions use the existing strategies label and do not create extra mailbox folders. Per-source/global limits, receipt deduplication and retention are unchanged.
