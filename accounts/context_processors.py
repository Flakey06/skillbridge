def notifications(request):
    if not request.user.is_authenticated:
        return {"unread_notification_count": 0}
    from .interview_reminders import queue_interview_reminders
    queue_interview_reminders(request)
    return {
        "unread_notification_count": request.user.notifications.filter(is_read=False).count(),
    }
