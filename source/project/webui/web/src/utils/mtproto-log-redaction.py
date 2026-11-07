# Install before importing upstream code, including before it configures logging.
import logging
import traceback

_previous_record_factory = logging.getLogRecordFactory()


def _secret_safe_record(*args, **kwargs):
    record = _previous_record_factory(*args, **kwargs)
    try:
        message = record.getMessage()
    except Exception:
        message = '[unavailable log message]'
    record.msg = message.replace(secret, '[redacted]') if secret else message
    record.args = ()
    # Format exception chains before a handler can append an unredacted value.
    if record.exc_info:
        try:
            record.exc_text = ''.join(traceback.format_exception(*record.exc_info)).rstrip()
        except Exception:
            record.exc_text = '[unavailable exception]'
        record.exc_info = None
    for field in ('exc_text', 'stack_info'):
        value = getattr(record, field, None)
        if value and secret:
            setattr(record, field, value.replace(secret, '[redacted]'))
    return record


logging.setLogRecordFactory(_secret_safe_record)
