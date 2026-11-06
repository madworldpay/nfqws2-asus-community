# Updates

## Lua copies and settings preservation: Build 90

An old worker could reject an installed package because `opkg` left a factory `*.lua-opkg` copy. The ASUS package now preserves existing alternatives before unpacking, restores their contents and permissions afterwards, and removes only its own verified new factory duplicates. Owner edits, Lua and blobs are retained.

If an old panel reports `settings_changed` **before downloading**, use the current standalone installer for the first transition. Checking for an update cannot replace the installed old worker.

## Updating older builds

**Updating an older build to Build 74 or later requires the installer once.**
Current releases use a new signing key. Rerun the usual installer command for
your platform to complete the transition. Subsequent updates are available
through the panel with signature and SHA256 verification.

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
and updating do not require a VPS.

## Slow USB writes on ASUS: Build 85/86 → 87

On some USB drives, Build 85/86 snapshot creation exceeded the fixed 240-second limit before package replacement began. Build 87 and the current standalone installer estimate preparation time using the checked file count and two durable-write probes on the same drive, up to 30 minutes. Network timeouts and checks remain separate; an already-running package manager is not interrupted. The operation log retains the calculation in `apply-budget.json`.

If the old worker fails with `timed_out`, run the usual installer command below once. It preserves settings and former service state. Removing NFQWS2, formatting USB and rebooting are unnecessary for this transition.

## Snapshot preparation on older ASUS routers and Build 84

Build 84 fixes a separate PHP CPU limit that could stop snapshot preparation
on a slower ASUS before package replacement began. If the old panel fails at
this step, rerun the usual installer command below once. It uses the corrected
standalone worker and preserves settings. An already installed old worker does
not change before the new package is installed.

The current installer also handles older Entware configurations with an 8 MiB
PHP limit. Only the validated background bootstrap receives a 32 MiB allowance
and releases extracted buffers before package inspection. The global `php.ini`
and web-panel limits are unchanged. Build 84 packages have not been replaced
for this installer repair; rerunning the command fetches the corrected script.

The installer also fixes a false `timed_out` during worker startup on older
ASUS routers. An exec transition within the same process is now recognized.
Live-worker, deadline and package-manager checks remain enforced. The standalone
installer includes this repair; the panel includes it from Build 85.

## Interrupted ASUS installation

From Build 81, the installer can finish an interrupted NFQWS2 ASUS installation.
For an older panel, rerun the usual installer command: it verifies the interrupted
package's signature, exact version and installed files before continuing to the
latest release. Other unfinished Entware packages and active operations still
block the update; rebooting does not replace those checks.

**The November 6, 2026 installer** also handles older packages that did not yet list Lua as configuration files. An edited Lua file is preserved when its factory counterpart is verified against the signed package. This resolves one `recovery_required` case during recovery of an interrupted old installation. Factory files, binaries and installation scripts remain checked; other mismatches still require the log. Build 89 packages were not replaced for this installer fix.

An SSH disconnect does not cancel an installation already running in the
background. On failure, the installer shows the retained log path. Check the
final status before starting the service manually.

## Backup and service restoration on ASUS in Build 85

Checking a release, downloading and preparing the package leave services running.
When you click **Install update**, the updater records their state and stops
NFQWS2 and its related writers. It then saves the final settings, lists and old
package for recovery, installs the new package and verifies the result.
Services return to their previous state: a stopped NFQWS2 stays stopped.
The active strategy is preserved even if the saved editor draft differs.

If a failure occurs before package replacement, the updater verifies the old
installation before restoring its services. After replacement has begun, a
verified rollback restores the previous package and settings. If restoration
cannot be verified, the updater keeps the backup and log and reports the reason.
It does not start an unverified or partly installed version.

Since Build 87, the normal worker can stop the panel while retaining an existing technical channel; the exception applies only to the verified installation process. The connection and original expiry remain unchanged. Manual panel stop, channel disconnect and expiry still end access. On the first transition from Build 85/86, old code may close the channel; reconnect using the same valid invitation. An already disconnected channel is not recreated automatically.
The technical-channel expiry is never extended automatically. Losing power or
all update controllers does not justify replaying an old start request after a
reboot; such an interrupted operation requires a new verified recovery.

**First transition from an older panel:** if it fails before installation, rerun
the usual installation command below once. The old installed worker cannot gain
this fix before package replacement; the current command runs the corrected
standalone coordinator. Settings and the chosen service state are preserved.

A direct `opkg install` does not run this backup-and-rollback workflow. Native
OpenWrt retains its own package verification and service-state restoration;
full automatic package rollback in this section applies to ASUS / Entware.

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

1. **Prepare package** — download it and verify the signature, compatibility and free space.
2. **Install update** — wait for the result. On ASUS, services are stopped,
   a backup is created, the package is replaced and the previous service state is restored.

The panel may disconnect temporarily. Closing the tab does not cancel installation.
The updater preserves settings, lists, login credentials and the chosen on/off service state.
It does not change firmware, ARK or routes; no reboot is required.

Previously confirmed SmartDNS is restored with its saved profile,
even if the editor contains a different draft. The draft is retained.
If you clicked **Restore previous DNS**, the update does not reconnect SmartDNS.
After updating, check the version, service state and DNS:
**SmartDNS connected** accounts for both the process and the actual request path.
If restoration is incomplete, the panel shows the reason and guidance.

## Phases, failures and the operation log

The update window shows the current phase and percentage of phases completed, rather than time remaining. A failure retains the original phase and reason even if the old version is restored afterwards. **Copy error** includes versions, phase, codes and operation number. A current panel-connection error is shown separately.

## OpenWrt: stop, backup and restoration

The background installer and stop controller use an external supervisor; ordinary web requests retain their PHP limit. A running OPKG/APK process is not terminated on a timeout. The settings backup uses RAM, so the Entware USB write-latency estimate does not apply.

Settings identity is recorded before stopping services and refreshed for the final copy. A failed partial copy is not treated as a damaged installed package. Former services return only after checks of the old package, version, unrelated packages and settings. A previously running service receives a fresh stop/start to restore processing after an incomplete stop; a previously stopped service remains stopped.

A partially replaced package is not started without verification: the log is retained and package recovery is required. For a saved `pending_packages` state, use the supported recovery path rather than editing the OPKG/APK database manually.

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

### OpenWrt

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

Older panels may have supported only a private channel. After updating,
you can install through the panel without a token or GitHub account.

The panel verifies the release signature with a pinned key, then the package size
and SHA256. Installation does not start if verification fails.
An existing private channel configured by the operator remains in use.

See **Backup and service restoration on ASUS in Build 85** above for automatic restoration
of the previous ASUS package.

If package preparation is interrupted, you can retry installation.
Custom submission channel settings are retained.

[Project documentation](README.en.md#documentation).
