from datetime import date

from rest_framework import serializers, status
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.generics import ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.accounts.models import Role
from apps.accounts.permissions import IsAdminOrHR, IsHR, PasswordChanged
from apps.employees.models import Employee
from apps.org.models import CompanySettings
from apps.org.services import WorkCalendar, local_today, month_bounds
from config.exceptions import BusinessRuleError

from . import services
from .geo import MAX_GPS_ACCURACY_M, haversine_m
from .models import Attendance, AttendanceCorrection

AUTH = [IsAuthenticated, PasswordChanged]


class AttendanceSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_code", read_only=True)

    class Meta:
        model = Attendance
        fields = ["id", "employee", "employee_name", "employee_code", "date", "check_in", "check_out", "status",
                  "is_late", "worked_minutes", "source", "distance_m"]


class CorrectionSerializer(serializers.ModelSerializer):
    employee_name = serializers.CharField(source="employee.full_name", read_only=True)
    employee_code = serializers.CharField(source="employee.employee_code", read_only=True)
    reviewed_by_name = serializers.CharField(source="reviewed_by.full_name", read_only=True, default=None)

    class Meta:
        model = AttendanceCorrection
        fields = ["id", "employee", "employee_name", "employee_code", "date", "check_in_time", "check_out_time",
                  "reason", "status", "reviewed_by_name", "reviewed_at", "review_comment", "created_at"]
        read_only_fields = ["employee", "status", "reviewed_at", "review_comment", "created_at"]


def _today_payload(user):
    employee = getattr(user, "employee", None)
    s = CompanySettings.get()
    record = Attendance.objects.filter(employee=employee, date=local_today(s)).first() if employee else None
    return {
        "has_profile": employee is not None,
        "date": local_today(s),
        "record": AttendanceSerializer(record).data if record else None,
        "worked_minutes": services.worked_minutes_live(record) if record else 0,
        "office_start": s.office_start, "grace_minutes": s.grace_minutes,
        "camera_enabled": s.office_lat is not None and s.office_lng is not None,
        "office_radius_m": s.office_radius_m,
        "is_working_day": WorkCalendar(s).is_working_day(local_today(s)),
    }


class TodayView(APIView):
    permission_classes = AUTH

    def get(self, request):
        return Response(_today_payload(request.user))


class CheckInView(APIView):
    permission_classes = AUTH

    def post(self, request):
        services.check_in(request.user, request=request)
        return Response(_today_payload(request.user), status=status.HTTP_201_CREATED)


