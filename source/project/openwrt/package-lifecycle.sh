# Embedded verbatim in native package hooks. Never run downloaded shell code.
nfqws_package_state_dir=/tmp/nfqws2-native-package
nfqws_package_updates_dir=/tmp/nfqws2-native-state/updates

nfqws_package_guard() {
    local path=$1
    [ ! -L "$path" ] || return 1
    if [ ! -e "$path" ]; then (umask 077; mkdir -p "$path") || return 1; fi
    [ -d "$path" ] && [ "$(LC_ALL=C ls -dn "$path" | awk '{print $1,$3}')" = 'drwx------ 0' ]
}

nfqws_package_manager() {
    local pid=$PPID expected current fields parent ticks count=0 boot
    case "$NFQWS_PKG_FORMAT" in ipk) expected=/bin/opkg;; apk) expected=/usr/bin/apk;; *) return 1;; esac
    expected=$(readlink -f "$expected") || return 1
    boot=$(cat /proc/sys/kernel/random/boot_id) || return 1
    while [ "$pid" -gt 1 ] && [ "$count" -lt 16 ]; do
        current=$(readlink -f "/proc/$pid/exe") || return 1
        fields=$(sed 's/.*) //' "/proc/$pid/stat") || return 1
        parent=$(printf '%s\n' "$fields" | awk '{print $2}')
        ticks=$(printf '%s\n' "$fields" | awk '{print $20}')
        if [ "$current" = "$expected" ]; then printf '%s:%s:%s\n' "$boot" "$pid" "$ticks"; return 0; fi
        pid=$parent; count=$((count+1))
    done
    return 1
}

nfqws_package_service_state() {
    local enabled=0 running=0 web_present=0 web_enabled=0 web_running=0
    if [ -L /etc/init.d/nfqws2-native ] && [ "$(readlink /etc/init.d/nfqws2-native)" = /usr/lib/nfqws2/nfqws2-native ]; then
        /etc/init.d/nfqws2-native enabled && enabled=1
        /usr/lib/nfqws2/control.sh check >/dev/null 2>&1 && running=1
    fi
    printf 'enabled=%s\nrunning=%s\n' "$enabled" "$running"
    if [ -L /etc/init.d/nfqws2-native-web ] && [ "$(readlink /etc/init.d/nfqws2-native-web)" = /usr/lib/nfqws2-web/nfqws2-native-web ]; then
        web_present=1
        /etc/init.d/nfqws2-native-web enabled && web_enabled=1
        /etc/init.d/nfqws2-native-web running && web_running=1
    fi
    printf 'web_present=%s\nweb_enabled=%s\nweb_running=%s\n' "$web_present" "$web_enabled" "$web_running"
}

nfqws_package_snapshot() {
    local manager previous
    manager=$(nfqws_package_manager) || { echo native_manager_transaction_missing >&2; return 1; }
    nfqws_package_guard "$nfqws_package_state_dir" || return 1
    [ ! -L "$nfqws_package_state_dir/state" ] || return 1
    previous=$(sed -n 's/^manager=//p' "$nfqws_package_state_dir/state" 2>/dev/null)
    if [ "$previous" = "$manager" ]; then nfqws_package_resource_snapshot; return $?; fi
    if [ -e "$nfqws_package_state_dir/previous-resources.json" ] || [ -L "$nfqws_package_state_dir/previous-resources.json" ]; then
        [ -f "$nfqws_package_state_dir/previous-resources.json" ] && [ ! -L "$nfqws_package_state_dir/previous-resources.json" ] || return 1
        rm "$nfqws_package_state_dir/previous-resources.json" || return 1
    fi
    {
        printf 'manager=%s\n' "$manager"
        nfqws_package_service_state
    } > "$nfqws_package_state_dir/state"
    nfqws_package_resource_snapshot
}

