from django.core.management.base import BaseCommand, CommandError

from matching.ml_model import _model_path, train_and_persist_model


class Command(BaseCommand):
    help = "Train the suitability model and persist it as a Joblib artifact."

    def handle(self, *args, **options):
        try:
            train_and_persist_model()
        except (OSError, ValueError, ImportError) as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(f"Model saved to {_model_path()}"))
