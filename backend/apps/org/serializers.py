from zoneinfo import available_timezones

from rest_framework import serializers

from .models import CompanySettings, Department, Designation, Holiday, LeaveType


class CompanySettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = CompanySettings
        fields = ["company_name", "timezone", "currency", "office_start", "office_end", "grace_minutes",
                  "half_day_hours", "weekend_days", "office_lat", "office_lng", "office_radius_m",
                  "late_penalty_enabled", "updated_at"]
        read_only_fields = ["updated_at"]

    def validate_weekend_days(self, value):
        if not isinstance(value, list) or any(not isinstance(d, int) or d < 0 or d > 6 for d in value):
            raise serializers.ValidationError("Use a list of weekday numbers 0 (Mon) to 6 (Sun).")
        if len(set(value)) >= 7:
            raise serializers.ValidationError("At least one working day is required.")
        return sorted(set(value))

    def validate_timezone(self, value):
        if value not in available_timezones():
            raise serializers.ValidationError("Unknown timezone.")
        return value

    def validate(self, attrs):
        start = attrs.get("office_start", getattr(self.instance, "office_start", None))
        end = attrs.get("office_end", getattr(self.instance, "office_end", None))
        if start and end and end <= start:
            raise serializers.ValidationError({"office_end": "Office end must be after office start."})
        lat = attrs.get("office_lat", getattr(self.instance, "office_lat", None))
        lng = attrs.get("office_lng", getattr(self.instance, "office_lng", None))
        if (lat is None) != (lng is None):
            raise serializers.ValidationError({"office_lat": "Set both latitude and longitude, or neither."})
        return attrs


class DepartmentSerializer(serializers.ModelSerializer):
    employee_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Department
        fields = ["id", "name", "code", "is_active", "employee_count", "created_at"]
        read_only_fields = ["created_at"]

    def validate_code(self, value):
        return value.strip().upper()


class DesignationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Designation
        fields = ["id", "name", "is_active", "created_at"]
        read_only_fields = ["created_at"]


class LeaveTypeSerializer(serializers.ModelSerializer):
    class Meta:
        model = LeaveType
        fields = ["id", "code", "name", "yearly_quota", "is_paid", "is_active"]


class HolidaySerializer(serializers.ModelSerializer):
    class Meta:
        model = Holiday
        fields = ["id", "date", "name"]
