from django.contrib import admin
from .models import ParkingUnit, ParkingSpot, ParkingSession


@admin.register(ParkingUnit)
class ParkingUnitAdmin(admin.ModelAdmin):
    list_display = ["id", "title", "sort_order", "is_active"]
    list_editable = ["sort_order", "is_active"]


@admin.register(ParkingSpot)
class ParkingSpotAdmin(admin.ModelAdmin):
    list_display = ["id", "unit", "code", "row", "col", "is_active"]
    list_filter = ["unit", "is_active"]
    search_fields = ["code"]


@admin.register(ParkingSession)
class ParkingSessionAdmin(admin.ModelAdmin):
    list_display = ["id", "telegram_user_id", "unit", "spot", "entered_at", "exited_at"]
    list_filter = ["unit", "spot", "exited_at"]
    search_fields = ["telegram_user_id", "spot__code"]
from django.contrib import admin
from .models import WorkStatus


@admin.register(WorkStatus)
class WorkStatusAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "emoji",
        "title",
        "code",
        "is_active",
        "sort_order",
        "updated_at",
    )
    list_filter = ("is_active",)
    search_fields = ("code", "title")
    ordering = ("sort_order", "id")
    list_editable = ("is_active", "sort_order")
    readonly_fields = ("created_at", "updated_at")

    fieldsets = (
        (
            "اطلاعات وضعیت",
            {
                "fields": (
                    "code",
                    "title",
                    "emoji",
                    "is_active",
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

        # اگر وضعیت قبلاً ساخته شده، code را قفل کن.
        # چون user_current_status با همین code ذخیره می‌شود.
        if obj:
            readonly_fields.append("code")

        return readonly_fields