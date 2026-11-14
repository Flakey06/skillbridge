from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("applications", "0014_interviewreminder")]

    operations = [
        migrations.AddField(
            model_name="interview",
            name="candidate_response",
            field=models.CharField(
                choices=[
                    ("pending", "Awaiting candidate response"),
                    ("accepted", "Accepted by candidate"),
                ],
                default="pending",
                max_length=20,
            ),
        ),
    ]
