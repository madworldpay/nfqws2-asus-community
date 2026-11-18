# Supported dnsmasq data includes only. Shell verifies every source before use.
function trim(s) { sub(/^[ \t\r]+/,"",s);sub(/[ \t\r]+$/,"",s);return s }
function literal(line, end,suffix,out) {
    sub(/^[^=]*=[ \t]*/,"",line)
    if (index(line,"\\")) return ""
    if (substr(line,1,1)=="\"") {
        end=index(substr(line,2),"\"")+1;if (end==1) return ""
        out=substr(line,2,end-2);suffix=substr(line,end+1)
        if (suffix!~/^[ \t\r]*$/ && suffix!~/^[ \t\r]+#/) return ""
    } else {
        out=line;sub(/[ \t\r]+#.*/,"",out);sub(/[ \t\r]+$/,"",out)
        if (index(out,"\"")) return ""
    }
    if (length(out)>1024 || out!~/^\/[A-Za-z0-9_.+\/ -]+$/ || out~/\/\/|\/(\.\.?)(\/|$)/) return ""
    return out
}
function emit(line) {
    written+=length(line)+1
    if (written>262144) {bad=1;return 0}
    print line;return 1
}
function service_target(value, ip,octets,n,i) {
    if (value!~/^\/[A-Za-z0-9_-]+\/[0-9.]+$/) return ""
    ip=value;sub(/^.*\//,"",ip);n=split(ip,octets,".");if (n!=4) return ""
    for (i=1;i<=4;i++) if (octets[i]!~/^[0-9]+$/ || octets[i]>255 || (length(octets[i])>1 && substr(octets[i],1,1)=="0")) return ""
    if (octets[1]==127 || ip=="0.0.0.0") return ""
    return ip
}
function defaults(path,writeRoutes, line,status,count,total,value,target,globals,routes,routeCount,i) {
    if (path!=servers1 && path!=servers2) return 0
    while ((status=getline line < path)>0) {
        if (++count>4096 || (total+=length(line)+1)>262144) {close(path);return 0}
        line=trim(line)
        if (line=="" || line~/^#/) continue
        value=line;sub(/^server[ \t]*=[ \t]*/,"",value)
        if (line~/^server[ \t]*=[ \t]*\//) {
            if (service_target(value)=="") {close(path);return 0}
            routes[++routeCount]=value
        } else {
            if (line!~/^server[ \t]*=[ \t]*[^\/ \t#][^\/ \t]*$/) {close(path);return 0}
            globals[value]=1
        }
    }
    close(path);if (status!=0) return 0
    for (i=1;i<=routeCount;i++) {
        target=service_target(routes[i]);if (!globals[target]) return 0
        approved_service[routes[i]]=1
        if (writeRoutes && !emit("server="routes[i])) return 0
    }
    return 1
}
function configuration(path,depth, line,status,count,total,ok) {
    if (!allowed[path] || active[path] || depth>8) return 0
    active[path]=1;ok=1
    while ((status=getline line < path)>0) {
        count++
        if ((total+=length(line)+1)>262144 || !directive(line,depth)) {ok=0;break}
    }
    if (ok && count==0 && !directive("",depth)) ok=0
    close(path);delete active[path];return ok && status==0
}
function directive(raw,depth, line,path,value) {
    # Bound all repeated traversal, including include edges and filtered data.
    if (mode!="includes" && (visited+=length(raw)+1)>1048576) return 0
    line=trim(raw)
    if (line~/^(conf-dir|conf-script)[ \t]*(=|$)/) return 0
    if (line~/^conf-file[ \t]*(=|$)/) {
        if (line!~/^conf-file[ \t]*=/) return 0
        path=literal(line);if (path=="") return 0
        if (mode=="includes") {print path;return 1}
        return configuration(path,depth+1)
    }
    if (mode=="includes") return 1
    # The PHP preview bounds flattened content before removing upstreams.
    if ((expanded+=length(raw)+1)>262144) return 0
    if (line~/^server[ \t]*=[ \t]*\//) {
        value=line;sub(/^server[ \t]*=[ \t]*/,"",value)
        # One current formatting pass only; this is data, never future readiness.
        if (!service_loaded) {service_loaded=1;if (!defaults(servers1,0)) return 0}
        return approved_service[value] && emit(raw)
    }
    if (line~/^rev-server[ \t]*(=|$)/) return 0
    if (line~/^servers-file[ \t]*=/) {
        path=line;sub(/^servers-file[ \t]*=[ \t]*/,"",path)
        return defaults(trim(path),1)
    }
    if (line~/^(server|resolv-file)[ \t]*=/ || line~/^(no-resolv|all-servers|strict-order)$/) return 1
    return emit(raw)
}
BEGIN {
    if (mode=="render") {
        n=split(configs,paths,"\n");for (i=1;i<=n;i++) if (paths[i]!="") allowed[paths[i]]=1
        if (!configuration(main,1)) bad=1
        exit bad?2:0
    }
}
{if (!directive($0,1)) {bad=1;exit 2}}
END {
    if (bad) exit 2
    if (mode!="includes" && (!emit("no-resolv") || !emit("server=127.0.0.1#6054"))) exit 2
}
