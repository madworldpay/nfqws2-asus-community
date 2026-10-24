#!/bin/sh
# One-off recovery for a legacy SmartDNS rollback blocked by conf-file.
# Installed code and third-party DNS/VPN configuration are never replaced.
PATH=/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077
set -f
nfqws_owner=0

nfqws_error() { printf '%s\n' "$1" >&2; return 1; }
nfqws_native_repair() (
    . /jffs/nfqws2-asus-smartdns/native-common.sh || exit 1
    sd_protected "$sd_root" d && sd_protected "$sd_root/native-common.sh" - || exit 1
    sd_protected /opt/var/lib/nfqws2-asus/updates d &&
        sd_protected /opt/var/lib/nfqws2-asus/updates/apply.lock - || exit 1
    exec 8>>/opt/var/lib/nfqws2-asus/updates/apply.lock || exit 1
    /usr/bin/flock -s -n 8 || { nfqws_error 'Обновление уже выполняется. Дождитесь завершения.'; exit 1; }
    /opt/bin/php-cgi -n -d register_argc_argv=1 -q -f /opt/lib/nfqws2-asus/update/worker.php -- shell-check || {
        nfqws_error 'Не удалось подтвердить завершение предыдущего обновления.'; exit 1;
    }
    . "$nfqws_tmp/check.sh" || exit 1
    sd_current_boot=$(cat /proc/sys/kernel/random/boot_id) || exit 1
    sd_lock || exit 1
    if ! sd_state_load; then sd_unlock; exit 1; fi
    case "$sd_phase" in
        conflict|rolling_back|rolled_back) :;;
        *) sd_unlock; nfqws_error 'Активная настройка SmartDNS: восстановление не запущено.'; exit 1;;
    esac
    sd_rollback
    nfqws_result=$?
    sd_unlock
    exit "$nfqws_result"
)

nfqws_main() {
    [ "$(id -u)" = "$nfqws_owner" ] || { nfqws_error 'Запустите в SSH роутера с правами root.'; return 1; }
    nfqws_tmp=$(mktemp -d /tmp/nfqws-dns-repair.XXXXXX) || return 1
    trap 'rm -f "$nfqws_tmp/native-common.sh" "$nfqws_tmp/check.sh"; rmdir "$nfqws_tmp"' 0
    trap 'exit 1' 1 2 15
    nfqws_url=https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/1cf1beb57fc209abc0bb28dab76e897b9c89bd65/source/project/asus/smartdns/native-common.sh
    curl -fL --proto '=https' --proto-redir '=https' --connect-timeout 10 --max-time 60 --max-filesize 262144 \
        "$nfqws_url" -o "$nfqws_tmp/native-common.sh" || return 1
    nfqws_hash=$(/bin/busybox sha256sum "$nfqws_tmp/native-common.sh") || return 1
    [ "${nfqws_hash%% *}" = 5f92ef885d3a7ba1f0907c24bbce04e24cedebed7631c7327427ed5e77ee39c9 ] || {
        nfqws_error 'Проверка файла не пройдена. Настройки не изменены.'; return 1;
    }
    /bin/busybox awk '/^sd_restored_config\(\)/ {inside=1} inside {print} inside && /^\)$/ {done=1;exit} END {if(!done)exit 2}' \
        "$nfqws_tmp/native-common.sh" > "$nfqws_tmp/check.sh" && sh -n "$nfqws_tmp/check.sh" || return 1
    nfqws_native_repair || { nfqws_error 'Восстановление не завершено. Сохраните этот вывод для диагностики.'; return 1; }
    # Read-only projection. The ordinary updater reconciles this native result
    # under its own lease; never roll back a newer transaction here.
    /opt/bin/nfqws2-smartdns-control status || return 1
    printf '%s\n' 'Восстановление завершено. Можно повторить обновление NFQWS2.'
}

nfqws_main "$@"
