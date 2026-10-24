from django.urls import path

from . import views

urlpatterns = [
    path("ai/status/", views.StatusView.as_view()),
    path("ai/chat/", views.ChatView.as_view()),
    path("ai/summary/", views.SummaryView.as_view()),
    path("ai/smart-leave/", views.SmartLeaveView.as_view()),
    path("ai/logs/", views.AILogListView.as_view()),
]
