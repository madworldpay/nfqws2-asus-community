# Происхождение компонентов

Это самостоятельная экспериментальная адаптация для ASUS, не официальный
пакет ASUS, Entware или авторов исходных проектов.

- `core/`: https://github.com/nfqws/nfqws2-keenetic — импорт коммита
  `077f9af`, пакет v1.3.1; MIT, исходное авторство сохранено.
- `webui/`: https://github.com/nfqws/nfqws-keenetic-web — импорт коммита
  `c225df3`; MIT, исходное авторство сохранено. Интерфейс адаптирован для ASUS.
- NFQWS2 ARMv7/AArch64 и Lua взяты из указанного пакета без изменения бинарника;
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
Бинарник NFQWS2 и Lua не изменены.
Личные имена и контакты владельца этого проекта в метаданные не добавляются.

ASUS browser favicon: https://www.asus.com/favicon.ico (PNG supplied by ASUS; ASUS trademark belongs to ASUSTeK, no endorsement implied).

## DPI Detector

Необязательный компонент [Runnin4ik/dpi-detector](https://github.com/Runnin4ik/dpi-detector), MIT, закреплённый предварительный выпуск v5.0.0-alpha.21 (`a09d03b58d452c71bd63a9b3d410713dd22049f6`). Отдельная установка с проверкой TLS/SHA256; бинарник в IPK не включён. Ограничения интеграции описаны в DPI-DETECTOR.md.
