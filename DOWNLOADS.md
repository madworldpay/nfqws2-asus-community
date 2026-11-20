# Загрузки

[**Открыть последний выпуск**](https://github.com/madworldpay/nfqws2-asus-community/releases/latest).
Сначала определите прошивку и среду установки:

| Где устанавливаете | Какой пакет выбрать |
| --- | --- |
| ASUSWRT / Merlin с готовой Entware | `nfqws2-asus_…_armv7.ipk` или `nfqws2-asus_…_aarch64-3.10.ipk` по архитектуре Entware |
| KeeneticOS с Entware на Keenetic или Netcraze | [Выбрать IPK панели](#keenetic) по архитектуре установленной Entware |
| OpenWrt 24.10 | `nfqws2-native_ВЕРСИЯ_АРХИТЕКТУРА.ipk` по точному `DISTRIB_ARCH` |
| OpenWrt 25.12 | `nfqws2-native_ВЕРСИЯ_АРХИТЕКТУРА.apk` по точному `DISTRIB_ARCH`; подпись проверяется нативным установщиком OpenWrt |

Расширение нативного файла определяет серию OpenWrt, имя содержит архитектуру;
сверяйте их с `cat /etc/openwrt_release`. Модель ASUS сама по себе не определяет пакет:
на одной модели могут использоваться разные прошивки.

<a id="keenetic"></a>

## Keenetic и Netcraze

Панель Build 101 устанавливается рядом со штатной веб-панелью. Для неё нужны Entware, `nfqws2-keenetic` версии `1.3.3` и `nfqws-keenetic-web` версии `3.0.24` или новее. Установка сохраняет конфигурацию штатной службы. [Штатный NFQWS2](https://github.com/nfqws/nfqws2-keenetic) · [Штатная веб-панель](https://github.com/nfqws/nfqws-keenetic-web).

В терминале Entware выполните `opkg print-architecture`. Найдите свою архитектуру в таблице и скачайте один файл.

| Архитектура Entware | Пакет Build 101 |
| --- | --- |
| `aarch64-3.10` | [Скачать ARM64](https://github.com/madworldpay/nfqws2-asus-community/releases/download/keenetic-build101-r2/nfqws2-keenetic-community_1.3.3%2Bb101-2_aarch64-3.10.ipk) |
| `mips-3.4` | [Скачать MIPS](https://github.com/madworldpay/nfqws2-asus-community/releases/download/keenetic-build101-r2/nfqws2-keenetic-community_1.3.3%2Bb101-2_mips-3.4.ipk) |
| `mipsel-3.4` | [Скачать MIPSEL](https://github.com/madworldpay/nfqws2-asus-community/releases/download/keenetic-build101-r2/nfqws2-keenetic-community_1.3.3%2Bb101-2_mipsel-3.4.ipk) |

Для Extra KN-1711 производитель указывает MIPSEL. [Инструкция Keenetic для этой модели](https://support.keenetic.ru/eaeu/extra/kn-1711/ru/20980-installing-the-entware-repository-on-a-usb-drive.html).

Сверьте SHA-256, скопируйте IPK на роутер и в его каталоге выполните `opkg install ./имя-файла.ipk`, подставив имя скачанного файла. Затем откройте `http://<адрес-роутера>:90/nfqws-community/`. [Выпуск, контрольные суммы и исходники](https://github.com/madworldpay/nfqws2-asus-community/releases/tag/keenetic-build101-r2).

## ASUS и OpenWrt

Для **ASUS/Entware** выберите IPK по архитектуре Entware:

| Архитектура Entware | Окончание имени файла |
|---|---|
| `armv7-2.6` / `armv7-3.2` | `_armv7.ipk` |
| `aarch64-3.10` | `_aarch64-3.10.ipk` |

Каждый IPK содержит NFQWS2 и WebUI на RU и EN. SmartDNS устанавливается
отдельной кнопкой в панели. Установщик
сам выбирает актуальный пакет.

[SHA256 последнего выпуска](https://github.com/madworldpay/nfqws2-asus-community/releases/latest/download/SHA256SUMS).
Архив исходников с окончанием `_source.tar.gz` находится рядом с IPK в каждом
выпуске. Для установленной версии выбирайте исходники из того же выпуска.
[Исходники в репозитории](source/).

Для установки без ручного выбора файла используйте [быстрый старт](QUICKSTART.md):
сначала приведена команда для ASUSWRT-Merlin, ниже — для OpenWrt.

[Документация проекта](README.md#документация).
