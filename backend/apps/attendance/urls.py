from django.urls import path

from . import views

urlpatterns = [
    path("attendance/today/", views.TodayView.as_view()),
    path("attendance/check-in/", views.CheckInView.as_view()),
    path("attendance/camera-check-in/", views.CameraCheckInView.as_view()),
    path("attendance/check-out/", views.CheckOutView.as_view()),
    path("attendance/calendar/", views.CalendarView.as_view()),
    path("attendance/board/", views.BoardView.as_view()),
    path("attendance/records/", views.RecordListView.as_view()),
    path("attendance/corrections/", views.CorrectionListCreateView.as_view()),
    path("attendance/corrections/<int:pk>/approve/", views.CorrectionDecisionView.as_view(approve=True)),
    path("attendance/corrections/<int:pk>/reject/", views.CorrectionDecisionView.as_view(approve=False)),
]
