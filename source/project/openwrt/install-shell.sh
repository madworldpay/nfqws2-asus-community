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
            /^Downloading https?:\/\/[^ \t\r]+$/ {next}
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
