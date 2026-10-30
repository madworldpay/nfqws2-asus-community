# Updates

## One-time signing-key transition

**Updating an older build to Build 74 or later requires the installer once.**
The previous private signing key was lost when the server was deleted, with no
backup remaining. Older panels trust that key and cannot verify a release
signed with the new one. The new release may therefore not appear in an older panel.

This update restores the path for future fixes and features through the panel.
Build 74 adds strategy dates and a temporary technical channel by prior arrangement
with the Administrator, and fixes repeated service stops on OpenWrt and the
explanation of SmartDNS validation failures. If you missed the catalog-source
update, this transition also restores access to current strategies and submissions
to the project.

1. Connect to your router over SSH and run the command for your platform below once.
2. When it finishes, open the panel and check the version, service state and DNS.
3. Install subsequent updates using the panel's usual buttons.

Settings, lists, login credentials and the chosen service state are preserved.
Strategies already applied keep working before the transition too.

Old metadata URLs retain the previous signed release; the new key is not substituted
through the old channel. Obtain the new installer over GitHub HTTPS: the ASUS branch
checks the package against the release's `SHA256SUMS`; the OpenWrt branch also
verifies its signature with the new embedded key.

The strategy catalog and submission receiver run on ASUS, submissions are delivered
to the project's Gmail inbox, and releases come from GitHub. Importing, submitting
and updating do not require a VPS. The new signing key is stored separately from
the delivery server and has a backup; moving services does not itself require a key change.

## Through the panel

The panel automatically checks current public GitHub releases.
Click **Check for updates** to find an available release for your platform.

**Changes since your version** shows the descriptions of all published
intermediate builds, including the target build, from oldest to newest.
Descriptions load automatically from public GitHub releases when you open the window,
without signing in to GitHub. Release text is shown in its original language.
If the complete history cannot be loaded, the panel says so and keeps the
target release description available. Package preparation and installation
remain available, with all package verification checks retained.

This feature requires a panel that supports it: older published panels
get the new interface only after they are updated.

After reviewing the changes:

1. **Prepare package** — download it, verify the signature, compatibility and free space,
   and save a settings snapshot.
2. **Install update** — replace the package and wait for the result.

The panel may disconnect temporarily. Closing the tab does not cancel installation.
The updater preserves settings, lists, login credentials and the chosen on/off service state.
It does not change firmware, ARK or routes; no reboot is required.

Previously confirmed SmartDNS is restored with its saved profile,
even if the editor contains a different draft. The draft is retained.
If you clicked **Restore previous DNS**, the update does not reconnect SmartDNS.
After updating, check the version, service state and DNS:
**SmartDNS connected** accounts for both the process and the actual request path.
If restoration is incomplete, the panel shows the reason and guidance.

## Manually

**ASUSWRT-Merlin / Entware:**

Download the IPK for your architecture from the [latest release](https://github.com/madworldpay/nfqws2-asus-community/releases/latest),
verify SHA256 against `SHA256SUMS` and copy the file to `/opt/tmp/nfqws2-asus.ipk`.
To install with processing off, run:

```sh
NFQWS_ASUS_NO_START=1 /opt/bin/opkg install /opt/tmp/nfqws2-asus.ipk
```

To install and start the service, use the same command without `NFQWS_ASUS_NO_START=1`.
A regular `opkg install` may start a previously stopped NFQWS2;
the panel and one-command installer preserve the chosen state automatically.

Reinstallation preserves retained settings. The package also restores a missing
required configuration file from its current template. If the configuration file
exists, deliberately deleted lists are not restored.
If installation is interrupted, save its output and `opkg status nfqws2-asus`:
these help distinguish an installation error from incomplete DNS restoration.
In the panel, open **Export / share**, collect diagnostics,
review the preview and download the JSON or send it to the project.

For OpenWrt, rerun the native installer command below;
use the native package rather than the ASUS/Entware package.

## If an old panel cannot find an update

Rerun the installer for your platform over SSH on the router.
It updates the package and preserves the previous service state.

### ASUSWRT-Merlin / Entware

```sh
( nfqws_url=https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh; nfqws_file=$(mktemp) && trap 'rm -f "$nfqws_file"' 0 && { curl -fL --connect-timeout 10 --max-time 60 "$nfqws_url" -o "$nfqws_file" || wget --https-only -T 20 -t 2 -O "$nfqws_file" "$nfqws_url"; } && sh "$nfqws_file" )
```

### OpenWrt

```sh
( nfqws_url=https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/install.sh; nfqws_file=$(mktemp) && trap 'rm -f "$nfqws_file"' 0 && { curl -fL --connect-timeout 10 --max-time 60 "$nfqws_url" -o "$nfqws_file" || uclient-fetch -T 20 -O "$nfqws_file" "$nfqws_url"; } && sh "$nfqws_file" )
```

Older panels may have supported only a private channel. After updating,
you can install through the panel without a token or GitHub account.

The panel verifies the release signature with a pinned key, then the package size
and SHA256. Installation does not start if verification fails.
An existing private channel configured by the operator remains in use.

A published Build number is not reused for different contents.
There is no automatic package version rollback.

If package preparation is interrupted, you can retry installation.
Custom submission channel settings are retained.

[Project documentation](README.en.md#documentation).
