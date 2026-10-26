nfqws_native_fail() { [ -z "$NFQWS_NATIVE_WORK" ] || NFQWS_NATIVE_KEEP=1; printf '\nОшибка OpenWrt: %s\n' "$*" >&2; exit 1; }
nfqws_native_cleanup() {
    if [ "$NFQWS_NATIVE_KEEP" = 0 ]; then rm -rf "$NFQWS_NATIVE_WORK";
    elif [ -n "$NFQWS_NATIVE_WORK" ]; then printf '\nЖурнал и пакет сохранены: %s\n' "$NFQWS_NATIVE_WORK" >&2; fi
}
nfqws_native_php() {
    /usr/bin/php8-cgi -d register_argc_argv=1 -q -f "$NFQWS_NATIVE_WORK/bundle.php" -- "$1" "$NFQWS_NATIVE_WORK"
}
nfqws_native_provision() {
    [ "$#" -gt 0 ] || return 0
    for nfqws_dep in "$@"; do
        case "$nfqws_dep" in ''|*[!a-z0-9+._-]*) nfqws_native_fail 'Некорректное имя зависимости.';; esac
    done
    nfqws_native_database_safe "$NFQWS_NATIVE_FORMAT" "$NFQWS_NATIVE_DB" || nfqws_native_fail 'Сначала завершите незавершённые операции менеджера пакетов OpenWrt.'
    # opkg configure also processes unrelated unpacked rows. Own incomplete
    # installations may be inspected, but never implicitly configured here.
    if [ "$NFQWS_NATIVE_FORMAT" = ipk ]; then
        if awk 'BEGIN{RS=""} /^Package: nfqws2-native\n/ && /Status: / && !/Status: (install|hold) (ok|user|prefer|hold)(,(ok|user|prefer|hold))* installed(\n|$)/ {found=1} END{exit !found}' "$NFQWS_NATIVE_DB"; then
            nfqws_native_fail 'Пакет NFQWS2 не настроен. Сначала завершите его настройку через opkg; зависимости автоматически не менялись.'
        fi
        nfqws_native_signed_opkg || nfqws_native_fail 'В opkg не включена проверка подписей репозиториев OpenWrt.'
        nfqws_native_background /bin/opkg update || nfqws_native_fail 'Не удалось обновить индексы OpenWrt. См. job.log в сохранённом каталоге.'
        /bin/opkg --noaction install "$@" > "$NFQWS_NATIVE_WORK/provision.plan" 2>&1 || nfqws_native_fail 'Зависимости недоступны для этой версии OpenWrt; проверьте её репозитории.'
        nfqws_native_install_only_plan ipk < "$NFQWS_NATIVE_WORK/provision.plan" || nfqws_native_fail 'Зависимости требуют изменения уже установленных системных пакетов. Обновите их штатным способом OpenWrt и повторите команду.'
        nfqws_native_background /bin/opkg install "$@" || nfqws_native_fail 'opkg не завершил установку зависимостей. Сохраните job.log.'
    else
        nfqws_native_background /usr/bin/apk update || nfqws_native_fail 'Не удалось обновить подписанные индексы OpenWrt.'
        /usr/bin/apk add --simulate "$@" > "$NFQWS_NATIVE_WORK/provision.plan" 2>&1 || nfqws_native_fail 'Зависимости недоступны для этой версии OpenWrt; проверьте её репозитории.'
        nfqws_native_install_only_plan apk < "$NFQWS_NATIVE_WORK/provision.plan" || nfqws_native_fail 'Зависимости требуют изменения уже установленных системных пакетов. Обновите их штатным способом OpenWrt и повторите команду.'
        nfqws_native_background /usr/bin/apk add "$@" || nfqws_native_fail 'apk не завершил установку зависимостей. Сохраните job.log.'
    fi
}
nfqws_native_main() {
    PATH=/usr/sbin:/usr/bin:/sbin:/bin
    export PATH
    unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
    umask 077
    nfqws_check=0
    case "${1-}" in '') ;; --check) nfqws_check=1;; --help|-h) printf 'Установка OpenWrt: sh install.sh; проверка без установки: sh install.sh --check\n'; return 0;; *) nfqws_native_fail 'Неизвестный параметр.';; esac
    [ "$#" -le 1 ] || nfqws_native_fail 'Передано слишком много параметров.'
    nfqws_uid=''
    while read -r nfqws_key nfqws_real nfqws_effective nfqws_rest; do [ "$nfqws_key" != Uid: ] || { nfqws_uid=$nfqws_effective; break; }; done < /proc/self/status
    [ "$nfqws_uid" = 0 ] || nfqws_native_fail 'Войдите в SSH роутера с правами root.'
    nfqws_release=$(sed -n "s/^DISTRIB_RELEASE='\([^']*\)'$/\1/p" /etc/openwrt_release)
    case "$nfqws_release" in 24.10|24.10.*) NFQWS_NATIVE_FORMAT=ipk; NFQWS_NATIVE_DB=/usr/lib/opkg/status;; 25.12|25.12.*) NFQWS_NATIVE_FORMAT=apk; NFQWS_NATIVE_DB=/lib/apk/db/installed;; *) nfqws_native_fail 'Для этой версии OpenWrt ещё нет пакета в каталоге.';; esac
    NFQWS_NATIVE_WORK=$(mktemp -d /tmp/nfqws2-native-install.XXXXXX) || nfqws_native_fail 'Нет места во временной памяти роутера.'
    NFQWS_NATIVE_KEEP=0
    trap nfqws_native_cleanup 0
    trap 'exit 130' INT
    trap 'exit 143' TERM HUP
    nfqws_native_emit_bundle > "$NFQWS_NATIVE_WORK/bundle.php"
    printf '%s\n' '{"schema_version":1,"platform":"openwrt"}' > "$NFQWS_NATIVE_WORK/platform-profile.json"
    nfqws_minimum=''
    for nfqws_dep in php8-cgi php8-mod-openssl php8-mod-curl ca-bundle; do
        if [ "$NFQWS_NATIVE_FORMAT" = ipk ]; then
            /bin/opkg status "$nfqws_dep" 2>/dev/null | grep -Eq '^Status: (install|hold) (ok|user|prefer|hold)(,(ok|user|prefer|hold))* installed$' || nfqws_minimum="$nfqws_minimum $nfqws_dep"
        else /usr/bin/apk info --exists "$nfqws_dep" >/dev/null 2>&1 || nfqws_minimum="$nfqws_minimum $nfqws_dep"; fi
    done
    command -v flock >/dev/null 2>&1 || nfqws_minimum="$nfqws_minimum flock"
    if [ -n "$nfqws_minimum" ]; then
        [ "$nfqws_check" = 0 ] || nfqws_native_fail "Для проверки нужны штатные компоненты OpenWrt:$nfqws_minimum. Режим --check ничего не устанавливает."
        printf 'Установка компонентов OpenWrt:%s\n' "$nfqws_minimum"
        nfqws_native_provision $nfqws_minimum
    fi
    [ -x /usr/bin/php8-cgi ] || nfqws_native_fail 'Штатный PHP8-CGI OpenWrt недоступен.'
    nfqws_native_bootstrap_lock || nfqws_native_fail 'Другой установщик NFQWS2 уже работает или его каталог блокировки недоступен.'
    printf 'OpenWrt %s · проверка подписанного выпуска…\n' "$nfqws_release"
    nfqws_native_php prepare || nfqws_native_fail 'Подготовка не завершена. Проверьте сообщение выше; настройки не менялись.'
    nfqws_description=$(nfqws_native_php describe) || nfqws_native_fail 'Не удалось прочитать проверенный пакет.'
    nfqws_action=$(printf '%s\n' "$nfqws_description" | sed -n 1p)
    nfqws_version=$(printf '%s\n' "$nfqws_description" | sed -n 2p)
    nfqws_missing=$(printf '%s\n' "$nfqws_description" | sed -n 3p)
    printf 'Пакет: nfqws2-native %s (%s).\n' "$nfqws_version" "$NFQWS_NATIVE_FORMAT"
    case "$nfqws_action" in current) printf 'Актуальная версия уже установлена.\n'; return 0;; repair_required) nfqws_native_fail 'Предыдущая установка не завершена. Сохраните вывод opkg status nfqws2-native или apk info -a nfqws2-native; принудительная переустановка не выполнялась.';; esac
    if [ "$nfqws_check" = 1 ]; then printf 'Подпись и пакет проверены. Установка не запускалась.\nНедостающие компоненты: %s\n' "${nfqws_missing:-нет}"; return 0; fi
    [ -z "$nfqws_missing" ] || nfqws_native_provision $nfqws_missing
    printf 'Установка с сохранением настроек…\n'
    nfqws_native_background /usr/bin/php8-cgi -d register_argc_argv=1 -q -f "$NFQWS_NATIVE_WORK/bundle.php" -- run "$NFQWS_NATIVE_WORK" || nfqws_native_fail 'Установка не завершена. Сохраните журналы в указанном каталоге.'
    while :; do
        nfqws_status=$(nfqws_native_php status) || nfqws_native_fail 'Не удалось получить результат обновления; проверьте панель перед повторной установкой.'
        case "$(printf '%s\n' "$nfqws_status" | sed -n 1p)" in
            installed|succeeded) break;;
            applying|preparing) NFQWS_NATIVE_KEEP=1; sleep 2;;
            *) NFQWS_NATIVE_KEEP=1; nfqws_native_fail "Обновление не завершено: $nfqws_status";;
        esac
    done
    NFQWS_NATIVE_KEEP=0
    printf 'Готово: nfqws2-native %s установлен.\n' "$nfqws_version"
    nfqws_ip=$(uci -q get network.lan.ipaddr)
    if ! printf '%s\n' "$nfqws_ip" | awk -F. 'NF!=4{exit 1} {for(i=1;i<=4;i++)if($i!~/^[0-9]+$/||$i>255)exit 1}'; then nfqws_ip=IP-роутера; fi
    printf 'Панель: http://%s:90\n' "$nfqws_ip"
    [ "$nfqws_action" != install ] || printf 'Обработка выключена. Выберите интерфейсы, устройства и стратегию в панели, затем включите NFQWS2.\n'
}
