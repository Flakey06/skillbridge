from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0008_notification"),
    ]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="trial_started_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
