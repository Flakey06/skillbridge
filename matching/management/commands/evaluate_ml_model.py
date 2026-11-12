from django.core.management.base import BaseCommand, CommandError

from matching.ml_model import evaluate_model


class Command(BaseCommand):
    help = "Evaluate the Logistic Regression suitability baseline on held-out CSV data."

    def add_arguments(self, parser):
        parser.add_argument("--path", help="Optional path to a labelled screening CSV.")

    def handle(self, *args, **options):
        try:
            results = evaluate_model(options.get("path"))
        except (OSError, ValueError) as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(f"Records: {results['records']}")
        self.stdout.write(f"Train/test split: {results['train_records']}/{results['test_records']}")
        self.stdout.write(f"Hire rate: {results['hire_rate']:.1%}")
        self.stdout.write(
            f"Majority baseline accuracy: {results['majority_baseline_accuracy']:.1%}"
        )
        for metric in ("accuracy", "balanced_accuracy", "precision", "recall", "roc_auc"):
            self.stdout.write(f"{metric.replace('_', ' ').title()}: {results[metric]:.1%}")
        self.stdout.write(
            "Excluded fields: " + ", ".join(results["excluded_fields"])
        )
