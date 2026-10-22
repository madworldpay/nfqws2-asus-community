# Embedded in preinst, available before the new payload is unpacked.
ASUS_MIGRATION_DIR=/opt/etc/nfqws2-asus-migration
ASUS_MIGRATION_BUSYBOX=/opt/libexec/nfqws2-asus/busybox
ASUS_MIGRATION_OWNER=0
asus_migration_cmd() { "$ASUS_MIGRATION_BUSYBOX" "$@"; }
asus_migration_busybox_ready() {
    local tool=$1 applets applet owner
    [ -f "$tool" ] && [ -x "$tool" ] || return 1
    applets=$("$tool" --list 2>/dev/null) || return 1
    for applet in awk chmod cp find grep mkdir mv rm sha256sum stat sync; do
        case "
$applets
" in *"
$applet
"*) ;; *) return 1;; esac
    done
    owner=$("$tool" stat -t /proc/self/status 2>/dev/null | "$tool" awk '{print $5}') || return 1
    [ "$owner" = "$ASUS_MIGRATION_OWNER" ] || return 1
    printf '%s  /dev/null\n' e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855 |
        "$tool" sha256sum -c - >/dev/null 2>&1 || return 1
    if printf '%s  /dev/null\n' 0000000000000000000000000000000000000000000000000000000000000000 |
        "$tool" sha256sum -c - >/dev/null 2>&1; then return 1; fi
}
asus_migration_select_busybox() {
    local candidate bootstrap='' abi_tool='' private=$ASUS_MIGRATION_BUSYBOX
    ASUS_MIGRATION_PRIVATE_READY=0
    case "${ASUS_PACKAGE_ABI:-}" in
        aarch64-3.10|armv7-2.6|armv7-3.2)
            # opkg extracts control files into the same private directory as
            # preinst before running it, including on a removed-package install.
            # BusyBox dispatches by argv[0]; the ELF name must start with busybox.
            case "$0" in */*) bootstrap=${0%/*}/busybox-migration-$ASUS_PACKAGE_ABI;; esac
            abi_tool=/opt/libexec/nfqws2-asus/$ASUS_PACKAGE_ABI/busybox;;
    esac
    for candidate in "$private" "$bootstrap" "$abi_tool" /opt/bin/busybox /bin/busybox; do
        [ -n "$candidate" ] || continue
        if asus_migration_busybox_ready "$candidate"; then
            ASUS_MIGRATION_BUSYBOX=$candidate
            [ "$candidate" != "$private" ] || ASUS_MIGRATION_PRIVATE_READY=1
            return 0
        fi
    done
    return 1
}
asus_migration_has_data() {
    local path
    for path in /opt/etc/nfqws2/nfqws2.conf /opt/etc/nfqws2/lists /opt/etc/nfqws-asus-web/auth.json /opt/etc/nfqws-asus-web/ark-backup.json "$ASUS_MIGRATION_DIR/snapshot"; do
        [ ! -e "$path" ] && [ ! -L "$path" ] && [ ! -e "$path.opkg-save" ] && [ ! -L "$path.opkg-save" ] || return 0
    done
    return 1
}
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
    # A clean install needs no snapshot. After remove, settings remain while
    # package-owned tools are absent: use the control bootstrap, never skip data.
    if [ ! -x "$ASUS_MIGRATION_BUSYBOX" ] && ! asus_migration_has_data; then return 0; fi
    if ! asus_migration_select_busybox; then
        asus_migration_has_data || return 0
        echo 'Cannot back up existing data: no compatible BusyBox with SHA256/stat support.' >&2
        return 1
    fi
    umask 077
    asus_migration_safe_dir "$ASUS_MIGRATION_DIR" || return 1
    [ ! -L "$ASUS_MIGRATION_DIR/data-restored" ] && [ ! -L "$ASUS_MIGRATION_DIR/complete" ] || return 1
    if [ -e "$ASUS_MIGRATION_DIR/snapshot" ] || [ -L "$ASUS_MIGRATION_DIR/snapshot" ]; then
        asus_migration_verify || return 1
        if [ "$ASUS_MIGRATION_PRIVATE_READY" = 1 ] || { [ ! -f "$ASUS_MIGRATION_DIR/data-restored" ] && [ ! -f "$ASUS_MIGRATION_DIR/complete" ]; }; then return 0; fi
        # A completed snapshot belongs to an earlier installation. Preserve it
        # atomically and back up the current owner data before this reinstall.
        local previous index=1
        while :; do
            [ "$index" -le 1000 ] || return 1
            previous=$ASUS_MIGRATION_DIR.previous.$index
            [ -e "$previous" ] || [ -L "$previous" ] || break
            index=$((index + 1))
        done
        [ ! -L "$ASUS_MIGRATION_DIR/defaults-initialized" ] || return 1
        asus_migration_cmd mv "$ASUS_MIGRATION_DIR" "$previous" || return 1
        asus_migration_safe_dir "$ASUS_MIGRATION_DIR" || return 1
        if [ -f "$previous/defaults-initialized" ]; then
            asus_migration_cmd cp -p "$previous/defaults-initialized" "$ASUS_MIGRATION_DIR/defaults-initialized" || return 1
        fi
    elif [ -e "$ASUS_MIGRATION_DIR/data-restored" ] || [ -e "$ASUS_MIGRATION_DIR/complete" ]; then
        # A missing snapshot with completion markers is damaged state.
        return 1
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
        if [ ! -e "$path" ] && [ ! -L "$path" ] && { [ -e "$path.opkg-save" ] || [ -L "$path.opkg-save" ]; }; then src=$path.opkg-save; fi
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
