from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("jobs", "0002_job_salary_currency_job_salary_period_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="job",
            name="skill_weights",
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name="job",
            name="evidence_weights",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
