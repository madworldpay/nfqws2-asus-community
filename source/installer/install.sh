#!/bin/sh
# NFQWS2 ASUS bootstrap for an existing Entware installation. No sourced downloads.
PATH=/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077

fail() { printf '\nОшибка: %s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }
tool() {
    for directory in $(printf '%s' "$PATH" | tr ':' ' '); do
        if [ -f "$directory/$1" ] && [ -x "$directory/$1" ]; then
            printf '%s\n' "$directory/$1"; return 0
        fi
    done
    return 1
}
cleanup() { [ -z "$WORK" ] || rm -rf "$WORK"; }

download() {
    download_url=$1 download_file=$2 download_cap=$3
    # ulimit also bounds GNU wget, which has no per-file size limit.
    if [ -n "$CURL" ]; then
        (
            ulimit -f "$(( (download_cap + 511) / 512 ))" || exit 1
            set -- -fSL --connect-timeout 10 --max-time 180 --retry 2 --max-redirs 5 \
                --proto '=https' --proto-redir '=https' --max-filesize "$download_cap"
            [ ! -f /opt/etc/ssl/certs/ca-certificates.crt ] || set -- "$@" --cacert /opt/etc/ssl/certs/ca-certificates.crt
            "$CURL" "$@" -o "$download_file" "$download_url"
        ) || fail 'Не удалось скачать файл. Проверьте интернет, время роутера и HTTPS-доступ к GitHub; затем повторите команду.'
    else
        (
            ulimit -f "$(( (download_cap + 511) / 512 ))" || exit 1
            set -- --timeout=20 --tries=2 --max-redirect=5 --https-only
            [ ! -f /opt/etc/ssl/certs/ca-certificates.crt ] || set -- "$@" --ca-certificate=/opt/etc/ssl/certs/ca-certificates.crt
            "$WGET" "$@" -O "$download_file" "$download_url"
        ) || fail 'Не удалось скачать файл с GitHub. Проверьте интернет, время роутера и сертификаты HTTPS.'
    fi
    download_bytes=$(wc -c < "$download_file") || fail 'Не удалось прочитать скачанный файл.'
    [ "$download_bytes" -gt 0 ] && [ "$download_bytes" -le "$download_cap" ] || fail 'Размер скачанного файла некорректен.'
}

panel_link() {
    panel_ip=$(nvram get lan_ipaddr 2>/dev/null)
    if ! printf '%s\n' "$panel_ip" | awk -F. 'NF!=4{exit 1} {for(i=1;i<=4;i++)if($i!~/^[0-9]+$/||$i>255)exit 1}'; then
        panel_ip='IP-роутера'
    fi
    say "Панель: http://$panel_ip:90"
}

read_package_status() {
    package_record=$("$OPKG" status nfqws2-asus 2>/dev/null)
    installed=$(printf '%s\n' "$package_record" | awk '$1=="Version:"{print $2}')
    package_status=$(printf '%s\n' "$package_record" | awk '$1=="Status:"{print $2 " " $3 " " $4}')
}

package_healthy() {
    [ -n "$installed" ] || return 1
    case "$package_status" in
        'install ok installed'|'hold ok installed') return 0 ;;
        *) return 1 ;;
    esac
}