class CameraCheckInView(APIView):
    """Bonus: the phone/browser sends face count + GPS; the server decides using the Haversine distance."""

    permission_classes = AUTH

    class Input(serializers.Serializer):
        latitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-90, max_value=90)
        longitude = serializers.DecimalField(max_digits=9, decimal_places=6, min_value=-180, max_value=180)
        accuracy = serializers.FloatField(min_value=0)
        face_count = serializers.IntegerField(min_value=0)

    def post(self, request):
        ser = self.Input(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        s = CompanySettings.get()
        if s.office_lat is None or s.office_lng is None:
            raise BusinessRuleError("Admin has not set the office location yet.", code="no_office_location")
        if d["face_count"] == 0:
            raise BusinessRuleError("No face detected. Face the camera and try again.", code="no_face")
        if d["face_count"] > 1:
            raise BusinessRuleError("More than one face detected. Only you should be in the frame.",
                                    code="multiple_faces")
        if d["accuracy"] > MAX_GPS_ACCURACY_M:
            raise BusinessRuleError(f"GPS accuracy is {d['accuracy']:.0f} m; it must be {MAX_GPS_ACCURACY_M} m or "
                                    "better. Move near a window or enable precise location.", code="poor_accuracy")
        distance = haversine_m(d["latitude"], d["longitude"], s.office_lat, s.office_lng)
        if distance > s.office_radius_m:
            raise BusinessRuleError(f"You are {distance:.0f} m from the office; check-in is allowed within "
                                    f"{s.office_radius_m} m.", code="outside_geofence",
                                    errors={"distance_m": [round(distance)]})
        services.check_in(request.user, source=Attendance.Source.CAMERA, latitude=d["latitude"],
                          longitude=d["longitude"], distance_m=round(distance), request=request)
        return Response(_today_payload(request.user), status=status.HTTP_201_CREATED)


class CheckOutView(APIView):
    permission_classes = AUTH

    def post(self, request):
        services.check_out(request.user, request=request)
        return Response(_today_payload(request.user))


def _parse_month(value):
    today = local_today()
    if not value:
        return today.year, today.month
    try:
        y, m = value.split("-")
        y, m = int(y), int(m)
        assert 1 <= m <= 12
        return y, m
    except (ValueError, AssertionError):
        raise ValidationError({"month": ["Use YYYY-MM."]})


def _parse_date(value, field, default=None):
    if not value:
        return default
    try:
        return date.fromisoformat(value)
    except ValueError:
        raise ValidationError({field: ["Use YYYY-MM-DD."]})


class CalendarView(APIView):
    """One employee's month. Employees always get their own; Admin/HR may pass ?employee=."""

    permission_classes = AUTH

    def get(self, request):
        user = request.user
        if user.role == Role.EMPLOYEE or not request.query_params.get("employee"):
            employee = getattr(user, "employee", None)
            if employee is None:
                raise BusinessRuleError("No employee profile linked to this login.", code="no_employee_profile")
        else:
            employee = Employee.objects.filter(pk=request.query_params["employee"]).first()
            if employee is None:
                raise ValidationError({"employee": ["Unknown employee."]})
        year, month = _parse_month(request.query_params.get("month"))
        start, end = month_bounds(year, month)
        cal = WorkCalendar()
        row = services.day_matrix([employee], start, end, cal=cal)[employee.pk]
        records = {a.date: a for a in Attendance.objects.filter(employee=employee, date__range=(start, end))}
        days = []
        for d, info in row.items():
            rec = records.get(d)
            days.append({"date": d, "status": info.status, "leave_type": info.leave_code, "is_late": info.is_late,
                         "working": info.working, "holiday": d in cal.holidays,
                         "check_in": rec.check_in if rec else None, "check_out": rec.check_out if rec else None,
                         "worked_minutes": rec.worked_minutes if rec else None})
        return Response({"employee": {"id": employee.pk, "name": employee.full_name, "code": employee.employee_code},
                         "month": f"{year}-{month:02d}", "summary": services.summarize([row]), "days": days})


class BoardView(APIView):
    """Daily attendance board for Admin/HR."""

    permission_classes = AUTH + [IsAdminOrHR]

    def get(self, request):
        day = _parse_date(request.query_params.get("date"), "date", local_today())
        dept = request.query_params.get("department") or None
        employees = list(services.employees_in_scope(dept, day, day).select_related("department"))
        matrix = services.day_matrix(employees, day, day)
        records = {a.employee_id: a for a in Attendance.objects.filter(date=day, employee__in=employees)}
        rows = []
        for e in employees:
            info = matrix[e.pk][day]
            rec = records.get(e.pk)
            rows.append({"employee_id": e.pk, "employee_code": e.employee_code, "name": e.full_name,
                         "department": e.department.name, "status": info.status, "leave_type": info.leave_code,
                         "is_late": info.is_late, "check_in": rec.check_in if rec else None,
                         "check_out": rec.check_out if rec else None,
                         "worked_minutes": services.worked_minutes_live(rec) if rec else None,
                         "source": rec.source if rec else None})
        status_filter = request.query_params.get("status")
        if status_filter:
            rows = [r for r in rows if r["status"] == status_filter]
        return Response({"date": day, "summary": services.summarize(matrix.values()), "rows": rows})


class RecordListView(ListAPIView):
    permission_classes = AUTH
    serializer_class = AttendanceSerializer

    def get_queryset(self):
        services.close_stale_records()
        qs = Attendance.objects.select_related("employee")
        user = self.request.user
        if user.role == Role.EMPLOYEE:
            qs = qs.filter(employee__user=user)
        elif self.request.query_params.get("employee"):
            qs = qs.filter(employee_id=self.request.query_params["employee"])
        p = self.request.query_params
        if p.get("from"):
            qs = qs.filter(date__gte=_parse_date(p["from"], "from"))
        if p.get("to"):
            qs = qs.filter(date__lte=_parse_date(p["to"], "to"))
        if p.get("status"):
            qs = qs.filter(status=p["status"])
        return qs


class CorrectionListCreateView(ListAPIView):
    permission_classes = AUTH
    serializer_class = CorrectionSerializer

    def get_queryset(self):
        qs = AttendanceCorrection.objects.select_related("employee", "reviewed_by")
        user = self.request.user
        mine = self.request.query_params.get("mine") == "true"
        if user.role == Role.EMPLOYEE or mine:
            qs = qs.filter(employee__user=user)
        if self.request.query_params.get("status"):
            qs = qs.filter(status=self.request.query_params["status"])
        return qs

    def post(self, request):
        if request.user.role == Role.ADMIN:
            raise PermissionDenied("Admins do not request attendance corrections.")
        ser = CorrectionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        d = ser.validated_data
        corr = services.request_correction(request.user, date=d["date"], check_in_time=d["check_in_time"],
                                           check_out_time=d.get("check_out_time"), reason=d["reason"],
                                           request=request)
        return Response(CorrectionSerializer(corr).data, status=status.HTTP_201_CREATED)


class CorrectionDecisionView(APIView):
    permission_classes = AUTH + [IsHR]
    approve = True

    def post(self, request, pk):
        if not AttendanceCorrection.objects.filter(pk=pk).exists():
            return Response({"detail": "Not found.", "code": "not_found"}, status=404)
        corr = services.decide_correction(pk, approve=self.approve, comment=str(request.data.get("comment", ""))[:500],
                                          actor=request.user, request=request)
        return Response(CorrectionSerializer(corr).data)


