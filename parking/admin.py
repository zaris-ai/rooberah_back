from datetime import datetime
from decimal import Decimal

from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError
from django.db.models import Count, Sum
from django.http import HttpResponse
from django.urls import path
from django.utils import timezone
from django.template.response import TemplateResponse


from django.contrib import admin, messages
from django.shortcuts import redirect
from django.urls import path, reverse
from django.utils.html import format_html


from .models import (
    DepartmentTeam,
    EmployeeUser,
    FoodReservation,
    FoodReservationSettings,
    ParkingSession,
    ParkingSpot,
    ParkingUnit,
    WeekMenu,
    WorkStatus,
)


# =========================
# Admin Site Titles
# =========================

admin.site.site_header = "پنل مدیریت"
admin.site.site_title = "مدیریت سامانه"
admin.site.index_title = "مدیریت وبگاه"
admin.site.empty_value_display = "—"


# =========================
# Shared Helpers
# =========================

DAY_ORDER = {
    "شنبه": 1,
    "یکشنبه": 2,
    "دوشنبه": 3,
    "سه شنبه": 4,
    "سه‌شنبه": 4,
    "چهارشنبه": 5,
    "پنج شنبه": 6,
    "پنج‌شنبه": 6,
}


def get_employee(telegram_user_id):
    if not telegram_user_id:
        return None

    return EmployeeUser.objects.filter(
        telegram_user_id=str(telegram_user_id)
    ).first()


def get_employee_display_name(telegram_user_id):
    user = get_employee(telegram_user_id)

    if not user:
        return "کاربر ناشناس"

    full_name = f"{user.first_name or ''} {user.last_name or ''}".strip()

    if full_name:
        return full_name

    if user.username:
        return f"@{user.username}"

    return "بدون نام"


def get_employee_telegram_username(telegram_user_id):
    user = get_employee(telegram_user_id)

    if not user or not user.username:
        return "—"

    username = str(user.username).strip()

    if not username:
        return "—"

    return username if username.startswith("@") else f"@{username}"


def get_employee_department_title(telegram_user_id):
    user = get_employee(telegram_user_id)

    if not user or not user.department:
        return "—"

    team = DepartmentTeam.objects.filter(code=user.department).first()

    if team:
        return team.title

    return user.department


