from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("accounts", "0014_securityquestionanswer")]

    operations = [
        migrations.AddField(
            model_name="userprofile",
            name="password_hint",
            field=models.CharField(blank=True, max_length=160),
        ),
        migrations.AlterField(
            model_name="securityquestionanswer",
            name="question",
            field=models.CharField(
                choices=[
                    ("favorite_color", "What is your favorite color?"),
                    ("childhood_nickname", "What was your childhood nickname?"),
                    ("first_school", "What was the name of your first school?"),
                    ("favorite_teacher", "What was the surname of your favorite teacher?"),
                    ("memorable_city", "In which city did you take a memorable trip?"),
                    ("favorite_book", "What is the title of a favorite childhood book?"),
                    ("first_pet", "What was the name of your first pet?"),
                    ("childhood_street", "What street did you grow up on?"),
                    ("childhood_friend", "What was the first name of your childhood best friend?"),
                    ("first_job", "What was your first job?"),
                ],
                max_length=40,
            ),
        ),
    ]
