# Component origins

Full notices: [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).
[Release status](DOWNLOADS.en.md).

## Component licenses

The MIT license in [LICENSE](LICENSE) applies to our adaptation code. Third-party components
retain their own licenses and copyright notices.

NFQWS2 Keenetic, WebUI Keenetic, zapret2, and DPI Detector retain their MIT notices.
BusyBox and the legacy kernel module use GPLv2; netfilter libraries use GPLv2/LGPLv2.1.
lighttpd uses BSD-3-Clause. LuaJIT, musl, Rust, and the interface dependencies
retain their own notices. SmartDNS uses GPLv3; versions for the different platforms are described below.
The full list of attributions and terms is preserved in [THIRD-PARTY-NOTICES.txt](THIRD-PARTY-NOTICES.txt).

## Origins and changes

This is an independent community adaptation for ASUS/Entware and OpenWrt, not an official
package from ASUS, Entware, or the authors of the original projects.

In the **ASUS/Entware** packages, the SmartDNS installer uses the official
[Release48.4](https://github.com/pymumu/smartdns/releases/tag/Release48.4).
The sizes and SHA256 checksums of the ARM/AArch64 packages, engine, and bundled libraries are pinned
in `support/smartdns-catalog.json`. The binaries are unchanged and are not included
in the main IPK: they are downloaded after the user's consent. The engine's license is GPLv3. The stock init/UI
and installation scripts from that package are not run. Sources, attribution, and
license terms: [pymumu/smartdns](https://github.com/pymumu/smartdns/tree/Release48.4).

The **native OpenWrt packages** use the system PHP, uhttpd, and firewall4.
The bundled SmartDNS comes from official OpenWrt packages: 1.2023.43 for 24.10
and 46.1 for 25.12. Its binaries are unchanged; the component is enabled separately
in the panel. Exact inputs and SHA256 checksums: [smartdns-assets.json](source/project/openwrt/smartdns-assets.json).
The corresponding sources and recipe snapshots are included in the release archive:
[sources](source/metadata/openwrt-smartdns-sources.json),
[OpenWrt recipes](source/recipes/openwrt-smartdns/README.md).
Native packages do not include the legacy ASUS kernel module or the private Entware runtime.

- `core/`: https://github.com/nfqws/nfqws2-keenetic — imported commit
  `5d155f33ab00f3a4879c485c1094e8ec1e014586`, package v1.3.2; MIT, original attribution preserved.
- `webui/`: https://github.com/nfqws/nfqws-keenetic-web — imported commit
  `c225df3`; MIT, original attribution preserved. The interface has been adapted for ASUS.
- NFQWS2 ARMv7/AArch64 and Lua come from the specified package. The AArch64 binary
  is preserved byte for byte; the ARMv7 binary was unpacked from UPX for compatible
  process checks on the legacy kernel. The engine's machine code and algorithms were not rewritten;
  its zapret2 version is v1.0.6,
  `221d7dff24bfec0cd5ac0a5070b8acef2008af3d`.
  Sources: https://github.com/bol-van/zapret2/tree/221d7dff24bfec0cd5ac0a5070b8acef2008af3d
  The supplier's build recipe and patches are in `core/.github/workflows/`
  and `core/patches/`. The main project's license is MIT; third-party libraries
  retain their own licenses.
- lighttpd 1.4.82-2 and mod_cgi of the same version come from Entware armv7sf-k3.2/aarch64-k3.10
  (BSD-3-Clause). They are installed at private paths, without the standard S80lighttpd.
  Sources: https://github.com/lighttpd/lighttpd1.4/tree/lighttpd-1.4.82
  Entware recipe: https://github.com/Entware/entware-packages/tree/master/net/lighttpd
  mod_rewrite and mod_setenv are built into this binary.
- For Entware `armv7sf-k2.6`, private BusyBox
  1.36.1-1b and lighttpd/mod_cgi 1.4.71-1 have been added to the ARMv7 package. Sources:
  https://busybox.net/downloads/busybox-1.36.1.tar.bz2 and
  https://download.lighttpd.net/lighttpd/releases-1.4.x/lighttpd-1.4.71.tar.xz
  Historical BusyBox recipe, config, and patches:
  https://github.com/Entware/Entware/tree/cb2ce7f6f062ed4342a686aa68d895d16ba91f64/package/utils/busybox
  https://github.com/Entware/Entware/blob/cb2ce7f6f062ed4342a686aa68d895d16ba91f64/configs/armv7-2.6.config
  lighttpd recipe:
  https://github.com/Entware/entware-packages/tree/473cdf322ba2ad0a50079ce85e110fcb3770943e/net/lighttpd
  The BusyBox sources, configurations, patches, and Entware recipes are included
  in the release source archive.
- Exact URLs and SHA256 checksums of binary inputs are recorded in `asus/assets.json`.
  The build refuses to use a file with a mismatched checksum.
- BusyBox 1.37.0-6 from Entware (GPL-2.0) is used as a private shell
  and set of utilities for this service only. Global Entware symlinks are unchanged.
  This removes the dependency on the limited ASUS shell and the first-installation error
  in the standard BusyBox, whose preinst already requires `/opt/bin/busybox`.
  BusyBox sources: https://busybox.net/downloads/busybox-1.37.0.tar.bz2
  Entware build: https://github.com/Entware/Entware/tree/36db8558ac7840d993cb11df1e47e0326d681077/package/utils/busybox
- Frontend dependency license notices are added to the combined package
  from the modules installed according to `yarn.lock`.

ASUS changes: a separate service, NFQUEUE rules, WAN and client selection,
model and kernel capability checks, recovery through cru, a separate
web server, ASUS authentication, disabled Keenetic updates, and IPK packaging.
The UI/API domain check has been removed from the ASUS version. IPv6 is available as a separate
option, disabled by default; the arguments preserve upstream IPv4/IPv6 binding.
The built-in Lua scripts are included in the package; custom ASUS adapters are supplied separately.
The way the ARMv7 binary is supplied is detailed above.
The project owner's personal names and contact details are not added to the metadata.

For the exact RT-AC87U / Merlin 384.13_10 combination, the ARMv7 package contains an additional
`nfnetlink_queue.ko` from Linux 2.6.36 GPLv2. The `nfnetlink_queue.c` source is
unchanged: [Merlin commit 26e1f3f17a2f29ba7cb9013c67142f8a8c8adfd7](https://github.com/RMerl/asuswrt-merlin.ng/tree/26e1f3f17a2f29ba7cb9013c67142f8a8c8adfd7/release/src-rt-6.x.4708/linux/linux-2.6.36).
The project preserves the source, COPYING, configuration, Module.symvers, flags,
and reproduction recipe in `asus/legacy/rt-ac87u-384.13_10/`.
The loader checks the model, firmware release, architecture, and stock files;
vermagic/MODVERSIONS checks have not been weakened. This module is not in the AArch64 package.

ASUS browser favicon: https://www.asus.com/favicon.ico (PNG supplied by ASUS; ASUS trademark belongs to ASUSTeK, no endorsement implied).

DPI Detector: https://github.com/Runnin4ik/dpi-detector, MIT. Optional binaries are pinned to v5.0.0-alpha.21 / a09d03b58d452c71bd63a9b3d410713dd22049f6. The original notice is in support/dpi-detector-MIT.txt; the catalog of URLs, SHA256 checksums, and sizes is in support/dpi-catalog.json. For `armv7-2.6`, the ARM package contains a compatible ARMv5TE soft-float build of the same unchanged sources; the algorithms have not been changed. The file is supplied as non-executable data and activated after consent, with SHA256, ELF, and version checks. For `armv7-3.2` and AArch64, the official downloadable files are preserved; postinst does not run DPI. Recipe and tools: `asus/dpi/legacy/README.md` and `build.py`.

## Libraries and additional notices

The engine recipe includes LuaJIT/OpenResty, musl, zlib, and netfilter libraries:
libmnl1.0.5 (LGPLv2.1), libnfnetlink1.0.2, and libnetfilter_queue1.0.5 (GPLv2).
For the compatible DPI build, notices have been added for 173 source Rust dependencies,
the Rust1.98.1 standard library, and musl from Zig0.13.0.
433 frontend notice files are preserved unchanged in the IPK.

The complete LICENSE and THIRD-PARTY-NOTICES are included in the IPK. They contain the exact notices for zlib1.3.2, musl1.2.5, and GCC15.2.0 with the Runtime Library
Exception. The versions were checked against the official build log and pinned tools.

The release source archive contains the ASUS code, component sources, configurations,
patches, and recipes. The exact build was reproduced for the 87U module; a full rebuild of all
external libraries is not claimed. [Download the sources](DOWNLOADS.en.md).

[Project documentation](README.en.md#documentation).
