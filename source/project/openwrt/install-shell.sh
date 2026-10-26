# Native bootstrap helpers, embedded in the one-command installer.
# These functions do not change manager configuration, keys or installed state.
nfqws_native_database_safe() {
    case "$1" in
        ipk) LC_ALL=C awk '
            BEGIN {RS=""; FS="\n"}
            function bad(){failed=1;exit}
            {name="";status="";nc=0;sc=0;records++;
                for(i=1;i<=NF;i++){
                    if($i~/^Package: /){name=substr($i,10);nc++}
                    if($i~/^Status: /){status=substr($i,9);sc++}
                }
                if(nc!=1 || name!~/^[a-z0-9][a-z0-9+._-]*$/)bad();
                if(name=="nfqws2-native")next;
                if(sc!=1 || split(status,s," ")!=3)bad();
                n=split(s[2],flags,",");delete seen;
                for(i=1;i<=n;i++){if(flags[i]!~/^(ok|user|prefer|hold)$/ || seen[flags[i]]++)bad()}
                if(s[3]=="not-installed" || s[3]=="config-files")next;
                if(s[3]!="installed" || s[1]!~/^(install|hold)$/)bad();
            }
            END {if(failed || !records)exit 1}
        ' "$2";;
        apk) LC_ALL=C awk '
            BEGIN {RS="";FS="\n"}
            function bad(){failed=1;exit}
            {name="";flags="";nc=0;vc=0;fc=0;records++;
                for(i=1;i<=NF;i++){
                    if($i~/^P:/){name=substr($i,3);nc++}
                    if($i~/^V:/)vc++;
                    if($i~/^f:/){flags=substr($i,3);fc++}
                }
                if(nc!=1 || vc!=1 || name!~/^[a-z0-9][a-z0-9+._-]*$/)bad();
                if(name=="nfqws2-native")next;
                if(fc>1 || flags!~/^[Sx]*$/)bad();
            }
            END {if(failed || !records)exit 1}
        ' "$2";;
        *) return 1;;
    esac
}

nfqws_native_signed_config() {
    [ "$#" -gt 0 ] || return 1
    LC_ALL=C awk '
        /^[ \t]*#/ {next}
        $1=="option" && $2=="check_signature" {
            value=$3;sub(/#.*/,"",value);
            if(value=="" || value=="1" || value=="true" || value=="on")found=1;else failed=1
        }
        END {if(!found || failed)exit 1}
    ' "$@"
}

nfqws_native_install_only_plan() {
    case "$1" in
        ipk) LC_ALL=C awk '
            function bad(){failed=1;exit}
            /^$/ {next}
            /^Installing [a-z0-9][a-z0-9+._-]* \([A-Za-z0-9.+_:~\-]+\) to root\.\.\.$/ {planned++;next}
            /^Package [a-z0-9][a-z0-9+._-]* \([A-Za-z0-9.+_:~\-]+\) installed in root is up to date\.$/ {planned++;next}
            /^Downloading (https?:\/\/|file:\/\/\/)[^ \t\r]+$/ {next}
            {bad()}
            END {if(failed || !planned)exit 1}
        ';;
        apk) LC_ALL=C awk '
            function bad(){failed=1;exit}
            /^$/ {next}
            /^\( *[0-9]+\/[0-9]+\) Installing [a-z0-9][a-z0-9+._-]* \([A-Za-z0-9.+_:~\-]+\)$/ {planned++;next}
            /^OK: [0-9]+(\.[0-9]+)? (B|KiB|MiB|GiB) in [0-9]+ packages$/ {next}
            {bad()}
            END {if(failed || !planned)exit 1}
        ';;
        *) return 1;;
    esac
}

# No timeout or signal forwarding to a native package transaction. The private
# work directory is retained if SSH exits before the command has completed.
nfqws_native_background() {
    NFQWS_NATIVE_KEEP=1
    rm -f "$NFQWS_NATIVE_WORK/job.status" "$NFQWS_NATIVE_WORK/job.pid" || return 1
    cat > "$NFQWS_NATIVE_WORK/job.sh" <<'NFQWS_JOB'
#!/bin/sh
trap '' HUP
umask 077
nfqws_job_dir=$1
shift
exec 9>&-
printf '%s\n' "$$" > "$nfqws_job_dir/job.pid" || exit 1
"$@" < /dev/null >> "$nfqws_job_dir/job.log" 2>&1
nfqws_job_result=$?
printf '%s\n' "$nfqws_job_result" > "$nfqws_job_dir/job.status.new" && mv "$nfqws_job_dir/job.status.new" "$nfqws_job_dir/job.status"
exit "$nfqws_job_result"
NFQWS_JOB
    /bin/busybox start-stop-daemon -S -b -p "$NFQWS_NATIVE_WORK/unused-job.pid" -x /bin/sh -- "$NFQWS_NATIVE_WORK/job.sh" "$NFQWS_NATIVE_WORK" "$@" || return 1
    nfqws_job_attempt=0
    while [ ! -f "$NFQWS_NATIVE_WORK/job.pid" ]; do
        nfqws_job_attempt=$((nfqws_job_attempt+1))
        [ "$nfqws_job_attempt" -lt 5 ] || return 1
        sleep 1
    done
    nfqws_job_pid=$(cat "$NFQWS_NATIVE_WORK/job.pid")
    case "$nfqws_job_pid" in ''|*[!0-9]*) return 1;; esac
    while [ ! -f "$NFQWS_NATIVE_WORK/job.status" ]; do
        kill -0 "$nfqws_job_pid" 2>/dev/null || { [ -f "$NFQWS_NATIVE_WORK/job.status" ] && break; return 1; }
        sleep 1
    done
    nfqws_job_status=$(cat "$NFQWS_NATIVE_WORK/job.status")
    case "$nfqws_job_status" in 0) NFQWS_NATIVE_KEEP=0; return 0;; *) return 1;; esac
}

nfqws_native_signed_opkg() {
    nfqws_config_files=/etc/opkg.conf
    for nfqws_config in /etc/opkg/*.conf; do [ ! -f "$nfqws_config" ] || nfqws_config_files="$nfqws_config_files $nfqws_config"; done
    nfqws_native_signed_config $nfqws_config_files
}

nfqws_native_bootstrap_lock() {
    nfqws_lock_dir=/tmp/nfqws2-native-bootstrap
    [ ! -L "$nfqws_lock_dir" ] || return 1
    if [ ! -e "$nfqws_lock_dir" ]; then mkdir -m 700 "$nfqws_lock_dir" || return 1; fi
    [ -d "$nfqws_lock_dir" ] && [ "$(LC_ALL=C ls -dn "$nfqws_lock_dir" | awk '{print $1,$3}')" = 'drwx------ 0' ] || return 1
    [ ! -L "$nfqws_lock_dir/install.lock" ] || return 1
    if [ -e "$nfqws_lock_dir/install.lock" ]; then
        [ -f "$nfqws_lock_dir/install.lock" ] && [ "$(LC_ALL=C ls -ln "$nfqws_lock_dir/install.lock" | awk '{print $1,$2,$3}')" = '-rw------- 1 0' ] || return 1
    fi
    exec 9> "$nfqws_lock_dir/install.lock" || return 1
    flock -n 9
}
