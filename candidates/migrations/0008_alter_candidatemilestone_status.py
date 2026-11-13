from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("candidates", "0007_update_data_analytics_skills")]

    operations = [
        migrations.AlterField(
            model_name="candidatemilestone",
            name="status",
            field=models.CharField(
                choices=[
                    ("planned", "Planned"),
                    ("in_progress", "In progress"),
                    ("pending_verification", "Pending verification"),
                    ("rejected", "Rejected"),
                    ("completed", "Completed"),
                ],
                default="planned",
                max_length=20,
            ),
        ),
    ]
