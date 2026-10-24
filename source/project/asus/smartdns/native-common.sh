#!/bin/sh
# Installed together on JFFS. No PHP, Entware utilities or profile secrets.
. /jffs/nfqws2-asus-smartdns/native-state.sh || exit 2
. /jffs/nfqws2-asus-smartdns/primary-dns.sh || exit 2
sd_owner=0
sd_hook=/jffs/scripts/dnsmasq.postconf
sd_opt=/opt/etc/nfqws-asus-web
sd_updates=/opt/var/lib/nfqws2-asus/updates

sd_protected() {
    [ ! -L "$1" ] || return 1
    "$sd_bb" ls -ldn "$1" 2>/dev/null | "$sd_bb" awk -v owner="$sd_owner" -v kind="$2" '
      NR==1 {ok=($3==owner && substr($1,1,1)==kind && substr($1,6,1)!="w" && substr($1,9,1)!="w" && (kind=="d" || $2==1))}
      END {exit !(NR==1 && ok)}'
}
sd_lock() {
    sd_protected "$sd_root" d && sd_protected "$sd_root/state" - && sd_protected "$sd_root/state.lock" - || return 1
    exec 7>>"$sd_root/state.lock" || return 1
    /usr/bin/flock -n 7 || return 3
}
sd_unlock() { /usr/bin/flock -u 7;exec 7>&-; }
sd_startof() {
    local line rest
    case "$1" in ''|*[!0-9]*) return 1;; esac
    [ "$1" -gt 1 ] 2>/dev/null || return 1
    IFS= read -r line 2>/dev/null < "/proc/$1/stat" || return 1
    rest=${line##*) };set -- $rest
    [ "${1:-Z}" != Z ] && [ -n "${20:-}" ] || return 1
    printf '%s\n' "${20}"
}
sd_same() { [ -n "$2" ] && [ "$(sd_startof "$1")" = "$2" ]; }
sd_runtime_alive() {
    [ "$sd_boot_id" = "$sd_current_boot" ] && sd_same "$sd_runtime_pid" "$sd_runtime_ticks" || return 1
    sd_exe=$("$sd_bb" readlink "/proc/$sd_runtime_pid/exe" 2>/dev/null) || return 1
    [ "$sd_exe" = "$sd_runtime_exe" ] || [ "$sd_exe" = "$sd_runtime_exe (deleted)" ]
}
sd_before() { "$sd_bb" awk -v end="$1" '{exit !($1<end)}' /proc/uptime; }
sd_now() { "$sd_bb" awk '{printf "%.3f\n",$1}' /proc/uptime; }
sd_log() {
    # Only fixed result tokens, never DNS names, addresses, query history,
    # upstream URLs or raw tool output. Two bounded 64KiB files.
    case "$1" in guard_ready|confirmed|rolled_back|hook_conflict|primary_dns_unverified|dns_restart_failed|dns_validation_failed|runtime_stop_failed|runtime_lost|timed_out|interrupted|invalid_state) :;; *) return 1;; esac
    [ ! -L "$sd_root/recovery.log" ] && [ ! -L "$sd_root/recovery.log.1" ] || return 1
    if [ -f "$sd_root/recovery.log" ]; then
        sd_bytes=$("$sd_bb" wc -c < "$sd_root/recovery.log")
        if [ "$sd_bytes" -ge 65000 ] 2>/dev/null; then "$sd_bb" mv "$sd_root/recovery.log" "$sd_root/recovery.log.1" || return 1;fi
    fi
    sd_log_request=${sd_request_id:--}
    case "$sd_log_request" in ''|*[!a-f0-9]*) sd_log_request=-;; esac
    [ "${#sd_log_request}" = 32 ] || sd_log_request=-
    printf '%s %s %s\n' "$(sd_now)" "$sd_log_request" "$1" >> "$sd_root/recovery.log"
}
sd_conflict() { sd_phase=conflict;sd_state_save || return 1;sd_log "$1";return 1; }

