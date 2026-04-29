from django.db import models
from django.db.models import Q


class EmployeeUser(models.Model):
    
    telegram_user_id = models.CharField(max_length=64, unique=True)
    username = models.CharField(max_length=255, null=True, blank=True)
    first_name = models.CharField(max_length=255, null=True, blank=True)
    last_name = models.CharField(max_length=255, null=True, blank=True)
    status = models.CharField(max_length=50, default="pending")
    access_level = models.CharField(max_length=50, null=True, blank=True)
    department = models.CharField(max_length=100, null=True, blank=True)

    class Meta:
        managed = False
        db_table = "users"


class ParkingUnit(models.Model):
    title = models.CharField(max_length=100)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "parking_units"
        ordering = ["sort_order", "id"]

    def __str__(self):
        return self.title


class ParkingSpot(models.Model):
    unit = models.ForeignKey(
        ParkingUnit,
        on_delete=models.CASCADE,
        related_name="spots",
    )
    code = models.CharField(max_length=50)
    row = models.PositiveIntegerField()
    col = models.PositiveIntegerField()
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = "parking_spots"
        ordering = ["unit_id", "row", "col"]
        constraints = [
            models.UniqueConstraint(
                fields=["unit", "code"],
                name="unique_spot_code_per_unit",
            ),
            models.UniqueConstraint(
                fields=["unit", "row", "col"],
                name="unique_spot_position_per_unit",
            ),
        ]

    def __str__(self):
        return f"{self.unit.title} - {self.code}"


class ParkingSession(models.Model):
    telegram_user_id = models.CharField(max_length=64)
    unit = models.ForeignKey(
        ParkingUnit,
        on_delete=models.PROTECT,
        related_name="parking_sessions",
    )
    spot = models.ForeignKey(
        ParkingSpot,
        on_delete=models.PROTECT,
        related_name="parking_sessions",
    )
    entered_at = models.DateTimeField(auto_now_add=True)
    exited_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "parking_sessions"
        ordering = ["-entered_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["telegram_user_id"],
                condition=Q(exited_at__isnull=True),
                name="unique_active_session_per_user",
            ),
            models.UniqueConstraint(
                fields=["spot"],
                condition=Q(exited_at__isnull=True),
                name="unique_active_session_per_spot",
            ),
        ]
        indexes = [
            models.Index(fields=["telegram_user_id", "exited_at"]),
            models.Index(fields=["spot", "exited_at"]),
        ]

    def __str__(self):
        return f"{self.telegram_user_id} - {self.spot.code}"



class WorkStatus(models.Model):
    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="کد وضعیت",
        help_text="مثلاً: present, remote, busy. بعد از استفاده تغییرش ندهید.",
    )
    title = models.CharField(
        max_length=100,
        verbose_name="عنوان وضعیت",
        help_text="مثلاً: حضوری، دورکار، جلسه، مرخصی",
    )
    emoji = models.CharField(
        max_length=10,
        blank=True,
        null=True,
        verbose_name="ایموجی",
        help_text="مثلاً: 🟢 یا 🏠 یا 🔴",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال است؟",
    )
    sort_order = models.IntegerField(
        default=100,
        verbose_name="ترتیب نمایش",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان ایجاد",
    )
    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین بروزرسانی",
    )

    class Meta:
        db_table = "work_statuses"
        managed = False
        ordering = ["sort_order", "id"]
        verbose_name = "وضعیت کاری"
        verbose_name_plural = "وضعیت‌های کاری"

    def __str__(self):
        emoji = self.emoji or ""
        return f"{emoji} {self.title}".strip()