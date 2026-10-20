# Embedded in preinst, available before the new payload is unpacked.
ASUS_MIGRATION_DIR=/opt/etc/nfqws2-asus-migration
ASUS_MIGRATION_BUSYBOX=/opt/libexec/nfqws2-asus/busybox
ASUS_MIGRATION_OWNER=0
asus_migration_cmd() { "$ASUS_MIGRATION_BUSYBOX" "$@"; }
asus_migration_safe_dir() {
    [ ! -L "$1" ] || return 1
    asus_migration_cmd mkdir -p "$1" || return 1
    [ "$(asus_migration_cmd stat -t "$1" | asus_migration_cmd awk '{print $5}')" = "$ASUS_MIGRATION_OWNER" ] || return 1
    asus_migration_cmd chmod 700 "$1"
}
asus_migration_verify() {
    [ ! -L "$ASUS_MIGRATION_DIR" ] && [ ! -L "$ASUS_MIGRATION_DIR/snapshot" ] || return 1
    [ -f "$ASUS_MIGRATION_DIR/snapshot/manifest" ] || return 1
    (cd "$ASUS_MIGRATION_DIR/snapshot" && asus_migration_cmd sha256sum -c manifest >/dev/null)
}
asus_migration_save() {
    # Fresh installs have no old private BusyBox/data to migrate.
    if [ ! -x "$ASUS_MIGRATION_BUSYBOX" ]; then
        for path in /opt/etc/nfqws2/nfqws2.conf /opt/etc/nfqws2/lists /opt/etc/nfqws-asus-web/auth.json /opt/etc/nfqws-asus-web/ark-backup.json; do
            [ ! -e "$path" ] && [ ! -L "$path" ] || { echo 'Cannot back up existing data: private BusyBox missing.' >&2; return 1; }
        done
        return 0
    fi
    umask 077
    asus_migration_safe_dir "$ASUS_MIGRATION_DIR" || return 1
    if [ -e "$ASUS_MIGRATION_DIR/snapshot" ] || [ -L "$ASUS_MIGRATION_DIR/snapshot" ]; then
        asus_migration_verify
        return $?
    fi
    local stage="$ASUS_MIGRATION_DIR/stage.$$" path src key
    [ ! -e "$stage" ] && [ ! -L "$stage" ] || return 1
    asus_migration_safe_dir "$stage" || return 1
    for key in config lists auth ark; do
        case "$key" in
            config) path=/opt/etc/nfqws2/nfqws2.conf;;
            lists) path=/opt/etc/nfqws2/lists;;
            auth) path=/opt/etc/nfqws-asus-web/auth.json;;
            ark) path=/opt/etc/nfqws-asus-web/ark-backup.json;;
        esac
        src=$path
        if [ ! -e "$path" ] && [ ! -L "$path" ] && [ -e "$path.opkg-save" ]; then src=$path.opkg-save; fi
        [ ! -L "$src" ] || return 1
        if [ -e "$src" ]; then
            case "$src" in */nfqws2/*) [ ! -L /opt/etc/nfqws2 ] || return 1;; *) [ ! -L /opt/etc/nfqws-asus-web ] || return 1;; esac
            if [ -d "$src" ]; then
                local links
                links=$(asus_migration_cmd find "$src" -type l) || return 1
                [ -z "$links" ] || return 1
            elif [ ! -f "$src" ]; then return 1
            fi
            asus_migration_cmd cp -pR "$src" "$stage/$key" || return 1
            if [ "$key" = lists ]; then
                # Inactive package samples are not user data to restore over a newer release.
                asus_migration_cmd find "$stage/lists" -type f -name '*.notactive' -exec "$ASUS_MIGRATION_BUSYBOX" rm '{}' ';' || return 1
            fi
            printf '%s present\n' "$key" >> "$stage/presence" || return 1
        else
            printf '%s absent\n' "$key" >> "$stage/presence" || return 1
        fi
    done
    (cd "$stage" && asus_migration_cmd find . -type f -exec "$ASUS_MIGRATION_BUSYBOX" sha256sum '{}' ';') > "$stage/manifest.new" || return 1
    # The manifest itself is not one of its input files.
    asus_migration_cmd grep -v ' ./manifest.new$' "$stage/manifest.new" > "$stage/manifest" || return 1
    asus_migration_cmd rm "$stage/manifest.new" || return 1
    asus_migration_cmd chmod 600 "$stage/manifest" "$stage/presence" || return 1
    asus_migration_cmd sync || return 1
    asus_migration_cmd mv "$stage" "$ASUS_MIGRATION_DIR/snapshot" || return 1
    asus_migration_cmd sync
}
asus_migration_restore() {
    [ -e "$ASUS_MIGRATION_DIR/snapshot" ] || return 0
    asus_migration_verify || return 1
    [ ! -L "$ASUS_MIGRATION_DIR/data-restored" ] || return 1
    [ ! -f "$ASUS_MIGRATION_DIR/data-restored" ] || return 0
    [ ! -f "$ASUS_MIGRATION_DIR/complete" ] || return 0
    local key path src
    for key in config lists auth ark; do
        case "$key" in
            config) path=/opt/etc/nfqws2/nfqws2.conf;;
            lists) path=/opt/etc/nfqws2/lists;;
            auth) path=/opt/etc/nfqws-asus-web/auth.json;;
            ark) path=/opt/etc/nfqws-asus-web/ark-backup.json;;
        esac
        src=$ASUS_MIGRATION_DIR/snapshot/$key
        if [ -e "$src" ]; then
            [ ! -L "$path" ] || return 1
            asus_migration_cmd mkdir -p "${path%/*}" || return 1
            if [ "$key" = lists ]; then
                asus_migration_cmd cp -pR "$src/." "$path/" || return 1
            else
                asus_migration_cmd cp -p "$src" "$path" || return 1
            fi
        fi
    done
    asus_migration_cmd sync || return 1
    # Data recovery is complete before web/core expose settings to the owner.
    # A failed service start must never replay this snapshot over later edits.
    [ ! -L "$ASUS_MIGRATION_DIR/data-restored.new" ] || return 1
    [ ! -e "$ASUS_MIGRATION_DIR/data-restored.new" ] || [ -f "$ASUS_MIGRATION_DIR/data-restored.new" ] || return 1
    printf 'Original data restored.\n' > "$ASUS_MIGRATION_DIR/data-restored.new" || return 1
    asus_migration_cmd chmod 600 "$ASUS_MIGRATION_DIR/data-restored.new" || return 1
    asus_migration_cmd sync || return 1
    asus_migration_cmd mv "$ASUS_MIGRATION_DIR/data-restored.new" "$ASUS_MIGRATION_DIR/data-restored" || return 1
    asus_migration_cmd sync
}
asus_migration_complete() {
    [ -e "$ASUS_MIGRATION_DIR/snapshot" ] || return 0
    asus_migration_verify || return 1
    [ ! -L "$ASUS_MIGRATION_DIR/complete" ] || return 1
    printf 'Migration completed; original snapshot retained.\n' > "$ASUS_MIGRATION_DIR/complete" || return 1
    asus_migration_cmd chmod 600 "$ASUS_MIGRATION_DIR/complete" || return 1
    asus_migration_cmd sync
}
