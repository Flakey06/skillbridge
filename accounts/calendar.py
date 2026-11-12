import calendar
from collections import defaultdict
from datetime import datetime, timedelta

from django.utils import timezone


def _parse_date(value, fallback):
    try:
        return datetime.strptime(value, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return fallback


def _parse_month(value, fallback):
    try:
        return datetime.strptime(value, "%Y-%m").date().replace(day=1)
    except (TypeError, ValueError):
        return fallback.replace(day=1)


def build_month_calendar(interviews, month_value=None, selected_value=None):
    today = timezone.localdate()
    month_date = _parse_month(month_value, today)
    selected_date = _parse_date(selected_value, today)
    month = calendar.Calendar(firstweekday=6)
    events_by_date = defaultdict(list)

    for interview in interviews:
        event_date = timezone.localtime(interview.scheduled_start).date()
        events_by_date[event_date].append(interview)

    weeks = []
    for week in month.monthdatescalendar(month_date.year, month_date.month):
        weeks.append([
            {
                "date": day,
                "day": day.day,
                "in_month": day.month == month_date.month,
                "is_today": day == today,
                "is_selected": day == selected_date,
                "events": events_by_date.get(day, []),
            }
            for day in week
        ])

    previous_month = (month_date.replace(day=1) - timedelta(days=1)).replace(day=1)
    next_month = (month_date.replace(day=28) + timedelta(days=4)).replace(day=1)
    return {
        "month_label": month_date.strftime("%B %Y"),
        "month": month_date,
        "row_count": len(weeks),
        "previous_month": previous_month,
        "next_month": next_month,
        "selected_date": selected_date,
        "selected_events": events_by_date.get(selected_date, []),
        "weekdays": ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"],
        "weeks": weeks,
    }


def _calendar_text(value):
    """Escape an iCalendar TEXT property without allowing extra content lines."""
    return str(value).replace("\\", "\\\\").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n").replace(";", "\\;").replace(",", "\\,")


def _fold_calendar_line(line):
    """Fold at 75 UTF-8 octets, keeping complete Unicode characters."""
    parts = []
    current = ""
    for char in line:
        if len((current + char).encode("utf-8")) > 75:
            parts.append(current)
            current = " "
        current += char
    parts.append(current)
    return "\r\n".join(parts)


def calendar_download_or_reminder(request, interviews):
    """Export authorised events or detect changes on the next calendar visit.

    The caller must supply its permission-filtered interview queryset. Session
    fingerprints exclude timestamps generated during export and private notes.
    """
    from datetime import timezone as datetime_timezone
    from hashlib import sha256
    from django.http import HttpResponse

    def utc(value):
        return value.astimezone(datetime_timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    events = []
    for interview in interviews.order_by("pk"):
        job = interview.application.job
        lines = [
            "BEGIN:VEVENT",
            f"UID:skillbridge-interview-{interview.pk}@skillbridge.local",
            f"DTSTART:{utc(interview.scheduled_start)}",
            "SUMMARY:" + _calendar_text(f"Interview: {job.title} — {job.company.name}"),
            "DESCRIPTION:" + _calendar_text("Interview with " + job.company.name +
                ("\nMeeting: " + interview.meeting_url if interview.meeting_url else "") +
                ("\nBooking: " + interview.calcom_event_url if interview.calcom_event_url else "")),
        ]
        if interview.scheduled_end:
            lines.append(f"DTEND:{utc(interview.scheduled_end)}")
        lines.append("END:VEVENT")
        events.append(lines)
    fingerprint = sha256(repr(events).encode("utf-8")).hexdigest()
    key = f"calendar_seen_{request.user.pk}"
    previous = request.session.get(key)
    request.session[key] = fingerprint
    if request.method == "GET" and request.GET.get("download") == "ics":
        lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//SkillBridge//Interview Calendar//EN", "CALSCALE:GREGORIAN"]
        for event in events:
            lines.extend([event[0], f"DTSTAMP:{utc(timezone.now())}", *event[1:]])
        lines.append("END:VCALENDAR")
        content = "\r\n".join(_fold_calendar_line(line) for line in lines) + "\r\n"
        response = HttpResponse(content, content_type="text/calendar; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="skillbridge-interviews.ics"'
        response["Cache-Control"] = "private, no-store"
        return response, False
    return None, previous is not None and previous != fingerprint
