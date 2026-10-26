# Загрузки

Для **OpenWrt**: [нативная установка и таблица совместимости](OPENWRT.md) ([English](OPENWRT.en.md)).

[**Открыть последний выпуск**](https://github.com/madworldpay/nfqws2-asus-community/releases/latest).
Сначала определите прошивку и среду установки:

| Где устанавливаете | Какой пакет выбрать |
| --- | --- |
| ASUSWRT / Merlin с готовой Entware | `nfqws2-asus_…_armv7.ipk` или `nfqws2-asus_…_aarch64-3.10.ipk` по архитектуре Entware |
| OpenWrt 24.10 | `nfqws2-native_ВЕРСИЯ_АРХИТЕКТУРА.ipk` по точному `DISTRIB_ARCH` |
| OpenWrt 25.12 | `nfqws2-native_ВЕРСИЯ_АРХИТЕКТУРА.apk` по точному `DISTRIB_ARCH`; используйте [нативный установщик](OPENWRT.md#установить) для проверки подписи |

Расширение нативного файла определяет серию OpenWrt, имя содержит архитектуру;
сверяйте их с `cat /etc/openwrt_release`. Модель ASUS сама по себе не определяет пакет:
на одной модели могут использоваться разные прошивки. [Таблица архитектур и устройств](OPENWRT.md#какие-устройства-и-пакеты).

Для **ASUS/Entware** выберите IPK по архитектуре Entware:

| Архитектура Entware | Окончание имени файла |
|---|---|
| `armv7-2.6` / `armv7-3.2` | `_armv7.ipk` |
| `aarch64-3.10` | `_aarch64-3.10.ipk` |

Каждый IPK содержит NFQWS2 и WebUI на RU и EN. SmartDNS устанавливается
отдельной кнопкой в панели. [Установщик одной командой](QUICKSTART.md#1-установить)
сам выбирает актуальный пакет.

[SHA256 последнего выпуска](https://github.com/madworldpay/nfqws2-asus-community/releases/latest/download/SHA256SUMS).
Архив исходников с окончанием `_source.tar.gz` находится рядом с IPK в каждом
выпуске. Для установленной версии выбирайте исходники из того же выпуска.
[Исходники в репозитории](source/).

[Быстрый старт](QUICKSTART.md) · [Ручная установка](MANUAL-INSTALL.md) · [Каталог пресетов](PRESETS.md) · [Совместимость](COMPATIBILITY.md).
