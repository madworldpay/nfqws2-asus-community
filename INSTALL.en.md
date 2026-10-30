# Installation and removal

## ASUSWRT-Merlin / Entware

### Before installation

Back up your ASUS settings.

**If Entware is already working in `/opt`, continue with the installation command.**
On a fresh ASUSWRT-Merlin installation, prepare Entware first:

1. Connect a USB drive with a Linux filesystem — normally ext4; ext2/ext3 also work. Save any files you need before formatting the drive.
2. Enable SSH for the local network under **Administration → System**, then connect to the router using your ASUS administrator account.
3. Run `amtm` over SSH, choose `ep` and wait for Entware installation to finish.
4. Press `e`, then Enter, to leave `amtm` and return to the same SSH shell. Check Entware with `/opt/bin/opkg print-architecture`.

| Entware architecture | IPK |
|---|---|
| `armv7-2.6` / `armv7-3.2` | ARMv7 |
| `aarch64-3.10` | AArch64 |

[Official Entware setup guide](https://github.com/RMerl/asuswrt-merlin.ng/wiki/Entware).

### Install with one command

Connect to the router over SSH with Entware ready and run:

```sh
(
  set -e
  umask 077
  nfqws_dir=/tmp/nfqws2-install.$$
  mkdir "$nfqws_dir"
  trap 'rm -rf "$nfqws_dir"' 0
  curl -fL --connect-timeout 10 --max-time 60 \
    https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh \
    -o "$nfqws_dir/install.sh"
  sh "$nfqws_dir/install.sh"
)
```

The command is the same for supported ARMv7 and AArch64 packages.

The installer downloads the current IPK over HTTPS and verifies SHA256.
The command above uses `curl` supplied with Merlin; the installer also supports GNU `wget`. Installation requires at least 128 MB of free Entware storage
and 32 MB of available RAM. Temporary files are placed in `/opt/tmp` and removed
when finished. The installer does not delete files belonging to other applications.

Start processing in the panel after initial setup. Updates preserve settings
and the chosen on/off service state. If the current version is already installed,
running the command again only prints the panel address.

### Install an IPK

This is the manual installation method. Transfer the file using WinSCP/SCP
or copy it to USB through Samba in your normal file manager.
[File Explorer transfer and USB path mapping](MANUAL-INSTALL.en.md#2-transfer-it-to-the-router).

Verify the downloaded file's SHA256 against the release's `SHA256SUMS`,
copy the IPK to `/opt/tmp/nfqws2-asus.ipk` and run:

```sh
NFQWS_ASUS_NO_START=1 /opt/bin/opkg install /opt/tmp/nfqws2-asus.ipk
```

Processing stays off until setup. Dependencies are installed from Entware.

### First run

Open `http://ROUTER_IP:90`.

**ASUS panel login:** use your router administrator username and password.
If the panel cannot read the ASUS system credentials, it automatically enables the
fallback login: **username `root`, password `asus`**.
A separate panel password set earlier is preserved during updates; use that password.
Use **Change password** to set your own panel password.

**ARK check** offers preparation with a backup only when needed.
Reboot manually to apply it.

Select WAN, clients and a strategy, then save settings. If needed,
open SmartDNS and follow **Check profile → Connect → confirm**.
Then start NFQWS2 and test the service from a client.
IPv6 processing is off by default; this does not disable IPv6 in the firmware.

### Stop or remove

To stop temporarily:

```sh
/opt/etc/init.d/S51nfqws2 stop
```

Save your profile before removal. If SmartDNS is connected, click
**Restore previous DNS** first. To restore the original ARK configuration,
restore its backup before removing the panel. Then run:

```sh
/opt/bin/opkg remove nfqws2-asus
```

The package removes its rules and services. Settings, lists and logs are retained
for reinstallation; Entware and its shared dependencies remain.
If a required configuration file is missing, the package restores the current template
and only the missing default lists needed by that template. Existing files are retained.
If stopping fails, save diagnostics and investigate the cause; do not use force.

## OpenWrt

The native package installs without Entware. Connect to the router over SSH as `root` and run:

```sh
(
  umask 077
  nfqws_dir=/tmp/nfqws2-install.$$
  mkdir "$nfqws_dir" || exit 1
  trap 'rm -rf "$nfqws_dir"' 0
  nfqws_url=https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh
  { curl -fL --connect-timeout 10 --max-time 60 "$nfqws_url" -o "$nfqws_dir/install.sh" || uclient-fetch -T 20 -O "$nfqws_dir/install.sh" "$nfqws_url"; } &&
  sh "$nfqws_dir/install.sh"
)
```

After installation, open the panel address, select devices and a strategy,
save settings and start NFQWS2. To stop: `/etc/init.d/nfqws2-native stop`.
Before removal, save your profile and restore the previous DNS through SmartDNS.
Remove with `opkg remove nfqws2-native` on 24.10 or `apk del nfqws2-native` on 25.12.

[Project documentation](README.en.md#documentation).
