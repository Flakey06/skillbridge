from django.db import migrations


def _percentage(value, maximum):
    if not maximum:
        return 0
    return round(float(value or 0) * 100 / float(maximum))


def separate_scores(apps, schema_editor):
    JobApplication = apps.get_model("applications", "JobApplication")
    for application in JobApplication.objects.iterator():
        breakdown = dict(application.match_breakdown or {})
        skill = dict(breakdown.get("skill_match") or {})
        evidence = dict(breakdown.get("evidence_match") or {})
        changed = False

        for component in (skill, evidence):
            old_max = component.get("max")
            if old_max and old_max != 100:
                component["earned"] = _percentage(component.get("earned"), old_max)
                component["max"] = 100
                details = dict(component.get("details") or {})
                for label, detail_value in details.items():
                    detail = dict(detail_value or {})
                    detail["earned"] = _percentage(detail.get("earned"), old_max)
                    detail["max"] = _percentage(detail.get("max"), old_max)
                    details[label] = detail
                component["details"] = details
                changed = True

        if skill:
            breakdown["skill_match"] = skill
            application.match_score = skill.get("earned", application.match_score)
            score = application.match_score or 0
            application.match_assessment = (
                "Strong fit" if score >= 80 else
                "Good foundation" if score >= 60 else
                "Developing fit" if score >= 40 else
                "Early-stage fit"
            )
        if evidence:
            breakdown["evidence_match"] = evidence
        if changed:
            application.match_breakdown = breakdown
            application.save(update_fields=["match_score", "match_breakdown", "match_assessment"])


class Migration(migrations.Migration):
    dependencies = [
        ("applications", "0012_interview_response_status"),
    ]

    operations = [
        migrations.RunPython(separate_scores, migrations.RunPython.noop),
    ]
