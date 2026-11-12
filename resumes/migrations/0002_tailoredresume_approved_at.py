from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("resumes", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="tailoredresume",
            name="approved_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
