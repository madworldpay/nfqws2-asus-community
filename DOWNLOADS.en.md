# Downloads

[**Open the latest release**](https://github.com/madworldpay/nfqws2-asus-community/releases/latest).
First, identify your firmware and installation environment:

| Installation environment | Which package to choose |
| --- | --- |
| ASUSWRT / Merlin with Entware already installed | `nfqws2-asus_…_armv7.ipk` or `nfqws2-asus_…_aarch64-3.10.ipk`, according to the Entware architecture |
| OpenWrt 24.10 | `nfqws2-native_VERSION_ARCHITECTURE.ipk`, matching the exact `DISTRIB_ARCH` |
| OpenWrt 25.12 | `nfqws2-native_VERSION_ARCHITECTURE.apk`, matching the exact `DISTRIB_ARCH`; the signature is checked by the native OpenWrt installer |

The native file's extension identifies the OpenWrt series, and its name contains the architecture;
check both against `cat /etc/openwrt_release`. The ASUS model alone does not determine the package:
different firmware can run on the same model.

For **ASUS/Entware**, choose an IPK according to the Entware architecture:

| Entware architecture | Filename suffix |
|---|---|
| `armv7-2.6` / `armv7-3.2` | `_armv7.ipk` |
| `aarch64-3.10` | `_aarch64-3.10.ipk` |

Each IPK contains NFQWS2 and the WebUI in RU and EN. SmartDNS is installed
using a separate button in the panel. The installer
automatically selects the current package.

[SHA256 checksums for the latest release](https://github.com/madworldpay/nfqws2-asus-community/releases/latest/download/SHA256SUMS).
The source archive ending in `_source.tar.gz` is available alongside the IPK files in each
release. For your installed version, choose the sources from the same release.
[Sources in the repository](source/).

To install without choosing a file manually, use the [quick start](QUICKSTART.en.md):
the ASUSWRT-Merlin command comes first, followed by the OpenWrt command.

[Project documentation](README.en.md#documentation).
