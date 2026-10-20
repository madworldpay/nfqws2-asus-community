# Package templates live beside active files and are never sourced here.
asus_install_defaults() {
    local template active found=0
    for template in /opt/etc/nfqws2/nfqws2.conf.notactive /opt/etc/nfqws2/lists/*.notactive; do
        [ ! -f "$template" ] || found=1
    done
    [ "$found" = 1 ] || return 0
    asus_migration_safe_dir "$ASUS_MIGRATION_DIR" || return 1
    [ ! -L "$ASUS_MIGRATION_DIR/defaults-initialized" ] || return 1
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
        asus_migration_cmd cp -pn "$template" "$active" || return 1
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
