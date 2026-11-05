# Preserve factory fingerprints and existing alternatives before opkg unpack.
# Active Lua is protected by conffiles; private alternatives retain owner bytes.
asus_lua_sidecar_file_safe() {
    local metadata mode owner size
    asus_migration_blob_parent_safe "${1%/*}" && asus_migration_blob_file_safe "$1" || return 1
    metadata=$(asus_migration_cmd stat -t "$1" | asus_migration_cmd awk '{print $(NF-11) " " $(NF-10) " " $(NF-13)}') || return 1
    mode=${metadata%% *};metadata=${metadata#* };owner=${metadata%% *};size=${metadata##* }
    case "$mode:$size" in *[!0-9a-fA-F:]*|:*) return 1;; esac
    [ "$owner" = "$ASUS_MIGRATION_OWNER" ] && [ "$((0x$mode & 07022))" = 0 ] && [ "$size" -le 8388608 ]
}

asus_lua_sidecars_save() {
    local state=$1 previous=$2 snapshot=$1/sidecar-snapshot garbage=$1/sidecar-complete stage path name factory metadata mode owner size total=0 count=0
    for stage in "$state"/.sidecars.??????; do
        [ -e "$stage" ] || [ -L "$stage" ] || continue
        case "${stage##*/}" in .sidecars.[A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9][A-Za-z0-9]) ;; *) continue;; esac
        [ -d "$stage" ] && [ ! -L "$stage" ] && asus_migration_blob_parent_safe "$stage" || return 1
        asus_migration_cmd rm -rf "$stage" || return 1
    done
    if [ -e "$garbage" ] || [ -L "$garbage" ]; then
        [ -d "$garbage" ] && [ ! -L "$garbage" ] && asus_migration_blob_parent_safe "$garbage" || return 1
        if [ -e "$previous" ] && [ ! -e "$snapshot" ]; then
            # Interrupted publication of a refreshed unfinished snapshot.
            asus_migration_cmd mv "$garbage" "$snapshot" && asus_migration_cmd sync || return 1
        else asus_migration_cmd rm -rf "$garbage" || return 1;fi
    fi
    if [ -e "$snapshot" ] || [ -L "$snapshot" ]; then
        [ -d "$snapshot" ] && [ ! -L "$snapshot" ] && asus_migration_blob_parent_safe "$snapshot" || return 1
        asus_migration_blob_file_safe "$snapshot/names" || return 1
        if [ ! -e "$previous" ]; then
            if [ -e "$snapshot/complete" ] || [ -L "$snapshot/complete" ]; then
                asus_migration_blob_file_safe "$snapshot/complete" || return 1
                [ "$(asus_migration_cmd cat "$snapshot/complete")" = 'restored' ] || return 1
            fi
            # The preceding postinst committed. Retain one snapshot until the
            # next upgrade. Without a baseline/complete marker, preinst never
            # reached unpack: refresh to include later operator edits too.
            asus_migration_cmd mv "$snapshot" "$garbage" && asus_migration_cmd sync && asus_migration_cmd rm -rf "$garbage" || return 1
        fi
    fi
    stage=$(asus_migration_cmd mktemp -d "$state/.sidecars.XXXXXX") || return 1
    if ! (
        printf 'NFQWS LUA SIDECARS 1\n' > "$stage/names" || exit 1
        for path in /opt/etc/nfqws2/lua/*.lua-opkg "$snapshot"/*.lua-opkg; do
            [ -e "$path" ] || [ -L "$path" ] || continue
            name=${path##*/}
            # Only canonical packaged Lua names can collide with opkg offers.
            # Other operator names are neither copied nor cleaned up.
            case "$name" in ''|*[!a-zA-Z0-9_.-]*) continue;; esac
            printf '%s\n' "$name" | asus_migration_cmd grep -Eq '^[a-zA-Z0-9][a-zA-Z0-9_.-]{0,123}\.lua-opkg$' || continue
            [ ! -e "$stage/$name" ] || continue
            asus_lua_sidecar_file_safe "$path" || exit 1
            if [ -e "$previous" ] && [ -e "$snapshot/$name" ]; then
                factory=/opt/share/nfqws2-asus/factory/lua/${name%-opkg}
                # Preserve the original across a completed unpack. A later
                # operator edit differs from factory and refreshes the copy.
                if asus_lua_sidecar_file_safe "$factory" &&
                    asus_migration_cmd cmp -s "$path" "$factory"; then path=$snapshot/$name;fi
            fi
            count=$((count + 1));[ "$count" -le 512 ] || exit 1
            asus_migration_blob_parent_safe "${path%/*}" && asus_migration_blob_file_safe "$path" || exit 1
            metadata=$(asus_migration_cmd stat -t "$path" | asus_migration_cmd awk '{print $(NF-11) " " $(NF-10) " " $(NF-13)}') || exit 1
            mode=${metadata%% *};metadata=${metadata#* };owner=${metadata%% *};size=${metadata##* }
            case "$mode:$size" in *[!0-9a-fA-F:]*|:*) exit 1;; esac
            [ "$owner" = "$ASUS_MIGRATION_OWNER" ] && [ "$((0x$mode & 07022))" = 0 ] && [ "$size" -le 8388608 ] || exit 1
            total=$((total + size));[ "$total" -le 33554432 ] || exit 1
            asus_migration_cmd cp -p "$path" "$stage/$name" && asus_migration_cmd cmp -s "$path" "$stage/$name" || exit 1
            printf '%s\n' "$name" >> "$stage/names" || exit 1
        done
        asus_migration_cmd chmod 600 "$stage/names" && asus_migration_cmd sync || exit 1
    ); then
        asus_migration_cmd rm -rf "$stage";return 1
    fi
    if [ -e "$snapshot" ]; then
        asus_migration_cmd mv "$snapshot" "$garbage" && asus_migration_cmd sync || return 1
    fi
    if asus_migration_cmd mv "$stage" "$snapshot" && asus_migration_cmd sync && asus_migration_cmd rm -rf "$garbage"; then return 0;fi
    [ ! -d "$stage" ] || asus_migration_cmd rm -rf "$stage"
    return 1
}