def to_persian_digits(value):
    return str(value).translate(str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹"))


def gregorian_to_jalali(gy, gm, gd):
    g_days_in_month = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
    j_days_in_month = [31, 31, 31, 31, 31, 31, 30, 30, 30, 30, 30, 29]

    gy -= 1600
    gm -= 1
    gd -= 1

    g_day_no = (
        365 * gy
        + (gy + 3) // 4
        - (gy + 99) // 100
        + (gy + 399) // 400
    )

    for i in range(gm):
        g_day_no += g_days_in_month[i]

    leap_gregorian = (
        (gy + 1600) % 4 == 0
        and ((gy + 1600) % 100 != 0 or (gy + 1600) % 400 == 0)
    )

    if gm > 1 and leap_gregorian:
        g_day_no += 1

    g_day_no += gd

    j_day_no = g_day_no - 79

    j_np = j_day_no // 12053
    j_day_no %= 12053

    jy = 979 + 33 * j_np + 4 * (j_day_no // 1461)
    j_day_no %= 1461

    if j_day_no >= 366:
        jy += (j_day_no - 1) // 365
        j_day_no = (j_day_no - 1) % 365

    jm = 0

    while jm < 11 and j_day_no >= j_days_in_month[jm]:
        j_day_no -= j_days_in_month[jm]
        jm += 1

    jd = j_day_no + 1

    return jy, jm + 1, jd


def format_jalali_date(date_value):
    if not date_value:
        return "—"

    if isinstance(date_value, str):
        date_value = parse_week_start_date(date_value)

    if not date_value:
        return "—"

    jy, jm, jd = gregorian_to_jalali(
        date_value.year,
        date_value.month,
        date_value.day,
    )

    return to_persian_digits(f"{jy:04d}/{jm:02d}/{jd:02d}")


def format_jalali_datetime(datetime_value):
    if not datetime_value:
        return "—"

    if timezone.is_aware(datetime_value):
        datetime_value = timezone.localtime(datetime_value)

    date_text = format_jalali_date(datetime_value.date())
    time_text = datetime_value.strftime("%H:%M")

    return f"{date_text} - {to_persian_digits(time_text)}"


def parse_week_start_date(value):
    if not value:
        return None

    if hasattr(value, "year") and hasattr(value, "month") and hasattr(value, "day"):
        return value

    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError:
        return None


def format_portion_qty(value):
    if value is None:
        return "0"

    decimal_value = Decimal(value)

    if decimal_value == decimal_value.to_integral():
        return str(int(decimal_value))

    return str(decimal_value.normalize())


def build_food_purchase_summary_data(week_start_date):
    parsed_week_start_date = parse_week_start_date(week_start_date)

    if not parsed_week_start_date:
        return {
            "week_start_date": None,
            "week_start_jalali": "—",
            "days": [],
            "total_people": 0,
            "total_portion_qty": "0",
            "has_data": False,
        }

    reservations = (
        FoodReservation.objects
        .filter(week_start_date=parsed_week_start_date)
        .values("day_of_week", "food", "portion_label")
        .annotate(
            people_count=Count("id"),
            total_portion_qty=Sum("portion_qty"),
        )
    )

    rows = sorted(
        reservations,
        key=lambda row: (
            DAY_ORDER.get(str(row["day_of_week"] or "").strip(), 99),
            row["food"] or "",
            row["portion_label"] or "",
        ),
    )

    grouped = {}
    total_people = 0
    total_portion_qty = Decimal("0")

    for row in rows:
        day = row["day_of_week"] or "نامشخص"

        if day not in grouped:
            grouped[day] = []

        people_count = int(row["people_count"] or 0)
        portion_qty = Decimal(row["total_portion_qty"] or 0)

        total_people += people_count
        total_portion_qty += portion_qty

        grouped[day].append(
            {
                "food": row["food"] or "—",
                "portion_label": row["portion_label"] or "پرس کامل",
                "people_count": people_count,
                "portion_qty": format_portion_qty(portion_qty),
            }
        )

    ordered_days = []
    for day in ["شنبه", "یکشنبه", "دوشنبه", "سه شنبه", "چهارشنبه", "پنج شنبه"]:
        if day in grouped:
            ordered_days.append(
                {
                    "title": day,
                    "items": grouped[day],
                }
            )

    return {
        "week_start_date": parsed_week_start_date,
        "week_start_jalali": format_jalali_date(parsed_week_start_date),
        "days": ordered_days,
        "total_people": total_people,
        "total_portion_qty": format_portion_qty(total_portion_qty),
        "has_data": bool(ordered_days),
    }
# =========================
# Parking Unit
# =========================

@admin.register(ParkingUnit)
class ParkingUnitAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "sort_order",
        "is_active",
    )

    list_editable = (
        "sort_order",
        "is_active",
    )

    search_fields = (
        "title",
    )

    ordering = (
        "sort_order",
        "id",
    )

    fieldsets = (
        (
            "اطلاعات واحد پارکینگ",
            {
                "fields": (
                    "title",
                    "sort_order",
                    "is_active",
                )
            },
        ),
    )


# =========================
# Parking Spot
# =========================

@admin.register(ParkingSpot)
class ParkingSpotAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "unit",
        "code",
        "row",
        "col",
        "is_active",
    )

    list_filter = (
        "unit",
        "is_active",
    )

    search_fields = (
        "code",
        "unit__title",
    )

    list_editable = (
        "is_active",
    )

    ordering = (
        "unit",
        "row",
        "col",
        "id",
    )

    fieldsets = (
        (
            "اطلاعات جایگاه پارکینگ",
            {
                "fields": (
                    "unit",
                    "code",
                    "row",
                    "col",
                    "is_active",
                )
            },
        ),
    )


