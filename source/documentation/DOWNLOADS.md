# Загрузки

**[Build 108 для всех поддерживаемых платформ](https://github.com/madworldpay/nfqws2-asus-community/releases/tag/build108)**

[Установить одной командой](QUICKSTART.md#install-command). Для ручного выбора файла используйте таблицу ниже.

| Где устанавливаете | Какой пакет выбрать |
| --- | --- |
| ASUSWRT / Merlin с готовой Entware | `nfqws2-asus_…_armv7.ipk` или `nfqws2-asus_…_aarch64-3.10.ipk` по архитектуре Entware |
| Keenetic или Netcraze с Entware | [Выбрать пакеты](#keenetic) по архитектуре установленной Entware |
| OpenWrt 24.10 | `nfqws2-native_ВЕРСИЯ_АРХИТЕКТУРА.ipk` по точному `DISTRIB_ARCH` |
| OpenWrt 25.12 | `nfqws2-native_ВЕРСИЯ_АРХИТЕКТУРА.apk` по точному `DISTRIB_ARCH`; подпись проверяется нативным установщиком OpenWrt |

Расширение нативного файла определяет серию OpenWrt, имя содержит архитектуру;
сверяйте их с `cat /etc/openwrt_release`. Модель ASUS сама по себе не определяет пакет:
на одной модели могут использоваться разные прошивки.

<a id="keenetic"></a>

## Keenetic и Netcraze

Панель Build 108 использует штатную службу NFQWS2 с движком и Lua zapret2 1.0.8. Нужны Entware и штатная веб-панель `nfqws-keenetic-web` версии `3.0.24` или новее.

Для установки или перехода со старой ревизии запустите [универсальный установщик](README.md#install-command) по SSH. Он проверит пакеты и установит подходящую пару. Узнать архитектуру можно командой `opkg print-architecture`. Если рядом есть вариант с суффиксом `_kn`, используйте основную архитектуру без этого суффикса.

| Архитектура Entware | Панель | Движок |
| --- | --- | --- |
| `aarch64-3.10` | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic-community_1.3.3%2Bb108-3_aarch64-3.10.ipk) | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic_1.3.3%2Bcommunity108-1_aarch64-3.10.ipk) |
| `mips-3.4` | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic-community_1.3.3%2Bb108-3_mips-3.4.ipk) | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic_1.3.3%2Bcommunity108-1_mips-3.4.ipk) |
| `mipsel-3.4` | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic-community_1.3.3%2Bb108-3_mipsel-3.4.ipk) | [IPK](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/nfqws2-keenetic_1.3.3%2Bcommunity108-1_mipsel-3.4.ipk) |

Для Extra KN-1711 производитель указывает MIPSEL. [Инструкция Keenetic для этой модели](https://support.keenetic.ru/eaeu/extra/kn-1711/ru/20980-installing-the-entware-repository-on-a-usb-drive.html).

После установки откройте `http://<адрес-роутера>:90/nfqws-community/`.

## ASUS и OpenWrt

Для **ASUS/Entware** выберите IPK по архитектуре Entware:

| Архитектура Entware | Окончание имени файла |
|---|---|
| `armv7-2.6` / `armv7-3.2` | `_armv7.ipk` |
| `aarch64-3.10` | `_aarch64-3.10.ipk` |

Каждый IPK содержит NFQWS2 и WebUI на RU и EN. SmartDNS устанавливается
отдельной кнопкой в панели. Установщик
сам выбирает актуальный пакет.

[Контрольные суммы SHA‑256 для всех пакетов](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build108/SHA256SUMS).
Архив исходников с окончанием `_source.tar.gz` находится рядом с IPK в каждом
выпуске. Для установленной версии выбирайте исходники из того же выпуска.
[Исходники в репозитории](source/).

[Документация проекта](README.md#документация).
