"""Read-only availability probe; no user files/buckets are created by MVP."""
import urllib.request
from django.conf import settings

def available():
    if not settings.SUPABASE_URL or not settings.SUPABASE_SERVICE_ROLE_KEY:return False
    request=urllib.request.Request(settings.SUPABASE_URL.rstrip('/')+'/storage/v1/bucket',headers={'apikey':settings.SUPABASE_SERVICE_ROLE_KEY,'Authorization':'Bearer '+settings.SUPABASE_SERVICE_ROLE_KEY})
    try:
        with urllib.request.urlopen(request,timeout=10) as response:return response.status==200
    except Exception:return False
