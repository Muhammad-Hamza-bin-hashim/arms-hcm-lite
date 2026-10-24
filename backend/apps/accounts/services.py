import secrets
import string

from django.contrib.auth.password_validation import validate_password
from django.db import transaction

from apps.comms.services import record_audit
from apps.org.models import DEFAULT_LEAVE_TYPES, CompanySettings, LeaveType

from .models import Role, User


def generate_temp_password() -> str:
    alphabet = string.ascii_letters + string.digits
    core = "".join(secrets.choice(alphabet) for _ in range(10))
    return f"Tmp-{core}"


def setup_completed() -> bool:
    return User.objects.filter(role=Role.ADMIN).exists() and CompanySettings.objects.filter(pk=1).exists()


@transaction.atomic
def run_first_setup(*, company_name, email, password, first_name="", last_name="", request=None):
    """Creates company settings, default leave types and the Admin. Only allowed once."""
    if setup_completed():
        return None
    settings_obj, _ = CompanySettings.objects.get_or_create(pk=1, defaults={"company_name": company_name})
    settings_obj.company_name = company_name
    settings_obj.save()
    for lt in DEFAULT_LEAVE_TYPES:
        LeaveType.objects.get_or_create(code=lt["code"], defaults=lt)
    admin = User.objects.create_user(
        email=email, password=password, first_name=first_name, last_name=last_name,
        role=Role.ADMIN, is_staff=True, must_change_password=False,
    )
    record_audit(admin, "setup.completed", "company", 1, summary=f"First-run setup for {company_name}",
                 after={"company_name": company_name, "admin_email": admin.email}, request=request)
    return admin


def create_login(*, email, role, first_name="", last_name="", actor=None, request=None):
    temp = generate_temp_password()
    user = User.objects.create_user(email=email, password=temp, first_name=first_name, last_name=last_name,
                                    role=role, must_change_password=True)
    record_audit(actor, "user.created", "user", user.pk, summary=f"Created {role} login {user.email}",
                 after={"email": user.email, "role": role}, request=request)
    return user, temp


def change_password(user, new_password, request=None):
    validate_password(new_password, user)
    user.set_password(new_password)
    user.must_change_password = False
    user.token_version += 1
    user.save(update_fields=["password", "must_change_password", "token_version"])
    record_audit(user, "user.password_changed", "user", user.pk, summary="Changed own password", request=request)


def reset_password(user, *, actor, request=None):
    temp = generate_temp_password()
    user.set_password(temp)
    user.must_change_password = True
    user.token_version += 1
    user.save(update_fields=["password", "must_change_password", "token_version"])
    record_audit(actor, "user.password_reset", "user", user.pk, summary=f"Reset password for {user.email}",
                 request=request)
    return temp


def set_active(user, active, *, actor, request=None):
    before = {"is_active": user.is_active}
    user.is_active = active
    user.token_version += 1
    user.save(update_fields=["is_active", "token_version"])
    record_audit(actor, "user.activated" if active else "user.deactivated", "user", user.pk,
                 summary=f"{'Activated' if active else 'Deactivated'} {user.email}",
                 before=before, after={"is_active": active}, request=request)
