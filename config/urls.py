from django.urls import path
from myteam import views
urlpatterns = [path('rounds/<uuid:round_id>/enrollment/', views.enrollment), path('reconnect/', views.reconnect), path('profile/', views.profile), path('onboarding/', views.onboarding), path('login/', views.login), path('logout/', views.logout), path('telegram/webhook/', views.telegram_webhook), path('', views.home, name='home'), path('health/live', views.live)]
