#!/bin/sh
# Read-only. Never source user configuration, run preflight or acquire a lock.
asus_diagnostic_queue() {
    [ -r "$1" ] && [ -f "$1" ] || { echo null; return; }
    awk '
    /^[ \t]*(export[ \t]+)?NFQUEUE_NUM[ \t]*=/ {
        count++; value=$0; sub(/^[^=]*=[ \t]*/, "", value)
        sub(/[ \t]+#.*/, "", value); sub(/[ \t]+$/, "", value)
        quote=substr(value,1,1)
        if (quote == "\047" || quote == "\042") {
            if (substr(value,length(value),1) != quote) { invalid=1; next }
            value=substr(value,2,length(value)-2)
        }
        if (value !~ /^[0-9]+$/ || value+0 > 65535) invalid=1
        number=value+0
    }
    END { if (count == 0) print "300"; else if (count == 1 && !invalid) printf "%.0f\n", number; else print "null" }
    ' "$1" 2>/dev/null || echo null
}

asus_diagnostic_process() {
    local pid exe binary
    [ -r /proc/self/status ] || { echo null; return; }
    if [ ! -e "$PIDFILE" ]; then echo false; return; fi
    [ -r "$PIDFILE" ] && [ -f "$PIDFILE" ] || { echo null; return; }
    pid=$(cat "$PIDFILE" 2>/dev/null) || { echo null; return; }
    case "$pid" in ''|*[!0-9]*) echo false; return;; esac
    [ "$pid" -gt 1 ] 2>/dev/null || { echo false; return; }
    [ -d "/proc/$pid" ] || { echo false; return; }
    exe=$(readlink "/proc/$pid/exe" 2>/dev/null) || { echo null; return; }
    binary=$(readlink -f "$NFQWS_BIN" 2>/dev/null) || { echo null; return; }
    case "$exe" in "$binary"|"$binary (deleted)") echo true;; *) echo false;; esac
}

# A port id can be reused. Bind evidence to the boot, daemon start and owned
# NETLINK_NETFILTER socket inode; never expose these private identifiers.
nfqws_diagnostic_lifetime() (
    # The init script disables globbing; the fixed proc fd directory needs it.
    set +f
    local port=$1 pid=$2 binary=$3 proc_root=${4:-/proc} boot start exe inode fd owned=0 digest
    case "$port:$pid" in *[!0-9:]*|:*|*:) return;; esac
    [ "$pid" -gt 1 ] 2>/dev/null || return
    boot=$(cat "$proc_root/sys/kernel/random/boot_id" 2>/dev/null) || return
    [ "${#boot}" = 36 ] || return
    case "$boot" in *[!0-9a-f-]*) return;; esac
    exe=$(readlink "$proc_root/$pid/exe" 2>/dev/null) || return
    binary=$(readlink -f "$binary" 2>/dev/null) || return
    case "$exe" in "$binary"|"$binary (deleted)") ;; *) return;; esac
    start=$(awk '
        { sub(/^.*\) /, ""); if (NF >= 20 && $1 != "Z" && $20 ~ /^[0-9]+$/) print $20 }
        ' "$proc_root/$pid/stat" 2>/dev/null) || return
    case "$start" in ''|*[!0-9]*) return;; esac
    inode=$(awk -v port="$port" '
        $2 == 12 && $3 == port && $3 ~ /^[0-9]+$/ {
            count++; if (NF != 10 || $10 !~ /^[0-9]+$/ || $10+0 == 0) bad=1; value=$10
        }
        END { if (count == 1 && !bad) print value }
        ' "$proc_root/net/netlink" 2>/dev/null) || return
    case "$inode" in ''|*[!0-9]*) return;; esac
    for fd in "$proc_root/$pid/fd/"*; do
        [ "$(readlink "$fd" 2>/dev/null)" != "socket:[$inode]" ] || { owned=1; break; }
    done
    [ "$owned" = 1 ] || return
    digest=$(printf '%s\n' "$boot" "$pid" "$start" "$exe" "$port" "$inode" | sha256sum 2>/dev/null) || return
    digest=${digest%% *}
    [ "${#digest}" = 64 ] || return
    case "$digest" in *[!0-9a-f]*) return;; esac
    printf '%s\n' "$digest"
)

