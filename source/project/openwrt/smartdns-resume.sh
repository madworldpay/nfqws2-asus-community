#!/bin/sh
# Boot-only retries of fresh validation after native network/DNS regeneration.
# Never replay a failed switch, relax a conflict or reuse an obsolete preview.
set -f
umask 077
PATH=/usr/sbin:/usr/bin:/sbin:/bin
export PATH
unset REQUEST_METHOD QUERY_STRING CONTENT_TYPE CONTENT_LENGTH SCRIPT_FILENAME
nfqws_resume_attempt=0
while :; do
    nfqws_resume_attempt=$((nfqws_resume_attempt+1))
    nfqws_resume_result=$(/usr/bin/php-cgi -d register_argc_argv=1 -q -f /usr/lib/nfqws2/smartdns/control.php -- resume)
    nfqws_resume_rc=$?
    nfqws_resume_state=$(/usr/bin/jsonfilter -s "$nfqws_resume_result" -e '@.state' 2>/dev/null)
    nfqws_resume_code=$(/usr/bin/jsonfilter -s "$nfqws_resume_result" -e '@.code' 2>/dev/null)
    nfqws_resume_error=$(/usr/bin/jsonfilter -s "$nfqws_resume_result" -e '@.error' 2>/dev/null)
    case "$nfqws_resume_error" in
        stale_baseline|baseline_unavailable)
            nfqws_resume_state=failed
            nfqws_resume_code=$nfqws_resume_error;;
    esac
    # An install without consent is silent and inert.
    if [ -z "$nfqws_resume_result" ] && [ "$nfqws_resume_rc" = 0 ]; then exit 0; fi
    case "$nfqws_resume_state:$nfqws_resume_code" in
        confirmed:*|idle:*)
            printf '%s\n' "$nfqws_resume_result"
            exit "$nfqws_resume_rc";;
        failed:stale_baseline|rolled_back:stale_baseline|failed:baseline_unavailable)
            # Each invocation checks saved consent/engine again and obtains a
            # new preview against current firmware files. No concurrent edit
            # is adopted by an already-prepared transaction.
            if [ "$nfqws_resume_attempt" -lt 4 ]; then
                /bin/busybox sleep "$((nfqws_resume_attempt*2))"
                continue
            fi;;
    esac
    printf '%s\n' "$nfqws_resume_result"
    exit 1
done
