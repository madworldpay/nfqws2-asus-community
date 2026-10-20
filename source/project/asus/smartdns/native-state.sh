#!/bin/sh
# Fixed recovery metadata only. This file is code; the state file is never
# sourced, evaluated, used as a command, or copied into an executable script.
sd_root=/jffs/nfqws2-asus-smartdns
sd_bb=/bin/busybox

sd_digits() {
    case "$1" in ''|*[!0-9]*) return 1;; esac
    [ "${#1}" -le "$2" ]
}
sd_pid() { sd_digits "$1" 10 && [ "$1" -le 2147483647 ] 2>/dev/null; }
sd_state_validate() {
    [ "$sd_schema" = 1 ] || return 1
    case "$sd_request_id" in *[!a-f0-9]*|'') return 1;; esac
    [ "${#sd_request_id}" = 32 ] || return 1
    case "$sd_profile_hash" in *[!a-f0-9]*|'') return 1;; esac
    [ "${#sd_profile_hash}" = 64 ] || return 1
    case "$sd_boot_id" in *[!a-f0-9-]*) return 1;; esac
    case "$sd_boot_id" in ????????-????-????-????-????????????) :;; *) return 1;; esac
    case "$sd_phase" in prepared|awaiting_confirmation|confirmed|rolling_back|rolled_back|conflict) :;; *) return 1;; esac
    case "$sd_deadline" in ''|*[!0-9.]*|.*|*.*.*|*.) return 1;; esac
    sd_whole=${sd_deadline%.*};sd_fraction=${sd_deadline#*.}
    sd_digits "$sd_whole" 16 && sd_digits "$sd_fraction" 3 && [ "${#sd_fraction}" = 3 ] && [ "$sd_fraction" != "$sd_deadline" ] || return 1
    sd_pid "$sd_guard_pid" && sd_pid "$sd_runtime_pid" && sd_digits "$sd_guard_ticks" 20 && sd_digits "$sd_runtime_ticks" 20 || return 1
    case "$sd_hook_created" in 0|1) :;; *) return 1;; esac
    if [ "$sd_guard_pid" = 0 ]; then [ "$sd_guard_ticks" = 0 ] || return 1
    else [ "$sd_guard_pid" -gt 1 ] && [ "$sd_guard_ticks" != 0 ] || return 1;fi
    if [ "$sd_runtime_pid" = 0 ]; then
        [ "$sd_runtime_ticks" = 0 ] && [ -z "$sd_runtime_exe" ] || return 1
    else
        [ "$sd_runtime_pid" -gt 1 ] && [ "$sd_runtime_ticks" != 0 ] || return 1
        # A literal path used only for /proc/exe identity comparison. Quoting
        # preserves spaces/metacharacters in a USB volume name without eval.
        case "$sd_runtime_exe" in /*) :;; *) return 1;; esac
        [ "${#sd_runtime_exe}" -le 4096 ] || return 1
    fi
    case "$sd_phase" in awaiting_confirmation|confirmed)
        [ "$sd_guard_pid" -gt 1 ] && [ "$sd_runtime_pid" -gt 1 ] || return 1;; esac
}

sd_state_load() {
    [ -d "$sd_root" ] && [ ! -L "$sd_root" ] && [ -f "$sd_root/state" ] && [ ! -L "$sd_root/state" ] || return 1
    sd_size=$("$sd_bb" wc -c < "$sd_root/state") || return 1
    set -- $sd_size
    sd_digits "${1:-}" 6 && [ "$1" -le 16384 ] || return 1
    # stdin comparison avoids writing flash on each health/status read.
    "$sd_bb" tr -d '\000' < "$sd_root/state" | "$sd_bb" cmp -s "$sd_root/state" - || return 1
    sd_schema=;sd_request_id=;sd_boot_id=;sd_phase=;sd_deadline=
    sd_guard_pid=;sd_guard_ticks=;sd_runtime_pid=;sd_runtime_ticks=
    sd_runtime_exe=;sd_hook_created=;sd_profile_hash=
    sd_seen='|';sd_count=0;sd_tab=$(printf '\t')
    while IFS= read -r sd_line; do
        case "$sd_line" in *"$sd_tab"*) :;; *) return 1;; esac
        sd_key=${sd_line%%"$sd_tab"*};sd_value=${sd_line#*"$sd_tab"}
        case "$sd_value" in *"$sd_tab"*) return 1;; esac
        case "$sd_seen" in *"|$sd_key|"*) return 1;; esac
        sd_seen=$sd_seen$sd_key'|';sd_count=$((sd_count+1))
        case "$sd_key" in
            schema) sd_schema=$sd_value;;
            request_id) sd_request_id=$sd_value;;
            boot_id) sd_boot_id=$sd_value;;
            phase) sd_phase=$sd_value;;
            deadline) sd_deadline=$sd_value;;
            guard_pid) sd_guard_pid=$sd_value;;
            guard_ticks) sd_guard_ticks=$sd_value;;
            runtime_pid) sd_runtime_pid=$sd_value;;
            runtime_ticks) sd_runtime_ticks=$sd_value;;
            runtime_exe) sd_runtime_exe=$sd_value;;
            hook_created) sd_hook_created=$sd_value;;
            profile_hash) sd_profile_hash=$sd_value;;
            *) return 1;;
        esac
    done < "$sd_root/state"
    [ "$sd_count" = 12 ] && sd_state_validate
}

sd_state_save() {
    sd_state_validate || return 1
    [ -d "$sd_root" ] && [ ! -L "$sd_root" ] && [ ! -L "$sd_root/state" ] || return 1
    sd_new=$sd_root/.state.$$.new
    (umask 077;set -C;: > "$sd_new") 2>/dev/null || return 1
    if ! {
        printf '%s\t%s\n' schema "$sd_schema" request_id "$sd_request_id" boot_id "$sd_boot_id" phase "$sd_phase" deadline "$sd_deadline" \
            guard_pid "$sd_guard_pid" guard_ticks "$sd_guard_ticks" runtime_pid "$sd_runtime_pid" runtime_ticks "$sd_runtime_ticks" \
            runtime_exe "$sd_runtime_exe" hook_created "$sd_hook_created" profile_hash "$sd_profile_hash"
    } > "$sd_new"; then "$sd_bb" rm -f "$sd_new";return 1;fi
    "$sd_bb" mv "$sd_new" "$sd_root/state"
}
