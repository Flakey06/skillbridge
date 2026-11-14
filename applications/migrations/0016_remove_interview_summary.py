from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("applications", "0015_interview_candidate_response")]
    operations = [migrations.RemoveField(model_name="interview", name="summary")]
