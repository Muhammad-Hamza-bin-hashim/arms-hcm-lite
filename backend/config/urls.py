from django.conf import settings
from django.http import HttpResponse, JsonResponse
from django.urls import include, path, re_path


def health(_request):
    return JsonResponse({"status": "ok"})


def spa(_request):
    """Serves the built React app for any non-API route (production single-service deploy)."""
    index = settings.FRONTEND_DIST / "index.html"
    if not index.exists():
        return HttpResponse("Frontend not built. Run `npm run build` in /frontend, or use the Vite dev server.",
                            status=404, content_type="text/plain")
    return HttpResponse(index.read_text(encoding="utf-8"))


api = [
    path("", include("apps.accounts.urls")),
    path("", include("apps.org.urls")),
    path("", include("apps.employees.urls")),
    path("", include("apps.attendance.urls")),
    path("", include("apps.leaves.urls")),
    path("", include("apps.payroll.urls")),
    path("", include("apps.analytics.urls")),
    path("", include("apps.ai.urls")),
    path("", include("apps.comms.urls")),
]

urlpatterns = [
    path("api/health/", health),
    path("api/", include(api)),
    re_path(r"^(?!api/|static/).*$", spa),
]
