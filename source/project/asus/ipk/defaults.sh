# Package templates live beside active files and are never sourced here.
asus_install_default() {
    local source=$1 destination=$2 stage result=1
    [ ! -L "$destination" ] || return 1
    if [ -e "$destination" ]; then [ -f "$destination" ]; return $?; fi
    [ -f "$source" ] && [ ! -L "$source" ] && [ ! -L "${destination%/*}" ] || return 1
    # Stage on the destination filesystem. No failed or interrupted copy is
    # visible under the active name, and link(2) never replaces owner data.
    stage=$(asus_migration_cmd mktemp -d "${destination%/*}/.nfqws2-default.XXXXXX") || return 1
    if ! asus_migration_safe_dir "$stage"; then asus_migration_cmd rmdir "$stage"; return 1; fi
    if asus_migration_cmd cp -p "$source" "$stage/file" &&
        asus_migration_cmd cmp -s "$source" "$stage/file" && asus_migration_cmd sync; then
        if asus_migration_cmd ln -T "$stage/file" "$destination" 2>/dev/null; then
            asus_migration_cmd sync && result=0
        elif [ ! -L "$destination" ] && [ -f "$destination" ]; then
            # Another owner operation published its file first; preserve it.
            result=0
        fi
    fi
    asus_migration_cmd rm -f "$stage/file" || result=1
    asus_migration_cmd rmdir "$stage" || result=1
    return "$result"
}

asus_install_defaults() {
    local template active list sample referenced found=0
    for template in /opt/etc/nfqws2/nfqws2.conf.notactive /opt/etc/nfqws2/lists/*.notactive; do
        [ ! -f "$template" ] || found=1
    done
    [ "$found" = 1 ] || return 0
    asus_migration_safe_dir "$ASUS_MIGRATION_DIR" || return 1
    [ ! -L "$ASUS_MIGRATION_DIR/defaults-initialized" ] || return 1
    # The core always needs a config, even when a reinstall retains lists or
    # a previous defaults marker. Migration has already restored owner data;
    # initialize a missing config and its required stock lists from the current
    # payload. Existing configs keep the owner's deliberately deleted lists.
    template=/opt/etc/nfqws2/nfqws2.conf.notactive
    active=/opt/etc/nfqws2/nfqws2.conf
    if [ ! -e "$active" ] && [ ! -L "$active" ]; then
        [ ! -L /opt/etc/nfqws2 ] && [ -f "$template" ] && [ ! -L "$template" ] || return 1
        [ ! -L /opt/etc/nfqws2/lists ] || return 1
        for list in user.list auto.list exclude.list ipset.list ipset_exclude.list; do
            referenced=0
            asus_migration_cmd grep -Fq -- "/opt/etc/nfqws2/lists/$list" "$template" || referenced=$?
            [ "$referenced" -le 1 ] || return 1
            [ "$referenced" = 0 ] || continue
            sample=/opt/etc/nfqws2/lists/$list.notactive
            [ ! -L "/opt/etc/nfqws2/lists/$list" ] || return 1
            if [ -e "/opt/etc/nfqws2/lists/$list" ]; then
                [ -f "/opt/etc/nfqws2/lists/$list" ] || return 1
                continue
            fi
            [ -f "$sample" ] && [ ! -L "$sample" ] || return 1
            asus_install_default "$sample" "/opt/etc/nfqws2/lists/$list" || return 1
        done
        # Publish the config last so an interrupted copy can be retried without
        # accepting a new config whose required stock files are still absent.
        asus_install_default "$template" "$active" || return 1
    fi
    [ ! -f "$ASUS_MIGRATION_DIR/defaults-initialized" ] || return 0
    # Any prior NFQWS2 data means this is a migration, not a clean install.
    if [ -f "$ASUS_MIGRATION_DIR/snapshot/presence" ]; then
        asus_migration_cmd grep -Eq '^config present$' "$ASUS_MIGRATION_DIR/snapshot/presence" && return 0
        if [ -d "$ASUS_MIGRATION_DIR/snapshot/lists" ]; then
            local active_lists
            active_lists=$(asus_migration_cmd find "$ASUS_MIGRATION_DIR/snapshot/lists" -type f) || return 1
            [ -z "$active_lists" ] || return 0
        fi
    fi
    for template in /opt/etc/nfqws2/nfqws2.conf.notactive /opt/etc/nfqws2/lists/*.notactive; do
        [ -f "$template" ] && [ ! -L "$template" ] || continue
        active=${template%.notactive}
        [ ! -e "$active" ] && [ ! -L "$active" ] || continue
        asus_install_default "$template" "$active" || return 1
    done
    # Later upgrades must not recreate intentionally deleted lists or activate new ones.
    [ ! -L "$ASUS_MIGRATION_DIR/defaults-initialized.new" ] || return 1
    [ ! -e "$ASUS_MIGRATION_DIR/defaults-initialized.new" ] || [ -f "$ASUS_MIGRATION_DIR/defaults-initialized.new" ] || return 1
    printf 'Initial defaults installed.\n' > "$ASUS_MIGRATION_DIR/defaults-initialized.new" || return 1
    asus_migration_cmd chmod 600 "$ASUS_MIGRATION_DIR/defaults-initialized.new" || return 1
    asus_migration_cmd sync || return 1
    asus_migration_cmd mv "$ASUS_MIGRATION_DIR/defaults-initialized.new" "$ASUS_MIGRATION_DIR/defaults-initialized" || return 1
    asus_migration_cmd sync
}
