# Native SmartDNS inputs / исходники нативного SmartDNS

Our native package copies the SmartDNS executable from the matching official
OpenWrt package without patching its binary. It installs the executable only
when enabled in the panel; OpenWrt's standard SmartDNS init/config is not run.

- OpenWrt 24.10: SmartDNS 1.2023.43, upstream commit `1ba6ee7cb98b5b6448bc2a2be318eb3518d4de79`.
- OpenWrt 25.12: SmartDNS Release46.1.
- Source archives are in `../../sources/`; hashes and recipe snapshots are in
  `../../metadata/openwrt-smartdns-sources.json`.
- Exact official binary input packages, architectures, sizes and SHA256 are in
  `../../project/openwrt/smartdns-assets.json`.
- GPL-3.0-or-later text: `../../project/licenses/smartdns-GPL3.txt`.

To rebuild, use the official OpenWrt SDK matching the package series and target.
Add the OpenWrt packages feed at the recorded commit, use the saved
`net/smartdns/Makefile`, and run `make package/feeds/packages/smartdns/compile V=s`.
The recipe records the source revision, build path, version macro and native
OpenSSL dependency. For 24.10, the included GitHub source tarball is pinned to
the exact upstream commit; its compression/hash differs from OpenWrt's generated
mirror tarball. It can be unpacked into the recipe's build directory for an
offline build. The source archive includes all upstream OpenWrt integration
files used by the recipe. SDK/compiler revisions affect binary reproducibility;
the supplied binary's identity is established by its recorded SHA256.

Нативный пакет использует бинарники официальных пакетов OpenWrt без изменения.
Для воспроизведения нужны SDK той же серии/целевой платформы, сохранённый рецепт
и соответствующий архив исходников. `Makefile` фиксирует версию, ревизию,
параметр `VER` и зависимость OpenSSL. Хеши наших исходных архивов и двоичных
входов записаны отдельно: сжатие исходников GitHub и зеркала OpenWrt различается.
