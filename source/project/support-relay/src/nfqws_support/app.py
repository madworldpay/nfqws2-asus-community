"""WSGI boundary: closed inputs, trusted local proxy and safe outcome enums."""

import ipaddress
import json
import os
import re

from .bundle import validate_bundle
from .share import validate_share
from .geo import GeoLookup
from .config import load_credentials
from .smtp import SmtpSender
from .store import RelayStore, valid_submission_id
from .validation import InvalidReport, MAX_BYTES, validate_report

STATUS = {'accepted':200, 'failed_safe':503, 'unknown':503, 'busy':409, 'limited':429, 'invalid':422}
CODE = {'accepted':'smtp_accepted', 'failed_safe':'transport_failed', 'unknown':'delivery_unknown',
        'busy':'busy', 'limited':'rate_limited', 'invalid':'invalid_request'}


def create_app(config, store, sender,geo=None):
    geo=geo if geo is not None else GeoLookup()
    def app(env, start_response):
        def respond(state, sid='', code=None, retry=0):
            status = STATUS[state]
            if code == 'id_conflict': status = 409
            payload = json.dumps({'state':state,'submission_id':sid,'code':code or CODE[state]}, separators=(',',':')).encode('ascii')
            headers = [('Content-Type','application/json'),('Content-Length',str(len(payload))),('Cache-Control','no-store')]
            if retry: headers.append(('Retry-After',str(retry)))
            start_response(f'{status} Result', headers)
            return [payload]
        if env.get('REQUEST_METHOD') == 'GET' and env.get('PATH_INFO') == '/health':
            payload = b'{"state":"ready"}'
            start_response('200 OK',[('Content-Type','application/json'),('Content-Length',str(len(payload))),('Cache-Control','no-store'),('X-NFQWS2-Sharing','4')])
            return [payload]
        if env.get('PATH_INFO')=='/nfqws-support/v3/location':
            result={'available':False}
            try:
                if env.get('REQUEST_METHOD')!='GET' or env.get('REMOTE_ADDR') not in ('127.0.0.1','::1') or env.get('QUERY_STRING') or env.get('CONTENT_LENGTH','') not in ('','0') or env.get('HTTP_TRANSFER_ENCODING') or env.get('CONTENT_ENCODING') or env.get('HTTP_CONTENT_ENCODING'):raise ValueError()
                source=str(ipaddress.ip_address(env.get('HTTP_X_REAL_IP','')))
                result=geo.lookup(source)
            except (ValueError,TypeError):pass
            payload=json.dumps(result,ensure_ascii=False,separators=(',',':')).encode('utf-8')
            start_response('200 OK',[('Content-Type','application/json'),('Content-Length',str(len(payload))),('Cache-Control','no-store')])
            return [payload]
        sid = env.get('HTTP_X_NFQWS2_SUBMISSION_ID','')
        safe_id = sid if valid_submission_id(sid) else ''
        try:
            v2=env.get('PATH_INFO')=='/nfqws-support/v2/reports'
            v3=env.get('PATH_INFO')=='/nfqws-support/v3/reports'
            v4=env.get('PATH_INFO')=='/nfqws-support/v4/reports'
            if env.get('REQUEST_METHOD') != 'POST' or env.get('PATH_INFO') not in ('/nfqws-support/v1/reports','/nfqws-support/v2/reports','/nfqws-support/v3/reports','/nfqws-support/v4/reports'): raise InvalidReport()
            if (v3 or v4) and env.get('QUERY_STRING'):raise InvalidReport()
            if env.get('REMOTE_ADDR') not in ('127.0.0.1','::1'): raise InvalidReport()
            source = str(ipaddress.ip_address(env.get('HTTP_X_REAL_IP','')))
            if not safe_id or env.get('CONTENT_ENCODING') or env.get('HTTP_CONTENT_ENCODING') or env.get('HTTP_TRANSFER_ENCODING'): raise InvalidReport()
            if env.get('CONTENT_TYPE','').lower() not in ('application/json','application/json; charset=utf-8'): raise InvalidReport()
            length = env.get('CONTENT_LENGTH','')
            if not re.fullmatch('[0-9]{1,7}', length) or not 0 < int(length) <= (4194304 if v4 else (2097152 if v2 or v3 else MAX_BYTES)): raise InvalidReport()
            raw = env['wsgi.input'].read(int(length))
            if len(raw) != int(length): raise InvalidReport()
            filename = env.get('HTTP_X_NFQWS2_FILENAME','')
            if (v2 or v3 or v4) and filename: raise InvalidReport()
            info = validate_share(raw,sid) if v3 or v4 else (validate_bundle(raw,sid) if v2 else validate_report(raw,filename))
            if (v3 and info.version!=3) or (v4 and info.version!=4):raise InvalidReport()
        except (InvalidReport, ValueError, KeyError, OSError, TypeError):
            return respond('invalid',safe_id)
        try:
            reservation = store.reserve(sid,info.sha256,source)
        except Exception:
            return respond('busy',sid,retry=30)
        if reservation.decision == 'id_conflict': return respond('invalid',sid,'id_conflict')
        if reservation.decision != 'reserved': return respond(reservation.decision,sid,retry=reservation.retry_after)
        # Any unexpected exception after handing data to a sender is ambiguous.
        try:
            state = (sender.send_bundle(info) if v2 or v3 or v4 else sender.send(raw,filename,info)).state
            if state not in ('accepted','failed_safe','unknown'): state = 'unknown'
        except Exception:
            state = 'unknown'
        try:
            store.finish(sid,state)
        except Exception:
            state = 'unknown'
        return respond(state,sid)
    return app


def load_app():
    config = load_credentials(os.environ.get('CREDENTIALS_DIRECTORY',''))
    store = RelayStore('/var/lib/nfqws-support/metadata.sqlite',config.hmac_key,
                       source_limit=config.source_limit,global_limit=config.global_limit)
    return create_app(config,store,SmtpSender(config))