nfqws_package_resource_snapshot() {
    local src=/usr/share/nfqws2/report-baseline.json dst=$nfqws_package_state_dir/previous-resources.json
    [ ! -L "$dst" ] || return 1
    if [ -e "$dst" ]; then [ -f "$dst" ]; return $?; fi
    [ -e "$src" ] || [ -L "$src" ] || return 0
    [ -f "$src" ] && [ ! -L "$src" ] || return 1
    case "$(LC_ALL=C ls -ln "$src" | awk '{print $1,$2,$3}')" in '-rw-r--r-- 1 0'|'-rw------- 1 0') ;; *) return 1;; esac
    [ "$(wc -c < "$src")" -le 1048576 ] || return 1
    cp "$src" "$dst" && chmod 600 "$dst"
}

nfqws_package_prepare_upgrade() {
    # apk runs pre-upgrade/post-upgrade, without old pre-deinstall in between.
    # Stop while /proc/PID/exe still matches the old installed executable.
    [ "$NFQWS_PKG_FORMAT" = apk ] && [ "$PKG_UPGRADE" = 1 ] || return 0
    nfqws_package_preremove upgrade
}

nfqws_package_service_owner() {
    local name=$1 target path
    case "$name" in
        nfqws2-native) target=/usr/lib/nfqws2/nfqws2-native;;
        nfqws2-native-web) target=/usr/lib/nfqws2-web/nfqws2-native-web;;
        nfqws2-native-dns|nfqws2-native-dns-resume) target=/usr/lib/nfqws2/smartdns/$name;;
        *) return 1;;
    esac
    path=/etc/init.d/$name
    [ -e "$path" ] || [ -L "$path" ] || return 0
    [ -L "$path" ] && [ "$(readlink "$path")" = "$target" ] && [ -x "$path" ] || { echo native_service_owner_conflict >&2; return 1; }
}

nfqws_package_service() {
    local name=$1 action=$2 path=/etc/init.d/$1
    case "$action" in start|stop|disable) ;; *) return 1;; esac
    nfqws_package_service_owner "$name" || return 1
    [ -e "$path" ] || [ -L "$path" ] || return 0
    "$path" "$action"
}

nfqws_package_dns_control() {
    local mode=$1 path=/usr/lib/nfqws2/smartdns/control.php
    case "$mode" in upgrade|remove) ;; *) return 1;; esac
    if [ ! -e "$path" ] && [ ! -L "$path" ]; then
        # Older core-only packages have no DNS component. Existing journals
        # without their controller require recovery before files are replaced.
        [ ! -e /etc/nfqws2-web/smartdns ] && [ ! -L /etc/nfqws2-web/smartdns ] &&
        [ ! -e /tmp/nfqws2-native-state/smartdns-runtime ] && [ ! -L /tmp/nfqws2-native-state/smartdns-runtime ] || { echo dns_restore_required >&2; return 1; }
        return 0
    fi
    [ -f "$path" ] && [ ! -L "$path" ] || return 1
    case "$(LC_ALL=C ls -ln "$path" | awk '{print $1,$2,$3}')" in '-rw-r--r-- 1 0'|'-rw------- 1 0') ;; *) return 1;; esac
    /usr/bin/php-cgi -d register_argc_argv=1 -q -f "$path" -- "$mode" || { echo dns_restore_failed >&2; return 1; }
}

