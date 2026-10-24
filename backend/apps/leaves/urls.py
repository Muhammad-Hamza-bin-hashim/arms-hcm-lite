from django.urls import path

from . import views

urlpatterns = [
    path("leave/requests/", views.LeaveRequestListCreateView.as_view()),
    path("leave/requests/<int:pk>/approve/", views.LeaveDecisionView.as_view(approve=True)),
    path("leave/requests/<int:pk>/reject/", views.LeaveDecisionView.as_view(approve=False)),
    path("leave/requests/<int:pk>/cancel/", views.LeaveCancelView.as_view()),
    path("leave/preview/", views.LeavePreviewView.as_view()),
    path("leave/balance/", views.LeaveBalanceView.as_view()),
    path("leave/types/", views.LeaveTypeOptionsView.as_view()),
]
