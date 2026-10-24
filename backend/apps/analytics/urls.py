from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/admin/", views.AdminDashboardView.as_view()),
    path("dashboard/hr/", views.HRDashboardView.as_view()),
    path("dashboard/employee/", views.EmployeeDashboardView.as_view()),
]
