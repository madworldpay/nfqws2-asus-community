# Происхождение компонентов

Описание соответствует компонентам проверяемой сборки Build 60.
[Состояние выпуска](DOWNLOADS.md).

Это самостоятельная экспериментальная адаптация для ASUS, не официальный
пакет ASUS, Entware или авторов исходных проектов.

Необязательный установщик SmartDNS использует официальный
[Release48.4](https://github.com/pymumu/smartdns/releases/tag/Release48.4).
Размеры и SHA256 пакетов ARM/AArch64, движка и комплектных библиотек закреплены
в `support/smartdns-catalog.json`. Бинарные файлы не изменяются и не включаются
в основной IPK: они загружаются после согласия пользователя. Штатные init/UI
и установочные скрипты этого пакета не выполняются. Исходники, авторство и
условия лицензии: [pymumu/smartdns](https://github.com/pymumu/smartdns/tree/Release48.4).

- `core/`: https://github.com/nfqws/nfqws2-keenetic — импорт коммита
  `077f9af`, пакет v1.3.1; MIT, исходное авторство сохранено.
- `webui/`: https://github.com/nfqws/nfqws-keenetic-web — импорт коммита
  `c225df3`; MIT, исходное авторство сохранено. Интерфейс адаптирован для ASUS.
- NFQWS2 ARMv7/AArch64 и Lua взяты из указанного пакета. AArch64-бинарник
  сохранён побайтно; ARMv7-бинарник распакован из UPX для совместимой проверки
  процесса на старом ядре. Машинный код и алгоритмы движка не переписывались;
  его версия zapret2 — v1.0.5.2,
  `6b6c63e3385fa73f8af3be4a69171e947f5a319d`.
  Исходники: https://github.com/bol-van/zapret2/tree/6b6c63e3385fa73f8af3be4a69171e947f5a319d
  Рецепт сборки и патчи поставщика находятся в `core/.github/workflows/`
  и `core/patches/`. Лицензия основного проекта MIT; сторонние библиотеки
  сохраняют собственные лицензии.
- Из Entware armv7sf-k3.2/aarch64-k3.10 взяты lighttpd 1.4.82-2 и mod_cgi той же версии
  (BSD-3-Clause). Устанавливаются по частным путям, без стандартного S80lighttpd.
  Исходники: https://github.com/lighttpd/lighttpd1.4/tree/lighttpd-1.4.82
  Рецепт Entware: https://github.com/Entware/entware-packages/tree/master/net/lighttpd
  mod_rewrite и mod_setenv встроены в этот бинарник.
- Для Entware `armv7sf-k2.6` в ARMv7-пакет добавлены частные BusyBox
  1.36.1-1b и lighttpd/mod_cgi 1.4.71-1. Исходники:
  https://busybox.net/downloads/busybox-1.36.1.tar.bz2 и
  https://download.lighttpd.net/lighttpd/releases-1.4.x/lighttpd-1.4.71.tar.xz
  Исторический рецепт BusyBox, config и patches:
  https://github.com/Entware/Entware/tree/cb2ce7f6f062ed4342a686aa68d895d16ba91f64/package/utils/busybox
  https://github.com/Entware/Entware/blob/cb2ce7f6f062ed4342a686aa68d895d16ba91f64/configs/armv7-2.6.config
  Рецепт lighttpd:
  https://github.com/Entware/entware-packages/tree/473cdf322ba2ad0a50079ce85e110fcb3770943e/net/lighttpd
  Для будущей публичной поставки BusyBox подготовить соответствующий комплект
  исходников с конфигурацией, патчами и скриптами сборки рядом с бинарниками.
- Точные URL и SHA256 бинарных входов зафиксированы в `asus/assets.json`.
  Сборка отказывается использовать файл с несовпадающей контрольной суммой.
- BusyBox 1.37.0-6 из Entware (GPL-2.0) используется как частная оболочка
  и набор утилит только этой службы. Глобальные symlink Entware не меняются.
  Это устраняет зависимость от урезанной оболочки ASUS и ошибку первой установки
  стандартного BusyBox, чей preinst уже требует `/opt/bin/busybox`.
  Исходники BusyBox: https://busybox.net/downloads/busybox-1.37.0.tar.bz2
  Сборка Entware: https://github.com/Entware/Entware/tree/master/package/utils/busybox
- Уведомления о лицензиях frontend-зависимостей добавляются в объединённый пакет
  из установленных по `yarn.lock` модулей.

Изменения ASUS: отдельная служба, правила NFQUEUE, выбор WAN и клиентов,
проверка модели и возможностей ядра, восстановление через cru, отдельный
веб-сервер, аутентификация ASUS, отключение обновлений Keenetic и сборка IPK.
Из ASUS-версии удалена проверка доменов UI/API. IPv6 доступен отдельной
опцией, по умолчанию выключен; аргументы сохраняют upstream binding IPv4/IPv6.
Встроенные Lua входят в пакет; собственные адаптеры ASUS поставляются отдельно.
Способ поставки ARMv7-бинарника уточнён выше.
Личные имена и контакты владельца этого проекта в метаданные не добавляются.

Для точного RT-AC87U / Merlin 384.13_10 ARMv7-пакет содержит дополнительный
`nfnetlink_queue.ko` из Linux 2.6.36 GPLv2. Исходник `nfnetlink_queue.c` не
изменён: [Merlin commit 26e1f3f17a2f29ba7cb9013c67142f8a8c8adfd7](https://github.com/RMerl/asuswrt-merlin.ng/tree/26e1f3f17a2f29ba7cb9013c67142f8a8c8adfd7/release/src-rt-6.x.4708/linux/linux-2.6.36).
В проекте сохранены исходник, COPYING, конфигурация, Module.symvers, флаги
и рецепт воспроизведения в `asus/legacy/rt-ac87u-384.13_10/`.
Загрузчик сверяет модель, выпуск прошивки, архитектуру и штатные файлы;
проверки vermagic/MODVERSIONS не ослаблены. В AArch64-пакете этого модуля нет.

ASUS browser favicon: https://www.asus.com/favicon.ico (PNG supplied by ASUS; ASUS trademark belongs to ASUSTeK, no endorsement implied).

DPI Detector: https://github.com/Runnin4ik/dpi-detector, MIT. Необязательные бинарники закреплены на v5.0.0-alpha.21 / a09d03b58d452c71bd63a9b3d410713dd22049f6. Оригинальное уведомление — support/dpi-detector-MIT.txt; каталог URL, SHA256 и размеров — support/dpi-catalog.json. Для `armv7-2.6` ARM-пакет содержит совместимую ARMv5TE soft-float сборку тех же неизменённых исходников; алгоритмы не менялись. Файл поставляется неисполняемыми данными и активируется после согласия с проверкой SHA256, ELF и версии. Для `armv7-3.2` и AArch64 сохранены официальные скачиваемые файлы; postinst DPI не запускает. Рецепт и инструменты: `asus/dpi/legacy/README.md` и `build.py`.
