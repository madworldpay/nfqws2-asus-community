# Исходники Build 62

- [project/](project/) — весь код ASUS, WebUI, службы, модуль, тесты и серверная часть.
- [sources/](sources/) — исходники движка, SmartDNS, BusyBox, lighttpd и библиотек.
- [recipes/](recipes/) — конфигурации, патчи и рецепты сборки модуля, движка и DPI.
- [metadata/](metadata/) — точные версии, происхождение и SHA256 компонентов.
- [documentation/](documentation/) — инструкции. Лицензии компонентов сохранены.

Проверка файлов в Linux: `sha256sum -c SHA256SUMS`.

## Исходники ядра для модуля 87U

Архив ядра разбит на пять частей. Перед сборкой соедините их из этого каталога:

```sh
cat sources/linux-merlin-26e1f3f1-kernel-sdk.tar.gz.part-* > sources/linux-merlin-26e1f3f1-kernel-sdk.tar.gz
```

Windows, командная строка:

```bat
copy /b sources\linux-merlin-26e1f3f1-kernel-sdk.tar.gz.part-001+sources\linux-merlin-26e1f3f1-kernel-sdk.tar.gz.part-002+sources\linux-merlin-26e1f3f1-kernel-sdk.tar.gz.part-003+sources\linux-merlin-26e1f3f1-kernel-sdk.tar.gz.part-004+sources\linux-merlin-26e1f3f1-kernel-sdk.tar.gz.part-005 sources\linux-merlin-26e1f3f1-kernel-sdk.tar.gz
```

SHA256 исходного архива указан в `metadata/kernel-archive-parts.json`.
После соединения используйте [рецепт модуля](recipes/legacy-module/README.md).
Полный единый архив также доступен [в выпуске Build 62](https://github.com/madworldpay/nfqws2-asus-community/releases/download/build62/nfqws2-asus_1.3.1-asus6+b62_source.tar.gz); в каталоге репозитория дополнительно опубликованы тесты, серверная часть и исходник SmartDNS.
