#!/bin/sh
# Sourced with the platform's core mutex held. Settings are data, never shell.
nfqws_restart_settings() {
    local config=${NFQWS_RESTART_CONFIG:-/opt/etc/nfqws2/restart-schedule.conf} settings
    [ -e "$config" ] || return 1
    nfqws_restart_file_safe "$config" 256 || return 2
    settings=$(awk '
      NR==1 && /^enabled=[01]$/ {enabled=substr($0,9);next}
      NR==2 && /^interval_hours=[1-9][0-9]*$/ {hours=substr($0,16);next}
      NR==3 && /^watchdog_enabled=[01]$/ {watchdog=substr($0,18);next}
      NR==4 && /^revision=[a-f0-9]+$/ && length($0)==41 {revision=substr($0,10);next}
      NR==5 && /^watchdog_revision=[a-f0-9]+$/ && length($0)==50 {wr=substr($0,19);next}
      {bad=1}
      END {if(bad||NR!=5||enabled==""||hours+0<1||hours+0>168||watchdog==""||revision==""||wr=="")exit 1;print enabled,hours,watchdog,revision,wr}
    ' "$config") || return 2
    set -- $settings
    NFQWS_TIMER_ENABLED=$1; NFQWS_TIMER_HOURS=$2; NFQWS_WATCHDOG_ENABLED=$3
    NFQWS_TIMER_REVISION=$4; NFQWS_WATCHDOG_REVISION=$5
}

nfqws_restart_now() {
    awk '{split($1,a,".");if(a[1]~/^[0-9]+$/)print a[1]}' "${NFQWS_RESTART_UPTIME:-/proc/uptime}"
}

nfqws_restart_file_safe() {
    [ -f "$1" ] && [ ! -L "$1" ] || return 2
    # Base OpenWrt ships numeric ls, but does not require the stat applet.
    LC_ALL=C ls -ln "$1" 2>/dev/null | awk -v owner=0 -v limit="$2" '
      NR==1 && $1=="-rw-------" && $2==1 && $3==owner && $5~/^[0-9]+$/ && $5+0<=limit {safe=1}
      END {exit !(NR==1&&safe)}'
}

nfqws_restart_state_safe() { nfqws_restart_file_safe "$1" 128; }

nfqws_restart_schedule_due() {
    local pid=$1 state=${NFQWS_RESTART_STATE:-$RUN_DIR/restart-schedule} proc=${NFQWS_RESTART_PROC:-/proc}
    local now ticks identity saved anchor tmp
    nfqws_restart_settings || return 1
    [ "$NFQWS_TIMER_ENABLED" = 1 ] || return 1
    case "$pid" in ''|*[!0-9]*) return 2;; esac
    ticks=$(sed 's/^.*) //' "$proc/$pid/stat" 2>/dev/null | awk '{print $20}')
    case "$ticks" in ''|*[!0-9]*) return 2;; esac
    now=$(nfqws_restart_now)
    case "$now" in ''|*[!0-9]*) return 2;; esac
    identity="$NFQWS_TIMER_REVISION:$NFQWS_TIMER_HOURS:$pid:$ticks"
    [ ! -L "$state" ] || return 2
    saved=''; anchor=''
    if [ -f "$state" ]; then nfqws_restart_state_safe "$state" || return 2; read -r saved anchor < "$state"; fi
    case "$anchor" in ''|*[!0-9]*) anchor=$((now + 1));; esac
    if [ "$saved" != "$identity" ] || [ "$now" -lt "$anchor" ]; then
        tmp="$state.new.$$"
        [ ! -e "$tmp" ] && [ ! -L "$tmp" ] || return 2
        (umask 077; set -C; printf '%s %s\n' "$identity" "$now" > "$tmp") || return 2
        mv "$tmp" "$state" || { rm -f "$tmp"; return 2; }
        return 1
    fi
    [ "$((now - anchor))" -ge "$((NFQWS_TIMER_HOURS * 3600))" ]
}