@admin.register(ParkingSession)
class ParkingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "employee_name",
        "employee_telegram_id",
        "unit",
        "spot",
        "entered_at_jalali",
        "exited_at_jalali",
        "session_status",
        "exit_button",
    )

    list_filter = (
        "unit",
        "spot",
        "exited_at",
    )

    search_fields = (
        "telegram_user_id",
        "spot__code",
        "unit__title",
    )

    readonly_fields = (
        "employee_name",
        "employee_telegram_id",
        "unit",
        "spot",
        "entered_at_jalali",
        "exited_at_jalali",
        "session_status",
    )

    actions = (
        "mark_selected_sessions_exited",
    )

    ordering = (
        "-entered_at",
        "id",
    )

    fieldsets = (
        (
            "اطلاعات کاربر",
            {
                "fields": (
                    "employee_name",
                    "employee_telegram_id",
                )
            },
        ),
        (
            "اطلاعات پارکینگ",
            {
                "fields": (
                    "unit",
                    "spot",
                    "session_status",
                )
            },
        ),
        (
            "زمان ورود و خروج",
            {
                "fields": (
                    "entered_at_jalali",
                    "exited_at_jalali",
                )
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "<int:session_id>/mark-exit/",
                self.admin_site.admin_view(self.mark_exit_view),
                name="parking_parkingsession_mark_exit",
            ),
        ]

        return custom_urls + urls

    def mark_exit_view(self, request, session_id):
        session = ParkingSession.objects.filter(id=session_id).first()

        if not session:
            self.message_user(
                request,
                "این رکورد پارکینگ پیدا نشد.",
                level=messages.ERROR,
            )
            return redirect("..")

        if session.exited_at:
            self.message_user(
                request,
                "خروج این کاربر قبلاً ثبت شده است.",
                level=messages.WARNING,
            )
            return redirect("..")

        session.exited_at = timezone.now()
        session.save(update_fields=["exited_at"])

        self.message_user(
            request,
            f"خروج کاربر {get_employee_display_name(session.telegram_user_id)} از جایگاه {session.spot.code} ثبت شد و جایگاه آزاد شد.",
            level=messages.SUCCESS,
        )

        return redirect(
            request.META.get(
                "HTTP_REFERER",
                reverse("admin:parking_parkingsession_changelist"),
            )
        )

    @admin.action(description="ثبت خروج برای sessionهای انتخاب‌شده")
    def mark_selected_sessions_exited(self, request, queryset):
        active_queryset = queryset.filter(exited_at__isnull=True)
        count = active_queryset.update(exited_at=timezone.now())

        if count:
            self.message_user(
                request,
                f"خروج {to_persian_digits(count)} مورد ثبت شد و جایگاه‌ها آزاد شدند.",
                level=messages.SUCCESS,
            )
        else:
            self.message_user(
                request,
                "هیچ session فعالی برای ثبت خروج انتخاب نشده بود.",
                level=messages.WARNING,
            )

    @admin.display(description="نام کاربر")
    def employee_name(self, obj):
        return get_employee_display_name(obj.telegram_user_id)

    @admin.display(description="آیدی تلگرام")
    def employee_telegram_id(self, obj):
        return get_employee_telegram_username(obj.telegram_user_id)

    @admin.display(description="زمان ورود")
    def entered_at_jalali(self, obj):
        return format_jalali_datetime(obj.entered_at)

    @admin.display(description="زمان خروج")
    def exited_at_jalali(self, obj):
        return format_jalali_datetime(obj.exited_at)

    @admin.display(description="وضعیت")
    def session_status(self, obj):
        if obj.exited_at:
            return "خارج شده"
        return "داخل پارکینگ"

    @admin.display(description="عملیات")
    def exit_button(self, obj):
        if obj.exited_at:
            return "—"

        url = reverse(
            "admin:parking_parkingsession_mark_exit",
            args=[obj.id],
        )

        return format_html(
            '<a class="button" href="{}" '
            'style="background:#d9534f;color:white;padding:6px 12px;'
            'border-radius:8px;text-decoration:none;font-weight:bold;display:block;">'
            'ثبت خروج</a>',
            url,
        )

# =========================
# Work Status
# =========================

class WorkStatusAdminForm(forms.ModelForm):
    class Meta:
        model = WorkStatus
        fields = "__all__"

    def clean(self):
        cleaned_data = super().clean()

        parent = cleaned_data.get("parent")
        obj = self.instance

        if parent and obj and obj.pk and parent.pk == obj.pk:
            raise ValidationError("یک وضعیت نمی‌تواند والد خودش باشد.")

        if parent and parent.parent_id:
            raise ValidationError("فقط دو سطح مجاز است: وضعیت اصلی و زیر وضعیت.")

        return cleaned_data


class WorkStatusChildInline(admin.TabularInline):
    model = WorkStatus
    fk_name = "parent"

    fields = (
        "emoji",
        "title",
        "code",
        "is_active",
        "is_selectable",
        "sort_order",
    )

    extra = 1
    show_change_link = True

    def get_queryset(self, request):
        return (
            super()
            .get_queryset(request)
            .filter(parent__isnull=False)
            .order_by("sort_order", "id")
        )


@admin.register(WorkStatus)
class WorkStatusAdmin(admin.ModelAdmin):
    form = WorkStatusAdminForm

    list_display = (
        "id",
        "emoji",
        "title",
        "parent",
        "code",
        "is_active",
        "is_selectable",
        "sort_order",
        "updated_at",
    )

    list_display_links = (
        "id",
    )

    list_editable = (
        "emoji",
        "title",
        "parent",
        "is_active",
        "is_selectable",
        "sort_order",
    )

    list_filter = (
        "parent",
        "is_active",
        "is_selectable",
    )

    search_fields = (
        "code",
        "title",
        "parent__title",
    )

    ordering = (
        "parent_id",
        "sort_order",
        "id",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    inlines = (
        WorkStatusChildInline,
    )

    fieldsets = (
        (
            "ساختار وضعیت",
            {
                "fields": (
                    "parent",
                    "code",
                    "title",
                    "emoji",
                )
            },
        ),
        (
            "تنظیمات نمایش",
            {
                "fields": (
                    "is_active",
                    "is_selectable",
                    "sort_order",
                )
            },
        ),
        (
            "زمان‌ها",
            {
                "fields": (
                    "created_at",
                    "updated_at",
                )
            },
        ),
    )

    def get_readonly_fields(self, request, obj=None):
        readonly_fields = list(super().get_readonly_fields(request, obj))

        if obj:
            readonly_fields.append("code")

        return readonly_fields

    def get_inline_instances(self, request, obj=None):
        if not obj:
            return []

        if obj.parent_id:
            return []

        return super().get_inline_instances(request, obj)


# =========================
# Week Menu
# =========================

@admin.register(WeekMenu)
class WeekMenuAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "week_start_date_jalali",
        "day_of_week",
        "food1",
        "food2",
        "food3",
    )

    list_filter = (
        "week_start_date",
        "day_of_week",
    )

    search_fields = (
        "day_of_week",
        "food1",
        "food2",
        "food3",
    )

    fields = (
        "week_start_date",
        "day_of_week",
        "food1",
        "food2",
        "food3",
    )

    ordering = (
        "week_start_date",
        "id",
    )

    @admin.display(description="تاریخ شروع هفته")
    def week_start_date_jalali(self, obj):
        return format_jalali_date(obj.week_start_date)


# =========================
# Food Reservation
# =========================

@admin.register(FoodReservation)
class FoodReservationAdmin(admin.ModelAdmin):
    change_list_template = "admin/parking/foodreservation/change_list.html"

    list_display = (
        "id",
        "employee_name",
        "employee_telegram_id",
        "food",
        "portion_label",
        "week_start_date_jalali",
        "day_of_week",
        "portion_qty",
        "reserved_at_jalali",
        "employee_department",
    )

    list_filter = (
        "week_start_date",
        "day_of_week",
        "food",
        "portion_type",
    )

    search_fields = (
        "telegram_user_id",
        "food",
        "day_of_week",
    )

    readonly_fields = (
        "employee_name",
        "employee_telegram_id",
        "employee_department",
        "week_start_date_jalali",
        "day_of_week",
        "food",
        "food_slot",
        "portion_type",
        "portion_label",
        "portion_qty",
        "reserved_at_jalali",
    )

    ordering = (
        "-week_start_date",
        "day_of_week",
        "food",
        "telegram_user_id",
    )

    date_hierarchy = "week_start_date"
    list_per_page = 50

    fieldsets = (
        (
            "اطلاعات کاربر",
            {
                "fields": (
                    "employee_name",
                    "employee_telegram_id",
                    "employee_department",
                )
            },
        ),
        (
            "اطلاعات رزرو غذا",
            {
                "fields": (
                    "week_start_date_jalali",
                    "day_of_week",
                    "food",
                    "food_slot",
                    "portion_type",
                    "portion_label",
                    "portion_qty",
                )
            },
        ),
        (
            "زمان رزرو",
            {
                "fields": (
                    "reserved_at_jalali",
                )
            },
        ),
    )

    def get_urls(self):
        urls = super().get_urls()

        custom_urls = [
            path(
                "purchase-summary/",
                self.admin_site.admin_view(self.purchase_summary_view),
                name="parking_foodreservation_purchase_summary",
            ),
        ]

        return custom_urls + urls

    def purchase_summary_view(self, request):
        week_start_date = (
            request.GET.get("week_start_date")
            or request.GET.get("week_start_date__exact")
            or request.GET.get("week_start_date__gte")
        )

        if not week_start_date:
            latest_week = (
                FoodReservation.objects
                .exclude(week_start_date__isnull=True)
                .order_by("-week_start_date")
                .values_list("week_start_date", flat=True)
                .first()
            )

            if not latest_week:
                context = dict(
                    self.admin_site.each_context(request),
                    title="خلاصه خرید غذای کل هفته",
                    summary={
                        "week_start_jalali": "—",
                        "days": [],
                        "total_people": 0,
                        "total_portion_qty": "0",
                        "has_data": False,
                    },
                )
                return TemplateResponse(
                    request,
                    "admin/parking/foodreservation/purchase_summary.html",
                    context,
                )

            week_start_date = latest_week

            summary = build_food_purchase_summary_data(week_start_date)

            context = dict(
                self.admin_site.each_context(request),
                title="خلاصه خرید غذای کل هفته",
                summary=summary,
            )

            return TemplateResponse(
                request,
                "admin/parking/foodreservation/purchase_summary.html",
                context,
            )

        

    @admin.display(description="نام کاربر")
    def employee_name(self, obj):
        return get_employee_display_name(obj.telegram_user_id)

    @admin.display(description="آیدی تلگرام")
    def employee_telegram_id(self, obj):
        return get_employee_telegram_username(obj.telegram_user_id)

    @admin.display(description="تیم")
    def employee_department(self, obj):
        return get_employee_department_title(obj.telegram_user_id)

    @admin.display(description="تاریخ شروع هفته")
    def week_start_date_jalali(self, obj):
        return format_jalali_date(obj.week_start_date)

    @admin.display(description="زمان رزرو")
    def reserved_at_jalali(self, obj):
        return format_jalali_datetime(obj.reserved_at)


# =========================
# Food Reservation Settings
# =========================

@admin.register(FoodReservationSettings)
class FoodReservationSettingsAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "cutoff_hour",
        "cutoff_minute",
        "is_active",
        "updated_at",
    )

    list_display_links = (
        "id",
    )

    list_editable = (
        "cutoff_hour",
        "cutoff_minute",
        "is_active",
    )

    readonly_fields = (
        "updated_at",
    )

    def has_add_permission(self, request):
        if FoodReservationSettings.objects.exists():
            return False

        return super().has_add_permission(request)


