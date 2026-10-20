# Input is a bounded, NUL-free private copy; caller verifies it before rename.
# expected is the immutable owned block, including its leading/trailing LF.
# ending is 1 only if the current hook's last byte is LF.
BEGIN {
    if ((getline line < expected) != 1 || line != "") { bad=1;exit 2 }
    n=0
    while ((status=getline line < expected) > 0) block[++n]=line
    close(expected)
    if (status<0 || n<2 || block[1]!="# BEGIN NFQWS2 SMARTDNS MANAGED" || block[n]!="# END NFQWS2 SMARTDNS MANAGED" || (ending!="0" && ending!="1")) { bad=1;exit 2 }
}
{
    if (inside) {
        if ($0!=block[++at]) { bad=1;exit 2 }
        if (at==n) { inside=0;lastBlock=NR }
        next
    }
    if ($0==block[1]) {
        if (seen || !held) { bad=1;exit 2 }
        # The previous record's LF belongs to the owned block. Holding one
        # record handles both an empty boundary and an original missing LF.
        printf "%s",previous
        held=0;seen=1;inside=1;at=1
        next
    }
    if (index($0,"NFQWS2 SMARTDNS MANAGED")) { bad=1;exit 2 }
    if (held) printf "%s\n",previous
    previous=$0;held=1
}
END {
    if (bad || inside || !seen || (NR==lastBlock && ending!="1")) exit 2
    if (held) {
        printf "%s",previous
        if (ending=="1") printf "\n"
    }
}
