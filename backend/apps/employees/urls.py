from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter(trailing_slash=True)
router.register("employees", views.EmployeeViewSet, basename="employee")

urlpatterns = router.urls
