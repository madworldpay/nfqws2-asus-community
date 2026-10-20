# Native counterpart of AsusSmartDnsHook::forwarding. Caller discards all
# output on failure and only installs a successful, syntax-checked copy.
function trim(s) { sub(/^[ \t\r]+/,"",s);sub(/[ \t\r]+$/,"",s);return s }
function defaults(path, line,status) {
    if (path!=servers1 && path!=servers2) return 0
    while ((status=getline line < path)>0) {
        line=trim(line)
        if (line=="" || line~/^#/) continue
        if (line!~/^server[ \t]*=[ \t]*[^\/ \t#][^\/ \t]*$/) { close(path);return 0 }
    }
    close(path);return status==0
}
{
    directive=trim($0)
    if (directive~/^(conf-file|conf-dir|conf-script)[ \t]*(=|$)/ || directive~/^server[ \t]*=[ \t]*\//) { bad=1;exit 2 }
    if (directive~/^servers-file[ \t]*=/) {
        path=directive;sub(/^servers-file[ \t]*=[ \t]*/,"",path)
        if (!defaults(trim(path))) { bad=1;exit 2 }
        next
    }
    if (directive~/^(server|resolv-file)[ \t]*=/ || directive~/^(no-resolv|all-servers|strict-order)$/) next
    print $0
}
END { if (bad) exit 2;print "no-resolv\nserver=127.0.0.1#6054" }
