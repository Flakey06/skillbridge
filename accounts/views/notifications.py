"""Account inbox and read status."""

from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render
from ..models import Notification
from .common import _role


@login_required
def inbox(request):
    notifications = Notification.objects.filter(recipient=request.user)
    if request.method == "POST":
        notifications.filter(is_read=False).update(is_read=True)
        return redirect("inbox")
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, "accounts/inbox.html", {
        "role": _role(request),
        "notifications": notifications,
    })
