from rest_framework.permissions import SAFE_METHODS, BasePermission

from .models import Role


class PasswordChanged(BasePermission):
    """Users holding a temporary password may only change it."""

    message = "You must change your temporary password first."

    def has_permission(self, request, view):
        user = request.user
        return not (user and user.is_authenticated and user.must_change_password)


def _role(request):
    user = request.user
    return getattr(user, "role", None) if user and user.is_authenticated else None


class RoleAccess(BasePermission):
    """Views declare `read_roles` and `write_roles`; checked on the server for every request."""

    def has_permission(self, request, view):
        role = _role(request)
        if role is None:
            return False
        if request.method in SAFE_METHODS:
            return role in getattr(view, "read_roles", ())
        return role in getattr(view, "write_roles", ())


def roles(*allowed):
    class _HasRole(BasePermission):
        message = "You do not have permission to perform this action."

        def has_permission(self, request, view):
            return _role(request) in allowed

    _HasRole.__name__ = "HasRole_" + "_".join(allowed)
    return _HasRole


IsAdmin = roles(Role.ADMIN)
IsHR = roles(Role.HR)
IsAdminOrHR = roles(Role.ADMIN, Role.HR)
IsEmployee = roles(Role.EMPLOYEE)