sd_install_hook() {
    sd_protected "$sd_root/hook-original" - && sd_protected "$sd_root/owned-block" - || return 1
    sd_next=/jffs/scripts/.nfqws2-smartdns.$$.new
    [ ! -e "$sd_next" ] && [ ! -L "$sd_next" ] && [ ! -L "$sd_hook" ] || return 1
    if [ "$sd_hook_created" = 1 ]; then
        [ ! -e "$sd_hook" ] || return 1
        (set -C;printf '#!/bin/sh\n' > "$sd_next") 2>/dev/null || return 1
        "$sd_bb" chmod 700 "$sd_next" || return 1
    else
        sd_protected "$sd_hook" - && "$sd_bb" cmp -s "$sd_hook" "$sd_root/hook-original" || return 1
        # Match the PHP preflight: one exact existing block is idempotent.
        # Validate every marker before adopting it; never append a duplicate.
        if "$sd_bb" grep -q 'NFQWS2 SMARTDNS MANAGED' "$sd_root/hook-original"; then
            sd_protected "$sd_root/hook-edit.awk" - || return 1
            sd_ending=0;[ -z "$("$sd_bb" tail -c 1 "$sd_root/hook-original")" ] && sd_ending=1
            "$sd_bb" awk -v expected="$sd_root/owned-block" -v ending="$sd_ending" -f "$sd_root/hook-edit.awk" "$sd_root/hook-original" > /dev/null || return 1
            "$sd_bb" cmp -s "$sd_hook" "$sd_root/hook-original"
            return $?
        fi
        "$sd_bb" cp -p "$sd_hook" "$sd_next" || return 1
    fi
    sd_ok=0
    if "$sd_bb" cat "$sd_root/owned-block" >> "$sd_next"; then
        sd_bytes=$("$sd_bb" wc -c < "$sd_next")
        if [ "$sd_bytes" -le 262144 ] 2>/dev/null; then
            if [ "$sd_hook_created" = 1 ]; then
                if [ ! -e "$sd_hook" ] && [ ! -L "$sd_hook" ] && "$sd_bb" mv "$sd_next" "$sd_hook"; then sd_ok=1;fi
            elif sd_protected "$sd_hook" - && "$sd_bb" cmp -s "$sd_hook" "$sd_root/hook-original" && "$sd_bb" mv "$sd_next" "$sd_hook"; then sd_ok=1;fi
        fi
    fi
    "$sd_bb" rm -f "$sd_next"
    [ "$sd_ok" = 1 ]
}

sd_forward() {
    sd_error=guard_unavailable
    [ "$sd_phase" = prepared ] && sd_runtime_alive && sd_same "$sd_guard_pid" "$sd_guard_ticks" || return 1
    sd_error=primary_dns_unverified
    sd_before_dns=$(sd_primary_identity) || return 1
    printf '%s\n' "$sd_before_dns" > "$sd_root/.dns-before.$$" || return 1
    "$sd_bb" mv "$sd_root/.dns-before.$$" "$sd_root/dns-before" || return 1
    sd_error=hook_conflict
    sd_install_hook || return 1
    sd_deadline=$("$sd_bb" awk '{printf "%.3f\n",$1+120}' /proc/uptime)
    sd_phase=awaiting_confirmation;sd_error=invalid_state
    sd_state_save || return 1
    if ! sd_restart_verified forwarded "$sd_before_dns"; then sd_error=dns_restart_failed;sd_rollback || :;return 1;fi
    sd_error=;return 0
}