# A staged update survives replacement/removal of the old application files.
# Only protected native state chooses this entry; no environment or HTTP path.
nfqws_package_native_update() {
    local action=$1 dir=$nfqws_package_updates_dir phase id path parent inactive=0
    case "$action" in verify|capture) ;; postinstall) inactive=10;; *) return 1;; esac
    path=$dir/native-transaction.json
    [ -e "$path" ] || [ -L "$path" ] || return "$inactive"
    parent=$path
    while [ "$parent" != / ] && [ -n "$parent" ]; do
        [ ! -L "$parent" ] || return 1
        parent=${parent%/*}
    done
    [ -d "$dir" ] && nfqws_package_guard "$dir" || return 1
    [ -f "$path" ] && [ "$(LC_ALL=C ls -ln "$path" | awk '{print $1,$2,$3}')" = '-rw------- 1 0' ] && [ "$(wc -c < "$path")" -le 16384 ] || return 1
    phase=$(jsonfilter -i "$path" -e '@.phase') || return 1
    case "$phase" in finished) return "$inactive";; validating|installing|starting) ;; *) return 1;; esac
    id=$(jsonfilter -i "$path" -e '@.id') || return 1
    case "$id" in ''|*[!a-f0-9]*) return 1;; esac
    [ "${#id}" = 32 ] || return 1
    for parent in "$dir/operations" "$dir/operations/$id" "$dir/operations/$id/runtime"; do
        [ -d "$parent" ] && nfqws_package_guard "$parent" || return 1
    done
    path=$dir/operations/$id/runtime/worker.php
    [ -f "$path" ] && [ ! -L "$path" ] && [ "$(LC_ALL=C ls -ln "$path" | awk '{print $1,$2,$3}')" = '-rw------- 1 0' ] || return 1
    /usr/bin/php-cgi -d register_argc_argv=1 -q -f "$path" -- "hook-$action" "$id"
}

nfqws_package_stop_services() {
    local path=/usr/lib/nfqws2/update/quiesce.php parent
    if [ -e "$path" ] || [ -L "$path" ]; then
        [ -f "$path" ] && [ ! -L "$path" ] || return 1
        case "$(LC_ALL=C ls -ln "$path" | awk '{print $1,$2,$3}')" in '-rw-r--r-- 1 0'|'-rw------- 1 0') ;; *) return 1;; esac
        parent=${path%/*}
        while [ -n "$parent" ] && [ "$parent" != / ]; do
            [ -d "$parent" ] && [ ! -L "$parent" ] || return 1
            LC_ALL=C ls -dn "$parent" | awk '{if($3!=0 || substr($1,1,1)!="d" || substr($1,6,1)=="w" || substr($1,9,1)=="w")exit 1}' || return 1
            parent=${parent%/*}
        done
        /usr/bin/php8-cgi -d register_argc_argv=1 -q -f "$path" -- "$1"
    else
        # Earlier experimental native packages predate the controller. Their
        # own UI updater is absent; retain the verified inline DNS fallback.
        nfqws_package_stop_services_internal "$1"
    fi
}

nfqws_package_stop_services_internal() {
    local name
    for name in nfqws2-native nfqws2-native-web nfqws2-native-dns nfqws2-native-dns-resume; do
        nfqws_package_service_owner "$name" || return 1
    done
    # Verify fallback DNS while the old engine and controller still exist.
    # A conflict aborts the package-manager pre-commit hook.
    nfqws_package_native_update verify &&
    nfqws_package_dns_control "$1" &&
    nfqws_package_service nfqws2-native-dns stop &&
    nfqws_package_service nfqws2-native-dns-resume stop &&
    nfqws_package_service nfqws2-native stop &&
    nfqws_package_service nfqws2-native-web stop &&
    nfqws_package_native_update capture
}

nfqws_package_preinstall() {
    [ -z "$IPKG_INSTROOT" ] || return 0
    [ -f /etc/openwrt_release ] || { echo native_openwrt_required >&2; return 1; }
    local arch version
    arch=$(sed -n "s/^DISTRIB_ARCH='\([^']*\)'$/\1/p" /etc/openwrt_release)
    version=$(sed -n "s/^DISTRIB_RELEASE='\([^']*\)'$/\1/p" /etc/openwrt_release)
    [ "$arch" = "$NFQWS_PKG_ARCH" ] && [ "${version%.*}" = "$NFQWS_PKG_SERIES" ] || { echo native_package_mismatch >&2; return 1; }
    case "$NFQWS_PKG_FORMAT" in
        ipk) [ -x /bin/opkg ];;
        apk) [ -x /usr/bin/apk ];;
        *) return 1;;
    esac || { echo native_package_manager_required >&2; return 1; }
    if [ -e /etc/init.d/nfqws2-native ] || [ -L /etc/init.d/nfqws2-native ]; then
        [ -L /etc/init.d/nfqws2-native ] && [ "$(readlink /etc/init.d/nfqws2-native)" = /usr/lib/nfqws2/nfqws2-native ] || { echo native_service_owner_conflict >&2; return 1; }
    fi
    if [ -e /etc/init.d/nfqws2-native-web ] || [ -L /etc/init.d/nfqws2-native-web ]; then
        [ -L /etc/init.d/nfqws2-native-web ] && [ "$(readlink /etc/init.d/nfqws2-native-web)" = /usr/lib/nfqws2-web/nfqws2-native-web ] || { echo native_web_owner_conflict >&2; return 1; }
    fi
    for dns_service in nfqws2-native-dns nfqws2-native-dns-resume; do
        if [ -e "/etc/init.d/$dns_service" ] || [ -L "/etc/init.d/$dns_service" ]; then
            [ -L "/etc/init.d/$dns_service" ] && [ "$(readlink "/etc/init.d/$dns_service")" = "/usr/lib/nfqws2/smartdns/$dns_service" ] || { echo native_dns_owner_conflict >&2; return 1; }
        fi
    done
    nfqws_package_snapshot && nfqws_package_prepare_upgrade
}

nfqws_package_defaults() {
    local root=${IPKG_INSTROOT} src dst name file leaf
    [ ! -L "$root/etc/nfqws2" ] || { echo native_config_owner_conflict >&2; return 1; }
    mkdir -p "$root/etc/nfqws2" "$root/etc/init.d" || return 1
    chmod 755 "$root/etc/nfqws2"
    src="$root/usr/share/nfqws2/defaults"
    for name in nfqws2.conf lists lua blobs; do
        dst="$root/etc/nfqws2/$name"
        [ ! -L "$dst" ] || { echo native_config_owner_conflict >&2; return 1; }
        if [ ! -e "$dst" ]; then
            cp -R "$src/$name" "$dst" || return 1
            if [ -d "$dst" ]; then
                find "$dst" -type d -exec chmod 755 '{}' ';' || return 1
                find "$dst" -type f -exec chmod 644 '{}' ';' || return 1
            fi
        fi
        # Add newly supplied resources on upgrade without replacing a user's
        # existing files. Package defaults are flat, regular-file directories.
        if [ -d "$dst" ]; then
            for file in "$src/$name"/*; do
                [ -f "$file" ] && [ ! -L "$file" ] || continue
                leaf="$dst/${file##*/}"
                if [ ! -e "$leaf" ] && [ ! -L "$leaf" ]; then cp "$file" "$leaf" && chmod 644 "$leaf" || return 1; fi
            done
        fi
    done
    for dns_service in nfqws2-native-dns nfqws2-native-dns-resume; do
        if [ -f "$root/usr/lib/nfqws2/smartdns/$dns_service" ]; then
            dst="$root/etc/init.d/$dns_service"
            if [ -e "$dst" ] || [ -L "$dst" ]; then
                [ -L "$dst" ] && [ "$(readlink "$dst")" = "/usr/lib/nfqws2/smartdns/$dns_service" ] || return 1
            else ln -s "/usr/lib/nfqws2/smartdns/$dns_service" "$dst" || return 1; fi
        fi
    done
    chmod 600 "$root/etc/nfqws2/nfqws2.conf"
    # Only the automatic list needs writes from the privilege-dropped engine.
    [ ! -L "$root/etc/nfqws2/lists/auto.list" ] || return 1
    chown 65534:65534 "$root/etc/nfqws2/lists/auto.list" || return 1
    chmod 600 "$root/etc/nfqws2/lists/auto.list"
    dst="$root/etc/init.d/nfqws2-native"
    if [ -e "$dst" ] || [ -L "$dst" ]; then
        [ -L "$dst" ] && [ "$(readlink "$dst")" = /usr/lib/nfqws2/nfqws2-native ] || return 1
    else
        ln -s /usr/lib/nfqws2/nfqws2-native "$dst" || return 1
    fi
    if [ -f "$root/usr/lib/nfqws2-web/nfqws2-native-web" ]; then
        [ ! -L "$root/etc/nfqws2-web" ] && [ ! -L "$root/etc/config/nfqws2-web" ] || return 1
        mkdir -p "$root/etc/config" "$root/etc/nfqws2-web" || return 1
        chmod 700 "$root/etc/nfqws2-web" || return 1
        if [ ! -e "$root/etc/config/nfqws2-web" ]; then cp "$src/web-config" "$root/etc/config/nfqws2-web" || return 1; fi
        dst="$root/etc/nfqws2-web/auth.json"
        [ ! -L "$dst" ] || return 1
        if [ ! -e "$dst" ]; then
            printf '%s\n' '{"mode":"system","username":"root","password_hash":""}' > "$dst" || return 1
            chmod 600 "$dst" || return 1
        fi
        dst="$root/etc/init.d/nfqws2-native-web"
        if [ -e "$dst" ] || [ -L "$dst" ]; then
            [ -L "$dst" ] && [ "$(readlink "$dst")" = /usr/lib/nfqws2-web/nfqws2-native-web ] || return 1
        else ln -s /usr/lib/nfqws2-web/nfqws2-native-web "$dst" || return 1; fi
    fi
}

