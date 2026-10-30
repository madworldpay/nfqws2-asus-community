# Temporary technical channel

The panel footer contains **Technical channel** and a tap-accessible `?` help
button. After prior arrangements with the Administrator, the owner pastes the
provided link and connects. A protected panel login is required. The owner does
not need a PC. This does not submit a support request or start a permanent agent.

This is trusted root access for router diagnostics and configuration, not a
sandbox. The owner sees the state, deadline and Disconnect button. Stop, expiry,
worker failure and reboot invalidate access, including a running command.
Configuration changes already made by the Administrator remain in effect.

## Administrator setup

Run these tools on a trusted PC with Python 3 and `cryptography`. Use your normal,
already configured root SSH access to the VPS with host key verification. The
server needs OpenSSH, systemd, Python 3, useradd/userdel and pkill.

Keep the separate RSA invitation signing key on the Administrator's PC. The
package contains only the matching `technical-channel-public.pem`. Never place
the signing private key in Git, router packages, diagnostics or on the VPS.

```sh
python3 admin.py --server VPS_IPV4 --remote-port 44901 --minutes 60 \
  --label 'Router owner' --signing-key /private/technical-channel-private.pem \
  --known-hosts /private/vps-known-hosts --output /private/new-session
```

The output directory must be empty and private (0700). Give the owner only
**CONNECT.txt**. Its link includes a limited temporary tunnel credential; do not
publish it. `operator` is the Administrator's private access key and must stay on
their PC. `session.json` contains session metadata without private keys.
`--control-path` can reuse an existing trusted Administrator SSH connection.

The router verifies the link offline without fetching its URL. The signed data
contains the VPS address, port and SSH host key. To move servers, issue a fresh
link: neither the old VPS nor a package rebuild is required. A conflicting
previously saved key for the same IP is preserved and requires investigation.

## Connection and revocation

The VPS creates one `nfqs-…` account without shell/TTY, local forwarding or Unix
socket forwarding. Only its exact reverse listener on `127.0.0.1` is permitted.
The router's SSH port is not exposed publicly. A server timer removes the account
at expiry. To revoke it immediately on the VPS:

```sh
python3 /usr/local/libexec/nfqws-technical-server.py revoke SESSION_ID
```

The Administrator uses their normal VPS SSH login to reach that local port, then
authenticates to the router with `operator`. Use root on OpenWrt or the UID 0
account on ASUS. Verify the router's host key through a trusted source as well;
do not disable host key checking. An interactive empty command and PTY are denied.

The router uses its existing Dropbear and the package's PHP/OpenSSL. A separate
temporary Dropbear listens only on loopback, disables passwords/forwarding and
forces the live-session/deadline guard for every command. Normal SSH, the router
password, routing, DNS, VPN and firewall settings are not reconfigured.
Private session material stays in `/tmp`; a private persistent journal in the
panel configuration directory records only public-key file recovery data.
Both wall time and uptime deadlines are checked, along with the boot ID.

Hardware validation applies to the devices actually tested. A matching CPU
architecture does not replace testing the firmware and its Dropbear build.