sd_forward_config() {
    sd_protected /tmp/etc/dnsmasq.conf - || return 1
    "$sd_bb" awk '
        {line=$0;sub(/^[ \t]+/,"",line);sub(/[ \t\r]+$/,"",line)}
        line=="no-resolv" {noresolve++;next}
        line~/^server[ \t]*=/ {if (line!="server=127.0.0.1#6054") bad=1;server++;next}
        line~/^(resolv-file|servers-file|conf-file|conf-dir|conf-script)[ \t]*=/ {bad=1}
        END {exit (bad || noresolve!=1 || server!=1)}' /tmp/etc/dnsmasq.conf
}
# Merlin creates these two native resolver data files as 0666. They are
# parsed only as bounded DNS data, never sourced/executed. Keep ownership,
# type/link and all content checks; do not relax executable/config protection.
sd_native_resolver_data() {
    case "$1" in /tmp/resolv.dnsmasq|/tmp/resolv.conf) :;; *) return 1;; esac
    [ ! -L "$1" ] || return 1
    "$sd_bb" ls -ldn "$1" 2>/dev/null | "$sd_bb" awk -v owner="$sd_owner" '
      NR==1 {ok=($3==owner && substr($1,1,1)=="-" && $2==1)}
      END {exit !(NR==1 && ok)}'
}
sd_restored_config() (
    # Configuration includes are data, not executable recovery dependencies.
    # Inspect a bounded graph before stopping our listener; never evaluate a
    # conf-script or assume an unknown include cannot still forward to us.
    set -f
    newline='
'
    IFS=$newline
    literal_awk='
        function literal(line, end,suffix,out) {
            sub(/^[^=]*=[ \t]*/,"",line)
            if (index(line,"\\")) return ""
            if (substr(line,1,1)=="\"") {
                end=index(substr(line,2),"\"")+1;if (end==1) return ""
                out=substr(line,2,end-2);suffix=substr(line,end+1)
                if (suffix!~/^[ \t\r]*$/ && suffix!~/^[ \t\r]+#/) return ""
                # Whitespace inside the quotes belongs to the filename.
            } else {
                out=line;sub(/[ \t\r]+#.*/,"",out);sub(/[ \t\r]+$/,"",out)
                if (index(out,"\"")) return ""
            }
            if (length(out)>1024 || out!~/^\/[A-Za-z0-9_.+\/ -]+$/ || out~/\/\/|\/(\.\.?)(\/|$)/) return ""
            return out
        }
    '
    queue=/tmp/etc/dnsmasq.conf
    configs=;seen=$newline;files=0;total=0;depth=0
    while [ -n "$queue" ]; do
        depth=$((depth+1));[ "$depth" -le 8 ] || return 1
        next=
        for file in $queue; do
            case "$seen" in *"$newline$file$newline"*) continue;; esac
            sd_protected "$file" - || return 1
            bytes=$("$sd_bb" wc -c < "$file") || return 1
            files=$((files+1));total=$((total+bytes))
            [ "$files" -le 32 ] && [ "$bytes" -le 262144 ] && [ "$total" -le 1048576 ] || return 1
            "$sd_bb" tr -d '\000' < "$file" | "$sd_bb" cmp -s "$file" - || return 1
            configs=$configs$file$newline;seen=$seen$file$newline
            includes=$("$sd_bb" awk "$literal_awk"'
                {line=$0;sub(/^[ \t\r]+/,"",line);sub(/[ \t\r]+$/,"",line)}
                line~/^conf-file[ \t]*=/ {
                    # Only a literal absolute path; no escape evaluation.
                    path=literal(line);if (path=="") exit 2
                    print path
                }' "$file") || return 1
            if [ -n "$includes" ]; then next=$next$includes$newline;fi
        done
        queue=$next
    done
    good1=0;good2=0
    for file in /tmp/resolv.dnsmasq /tmp/resolv.conf; do
        good=0
        if sd_native_resolver_data "$file"; then
            bytes=$("$sd_bb" wc -c < "$file")
            [ "$bytes" -le 262144 ] 2>/dev/null && good=1
        fi
        case "$file" in /tmp/resolv.dnsmasq) good1=$good;; *) good2=$good;; esac
    done
    # A successful public-name query alone cannot prove independence. Every
    # accepted include and native resolver source must pass the same check.
    "$sd_bb" awk -v configs="$configs" -v main=/tmp/etc/dnsmasq.conf -v servers1=/tmp/resolv.dnsmasq -v servers2=/tmp/resolv.conf -v good1="$good1" -v good2="$good2" "$literal_awk"'
        function trim(s) {sub(/^[ \t\r]+/,"",s);sub(/[ \t\r]+$/,"",s);return s}
        function numeric4(s,octets,n,i) {
            n=split(s,octets,".");if (n!=4) return 0
            for (i=1;i<=4;i++) {
                if (octets[i]!~/^[0-9]+$/ || octets[i]>255 || (length(octets[i])>1 && substr(octets[i],1,1)=="0")) return 0
            }
            return octets[1]!=127 && s!="0.0.0.0"
        }
        function independent(s,parts,n,endpoint,hex,kind,quotes) {
            # dnsmasq also accepts legacy integer/octal IPv4 forms. Only
            # supported numeric syntax may prove that a listener is external.
            if (index(s,"\\")) return 0
            quotes=gsub(/"/,"",s);if (quotes%2) return 0
            s=trim(tolower(s));sub(/[ \t]+#.*/,"",s)
            if (s~/^nameserver[ \t]+/) sub(/^nameserver[ \t]+/,"",s)
            else {
                kind=s;sub(/[ \t]*=.*/,"",kind);sub(/^[^=]*=[ \t]*/,"",s)
                if (kind=="rev-server") {n=split(s,parts,",");if (n!=2) return 0;s=parts[2]}
                else if (kind=="server") sub(/^.*\//,"",s)
                else return 0
                if (s=="" || s=="#") return 1
            }
            endpoint=trim(s);sub(/[#@].*/,"",endpoint);gsub(/[\[\]]/,"",endpoint);sub(/%.*/,"",endpoint)
            if (!index(endpoint,":")) return numeric4(endpoint)
            if (endpoint!~/^[0-9a-f:.]+$/) return 0
            hex=endpoint;gsub(/[:0]/,"",hex);if (hex=="" || hex=="1") return 0
            if (endpoint~/(^|:)ffff:/) {
                hex=endpoint;sub(/^.*ffff:/,"",hex)
                if (index(hex,".")) return numeric4(hex)
                if (hex~/^0*7f[0-9a-f][0-9a-f]:/ || hex~/^0+:0+$/) return 0
            } else if (index(endpoint,".")) return 0
            return 1
        }
        function source(path,kind, line,status,count,total) {
            if ((path!=servers1 || !good1) && (path!=servers2 || !good2)) return 0
            count=0;total=0
            while ((status=getline line < path)>0) {
                if (++count>4096 || (total+=length(line)+1)>262144) {close(path);return 0}
                line=trim(line);if (line=="" || line~/^#/) continue
                if (kind=="servers-file") {
                    if (line!~/^server[ \t]*=/ || !independent(line)) {close(path);return 0}
                } else if (line~/^nameserver[ \t]+/) {
                    if (!independent(line)) {close(path);return 0}
                } else if (line!~/^(search|domain|options)[ \t]+/) {close(path);return 0}
            }
            close(path);return status==0
        }
        function directive(line,depth, kind,path) {
            line=trim(line);if (line=="" || line~/^#/) return 1
            if (line~/^(conf-dir|conf-script)[ \t]*(=|$)/) return 0
            if (line~/^conf-file[ \t]*(=|$)/) {
                if (line!~/^conf-file[ \t]*=/) return 0
                path=literal(line)
                return path!="" && configuration(path,depth+1)
            }
            if (line~/^(server|rev-server)[ \t]*=/) return independent(line)
            if (line~/^(servers-file|resolv-file)[ \t]*=/) {
                kind=line;sub(/[ \t]*=.*/,"",kind);path=line;sub(/^[^=]*=[ \t]*/,"",path)
                return source(trim(path),kind)
            }
            return 1
        }
        function configuration(path,depth, line,status,count,total,ok) {
            if (!allowed[path] || depth>8 || active[path]) return 0
            if (checked[path]) return 1
            active[path]=1;count=0;total=0;ok=1
            while ((status=getline line < path)>0) {
                if (++count>4096 || (total+=length(line)+1)>262144 || !directive(line,depth)) {ok=0;break}
            }
            close(path);delete active[path]
            if (!ok || status!=0) return 0
            checked[path]=1;return 1
        }
        BEGIN {
            n=split(configs,paths,"\n");for (i=1;i<=n;i++) if (paths[i]!="") allowed[paths[i]]=1
            exit !configuration(main,1)
        }'
)

sd_forward_ready() {
    sd_protected "$sd_root/dns-before" - || return 1
    IFS=' ' read -r sd_old_pid sd_old_ticks sd_extra < "$sd_root/dns-before" || return 1
    [ -z "$sd_extra" ] && sd_pid "$sd_old_pid" && sd_digits "$sd_old_ticks" 20 || return 1
    sd_primary_now=$(sd_primary_identity) || return 1
    [ "$sd_primary_now" != "$sd_old_pid $sd_old_ticks" ] && sd_forward_config
}
sd_restart_verified() {
    local stage previous end iterations queries current
    stage=$1;previous=$2
    end=$("$sd_bb" awk '{printf "%.3f\n",$1+12}' /proc/uptime)
    sd_restart_dns || return 1
    iterations=0;queries=0
    # Firmware service may return before rc creates the new daemon. An answer
    # from the old cached resolver must never confirm the new forwarding.
    while sd_before "$end" && [ "$iterations" -lt 12 ]; do
        current=$(sd_primary_identity) || current=
        if [ -n "$current" ] && [ "$current" != "$previous" ]; then
            if { [ "$stage" = forwarded ] && sd_forward_config; } || { [ "$stage" = restored ] && sd_restored_config; }; then
                sd_dns53 && return 0
                queries=$((queries+1));[ "$queries" -lt 3 ] || return 1
            fi
        fi
        iterations=$((iterations+1));"$sd_bb" sleep 1
    done
    return 1
}

sd_remove_hook() {
    [ ! -L "$sd_hook" ] || return 1
    [ -e "$sd_hook" ] || return 0
    sd_protected "$sd_hook" - && sd_protected "$sd_root/owned-block" - && sd_protected "$sd_root/hook-edit.awk" - || return 1
    sd_bytes=$("$sd_bb" wc -c < "$sd_hook")
    [ "$sd_bytes" -le 262144 ] 2>/dev/null || return 1
    sd_copy=$sd_root/.hook.$$.copy;sd_clean=$sd_root/.hook.$$.clean
    sd_next=/jffs/scripts/.nfqws2-smartdns.$$.new
    [ ! -e "$sd_copy" ] && [ ! -e "$sd_clean" ] && [ ! -e "$sd_next" ] && [ ! -L "$sd_copy" ] && [ ! -L "$sd_clean" ] && [ ! -L "$sd_next" ] || return 1
    "$sd_bb" cp -p "$sd_hook" "$sd_copy" || return 1
    sd_ok=0
    if "$sd_bb" tr -d '\000' < "$sd_copy" | "$sd_bb" cmp -s "$sd_copy" -; then
        if ! "$sd_bb" grep -q 'NFQWS2 SMARTDNS MANAGED' "$sd_copy"; then sd_ok=1
        else
            sd_ending=0;[ -z "$("$sd_bb" tail -c 1 "$sd_copy")" ] && sd_ending=1
            if "$sd_bb" awk -v expected="$sd_root/owned-block" -v ending="$sd_ending" -f "$sd_root/hook-edit.awk" "$sd_copy" > "$sd_clean" &&
                sd_protected "$sd_hook" - && "$sd_bb" cmp -s "$sd_hook" "$sd_copy" &&
                "$sd_bb" cp -p "$sd_hook" "$sd_next" && "$sd_bb" cat "$sd_clean" > "$sd_next" &&
                "$sd_bb" cmp -s "$sd_hook" "$sd_copy" && "$sd_bb" mv "$sd_next" "$sd_hook"; then sd_ok=1;fi
        fi
    fi
    "$sd_bb" rm -f "$sd_copy" "$sd_clean" "$sd_next"
    [ "$sd_ok" = 1 ]
}
sd_restart_dns() {
    # Firmware service asks rc to regenerate dnsmasq using current hooks and
    # NVRAM. Never overwrite the generated config with an old snapshot.
    /sbin/service restart_dnsmasq >/dev/null 2>&1 7>&- 8>&- 9>&- &
    sd_child=$!;sd_child_ticks=$(sd_startof "$sd_child");sd_wait=0
    while sd_same "$sd_child" "$sd_child_ticks"; do
        if [ "$sd_wait" -ge 10 ]; then
            kill -TERM "$sd_child" 2>/dev/null || :;"$sd_bb" sleep 1
            if sd_same "$sd_child" "$sd_child_ticks"; then kill -KILL "$sd_child" 2>/dev/null || :;fi
            wait "$sd_child" 2>/dev/null || :;return 1
        fi
        sd_wait=$((sd_wait+1));"$sd_bb" sleep 1
    done
    wait "$sd_child"
}
sd_dns53() {
    sd_protected "$sd_root/dns-probe" - && [ -x "$sd_root/dns-probe" ] || return 1
    "$sd_root/dns-probe" 127.0.0.1 53 example.com A udp 2500 >/dev/null 2>&1 7>&- 8>&- 9>&-
}
sd_stop_runtime() {
    sd_runtime_alive || return 0
    kill -TERM "$sd_runtime_pid" 2>/dev/null || :
    sd_wait=0
    while sd_runtime_alive && [ "$sd_wait" -lt 2 ]; do sd_wait=$((sd_wait+1));"$sd_bb" sleep 1;done
    if sd_runtime_alive; then kill -KILL "$sd_runtime_pid" 2>/dev/null || return 1;fi
    sd_wait=0
    while sd_runtime_alive && [ "$sd_wait" -lt 2 ]; do sd_wait=$((sd_wait+1));"$sd_bb" sleep 1;done
    ! sd_runtime_alive
}
sd_rollback() {
    [ "$sd_phase" != rolled_back ] || return 0
    sd_phase=rolling_back;sd_state_save || return 1
    sd_remove_hook || { sd_conflict hook_conflict;return 1; }
    sd_before_dns=$(sd_primary_identity) || { sd_conflict primary_dns_unverified;return 1; }
    sd_restart_verified restored "$sd_before_dns" || { sd_conflict dns_restart_failed;return 1; }
    sd_stop_runtime || { sd_conflict runtime_stop_failed;return 1; }
    sd_phase=rolled_back;sd_state_save || return 1
    sd_log rolled_back || :
    return 0
}
