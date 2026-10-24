from django.urls import path
from myteam import views
urlpatterns = [path('', views.home, name='home'), path('health/live', views.live)]
