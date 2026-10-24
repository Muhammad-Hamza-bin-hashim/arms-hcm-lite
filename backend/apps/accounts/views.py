from django.db import transaction
from django.utils import timezone
from rest_framework import mixins, status, viewsets
from rest_framework.decorators import action
from rest_framework.exceptions import AuthenticationFailed, PermissionDenied
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView
from rest_framework_simplejwt.exceptions import TokenError
from rest_framework_simplejwt.tokens import RefreshToken

from apps.org.models import CompanySettings

from . import services
from .authentication import issue_tokens
from .models import Role, User
from .permissions import IsAdmin
from .serializers import (ChangePasswordSerializer, CreateHRUserSerializer, LoginSerializer, SetupSerializer,
                          UserSerializer)


def _auth_payload(user):
    return {**issue_tokens(user), "user": UserSerializer(user).data}


class SetupStatusView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get(self, request):
        s = CompanySettings.objects.filter(pk=1).first()
        return Response({"setup_completed": services.setup_completed(), "company_name": s.company_name if s else ""})


class SetupView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "setup"

    def post(self, request):
        if services.setup_completed():
            raise PermissionDenied("Setup has already been completed.")
        ser = SetupSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        admin = services.run_first_setup(**ser.validated_data, request=request)
        if admin is None:
            raise PermissionDenied("Setup has already been completed.")
        return Response(_auth_payload(admin), status=status.HTTP_201_CREATED)


class LoginView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_authenticate_header(self, request):  # makes failed logins 401, not 403
        return "Bearer"
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = "login"

    def post(self, request):
        ser = LoginSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = User.objects.filter(email__iexact=ser.validated_data["email"]).first()
        if user is None or not user.check_password(ser.validated_data["password"]):
            raise AuthenticationFailed("Invalid email or password.")
        if not user.is_active:
            raise AuthenticationFailed("This account has been deactivated. Contact your administrator.")
        user.last_login = timezone.now()
        user.save(update_fields=["last_login"])
        return Response(_auth_payload(user))


class RefreshView(APIView):
    permission_classes = [AllowAny]
    authentication_classes = []

    def get_authenticate_header(self, request):
        return "Bearer"

    def post(self, request):
        try:
            refresh = RefreshToken(request.data.get("refresh", ""))
        except TokenError:
            raise AuthenticationFailed("Session expired. Please sign in again.")
        user = User.objects.filter(pk=refresh.get("user_id")).first()
        if user is None or not user.is_active or refresh.get("ver") != user.token_version:
            raise AuthenticationFailed("Session expired. Please sign in again.")
        return Response(_auth_payload(user))


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user
        user.token_version += 1
        user.save(update_fields=["token_version"])
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(UserSerializer(request.user).data)


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        ser = ChangePasswordSerializer(data=request.data, context={"request": request})
        ser.is_valid(raise_exception=True)
        services.change_password(request.user, ser.validated_data["new_password"], request=request)
        return Response(_auth_payload(request.user))


class UserViewSet(mixins.ListModelMixin, mixins.RetrieveModelMixin, mixins.CreateModelMixin, viewsets.GenericViewSet):
    """Admin: list all logins, create HR logins, activate / deactivate / reset any login."""

    serializer_class = UserSerializer
    permission_classes = [IsAuthenticated, IsAdmin]

    def get_queryset(self):
        qs = User.objects.select_related("employee").order_by("role", "email")
        role = self.request.query_params.get("role")
        if role in Role.values:
            qs = qs.filter(role=role)
        q = self.request.query_params.get("search")
        if q:
            from django.db.models import Q
            qs = qs.filter(Q(email__icontains=q) | Q(first_name__icontains=q) | Q(last_name__icontains=q))
        return qs

    @transaction.atomic
    def create(self, request, *args, **kwargs):
        ser = CreateHRUserSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user, temp = services.create_login(actor=request.user, request=request, **ser.validated_data)
        return Response({"user": UserSerializer(user).data, "temporary_password": temp}, status=status.HTTP_201_CREATED)

    def _target(self, request):
        user = self.get_object()
        if user.pk == request.user.pk:
            raise PermissionDenied("You cannot change your own account here.")
        return user

    @action(detail=True, methods=["post"])
    def deactivate(self, request, pk=None):
        user = self._target(request)
        services.set_active(user, False, actor=request.user, request=request)
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"])
    def activate(self, request, pk=None):
        user = self._target(request)
        services.set_active(user, True, actor=request.user, request=request)
        return Response(UserSerializer(user).data)

    @action(detail=True, methods=["post"], url_path="reset-password")
    def reset_password(self, request, pk=None):
        user = self._target(request)
        temp = services.reset_password(user, actor=request.user, request=request)
        return Response({"user": UserSerializer(user).data, "temporary_password": temp})
