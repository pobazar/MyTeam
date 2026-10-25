from django.urls import path
from myteam import views,pages,scheduler,api
urlpatterns = [
    path('api/login/',api.login),path('api/login/status/',api.login_status),path('api/logout/',api.logout),
    path('api/onboarding/',api.onboarding),path('api/profile/',api.profile),path('api/activities/',api.activities),
    path('api/history/',api.history),path('api/rounds/<uuid:round_id>/enrollment/',api.enrollment),
    path('api/meetings/<uuid:meeting_id>/feedback/',api.feedback),
path('internal/schedule/',scheduler.run), path('bridge/bootstrap/', pages.bootstrap), path('login/status/',views.login_status), path('health/ready', views.ready), path('meetings/<uuid:meeting_id>/feedback/', views.feedback_view), path('meetings/<uuid:meeting_id>/', views.meeting_detail), path('history/', views.history), path('rounds/<uuid:round_id>/enrollment/', views.enrollment), path('reconnect/', views.reconnect), path('profile/', views.profile), path('onboarding/', views.onboarding), path('login/', views.login), path('logout/', views.logout), path('telegram/webhook/', views.telegram_webhook), path('', views.home, name='home'), path('health/live', views.live)]
