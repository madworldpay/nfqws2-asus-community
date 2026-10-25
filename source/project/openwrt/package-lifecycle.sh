# Embedded verbatim in native package hooks. Never run downloaded shell code.
nfqws_package_state_dir=/tmp/nfqws2-native-package

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
    local enabled=0 running=0
    if [ -L /etc/init.d/nfqws2-native ] && [ "$(readlink /etc/init.d/nfqws2-native)" = /usr/lib/nfqws2/nfqws2-native ]; then
        /etc/init.d/nfqws2-native enabled && enabled=1
        /usr/lib/nfqws2/control.sh check >/dev/null 2>&1 && running=1
    fi
    printf 'enabled=%s\nrunning=%s\n' "$enabled" "$running"
}

nfqws_package_snapshot() {
    local manager previous
    manager=$(nfqws_package_manager) || { echo native_manager_transaction_missing >&2; return 1; }
    nfqws_package_guard "$nfqws_package_state_dir" || return 1
    [ ! -L "$nfqws_package_state_dir/state" ] || return 1
    previous=$(sed -n 's/^manager=//p' "$nfqws_package_state_dir/state" 2>/dev/null)
    [ "$previous" != "$manager" ] || return 0
    {
        printf 'manager=%s\n' "$manager"
        nfqws_package_service_state
    } > "$nfqws_package_state_dir/state"
}

nfqws_package_prepare_upgrade() {
    # apk runs pre-upgrade/post-upgrade, without old pre-deinstall in between.
    # Stop while /proc/PID/exe still matches the old installed executable.
    [ "$NFQWS_PKG_FORMAT" = apk ] && [ "$PKG_UPGRADE" = 1 ] || return 0
    nfqws_package_preremove upgrade
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
    nfqws_package_snapshot && nfqws_package_prepare_upgrade
}

nfqws_package_defaults() {
    local root=${IPKG_INSTROOT} src dst name
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
}

nfqws_package_postinstall() {
    nfqws_package_defaults || return 1
    [ -z "$IPKG_INSTROOT" ] || return 0
    local enabled=0 running=0 path manager
    nfqws_package_guard "$nfqws_package_state_dir" || return 1
    if [ -f "$nfqws_package_state_dir/state" ] && [ ! -L "$nfqws_package_state_dir/state" ]; then
        manager=$(nfqws_package_manager) || return 1
        [ "$(sed -n 's/^manager=//p' "$nfqws_package_state_dir/state")" = "$manager" ] || { echo stale_package_transaction >&2; return 1; }
        enabled=$(sed -n 's/^enabled=\([01]\)$/\1/p' "$nfqws_package_state_dir/state")
        running=$(sed -n 's/^running=\([01]\)$/\1/p' "$nfqws_package_state_dir/state")
        case "$enabled:$running" in 0:0|0:1|1:0|1:1) ;; *) return 1;; esac
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
    if [ "$enabled" = 1 ]; then /etc/init.d/nfqws2-native enable || return 1
    else /etc/init.d/nfqws2-native disable || return 1; fi
    [ "$running" != 1 ] || /etc/init.d/nfqws2-native start || return 1
    rm -f "$nfqws_package_state_dir/state"
    rmdir "$nfqws_package_state_dir" 2>/dev/null || :
}

nfqws_package_preremove() {
    [ -z "$IPKG_INSTROOT" ] || return 0
    if [ -e /etc/init.d/nfqws2-native ] || [ -L /etc/init.d/nfqws2-native ]; then
        [ -L /etc/init.d/nfqws2-native ] && [ "$(readlink /etc/init.d/nfqws2-native)" = /usr/lib/nfqws2/nfqws2-native ] || return 1
    fi
    if [ "$PKG_UPGRADE" = 1 ] || [ "$1" = upgrade ]; then nfqws_package_snapshot || return 1
    else [ ! -x /etc/init.d/nfqws2-native ] || /etc/init.d/nfqws2-native disable || return 1; fi
    [ ! -x /etc/init.d/nfqws2-native ] || /etc/init.d/nfqws2-native stop || return 1
}

nfqws_package_postremove() {
    [ -z "$IPKG_INSTROOT" ] || return 0
    [ "$PKG_UPGRADE" != 1 ] && [ "$1" != upgrade ] || return 0
    if [ -L /etc/init.d/nfqws2-native ] && [ "$(readlink /etc/init.d/nfqws2-native)" = /usr/lib/nfqws2/nfqws2-native ]; then
        rm /etc/init.d/nfqws2-native
    fi
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
