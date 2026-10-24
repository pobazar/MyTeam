import json
import logging
import sys
class SafeErrorHandler(logging.Handler):
    """Keep useful error classes/status without credentials, bodies, or exception messages."""
    def emit(self,record):
        exception=record.exc_info[0].__name__ if record.exc_info and record.exc_info[0] else None
        sys.stderr.write(json.dumps({'logger':record.name,'level':record.levelname,'exception':exception,'status':getattr(record,'status_code',None)})+'\n')
