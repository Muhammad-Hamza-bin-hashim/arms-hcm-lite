from django.urls import path

from . import views

urlpatterns = [
    path("announcements/", views.AnnouncementListCreateView.as_view()),
    path("announcements/<int:pk>/", views.AnnouncementDeleteView.as_view()),
    path("notifications/", views.NotificationListView.as_view()),
    path("notifications/read-all/", views.NotificationReadView.as_view()),
    path("notifications/<int:pk>/read/", views.NotificationReadView.as_view()),
    path("audit-logs/", views.AuditLogView.as_view()),
]