asus_lua_upgrade_save() {
    local source=/opt/share/nfqws2-asus/report-baseline.json
    local state=/opt/var/lib/nfqws2-asus/lua-upgrade
    local previous=$state/previous-baseline.json stage metadata mode owner size
    [ -e "$source" ] || [ -L "$source" ] || return 0
    asus_migration_select_busybox || return 1
    asus_migration_blob_parent_safe "${source%/*}" && asus_migration_blob_file_safe "$source" || return 1
    metadata=$(asus_migration_cmd stat -t "$source" | asus_migration_cmd awk '{print $(NF-11) " " $(NF-10) " " $(NF-13)}') || return 1
    mode=${metadata%% *};metadata=${metadata#* };owner=${metadata%% *};size=${metadata##* }
    case "$mode:$size" in *[!0-9a-fA-F:]*|:*) return 1;; esac
    [ "$owner" = "$ASUS_MIGRATION_OWNER" ] && [ "$((0x$mode & 0022))" = 0 ] && [ "$size" -le 1048576 ] || return 1
    umask 077
    asus_migration_blob_parent_safe "${state%/*}" && asus_migration_safe_dir "$state" || return 1
    asus_lua_sidecars_save "$state" "$previous" || return 1
    if [ -e "$previous" ] || [ -L "$previous" ]; then
        # Keep the original fingerprints across interrupted unpack/postinst.
        asus_migration_blob_file_safe "$previous"
        return $?
    fi
    stage=$state/previous-baseline.new
    if [ -e "$stage" ] || [ -L "$stage" ]; then
        asus_migration_blob_file_safe "$stage" || return 1
        metadata=$(asus_migration_cmd stat -t "$stage" | asus_migration_cmd awk '{print $(NF-11) " " $(NF-10)}') || return 1
        mode=${metadata% *};owner=${metadata##* }
        case "$mode" in ''|*[!0-9a-fA-F]*) return 1;; esac
        [ "$owner" = "$ASUS_MIGRATION_OWNER" ] && [ "$((0x$mode & 0022))" = 0 ] && asus_migration_cmd rm "$stage" || return 1
    fi
    asus_migration_cmd cp -p "$source" "$stage" && asus_migration_cmd chmod 600 "$stage" &&
        asus_migration_cmd cmp -s "$source" "$stage" && asus_migration_cmd sync || return 1
    asus_migration_cmd mv "$stage" "$previous" && asus_migration_cmd sync
}
