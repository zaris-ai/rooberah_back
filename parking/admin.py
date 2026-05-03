from django.contrib import admin

from .models import (
    ParkingUnit,
    ParkingSpot,
    ParkingSession,
    WorkStatus,
    WeekMenu,
    FoodReservation,
)


# =========================
# Admin Site Titles
# =========================

admin.site.site_header = "پنل مدیریت"
admin.site.site_title = "مدیریت سامانه"
admin.site.index_title = "مدیریت وبگاه"
admin.site.empty_value_display = "—"


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


# =========================
# Parking Session
# =========================

@admin.register(ParkingSession)
class ParkingSessionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "telegram_user_id",
        "unit",
        "spot",
        "entered_at",
        "exited_at",
        "session_status",
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
        "entered_at",
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
                    "telegram_user_id",
                )
            },
        ),
        (
            "اطلاعات پارکینگ",
            {
                "fields": (
                    "unit",
                    "spot",
                )
            },
        ),
        (
            "زمان ورود و خروج",
            {
                "fields": (
                    "entered_at",
                    "exited_at",
                )
            },
        ),
    )

    @admin.display(description="وضعیت")
    def session_status(self, obj):
        if obj.exited_at:
            return "خارج شده"
        return "فعال"


from django import forms
from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import WorkStatus


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
        """
        فقط برای وضعیت‌های اصلی، زیر وضعیت‌ها را inline نشان بده.
        برای زیر وضعیت‌ها دوباره inline نشان نده.
        """
        if not obj:
            return []

        if obj.parent_id:
            return []

        return super().get_inline_instances(request, obj)

@admin.register(WeekMenu)
class WeekMenuAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "week_start_date",
        "day_of_week",
        "food1",
        "food2",
    )

    list_filter = (
        "week_start_date",
        "day_of_week",
    )

    search_fields = (
        "day_of_week",
        "food1",
        "food2",
    )

    ordering = (
        "-week_start_date",
        "id",
    )

    fieldsets = (
        (
            "اطلاعات برنامه غذایی",
            {
                "fields": (
                    "week_start_date",
                    "day_of_week",
                    "food1",
                    "food2",
                )
            },
        ),
    )


# =========================
# Food Reservation
# =========================

@admin.register(FoodReservation)
class FoodReservationAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "telegram_user_id",
        "week_start_date",
        "day_of_week",
        "food",
        "food_slot",
        "portion_label",
        "portion_qty",
        "reserved_at",
    )

    list_filter = (
        "week_start_date",
        "day_of_week",
        "portion_type",
    )

    search_fields = (
        "telegram_user_id",
        "food",
        "day_of_week",
    )

    readonly_fields = (
        "reserved_at",
    )

    ordering = (
        "-reserved_at",
        "id",
    )

    fieldsets = (
        (
            "اطلاعات کاربر",
            {
                "fields": (
                    "telegram_user_id",
                )
            },
        ),
        (
            "اطلاعات رزرو غذا",
            {
                "fields": (
                    "week_start_date",
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
                    "reserved_at",
                )
            },
        ),
    )