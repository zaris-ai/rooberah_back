from django.db import models
from django.db.models import Q


class EmployeeUser(models.Model):
    telegram_user_id = models.CharField(
        max_length=64,
        unique=True,
        verbose_name="شناسه تلگرام",
    )
    username = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="نام کاربری",
    )
    first_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="نام",
    )
    last_name = models.CharField(
        max_length=255,
        null=True,
        blank=True,
        verbose_name="نام خانوادگی",
    )
    status = models.CharField(
        max_length=50,
        default="pending",
        verbose_name="وضعیت تایید",
    )
    access_level = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        verbose_name="سطح دسترسی",
    )
    department = models.CharField(
        max_length=100,
        null=True,
        blank=True,
        verbose_name="واحد سازمانی",
    )

    class Meta:
        managed = False
        db_table = "users"
        verbose_name = "کاربر"
        verbose_name_plural = "کاربران"

    def __str__(self):
        full_name = f"{self.first_name or ''} {self.last_name or ''}".strip()
        return full_name or self.username or str(self.telegram_user_id)


class ParkingUnit(models.Model):
    title = models.CharField(
        max_length=100,
        verbose_name="عنوان واحد",
    )
    sort_order = models.PositiveIntegerField(
        default=0,
        verbose_name="ترتیب نمایش",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال است؟",
    )

    class Meta:
        db_table = "parking_units"
        ordering = ["sort_order", "id"]
        verbose_name = "واحد پارکینگ"
        verbose_name_plural = "واحدهای پارکینگ"

    def __str__(self):
        return self.title


