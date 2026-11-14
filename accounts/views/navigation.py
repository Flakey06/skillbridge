"""Session-backed navigation preferences without client-side scripts."""
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST


@login_required
@require_POST
def toggle_navigation(request):
    request.session["sidebar_expanded"] = not request.session.get("sidebar_expanded", True)
    destination = request.POST.get("next", "")
    if url_has_allowed_host_and_scheme(destination, {request.get_host()}, require_https=request.is_secure()):
        return redirect(destination)
    return redirect("home")
