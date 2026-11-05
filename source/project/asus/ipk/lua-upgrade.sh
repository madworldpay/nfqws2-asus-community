# Preserve the old factory fingerprints before opkg replaces report-baseline.
# Active Lua is protected by conffiles; this snapshot never contains owner Lua.
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
