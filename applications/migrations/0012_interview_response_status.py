from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0011_interview_attendance_status_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="interview",
            name="response_status",
            field=models.CharField(
                choices=[
                    ("awaiting", "Awaiting applicant response"),
                    ("accepted", "Accepted by applicant"),
                    ("reschedule_requested", "Reschedule requested"),
                ],
                default="awaiting",
                max_length=24,
            ),
        ),
    ]