main() {
    WORK='' CHECK_ONLY=0
    case "${1-}" in
        '') ;;
        --check) CHECK_ONLY=1 ;;
        --help|-h) say 'Установка: sh install.sh; только проверка пакета: sh install.sh --check'; return 0 ;;
        *) fail 'Неизвестный параметр. Используйте sh install.sh или sh install.sh --check.' ;;
    esac
    [ "$#" -le 1 ] || fail 'Передано слишком много параметров.'
    uid=''
    while read -r key real effective rest; do
        [ "$key" != 'Uid:' ] || { uid=$effective; break; }
    done < /proc/self/status
    [ "$uid" = 0 ] || fail 'Войдите по SSH как администратор роутера.'
    OPKG=/opt/bin/opkg
    [ -x "$OPKG" ] || fail 'Сначала установите и запустите Entware в /opt.'
    tool nvram >/dev/null || fail 'Установщик предназначен для ASUS с Asuswrt/Merlin.'
    model=$(nvram get productid 2>/dev/null)
    [ -n "$model" ] || model=$(nvram get odmpid 2>/dev/null)
    [ -n "$model" ] || fail 'Не удалось определить модель ASUS.'

    # Resolve the primary Entware ABI, never a supported lower-priority ABI.
    arches=$("$OPKG" print-architecture) || fail 'Не удалось прочитать архитектуру Entware.'
    abi=$(printf '%s\n' "$arches" | awk '
        $1=="arch" && $2!="all" {
            if(NF!=3 || $3!~/^[0-9]+$/ || $3>2147483647){bad=1;next}
            if($2 in seen)next;seen[$2]=1
            if(!have || $3+0>priority){have=1;priority=$3+0;abi=$2;tied=0}
            else if($3+0==priority)tied=1
        }
        END{if(bad||!have||priority<=0||tied)exit 1;print abi}
    ') || fail 'Не удалось однозначно определить основную архитектуру Entware.'
    case "$abi:$(uname -m)" in
        armv7-2.6:armv7*|armv7-3.2:armv7*|armv7-2.6:aarch64|armv7-3.2:aarch64) family=armv7 ;;
        aarch64-3.10:aarch64) family=aarch64-3.10 ;;
        *) fail "Архитектура Entware $abi не поддерживается этим установщиком." ;;
    esac
    CURL=$(tool curl) || CURL=''
    WGET=''
    if [ -z "$CURL" ]; then
        WGET=$(tool wget) || fail 'Для скачивания нужен curl или GNU wget: установите один из них через opkg.'
        "$WGET" --version 2>/dev/null | grep -q 'GNU Wget' || fail 'Для HTTPS нужен curl или GNU wget из Entware.'
    fi
    HASH=$(tool sha256sum) || HASH=''
    HASH_BUSYBOX=0
    if [ -z "$HASH" ]; then
        /bin/busybox sha256sum /dev/null >/dev/null 2>&1 || fail 'Не найден sha256sum. Установите coreutils-sha256sum через opkg.'
        HASH=/bin/busybox HASH_BUSYBOX=1
    fi
    mkdir -p /opt/tmp || fail 'Entware недоступна для записи.'
    WORK=$(mktemp -d /opt/tmp/nfqws2-asus-install.XXXXXX) || fail 'Не удалось создать временный каталог в Entware.'
    trap cleanup 0
    trap 'exit 130' INT
    trap 'exit 143' TERM HUP
    say "ASUS $model · Entware $abi"
    say 'Проверка актуального выпуска…'
    download 'https://github.com/madworldpay/nfqws2-asus-community/releases/latest/download/SHA256SUMS' "$WORK/SHA256SUMS" 65536
    candidate=$(awk -v family="$family" '
        $2 ~ ("_" family "[.]ipk$") {
            if(NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || length($2)>160 ||
               $2!~/^nfqws2-asus_[0-9]+[.][0-9]+[.][0-9]+-asus[1-9][0-9]*[+]b[1-9][0-9]*_(armv7|aarch64-3[.]10)[.]ipk$/){bad=1;next}
            count++;hash=$1;name=$2
        }
        END{if(bad||count!=1)exit 1;print hash " " name}
    ' "$WORK/SHA256SUMS") || fail 'В выпуске не найден один подходящий IPK с контрольной суммой.'
    read -r expected_sha asset_name <<EOF
$candidate
EOF
    version=${asset_name#nfqws2-asus_}
    version=${version%_$family.ipk}
    build=${version##*+b}
    read_package_status
    if ! package_healthy; then
        case "$package_status:$installed" in
            ':'|'deinstall ok config-files:'*|'deinstall ok not-installed:'*|'purge ok not-installed:'*|'unknown ok not-installed:'*) installed='' ;;
            *) fail "Предыдущая установка NFQWS2 ASUS не завершена (статус: $package_status). Сохраните вывод opkg status nfqws2-asus для исправления. Настройки и состояние службы не менялись." ;;
        esac
    fi
    if [ "$installed" = "$version" ]; then
        say "Build $build уже установлен."
        panel_link
        return 0
    fi
    if [ -n "$installed" ] && "$OPKG" compare-versions "$installed" '>' "$version"; then
        fail "Уже установлен более новый пакет: $installed. Понижение версии не выполнялось."
    fi
    free_kb=$(df -Pk /opt/ | awk 'NR==2 && $4~/^[0-9]+$/{print $4}')
    [ -n "$free_kb" ] && [ "$free_kb" -ge 131072 ] || fail 'В Entware нужно не менее 128 МБ свободного места для установки и сохранения настроек.'
    memory_kb=$(awk '
        /^MemAvailable:/{available=$2;have=1} /^MemFree:/{free=$2}
        /^Buffers:/{buffers=$2} /^Cached:/{cached=$2}
        END{if(have)print available;else print free+buffers+cached}
    ' /proc/meminfo)
    [ "$memory_kb" -ge 32768 ] || fail 'Недостаточно свободной оперативной памяти: нужно не менее 32 МБ. Освободите память и повторите команду.'
    say "Скачивание Build $build…"
    package=$WORK/$asset_name
    download "https://github.com/madworldpay/nfqws2-asus-community/releases/download/build$build/$asset_name" "$package" 33554432
    if [ "$HASH_BUSYBOX" = 1 ]; then actual_sha=$("$HASH" sha256sum "$package"); else actual_sha=$("$HASH" "$package"); fi
    [ "$?" = 0 ] || fail 'Не удалось проверить контрольную сумму IPK.'
    actual_sha=${actual_sha%% *}
    [ "$actual_sha" = "$expected_sha" ] || fail 'Контрольная сумма IPK не совпала. Установка не выполнялась; повторите команду.'
    if [ "$CHECK_ONLY" = 1 ]; then
        say "Пакет Build $build для $abi скачан и проверен. Установка не выполнялась."
        return 0
    fi
    # prerm/postinst handle migration and service changes. Read intent right before opkg.
    no_start=1
    if [ -n "$installed" ]; then
        if [ -f /tmp/nfqws2-asus/enabled ] || { [ -x /opt/etc/init.d/S51nfqws2 ] && /opt/etc/init.d/S51nfqws2 status >/dev/null 2>&1; }; then
            no_start=0
        fi
    fi
    mkdir "$WORK/opkg" || fail 'Не удалось подготовить временный каталог opkg.'
    say 'Обновление списка пакетов Entware…'
    "$OPKG" --tmp-dir "$WORK/opkg" update || fail 'Не удалось обновить список пакетов Entware. Установка не выполнялась.'
    say 'Установка NFQWS2 ASUS с сохранением настроек…'
    NFQWS_ASUS_NO_START=$no_start "$OPKG" --tmp-dir "$WORK/opkg" install "$package" || fail 'opkg сообщил об ошибке установки. Сохраните вывод выше; принудительная установка не выполнялась.'
    was_installed=$installed
    read_package_status
    [ "$installed" = "$version" ] && package_healthy || fail 'opkg завершился, но установка нужной версии не завершена. Сохраните вывод установки и opkg status nfqws2-asus.'
    say "Готово: Build $build установлен."
    panel_link
    [ -n "$was_installed" ] || say 'Выберите WAN, устройства и профиль в панели, затем запустите NFQWS2.'
    return 0
}

# Keep the entry point last so an incomplete piped download cannot run a partial installer.
main "$@"
