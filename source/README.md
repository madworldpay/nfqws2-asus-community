# Исходники

- [project/](project/) — весь код ASUS, WebUI, службы, модуль, тесты и серверная часть.
- [sources/](sources/) — исходники движка, SmartDNS, BusyBox, lighttpd и библиотек.
- [recipes/](recipes/) — конфигурации, патчи и рецепты сборки модуля, движка и DPI.
- [metadata/](metadata/) — точные версии, происхождение и SHA256 компонентов.
- [documentation/](documentation/) — снимок инструкций при подготовке исходников выпуска. Лицензии компонентов сохранены.
- [installer/](installer/) — установщик одной командой и его проверки.

Проверка файлов в Linux: `sha256sum -c SHA256SUMS`.

[Актуальные пользовательские инструкции](../README.md) находятся в корне
репозитория. Для точного воспроизведения установленного пакета используйте
архив соответствующего выпуска; документация в нём сохраняет состояние на момент сборки.

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
Архив соответствующих исходников приложен к каждому [выпуску](https://github.com/madworldpay/nfqws2-asus-community/releases). Выбирайте тот же выпуск, из которого установлен IPK.

Контрольные суммы в documentation/SHA256SUMS фиксируют IPK на момент сборки исходников. Полный SHA256SUMS выпуска, включая архив и подписанную метадату, находится среди release assets.
