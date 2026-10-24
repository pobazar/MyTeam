from django.apps import AppConfig
class MyteamConfig(AppConfig):
    name='myteam'
    default_auto_field='django.db.models.BigAutoField'
    def ready(self):
        from . import analytics