# =========================
# Department Teams
# =========================

@admin.register(DepartmentTeam)
class DepartmentTeamAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "code",
        "is_active",
        "sort_order",
        "updated_at",
    )

    list_display_links = (
        "id",
        "title",
    )

    list_editable = (
        "is_active",
        "sort_order",
    )

    search_fields = (
        "title",
        "code",
    )

    list_filter = (
        "is_active",
    )

    readonly_fields = (
        "created_at",
        "updated_at",
    )

    ordering = (
        "sort_order",
        "id",
    )
# =========================
# Employee Users
# =========================

class EmployeeUserAdminForm(forms.ModelForm):
    ACCESS_LEVEL_CHOICES = (
        ("", "—"),
        ("user", "کاربر"),
        ("admin", "ادمین"),
    )

    STATUS_CHOICES = (
        ("pending", "در انتظار تایید"),
        ("approved", "تایید شده"),
        ("rejected", "رد شده"),
    )

    access_level = forms.ChoiceField(
        choices=ACCESS_LEVEL_CHOICES,
        required=False,
        label="سطح دسترسی",
    )

    status = forms.ChoiceField(
        choices=STATUS_CHOICES,
        required=True,
        label="وضعیت تایید",
    )

    department = forms.ChoiceField(
        choices=(),
        required=False,
        label="تیم",
    )

    class Meta:
        model = EmployeeUser
        fields = "__all__"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        team_choices = [("", "—")]

        for team in DepartmentTeam.objects.filter(is_active=True).order_by(
            "sort_order",
            "id",
        ):
            if team.code:
                team_choices.append((team.code, team.title))

        self.fields["department"].choices = team_choices