nfqws_package_mark_starting() {
    local manager path=$nfqws_package_state_dir/phase
    manager=$(nfqws_package_manager) || return 1
    [ ! -L "$path" ] || return 1
    if [ -e "$path" ]; then
        [ -f "$path" ] && [ "$(LC_ALL=C ls -ln "$path" | awk '{print $1,$2,$3}')" = '-rw------- 1 0' ] || return 1
    fi
    (umask 077; printf '%s\nstarting\n' "$manager" > "$path")
}

# OPKG may retry only postinst for an unpacked package. Keep the saved intent
# from the dead manager instead of treating all previously stopped services as
# the operator's new choice. This never changes the package database.
nfqws_package_adopt_configure() {
    local current=$1 path=$nfqws_package_state_dir/state previous boot old_pid old_ticks actual_ticks next
    [ "$NFQWS_PKG_FORMAT" = ipk ] && [ -f "$path" ] && [ ! -L "$path" ] || return 1
    [ "$(LC_ALL=C ls -ln "$path" | awk '{print $1,$2,$3}')" = '-rw------- 1 0' ] && [ "$(wc -c < "$path")" -le 4096 ] || return 1
    awk -F= '
      $1=="manager" {if(NF!=2 || seen[$1]++)exit 1;next}
      $1~/^(enabled|running|web_present|web_enabled|web_running)$/ {if(NF!=2 || $2!~/^[01]$/ || seen[$1]++)exit 1;next}
      {exit 1}
      END {if(length(seen)!=6)exit 1}
    ' "$path" || return 1
    previous=$(sed -n 's/^manager=//p' "$path")
    boot=$(cat /proc/sys/kernel/random/boot_id) || return 1
    printf '%s\n' "$previous" | awk -F: -v boot="$boot" 'NF!=3 || $1!=boot || $2!~/^[1-9][0-9]*$/ || $2>2147483647 || $3!~/^[1-9][0-9]*$/ {exit 1}' || return 1
    old_pid=$(printf '%s\n' "$previous" | cut -d: -f2)
    old_ticks=$(printf '%s\n' "$previous" | cut -d: -f3)
    actual_ticks=$(sed 's/.*) //' "/proc/$old_pid/stat" 2>/dev/null | awk '{print $20}')
    [ "$actual_ticks" != "$old_ticks" ] || return 1
    # opkg itself holds its lock: read its current native database rather than
    # spawning another opkg command from a maintainer script.
    awk 'BEGIN {RS=""}
      $0~/(^|\n)Package: nfqws2-native(\n|$)/ {
        package++; if($0!~/(^|\n)Status: (install|hold) (ok|user|prefer|hold)(,(ok|user|prefer|hold))* unpacked(\n|$)/)bad=1
      }
      END {if(package!=1 || bad)exit 1}
    ' /usr/lib/opkg/status || return 1
    next=$(mktemp "$nfqws_package_state_dir/configure.XXXXXX") || return 1
    if ! { printf 'manager=%s\n' "$current"; sed '/^manager=/d' "$path"; } > "$next"; then rm -f "$next"; return 1; fi
    mv "$next" "$path"
}

