"""Safe request timings: aggregate counts/durations, never SQL, credentials or bodies."""
from time import perf_counter
from django.conf import settings
from django.db import connection

class TimingMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        started=perf_counter()
        metrics={'count':0,'seconds':0.0}
        def measure(execute,sql,params,many,context):
            before=perf_counter()
            try:return execute(sql,params,many,context)
            finally:
                metrics['count']+=1
                metrics['seconds']+=perf_counter()-before
        with connection.execute_wrapper(measure):response=self.get_response(request)
        total=(perf_counter()-started)*1000
        response['Server-Timing']=f'app;dur={total:.1f}, db;dur={metrics["seconds"]*1000:.1f};desc="{metrics["count"]} queries"'
        origin=request.headers.get('Origin','')
        if origin in settings.FRONTEND_ORIGINS:response['Timing-Allow-Origin']=origin
        return response
