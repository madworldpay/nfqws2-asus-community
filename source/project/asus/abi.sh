#!/bin/sh
# Read opkg architecture declarations without acquiring its install lock.
_asus_entware_arches() (
    # S51 runs with noglob. Expand only these fixed paths in this subshell.
    set +f
    local arch_mode="$1" arch_wanted="$2" arch_config arch_awk arch_result
    # A private awk shim can itself need this selector to find its BusyBox.
    # Never look up awk through PATH, or invoke that shim recursively.
    for arch_awk in /usr/bin/awk /bin/awk /opt/bin/awk; do
        [ -f "$arch_awk" ] && [ -x "$arch_awk" ] && break
    done
    if [ ! -f "$arch_awk" ] || [ ! -x "$arch_awk" ]; then
        [ "$arch_mode" = matches ] || printf '%s\n' 'Entware ABI: system awk unavailable' >&2
        return 1
    fi
    set --
    for arch_config in /opt/etc/opkg.conf /opt/etc/opkg/*.conf; do
        [ -r "$arch_config" ] || continue
        set -- "$@" "$arch_config"
    done
    if [ "$#" -eq 0 ]; then
        [ "$arch_mode" = matches ] || printf '%s\n' 'Entware ABI: configuration unavailable' >&2
        return 1
    fi
    arch_result=0
    LC_ALL=C ASUS_ABI_WANTED="$arch_wanted" "$arch_awk" -v mode="$arch_mode" '
        # libopkg/opkg_conf.c accepts quoted first/second/third tokens and
        # one unquoted fourth token; more trailing text invalidates the line.
        function word(last,   end, value, after) {
            sub(/^[[:space:]]*/, "", tail)
            if (substr(tail, 1, 1) == "\"") {
                end = index(substr(tail, 2), "\"")
                after = substr(tail, end + 2, 1)
                if (end && (!last || after == "" || after ~ /[[:space:]]/)) {
                    value = substr(tail, 2, end - 1)
                    tail = substr(tail, end + 2)
                    return value
                }
            }
            match(tail, /^[^[:space:]]*/)
            value = substr(tail, 1, RLENGTH)
            tail = substr(tail, RLENGTH + 1)
            return value
        }
        {
            tail = $0
            kind = word(0); abi = word(0); priority = word(1)
            sub(/^[[:space:]]*/, "", tail)
            sub(/^[^[:space:]]*/, "", tail)
            sub(/^[[:space:]]*/, "", tail)
            if (tail != "" || kind != "arch") next
            if (mode == "matches") {
                if (abi == ENVIRON["ASUS_ABI_WANTED"]) found = 1
                next
            }
            # opkg uses the first declaration for each architecture and
            # atoi(priority): empty/nonnumeric priorities therefore mean 0.
            if (abi in seen) next
            seen[abi] = 1
            if (abi == "all") next
            sub(/^[[:space:]]*/, "", priority)
            match(priority, /^[+-]?[0-9]+/)
            number = substr(priority, 1, RLENGTH) + 0
            # C int overflow varies by libc/word size; do not guess an ABI.
            if (number > 2147483647 || number < -2147483648) {
                invalid = 1
                next
            }
            if (!have || number > highest) {
                have = 1; highest = number; primary = abi; tied = 0
            } else if (number == highest) tied = 1
        }
        END {
            if (mode == "matches") exit !found
            if (invalid) exit 20
            if (!have || highest <= 0 || primary == "") exit 21
            if (tied) exit 22
            print primary
        }
    ' "$@" || arch_result=$?
    if [ "$arch_mode" != matches ]; then
        case "$arch_result" in
            0) ;;
            20) printf '%s\n' 'Entware ABI: priority outside supported integer range' >&2 ;;
            21) printf '%s\n' 'Entware ABI: no usable primary architecture' >&2 ;;
            22) printf '%s\n' 'Entware ABI: ambiguous primary architectures' >&2 ;;
            *) printf '%s\n' 'Entware ABI: cannot read architecture declarations' >&2 ;;
        esac
    fi
    return "$arch_result"
)

asus_entware_abi_matches() (
    _asus_entware_arches matches "${1-}"
)

# Print the highest-priority non-all architecture, including unknown ABIs.
asus_entware_primary_abi() (
    _asus_entware_arches primary ''
)

# Resolve one package family to its private runtime, never a secondary ABI.
asus_resolve_package_abi() (
    local package_family="${1-}" primary_abi
    case "$package_family" in
        armv7|aarch64-3.10) ;;
        *) printf '%s\n' 'Entware ABI: unsupported package family' >&2; return 1 ;;
    esac
    primary_abi=$(asus_entware_primary_abi) || return 1
    case "$package_family:$primary_abi" in
        armv7:armv7-2.6|armv7:armv7-3.2|aarch64-3.10:aarch64-3.10)
            printf '%s\n' "$primary_abi" ;;
        *) printf '%s\n' 'Entware ABI: primary architecture does not match package family' >&2; return 1 ;;
    esac
)