# The packet sequence is uint32. Diagnostics never reset its counter.
nfqws_diagnostic_queue_sample() {
    local queue=$1 file=$2
    [ -r "$file" ] && [ -f "$file" ] || { echo 'unknown null null'; return; }
    awk -v q="$queue" '
    $1+0 == q && $1 ~ /^[0-9]+$/ {
        found++; if (NF != 9) invalid=1
        for (i=1;i<=NF;i++) if ($i !~ /^[0-9]+$/ || $i+0 > 4294967295) invalid=1
        seq=$8+0; port=$2
    }
    END {
        if (invalid || found>1) print "unknown null null"
        else if (found) printf "bound %.0f %s\n",seq,port
        else print "unbound null null"
    }' "$file" 2>/dev/null || echo 'unknown null null'
}

asus_diagnostics_json() {
    local q=$1 proc_root=${2:-/proc} sys_root=${3:-/sys} ark_root=${4:-/usr/ark}
    local loaded=unknown present=unknown queue_state=unknown sequence=null queue=null result port pid lifetime=null first second sample
    if [ -d "$sys_root/module/ark" ]; then
        loaded=loaded
    elif [ -r "$proc_root/modules" ] && [ -f "$proc_root/modules" ] && [ -r "$sys_root/module" ] && [ -x "$sys_root/module" ]; then
        result=$(awk '$1 == "ark" { found=1 } END { print found ? "loaded" : "unloaded" }' "$proc_root/modules" 2>/dev/null) && loaded=$result
    fi
    if [ "$loaded" = loaded ]; then present=present
    elif [ -r "$ark_root" ] && [ -x "$ark_root" ]; then
        present=absent
        for result in ark.ko ark_service arkctl; do
            [ ! -f "$ark_root/$result" ] || present=present
        done
    elif [ ! -e "$ark_root" ] && [ -r "${ark_root%/*}" ] && [ "$loaded" = unloaded ]; then present=absent
    fi
    case "$q" in ''|*[!0-9]*) ;;
        *) queue=$(awk -v q="$q" 'BEGIN { if (q+0<=65535) printf "%.0f",q; else print "null" }');;
    esac
    if [ "$queue" != null ] && [ -r "$proc_root/net/netfilter/nfnetlink_queue" ] && [ -f "$proc_root/net/netfilter/nfnetlink_queue" ]; then
        sample=$(nfqws_diagnostic_queue_sample "$queue" "$proc_root/net/netfilter/nfnetlink_queue")
        port=${sample##* }
        if [ "${ASUS_DIAGNOSTIC_PROCESS:-null}" = true ]; then
            pid=$(cat "$PIDFILE" 2>/dev/null)
            first=$(nfqws_diagnostic_lifetime "$port" "$pid" "$NFQWS_BIN" "$proc_root")
            result=$(nfqws_diagnostic_queue_sample "$queue" "$proc_root/net/netfilter/nfnetlink_queue")
            second=$(nfqws_diagnostic_lifetime "${result##* }" "$pid" "$NFQWS_BIN" "$proc_root")
            # Sandwich the counter read; changing identity cannot authenticate it.
            [ -z "$first" ] || [ "$first" != "$second" ] || lifetime="\"$first\""
            sample=$result
        fi
        queue_state=${sample%% *}; result=${sample#* }; sequence=${result%% *}
    fi
    case "${ASUS_DIAGNOSTIC_PROCESS:-null}" in true|false|null) ;; *) ASUS_DIAGNOSTIC_PROCESS=null;; esac
    printf '{"ark":{"present":"%s","loaded":"%s"},"nfqueue":{"queue_number":%s,"state":"%s","sequence":%s,"lifetime":%s},"process_running":%s}\n' "$present" "$loaded" "$queue" "$queue_state" "$sequence" "$lifetime" "${ASUS_DIAGNOSTIC_PROCESS:-null}"
}
