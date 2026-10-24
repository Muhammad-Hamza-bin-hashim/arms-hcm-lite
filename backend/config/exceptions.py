"""Uniform error envelope: {"detail": str, "code": str, "errors": {...}}."""
from django.core.exceptions import PermissionDenied as DjangoPermissionDenied
from django.core.exceptions import ValidationError as DjangoValidationError
from django.http import Http404
from rest_framework import status
from rest_framework.exceptions import APIException, PermissionDenied
from rest_framework.response import Response
from rest_framework.views import exception_handler


class BusinessRuleError(APIException):
    """A request that is well-formed but breaks a business rule (HTTP 422)."""

    status_code = status.HTTP_422_UNPROCESSABLE_ENTITY
    default_detail = "The request breaks a business rule."
    default_code = "business_rule"

    def __init__(self, detail=None, code=None, errors=None):
        super().__init__(detail, code)
        self.errors = errors or {}


class ConflictError(APIException):
    status_code = status.HTTP_409_CONFLICT
    default_detail = "The resource already exists."
    default_code = "conflict"


def api_exception_handler(exc, context):
    if isinstance(exc, DjangoValidationError):
        exc_detail = exc.message_dict if hasattr(exc, "error_dict") else {"non_field_errors": exc.messages}
        return Response(
            {"detail": "Validation failed.", "code": "invalid", "errors": exc_detail},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if isinstance(exc, DjangoPermissionDenied):
        exc = PermissionDenied()
    if isinstance(exc, Http404):
        return Response({"detail": "Not found.", "code": "not_found"}, status=status.HTTP_404_NOT_FOUND)

    response = exception_handler(exc, context)
    if response is None:
        return None
    data = response.data
    code = getattr(exc, "default_code", "error")
    if hasattr(exc, "get_codes"):
        codes = exc.get_codes()
        if isinstance(codes, str):
            code = codes
    if isinstance(data, dict) and set(data.keys()) == {"detail"}:
        body = {"detail": str(data["detail"]), "code": code}
    elif isinstance(data, list):
        body = {"detail": " ".join(str(d) for d in data), "code": code}
    else:
        body = {"detail": "Validation failed.", "code": code, "errors": data}
    if getattr(exc, "errors", None):
        body["errors"] = exc.errors
    response.data = body
    return response
