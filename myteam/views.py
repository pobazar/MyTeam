from django.http import HttpResponse, JsonResponse
def public_settings(request):
    return {}
def home(request):
    from django.shortcuts import render
    return render(request, 'myteam/home.html')
def live(request):
    return JsonResponse({'status': 'ok'})
