# NFQWS2 1.0.7

Пакет поставщика: NFQWS2 Keenetic 1.3.3, commit `afd9f6a8a1be6b7ca28afc722a1be81946c41c6b`.
Движок: zapret2 `038c97e5819df10f8e8c22a2f1fffe57f2f7379b` (`v1.0.7`, Lua compatibility 6).

Исходники: `sources/zapret2-038c97e5.tar.gz` и `sources/provider133-source.tar.gz`.
Рецепт поставщика сохранён в `provider-build-nfqws2.yml`, патчи — в `patches/`.
Штатный fastpath-патч перенесён поставщиком на 1.0.7 (ветка `88611a550078d338a02d4dd8e49277b9fde83fff`).
Он применяется к полному чистому архиву командой `patch --batch --fuzz=0 -p1`.
Экспериментальный partial-SNI патч в пакет не включён.

Для повторной компиляции зафиксируйте commit движка выше вместо выбора latest
и используйте версии/хеши исходников из `metadata/source-inputs.json` и инструменты
из `metadata/toolchains.json`. Унаследованный workflow проверяет SHA256 upstream
build.yml `24d184d2dd11701c794fcf48136fff8ba4edaf503e5f01c4dc8ed8da51f93ada`.
Эта проверка рецепта не заменяет проверку применимости патча.
Семь семейств: arm, arm64, mips, mipsel, mips64, x86, x86_64; MIPS32 soft-float.
Используются LuaJIT 2.1-20250826, Lua 5.5.1 для x86, UPX 4.2.4 (кроме mips64).
Входы toolchain/zlib через latest не являются сами по себе воспроизводимым lock:
перед компиляцией сверяйте сохранённые хеши и версии, не обновляйте их молча.

ASUS и native OpenWrt используют готовые официальные IPK 1.3.3, проверяя SHA256
в `project/asus/assets.json` и `project/openwrt/assets.json`.
AArch64 движок ASUS сохраняется побайтно. ARM ASUS и нативные движки распаковываются
на хосте UPX 4.2.4; packed/unpacked hashes проверяются до упаковки.
Комплектные Lua берутся из того же выпуска и распаковываются из gzip.
Старый архив `zapret2-221d7dff.tar.gz` оставлен для отдельно закреплённых публичных blob-шаблонов 1.0.6.

Сначала соберите WebUI по `project/README.md`, затем:

```sh
NFQWS_BUILD_UPX=/path/to/upx python3 asus/build.py --offline --cache /verified/cache --output /output/asus
python3 openwrt/build.py --series 24.10 --arch arm_cortex-a9 --release 88 --offline --cache /verified/cache --output /output/native --upx /path/to/upx
```

Матрица native: все значения `openwrt/release-targets.json`; для 25.12 используйте
`--sign-key` с существующим закрытым ключом вне исходников/пакетов.
BUILD_NUMBER должен совпадать с release. Версия продукта остаётся 1.3.2.
Повторная упаковка в двух отдельных каталогах должна дать одинаковые SHA256.
Полная независимая перекомпиляция всех библиотек и семи бинарников не заявляется.

Движок 1.0.7 запрещает повтор одного файла списков одного типа внутри одного профиля.
Проверяйте штатную и сохранённые конфигурации через `--dry-run` с обновлёнными Lua
и ресурсами. Пользовательские настройки и личные конфигурации не включайте в исходники.