nfqws_package_postinstall() {
    nfqws_package_defaults || return 1
    [ -z "$IPKG_INSTROOT" ] || return 0
    local enabled=0 running=0 path manager web_enabled=1 web_running=1 defer=0
    nfqws_package_guard "$nfqws_package_state_dir" || return 1
    if [ -f "$nfqws_package_state_dir/state" ] && [ ! -L "$nfqws_package_state_dir/state" ]; then
        manager=$(nfqws_package_manager) || return 1
        [ "$(sed -n 's/^manager=//p' "$nfqws_package_state_dir/state")" = "$manager" ] || nfqws_package_adopt_configure "$manager" || { echo stale_package_transaction >&2; return 1; }
        enabled=$(sed -n 's/^enabled=\([01]\)$/\1/p' "$nfqws_package_state_dir/state")
        running=$(sed -n 's/^running=\([01]\)$/\1/p' "$nfqws_package_state_dir/state")
        case "$enabled:$running" in 0:0|0:1|1:0|1:1) ;; *) return 1;; esac
        if [ "$(sed -n 's/^web_present=//p' "$nfqws_package_state_dir/state")" = 1 ]; then
            web_enabled=$(sed -n 's/^web_enabled=\([01]\)$/\1/p' "$nfqws_package_state_dir/state")
            web_running=$(sed -n 's/^web_running=\([01]\)$/\1/p' "$nfqws_package_state_dir/state")
            case "$web_enabled:$web_running" in 0:0|0:1|1:0|1:1) ;; *) return 1;; esac
        fi
    fi
    if [ -e "$nfqws_package_state_dir/previous-resources.json" ] || [ -L "$nfqws_package_state_dir/previous-resources.json" ]; then
        /usr/bin/php-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/resource-upgrade.php || return 1
    fi
    path=$(uci -q get firewall.nfqws2_native.path)
    if [ -n "$(uci -q get firewall.nfqws2_native)" ]; then
        [ "$path" = /usr/lib/nfqws2/firewall-hook.sh ] || { echo firewall_include_owner_conflict >&2; return 1; }
    else
        uci set firewall.nfqws2_native=include &&
        uci set firewall.nfqws2_native.type=script &&
        uci set firewall.nfqws2_native.path=/usr/lib/nfqws2/firewall-hook.sh &&
        uci set firewall.nfqws2_native.fw4_compatible=1 && uci commit firewall || return 1
    fi
    # A controlled panel update starts nothing until its immutable worker has
    # verified manager success, installed version, and the latest settings.
    nfqws_package_native_update postinstall
    case "$?" in 0) defer=1;; 10) ;; *) return 1;; esac
    if [ "$enabled" = 1 ]; then /etc/init.d/nfqws2-native enable || return 1
    else /etc/init.d/nfqws2-native disable || return 1; fi
    if [ -x /etc/init.d/nfqws2-native-web ]; then
        if [ "$web_enabled" = 1 ]; then /etc/init.d/nfqws2-native-web enable || return 1
        else /etc/init.d/nfqws2-native-web disable || return 1; fi
    fi
    if [ -x /etc/init.d/nfqws2-native-dns ]; then /etc/init.d/nfqws2-native-dns disable || return 1; fi
    if [ -x /etc/init.d/nfqws2-native-dns-resume ]; then /etc/init.d/nfqws2-native-dns-resume enable || return 1; fi
    [ "$defer" != 1 ] || return 0
    nfqws_package_mark_starting || return 1
    [ "$running" != 1 ] || /etc/init.d/nfqws2-native start || return 1
    if [ -x /etc/init.d/nfqws2-native-web ]; then
        [ "$web_running" != 1 ] || /etc/init.d/nfqws2-native-web start || return 1
    fi
    rm -f "$nfqws_package_state_dir/state" "$nfqws_package_state_dir/previous-resources.json" "$nfqws_package_state_dir/phase"
    rmdir "$nfqws_package_state_dir" 2>/dev/null || :
    # The detached worker revalidates only previously confirmed consent.
    # First installation remains inert when no saved DNS intent exists.
    nfqws_package_service nfqws2-native-dns-resume start
}

