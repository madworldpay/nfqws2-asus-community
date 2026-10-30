#!/bin/sh
# NFQWS2 ASUS bootstrap for an existing Entware installation. No sourced downloads.
PATH=/opt/sbin:/opt/bin:/usr/sbin:/usr/bin:/sbin:/bin
export PATH
umask 077

fail() { printf '\nОшибка: %s\n' "$*" >&2; exit 1; }
say() { printf '%s\n' "$*"; }
tool() {
    for directory in $(printf '%s' "$PATH" | tr ':' ' '); do
        if [ -f "$directory/$1" ] && [ -x "$directory/$1" ]; then
            printf '%s\n' "$directory/$1"; return 0
        fi
    done
    return 1
}
cleanup() { [ -z "$WORK" ] || rm -rf "$WORK"; }

download() {
    download_url=$1 download_file=$2 download_cap=$3
    # ulimit also bounds GNU wget, which has no per-file size limit.
    if [ -n "$CURL" ]; then
        (
            ulimit -f "$(( (download_cap + 511) / 512 ))" || exit 1
            set -- -fSL --connect-timeout 10 --max-time 180 --retry 2 --max-redirs 5 \
                --proto '=https' --proto-redir '=https' --max-filesize "$download_cap"
            [ ! -f /opt/etc/ssl/certs/ca-certificates.crt ] || set -- "$@" --cacert /opt/etc/ssl/certs/ca-certificates.crt
            "$CURL" "$@" -o "$download_file" "$download_url"
        ) || fail 'Не удалось скачать файл. Проверьте интернет, время роутера и HTTPS-доступ к GitHub; затем повторите команду.'
    else
        (
            ulimit -f "$(( (download_cap + 511) / 512 ))" || exit 1
            set -- --timeout=20 --tries=2 --max-redirect=5 --https-only
            [ ! -f /opt/etc/ssl/certs/ca-certificates.crt ] || set -- "$@" --ca-certificate=/opt/etc/ssl/certs/ca-certificates.crt
            "$WGET" "$@" -O "$download_file" "$download_url"
        ) || fail 'Не удалось скачать файл с GitHub. Проверьте интернет, время роутера и сертификаты HTTPS.'
    fi
    download_bytes=$(wc -c < "$download_file") || fail 'Не удалось прочитать скачанный файл.'
    [ "$download_bytes" -gt 0 ] && [ "$download_bytes" -le "$download_cap" ] || fail 'Размер скачанного файла некорректен.'
}

panel_link() {
    panel_ip=$(nvram get lan_ipaddr 2>/dev/null)
    if ! printf '%s\n' "$panel_ip" | awk -F. 'NF!=4{exit 1} {for(i=1;i<=4;i++)if($i!~/^[0-9]+$/||$i>255)exit 1}'; then
        panel_ip='IP-роутера'
    fi
    say "Панель: http://$panel_ip:90"
}

read_package_status() {
    package_record=$("$OPKG" status nfqws2-asus 2>/dev/null)
    installed=$(printf '%s\n' "$package_record" | awk '$1=="Version:"{print $2}')
    package_status=$(printf '%s\n' "$package_record" | awk '$1=="Status:"{print $2 " " $3 " " $4}')
}

package_healthy() {
    [ -n "$installed" ] || return 1
    case "$package_status" in
        'install ok installed'|'install user installed'|'hold ok installed') return 0 ;;
        *) return 1 ;;
    esac
}

