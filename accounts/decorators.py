from functools import wraps

from django.contrib.auth.decorators import login_required
from django.http import JsonResponse
from django.shortcuts import redirect


def role_required(role):
    def decorator(view):
        @login_required
        @wraps(view)
        def wrapped(request, *args, **kwargs):
            profile = getattr(request.user, "profile", None)
            if not profile or profile.role != role:
                if request.headers.get("x-requested-with") == "XMLHttpRequest":
                    return JsonResponse({
                        "ok": False,
                        "message": "Your session or account role changed. Refresh the page and sign in again.",
                    }, status=403)
                return redirect("home")
            return view(request, *args, **kwargs)

        return wrapped

    return decorator


candidate_required = role_required("candidate")
recruiter_required = role_required("recruiter")
