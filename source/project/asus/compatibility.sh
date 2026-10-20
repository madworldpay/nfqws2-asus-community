#!/bin/sh
# Private service dispatch. Never replace system or Entware executables.
asus_native_xtables_path() { printf '/usr/sbin/%s\n' "$1"; }

asus_xtables() (
    local cmd=$1 style path
    shift
    case "$cmd" in
        iptables|iptables-restore|iptables-save) style=${ASUS_XTABLES4:-entware} ;;
        ip6tables|ip6tables-restore|ip6tables-save) style=${ASUS_XTABLES6:-entware} ;;
        *) exit 1 ;;
    esac
    case "$style" in
        entware) command "$cmd" "$@" ;;
        native|native-no-w)
            path=$(asus_native_xtables_path "$cmd") || exit 1
            [ -x "$path" ] || exit 1
            if [ "$style" = native-no-w ] && [ "$1" = -w ]; then shift; fi
            # Old firmware tools lack -w. Serialize our callers, including
            # restore/save, instead of pretending they have an xtables lock.
            # This cannot make unrelated old firmware tools honor our lock.
            exec 7>"$RUN_DIR/xtables.lock" || exit 1
            flock -w 5 7 || exit 1
            "$path" "$@"
            ;;
        *) exit 1 ;;
    esac
)
iptables() { asus_xtables iptables "$@"; }
ip6tables() { asus_xtables ip6tables "$@"; }

asus_read_compatibility() {
    local tool4 dir4 tool6 dir6 extra file=$RUN_DIR/compatibility
    [ ! -L "$RUN_DIR" ] && [ -f "$file" ] && [ ! -L "$file" ] || return 1
    read -r tool4 dir4 tool6 dir6 extra < "$file" || return 1
    [ -z "$extra" ] || return 1
    case "$tool4:$tool6" in
        entware:entware|entware:native|entware:native-no-w|native:entware|native:native|native:native-no-w|native-no-w:entware|native-no-w:native|native-no-w:native-no-w) ;;
        *) return 1 ;;
    esac
    case "$dir4:$dir6" in normal:normal|normal:reverse|reverse:normal|reverse:reverse) ;; *) return 1;; esac
    ASUS_XTABLES4=$tool4; ASUS_CT4=$dir4
    ASUS_XTABLES6=$tool6; ASUS_CT6=$dir6
}

asus_choose_family_tools() {
    local cmd=$1 style direction
    for style in entware native native-no-w; do
        case "$cmd" in
            iptables) ASUS_XTABLES4=$style ;;
            ip6tables) ASUS_XTABLES6=$style ;;
            *) return 1 ;;
        esac
        asus_probe_family "$cmd" || continue
        direction=$(asus_probe_direction "$cmd") || continue
        case "$direction" in normal|reverse) ;; *) continue;; esac
        case "$cmd" in iptables) ASUS_CT4=$direction;; ip6tables) ASUS_CT6=$direction;; esac
        return 0
    done
    return 1
}

asus_choose_tools() {
    asus_choose_family_tools iptables || return 1
    ASUS_XTABLES6=entware; ASUS_CT6=normal
    if [ "$IPV6_ENABLED" = 1 ]; then
        asus_choose_family_tools ip6tables || return 1
    fi
}

# Only start commits dispatch with its runtime config. A check of newly
# saved settings must not replace the choices of an already running daemon.
asus_save_compatibility() {
    printf '%s %s %s %s\n' "$ASUS_XTABLES4" "$ASUS_CT4" "$ASUS_XTABLES6" "$ASUS_CT6" > "$RUN_DIR/compatibility.new" || return 1
    chmod 600 "$RUN_DIR/compatibility.new" || return 1
    mv "$RUN_DIR/compatibility.new" "$RUN_DIR/compatibility"
}
