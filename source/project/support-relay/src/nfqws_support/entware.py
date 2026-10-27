"""Entware entrypoint: private JFFS credentials, separate UID, local lighttpd only."""
import ctypes
import ipaddress
import os
import resource

SERVICE_UID = 65123


def trusted_lighttpd(app):
    """mod_proxy appends the actual peer to XFF; ignore all client-supplied identity."""
    def boundary(env, start_response):
        forwarded = env.get('HTTP_X_FORWARDED_FOR', '')
        try:
            if env.get('REMOTE_ADDR') not in ('127.0.0.1', '::1') or not isinstance(forwarded, str) or len(forwarded) > 2048:
                raise ValueError()
            parts = forwarded.split(',')
            if not 1 <= len(parts) <= 32:
                raise ValueError()
            source = str(ipaddress.ip_address(parts[-1].strip()))
        except (ValueError, TypeError):
            body = b'{"state":"invalid","code":"invalid_request"}'
            start_response('400 Bad Request', [('Content-Type','application/json'),('Content-Length',str(len(body))),('Cache-Control','no-store')])
            return [body]
        local = dict(env)
        local['HTTP_X_REAL_IP'] = source
        return app(local, start_response)
    return boundary


def drop_identity():
    """Run during Gunicorn --preload, before opening the metadata database."""
    if os.geteuid() != 0:
        raise RuntimeError('Root preload is required to read the private credential')
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    if ctypes.CDLL(None, use_errno=True).prctl(38, 1, 0, 0, 0) != 0:
        raise RuntimeError('Cannot set no_new_privs')
    os.setgroups([])
    os.setgid(SERVICE_UID)
    os.setuid(SERVICE_UID)
    if os.geteuid() != SERVICE_UID or os.getegid() != SERVICE_UID or os.getgroups():
        raise RuntimeError('Cannot drop relay privileges')


def load_app():
    # Import while privileged; deployed source/vendor paths are root-owned 0755.
    from .app import create_app
    from .config import load_credentials
    from .smtp import SmtpSender
    from .store import RelayStore
    from .geo import GeoLookup
    config = load_credentials('/jffs/nfqws-support')
    drop_identity()
    store = RelayStore('/opt/var/lib/nfqws-support/metadata.sqlite', config.hmac_key,
                       source_limit=config.source_limit, global_limit=config.global_limit)
    store.cleanup()
    geo = GeoLookup(os.path.realpath('/opt/var/lib/nfqws-support-geo/dbip-city-lite.mmdb'))
    return trusted_lighttpd(create_app(config, store, SmtpSender(config), geo=geo))