@admin.register(EmployeeUser)
class EmployeeUserAdmin(admin.ModelAdmin):
    form = EmployeeUserAdminForm

    list_display = (
        "id",
        "display_name",
        "telegram_user_id",
        "telegram_username",
        "status",
        "access_level",
        "admin_badge",
        "department_title",
    )

    list_display_links = (
        "id",
        "display_name",
    )

    # فقط این دو را مستقیم از جدول تغییر بده.
    # department را از صفحه جزئیات تغییر بده تا ارور admin.E122 نگیری.
    list_editable = (
        "status",
        "access_level",
    )

    list_filter = (
        "status",
        "access_level",
        "department",
    )

    search_fields = (
        "telegram_user_id",
        "username",
        "first_name",
        "last_name",
        "department",
    )

    readonly_fields = (
        "telegram_user_id",
        "username",
        "first_name",
        "last_name",
    )

    ordering = (
        "-access_level",
        "status",
        "department",
        "id",
    )

    list_per_page = 50

    actions = (
        "make_selected_admins",
        "make_selected_users",
        "approve_selected_users",
    )

    fieldsets = (
        (
            "اطلاعات تلگرام",
            {
                "fields": (
                    "telegram_user_id",
                    "username",
                    "first_name",
                    "last_name",
                )
            },
        ),
        (
            "دسترسی و تایید",
            {
                "fields": (
                    "status",
                    "access_level",
                    "department",
                )
            },
        ),
    )

    @admin.display(description="نام")
    def display_name(self, obj):
        full_name = f"{obj.first_name or ''} {obj.last_name or ''}".strip()

        if full_name:
            return full_name

        if obj.username:
            username = str(obj.username).strip()
            return username if username.startswith("@") else f"@{username}"

        return str(obj.telegram_user_id)

    @admin.display(description="یوزرنیم تلگرام")
    def telegram_username(self, obj):
        if not obj.username:
            return "—"

        username = str(obj.username).strip()
        return username if username.startswith("@") else f"@{username}"

    @admin.display(description="ادمین؟")
    def admin_badge(self, obj):
        if obj.access_level == "admin":
            return "✅ ادمین"

        return "—"

    @admin.display(description="تیم")
    def department_title(self, obj):
        if not obj.department:
            return "—"

        team = DepartmentTeam.objects.filter(code=obj.department).first()

        if team:
            return team.title

        return obj.department

    @admin.action(description="تبدیل کاربران انتخاب‌شده به ادمین")
    def make_selected_admins(self, request, queryset):
        count = queryset.update(
            access_level="admin",
            status="approved",
        )

        self.message_user(
            request,
            f"{to_persian_digits(count)} کاربر به ادمین تبدیل شد.",
            level=messages.SUCCESS,
        )

    @admin.action(description="تبدیل کاربران انتخاب‌شده به کاربر عادی")
    def make_selected_users(self, request, queryset):
        count = queryset.update(
            access_level="user",
            status="approved",
        )

        self.message_user(
            request,
            f"{to_persian_digits(count)} کاربر به کاربر عادی تبدیل شد.",
            level=messages.SUCCESS,
        )

    @admin.action(description="تایید کاربران انتخاب‌شده")
    def approve_selected_users(self, request, queryset):
        count = queryset.update(
            status="approved",
        )

        self.message_user(
            request,
            f"{to_persian_digits(count)} کاربر تایید شد.",
            level=messages.SUCCESS,
        )

    def has_add_permission(self, request):
        # کاربرها باید از بات / مینی‌اپ ساخته شوند، نه دستی از پنل.
        return False