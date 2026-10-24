from django.urls import path

from . import views

urlpatterns = [
    path("payroll/salaries/", views.SalaryView.as_view()),
    path("payroll/runs/", views.RunListCreateView.as_view()),
    path("payroll/runs/<int:pk>/", views.RunDetailView.as_view()),
    path("payroll/runs/<int:pk>/regenerate/", views.RunRegenerateView.as_view()),
    path("payroll/runs/<int:pk>/finalize/", views.RunFinalizeView.as_view()),
    path("payroll/payslips/", views.PayslipListView.as_view()),
    path("payroll/payslips/<int:pk>/", views.PayslipDetailView.as_view()),
    path("payroll/payslips/<int:pk>/pdf/", views.PayslipPdfView.as_view()),
]
