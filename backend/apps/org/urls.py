from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter(trailing_slash=True)
router.register("departments", views.DepartmentViewSet, basename="department")
router.register("designations", views.DesignationViewSet, basename="designation")
router.register("leave-types", views.LeaveTypeViewSet, basename="leave-type")
router.register("holidays", views.HolidayViewSet, basename="holiday")

urlpatterns = [
    path("settings/", views.CompanySettingsView.as_view()),
    *router.urls,
]
