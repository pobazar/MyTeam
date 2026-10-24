from django.http import HttpResponse, JsonResponse
def public_settings(request):
    return {}
def home(request):
    return HttpResponse('МАЙТИМ')
def live(request):
    return JsonResponse({'status': 'ok'})
