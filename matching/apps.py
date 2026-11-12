from django.apps import AppConfig


class MatchingConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'matching'

    def ready(self):
        from .ml_model import initialise_model

        initialise_model()