nfqws_package_preremove() {
    [ -z "$IPKG_INSTROOT" ] || return 0
    if [ -e /etc/init.d/nfqws2-native ] || [ -L /etc/init.d/nfqws2-native ]; then
        [ -L /etc/init.d/nfqws2-native ] && [ "$(readlink /etc/init.d/nfqws2-native)" = /usr/lib/nfqws2/nfqws2-native ] || return 1
    fi
    if [ "$PKG_UPGRADE" = 1 ] || [ "$1" = upgrade ]; then nfqws_package_snapshot || return 1; fi
    local mode=remove
    if [ "$PKG_UPGRADE" = 1 ] || [ "$1" = upgrade ]; then mode=upgrade; fi
    nfqws_package_stop_services "$mode" || return 1
    if [ "$mode" = remove ]; then
        nfqws_package_service nfqws2-native disable &&
        nfqws_package_service nfqws2-native-web disable &&
        nfqws_package_service nfqws2-native-dns disable &&
        nfqws_package_service nfqws2-native-dns-resume disable || return 1
    fi
}

nfqws_package_postremove() {
    [ -z "$IPKG_INSTROOT" ] || return 0
    [ "$PKG_UPGRADE" != 1 ] && [ "$1" != upgrade ] || return 0
    if [ -L /etc/init.d/nfqws2-native ] && [ "$(readlink /etc/init.d/nfqws2-native)" = /usr/lib/nfqws2/nfqws2-native ]; then
        rm /etc/init.d/nfqws2-native
    fi
    if [ -L /etc/init.d/nfqws2-native-web ] && [ "$(readlink /etc/init.d/nfqws2-native-web)" = /usr/lib/nfqws2-web/nfqws2-native-web ]; then rm /etc/init.d/nfqws2-native-web; fi
    for dns_service in nfqws2-native-dns nfqws2-native-dns-resume; do
        if [ -L "/etc/init.d/$dns_service" ] && [ "$(readlink "/etc/init.d/$dns_service")" = "/usr/lib/nfqws2/smartdns/$dns_service" ]; then rm "/etc/init.d/$dns_service"; fi
    done
    if [ "$(uci -q get firewall.nfqws2_native.path)" = /usr/lib/nfqws2/firewall-hook.sh ]; then
        uci -q delete firewall.nfqws2_native && uci commit firewall || return 1
    fi
    # User configuration is intentionally retained for a later reinstall.
}

case "$NFQWS_PKG_ACTION" in
    preinstall) nfqws_package_preinstall;;
    postinstall) nfqws_package_postinstall;;
    preremove) nfqws_package_preremove "$@";;
    postremove) nfqws_package_postremove "$@";;
    *) echo invalid_package_action >&2; exit 1;;
esac
