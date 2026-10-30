# Compatibility

## Tested devices

| Model | Firmware | Entware | Notes |
|---|---|---|---|
| GT-BE19000AI | Merlin 3006.102.9_0 | `aarch64-3.10` | ARK check and preparation with a backup |
| RT-AC87U | Merlin 384.13_10 | `armv7-2.6` | Working USB drive; additional module for this exact combination |

Installation and updates, the WebUI, importing with restoration of the original profile,
IPv4 traffic processing, and restoration of confirmed SmartDNS settings have been tested.
DPI Detector network checks have been run. On the GT-BE19000AI, switching
Amnezia on and off alongside SmartDNS was also tested. Results for a particular service and speed
depend on the connection, DNS, strategy, and traffic path; check them from your own device.

## Other devices and firmware

The two IPK files target `armv7-2.6` / `armv7-3.2` and `aarch64-3.10`.
The table above lists the checks performed, rather than every potentially compatible
model. For another combination, the Entware package architecture, NFQUEUE support, and actual
delivery of packets to the queue matter.

Firmware integration uses ASUS data, and SmartDNS integration uses a Merlin
JFFS script. When testing other firmware, these parts also need to be checked or adapted.
Successful results on another device are useful to the project: in **“Export / share”**,
provide the model, firmware, and result, check the preview, and submit the profile.

The RT-AC87U was tested with 256 MiB of RAM. This is the device's capacity, not a general minimum:
memory use depends on lists, the strategy, and DNS. USB does not increase RAM.
The checkup shows the current resource status and component availability.

A regular installation does not change ARK. If the kernel rejects the required rules,
the service reports an error; a running process alone does not prove that bypass works.

## OpenWrt

The native package has been tested on the RT-AC87U with OpenWrt 24.10. For other devices,
use the OpenWrt series and exact `DISTRIB_ARCH`, rather than just the model name.
[Table of architectures, models, and testing status](OPENWRT.en.md#devices-and-package-compatibility).

[Project documentation](README.en.md#documentation).
