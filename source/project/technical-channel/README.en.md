# Temporary technical channel

The panel footer contains **Technical channel** and a tap-accessible `?` help
button. After prior arrangements with the Administrator, the owner pastes the
provided link and connects. A protected panel login is required. The owner does
not need a PC. This does not submit a support request or start a permanent agent.

This is trusted root access for router diagnostics and configuration, not a
sandbox. The owner sees the state, deadline and Disconnect button. Stop, expiry,
worker failure and reboot invalidate access, including a running command.
Configuration changes already made by the Administrator remain in effect.

The controller checks both the outbound connection and its local SSH server.
If either exits, the channel closes the remaining process and releases the
reverse port. Stop and controller crash recovery use the same cleanup. It
targets only the current connection's processes, preserving a replacement
session and the router's normal SSH server. Reconnecting does not extend the
invitation deadline.

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

With a receiver on the operator's PC, connect directly to
`127.0.0.1:remote_port` from `session.json`; no VPS is required. `connect.py`
discovers the router's UID 0 account name before authenticating with `operator`.
The owner only pastes the signed invitation into WebUI and presses Connect;
they do not need to provide a login name or password.

```sh
python3 connect.py --session-dir /private/new-session \
  --router-known-hosts /private/router-known-hosts \
  --router-host-key-alias owner-router --command '/bin/busybox id -u'
```

`owner-router` identifies an already verified router SSH host key in that
known_hosts file. Host verification is mandatory during both discovery and
command execution. Verify a new host key through an existing trusted source;
automatically accepting a key from the same connection does not establish trust.
Without `--command`, the helper prints only the session ID and discovered login.
Use absolute command paths on firmware with a limited PATH.
For a VPS receiver, forward its loopback port to the same local port on the PC
using your normal trusted SSH access, then run the helper on the PC. The operator
key stays on the PC.
The restricted `nfqs-…` tunnel account never receives a shell or TTY.
An interactive empty command and PTY on the router are also denied.

The temporary loopback Dropbear uses `-b` to publish exactly one line:
`NFQWS2-TECH-META/1 SESSION_ID UID0_LOGIN`. It contains public metadata only,
with no password, key material or signed invitation. It travels inside the
existing authenticated tunnel and SSH connection with a pinned router host key.
The first short SSH probe requests only `none` authentication for a fixed
discovery identity, offers no operator key and exits before the next
connection starts. The helper accepts one valid line matching the expected
session ID; a mismatch, unsupported version or unsafe login prevents execution.
OpenSSH must display banners (`LogLevel=INFO`); `ERROR` suppresses them.
The signed invitation format, forced guard, deadline and revocation are unchanged.
The banner file has mode 0600 and is removed only when its activation ID,
device, inode and exact contents still match the owned file.

The router client must be updated to publish this metadata. Existing build 87 and 90
sessions do not transmit the login: updating the PC helper alone cannot repair
it. Update the client through an ordinary authorized path, then reconnect;
the helper does not guess account names or bypass authentication.

The router uses its existing Dropbear and the package's PHP/OpenSSL. A separate
temporary Dropbear listens only on loopback, disables passwords/forwarding and
forces the live-session/deadline guard for every command. Normal SSH, the router
password, routing, DNS, VPN and firewall settings are not reconfigured.
Private session material stays in `/tmp`; a private persistent journal in the
panel configuration directory records only public-key file recovery data.
Both wall time and uptime deadlines are checked, along with the boot ID.

Hardware validation applies to the devices actually tested. A matching CPU
architecture does not replace testing the firmware and its Dropbear build.