main() {
    WORK='' CHECK_ONLY=0
    case "${1-}" in
        '') ;;
        --check) CHECK_ONLY=1 ;;
        --help|-h) say 'Установка: sh install.sh; только проверка пакета: sh install.sh --check'; return 0 ;;
        *) fail 'Неизвестный параметр. Используйте sh install.sh или sh install.sh --check.' ;;
    esac
    [ "$#" -le 1 ] || fail 'Передано слишком много параметров.'
    uid=''
    while read -r key real effective rest; do
        [ "$key" != 'Uid:' ] || { uid=$effective; break; }
    done < /proc/self/status
    [ "$uid" = 0 ] || fail 'Войдите по SSH как администратор роутера.'
    OPKG=/opt/bin/opkg
    [ -x "$OPKG" ] || fail 'Сначала установите и запустите Entware в /opt.'
    tool nvram >/dev/null || fail 'Установщик предназначен для ASUS с Asuswrt/Merlin.'
    model=$(nvram get productid 2>/dev/null)
    [ -n "$model" ] || model=$(nvram get odmpid 2>/dev/null)
    [ -n "$model" ] || fail 'Не удалось определить модель ASUS.'

    # Resolve the primary Entware ABI, never a supported lower-priority ABI.
    arches=$("$OPKG" print-architecture) || fail 'Не удалось прочитать архитектуру Entware.'
    abi=$(printf '%s\n' "$arches" | awk '
        $1=="arch" && $2!="all" {
            if(NF!=3 || $3!~/^[0-9]+$/ || $3>2147483647){bad=1;next}
            if($2 in seen)next;seen[$2]=1
            if(!have || $3+0>priority){have=1;priority=$3+0;abi=$2;tied=0}
            else if($3+0==priority)tied=1
        }
        END{if(bad||!have||priority<=0||tied)exit 1;print abi}
    ') || fail 'Не удалось однозначно определить основную архитектуру Entware.'
    case "$abi:$(uname -m)" in
        armv7-2.6:armv7*|armv7-3.2:armv7*|armv7-2.6:aarch64|armv7-3.2:aarch64) family=armv7 ;;
        aarch64-3.10:aarch64) family=aarch64-3.10 ;;
        *) fail "Архитектура Entware $abi не поддерживается этим установщиком." ;;
    esac
    CURL=$(tool curl) || CURL=''
    WGET=''
    if [ -z "$CURL" ]; then
        WGET=$(tool wget) || fail 'Для скачивания нужен curl или GNU wget: установите один из них через opkg.'
        "$WGET" --version 2>/dev/null | grep -q 'GNU Wget' || fail 'Для HTTPS нужен curl или GNU wget из Entware.'
    fi
    HASH=$(tool sha256sum) || HASH=''
    HASH_BUSYBOX=0
    if [ -z "$HASH" ]; then
        /bin/busybox sha256sum /dev/null >/dev/null 2>&1 || fail 'Не найден sha256sum. Установите coreutils-sha256sum через opkg.'
        HASH=/bin/busybox HASH_BUSYBOX=1
    fi
    mkdir -p /opt/tmp || fail 'Entware недоступна для записи.'
    WORK=$(mktemp -d /opt/tmp/nfqws2-asus-install.XXXXXX) || fail 'Не удалось создать временный каталог в Entware.'
    trap cleanup 0
    trap 'exit 130' INT
    trap 'exit 143' TERM HUP
    say "ASUS $model · Entware $abi"
    say 'Проверка актуального выпуска…'
    download 'https://github.com/madworldpay/nfqws2-asus-community/releases/latest/download/SHA256SUMS' "$WORK/SHA256SUMS" 65536
    candidate=$(awk -v family="$family" '
        $2 ~ ("_" family "[.]ipk$") {
            if(NF!=2 || length($1)!=64 || $1~/[^0-9a-f]/ || length($2)>160 ||
               $2!~/^nfqws2-asus_[0-9]+[.][0-9]+[.][0-9]+-asus[1-9][0-9]*[+]b[1-9][0-9]*_(armv7|aarch64-3[.]10)[.]ipk$/){bad=1;next}
            count++;hash=$1;name=$2
        }
        END{if(bad||count!=1)exit 1;print hash " " name}
    ' "$WORK/SHA256SUMS") || fail 'В выпуске не найден один подходящий IPK с контрольной суммой.'
    read -r expected_sha asset_name <<EOF
$candidate
EOF
    version=${asset_name#nfqws2-asus_}
    version=${version%_$family.ipk}
    build=${version##*+b}
    read_package_status
    if ! package_healthy; then
        case "$package_status:$installed" in
            ':'|'deinstall ok config-files:'*|'deinstall ok not-installed:'*|'purge ok not-installed:'*|'unknown ok not-installed:'*) installed='' ;;
            *) fail "Предыдущая установка NFQWS2 ASUS не завершена (статус: $package_status). Сохраните вывод opkg status nfqws2-asus для исправления. Настройки и состояние службы не менялись." ;;
        esac
    fi
    if [ "$installed" = "$version" ]; then
        say "Build $build уже установлен."
        panel_link
        return 0
    fi
    if [ -n "$installed" ] && "$OPKG" compare-versions "$installed" '>' "$version"; then
        fail "Уже установлен более новый пакет: $installed. Понижение версии не выполнялось."
    fi
    free_kb=$(df -Pk /opt/ | awk 'NR==2 && $4~/^[0-9]+$/{print $4}')
    [ -n "$free_kb" ] && [ "$free_kb" -ge 131072 ] || fail 'В Entware нужно не менее 128 МБ свободного места для установки и сохранения настроек.'
    memory_kb=$(awk '
        /^MemAvailable:/{available=$2;have=1} /^MemFree:/{free=$2}
        /^Buffers:/{buffers=$2} /^Cached:/{cached=$2}
        END{if(have)print available;else print free+buffers+cached}
    ' /proc/meminfo)
    [ "$memory_kb" -ge 32768 ] || fail 'Недостаточно свободной оперативной памяти: нужно не менее 32 МБ. Освободите память и повторите команду.'
    say "Скачивание Build $build…"
    package=$WORK/$asset_name
    download "https://github.com/madworldpay/nfqws2-asus-community/releases/download/build$build/$asset_name" "$package" 33554432
    if [ "$HASH_BUSYBOX" = 1 ]; then actual_sha=$("$HASH" sha256sum "$package"); else actual_sha=$("$HASH" "$package"); fi
    [ "$?" = 0 ] || fail 'Не удалось проверить контрольную сумму IPK.'
    actual_sha=${actual_sha%% *}
    [ "$actual_sha" = "$expected_sha" ] || fail 'Контрольная сумма IPK не совпала. Установка не выполнялась; повторите команду.'
    if [ "$CHECK_ONLY" = 1 ]; then
        say "Пакет Build $build для $abi скачан и проверен. Установка не выполнялась."
        return 0
    fi
    # prerm/postinst handle migration and service changes. Read intent right before opkg.
    no_start=1
    if [ -n "$installed" ]; then
        if [ -f /tmp/nfqws2-asus/enabled ] || { [ -x /opt/etc/init.d/S51nfqws2 ] && /opt/etc/init.d/S51nfqws2 status >/dev/null 2>&1; }; then
            no_start=0
        fi
    fi
    mkdir "$WORK/opkg" || fail 'Не удалось подготовить временный каталог opkg.'
    say 'Обновление списка пакетов Entware…'
    "$OPKG" --tmp-dir "$WORK/opkg" update || fail 'Не удалось обновить список пакетов Entware. Установка не выполнялась.'
    say 'Установка NFQWS2 ASUS с сохранением настроек…'
    NFQWS_ASUS_NO_START=$no_start "$OPKG" --tmp-dir "$WORK/opkg" install "$package" || fail 'opkg сообщил об ошибке установки. Сохраните вывод выше; принудительная установка не выполнялась.'
    was_installed=$installed
    read_package_status
    [ "$installed" = "$version" ] && package_healthy || fail 'opkg завершился, но установка нужной версии не завершена. Сохраните вывод установки и opkg status nfqws2-asus.'
    say "Готово: Build $build установлен."
    panel_link
    [ -n "$was_installed" ] || say 'Выберите WAN, устройства и профиль в панели, затем запустите NFQWS2.'
    return 0
}

# BEGIN GENERATED NATIVE OPENWRT INSTALLER
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

nfqws_native_emit_bundle() {
cat <<'NFQWS_NATIVE_BUNDLE'
<?php
// Generated from shared native installer verification code.
interface AsusUpdateSource { public function manifest():array; public function download(array $package,string $destination):void; }
// webui/web/public/platform.php sha256=53877309af1524ed44aa076b1cdc00744d0cc8ca2e66b605dcae8e5c08c12d6c
/** Trusted package profile. HTTP fields and process environment cannot select it. */
final class NfqwsPlatform
{
    private const PROFILES=[
        'asus-entware'=>['root'=>'/opt','config'=>'/opt/etc/nfqws2','web_config'=>'/opt/etc/nfqws-asus-web',
            'library'=>'/opt/lib/nfqws2-asus','share'=>'/opt/share/nfqws2-asus','service'=>'/opt/etc/init.d/S51nfqws2'],
        'openwrt'=>['root'=>'','config'=>'/etc/nfqws2','web_config'=>'/etc/nfqws2-web',
            'library'=>'/usr/lib/nfqws2','share'=>'/usr/share/nfqws2','service'=>'/etc/init.d/nfqws2-native'],
    ];
    public static function settings(?string $profile=null):array
    {
        $profile??=self::current();
        if(!isset(self::PROFILES[$profile]))throw new RuntimeException('invalid_platform_profile');
        return self::PROFILES[$profile];
    }
    public static function current():string
    {
        static $profile=null;
        if($profile===null){
            $file=__DIR__.'/platform-profile.json';clearstatcache(true,$file);
            $profile=@lstat($file)===false?'asus-entware':self::readProfile($file);
        }
        return $profile;
    }
    public static function native():bool{return self::current()==='openwrt';}
    public static function readProfile(string $file,int $owner=0):string
    {
        clearstatcache(true,$file);$s=@lstat($file);
        if(!$s||is_link($file)||!is_file($file)||$s['uid']!==$owner||($s['mode']&0022)!==0||$s['size']>4096||$s['nlink']!==1)
            throw new RuntimeException('unsafe_platform_profile');
        for($p=dirname($file);$p!=='/';$p=dirname($p)){
            $d=@lstat($p);
            if(!$d||is_link($p)||!is_dir($p)||!in_array($d['uid'],[0,$owner],true))throw new RuntimeException('unsafe_platform_profile');
            // Root-owned sticky /tmp is a valid ancestor of a private fixture.
            if(($d['mode']&0022)!==0&&!(($d['mode']&01000)!==0&&$d['uid']===0))throw new RuntimeException('unsafe_platform_profile');
        }
        $v=json_decode((string)file_get_contents($file),true);
        if(!is_array($v)||array_keys($v)!==['schema_version','platform']||$v['schema_version']!==1||
            !is_string($v['platform'])||!isset(self::PROFILES[$v['platform']]))throw new RuntimeException('invalid_platform_profile');
        return $v['platform'];
    }
    public static function translate(string $path,?string $profile=null):string
    {
        if(str_contains($path,"\0")||preg_match('~(?:^|/)\.\.?(?:/|$)~',$path))throw new RuntimeException('invalid_platform_path');
        $settings=self::settings($profile);
        if($settings['root']==='/opt')return $path;
        $map=[
            '/opt/etc/nfqws2'=>'/etc/nfqws2','/opt/etc/nfqws-asus-web'=>'/etc/nfqws2-web',
            '/opt/share/nfqws2-asus'=>'/usr/share/nfqws2','/opt/lib/nfqws2-asus'=>'/usr/lib/nfqws2',
            '/opt/share/nfqws-asus-web'=>'/usr/share/nfqws2-web','/opt/lib/nfqws-asus-web'=>'/usr/lib/nfqws2-web',
            '/opt/var/lib/nfqws2-asus'=>'/tmp/nfqws2-native-state','/opt/var/log'=>'/var/log',
            '/opt/etc/ssl/certs/ca-certificates.crt'=>'/etc/ssl/certs/ca-certificates.crt',
            '/opt/bin/php-cgi'=>'/usr/bin/php-cgi','/opt/usr/bin/nfqws2'=>'/usr/bin/nfqws2',
        ];
        foreach($map as $from=>$to)if($path===$from||str_starts_with($path,$from.'/'))return $to.substr($path,strlen($from));
        if($path==='/opt'||str_starts_with($path,'/opt/'))throw new RuntimeException('unmapped_platform_path');
        return $path;
    }
    /** /proc/net IPv4 fields use kernel word byte order, including MIPS BE. */
    public static function procNetIPv4(string $address,?bool $littleEndian=null):string
    {
        $bytes=@inet_pton($address);if($bytes===false||strlen($bytes)!==4)throw new RuntimeException('invalid_ipv4_address');
        $littleEndian??=pack('L',1)==="\x01\x00\x00\x00";
        return strtoupper(bin2hex($littleEndian?strrev($bytes):$bytes));
    }
    public static function serviceCommand(string $action,?string $profile=null):array
    {
        if(!in_array($action,['start','stop','restart','status','check','diagnostics'],true))throw new RuntimeException('invalid_service_action');
        $settings=self::settings($profile);
        if($settings['root']===''&&in_array($action,['status','check','diagnostics'],true))return ['/usr/lib/nfqws2/control.sh',$action];
        return [$settings['service'],$action];
    }
    public static function reader(int $owner=0,bool $mutable=false):AsusShareRead
    {
        return self::native()?new AsusShareRead($owner,null,null,$mutable):new AsusShareRead($owner,realpath('/opt'),'/opt',$mutable);
    }
    public static function sharedFile(string $name,string $sourceFallback):string
    {
        if(!preg_match('/^[A-Za-z0-9_.-]{1,128}$/D',$name)||in_array($name,['.','..'],true))throw new RuntimeException('invalid_platform_path');
        $path=self::settings()['share'].'/'.$name;clearstatcache(true,$path);$s=@lstat($path);
        if($s===false)return $sourceFallback;
        if(self::native()&&(is_link($path)||!is_file($path)||$s['uid']!==0||($s['mode']&0022)!==0||$s['nlink']!==1))throw new RuntimeException('invalid_state');
        return $path;
    }
    /** Fixed argv selected by trusted callers, bounded output and deadline. */
    public static function run(array $argv,float $timeout=15,array $inherited=[],int $outputLimit=65536):array
    {
        if($outputLimit<1||$outputLimit>1048576)throw new RuntimeException('invalid_output_limit');
        $descriptors=[0=>['file','/dev/null','r'],1=>['pipe','w'],2=>['pipe','w']];
        foreach($inherited as $fd=>$stream){if(!is_int($fd)||$fd<3||$fd>9||!is_resource($stream))throw new RuntimeException('invalid_inherited_descriptor');$descriptors[$fd]=$stream;}
        $pipes=[];$p=@proc_open($argv,$descriptors,$pipes,null,['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin']);
        if(!is_resource($p))return ['status'=>1,'output'=>[]];
        foreach($pipes as $f)stream_set_blocking($f,false);
        $raw='';$until=microtime(true)+$timeout;$status=1;
        try{do{foreach($pipes as $f)$raw.=stream_get_contents($f);$s=proc_get_status($p);
            if(strlen($raw)>$outputLimit||microtime(true)>$until){proc_terminate($p,9);break;}
            if(!$s['running']){$status=$s['exitcode'];foreach($pipes as $f)$raw.=stream_get_contents($f);break;}usleep(20000);
        }while(true);}finally{foreach($pipes as $f)fclose($f);proc_close($p);}
        if(strlen($raw)>$outputLimit)$status=1;
        return ['status'=>$status,'output'=>explode("\n",rtrim(substr($raw,0,$outputLimit)))];
    }
    public static function guardFile(string $directory,string $name,int $owner=0):string
    {
        if(!preg_match('/^[A-Za-z0-9_.-]{1,128}$/D',$name)||in_array($name,['.','..'],true))throw new RuntimeException('unsafe_panel_file');
        for($p=$directory;$p!=='/'&&$p!=='.';$p=dirname($p)){
            $a=@lstat($p);
            if(!$a||!in_array($a['uid'],[0,$owner],true))throw new RuntimeException('unsafe_panel_file');
            if(is_link($p)&&!($p==='/var'&&$a['uid']===0&&realpath($p)==='/tmp'))throw new RuntimeException('unsafe_panel_file');
            if(!is_link($p)&&($a['mode']&0022)!==0&&!($a['uid']===0&&($a['mode']&01000)!==0))throw new RuntimeException('unsafe_panel_file');
        }
        $base=realpath($directory);$d=$base!==false?@lstat($base):false;
        if(!$d||!is_dir($base)||$d['uid']!==$owner||($d['mode']&0022)!==0)throw new RuntimeException('unsafe_panel_file');
        $path=$base.'/'.$name;clearstatcache(true,$path);$s=@lstat($path);
        if($s!==false&&(is_link($path)||!is_file($path)||$s['nlink']!==1||!in_array($s['uid'],[$owner,65534],true)||($s['mode']&0002)!==0))
            throw new RuntimeException('unsafe_panel_file');
        return $path;
    }
}

// webui/web/public/support-json-schema.php sha256=d4d5559f90d2bc9ebfd94e19500c22e87b2b3be8949558d2be5c86d4619f55d3
/** Bounded JSON reader and validator for our bundled, closed schemas only. */
final class AsusSupportSchema
{
    private static int $budget;
    public static function decode(string $raw,int $max,string $code): mixed
    {
        try {
            if($raw===''||strlen($raw)>$max)throw new RuntimeException();
            $i=0;self::scan($raw,$i,0);self::space($raw,$i);
            if($i!==strlen($raw))throw new RuntimeException();
            $value=json_decode($raw,false,32,JSON_THROW_ON_ERROR);
            self::finite($value);
            return $value;
        } catch(Throwable $e) {throw new RuntimeException($code);}
    }
    private static function space(string $s,int &$i): void
    {while(isset($s[$i])&&str_contains(" \n\r\t",$s[$i]))$i++;}
    private static function quoted(string $s,int &$i): string
    {
        $begin=$i++;
        while(isset($s[$i])) {
            if($s[$i]==='\\'){$i+=2;continue;}
            if($s[$i++]==='"')return json_decode(substr($s,$begin,$i-$begin),true,2,JSON_THROW_ON_ERROR);
        }
        throw new RuntimeException();
    }
    private static function scan(string $s,int &$i,int $depth): void
    {
        self::space($s,$i);$c=$s[$i]??'';
        if($c==='"'){self::quoted($s,$i);return;}
        if($c==='{'||$c==='[') {
            if(++$depth>32)throw new RuntimeException();
            $i++;$end=$c==='{'?'}':']';$seen=[];self::space($s,$i);
            if(($s[$i]??'')===$end){$i++;return;}
            do {
                self::space($s,$i);
                if($c==='{') {
                    if(($s[$i]??'')!=='"')throw new RuntimeException();
                    $key=self::quoted($s,$i);
                    if(array_key_exists($key,$seen))throw new RuntimeException();
                    $seen[$key]=true;self::space($s,$i);
                    if(($s[$i++]??'')!==':')throw new RuntimeException();
                }
                self::scan($s,$i,$depth);self::space($s,$i);$next=$s[$i++]??'';
                if($next===$end)return;
                if($next!==',')throw new RuntimeException();
            } while(isset($s[$i]));
            throw new RuntimeException();
        }
        $start=$i;
        while(isset($s[$i])&&!str_contains(" \n\r\t,]}",$s[$i]))$i++;
        if($start===$i)throw new RuntimeException();
    }
    private static function finite(mixed $v): void
    {
        if(is_float($v)&&!is_finite($v))throw new RuntimeException();
        if(is_array($v)||is_object($v))foreach($v as $x)self::finite($x);
    }
    public static function validate(string $raw,string $kind): array
    {
        $files=['report'=>['report.schema.json',1048576,'invalid_report'],'dpi'=>['dpi-report.schema.json',262144,'invalid_dpi'],
            'envelope'=>['dpi-envelope.schema.json',2097152,'invalid_bundle'],
            'dpi_saved'=>['dpi-saved.schema.json',262144,'invalid_dpi'],
            'strategy'=>['strategy.schema.json',65536,'invalid_strategy'],
            'strategy2'=>['strategy-v2.schema.json',65536,'invalid_strategy'],
            'resources'=>['resources.schema.json',786432,'invalid_resource'],
            'dns_share'=>['dns-share.schema.json',131072,'invalid_dns_resource'],
            'share4'=>['share-v4.schema.json',4194304,'invalid_share'],
            'share'=>['share-envelope.schema.json',2097152,'invalid_share']];
        if(!isset($files[$kind]))throw new RuntimeException('invalid_request');
        [$name,$max,$code]=$files[$kind];$v=self::decode($raw,$max,$code);
        if($kind==='dpi'&&is_object($v)&&($v->schema_version??null)===2)$name='dpi-analysis-v2.schema.json';
        $root=dirname(__DIR__,3).'/support';
        $file=NfqwsPlatform::sharedFile($name,$root.'/'.$name);
        $schema=json_decode(file_get_contents($file),true,128,JSON_THROW_ON_ERROR);
        self::$budget=200000;
        if(!self::match($v,$schema,$schema))throw new RuntimeException($code);
        return self::toArray($v);
    }
    /** Reuse validated strings instead of decoding a second full copy. */
    public static function toArray(mixed $value): mixed
    {
        if(is_object($value))$value=(array)$value;
        if(is_array($value))foreach($value as &$item)$item=self::toArray($item);
        return $value;
    }
    public static function projection(mixed $value,array $schema,array $root): void
    {self::$budget=200000;if(!self::match($value,$schema,$root))throw new RuntimeException('invalid_dpi');}
    private static function match(mixed $v,mixed $s,array $root): bool
    {
        if(--self::$budget<0)throw new RuntimeException('invalid_schema');
        if(is_bool($s))return $s;
        foreach($s as $key=>$_)if(!in_array($key,['$schema','$id','$defs','$ref','title','description','$comment','type','properties','required','additionalProperties','enum','const','pattern','maxLength','minLength','minimum','maximum','maxItems','minItems','items','prefixItems','uniqueItems','anyOf','allOf','if','then'],true))throw new RuntimeException('invalid_schema');
        if(isset($s['$ref'])) {
            if(!preg_match('~^#/\$defs/([A-Za-z0-9_-]+)$~D',$s['$ref'],$m)||!isset($root['$defs'][$m[1]]))throw new RuntimeException('invalid_schema');
            if(!self::match($v,$root['$defs'][$m[1]],$root))return false;
        }
        if(isset($s['type'])) {
            if(is_array($s['type'])) {
                foreach($s['type'] as $type) {$one=$s;$one['type']=$type;if(self::match($v,$one,$root))return true;}
                return false;
            }
            $valid=match($s['type']) {'object'=>is_object($v),'array'=>is_array($v),'string'=>is_string($v),'boolean'=>is_bool($v),'null'=>$v===null,
                'integer'=>(is_int($v)||is_float($v))&&is_finite((float)$v)&&floor($v)==$v,'number'=>(is_int($v)||is_float($v))&&is_finite((float)$v),default=>false};
            if(!$valid)return false;
        }
        if(array_key_exists('const',$s)&&$v!==$s['const']&&!((is_int($v)||is_float($v))&&(is_int($s['const'])||is_float($s['const']))&&$v==$s['const']))return false;
        if(isset($s['enum'])&&!in_array($v,$s['enum'],true))return false;
        if(isset($s['anyOf'])) { $ok=false;foreach($s['anyOf'] as $sub)if(self::match($v,$sub,$root)){$ok=true;break;}if(!$ok)return false; }
        foreach($s['allOf']??[] as $sub)if(!self::match($v,$sub,$root))return false;
        if(isset($s['if'])&&self::match($v,$s['if'],$root)&&isset($s['then'])&&!self::match($v,$s['then'],$root))return false;
        if(is_object($v)) {
            foreach($s['required']??[] as $key)if(!property_exists($v,$key))return false;
            foreach($v as $key=>$item) {
                if(isset($s['properties'][$key])){if(!self::match($item,$s['properties'][$key],$root))return false;}
                elseif(($s['additionalProperties']??true)===false)return false;
                elseif(is_array($s['additionalProperties']??null)&&!self::match($item,$s['additionalProperties'],$root))return false;
            }
        }
        if(is_array($v)) {
            $n=count($v);if($n<($s['minItems']??0)||$n>($s['maxItems']??PHP_INT_MAX))return false;
            if(($s['uniqueItems']??false)&&count(array_unique(array_map('serialize',$v)))!==$n)return false;
            foreach($v as $i=>$item)if(!self::match($item,$s['prefixItems'][$i]??($s['items']??true),$root))return false;
        }
        if(is_string($v)) {
            $len=preg_match_all('/./us',$v);
            if($len===false||$len<($s['minLength']??0)||$len>($s['maxLength']??PHP_INT_MAX))return false;
            if(isset($s['pattern'])) {
                $pattern=$s['pattern'];
                // Fixed-width, disjoint base64 quads never need backtracking. Avoid PCRE JIT's stack cap on a 1 MiB file.
                if($pattern==='^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$')$pattern='^(?:[A-Za-z0-9+/]{4})*+(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$';
                if(preg_match('~'.str_replace('~','\\~',$pattern).'~uD',$v)!==1)return false;
            }
        }
        if((is_int($v)||is_float($v))&&($v<($s['minimum']??-INF)||$v>($s['maximum']??INF)))return false;
        return true;
    }
}

// webui/web/public/update-manifest.php sha256=a137c8370a86e25f4cb3cddb4067521335e958b5fcced1e90c7277688d655be4

/** Release metadata is trusted only after closed-schema and pinned-key verification. */
final class AsusPackageManifest
{
    private const CORE='(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-asus[1-9][0-9]{0,5}';

    private static function version(string $version,string $code): array
    {
        if(!preg_match('/^('.self::CORE.')\+b([1-9][0-9]{0,9})$/D',$version,$m)||(float)$m[2]>2147483647)throw new RuntimeException($code);
        preg_match('/^([0-9]+)\.([0-9]+)\.([0-9]+)-asus([0-9]+)$/D',$m[1],$c);
        return ['core'=>$m[1],'parts'=>array_map('intval',array_slice($c,1)),'build'=>(int)$m[2]];
    }

    public static function verify(string $json,string $signature,string $publicKey): array
    {
        $value=AsusSupportSchema::decode($json,32768,'invalid_manifest');
        $path=dirname(__DIR__).'/resources/package-manifest.schema.json';
        if(!is_file($path))$path='/opt/share/nfqws2-asus/package-manifest.schema.json';
        if(!is_file($path))$path=dirname(__DIR__,3).'/updates/package-manifest.schema.json';
        try {
            $raw=@file_get_contents($path);if(!is_string($raw))throw new RuntimeException();
            $schema=json_decode($raw,true,32,JSON_THROW_ON_ERROR);
            AsusSupportSchema::projection($value,$schema,$schema);
        }catch(Throwable $e){throw new RuntimeException('invalid_manifest');}
        $manifest=json_decode($json,true,32,JSON_THROW_ON_ERROR);
        $version=self::version($manifest['package_version'],'invalid_manifest');
        if(!is_int($manifest['build'])||$version['build']!==$manifest['build']||$version['core']!==$manifest['core_version'])throw new RuntimeException('invalid_manifest');
        $seen=[];
        foreach($manifest['packages'] as $package){
            if(isset($seen[$package['family']])||!is_int($package['size'])||$package['filename']!=='nfqws2-asus_'.$manifest['package_version'].'_'.$package['family'].'.ipk')throw new RuntimeException('invalid_manifest');
            $seen[$package['family']]=true;
        }
        self::verifySignature($json,$signature,$publicKey);
        $manifest['revision']=hash('sha256',$json);
        return $manifest;
    }

    /** Shared signature primitive; each platform keeps its own closed identity schema. */
    public static function verifySignature(string $json,string $signature,string $publicKey):void
    {
        if(!extension_loaded('openssl'))throw new RuntimeException('signature_unavailable');
        if(strlen($signature)>1024)throw new RuntimeException('invalid_signature');
        $signature=trim($signature);$bytes=base64_decode($signature,true);
        if($bytes===false||strlen($bytes)!==384||base64_encode($bytes)!==$signature)throw new RuntimeException('invalid_signature');
        $key=@openssl_pkey_get_public($publicKey);$details=$key===false?false:openssl_pkey_get_details($key);
        if(!$details||$details['type']!==OPENSSL_KEYTYPE_RSA||$details['bits']!==3072||@openssl_verify($json,$bytes,$key,OPENSSL_ALGO_SHA256)!==1)throw new RuntimeException('invalid_signature');
    }

    public static function candidate(array $manifest,string $family,string $installedVersion): ?array
    {
        if(!in_array($family,['aarch64-3.10','armv7'],true))throw new RuntimeException('unsupported_abi');
        $installed=self::version($installedVersion,'unsupported_version');
        $target=self::version($manifest['package_version'],'invalid_manifest');
        // The global Build increases across core versions; a signed old core is never an upgrade.
        if($target['build']<=$installed['build']||$target['parts']<$installed['parts'])return null;
        foreach($manifest['packages'] as $package)if($package['family']===$family)return [
            'revision'=>$manifest['revision'],'package_version'=>$manifest['package_version'],
            'core_version'=>$manifest['core_version'],'web_version'=>$manifest['web_version'],
            'build'=>$manifest['build'],'notes'=>$manifest['notes'],'package'=>$package,
        ];
        throw new RuntimeException('unsupported_package');
    }
}

// webui/web/public/openwrt-update-manifest.php sha256=1f69c07e0c262a1a53b3c98d2aabfcac5b5a98f9ceae55a158a4b0f77bb15c83

/** Native and Entware releases use the same trust key, separate closed identities. */
final class NfqwsOpenWrtPackageManifest
{
    public static function verify(string $json,string $signature,string $key,?string $schemaPath=null):array
    {
        $value=AsusSupportSchema::decode($json,32768,'invalid_manifest');
        $path=$schemaPath??NfqwsPlatform::sharedFile('openwrt-package-manifest.schema.json',dirname(__DIR__,3).'/updates/openwrt-package-manifest.schema.json');
        try{$schema=json_decode((string)file_get_contents($path),true,32,JSON_THROW_ON_ERROR);AsusSupportSchema::projection($value,$schema,$schema);}
        catch(Throwable $e){throw new RuntimeException('invalid_manifest');}
        $v=AsusSupportSchema::toArray($value);$seen=[];
        foreach($v['packages']as $p){
            $format=$p['series']==='24.10'?'ipk':'apk';
            $version=$v['core_version'].'-'.($format==='apk'?'r':'').$v['build'];
            $name='nfqws2-native_'.$version.'_'.$p['arch'].'.'.$format;
            $id=$p['series'].':'.$p['arch'];
            if(isset($seen[$id])||$p['format']!==$format||$p['version']!==$version||$p['filename']!==$name)throw new RuntimeException('invalid_manifest');
            $seen[$id]=true;
        }
        AsusPackageManifest::verifySignature($json,$signature,$key);
        $v['revision']=hash('sha256',$json);return $v;
    }

    private static function identity(array $identity):array
    {
        $series=$identity['series']??null;$format=$series==='24.10'?'ipk':($series==='25.12'?'apk':null);$arch=$identity['arch']??null;
        if(($identity['platform']??null)!=='openwrt'||$format===null||($identity['format']??null)!==$format||!is_string($arch)||!preg_match('/^[a-z0-9][a-z0-9_+-]{0,99}$/D',$arch))throw new RuntimeException('unsupported_abi');
        return [$series,$format,$arch];
    }
    /** First install and updates share the same signed exact firmware target. */
    public static function select(array $manifest,array $identity):array
    {
        [$series,$format,$arch]=self::identity($identity);
        foreach($manifest['packages']as $p)if($p['series']===$series&&$p['arch']===$arch&&$p['format']===$format)return [
            'revision'=>$manifest['revision'],'package_version'=>$p['version'],'core_version'=>$manifest['core_version'],
            'web_version'=>$manifest['web_version'],'build'=>$manifest['build'],'notes'=>$manifest['notes'],
            'package'=>$p+['family'=>$arch],
        ];
        throw new RuntimeException('unsupported_package');
    }
    public static function candidate(array $manifest,array $identity,string $installed,int $build):?array
    {
        [, $format]=self::identity($identity);$suffix=$format==='apk'?'r':'';
        if(!preg_match('/^((?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5}))-'.$suffix.'([1-9][0-9]{0,9})$/D',$installed,$m)||(float)$m[2]>2147483647||$build<1)throw new RuntimeException('unsupported_version');
        if($manifest['build']<=$build||$manifest['build']<=(int)$m[2]||version_compare($manifest['core_version'],$m[1],'<'))return null;
        return self::select($manifest,$identity);
    }
}

// webui/web/public/update-store.php sha256=a31ffc910b5e75f02ea77e7e77986b9f87f502fd46abb7dc3f42269d792e14ff

/** Private transaction journal. Paths come from trusted code, never HTTP fields. */
final class AsusUpdateStore
{
    public const TERMINAL=['succeeded','failed','interrupted'];
    private string $root;
    private bool $locked=false;
    public function __construct(?string $root=null,private int $owner=0)
    {
        $this->root=$root??AsusDpiStore::optPath('/var/lib/nfqws2-asus/updates');
        self::noLinks($this->root);
        $missing=[];for($p=dirname($this->root);!is_dir($p);$p=dirname($p))$missing[]=$p;
        foreach(array_reverse($missing) as $p)if(!@mkdir($p,0755)&&!is_dir($p))throw new RuntimeException('invalid_state');
        $this->directory('');$this->directory('operations');
    }
    /** Canonicalize only the supported Entware /opt alias, not child symlinks. */
    public static function installed(string $relative): string
    {
        if(!preg_match('~^[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*$~D',$relative)||in_array('..',explode('/',$relative),true)||in_array('.',explode('/',$relative),true))throw new RuntimeException('invalid_state');
        return dirname(AsusDpiStore::optPath('/var')).'/'.$relative;
    }
    public static function noLinks(string $path): void
    {for($p=$path;$p!=='/'&&$p!=='.';$p=dirname($p))if(is_link($p))throw new RuntimeException('invalid_state');}
    public function path(string $name=''): string
    {
        if($name!==''&&(!preg_match('~^[a-zA-Z0-9_.-]+(?:/[a-zA-Z0-9_.-]+)*$~D',$name)||in_array('..',explode('/',$name),true)||in_array('.',explode('/',$name),true)))throw new RuntimeException('invalid_request');
        $p=$this->root.($name===''?'':'/'.$name);self::noLinks($p);return $p;
    }
    public function directory(string $name): string
    {
        $p=$this->path($name);$mask=umask(0077);try{if(!is_dir($p)&&!@mkdir($p,0700)&&!is_dir($p))throw new RuntimeException('invalid_state');}finally{umask($mask);}
        clearstatcache(true,$p);$s=@lstat($p);
        if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');return $p;
    }
    private function regular(string $path,int $max): ?array
    {
        clearstatcache(true,$path);$s=@lstat($path);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$this->owner||($s['mode']&0777)!==0600||$s['nlink']!==1||$s['size']>$max)throw new RuntimeException('invalid_state');return $s;
    }
    public function readFile(string $name,int $max=131072): ?string
    {
        $p=$this->path($name);$s=$this->regular($p,$max);if(!$s)return null;$f=@fopen($p,'rb');if(!$f)throw new RuntimeException('invalid_state');
        try{$a=fstat($f);if($s['ino']!==$a['ino']||$s['dev']!==$a['dev'])throw new RuntimeException('invalid_state');$v=stream_get_contents($f,$max+1);if(!is_string($v)||strlen($v)>$max)throw new RuntimeException('invalid_state');return $v;}finally{fclose($f);}
    }
    public function writeFile(string $name,string $raw): void
    {
        if(strlen($raw)>131072)throw new RuntimeException('output_limit');$p=$this->path($name);$this->regular($p,131072);
        $dir=dirname($p);$s=@lstat($dir);if(!$s||($s['mode']&0170000)!==0040000||$s['uid']!==$this->owner||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
        $tmp=$dir.'/.write-'.bin2hex(random_bytes(12));$mask=umask(0077);try{$f=@fopen($tmp,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('invalid_state');
        try{if(!chmod($tmp,0600)||fwrite($f,$raw)!==strlen($raw)||!fflush($f))throw new RuntimeException('invalid_state');fclose($f);$f=null;if(!rename($tmp,$p))throw new RuntimeException('invalid_state');}finally{if(is_resource($f))fclose($f);@unlink($tmp);}
    }
    public function withLock(callable $fn): mixed
    {
        if($this->locked)return $fn();$p=$this->path('control.lock');$s=$this->regular($p,0);$mask=umask(0077);
        try{$f=@fopen($p,$s?'r+be':'x+be');}finally{umask($mask);}if(!$f){$this->regular($p,0);$f=@fopen($p,'r+be');}if(!$f)throw new RuntimeException('invalid_state');
        try{$a=fstat($f);$s=$this->regular($p,0);if(!$s||$a['ino']!==$s['ino']||$a['dev']!==$s['dev'])throw new RuntimeException('invalid_state');if(!flock($f,LOCK_EX|LOCK_NB))throw new RuntimeException('busy');$this->locked=true;return $fn();}finally{$this->locked=false;flock($f,LOCK_UN);fclose($f);}
    }
    /** Trusted workers tolerate brief HTTP polling without replaying callbacks. */
    public function withRetryLock(callable $fn): mixed
    {
        $deadline=self::uptime()+1;
        do{$entered=false;try{return $this->withLock(function()use($fn,&$entered){$entered=true;return $fn();});}
            catch(RuntimeException $e){if($entered||$e->getMessage()!=='busy'||self::uptime()>=$deadline)throw $e;usleep(10000);}
        }while(true);
    }
    /** Independent leases keep long work out of the short journal lock. */
    public function lease(string $name,bool $shared=false)
    {
        if(!in_array($name,['apply.lock','check.lock'],true)&&!preg_match('~^operations/[a-f0-9]{32}/(?:work|critical)\.lock$~D',$name))throw new RuntimeException('invalid_request');
        $p=$this->path($name);$s=$this->regular($p,0);$mask=umask(0077);try{$f=@fopen($p,$s?'r+be':'x+be');}finally{umask($mask);}if(!$f){$this->regular($p,0);$f=@fopen($p,'r+be');}if(!$f)throw new RuntimeException('invalid_state');
        $a=fstat($f);$s=$this->regular($p,0);if(!$s||$s['ino']!==$a['ino']||$s['dev']!==$a['dev']){fclose($f);throw new RuntimeException('invalid_state');}
        if(!flock($f,($shared?LOCK_SH:LOCK_EX)|LOCK_NB)){fclose($f);throw new RuntimeException('busy');}return $f;
    }
    public function withOperationLock(string $id,callable $fn): mixed
    {self::id($id);$f=$this->lease('operations/'.$id.'/work.lock');try{return $fn();}finally{flock($f,LOCK_UN);fclose($f);}}
    public static function boot(): string {return trim(file_get_contents('/proc/sys/kernel/random/boot_id'));}
    public static function uptime(): float {return (float)explode(' ',file_get_contents('/proc/uptime'))[0];}
    private static function id(string $id): void {if(!preg_match('/^[a-f0-9]{32}$/D',$id))throw new RuntimeException('invalid_request');}
    private function db(): array
    {
        $raw=$this->readFile('operations.json');if($raw===null)return ['operations'=>[]];
        try{$db=json_decode($raw,true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($db)||array_keys($db)!==['operations']||!is_array($db['operations'])||count($db['operations'])>3)throw new RuntimeException('invalid_state');
        foreach($db['operations'] as $id=>$job)if(!preg_match('/^[a-f0-9]{32}$/D',(string)$id)||!is_array($job)||($job['id']??null)!==$id||!in_array($job['state']??null,array_merge(['preparing','prepared','applying'],self::TERMINAL),true))throw new RuntimeException('invalid_state');return $db;
    }
    private function save(array $db): void {$this->writeFile('operations.json',json_encode($db,JSON_THROW_ON_ERROR));}
    private function rotate(array &$db): void
    {
        $terminal=array_filter($db['operations'],fn($j)=>in_array($j['state'],self::TERMINAL,true));
        while(count($terminal)>2){$id=array_key_first($terminal);$this->clean($id);unset($terminal[$id],$db['operations'][$id]);}
    }
    private function clean(string $id): void
    {
        $dir=$this->path('operations/'.$id);if(!is_dir($dir))return;$this->directory('operations/'.$id);
        // A native APK gate lives outside this directory. Its exact private
        // token must not disappear while leaving an owned inactive hook behind.
        if($this->owner===0&&NfqwsPlatform::native()&&$this->readFile('operations/'.$id.'/apk-commit.json',2048)!==null){
            require_once __DIR__.'/openwrt-apk-commit.php';
            if(!NfqwsOpenWrtApkCommit::prune($this,$id))return;
        }
        // Unknown operator files and links are deliberately left alone.
        $this->pruneTree('operations/'.$id.'/backup','snapshot.json');
        $partial=$this->readFile('operations/'.$id.'/runtime/staging.json')!==null;
        $this->pruneTree('operations/'.$id.'/runtime',$partial?'staging.json':'closure.json',$partial,true);
        foreach(['apk-keys-prepare','apk-keys-apply']as $ring){$partial=$this->readFile('operations/'.$id.'/'.$ring.'/staging.json')!==null;$this->pruneTree('operations/'.$id.'/'.$ring,$partial?'staging.json':'keys-index.json',$partial);}
        foreach(['package.ipk','package.apk','native-preflight.json','quiesced.json','apk-commit.json','original-payload.json','manager.log','snapshot.json','candidate.json','manifest.json','manifest.sig','apply.json','work.lock','critical.lock','guard.json','cancel.json','boundary.json','preflight-error.json','network.json'] as $name){$p=$dir.'/'.$name;$s=@lstat($p);if($s&&($s['mode']&0170000)===0100000&&$s['uid']===$this->owner&&$s['nlink']===1)@unlink($p);}
        @rmdir($dir);
    }
    private function pruneTree(string $name,string $index,bool $incomplete=false,bool $runtime=false): void
    {
        $dir=$this->path($name);if(!is_dir($dir))return;$this->directory($name);$raw=$this->readFile($name.'/'.$index);if($raw===null)return;
        try{$v=json_decode($raw,true,32,JSON_THROW_ON_ERROR);}catch(Throwable $e){throw new RuntimeException('invalid_state');}
        if(!is_array($v['files']??null)||count($v['files'])>512)throw new RuntimeException('invalid_state');$dirs=[$dir];
        foreach($v['files'] as $file=>$meta){if(!is_string($file)||!preg_match('~^[a-zA-Z0-9_@+.-]+(?:/[a-zA-Z0-9_@+.-]+)*$~D',$file)||in_array('..',explode('/',$file),true)||in_array('.',explode('/',$file),true)||!is_array($meta)||!is_int($meta['mode']??null)||!is_int($meta['size']??null)||$meta['size']<0||!preg_match('/^[a-f0-9]{64}$/D',$meta['sha256']??''))throw new RuntimeException('invalid_state');
            $p=$dir.'/'.$file;$safe=true;for($parent=$p;$parent!==$dir;$parent=dirname($parent))if(is_link($parent)){$safe=false;break;}if(!$safe)continue;
            $s=@lstat($p);if($s&&($s['mode']&0170000)===0100000&&$s['uid']===$this->owner&&$s['nlink']===1){
                $complete=($s['mode']&0777)===$meta['mode']&&$s['size']===$meta['size']&&hash_file('sha256',$p)===$meta['sha256'];
                $partial=$incomplete&&in_array($s['mode']&0777,[0600,$meta['mode']],true)&&$s['size']<=$meta['size'];
                if($complete||$partial)@unlink($p);
            }
            for($parent=dirname($p);$parent!==$dir;$parent=dirname($parent))$dirs[]=$parent;
        }
        @unlink($dir.'/'.$index);if($incomplete&&$runtime){$s=@lstat($dir.'/closure.json');if($s&&($s['mode']&0170000)===0100000&&$s['uid']===$this->owner&&$s['nlink']===1&&($s['mode']&0777)===0600&&$s['size']<=131072)@unlink($dir.'/closure.json');}
        $dirs=array_values(array_unique($dirs));usort($dirs,fn($a,$b)=>strlen($b)<=>strlen($a));foreach($dirs as $p){$s=@lstat($p);if($s&&($s['mode']&0170000)===0040000&&$s['uid']===$this->owner)@rmdir($p);}
    }
    public function reserve(string $revision,string $requestId,array $candidate): array
    {
        self::id($requestId);if(!preg_match('/^[a-f0-9]{64}$/D',$revision)||($candidate['revision']??null)!==$revision)throw new RuntimeException('invalid_request');
        return $this->withLock(function()use($revision,$requestId,$candidate){$db=$this->db();
            foreach($db['operations'] as $job)if($job['request_id']===$requestId){if($job['revision']!==$revision)throw new RuntimeException('request_conflict');return $job;}
            foreach($db['operations'] as $job)if(!in_array($job['state'],self::TERMINAL,true))throw new RuntimeException('busy');
            $id=bin2hex(random_bytes(16));$this->directory('operations/'.$id);$this->writeFile('operations/'.$id.'/candidate.json',json_encode($candidate,JSON_THROW_ON_ERROR));
            $job=['id'=>$id,'request_id'=>$requestId,'revision'=>$revision,'state'=>'preparing','code'=>null,'boot_id'=>self::boot(),'created_at'=>time(),'created_uptime'=>self::uptime(),'package_version'=>$candidate['package_version']];
            $db['operations'][$id]=$job;$this->rotate($db);$this->save($db);return $job;
        });
    }
    public function update(string $id,array $patch): array
    {
        self::id($id);return $this->withRetryLock(function()use($id,$patch){$db=$this->db();if(!isset($db['operations'][$id]))throw new RuntimeException('missing_operation');$job=$db['operations'][$id];
            $allowed=['state','code','identity','prepared_uptime','apply_request_id','intent','installed_version','core_state','settings_verified','finished_at','phase','runtime_digest'];
            foreach($patch as $k=>$_)if(!in_array($k,$allowed,true))throw new RuntimeException('invalid_state');
            $next=$patch['state']??$job['state'];$transitions=['preparing'=>['preparing','prepared','failed','interrupted'],'prepared'=>['prepared','applying','failed','interrupted'],'applying'=>['applying','succeeded','failed','interrupted']];
            if(!in_array($next,$transitions[$job['state']]??[],true))throw new RuntimeException('invalid_transition');
            if(in_array($next,self::TERMINAL,true))$patch['finished_at']=time();$db['operations'][$id]=array_replace($job,$patch);$result=$db['operations'][$id];$this->rotate($db);$this->save($db);return $result;
        });
    }
    public function readOperation(string $id): array
    {self::id($id);return $this->withRetryLock(function()use($id){$db=$this->db();if(!isset($db['operations'][$id]))throw new RuntimeException('missing_operation');return $db['operations'][$id];});}
    public function claimApply(string $id,string $revision,string $requestId): array
    {
        self::id($id);self::id($requestId);if(!preg_match('/^[a-f0-9]{64}$/D',$revision))throw new RuntimeException('invalid_request');
        return $this->withLock(function()use($id,$revision,$requestId){$db=$this->db();if(!isset($db['operations'][$id]))throw new RuntimeException('missing_operation');$job=$db['operations'][$id];
            foreach($db['operations'] as $other)if(($other['apply_request_id']??null)===$requestId){
                if($other['id']!==$id||$other['revision']!==$revision)throw new RuntimeException('request_conflict');return ['operation'=>$other,'launch'=>false];
            }
            if($job['revision']!==$revision)throw new RuntimeException('stale_revision');
            if($job['state']!=='prepared'||$job['boot_id']!==self::boot()||!preg_match('/^[a-f0-9]{64}$/D',$job['runtime_digest']??''))throw new RuntimeException('invalid_state');
            if($this->readFile('operations/'.$id.'/cancel.json',1024)!==null)throw new RuntimeException('interrupted');
            $job=array_replace($job,['state'=>'applying','phase'=>'queued','apply_request_id'=>$requestId,'apply_uptime'=>self::uptime(),'identity'=>null]);
            $db['operations'][$id]=$job;$this->save($db);return ['operation'=>$job,'launch'=>true];
        });
    }
    public function claimPrepare(string $id): bool
    {
        self::id($id);return $this->withLock(function()use($id){$db=$this->db();if(!isset($db['operations'][$id]))throw new RuntimeException('missing_operation');$job=$db['operations'][$id];
            if($job['state']!=='preparing'||isset($job['prepare_launch_uptime']))return false;
            if($job['boot_id']!==self::boot())throw new RuntimeException('interrupted');$db['operations'][$id]['prepare_launch_uptime']=self::uptime();$this->save($db);return true;
        });
    }
    public function status(): array
    {return $this->withLock(function(){$db=$this->db();$active=null;$history=[];foreach($db['operations'] as $job)if(in_array($job['state'],self::TERMINAL,true))$history[]=$job;else $active=$job;if($this->readFile('operations.json')===null)$this->save($db);return ['active'=>$active,'history'=>array_reverse($history)];});}
    public function reconcile(string $boot,float $uptime): void
    {$this->withLock(function()use($boot,$uptime){$db=$this->db();$before=$db;foreach($db['operations'] as &$job)if(!in_array($job['state'],self::TERMINAL,true)&&($job['boot_id']!==$boot||$uptime<$job['created_uptime'])){$job['state']='interrupted';$job['code']='interrupted';$job['finished_at']=time();}unset($job);$this->rotate($db);if($db!==$before)$this->save($db);});}
}

// webui/web/public/update-lifecycle.php sha256=115ab11f20ba8af5d782b8c1633067db10d02402250d8167df7139e049b5a8b6

/** Only trusted worker code supplies paths; HTTP never supplies a command. */
final class AsusUpdateLifecycle
{
    public function __construct(private array $options=[]) {}
    public static function identity(int $pid): ?array
    {
        if($pid<2)return null;$stat=@file_get_contents('/proc/'.$pid.'/stat');$exe=@readlink('/proc/'.$pid.'/exe');$status=@file_get_contents('/proc/'.$pid.'/status');
        if(!is_string($stat)||!is_string($exe)||!is_string($status)||!preg_match('/^\d+ \(.*\) (.*)$/sD',trim($stat),$m))return null;$fields=preg_split('/\s+/',trim($m[1]));
        if(($fields[0]??'Z')==='Z'||!preg_match('/^[0-9]+$/D',$fields[19]??'')||!preg_match('/^Uid:\s+([0-9]+)/m',$status,$uid))return null;
        return ['pid'=>$pid,'start_ticks'=>$fields[19],'boot_id'=>AsusUpdateStore::boot(),'exe'=>$exe,'uid'=>(int)$uid[1]];
    }
    public static function alive(array $identity): bool
    {return isset($identity['pid'])&&is_int($identity['pid'])&&self::identity($identity['pid'])===$identity;}
    private function stateFile(string $name): ?string
    {
        $run=$this->options['run']??'/tmp/nfqws2-asus';AsusUpdateStore::noLinks($run);$dir=@lstat($run);if(!$dir)return null;$owner=$this->options['owner']??0;
        if(($dir['mode']&0170000)!==0040000||$dir['uid']!==$owner||($dir['mode']&0777)!==0700)throw new RuntimeException('invalid_state');$p=$run.'/'.$name;AsusUpdateStore::noLinks($p);$s=@lstat($p);if(!$s)return null;
        if(($s['mode']&0170000)!==0100000||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>64)throw new RuntimeException('invalid_state');$value=@file_get_contents($p);if(!is_string($value))throw new RuntimeException('invalid_state');return $value;
    }
    public function intent(): array
    {
        $raw=$this->stateFile('pid');$enabled=$this->stateFile('enabled')!==null;$identity=null;
        if($raw!==null&&preg_match('/^[1-9][0-9]{0,9}$/D',trim($raw))){$candidate=self::identity((int)trim($raw));$engine=realpath($this->options['engine']??'/opt/usr/bin/nfqws2');
            if($candidate!==null&&$engine!==false&&in_array($candidate['exe'],[$engine,$engine.' (deleted)'],true))$identity=$candidate;
        }
        return ['mode'=>$identity!==null?'running':($enabled?'waiting_for_wan':'stopped'),'process'=>$identity,'enabled'=>$enabled];
    }
    private function command(string $component,string $action): bool
    {
        if(!in_array($component,['core','web'],true)||!in_array($action,['start','stop','status'],true))throw new RuntimeException('invalid_state');$path=$this->options[$component.'_init']??(AsusUpdateStore::installed('etc/init.d').'/'.($component==='core'?'S51nfqws2':'S81nfqws-asus-web'));
        AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['uid']!==($this->options['owner']??0)||$s['nlink']!==1||($s['mode']&0022)!==0||!is_executable($path))throw new RuntimeException('invalid_state');
        $p=@proc_open([$path,$action],[0=>['file','/dev/null','r'],1=>['file','/dev/null','a'],2=>['file','/dev/null','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin:/opt/bin','LANG'=>'C','LC_ALL'=>'C']);if(!is_resource($p))return false;
        $first=proc_get_status($p);$identity=self::identity((int)$first['pid']);$deadline=microtime(true)+($this->options['service_timeout']??45);$status=$first;$exit=null;$timedOut=false;
        try{while(true){if(!$status['running']){$exit=$status['exitcode'];break;}if(microtime(true)>=$deadline){$timedOut=true;
                    // Signal only our own unreaped child, never the daemon PID.
                    $now=self::identity((int)$first['pid']);if($identity!==null&&$now!==null&&$now['start_ticks']===$identity['start_ticks']&&$now['boot_id']===$identity['boot_id'])proc_terminate($p,15);
                    $end=microtime(true)+1;do{usleep(10000);$status=proc_get_status($p);}while($status['running']&&microtime(true)<$end);
                    if($status['running'])proc_terminate($p,9);break;
                }usleep(20000);$status=proc_get_status($p);}
        }finally{$closed=proc_close($p);if($exit===null||$exit<0)$exit=$closed;}
        return !$timedOut&&$exit===0;
    }
    public function stop(): void
    {
        if($this->intent()['mode']==='stopped')return;
        if(!$this->command('core','stop')||$this->intent()['mode']!=='stopped')throw new RuntimeException('core_stop_failed');
    }
    public function restore(array $intent): string
    {
        if(!in_array($intent['mode']??null,['running','waiting_for_wan','stopped'],true))throw new RuntimeException('invalid_state');
        if($intent['mode']==='stopped'){if($this->intent()['mode']!=='stopped')throw new RuntimeException('intent_mismatch');return 'stopped';}
        if(!$this->command('core','start'))throw new RuntimeException('core_start_failed');$state=$this->intent()['mode'];if($state==='stopped')throw new RuntimeException('core_start_failed');return $state;
    }
    public function web(): void
    {if(!$this->command('web','start')||!$this->command('web','status'))throw new RuntimeException('web_start_failed');}
}

// webui/web/public/update-package.php sha256=db96be2389b0028dca0deed0c74e8032526ef3020bb8803157ee9f2c2ad4d90b
/** Read only bounded control metadata; never extract or execute archive paths. */
final class AsusUpdatePackage
{
    private const REPLACEES=['nfqws2-keenetic','nfqws-keenetic','tpws-keenetic','nfqws-keenetic-web','nfqws-asus-web'];
    public static function fields(string $raw): array
    {
        if(strlen($raw)>2097152||str_contains($raw,"\0"))throw new RuntimeException('invalid_package');$out=[];$key=null;
        foreach(explode("\n",rtrim($raw,"\n")) as $line){if(preg_match('/^[ \t]/',$line)&&$key!==null){$out[$key].=' '.trim($line);continue;}if(!preg_match('/^([A-Za-z][A-Za-z0-9-]*):[ \t]*(.*)$/D',$line,$m)||isset($out[$m[1]]))throw new RuntimeException('invalid_package');$key=$m[1];$out[$key]=$m[2];}return $out;
    }
    private static function dependencies(string $text): array
    {
        if($text==='')return [];$out=array_map('trim',explode(',',$text));foreach($out as $p)if(!preg_match('/^[a-z0-9][a-z0-9+.-]{0,80}$/D',$p))throw new RuntimeException('dependency_change');$out=array_values(array_unique($out));sort($out);return $out;
    }
    public static function database(string $raw): array
    {
        if(strlen($raw)>2097152)throw new RuntimeException('pending_packages');$db=[];
        foreach(preg_split('/\n[ \t]*\n/',trim($raw)) as $section){$p=self::fields($section);$name=$p['Package']??'';if(!preg_match('/^[a-z0-9][a-z0-9+.-]{0,80}$/D',$name))throw new RuntimeException('pending_packages');
            $status=preg_split('/\s+/',trim($p['Status']??''));if(count($status)!==3||!in_array($status[2],['installed','not-installed','config-files'],true))throw new RuntimeException('pending_packages');
            // Opkg retains superseded versions with preference/user flags. They
            // are absent packages, not an interrupted installation or the active version.
            if($status[2]==='not-installed'){
                $flags=explode(',',$status[1]);if(count($flags)!==count(array_unique($flags))||array_diff($flags,['ok','user','prefer']))throw new RuntimeException('pending_packages');continue;
            }
            if(isset($db[$name])||!in_array($status[1],['ok','user'],true))throw new RuntimeException('pending_packages');$db[$name]=$p;
        }return $db;
    }
    private static function header(string $h,bool $nativeRoot=false): ?array
    {
        if(strlen($h)!==512)throw new RuntimeException('invalid_package');if($h===str_repeat("\0",512))return null;
        $size=trim(substr($h,124,12)," \0");$sum=trim(substr($h,148,8)," \0");
        if(!preg_match('/^[0-7]{1,11}$/D',$size)||!preg_match('/^[0-7]{1,7}$/D',$sum))throw new RuntimeException('invalid_package');
        $actual=array_sum(unpack('C*',substr_replace($h,str_repeat(' ',8),148,8)));if($actual!==octdec($sum))throw new RuntimeException('invalid_package');
        $name=rtrim(substr($h,0,100),"\0");
        if($nativeRoot&&in_array($name,['.','./'],true)&&$h[156]==='5'&&octdec($size)===0&&trim(substr($h,345,155),"\0")==='')return ['name'=>'.','size'=>0,'directory'=>true];
        if(str_starts_with($name,'./'))$name=substr($name,2);
        if(trim(substr($h,345,155),"\0")!==''||!in_array($h[156],["\0",'0'],true)||!preg_match('/^[a-zA-Z0-9.-]+$/D',$name))throw new RuntimeException('invalid_package');
        return ['name'=>$name,'size'=>(int)octdec($size)];
    }
    private static function gzRead($f,int $n): string
    {$out='';while(strlen($out)<$n){$chunk=@gzread($f,min(16384,$n-strlen($out)));if(!is_string($chunk)||$chunk==='')throw new RuntimeException('invalid_package');$out.=$chunk;}return $out;}
    private static function control(string $path,string $family): array
    {
        if(!function_exists('gzopen'))throw new RuntimeException('package_reader_unavailable');$f=@gzopen($path,'rb');if(!$f)throw new RuntimeException('invalid_package');$found=[];$control=null;$total=0;
        try{for($i=0;$i<8;$i++){$h=self::header(self::gzRead($f,512));if($h===null)break;$name=$h['name'];$size=$h['size'];
            if(isset($found[$name])||!in_array($name,['control.tar.gz','data.tar.gz','debian-binary'],true)||$size>134217728||($name==='control.tar.gz'&&$size>2097152)||($name==='debian-binary'&&$size!==4))throw new RuntimeException('invalid_package');$found[$name]=true;$total+=$size;if($total>134217728)throw new RuntimeException('invalid_package');
            $raw='';for($left=$size;$left>0;){$chunk=self::gzRead($f,min(16384,$left));if($name!=='data.tar.gz')$raw.=$chunk;$left-=strlen($chunk);}if($size%512)self::gzRead($f,512-$size%512);
            if($name==='control.tar.gz')$control=$raw;elseif($name==='debian-binary'&&$raw!=="2.0\n")throw new RuntimeException('invalid_package');
        }}finally{gzclose($f);}
        if(count($found)!==3||$control===null)throw new RuntimeException('invalid_package');$tar=@gzdecode($control,4194304);if(!is_string($tar)||strlen($tar)>4194304)throw new RuntimeException('invalid_package');$fields=null;$seen=[];$bootstrap=[];
        $helpers=$family==='native'?[]:($family==='armv7'?['busybox-migration-armv7-2.6','busybox-migration-armv7-3.2']:['busybox-migration-aarch64-3.10']);
        for($p=0,$n=0;$p+512<=strlen($tar)&&$n<16;$n++){$block=substr($tar,$p,512);$h=self::header($block,$family==='native');$p+=512;if($h===null)break;
            if(isset($h['directory'])){if(isset($seen['.']))throw new RuntimeException('invalid_package');$seen['.']=true;continue;}
            $helper=in_array($h['name'],$helpers,true);
            if((!$helper&&!in_array($h['name'],['control','preinst','postinst','prerm','postrm','conffiles'],true))||isset($seen[$h['name']])||$h['size']>($helper?1048576:131072)||$p+$h['size']>strlen($tar))throw new RuntimeException('invalid_package');$seen[$h['name']]=true;
            if($helper){
                // Signed, fixed-name bootstrap binaries are read as bytes only.
                // They let preinst preserve data after the old payload was removed.
                $elf=substr($tar,$p,20);$mode=trim(substr($block,100,8),"\0 ");
                if($h['size']<20||substr($elf,0,4)!=="\x7fELF"||ord($elf[4])!==($family==='armv7'?1:2)||ord($elf[5])!==1||unpack('v',substr($elf,18,2))[1]!==($family==='armv7'?40:183)||!preg_match('/^[0-7]{1,7}$/D',$mode)||octdec($mode)!==0755)throw new RuntimeException('invalid_package');
                $bootstrap[]=$h['name'];
            }
            if($h['name']==='control'){if($h['size']>16384)throw new RuntimeException('invalid_package');$fields=self::fields(substr($tar,$p,$h['size']));}$p+=(int)(ceil($h['size']/512)*512);
        }if($fields===null)throw new RuntimeException('invalid_package');sort($bootstrap);sort($helpers);if($bootstrap!==[]&&$bootstrap!==$helpers)throw new RuntimeException('invalid_package');return $fields;
    }
    public static function nativeControl(string $path):array{return self::control($path,'native');}
    public static function inspect(string $path,array $candidate,string $status,string $abi,string $machine): array
    {
        $family=$candidate['package']['family']??null;
        if(!(($family==='aarch64-3.10'&&$abi==='aarch64-3.10'&&$machine==='aarch64')||($family==='armv7'&&in_array($abi,['armv7-2.6','armv7-3.2'],true)&&in_array($machine,['armv7l','armv8l'],true))))throw new RuntimeException('unsupported_abi');
        AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||($s['mode']&0170000)!==0100000||$s['nlink']!==1)throw new RuntimeException('invalid_state');
        if($s['size']!==($candidate['package']['size']??null))throw new RuntimeException('download_size');if(!hash_equals($candidate['package']['sha256'],hash_file('sha256',$path)))throw new RuntimeException('download_hash');
        $control=self::control($path,$family);
        if(($control['Package']??null)!=='nfqws2-asus'||($control['Version']??null)!==$candidate['package_version']||($control['Architecture']??null)!==($family==='armv7'?'all':$family)||($control['Replaces']??'')!=='nfqws-asus-web')throw new RuntimeException('invalid_package');
        $db=self::database($status);if(!isset($db['nfqws2-asus'])||!preg_match('/^install (?:ok|user) installed$/D',$db['nfqws2-asus']['Status']??''))throw new RuntimeException('unsupported_version');
        $deps=self::dependencies($control['Depends']??'');if($deps!==self::dependencies($db['nfqws2-asus']['Depends']??''))throw new RuntimeException('dependency_change');
        foreach($deps as $p)if(!isset($db[$p])||!preg_match('/^install (?:ok|user) installed$/D',$db[$p]['Status']))throw new RuntimeException('missing_dependencies');
        foreach(array_filter(array_map('trim',explode(',',$control['Conflicts']??''))) as $p)if(!in_array($p,self::REPLACEES,true))throw new RuntimeException('invalid_package');
        foreach(self::REPLACEES as $p)if(isset($db[$p])&&str_ends_with($db[$p]['Status'],' installed'))throw new RuntimeException('pending_packages');return $control;
    }
    public static function space(int|float $free,int $ipk,int $snapshot,int $runtime): bool
    {if(min($free,$ipk,$snapshot,$runtime)<0||$free<$ipk+$snapshot+$runtime+16777216)throw new RuntimeException('insufficient_space');return true;}
}


// webui/web/public/openwrt-manual-context.php sha256=b3a264dfca62e404746c61d789698950bd311c7744cc293c2161aba4518ee532

/** Only the fixed root quiesce controller inside a live native manager. */
final class NfqwsOpenWrtManualContext
{
    public static function manager():array
    {
        if(!NfqwsPlatform::native())throw new RuntimeException('invalid_state');$allowed=[];
        foreach(['ipk'=>'/bin/opkg','apk'=>'/usr/bin/apk']as $format=>$path){$real=realpath($path);if($real!==false)$allowed[$real]=$format;}
        $pid=getmypid();$seen=[];
        for($n=0;$n<32&&$pid>1;$n++){
            if(isset($seen[$pid]))break;$seen[$pid]=true;$i=AsusUpdateLifecycle::identity($pid);
            if($i!==null&&$i['uid']===0&&isset($allowed[$i['exe']])){
                $raw=@file_get_contents('/proc/'.$pid.'/cmdline',false,null,0,65537);
                if(!is_string($raw)||strlen($raw)>65536||!str_ends_with($raw,"\0")||AsusUpdateLifecycle::identity($pid)!==$i)throw new RuntimeException('invalid_state');
                return ['format'=>$allowed[$i['exe']],'identity'=>$i,'argv'=>explode("\0",substr($raw,0,-1))];
            }
            $raw=@file_get_contents('/proc/'.$pid.'/status');if(!is_string($raw)||!preg_match('/^PPid:\s+([0-9]+)/m',$raw,$m))break;$pid=(int)$m[1];
        }
        throw new RuntimeException('invalid_state');
    }
    /** Private journal + native process identity, independent of controller lifetime. */
    public static function activeManager():?array
    {
        if(!NfqwsPlatform::native())return null;$path='/tmp/nfqws2-native-package/state';
        try{AsusUpdateStore::noLinks($path);}catch(Throwable $e){return null;}$dir=@lstat(dirname($path));$s=@lstat($path);
        if(!$dir||!is_dir(dirname($path))||$dir['uid']!==0||($dir['mode']&0777)!==0700||!$s||!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>4096)return null;
        $raw=file_get_contents($path);if(!is_string($raw)||preg_match_all('/^manager=([^\r\n]*)$/m',$raw,$rows)!==1||!preg_match('/^([A-Za-z0-9-]{8,64}):([1-9][0-9]{0,9}):([1-9][0-9]{0,19})$/D',$rows[1][0],$m)||(float)$m[2]>2147483647||$m[1]!==AsusUpdateStore::boot())return null;
        $i=AsusUpdateLifecycle::identity((int)$m[2]);if($i===null||$i['uid']!==0||$i['start_ticks']!==$m[3]||$i['boot_id']!==$m[1])return null;
        foreach(['ipk'=>'/bin/opkg','apk'=>'/usr/bin/apk']as $format=>$path){$exe=realpath($path);if($exe!==false&&$exe===$i['exe']&&AsusUpdateLifecycle::alive($i))return ['format'=>$format,'identity'=>$i];}
        return null;
    }
    /** Only this manager's completed payload/defaults may restore saved starts. */
    public static function startingAuthorized(string $action):bool
    {
        if(!in_array($action,['core-start','web-start'],true))return false;$active=self::activeManager();if($active===null)return false;
        try{$actual=self::manager();if($actual['identity']!==$active['identity'])return false;}catch(Throwable $e){return false;}
        $m=$active['identity'];$tuple=$m['boot_id'].':'.$m['pid'].':'.$m['start_ticks'];$path='/tmp/nfqws2-native-package/phase';
        try{AsusUpdateStore::noLinks($path);}catch(Throwable $e){return false;}$s=@lstat($path);
        if(!$s||!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>256||file_get_contents($path)!==$tuple."\nstarting\n")return false;
        $raw=(string)file_get_contents('/tmp/nfqws2-native-package/state');$v=[];
        foreach(explode("\n",trim($raw))as $line){if(!preg_match('/^([a-z_]+)=([^\r\n]*)$/D',$line,$r)||isset($v[$r[1]]))return false;$v[$r[1]]=$r[2];}
        $keys=array_keys($v);sort($keys);$expected=['manager','enabled','running','web_present','web_enabled','web_running'];sort($expected);if($keys!==$expected||$v['manager']!==$tuple)return false;
        foreach(array_diff($keys,['manager'])as $key)if(!in_array($v[$key],['0','1'],true))return false;
        return AsusUpdateLifecycle::alive($m)&&($action==='core-start'?$v['running']==='1':($v['web_present']==='0'||$v['web_running']==='1'));
    }
    public static function authorize():bool
    {
        if(!NfqwsPlatform::native())return false;$entry='/usr/lib/nfqws2/update/quiesce.php';
        try{AsusUpdateStore::noLinks($entry);}catch(Throwable $e){return false;}
        clearstatcache(true,$entry);$file=@lstat($entry);
        if(!$file||!is_file($entry)||$file['uid']!==0||$file['nlink']!==1||($file['mode']&0022)!==0)return false;
        for($parent=dirname($entry);$parent!=='/';$parent=dirname($parent)){$d=@lstat($parent);if(!$d||!is_dir($parent)||$d['uid']!==0||($d['mode']&0022)!==0)return false;}
        $php=realpath('/usr/bin/php-cgi');if($php!=='/usr/bin/php8-cgi')return false;
        $allowed=array_filter([realpath('/bin/opkg'),realpath('/usr/bin/apk')]);$controller=null;$manager=null;$pid=getmypid();$seen=[];
        for($n=0;$n<32&&$pid>1;$n++){
            if(isset($seen[$pid]))return false;$seen[$pid]=true;$i=AsusUpdateLifecycle::identity($pid);
            if($i!==null&&$i['uid']===0){
                if($controller===null&&$i['exe']===$php){
                    $raw=@file_get_contents('/proc/'.$pid.'/cmdline',false,null,0,8193);
                    if(is_string($raw)&&strlen($raw)<=8192&&str_ends_with($raw,"\0")){
                        $args=explode("\0",substr($raw,0,-1));$prefix=[$php,'-d','register_argc_argv=1','-q','-f',$entry,'--'];
                        if(count($args)===8&&array_slice($args,0,7)===$prefix&&in_array($args[7],['upgrade','remove'],true))$controller=$i;
                    }
                }elseif($controller!==null&&in_array($i['exe'],$allowed,true)){$manager=$i;break;}
            }
            $raw=@file_get_contents('/proc/'.$pid.'/status');if(!is_string($raw)||!preg_match('/^PPid:\s+([0-9]+)/m',$raw,$m))return false;$pid=(int)$m[1];
        }
        if($controller===null||$manager===null||!AsusUpdateLifecycle::alive($controller)||!AsusUpdateLifecycle::alive($manager))return false;
        $path='/tmp/nfqws2-native-package/state';try{AsusUpdateStore::noLinks($path);}catch(Throwable $e){return false;}
        $dir=@lstat(dirname($path));$s=@lstat($path);
        if(!$dir||!is_dir(dirname($path))||$dir['uid']!==0||($dir['mode']&0777)!==0700||!$s||!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>4096)return false;
        $raw=file_get_contents($path);if(!is_string($raw)||preg_match_all('/^manager=([^\r\n]*)$/m',$raw,$m)!==1)return false;
        return $m[1][0]===$manager['boot_id'].':'.$manager['pid'].':'.$manager['start_ticks']&&AsusUpdateLifecycle::alive($manager)&&AsusUpdateLifecycle::alive($controller);
    }
}

// webui/web/public/openwrt-update-environment.php sha256=bb7a01b3d5e635683d8e52ce0d2d911faa6ab81e132d171fb89e5adcecafb3bc

/** Actual firmware metadata and the native manager must agree with our package. */
final class NfqwsOpenWrtUpdateEnvironment
{
    public static function firmware(string $release):array
    {
        if(strlen($release)>16384||str_contains($release,"\0"))throw new RuntimeException('unsupported_abi');
        $fields=[];preg_match_all("/^DISTRIB_(RELEASE|ARCH|TARGET)='([^'\r\n]*)'$/m",$release,$matches,PREG_SET_ORDER);
        foreach($matches as $m){if(isset($fields[$m[1]]))throw new RuntimeException('unsupported_abi');$fields[$m[1]]=$m[2];}
        $arch=$fields['ARCH']??'';
        if(count($fields)!==3||!preg_match('/^(24\.10|25\.12)(?:\.[0-9]+)?(?:[-+][A-Za-z0-9_.-]+)?$/D',$fields['RELEASE'],$m)||
            !preg_match('/^[a-z0-9][a-z0-9_+-]{0,99}$/D',$arch)||!preg_match('~^[a-z0-9_-]+/[a-z0-9_-]+$~D',$fields['TARGET']))throw new RuntimeException('unsupported_abi');
        $series=$m[1];$format=$series==='24.10'?'ipk':'apk';
        return ['platform'=>'openwrt','series'=>$series,'arch'=>$arch,'format'=>$format,'target'=>$fields['TARGET'],'manager'=>$format==='ipk'?'/bin/opkg':'/usr/bin/apk'];
    }
    public static function resolve(string $release,array $profile,array $record):array
    {
        $firmware=self::firmware($release);['series'=>$series,'arch'=>$arch,'format'=>$format]=$firmware;
        if(($profile['platform']??null)!=='openwrt'||($profile['arch']??null)!==$arch||($profile['series']??null)!==$series||($profile['format']??null)!==$format)throw new RuntimeException('unsupported_abi');
        $version=$profile['version']??null;$build=$profile['application_build']??null;
        if(!is_string($version)||!preg_match('/^(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-'.($format==='apk'?'r':'').'[1-9][0-9]{0,9}$/D',$version)||!is_int($build)||$build<1||$build>2147483647)throw new RuntimeException('unsupported_version');
        if(($record['name']??null)!=='nfqws2-native'||($record['version']??null)!==$version||($record['arch']??null)!==$arch)throw new RuntimeException('version_mismatch');
        return ['platform'=>'openwrt','series'=>$series,'arch'=>$arch,'format'=>$format,'target'=>$firmware['target'],
            'installed'=>$version,'build'=>$build,'manager'=>$format==='ipk'?'/bin/opkg':'/usr/bin/apk'];
    }

    public static function opkgRecord(string $raw):array
    {
        $v=AsusUpdatePackage::fields($raw);$status=preg_split('/\s+/',trim($v['Status']??''));
        $flags=explode(',',$status[1]??'');
        if(count($status)!==3||!in_array($status[0],['install','hold'],true)||$status[2]!=='installed'||count($flags)!==count(array_unique($flags))||array_diff($flags,['ok','user','prefer','hold']))throw new RuntimeException('pending_packages');
        return ['name'=>$v['Package']??null,'version'=>$v['Version']??null,'arch'=>$v['Architecture']??null];
    }

    public static function collect():array
    {
        if(!NfqwsPlatform::native())throw new RuntimeException('unsupported_abi');
        $path=NfqwsPlatform::sharedFile('platform.json','/usr/share/nfqws2/platform.json');
        $raw=@file_get_contents($path,false,null,0,4097);if(!is_string($raw)||strlen($raw)>4096)throw new RuntimeException('unsupported_abi');
        $profile=AsusSupportSchema::toArray(AsusSupportSchema::decode($raw,4096,'unsupported_abi'));
        if(!is_array($profile))throw new RuntimeException('unsupported_abi');
        $release=(string)@file_get_contents('/etc/openwrt_release',false,null,0,16385);
        $format=$profile['format']??null;
        if($format==='ipk'){
            $r=NfqwsPlatform::run(['/bin/opkg','status','nfqws2-native'],5);
            if($r['status']!==0)throw new RuntimeException('unsupported_version');
            $record=self::opkgRecord(implode("\n",$r['output']));
        }elseif($format==='apk'){
            $r=NfqwsPlatform::run(['/usr/bin/apk','query','--installed','--format','json','--fields','name,version,arch','nfqws2-native'],5);
            if($r['status']!==0)throw new RuntimeException('unsupported_version');
            $rows=AsusSupportSchema::toArray(AsusSupportSchema::decode(implode("\n",$r['output']),65536,'unsupported_version'));
            if(!is_array($rows)||array_keys($rows)!==[0]||!is_array($rows[0]))throw new RuntimeException('unsupported_version');$record=$rows[0];
        }else throw new RuntimeException('unsupported_abi');
        return self::resolve($release,$profile,$record);
    }
}

// webui/web/public/openwrt-update-package.php sha256=db65daea31bd9872ac983cef11fb581f684b82b37a3f652920fae52f73b352ce

/** Read-only preparation contract, before a package manager may run hooks. */
final class NfqwsOpenWrtUpdatePackage
{
    private static function identity(array $candidate,array $environment):array
    {
        $p=$candidate['package']??[];
        if(($environment['platform']??null)!=='openwrt'||!in_array($p['format']??null,['ipk','apk'],true))throw new RuntimeException('unsupported_abi');
        foreach(['series','format','arch']as $field)if(($p[$field]??null)!==($environment[$field]??null))throw new RuntimeException('unsupported_abi');
        return $p;
    }
    public static function metadata(array $record,array $candidate,array $environment):array
    {
        $p=self::identity($candidate,$environment);
        if(($record['name']??null)!=='nfqws2-native'||($record['version']??null)!==($candidate['package_version']??null)||
            ($record['version']??null)!==($p['version']??null)||($record['arch']??null)!==($p['arch']??null)||
            ($record['replaces']??[])!==[]||($record['conflicts']??[])!==[])throw new RuntimeException('invalid_package');
        $deps=$record['depends']??null;
        if(!is_array($deps)||!array_is_list($deps)||count($deps)>64)throw new RuntimeException('invalid_package');
        $seen=[];foreach($deps as $dep){if(!is_string($dep)||!preg_match('/^[a-z0-9][a-z0-9+._-]{0,80}$/D',$dep)||isset($seen[$dep]))throw new RuntimeException('invalid_package');$seen[$dep]=true;}
        $size=$record['installed_size']??null;$bound=$p['installed_size']??null;
        if(!is_int($bound)||$bound<1||$bound>134217728||($p['format']==='apk'&&(!is_int($size)||$size<1))||
            ($size!==null&&(!is_int($size)||$size<0||$size>$bound)))throw new RuntimeException('invalid_package');
        return $record;
    }
    public static function inspect(string $path,array $candidate,array $environment,?string $keys=null,int $owner=0):array
    {
        $p=self::identity($candidate,$environment);AsusUpdateStore::noLinks($path);clearstatcache(true,$path);$s=@lstat($path);
        if(!$s||!is_file($path)||$s['uid']!==$owner||$s['nlink']!==1||($s['mode']&0777)!==0600)throw new RuntimeException('invalid_state');
        if($s['size']!==($p['size']??null)||$s['size']>33554432)throw new RuntimeException('download_size');
        $hash=hash_file('sha256',$path);if(!is_string($p['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$p['sha256'])||!is_string($hash)||!hash_equals($p['sha256'],$hash))throw new RuntimeException('download_hash');
        if($p['format']==='ipk'){
            $fields=AsusUpdatePackage::nativeControl($path);
            $list=static fn(string $s):array=>trim($s)===''?[]:array_map('trim',explode(',',$s));
            $record=['name'=>$fields['Package']??null,'version'=>$fields['Version']??null,'arch'=>$fields['Architecture']??null,
                'depends'=>$list($fields['Depends']??''),'installed_size'=>null,'replaces'=>$list($fields['Replaces']??''),'conflicts'=>$list($fields['Conflicts']??'')];
        }else{
            if($keys===null)throw new RuntimeException('invalid_signature');AsusUpdateStore::noLinks($keys);$k=@lstat($keys);
            if(!$k||!is_dir($keys)||$k['uid']!==$owner||($k['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
            $verified=NfqwsPlatform::run(['/usr/bin/apk','verify','--keys-dir',$keys,$path],30);
            if($verified['status']!==0)throw new RuntimeException('invalid_signature');
            $dump=NfqwsPlatform::run(['/usr/bin/apk','adbdump','--format','json',$path],30,[],1048576);
            if($dump['status']!==0)throw new RuntimeException('invalid_package');
            $data=AsusSupportSchema::toArray(AsusSupportSchema::decode(implode("\n",$dump['output']),1048576,'invalid_package'));
            $info=$data['info']??null;if(!is_array($info))throw new RuntimeException('invalid_package');
            $record=['name'=>$info['name']??null,'version'=>$info['version']??null,'arch'=>$info['arch']??null,
                'depends'=>$info['depends']??[],'installed_size'=>$info['installed-size']??null,'replaces'=>$info['replaces']??[],'conflicts'=>$info['conflicts']??[]];
        }
        return self::metadata($record,$candidate,$environment);
    }
    public static function space(int|float $overlay,int|float $ram,array $package,int $snapshot,int $runtime):bool
    {
        $stored=$package['installed_size']??null;$download=$package['size']??null;
        if(!is_int($stored)||$stored<1||$stored>134217728||!is_int($download)||$download<1||$download>33554432)throw new RuntimeException('invalid_package');
        if(!is_finite((float)$overlay)||!is_finite((float)$ram)||min($overlay,$ram,$snapshot,$runtime)<0||
            $overlay<$stored+4194304||$ram<$download+$snapshot+$runtime+4194304)throw new RuntimeException('insufficient_space');
        return true;
    }
}

// webui/web/public/openwrt-update-manager.php sha256=78f79886bfbcf798cb43dd2a5323573ebc5e151971511add6c2d1dbbea07ce2f

/** Application-only native transaction. No general system upgrade is requested. */
final class NfqwsOpenWrtUpdateManager
{
    private static function package(string $name,string $version):void
    {
        if(!preg_match('/^[a-z0-9][a-z0-9+._-]{0,127}$/D',$name)||!preg_match('/^[A-Za-z0-9][A-Za-z0-9.+_:~\-]{0,199}$/D',$version))throw new RuntimeException('pending_packages');
    }
    public static function database(string $raw,string $format,bool $ownTransition=false,bool $ownOnly=false):array
    {
        if(strlen($raw)>2097152||str_contains($raw,"\0")||!in_array($format,['ipk','apk'],true)||trim($raw)==='')throw new RuntimeException('pending_packages');
        $out=[];
        foreach(preg_split('/\n[ \t]*\n/',trim($raw))as $section){
            if($ownOnly&&!preg_match($format==='ipk'?'/^Package:[ \t]+nfqws2-native[ \t]*$/m':'/^P:nfqws2-native$/m',$section))continue;
            if($format==='ipk'){
                $p=AsusUpdatePackage::fields($section);if($ownTransition&&($p['Package']??null)==='nfqws2-native')continue;$status=preg_split('/\s+/',trim($p['Status']??''));$flags=explode(',',$status[1]??'');
                if(count($status)!==3||!in_array($status[0],['install','hold','deinstall','purge','unknown'],true)||array_diff($flags,['ok','user','prefer','hold'])||count($flags)!==count(array_unique($flags)))throw new RuntimeException('pending_packages');
                if(in_array($status[2],['not-installed','config-files'],true))continue;
                if($status[2]!=='installed'||!in_array($status[0],['install','hold'],true))throw new RuntimeException('pending_packages');
                $name=$p['Package']??'';$version=$p['Version']??'';
            }else{
                $p=[];foreach(explode("\n",$section)as $line){if(!preg_match('/^([A-Za-z]):(.*)$/D',$line,$m))throw new RuntimeException('pending_packages');
                    if(in_array($m[1],['P','V','f'],true)){if(isset($p[$m[1]]))throw new RuntimeException('pending_packages');$p[$m[1]]=$m[2];}}
                $name=$p['P']??'';$version=$p['V']??'';if($ownTransition&&$name==='nfqws2-native')continue;
                if(!preg_match('/^[Sx]*$/D',$p['f']??''))throw new RuntimeException('pending_packages');
            }
            self::package($name,$version);if(isset($out[$name]))throw new RuntimeException('pending_packages');$out[$name]=$version;
        }
        if(count($out)>4096||count($out)<1)throw new RuntimeException('pending_packages');ksort($out);return $out;
    }
    public static function raw(array $environment):string
    {
        $file=match($environment['format']??null){'ipk'=>'/usr/lib/opkg/status','apk'=>'/lib/apk/db/installed',default=>throw new RuntimeException('unsupported_abi')};
        $path=realpath($file);if($path===false)throw new RuntimeException('pending_packages');$s=@lstat($path);
        if(!$s||!is_file($path)||$s['uid']!==0||($s['mode']&0022)!==0||$s['size']>2097152)throw new RuntimeException('pending_packages');
        $raw=file_get_contents($path);if(!is_string($raw))throw new RuntimeException('pending_packages');return $raw;
    }
    public static function installed(array $environment,bool $ownTransition=false,bool $ownOnly=false):array
    {return self::database(self::raw($environment),$environment['format'],$ownTransition,$ownOnly);}
    /** Dependencies may name a native installed provider, such as libgcc1 -> libgcc. */
    private static function provided(array $environment,array $installed,bool $ownTransition=false):array
    {
        $raw=self::raw($environment);if(self::database($raw,$environment['format'],$ownTransition)!==$installed)throw new RuntimeException('dependency_change');$out=[];
        foreach(preg_split('/\n[ \t]*\n/',trim($raw))as $section){
            if($environment['format']==='ipk'){$p=AsusUpdatePackage::fields($section);$name=$p['Package']??'';$offers=explode(',',$p['Provides']??'');}
            else{preg_match('/^P:(.*)$/m',$section,$nameRow);$name=$nameRow[1]??'';if(preg_match_all('/^p:(.*)$/m',$section,$rows)>1)throw new RuntimeException('pending_packages');$offers=preg_split('/[ \t]+/',$rows[1][0]??'');}
            if(!isset($installed[$name]))continue;
            foreach($offers as $offer){$offer=trim($offer);
                $pattern=$environment['format']==='ipk'?'/^([a-z0-9][a-z0-9+._-]{0,127})(?:[ \t]+\([<>=]+[ \t]*[A-Za-z0-9.+_:~\-]+\))?$/D':'/^([a-z0-9][a-z0-9+._-]{0,127})(?:=[A-Za-z0-9.+_:~\-]+)?$/D';
                if(preg_match($pattern,$offer,$m))$out[$m[1]]=true;
            }
        }return $out;
    }
    private static function unresolved(array $environment,array $installed,array $depends,bool $ownTransition):array
    {
        if(!array_is_list($depends)||count($depends)>64)throw new RuntimeException('invalid_package');
        foreach($depends as $name)if(!is_string($name)||!preg_match('/^[a-z0-9][a-z0-9+._-]{0,80}$/D',$name))throw new RuntimeException('invalid_package');
        $missing=array_values(array_diff($depends,array_keys($installed)));
        if($missing){$provided=self::provided($environment,$installed,$ownTransition);$missing=array_values(array_filter($missing,fn($name)=>!isset($provided[$name])));}
        return $missing;
    }
    public static function missing(array $environment,array $depends,bool $ownTransition=false):array
    {return self::unresolved($environment,self::installed($environment,$ownTransition),$depends,$ownTransition);}
    public static function argv(string $path,array $environment,array $installed,array $record,?string $keys=null,bool $simulate=false,bool $ownTransition=false):array
    {
        if(($record['name']??null)!=='nfqws2-native'||!is_array($record['depends']??null))throw new RuntimeException('invalid_package');
        if(!str_starts_with($path,'/')||strpbrk($path,"\0\r\n")!==false)throw new RuntimeException('invalid_state');
        if(self::unresolved($environment,$installed,$record['depends'],$ownTransition))throw new RuntimeException('missing_dependencies');
        if(($environment['format']??null)==='ipk')return array_merge(['/bin/opkg','--nodeps'],$simulate?['--noaction']:[],['install',$path]);
        if(($environment['format']??null)!=='apk')throw new RuntimeException('unsupported_abi');
        if($keys===null)throw new RuntimeException('invalid_signature');$argv=['/usr/bin/apk','add','--network=no','--cache=no','--repositories-file','/dev/null','--keys-dir',$keys];
        if($simulate)$argv[]='--simulate';
        $argv[]=$path;return $argv;
    }
    public static function plan(string $raw,string $format,array $record):bool
    {
        if(strlen($raw)>65536||str_contains($raw,"\0"))throw new RuntimeException('dependency_change');$seen=0;$version=preg_quote($record['version']??'','#');
        foreach(explode("\n",trim($raw))as $line){
            if($line==='')continue;
            if($format==='ipk'&&$line==='Multiple packages (nfqws2-native and nfqws2-native) providing same name marked HOLD or PREFER. Using latest.')continue;
            if($format==='ipk'&&preg_match('#^(?:Installing nfqws2-native \('.$version.'\) to root|Upgrading nfqws2-native on root from [A-Za-z0-9.+_:~\-]+ to '.$version.')\.\.\.$#D',$line)){$seen++;continue;}
            if($format==='apk'&&preg_match('#^\(1/1\) (?:Installing nfqws2-native \('.$version.'\)|Upgrading nfqws2-native \([A-Za-z0-9.+_:~\-]+ -> '.$version.'\))$#D',$line)){$seen++;continue;}
            if($format==='apk'&&preg_match('/^OK: [0-9]+(?:\.[0-9]+)? (?:B|KiB|MiB|GiB) in [0-9]+ packages$/D',$line))continue;
            throw new RuntimeException('dependency_change');
        }
        if($seen!==1)throw new RuntimeException('dependency_change');return true;
    }
}

// webui/web/public/openwrt-apk-trust.php sha256=fd1188686af7edde6886cdc7a12180f48ffcf99434c4bd6cb5df4a145faa156b

/** Per-operation union of native feed trust and the pinned application key. */
final class NfqwsOpenWrtApkTrust
{
    private static function directory(string $path,int $owner):void
    {
        AsusUpdateStore::noLinks($path);$s=@lstat($path);
        if(!$s||!is_dir($path)||!in_array($s['uid'],[0,$owner],true)||($s['mode']&0022)!==0)throw new RuntimeException('invalid_state');
    }
    public static function stage(string $destination,string $ownKey,array $roots=['/etc/apk/keys','/lib/apk/keys'],int $owner=0):array
    {
        if(!extension_loaded('openssl'))throw new RuntimeException('signature_unavailable');
        $own=@openssl_pkey_get_public($ownKey);$details=$own===false?false:openssl_pkey_get_details($own);
        if(strlen($ownKey)>16384||!$details||$details['type']!==OPENSSL_KEYTYPE_RSA||$details['bits']!==3072)throw new RuntimeException('invalid_signature');
        self::directory(dirname($destination),$owner);AsusUpdateStore::noLinks($destination);
        if(file_exists($destination)||is_link($destination)||count($roots)>2)throw new RuntimeException('invalid_state');
        $keys=[];$seen=[];$total=0;
        foreach($roots as $root){
            if(!is_string($root))throw new RuntimeException('invalid_state');
            if(!file_exists($root)&&!is_link($root))continue;self::directory($root,$owner);
            $names=scandir($root);if($names===false||count($names)>258)throw new RuntimeException('output_limit');
            foreach($names as $name){
                if(str_starts_with($name,'.')||isset($seen[$name]))continue;$seen[$name]=true;
                $path=$root.'/'.$name;$s=@lstat($path);
                if($s&&is_link($path)){
                    if(!in_array($s['uid'],[0,$owner],true))throw new RuntimeException('invalid_state');
                    $resolved=realpath($path);if($resolved===false)continue;
                    self::directory(dirname($resolved),$owner);$path=$resolved;$s=@lstat($path);
                }
                if(!$s||!is_file($path)||$s['size']>16384)continue;
                $raw=@file_get_contents($path,false,null,0,16385);
                if(!is_string($raw)||!preg_match('/\A\s*-----BEGIN (?:RSA )?PUBLIC KEY-----/',$raw)||@openssl_pkey_get_public($raw)===false)continue;
                if(!in_array($s['uid'],[0,$owner],true)||($s['mode']&0022)!==0||!preg_match('/^[A-Za-z0-9][A-Za-z0-9_.@+-]{0,191}$/D',$name))throw new RuntimeException('invalid_state');
                $keys[$name]=$raw;$total+=strlen($raw);if(count($keys)>128||$total>1048576)throw new RuntimeException('output_limit');
            }
        }
        $name='nfqws2-native-'.hash('sha256',$ownKey).'.pem';
        if(isset($keys[$name])&&$keys[$name]!==$ownKey)throw new RuntimeException('invalid_state');$keys[$name]=$ownKey;
        ksort($keys);$files=[];$mask=umask(0077);
        try{
            if(!mkdir($destination,0700))throw new RuntimeException('storage_unavailable');
            $index=[];foreach($keys as $name=>$raw)$index[$name]=['mode'=>0600,'size'=>strlen($raw),'sha256'=>hash('sha256',$raw)];
            $rawIndex=json_encode(['files'=>$index],JSON_THROW_ON_ERROR);
            if(strlen($rawIndex)>131072||file_put_contents($destination.'/staging.json',$rawIndex)!==strlen($rawIndex))throw new RuntimeException('storage_unavailable');
            foreach($keys as $name=>$raw){
                if(file_put_contents($destination.'/'.$name,$raw)!==strlen($raw)||!chmod($destination.'/'.$name,0600))throw new RuntimeException('storage_unavailable');
                $files[$name]=hash('sha256',$raw);
            }
            if(!rename($destination.'/staging.json',$destination.'/keys-index.json'))throw new RuntimeException('storage_unavailable');
        }finally{umask($mask);}
        return ['files'=>$files,'digest'=>hash('sha256',json_encode($files,JSON_THROW_ON_ERROR))];
    }
}

// webui/web/public/update-github.php sha256=4f0929dd2ed3f69ea333fed1e61221bca9e9ea360db7a8a15cbff7188ae2fb7e
/** Fixed public discovery and release locations. Signed metadata remains the trust gate. */
final class AsusGithubUpdateSource implements AsusUpdateSource
{
    private const METADATA='https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/updates/v2/public.json';
    private const NATIVE_METADATA='https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/updates/v2/openwrt/public.json';
    private const RELEASES='https://github.com/madworldpay/nfqws2-asus-community/releases/download/';
    private const ASSET_HOST='release-assets.githubusercontent.com';
    private const HTTPS_PORT=443;
    private const ENVELOPE_LIMIT=46080;
    private const CORE='(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-asus[1-9][0-9]{0,5}';
    private const NATIVE_CORE='(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})';

    public function __construct(private int $owner=0,private string $ca='/opt/etc/ssl/certs/ca-certificates.crt',private array $timeouts=['metadata'=>15,'download'=>180],private string $platform='asus-entware')
    {if(!in_array($platform,['asus-entware','openwrt'],true))throw new RuntimeException('invalid_channel');}

    private static function redirect(string $url): string
    {
        // GitHub asset URLs contain an expiring query, but their origin and path
        // are fixed. Never accept relative URLs, credentials or another service.
        $parts=parse_url($url);
        if(strlen($url)>8192||preg_match('/[^\x21-\x7e]|\\\\/',$url)||!is_array($parts)||($parts['scheme']??null)!=='https'||
            ($parts['host']??null)!==self::ASSET_HOST||($parts['port']??443)!==self::HTTPS_PORT||
            !preg_match('~^/github-production-release-asset/[A-Za-z0-9/_-]+$~D',$parts['path']??''))throw new RuntimeException('download_redirect');
        foreach(['user','pass','fragment'] as $key)if(array_key_exists($key,$parts))throw new RuntimeException('download_redirect');
        return $url;
    }

    private function request(string $url,int $cap,float $deadline,bool $redirects=false,?callable $consume=null): string
    {
        if(!extension_loaded('openssl')||!is_readable($this->ca))throw new RuntimeException('https_unavailable');
        for($hop=0;;$hop++){
            $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException('timed_out');
            // A fresh context per hop carries no credentials, cookies or headers
            // supplied by a server. TLS peer and hostname checks are mandatory.
            $context=stream_context_create(['ssl'=>['verify_peer'=>true,'verify_peer_name'=>true,'allow_self_signed'=>false,'cafile'=>$this->ca],
                'http'=>['timeout'=>min(15,$remaining),'follow_location'=>0,'max_redirects'=>0,'ignore_errors'=>true,'protocol_version'=>1.1,
                    'header'=>"Accept: application/octet-stream\r\nAccept-Encoding: identity\r\nConnection: close\r\nUser-Agent: NFQWS2-ASUS-Updater/1\r\n"]]);
            $f=@fopen($url,'rb',false,$context);if(!$f)throw new RuntimeException('download_failed');
            try{
                if(microtime(true)>=$deadline)throw new RuntimeException('timed_out');
                $status=0;$length=null;$encoding=null;$location=null;$headerBytes=0;
                foreach(stream_get_meta_data($f)['wrapper_data']??[] as $header){
                    $headerBytes+=strlen($header);if($headerBytes>16384)throw new RuntimeException('download_failed');
                    if(preg_match('~^HTTP/\S+ ([0-9]{3})\b~',$header,$match)){$status=(int)$match[1];$length=null;$encoding=null;$location=null;}
                    elseif(stripos($header,'Content-Length:')===0){$value=trim(substr($header,15));if($length!==null||!preg_match('/^[0-9]{1,10}$/D',$value)||(float)$value>$cap)throw new RuntimeException('download_size');$length=(int)$value;}
                    elseif(stripos($header,'Content-Encoding:')===0){if($encoding!==null)throw new RuntimeException('download_size');$encoding=strtolower(trim(substr($header,17)));}
                    elseif(stripos($header,'Location:')===0){if($location!==null)throw new RuntimeException('download_redirect');$location=trim(substr($header,9));}
                }
                if(in_array($status,[301,302,303,307,308],true)){
                    if(!$redirects||$hop>=3||$location===null)throw new RuntimeException('download_redirect');
                    $url=self::redirect($location);continue;
                }
                if($status!==200)throw new RuntimeException('download_failed');
                if($encoding!==null&&$encoding!=='identity')throw new RuntimeException('download_size');
                $count=0;$body='';
                while(!feof($f)){
                    $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException('timed_out');
                    $timeout=min(5,$remaining);stream_set_timeout($f,(int)$timeout,(int)(($timeout-(int)$timeout)*1000000));
                    $chunk=@fread($f,min(16384,$cap+1-$count));
                    if(microtime(true)>=$deadline)throw new RuntimeException('timed_out');
                    if($chunk===false||stream_get_meta_data($f)['timed_out'])throw new RuntimeException('download_failed');
                    $count+=strlen($chunk);if($count>$cap)throw new RuntimeException('download_size');
                    if($consume!==null)$consume($chunk);else $body.=$chunk;
                    if($chunk==='')usleep(1000);
                }
                if($length!==null&&$count!==$length)throw new RuntimeException('download_size');
                return $body;
            }finally{fclose($f);}
        }
    }

    public function manifest(): array
    {
        $raw=$this->request($this->platform==='openwrt'?self::NATIVE_METADATA:self::METADATA,self::ENVELOPE_LIMIT,microtime(true)+min(15,$this->timeouts['metadata']));
        $envelope=AsusSupportSchema::decode($raw,self::ENVELOPE_LIMIT,'invalid_manifest');
        if(!is_object($envelope))throw new RuntimeException('invalid_manifest');
        $keys=array_keys(get_object_vars($envelope));sort($keys);
        if($keys!==['manifest','signature']||!is_string($envelope->manifest)||!is_string($envelope->signature))throw new RuntimeException('invalid_manifest');
        $json=base64_decode($envelope->manifest,true);
        if($json===false||$json===''||strlen($json)>32768||base64_encode($json)!==$envelope->manifest)throw new RuntimeException('invalid_manifest');
        $signature=base64_decode($envelope->signature,true);
        if(strlen($envelope->signature)>1024||$signature===false||strlen($signature)!==384||base64_encode($signature)!==$envelope->signature)throw new RuntimeException('invalid_signature');
        return ['json'=>$json,'signature'=>$envelope->signature];
    }

    public function download(array $package,string $destination): void
    {
        $filename=$package['filename']??null;if(!is_string($filename))throw new RuntimeException('invalid_manifest');
        if($this->platform==='openwrt'){
            if(!preg_match('/^nfqws2-native_'.self::NATIVE_CORE.'-(r?)([1-9][0-9]{0,9})_([a-z0-9][a-z0-9_+-]{0,99})\.(ipk|apk)$/D',$filename,$match)||($match[1]==='r')!==($match[4]==='apk'))throw new RuntimeException('invalid_manifest');$build=$match[2];
        }else{
            if(!preg_match('/^nfqws2-asus_'.self::CORE.'\+b([1-9][0-9]{0,9})_(?:aarch64-3\.10|armv7)\.ipk$/D',$filename,$match))throw new RuntimeException('invalid_manifest');$build=$match[1];
        }
        if((float)$build>2147483647||!is_int($package['size']??null)||$package['size']<1||$package['size']>33554432||!is_string($package['sha256']??null)||!preg_match('/^[a-f0-9]{64}$/D',$package['sha256']))throw new RuntimeException('invalid_manifest');
        $url=self::RELEASES.'build'.$build.'/'.$filename;
        for($path=$destination;$path!=='/'&&$path!=='.';$path=dirname($path))if(is_link($path))throw new RuntimeException('invalid_state');
        $parent=@lstat(dirname($destination));
        if(!$parent||($parent['mode']&0170000)!==0040000||($parent['mode']&0777)!==0700||$parent['uid']!==$this->owner)throw new RuntimeException('invalid_state');
        $mask=umask(0077);try{$out=@fopen($destination,'xb');}finally{umask($mask);}
        if(!$out)throw new RuntimeException('invalid_state');$created=fstat($out);$success=false;
        try{
            if(!chmod($destination,0600))throw new RuntimeException('invalid_state');
            $hash=hash_init('sha256');$count=0;
            $this->request($url,$package['size'],microtime(true)+min(180,$this->timeouts['download']),true,function($chunk)use($out,$hash,&$count){
                $count+=strlen($chunk);hash_update($hash,$chunk);if(fwrite($out,$chunk)!==strlen($chunk))throw new RuntimeException('insufficient_space');
            });
            if($count!==$package['size'])throw new RuntimeException('download_size');
            if(!hash_equals($package['sha256'],hash_final($hash)))throw new RuntimeException('download_hash');
            if(!fflush($out))throw new RuntimeException('insufficient_space');$success=true;
        }finally{
            fclose($out);
            if(!$success){clearstatcache(true,$destination);$stat=@lstat($destination);if($stat&&$stat['ino']===$created['ino']&&$stat['dev']===$created['dev']&&($stat['mode']&0170000)===0100000)@unlink($destination);}
        }
    }
}

// openwrt/install-plan.php sha256=d8a89a96e8773a0789d8db32e68310ecb95ac8b29a5f88719de3c31542ae48b4

/** Pure bootstrap policy. Only verified metadata may select a native action. */
final class NfqwsOpenWrtInstallPlan
{
    public static function select(string $json,string $signature,string $key,string $release,?array $own=null,?string $schema=null):array
    {
        $manifest=NfqwsOpenWrtPackageManifest::verify($json,$signature,$key,$schema);
        $firmware=NfqwsOpenWrtUpdateEnvironment::firmware($release);
        $candidate=NfqwsOpenWrtPackageManifest::select($manifest,$firmware);$action='install';
        if($own!==null){
            $keys=array_keys($own);sort($keys);
            if($keys!==['arch','build','format','name','state','version']||$own['name']!=='nfqws2-native'||$own['format']!==$firmware['format']||$own['arch']!==$firmware['arch']||
                !in_array($own['state'],['installed','unpacked','recovery_pending','broken'],true)||!is_int($own['build'])||$own['build']<1||$own['build']>2147483647||
                !is_string($own['version'])||!preg_match('/^(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-'.($firmware['format']==='apk'?'r':'').'[1-9][0-9]{0,9}$/D',$own['version']))throw new RuntimeException('unsupported_version');
            if($own['version']===$candidate['package_version']){
                if($own['build']>$manifest['build'])throw new RuntimeException('unsupported_version');
                $action=$own['state']==='installed'&&$own['build']===$manifest['build']?'current':
                    ($firmware['format']==='ipk'&&$own['state']==='unpacked'?'configure':'repair_required');
            }else{
                if(NfqwsOpenWrtPackageManifest::candidate($manifest,$firmware,$own['version'],$own['build'])===null)throw new RuntimeException('unsupported_version');$action='upgrade';
            }
        }
        return ['action'=>$action,'firmware'=>$firmware,'candidate'=>$candidate,'installed'=>$own];
    }
}

// openwrt/install-state.php sha256=28410f46e913d8e5c1282ee8b56ebafeb612bca79652545d702cfc209fcfc672

/** Native manager state is observed, never repaired by editing its database. */
final class NfqwsOpenWrtInstallState
{
    public static function parse(string $raw,array $environment,?string $profile):?array
    {
        $format=$environment['format']??null;NfqwsOpenWrtUpdateManager::database($raw,$format,true);$own=null;
        foreach(preg_split('/\n[ \t]*\n/',trim($raw))as $section){
            if($format==='ipk'){
                $v=AsusUpdatePackage::fields($section);if(($v['Package']??null)!=='nfqws2-native')continue;
                $status=preg_split('/\s+/',trim($v['Status']??''));$flags=explode(',',$status[1]??'');
                if(count($status)!==3||!in_array($status[0],['install','hold','deinstall','purge','unknown'],true)||array_diff($flags,['ok','user','prefer','hold'])||count($flags)!==count(array_unique($flags)))throw new RuntimeException('pending_packages');
                if(in_array($status[2],['not-installed','config-files'],true))continue;
                if(!in_array($status[2],['installed','unpacked'],true)||!in_array($status[0],['install','hold','deinstall'],true))throw new RuntimeException('pending_packages');
                $state=$status[2]==='unpacked'?'unpacked':($status[0]==='deinstall'?'recovery_pending':'installed');$version=$v['Version']??null;$arch=$v['Architecture']??null;
            }else{
                $v=[];foreach(explode("\n",$section)as $line){if(preg_match('/^([PVAf]):(.*)$/D',$line,$m)){if(isset($v[$m[1]]))throw new RuntimeException('pending_packages');$v[$m[1]]=$m[2];}}
                if(($v['P']??null)!=='nfqws2-native')continue;$version=$v['V']??null;$arch=$v['A']??null;$state=preg_match('/^[Sx]*$/D',$v['f']??'')?'installed':'broken';
            }
            if($own!==null)throw new RuntimeException('pending_packages');
            if(!is_string($version)||!preg_match('/^(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})-'.($format==='apk'?'r':'').'([1-9][0-9]{0,9})$/D',$version,$parts)||(float)$parts[1]>2147483647||$arch!==($environment['arch']??null))throw new RuntimeException('unsupported_version');
            $build=(int)$parts[1];$valid=false;
            if($profile!==null){try{$p=AsusSupportSchema::toArray(AsusSupportSchema::decode($profile,4096,'invalid_state'));
                $valid=is_array($p)&&($p['platform']??null)==='openwrt'&&($p['series']??null)===($environment['series']??null)&&($p['arch']??null)===$arch&&($p['format']??null)===$format&&($p['version']??null)===$version&&is_int($p['application_build']??null)&&$p['application_build']>=1&&$p['application_build']<=2147483647;
                if($valid)$build=$p['application_build'];
            }catch(Throwable $ignored){}}
            if(!$valid)$state='broken';
            $own=['name'=>'nfqws2-native','version'=>$version,'arch'=>$arch,'format'=>$format,'state'=>$state,'build'=>$build];
        }
        return $own;
    }
    public static function read(array $environment):?array
    {
        $raw=NfqwsOpenWrtUpdateManager::raw($environment);$profile=null;$path='/usr/share/nfqws2/platform.json';
        try{AsusUpdateStore::noLinks($path);$s=@lstat($path);$safe=$s&&is_file($path)&&$s['uid']===0&&$s['nlink']===1&&($s['mode']&0022)===0&&$s['size']<=4096;
            for($parent=dirname($path);$safe&&$parent!=='/';$parent=dirname($parent)){$d=@lstat($parent);$safe=$d&&is_dir($parent)&&$d['uid']===0&&($d['mode']&0022)===0;}
            if($safe){$p=file_get_contents($path);if(is_string($p))$profile=$p;}
        }catch(Throwable $ignored){}
        return self::parse($raw,$environment,$profile);
    }
}

// openwrt/install-prepare.php sha256=b8ca78c9f10f7705a9de5b7a653da06a781ff583d448688675e726fbe06b6bf1

/** Signed bootstrap preparation. No native install/configure or service command. */
final class NfqwsOpenWrtInstallPrepare
{
    public function __construct(private string $work,private ?AsusUpdateSource $source=null,private ?string $key=null,private ?string $schema=null){}
    private function directory():void
    {
        AsusUpdateStore::noLinks($this->work);$s=@lstat($this->work);
        if(!$s){$parent=@lstat(dirname($this->work));if(!$parent||!is_dir(dirname($this->work))||$parent['uid']!==0||($parent['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
            $mask=umask(0077);try{if(!mkdir($this->work,0700))throw new RuntimeException('storage_unavailable');}finally{umask($mask);}$s=lstat($this->work);}
        if(!is_dir($this->work)||$s['uid']!==0||($s['mode']&0777)!==0700)throw new RuntimeException('invalid_state');
    }
    private function schema():string
    {
        if($this->schema!==null)return $this->schema;
        if(!defined('NFQWS_NATIVE_INSTALL_SCHEMA'))throw new RuntimeException('invalid_state');
        $path=$this->work.'/native-schema.json';AsusUpdateStore::noLinks($path);$s=@lstat($path);
        if($s){if(!is_file($path)||$s['uid']!==0||$s['nlink']!==1||($s['mode']&0777)!==0600||$s['size']>16384||file_get_contents($path)!==NFQWS_NATIVE_INSTALL_SCHEMA)throw new RuntimeException('invalid_state');return $path;}
        $mask=umask(0077);try{$f=fopen($path,'xb');}finally{umask($mask);}if(!$f)throw new RuntimeException('storage_unavailable');
        try{if(fwrite($f,NFQWS_NATIVE_INSTALL_SCHEMA)!==strlen(NFQWS_NATIVE_INSTALL_SCHEMA)||!fflush($f))throw new RuntimeException('insufficient_space');}finally{fclose($f);}return $path;
    }
    public function run():array
    {
        if(!NfqwsPlatform::native())throw new RuntimeException('unsupported_abi');$this->directory();
        $store=new AsusUpdateStore('/tmp/nfqws2-native-state/updates');$lease=$store->lease('apply.lock',true);
        try{
            $store->reconcile(AsusUpdateStore::boot(),AsusUpdateStore::uptime());
            if($store->status()['active']!==null||NfqwsOpenWrtManualContext::activeManager()!==null)throw new RuntimeException('busy');
            $firmware=NfqwsOpenWrtUpdateEnvironment::firmware((string)file_get_contents('/etc/openwrt_release'));$own=NfqwsOpenWrtInstallState::read($firmware);
            $key=$this->key??(defined('NFQWS_NATIVE_INSTALL_KEY')?NFQWS_NATIVE_INSTALL_KEY:throw new RuntimeException('signature_unavailable'));
            $source=$this->source??new AsusGithubUpdateSource(0,'/etc/ssl/certs/ca-certificates.crt',['metadata'=>15,'download'=>180],'openwrt');
            $raw=$source->manifest();$plan=NfqwsOpenWrtInstallPlan::select($raw['json'],$raw['signature'],$key,(string)file_get_contents('/etc/openwrt_release'),$own,$this->schema());$plan+=['manifest'=>$raw['json'],'signature'=>$raw['signature']];
            if(in_array($plan['action'],['current','repair_required'],true))return $plan+['archive'=>null,'record'=>null,'keys'=>null,'missing'=>[]];
            $package=$plan['candidate']['package'];NfqwsOpenWrtUpdatePackage::space(disk_free_space(is_dir('/overlay')?'/overlay':'/'),disk_free_space($this->work),$package,0,1048576);
            $archive=$this->work.'/'.$package['filename'];$source->download($package,$archive);$keys=null;
            if($firmware['format']==='apk'){$keys=$this->work.'/keys';NfqwsOpenWrtApkTrust::stage($keys,$key);}
            $record=NfqwsOpenWrtUpdatePackage::inspect($archive,$plan['candidate'],$firmware,$keys);
            return $plan+['archive'=>$archive,'record'=>$record,'keys'=>$keys,'missing'=>NfqwsOpenWrtUpdateManager::missing($firmware,$record['depends'],true)];
        }finally{flock($lease,LOCK_UN);fclose($lease);}
    }
}

// openwrt/install-execute.php sha256=c3032f0536f74b87777c18e626b8fd124a7ca1aed4d7bc657a926400e8a8ac4a

/** Root bootstrap execution. Healthy upgrades use the installed sealed worker. */
final class NfqwsOpenWrtInstallExecute
{
    public static function prepared(string $work,?string $key=null,?string $schema=null):array
    {
        $local=new AsusUpdateStore($work);$raw=$local->readFile('plan.json',262144);
        if($raw===null)throw new RuntimeException('invalid_state');$saved=json_decode($raw,true,32,JSON_THROW_ON_ERROR);
        $firmware=NfqwsOpenWrtUpdateEnvironment::firmware((string)file_get_contents('/etc/openwrt_release'));
        $plan=NfqwsOpenWrtInstallPlan::select($saved['manifest']??'',$saved['signature']??'',$key??NFQWS_NATIVE_INSTALL_KEY,(string)file_get_contents('/etc/openwrt_release'),NfqwsOpenWrtInstallState::read($firmware),$schema??$work.'/work/native-schema.json');
        foreach(['action','firmware','candidate','installed']as $name)if(($saved[$name]??null)!==$plan[$name])throw new RuntimeException('stale_revision');
        if(!in_array($plan['action'],['current','repair_required'],true)){
            $path=$saved['archive']??null;if(!is_string($path)||$path!==$work.'/work/'.$plan['candidate']['package']['filename'])throw new RuntimeException('invalid_state');
            $record=NfqwsOpenWrtUpdatePackage::inspect($path,$plan['candidate'],$firmware,$saved['keys']??null);
            if($record!==($saved['record']??null))throw new RuntimeException('invalid_package');
            if(NfqwsOpenWrtUpdateManager::missing($firmware,$record['depends'],true))throw new RuntimeException('missing_dependencies');
        }
        return $saved;
    }
    /** No execution deadline: a native manager must finish its own transaction. */
    private static function manager(array $argv,string $log):int
    {
        $p=@proc_open($argv,[0=>['file','/dev/null','r'],1=>['file',$log,'a'],2=>['file',$log,'a']],$pipes,'/',
            ['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);
        if(!is_resource($p))throw new RuntimeException('launch_failed');return proc_close($p);
    }
    public static function direct(string $work,?string $key=null,?string $schema=null):array
    {
        $plan=self::prepared($work,$key,$schema);$action=$plan['action'];
        // An installed payload can own DNS/services. Its sealed coordinator is
        // mandatory; never fall through to a less protected raw upgrade.
        if(!in_array($action,['install','configure'],true))throw new RuntimeException('repair_required');
        $store=new AsusUpdateStore('/tmp/nfqws2-native-state/updates');$store->reconcile(AsusUpdateStore::boot(),AsusUpdateStore::uptime());
        if($store->status()['active']!==null||NfqwsOpenWrtManualContext::activeManager()!==null)throw new RuntimeException('busy');
        $environment=$plan['firmware'];$before=NfqwsOpenWrtUpdateManager::installed($environment,true);
        if($action==='configure')$argv=['/bin/opkg','configure','nfqws2-native'];
        else{
            $argv=NfqwsOpenWrtUpdateManager::argv($plan['archive'],$environment,$before,$plan['record'],$plan['keys'],true,true);
            $simulation=NfqwsPlatform::run($argv,30);
            if($simulation['status']!==0)throw new RuntimeException('dependency_change');
            NfqwsOpenWrtUpdateManager::plan(implode("\n",$simulation['output']),$environment['format'],$plan['record']);
            $argv=NfqwsOpenWrtUpdateManager::argv($plan['archive'],$environment,$before,$plan['record'],$plan['keys'],false,true);
        }
        if(self::manager($argv,$work.'/manager.log')!==0)throw new RuntimeException('install_failed');
        $own=NfqwsOpenWrtInstallState::read($environment);$after=NfqwsOpenWrtUpdateManager::installed($environment,true);
        if($after!==$before)throw new RuntimeException('dependency_change');
        if(($own['version']??null)!==$plan['candidate']['package_version']||($own['state']??null)!=='installed'||($own['build']??null)!==$plan['candidate']['build'])throw new RuntimeException('version_mismatch');
        return ['state'=>'installed','version'=>$own['version']];
    }
}

const NFQWS_NATIVE_INSTALL_KEY = '-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAnMAJvg+5yMc2KriuNn8l
RJjCmnlDDp/c5425Fo88zFoXLW7eVTc1gimagMxRqFjQG+nWo4eR+ZuzAJ/ZPSMk
oXRzgwTh7tPMYefdR57aSGcFMAUZ3juBBolw6NWTKe0y71BVr6rhGgE7YJOLjySX
yRMPlVTxkDimS8Gx3/pXRFc3ZwcFJB+wYcN066hfbepo8OA390UqozCHff+1ZeX6
6CjFbhwuOC7KkDkteARQI74vZq8e4fy+KXFd1ZdWYW+aScgCFLGsKfGqKZ+uTiaW
x8ByXkuhoeiyePo31nN1UUe7WZPWlDyuueTgXlkKMtat/i8wHes5bQM8561vBCoF
LH8DZZ50Unbtyrkt6ZI+QKEcPxz8J3SKGcI34on77+hs+N/+uGrH6BLp87WgezWZ
lCbneSVH54pjbJ7wKmBvpHjZfL9QyNZYppJf8WrIBJSAOL+bKzZi276r52WeOhZj
iZKKHyVyZmj1/SXQb2oQJcOAwqPYN0rQKqzxmOwAa8OhAgMBAAE=
-----END PUBLIC KEY-----
';
const NFQWS_NATIVE_INSTALL_SCHEMA = '{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "NFQWS2 signed native OpenWrt release v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "platform",
    "package",
    "core_version",
    "web_version",
    "build",
    "notes",
    "packages"
  ],
  "properties": {
    "schema_version": {
      "type": "integer",
      "const": 1
    },
    "platform": {
      "const": "openwrt"
    },
    "package": {
      "const": "nfqws2-native"
    },
    "core_version": {
      "type": "string",
      "pattern": "^(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})$",
      "maxLength": 32
    },
    "web_version": {
      "type": "string",
      "pattern": "^(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})$",
      "maxLength": 32
    },
    "build": {
      "type": "integer",
      "minimum": 1,
      "maximum": 2147483647
    },
    "notes": {
      "type": "string",
      "maxLength": 2000
    },
    "packages": {
      "type": "array",
      "minItems": 1,
      "maxItems": 64,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "series",
          "arch",
          "format",
          "version",
          "filename",
          "size",
          "sha256",
          "installed_size"
        ],
        "properties": {
          "series": {
            "enum": [
              "24.10",
              "25.12"
            ]
          },
          "arch": {
            "type": "string",
            "pattern": "^[a-z0-9][a-z0-9_+-]{0,99}$"
          },
          "format": {
            "enum": [
              "ipk",
              "apk"
            ]
          },
          "version": {
            "type": "string",
            "pattern": "^(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})-(?:r)?[1-9][0-9]{0,9}$",
            "maxLength": 64
          },
          "filename": {
            "type": "string",
            "pattern": "^nfqws2-native_[a-zA-Z0-9._+-]+\\\\.(?:ipk|apk)$",
            "maxLength": 200
          },
          "size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 33554432
          },
          "sha256": {
            "type": "string",
            "pattern": "^[a-f0-9]{64}$"
          },
          "installed_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 134217728
          }
        }
      }
    }
  }
}
';
const NFQWS_NATIVE_INSTALL_BRIDGE = '<?php
// Trusted bridge emitted by the installer; runs in a separate PHP process so
// the installed coordinator owns its own class definitions and sealed runtime.
if(isset($_SERVER[\'REQUEST_METHOD\'])||!preg_match(\'/^Uid:\\s+0\\s+0\\s+0\\s+0\\s*$/m\',(string)@file_get_contents(\'/proc/self/status\')))exit(2);
$args=$argv??[];array_shift($args);if(($args[0]??null)===\'--\')array_shift($args);if(count($args)!==1)exit(2);
umask(0077);require_once \'/usr/share/nfqws2-web/openwrt-update-worker.php\';require_once \'/usr/share/nfqws2-web/openwrt-update-launch.php\';require_once \'/usr/share/nfqws2-web/update-dispatch.php\';
const NFQWS_NATIVE_INSTALL_KEY = \'-----BEGIN PUBLIC KEY-----
MIIBojANBgkqhkiG9w0BAQEFAAOCAY8AMIIBigKCAYEAnMAJvg+5yMc2KriuNn8l
RJjCmnlDDp/c5425Fo88zFoXLW7eVTc1gimagMxRqFjQG+nWo4eR+ZuzAJ/ZPSMk
oXRzgwTh7tPMYefdR57aSGcFMAUZ3juBBolw6NWTKe0y71BVr6rhGgE7YJOLjySX
yRMPlVTxkDimS8Gx3/pXRFc3ZwcFJB+wYcN066hfbepo8OA390UqozCHff+1ZeX6
6CjFbhwuOC7KkDkteARQI74vZq8e4fy+KXFd1ZdWYW+aScgCFLGsKfGqKZ+uTiaW
x8ByXkuhoeiyePo31nN1UUe7WZPWlDyuueTgXlkKMtat/i8wHes5bQM8561vBCoF
LH8DZZ50Unbtyrkt6ZI+QKEcPxz8J3SKGcI34on77+hs+N/+uGrH6BLp87WgezWZ
lCbneSVH54pjbJ7wKmBvpHjZfL9QyNZYppJf8WrIBJSAOL+bKzZi276r52WeOhZj
iZKKHyVyZmj1/SXQb2oQJcOAwqPYN0rQKqzxmOwAa8OhAgMBAAE=
-----END PUBLIC KEY-----
\';
const NFQWS_NATIVE_INSTALL_SCHEMA = \'{
  "$schema": "https://json-schema.org/draft/2020-12/schema",
  "title": "NFQWS2 signed native OpenWrt release v1",
  "type": "object",
  "additionalProperties": false,
  "required": [
    "schema_version",
    "platform",
    "package",
    "core_version",
    "web_version",
    "build",
    "notes",
    "packages"
  ],
  "properties": {
    "schema_version": {
      "type": "integer",
      "const": 1
    },
    "platform": {
      "const": "openwrt"
    },
    "package": {
      "const": "nfqws2-native"
    },
    "core_version": {
      "type": "string",
      "pattern": "^(?:0|[1-9][0-9]{0,5})\\\\\\\\.(?:0|[1-9][0-9]{0,5})\\\\\\\\.(?:0|[1-9][0-9]{0,5})$",
      "maxLength": 32
    },
    "web_version": {
      "type": "string",
      "pattern": "^(?:0|[1-9][0-9]{0,5})\\\\\\\\.(?:0|[1-9][0-9]{0,5})\\\\\\\\.(?:0|[1-9][0-9]{0,5})$",
      "maxLength": 32
    },
    "build": {
      "type": "integer",
      "minimum": 1,
      "maximum": 2147483647
    },
    "notes": {
      "type": "string",
      "maxLength": 2000
    },
    "packages": {
      "type": "array",
      "minItems": 1,
      "maxItems": 64,
      "items": {
        "type": "object",
        "additionalProperties": false,
        "required": [
          "series",
          "arch",
          "format",
          "version",
          "filename",
          "size",
          "sha256",
          "installed_size"
        ],
        "properties": {
          "series": {
            "enum": [
              "24.10",
              "25.12"
            ]
          },
          "arch": {
            "type": "string",
            "pattern": "^[a-z0-9][a-z0-9_+-]{0,99}$"
          },
          "format": {
            "enum": [
              "ipk",
              "apk"
            ]
          },
          "version": {
            "type": "string",
            "pattern": "^(?:0|[1-9][0-9]{0,5})\\\\\\\\.(?:0|[1-9][0-9]{0,5})\\\\\\\\.(?:0|[1-9][0-9]{0,5})-(?:r)?[1-9][0-9]{0,9}$",
            "maxLength": 64
          },
          "filename": {
            "type": "string",
            "pattern": "^nfqws2-native_[a-zA-Z0-9._+-]+\\\\\\\\.(?:ipk|apk)$",
            "maxLength": 200
          },
          "size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 33554432
          },
          "sha256": {
            "type": "string",
            "pattern": "^[a-f0-9]{64}$"
          },
          "installed_size": {
            "type": "integer",
            "minimum": 1,
            "maximum": 134217728
          }
        }
      }
    }
  }
}
\';
const NFQWS_NATIVE_INSTALL_DISCOVERY = \'<?php
/** Fixed public discovery and release locations. Signed metadata remains the trust gate. */
final class AsusGithubUpdateSource implements AsusUpdateSource
{
    private const METADATA=\\\'https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/updates/v2/public.json\\\';
    private const NATIVE_METADATA=\\\'https://raw.githubusercontent.com/madworldpay/nfqws2-asus-community/main/updates/v2/openwrt/public.json\\\';
    private const RELEASES=\\\'https://github.com/madworldpay/nfqws2-asus-community/releases/download/\\\';
    private const ASSET_HOST=\\\'release-assets.githubusercontent.com\\\';
    private const HTTPS_PORT=443;
    private const ENVELOPE_LIMIT=46080;
    private const CORE=\\\'(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})-asus[1-9][0-9]{0,5}\\\';
    private const NATIVE_CORE=\\\'(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})\\\\.(?:0|[1-9][0-9]{0,5})\\\';

    public function __construct(private int $owner=0,private string $ca=\\\'/opt/etc/ssl/certs/ca-certificates.crt\\\',private array $timeouts=[\\\'metadata\\\'=>15,\\\'download\\\'=>180],private string $platform=\\\'asus-entware\\\')
    {if(!in_array($platform,[\\\'asus-entware\\\',\\\'openwrt\\\'],true))throw new RuntimeException(\\\'invalid_channel\\\');}

    private static function redirect(string $url): string
    {
        // GitHub asset URLs contain an expiring query, but their origin and path
        // are fixed. Never accept relative URLs, credentials or another service.
        $parts=parse_url($url);
        if(strlen($url)>8192||preg_match(\\\'/[^\\\\x21-\\\\x7e]|\\\\\\\\\\\\\\\\/\\\',$url)||!is_array($parts)||($parts[\\\'scheme\\\']??null)!==\\\'https\\\'||
            ($parts[\\\'host\\\']??null)!==self::ASSET_HOST||($parts[\\\'port\\\']??443)!==self::HTTPS_PORT||
            !preg_match(\\\'~^/github-production-release-asset/[A-Za-z0-9/_-]+$~D\\\',$parts[\\\'path\\\']??\\\'\\\'))throw new RuntimeException(\\\'download_redirect\\\');
        foreach([\\\'user\\\',\\\'pass\\\',\\\'fragment\\\'] as $key)if(array_key_exists($key,$parts))throw new RuntimeException(\\\'download_redirect\\\');
        return $url;
    }

    private function request(string $url,int $cap,float $deadline,bool $redirects=false,?callable $consume=null): string
    {
        if(!extension_loaded(\\\'openssl\\\')||!is_readable($this->ca))throw new RuntimeException(\\\'https_unavailable\\\');
        for($hop=0;;$hop++){
            $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException(\\\'timed_out\\\');
            // A fresh context per hop carries no credentials, cookies or headers
            // supplied by a server. TLS peer and hostname checks are mandatory.
            $context=stream_context_create([\\\'ssl\\\'=>[\\\'verify_peer\\\'=>true,\\\'verify_peer_name\\\'=>true,\\\'allow_self_signed\\\'=>false,\\\'cafile\\\'=>$this->ca],
                \\\'http\\\'=>[\\\'timeout\\\'=>min(15,$remaining),\\\'follow_location\\\'=>0,\\\'max_redirects\\\'=>0,\\\'ignore_errors\\\'=>true,\\\'protocol_version\\\'=>1.1,
                    \\\'header\\\'=>"Accept: application/octet-stream\\\\r\\\\nAccept-Encoding: identity\\\\r\\\\nConnection: close\\\\r\\\\nUser-Agent: NFQWS2-ASUS-Updater/1\\\\r\\\\n"]]);
            $f=@fopen($url,\\\'rb\\\',false,$context);if(!$f)throw new RuntimeException(\\\'download_failed\\\');
            try{
                if(microtime(true)>=$deadline)throw new RuntimeException(\\\'timed_out\\\');
                $status=0;$length=null;$encoding=null;$location=null;$headerBytes=0;
                foreach(stream_get_meta_data($f)[\\\'wrapper_data\\\']??[] as $header){
                    $headerBytes+=strlen($header);if($headerBytes>16384)throw new RuntimeException(\\\'download_failed\\\');
                    if(preg_match(\\\'~^HTTP/\\\\S+ ([0-9]{3})\\\\b~\\\',$header,$match)){$status=(int)$match[1];$length=null;$encoding=null;$location=null;}
                    elseif(stripos($header,\\\'Content-Length:\\\')===0){$value=trim(substr($header,15));if($length!==null||!preg_match(\\\'/^[0-9]{1,10}$/D\\\',$value)||(float)$value>$cap)throw new RuntimeException(\\\'download_size\\\');$length=(int)$value;}
                    elseif(stripos($header,\\\'Content-Encoding:\\\')===0){if($encoding!==null)throw new RuntimeException(\\\'download_size\\\');$encoding=strtolower(trim(substr($header,17)));}
                    elseif(stripos($header,\\\'Location:\\\')===0){if($location!==null)throw new RuntimeException(\\\'download_redirect\\\');$location=trim(substr($header,9));}
                }
                if(in_array($status,[301,302,303,307,308],true)){
                    if(!$redirects||$hop>=3||$location===null)throw new RuntimeException(\\\'download_redirect\\\');
                    $url=self::redirect($location);continue;
                }
                if($status!==200)throw new RuntimeException(\\\'download_failed\\\');
                if($encoding!==null&&$encoding!==\\\'identity\\\')throw new RuntimeException(\\\'download_size\\\');
                $count=0;$body=\\\'\\\';
                while(!feof($f)){
                    $remaining=$deadline-microtime(true);if($remaining<=0)throw new RuntimeException(\\\'timed_out\\\');
                    $timeout=min(5,$remaining);stream_set_timeout($f,(int)$timeout,(int)(($timeout-(int)$timeout)*1000000));
                    $chunk=@fread($f,min(16384,$cap+1-$count));
                    if(microtime(true)>=$deadline)throw new RuntimeException(\\\'timed_out\\\');
                    if($chunk===false||stream_get_meta_data($f)[\\\'timed_out\\\'])throw new RuntimeException(\\\'download_failed\\\');
                    $count+=strlen($chunk);if($count>$cap)throw new RuntimeException(\\\'download_size\\\');
                    if($consume!==null)$consume($chunk);else $body.=$chunk;
                    if($chunk===\\\'\\\')usleep(1000);
                }
                if($length!==null&&$count!==$length)throw new RuntimeException(\\\'download_size\\\');
                return $body;
            }finally{fclose($f);}
        }
    }

    public function manifest(): array
    {
        $raw=$this->request($this->platform===\\\'openwrt\\\'?self::NATIVE_METADATA:self::METADATA,self::ENVELOPE_LIMIT,microtime(true)+min(15,$this->timeouts[\\\'metadata\\\']));
        $envelope=AsusSupportSchema::decode($raw,self::ENVELOPE_LIMIT,\\\'invalid_manifest\\\');
        if(!is_object($envelope))throw new RuntimeException(\\\'invalid_manifest\\\');
        $keys=array_keys(get_object_vars($envelope));sort($keys);
        if($keys!==[\\\'manifest\\\',\\\'signature\\\']||!is_string($envelope->manifest)||!is_string($envelope->signature))throw new RuntimeException(\\\'invalid_manifest\\\');
        $json=base64_decode($envelope->manifest,true);
        if($json===false||$json===\\\'\\\'||strlen($json)>32768||base64_encode($json)!==$envelope->manifest)throw new RuntimeException(\\\'invalid_manifest\\\');
        $signature=base64_decode($envelope->signature,true);
        if(strlen($envelope->signature)>1024||$signature===false||strlen($signature)!==384||base64_encode($signature)!==$envelope->signature)throw new RuntimeException(\\\'invalid_signature\\\');
        return [\\\'json\\\'=>$json,\\\'signature\\\'=>$envelope->signature];
    }

    public function download(array $package,string $destination): void
    {
        $filename=$package[\\\'filename\\\']??null;if(!is_string($filename))throw new RuntimeException(\\\'invalid_manifest\\\');
        if($this->platform===\\\'openwrt\\\'){
            if(!preg_match(\\\'/^nfqws2-native_\\\'.self::NATIVE_CORE.\\\'-(r?)([1-9][0-9]{0,9})_([a-z0-9][a-z0-9_+-]{0,99})\\\\.(ipk|apk)$/D\\\',$filename,$match)||($match[1]===\\\'r\\\')!==($match[4]===\\\'apk\\\'))throw new RuntimeException(\\\'invalid_manifest\\\');$build=$match[2];
        }else{
            if(!preg_match(\\\'/^nfqws2-asus_\\\'.self::CORE.\\\'\\\\+b([1-9][0-9]{0,9})_(?:aarch64-3\\\\.10|armv7)\\\\.ipk$/D\\\',$filename,$match))throw new RuntimeException(\\\'invalid_manifest\\\');$build=$match[1];
        }
        if((float)$build>2147483647||!is_int($package[\\\'size\\\']??null)||$package[\\\'size\\\']<1||$package[\\\'size\\\']>33554432||!is_string($package[\\\'sha256\\\']??null)||!preg_match(\\\'/^[a-f0-9]{64}$/D\\\',$package[\\\'sha256\\\']))throw new RuntimeException(\\\'invalid_manifest\\\');
        $url=self::RELEASES.\\\'build\\\'.$build.\\\'/\\\'.$filename;
        for($path=$destination;$path!==\\\'/\\\'&&$path!==\\\'.\\\';$path=dirname($path))if(is_link($path))throw new RuntimeException(\\\'invalid_state\\\');
        $parent=@lstat(dirname($destination));
        if(!$parent||($parent[\\\'mode\\\']&0170000)!==0040000||($parent[\\\'mode\\\']&0777)!==0700||$parent[\\\'uid\\\']!==$this->owner)throw new RuntimeException(\\\'invalid_state\\\');
        $mask=umask(0077);try{$out=@fopen($destination,\\\'xb\\\');}finally{umask($mask);}
        if(!$out)throw new RuntimeException(\\\'invalid_state\\\');$created=fstat($out);$success=false;
        try{
            if(!chmod($destination,0600))throw new RuntimeException(\\\'invalid_state\\\');
            $hash=hash_init(\\\'sha256\\\');$count=0;
            $this->request($url,$package[\\\'size\\\'],microtime(true)+min(180,$this->timeouts[\\\'download\\\']),true,function($chunk)use($out,$hash,&$count){
                $count+=strlen($chunk);hash_update($hash,$chunk);if(fwrite($out,$chunk)!==strlen($chunk))throw new RuntimeException(\\\'insufficient_space\\\');
            });
            if($count!==$package[\\\'size\\\'])throw new RuntimeException(\\\'download_size\\\');
            if(!hash_equals($package[\\\'sha256\\\'],hash_final($hash)))throw new RuntimeException(\\\'download_hash\\\');
            if(!fflush($out))throw new RuntimeException(\\\'insufficient_space\\\');$success=true;
        }finally{
            fclose($out);
            if(!$success){clearstatcache(true,$destination);$stat=@lstat($destination);if($stat&&$stat[\\\'ino\\\']===$created[\\\'ino\\\']&&$stat[\\\'dev\\\']===$created[\\\'dev\\\']&&($stat[\\\'mode\\\']&0170000)===0100000)@unlink($destination);}
        }
    }
}
\';
/** Local verified bootstrap archive, consumed once by the installed coordinator. */
final class NfqwsOpenWrtInstallLocalSource implements AsusUpdateSource
{
    public function __construct(private array $plan){}
    public function manifest():array{return [\'json\'=>$this->plan[\'manifest\'],\'signature\'=>$this->plan[\'signature\']];}
    public function download(array $package,string $destination):void
    {
        if($package!==$this->plan[\'candidate\'][\'package\'])throw new RuntimeException(\'stale_revision\');$source=$this->plan[\'archive\'];
        AsusUpdateStore::noLinks($source);AsusUpdateStore::noLinks($destination);clearstatcache(true,$source);$s=@lstat($source);$parent=@lstat(dirname($destination));
        if(!$s||!is_file($source)||$s[\'uid\']!==0||$s[\'nlink\']!==1||($s[\'mode\']&0777)!==0600||file_exists($destination)||!$parent||!is_dir(dirname($destination))||$parent[\'uid\']!==0||($parent[\'mode\']&0777)!==0700)throw new RuntimeException(\'invalid_state\');
        if($s[\'size\']!==$package[\'size\']||!hash_equals($package[\'sha256\'],hash_file(\'sha256\',$source)))throw new RuntimeException(\'download_hash\');
        // Both directories belong to the root-private /tmp bootstrap/update
        // stores. Rename retains ownership/mode and does not duplicate RAM.
        if(!rename($source,$destination))throw new RuntimeException(\'download_failed\');
    }
}

/** Bootstrap-trusted key/discovery apply only to this transaction, never live files. */
final class NfqwsOpenWrtInstallTrust
{
    public static function stage(AsusUpdateStore $local,string $key,string $schema,string $discovery,string $installed=\'/usr/share/nfqws2-web\',int $owner=0):array
    {
        $local->directory(\'coordinator\');$app=$local->directory(\'coordinator/app\');$resources=$local->directory(\'coordinator/resources\');
        $files=glob($installed.\'/*.php\')?:[];
        if(count($files)<1||count($files)>128)throw new RuntimeException(\'runtime_limit\');
        $files[]=$installed.\'/platform-profile.json\';$bytes=0;
        foreach($files as $file){
            AsusUpdateStore::noLinks($file);clearstatcache(true,$file);$s=@lstat($file);
            if(!$s||!is_file($file)||$s[\'uid\']!==$owner||$s[\'nlink\']!==1||($s[\'mode\']&0022)!==0||$s[\'size\']>131072||($bytes+=$s[\'size\'])>16777216)throw new RuntimeException(\'invalid_state\');
            $raw=file_get_contents($file);if(!is_string($raw)||strlen($raw)!==$s[\'size\'])throw new RuntimeException(\'invalid_state\');
            $local->writeFile(\'coordinator/app/\'.basename($file),basename($file)===\'update-github.php\'?$discovery:$raw);
        }
        $local->writeFile(\'coordinator/resources/update-release-key.pem\',$key);
        $local->writeFile(\'coordinator/resources/openwrt-package-manifest.schema.json\',$schema);
        return [\'application\'=>$app,\'resources\'=>$resources];
    }
}


try{
    if(!NfqwsPlatform::native())throw new RuntimeException(\'unsupported_abi\');$local=new AsusUpdateStore($args[0]);
    $plan=json_decode($local->readFile(\'plan.json\',262144)??\'\',true,32,JSON_THROW_ON_ERROR);
    if(($plan[\'action\']??null)!==\'upgrade\'||($plan[\'installed\'][\'state\']??null)!==\'installed\')throw new RuntimeException(\'repair_required\');
    $path=$plan[\'archive\']??\'\';$expected=$args[0].\'/work/\'.($plan[\'candidate\'][\'package\'][\'filename\']??\'\');if($path!==$expected)throw new RuntimeException(\'invalid_state\');
    AsusUpdateStore::noLinks($path);$s=@lstat($path);if(!$s||!is_file($path)||$s[\'uid\']!==0||$s[\'nlink\']!==1||($s[\'mode\']&0777)!==0600)throw new RuntimeException(\'invalid_state\');
    $source=new NfqwsOpenWrtInstallLocalSource($plan);
    $trust=NfqwsOpenWrtInstallTrust::stage($local,NFQWS_NATIVE_INSTALL_KEY,NFQWS_NATIVE_INSTALL_SCHEMA,NFQWS_NATIVE_INSTALL_DISCOVERY);
    $store=new AsusUpdateStore();$prepare=new NfqwsOpenWrtUpdatePrepare($store,$source,[\'resources\'=>$trust[\'resources\']]);$fresh=$prepare->check(true);
    if($fresh[\'state\']!==\'available\'||$fresh[\'candidate\']!==$plan[\'candidate\'])throw new RuntimeException(\'stale_revision\');
    $lease=(new NfqwsOpenWrtUpdateGuard($store))->mutationLease();
    try{$job=$prepare->reserveCached($fresh[\'candidate\'][\'revision\'],bin2hex(random_bytes(16)));$store->claimPrepare($job[\'id\']);}finally{flock($lease,LOCK_UN);fclose($lease);}
    $job=$prepare->completePrepare($job[\'id\'],fn($id)=>NfqwsOpenWrtUpdateRuntime::stage($store->path(\'operations/\'.$id.\'/runtime\'),$trust));
    if($job[\'state\']!==\'prepared\')throw new RuntimeException($job[\'code\']??\'install_failed\');
    $job=(new AsusUpdateDispatch($store,$prepare))->apply($job[\'id\'],$job[\'revision\'],bin2hex(random_bytes(16)));
    if(!in_array($job[\'state\'],[\'applying\',\'succeeded\'],true))throw new RuntimeException($job[\'code\']??\'launch_failed\');
    $local->writeFile(\'result.json\',json_encode([\'state\'=>\'updating\',\'id\'=>$job[\'id\']],JSON_THROW_ON_ERROR));exit(0);
}catch(Throwable $e){file_put_contents(\'php://stderr\',"Native bootstrap coordinator: ".AsusUpdatePrepare::code($e)."\\n");exit(1);}
';
/** Closed local entrypoint; no source URL, key, package or command arguments. */
final class NfqwsOpenWrtInstallMain
{
    public static function run(array $args):int
    {
        if(isset($_SERVER['REQUEST_METHOD'])||!preg_match('/^Uid:\s+0\s+0\s+0\s+0\s*$/m',(string)@file_get_contents('/proc/self/status')))return 2;
        if(count($args)!==2||!in_array($args[0],['prepare','describe','run','status'],true))return 2;
        [$mode,$work]=$args;umask(0077);$local=new AsusUpdateStore($work);
        try{
            if($mode==='prepare'){$r=(new NfqwsOpenWrtInstallPrepare($work.'/work'))->run();$local->writeFile('plan.json',json_encode($r,JSON_THROW_ON_ERROR));return 0;}
            $r=json_decode($local->readFile('plan.json',262144)??'',true,32,JSON_THROW_ON_ERROR);
            if($mode==='describe'){
                if(!in_array($r['action']??null,['install','upgrade','configure','current','repair_required'],true))throw new RuntimeException('invalid_state');
                echo $r['action'],"\n",$r['candidate']['package_version'],"\n",implode(' ',$r['missing']),"\n";return 0;
            }
            if($mode==='status'){
                $result=json_decode($local->readFile('result.json')??'',true,32,JSON_THROW_ON_ERROR);
                if(($result['state']??null)==='updating'){
                    $updates=new AsusUpdateStore('/tmp/nfqws2-native-state/updates');$updates->reconcile(AsusUpdateStore::boot(),AsusUpdateStore::uptime());$job=$updates->readOperation($result['id']);
                    echo $job['state'],"\n",$job['code']??'',"\n";return 0;
                }echo $result['state']??'failed',"\n";return 0;
            }
            $r=NfqwsOpenWrtInstallExecute::prepared($work);
            if($r['action']==='upgrade'){
                if(($r['installed']['state']??null)!=='installed')throw new RuntimeException('repair_required');
                $local->writeFile('update.php',NFQWS_NATIVE_INSTALL_BRIDGE);
                $p=proc_open(['/usr/bin/php8-cgi','-d','register_argc_argv=1','-q','-f',$work.'/update.php','--',$work],[0=>['file','/dev/null','r'],1=>['file',$work.'/coordinator.log','a'],2=>['file',$work.'/coordinator.log','a']],$pipes,'/',['PATH'=>'/usr/sbin:/usr/bin:/sbin:/bin','LANG'=>'C','LC_ALL'=>'C','HOME'=>'/']);
                if(!is_resource($p)||proc_close($p)!==0)throw new RuntimeException('install_failed');
            }else{$result=NfqwsOpenWrtInstallExecute::direct($work);$local->writeFile('result.json',json_encode($result,JSON_THROW_ON_ERROR));}
            return 0;
        }catch(Throwable $e){file_put_contents('php://stderr',"NFQWS2 OpenWrt: ".$e->getMessage()."\n");return 1;}
    }
}
$args=$argv??[];array_shift($args);if(($args[0]??null)==='--')array_shift($args);exit(NfqwsOpenWrtInstallMain::run($args));

NFQWS_NATIVE_BUNDLE
}
nfqws_native_fail() { [ -z "$NFQWS_NATIVE_WORK" ] || NFQWS_NATIVE_KEEP=1; printf '\nОшибка OpenWrt: %s\n' "$*" >&2; exit 1; }
nfqws_native_cleanup() {
    if [ "$NFQWS_NATIVE_KEEP" = 0 ]; then rm -rf "$NFQWS_NATIVE_WORK";
    elif [ -n "$NFQWS_NATIVE_WORK" ]; then printf '\nЖурнал и пакет сохранены: %s\n' "$NFQWS_NATIVE_WORK" >&2; fi
}
nfqws_native_php() {
    /usr/bin/php8-cgi -d register_argc_argv=1 -q -f "$NFQWS_NATIVE_WORK/bundle.php" -- "$1" "$NFQWS_NATIVE_WORK"
}
nfqws_native_provision() {
    [ "$#" -gt 0 ] || return 0
    for nfqws_dep in "$@"; do
        case "$nfqws_dep" in ''|*[!a-z0-9+._-]*) nfqws_native_fail 'Некорректное имя зависимости.';; esac
    done
    nfqws_native_database_safe "$NFQWS_NATIVE_FORMAT" "$NFQWS_NATIVE_DB" || nfqws_native_fail 'Сначала завершите незавершённые операции менеджера пакетов OpenWrt.'
    # opkg configure also processes unrelated unpacked rows. Own incomplete
    # installations may be inspected, but never implicitly configured here.
    if [ "$NFQWS_NATIVE_FORMAT" = ipk ]; then
        if awk 'BEGIN{RS=""} /^Package: nfqws2-native\n/ && /Status: / && !/Status: (install|hold) (ok|user|prefer|hold)(,(ok|user|prefer|hold))* installed(\n|$)/ {found=1} END{exit !found}' "$NFQWS_NATIVE_DB"; then
            nfqws_native_fail 'Пакет NFQWS2 не настроен. Сначала завершите его настройку через opkg; зависимости автоматически не менялись.'
        fi
        nfqws_native_signed_opkg || nfqws_native_fail 'В opkg не включена проверка подписей репозиториев OpenWrt.'
        nfqws_native_background /bin/opkg update || nfqws_native_fail 'Не удалось обновить индексы OpenWrt. См. job.log в сохранённом каталоге.'
        /bin/opkg --noaction install "$@" > "$NFQWS_NATIVE_WORK/provision.plan" 2>&1 || nfqws_native_fail 'Зависимости недоступны для этой версии OpenWrt; проверьте её репозитории.'
        nfqws_native_install_only_plan ipk < "$NFQWS_NATIVE_WORK/provision.plan" || nfqws_native_fail 'Зависимости требуют изменения уже установленных системных пакетов. Обновите их штатным способом OpenWrt и повторите команду.'
        nfqws_native_background /bin/opkg install "$@" || nfqws_native_fail 'opkg не завершил установку зависимостей. Сохраните job.log.'
    else
        nfqws_native_background /usr/bin/apk update || nfqws_native_fail 'Не удалось обновить подписанные индексы OpenWrt.'
        /usr/bin/apk add --simulate "$@" > "$NFQWS_NATIVE_WORK/provision.plan" 2>&1 || nfqws_native_fail 'Зависимости недоступны для этой версии OpenWrt; проверьте её репозитории.'
        nfqws_native_install_only_plan apk < "$NFQWS_NATIVE_WORK/provision.plan" || nfqws_native_fail 'Зависимости требуют изменения уже установленных системных пакетов. Обновите их штатным способом OpenWrt и повторите команду.'
        nfqws_native_background /usr/bin/apk add "$@" || nfqws_native_fail 'apk не завершил установку зависимостей. Сохраните job.log.'
    fi
}
nfqws_native_main() {
    PATH=/usr/sbin:/usr/bin:/sbin:/bin
    export PATH
    unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
    umask 077
    nfqws_check=0
    case "${1-}" in '') ;; --check) nfqws_check=1;; --help|-h) printf 'Установка OpenWrt: sh install.sh; проверка без установки: sh install.sh --check\n'; return 0;; *) nfqws_native_fail 'Неизвестный параметр.';; esac
    [ "$#" -le 1 ] || nfqws_native_fail 'Передано слишком много параметров.'
    nfqws_uid=''
    while read -r nfqws_key nfqws_real nfqws_effective nfqws_rest; do [ "$nfqws_key" != Uid: ] || { nfqws_uid=$nfqws_effective; break; }; done < /proc/self/status
    [ "$nfqws_uid" = 0 ] || nfqws_native_fail 'Войдите в SSH роутера с правами root.'
    nfqws_release=$(sed -n "s/^DISTRIB_RELEASE='\([^']*\)'$/\1/p" /etc/openwrt_release)
    case "$nfqws_release" in 24.10|24.10.*) NFQWS_NATIVE_FORMAT=ipk; NFQWS_NATIVE_DB=/usr/lib/opkg/status;; 25.12|25.12.*) NFQWS_NATIVE_FORMAT=apk; NFQWS_NATIVE_DB=/lib/apk/db/installed;; *) nfqws_native_fail 'Для этой версии OpenWrt ещё нет пакета в каталоге.';; esac
    NFQWS_NATIVE_WORK=$(mktemp -d /tmp/nfqws2-native-install.XXXXXX) || nfqws_native_fail 'Нет места во временной памяти роутера.'
    NFQWS_NATIVE_KEEP=0
    trap nfqws_native_cleanup 0
    trap 'exit 130' INT
    trap 'exit 143' TERM HUP
    nfqws_native_emit_bundle > "$NFQWS_NATIVE_WORK/bundle.php"
    printf '%s\n' '{"schema_version":1,"platform":"openwrt"}' > "$NFQWS_NATIVE_WORK/platform-profile.json"
    nfqws_minimum=''
    for nfqws_dep in php8-cgi php8-mod-openssl php8-mod-curl ca-bundle; do
        if [ "$NFQWS_NATIVE_FORMAT" = ipk ]; then
            /bin/opkg status "$nfqws_dep" 2>/dev/null | grep -Eq '^Status: (install|hold) (ok|user|prefer|hold)(,(ok|user|prefer|hold))* installed$' || nfqws_minimum="$nfqws_minimum $nfqws_dep"
        else /usr/bin/apk info --exists "$nfqws_dep" >/dev/null 2>&1 || nfqws_minimum="$nfqws_minimum $nfqws_dep"; fi
    done
    command -v flock >/dev/null 2>&1 || nfqws_minimum="$nfqws_minimum flock"
    if [ -n "$nfqws_minimum" ]; then
        [ "$nfqws_check" = 0 ] || nfqws_native_fail "Для проверки нужны штатные компоненты OpenWrt:$nfqws_minimum. Режим --check ничего не устанавливает."
        printf 'Установка компонентов OpenWrt:%s\n' "$nfqws_minimum"
        nfqws_native_provision $nfqws_minimum
    fi
    [ -x /usr/bin/php8-cgi ] || nfqws_native_fail 'Штатный PHP8-CGI OpenWrt недоступен.'
    nfqws_native_bootstrap_lock || nfqws_native_fail 'Другой установщик NFQWS2 уже работает или его каталог блокировки недоступен.'
    printf 'OpenWrt %s · проверка подписанного выпуска…\n' "$nfqws_release"
    nfqws_native_php prepare || nfqws_native_fail 'Подготовка не завершена. Проверьте сообщение выше; настройки не менялись.'
    nfqws_description=$(nfqws_native_php describe) || nfqws_native_fail 'Не удалось прочитать проверенный пакет.'
    nfqws_action=$(printf '%s\n' "$nfqws_description" | sed -n 1p)
    nfqws_version=$(printf '%s\n' "$nfqws_description" | sed -n 2p)
    nfqws_missing=$(printf '%s\n' "$nfqws_description" | sed -n 3p)
    printf 'Пакет: nfqws2-native %s (%s).\n' "$nfqws_version" "$NFQWS_NATIVE_FORMAT"
    case "$nfqws_action" in current) printf 'Актуальная версия уже установлена.\n'; return 0;; repair_required) nfqws_native_fail 'Предыдущая установка не завершена. Сохраните вывод opkg status nfqws2-native или apk info -a nfqws2-native; принудительная переустановка не выполнялась.';; esac
    if [ "$nfqws_check" = 1 ]; then printf 'Подпись и пакет проверены. Установка не запускалась.\nНедостающие компоненты: %s\n' "${nfqws_missing:-нет}"; return 0; fi
    [ -z "$nfqws_missing" ] || nfqws_native_provision $nfqws_missing
    printf 'Установка с сохранением настроек…\n'
    nfqws_native_background /usr/bin/php8-cgi -d register_argc_argv=1 -q -f "$NFQWS_NATIVE_WORK/bundle.php" -- run "$NFQWS_NATIVE_WORK" || nfqws_native_fail 'Установка не завершена. Сохраните журналы в указанном каталоге.'
    while :; do
        nfqws_status=$(nfqws_native_php status) || nfqws_native_fail 'Не удалось получить результат обновления; проверьте панель перед повторной установкой.'
        case "$(printf '%s\n' "$nfqws_status" | sed -n 1p)" in
            installed|succeeded) break;;
            applying|preparing) NFQWS_NATIVE_KEEP=1; sleep 2;;
            *) NFQWS_NATIVE_KEEP=1; nfqws_native_fail "Обновление не завершено: $nfqws_status";;
        esac
    done
    NFQWS_NATIVE_KEEP=0
    printf 'Готово: nfqws2-native %s установлен.\n' "$nfqws_version"
    nfqws_ip=$(uci -q get network.lan.ipaddr)
    if ! printf '%s\n' "$nfqws_ip" | awk -F. 'NF!=4{exit 1} {for(i=1;i<=4;i++)if($i!~/^[0-9]+$/||$i>255)exit 1}'; then nfqws_ip=IP-роутера; fi
    printf 'Панель: http://%s:90\n' "$nfqws_ip"
    [ "$nfqws_action" != install ] || printf 'Обработка выключена. Выберите интерфейсы, устройства и стратегию в панели, затем включите NFQWS2.\n'
}
# END GENERATED NATIVE OPENWRT INSTALLER

# Keep the entry point last so an incomplete piped download cannot run a partial installer.
if [ -f /etc/openwrt_release ]; then nfqws_native_main "$@"; else main "$@"; fi
