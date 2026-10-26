# Исходники NFQWS2 ASUS

Код адаптации для ASUS/Entware и нативного OpenWrt.

- `openwrt/` — нативные IPK/APK, procd, netifd, firewall4, установщик и каталог обновлений.
- `asus/` — сборка IPK, службы, чекап, ARK, SmartDNS и модуль старого ядра.
- `webui/web/` — интерфейс и PHP API.
- `core/` — исходная упаковка NFQWS2, Lua и патчи поставщика.
- `support/` — схемы, каталоги и шаблоны.
- `support-relay/`, `updates-feed/` — серверная часть и канал обновлений.
- `tests/` — проверки проекта.

Для сборки нужны Python 3, Node.js, Yarn 4.9.2 и UPX для ARM-пакета.

```sh
cd webui/web
corepack yarn install --immutable
corepack yarn build
cd ../..
python3 asus/build.py --help
```

Точные входные файлы закреплены в `asus/assets.json`. Исходники компонентов,
рецепты и контрольные суммы находятся уровнем выше.
Авторство и лицензии сохранены в `LICENSE`, `THIRD-PARTY-NOTICES.txt` и `UPSTREAM.md`.