nfqws_watchdog_write() {
    local state=${NFQWS_WATCHDOG_STATE:-$RUN_DIR/watchdog-state} tmp
    [ ! -L "$state" ] || return 2
    tmp="$state.new.$$"; [ ! -e "$tmp" ] && [ ! -L "$tmp" ] || return 2
    (umask 077; set -C; printf '%s %s %s %s\n' "$NFQWS_WATCHDOG_REVISION" "$NFQWS_WATCHDOG_ATTEMPTS" "$NFQWS_WATCHDOG_NEXT" "$NFQWS_WATCHDOG_PHASE" > "$tmp") || return 2
    mv "$tmp" "$state" || { rm -f "$tmp"; return 2; }
}

nfqws_watchdog_load() {
    local state=${NFQWS_WATCHDOG_STATE:-$RUN_DIR/watchdog-state} revision extra
    nfqws_restart_settings || return 1
    [ "$NFQWS_WATCHDOG_ENABLED" = 1 ] || return 1
    NFQWS_WATCHDOG_ATTEMPTS=0; NFQWS_WATCHDOG_NEXT=0; NFQWS_WATCHDOG_PHASE=ready
    [ ! -L "$state" ] || return 2
    if [ -f "$state" ]; then
        nfqws_restart_state_safe "$state" || return 2
        read -r revision NFQWS_WATCHDOG_ATTEMPTS NFQWS_WATCHDOG_NEXT NFQWS_WATCHDOG_PHASE extra < "$state" || return 2
        case "$NFQWS_WATCHDOG_ATTEMPTS:$NFQWS_WATCHDOG_PHASE" in [0123]:ready|[0123]:waiting|3:locked) ;; *) return 2;; esac
        case "$NFQWS_WATCHDOG_NEXT" in ''|*[!0-9]*) return 2;; esac
        [ "${#NFQWS_WATCHDOG_NEXT}" -le 10 ] && [ -z "$extra" ] || return 2
        if [ "$revision" != "$NFQWS_WATCHDOG_REVISION" ]; then
            NFQWS_WATCHDOG_ATTEMPTS=0; NFQWS_WATCHDOG_NEXT=0; NFQWS_WATCHDOG_PHASE=ready
        fi
    fi
}

nfqws_watchdog_due() {
    local now delay
    nfqws_watchdog_load || return 1
    now=$(nfqws_restart_now); case "$now" in ''|*[!0-9]*) return 2;; esac
    if [ "$NFQWS_WATCHDOG_ATTEMPTS" -ge 3 ]; then
        NFQWS_WATCHDOG_PHASE=locked; NFQWS_WATCHDOG_NEXT=0; nfqws_watchdog_write || return 2
        return 1
    fi
    if [ "$NFQWS_WATCHDOG_PHASE" = ready ]; then
        case "$NFQWS_WATCHDOG_ATTEMPTS" in 0) delay=60;; 1) delay=300;; 2) delay=900;; esac
        NFQWS_WATCHDOG_NEXT=$((now + delay)); NFQWS_WATCHDOG_PHASE=waiting
        nfqws_watchdog_write || return 2
        return 1
    fi
    [ "$now" -ge "$NFQWS_WATCHDOG_NEXT" ]
}

nfqws_watchdog_attempt() {
    local now delay
    nfqws_watchdog_due || return 1
    now=$(nfqws_restart_now)
    NFQWS_WATCHDOG_ATTEMPTS=$((NFQWS_WATCHDOG_ATTEMPTS + 1))
    case "$NFQWS_WATCHDOG_ATTEMPTS" in
        1) delay=300;; 2) delay=900;; 3) NFQWS_WATCHDOG_PHASE=locked;delay=0;; *) return 2;;
    esac
    NFQWS_WATCHDOG_NEXT=0
    [ "$delay" = 0 ] || NFQWS_WATCHDOG_NEXT=$((now + delay))
    nfqws_watchdog_write
}

nfqws_watchdog_running() {
    nfqws_watchdog_load || return 0
    NFQWS_WATCHDOG_PHASE=ready;NFQWS_WATCHDOG_NEXT=0
    nfqws_watchdog_write
}
