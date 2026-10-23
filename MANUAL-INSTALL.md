# Ручная установка IPK

Для готовой Entware. [Установка одной командой](QUICKSTART.md#1-установить).

## 1. Выбрать пакет

В SSH роутера проверьте архитектуру:

```sh
/opt/bin/opkg print-architecture
```

| Архитектура Entware | Пакет |
|---|---|
| `armv7-2.6` / `armv7-3.2` | ARMv7 |
| `aarch64-3.10` | AArch64 |

Скачайте подходящий IPK и `SHA256SUMS` из [актуального выпуска](https://github.com/madworldpay/nfqws2-asus-community/releases/latest).

## 2. Передать на роутер

Подготовьте папку на накопителе Entware:

```sh
mkdir -p /opt/tmp
```

В Windows передайте файл через WinSCP как `/opt/tmp/nfqws2-asus.ipk`.
Для штатного SSH ASUS выберите протокол SCP.

## 3. Проверить и установить

Сравните результат с суммой исходного файла в `SHA256SUMS`:

```sh
sha256sum /opt/tmp/nfqws2-asus.ipk
```

Если сумма совпала, для **первой установки** выполните:

```sh
/opt/bin/opkg update
NFQWS_ASUS_NO_START=1 /opt/bin/opkg install /opt/tmp/nfqws2-asus.ipk
```

Обработка останется выключенной до настройки. Для **обновления** с сохранением
прежнего состояния службы используйте вместо последней команды:

```sh
/opt/bin/opkg install /opt/tmp/nfqws2-asus.ipk
```

Зависимости загружаются из Entware. При ошибке не применяйте принудительную установку.

## 4. Открыть панель

Откройте `http://IP-роутера:90` и продолжите с [настройки](QUICKSTART.md#2-настроить).
Для удаления и возврата настроек — [отдельная инструкция](INSTALL.md#остановить-или-удалить).
