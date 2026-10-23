# NFQWS2 1.0.6

Пакет поставщика: NFQWS2 Keenetic 1.3.2, commit `5d155f33ab00f3a4879c485c1094e8ec1e014586`.
Движок: zapret2 `221d7dff24bfec0cd5ac0a5070b8acef2008af3d`.

Исходные архивы — `sources/zapret2-221d7dff.tar.gz` и `sources/provider132-source.tar.gz`. Рецепт поставщика сохранён в `provider-build-nfqws2.yml`, патчи — в `patches/`. При повторной сборке задайте указанный commit движка вместо выбора latest. Версии и архивы библиотек закреплены в `metadata/source-inputs.json`, инструменты — в `metadata/toolchains.json`.

ASUS-пакеты используют готовые официальные IPK, проверяя SHA256 в `project/asus/assets.json`. AArch64 движок сохраняется побайтно; ARM распаковывается UPX 4.2.4, обе контрольные суммы проверяются в `project/asus/build.py`. Комплектные Lua берутся из того же выпуска.

Для сборки ASUS IPK сначала соберите WebUI по `project/README.md`, затем выполните `python3 asus/build.py --cache <каталог-входов> --output <каталог-пакетов>`.