class ParkingSpot(models.Model):
    unit = models.ForeignKey(
        ParkingUnit,
        on_delete=models.CASCADE,
        related_name="spots",
        verbose_name="واحد پارکینگ",
    )
    code = models.CharField(
        max_length=50,
        verbose_name="کد جایگاه",
    )
    row = models.PositiveIntegerField(
        verbose_name="ردیف",
    )
    col = models.PositiveIntegerField(
        verbose_name="ستون",
    )
    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال است؟",
    )

    class Meta:
        db_table = "parking_spots"
        ordering = ["unit_id", "row", "col"]
        verbose_name = "جایگاه پارکینگ"
        verbose_name_plural = "جایگاه‌های پارکینگ"
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
    telegram_user_id = models.CharField(
        max_length=64,
        verbose_name="شناسه تلگرام",
    )
    unit = models.ForeignKey(
        ParkingUnit,
        on_delete=models.PROTECT,
        related_name="parking_sessions",
        verbose_name="واحد پارکینگ",
    )
    spot = models.ForeignKey(
        ParkingSpot,
        on_delete=models.PROTECT,
        related_name="parking_sessions",
        verbose_name="جایگاه پارکینگ",
    )
    entered_at = models.DateTimeField(
        auto_now_add=True,
        verbose_name="زمان ورود",
    )
    exited_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name="زمان خروج",
    )

    class Meta:
        db_table = "parking_sessions"
        ordering = ["-entered_at"]
        verbose_name = "ورود و خروج پارکینگ"
        verbose_name_plural = "ورود و خروج پارکینگ"
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
    parent = models.ForeignKey(
        "self",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="children",
        verbose_name="وضعیت اصلی",
        help_text="اگر این وضعیت زیرمجموعه است، وضعیت اصلی را انتخاب کنید.",
    )

    code = models.CharField(
        max_length=50,
        unique=True,
        verbose_name="کد وضعیت",
        help_text="مثلاً: onsite_available, remote_deep_work. بعد از استفاده تغییرش ندهید.",
    )

    title = models.CharField(
        max_length=100,
        verbose_name="عنوان وضعیت",
        help_text="مثلاً: حضوری، دورکاری، در دسترس، کار عمیق",
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

    is_selectable = models.BooleanField(
        default=True,
        verbose_name="قابل انتخاب توسط کاربر؟",
        help_text="برای وضعیت‌های اصلی مثل حضوری/دورکاری معمولاً غیرفعال باشد؛ برای زیر وضعیت‌ها فعال باشد.",
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
        ordering = ["parent_id", "sort_order", "id"]
        verbose_name = "وضعیت کاری"
        verbose_name_plural = "وضعیت‌های کاری"

    def __str__(self):
        emoji = self.emoji or ""

        if self.parent:
            return f"{emoji} {self.parent.title} - {self.title}".strip()

        return f"{emoji} {self.title}".strip()

class FoodReservation(models.Model):
    PORTION_FULL = "full"
    PORTION_HALF = "half"
    PORTION_KHORAK = "khorak"

    PORTION_CHOICES = [
        (PORTION_FULL, "پرس کامل"),
        (PORTION_HALF, "نیم پرس"),
        (PORTION_KHORAK, "خوراک"),
    ]

    FOOD_SLOT_1 = "f1"
    FOOD_SLOT_2 = "f2"
    FOOD_SLOT_3 = "f3"

    FOOD_SLOT_CHOICES = [
        (FOOD_SLOT_1, "غذای اول"),
        (FOOD_SLOT_2, "غذای دوم"),
        (FOOD_SLOT_3, "غذای سوم"),
    ]

    id = models.AutoField(primary_key=True)

    telegram_user_id = models.TextField(
        blank=True,
        null=True,
        verbose_name="شناسه تلگرام کاربر",
    )

    day_of_week = models.TextField(
        blank=True,
        null=True,
        verbose_name="روز هفته",
    )

    food = models.TextField(
        blank=True,
        null=True,
        verbose_name="غذای انتخاب‌شده",
    )

    reserved_at = models.DateTimeField(
        blank=True,
        null=True,
        verbose_name="زمان ثبت رزرو",
    )

    week_start_date = models.DateField(
        blank=True,
        null=True,
        verbose_name="تاریخ شروع هفته",
    )

    food_slot = models.TextField(
    blank=True,
    null=True,
    choices=FOOD_SLOT_CHOICES,
    verbose_name="انتخاب غذا",
    help_text="f1 یعنی غذای اول، f2 یعنی غذای دوم، f3 یعنی غذای سوم",
        )

    portion_type = models.TextField(
        choices=PORTION_CHOICES,
        default=PORTION_FULL,
        verbose_name="نوع پرس",
    )

    portion_label = models.TextField(
        default="پرس کامل",
        verbose_name="عنوان نوع پرس",
    )

    portion_qty = models.DecimalField(
        max_digits=4,
        decimal_places=2,
        default=1,
        verbose_name="ضریب پرس",
    )

    class Meta:
        db_table = "reservations"
        managed = False
        ordering = ["-reserved_at", "id"]
        verbose_name = "رزرو غذا"
        verbose_name_plural = "رزروهای غذا"

    def __str__(self):
        return f"{self.telegram_user_id} - {self.week_start_date} - {self.day_of_week} - {self.food}"


class WeekMenu(models.Model):
    id = models.AutoField(primary_key=True)

    day_of_week = models.TextField(
        verbose_name="روز هفته",
    )

    food1 = models.TextField(
        blank=True,
        null=True,
        verbose_name="غذای اول",
    )

    food2 = models.TextField(
        blank=True,
        null=True,
        verbose_name="غذای دوم",
    )
    food3 = models.TextField(
        blank=True,
        null=True,
        verbose_name="غذای سوم",
    )

    week_start_date = models.DateField(
        verbose_name="تاریخ شروع هفته",
    )

    class Meta:
        db_table = "week_menu"
        managed = False
        ordering = ["week_start_date", "id"]
        verbose_name = "برنامه غذایی هفته"
        verbose_name_plural = "برنامه‌های غذایی هفته"

    def __str__(self):
        return f"{self.week_start_date} - {self.day_of_week}"
class FoodReservationSettings(models.Model):
    cutoff_hour = models.PositiveSmallIntegerField(
        default=19,
        verbose_name="ساعت پایان امکان تغییر غذا",
        help_text="عدد بین ۰ تا ۲۳. مثال: ۱۹ یعنی ساعت ۷ عصر.",
    )

    cutoff_minute = models.PositiveSmallIntegerField(
        default=0,
        verbose_name="دقیقه پایان امکان تغییر غذا",
        help_text="عدد بین ۰ تا ۵۹.",
    )

    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال است؟",
    )

    updated_at = models.DateTimeField(
        auto_now=True,
        verbose_name="آخرین بروزرسانی",
    )

    class Meta:
        db_table = "food_reservation_settings"
        verbose_name = "تنظیمات رزرو غذا"
        verbose_name_plural = "تنظیمات رزرو غذا"

    def clean(self):
        from django.core.exceptions import ValidationError

        if self.cutoff_hour > 23:
            raise ValidationError("ساعت باید بین ۰ تا ۲۳ باشد.")

        if self.cutoff_minute > 59:
            raise ValidationError("دقیقه باید بین ۰ تا ۵۹ باشد.")

    def __str__(self):
        return f"{self.cutoff_hour:02d}:{self.cutoff_minute:02d}"
class DepartmentTeam(models.Model):
    code = models.CharField(
        max_length=100,
        unique=True,
        null=True,
        blank=True,
        verbose_name="کد تیم",
        help_text="مثلاً: team_a یا sales یا support. بعد از استفاده تغییرش ندهید.",
    )

    title = models.CharField(
        max_length=150,
        verbose_name="عنوان تیم",
        help_text="مثلاً: تیم فروش، تیم پشتیبانی، تیم فنی",
    )

   

    is_active = models.BooleanField(
        default=True,
        verbose_name="فعال است؟",
    )

    sort_order = models.PositiveIntegerField(
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
        db_table = "department_teams"
        ordering = ["sort_order", "id"]
        verbose_name = "تیم"
        verbose_name_plural = "تیم‌ها"

    def __str__(self):
        return self.title