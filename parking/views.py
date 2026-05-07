from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status

import json
import hmac
import hashlib
from urllib.parse import parse_qsl
from datetime import date, datetime, time, timedelta

from django.conf import settings

from .models import (
    EmployeeUser,
    ParkingUnit,
    ParkingSpot,
    ParkingSession,
    WeekMenu,
    FoodReservation,
    FoodReservationSettings,
)

from .serializers import (
    ParkingUnitSerializer,
    ParkingSpotSerializer,
    ActiveParkingSessionSerializer,
    WeekMenuSerializer,
    FoodReservationSerializer,
)


# =========================
# Telegram Auth
# =========================

def verify_telegram_init_data(init_data: str):
    if not init_data:
        return None

    bot_token = settings.TELEGRAM_BOT_TOKEN
    if not bot_token:
        return None

    parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))

    received_hash = parsed_data.pop("hash", None)
    if not received_hash:
        return None

    data_check_string = "\n".join(
        f"{key}={value}" for key, value in sorted(parsed_data.items())
    )

    secret_key = hmac.new(
        key=b"WebAppData",
        msg=bot_token.encode(),
        digestmod=hashlib.sha256,
    ).digest()

    calculated_hash = hmac.new(
        key=secret_key,
        msg=data_check_string.encode(),
        digestmod=hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(calculated_hash, received_hash):
        return None

    user_raw = parsed_data.get("user")
    if not user_raw:
        return None

    try:
        user = json.loads(user_raw)
    except json.JSONDecodeError:
        return None

    return str(user.get("id")) if user.get("id") else None


def get_dev_telegram_user_id(request):
   
    if not settings.DEBUG:
        return None

    value = (
        request.headers.get("X-Dev-Telegram-User-Id")
        or request.GET.get("telegram_user_id")
    )

    if not value:
        return None

    value = str(value).strip()

    if not value.isdigit():
        return None

    return value


def get_telegram_user_id(request):
    dev_user_id = get_dev_telegram_user_id(request)

    if dev_user_id:
        print("[Telegram Auth] DEV bypass user_id:", dev_user_id)
        return dev_user_id

    init_data = request.headers.get("X-Telegram-Init-Data")
    telegram_user_id = verify_telegram_init_data(init_data)

    if telegram_user_id:
        print("[Telegram Auth] verified user_id:", telegram_user_id)
        return telegram_user_id

    print("[Telegram Auth] invalid or missing initData")
    return None


def require_approved_user(request):
    telegram_user_id = get_telegram_user_id(request)

    if not telegram_user_id:
        return None, Response(
            {
                "success": False,
                "message": "احراز هویت تلگرام نامعتبر است.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    user = EmployeeUser.objects.filter(
        telegram_user_id=str(telegram_user_id),
        status="approved",
    ).first()

    if not user:
        return None, Response(
            {
                "success": False,
                "message": "کاربر مجاز نیست یا هنوز تایید نشده است.",
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    return str(telegram_user_id), None


# =========================
# Parking APIs
# =========================

@api_view(["GET"])
def list_units(request):
    telegram_user_id, error_response = require_approved_user(request)
    if error_response:
        return error_response

    units = ParkingUnit.objects.filter(is_active=True)
    serializer = ParkingUnitSerializer(units, many=True)

    return Response(
        {
            "success": True,
            "units": serializer.data,
        }
    )


@api_view(["GET"])
def list_spots(request, unit_id):
    telegram_user_id, error_response = require_approved_user(request)
    if error_response:
        return error_response

    unit = ParkingUnit.objects.filter(id=unit_id, is_active=True).first()
    if not unit:
        return Response(
            {
                "success": False,
                "message": "واحد پارکینگ پیدا نشد.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    spots = ParkingSpot.objects.filter(unit=unit, is_active=True)

    active_session_rows = list(
        ParkingSession.objects.filter(
            unit=unit,
            exited_at__isnull=True,
        )
    )

    owner_ids = [
        str(session.telegram_user_id)
        for session in active_session_rows
        if session.telegram_user_id
    ]

    users_by_telegram_id = {
        str(user.telegram_user_id): user
        for user in EmployeeUser.objects.filter(
            telegram_user_id__in=owner_ids,
        )
    }

    active_sessions = {}

    for session in active_session_rows:
        owner_id = str(session.telegram_user_id)
        owner = users_by_telegram_id.get(owner_id)

        active_sessions[session.spot_id] = {
            "telegram_user_id": owner_id,
            "username": owner.username if owner else None,
            "first_name": owner.first_name if owner else None,
            "last_name": owner.last_name if owner else None,
        }

    serializer = ParkingSpotSerializer(
        spots,
        many=True,
        context={
            "telegram_user_id": str(telegram_user_id),
            "active_sessions": active_sessions,
        },
    )

    return Response(
        {
            "success": True,
            "unit": ParkingUnitSerializer(unit).data,
            "spots": serializer.data,
        }
    )
@api_view(["GET"])
def active_session(request):
    telegram_user_id, error_response = require_approved_user(request)
    if error_response:
        return error_response

    session = (
        ParkingSession.objects
        .select_related("unit", "spot")
        .filter(
            telegram_user_id=telegram_user_id,
            exited_at__isnull=True,
        )
        .first()
    )

    if not session:
        return Response(
            {
                "success": True,
                "session": None,
            }
        )

    return Response(
        {
            "success": True,
            "session": ActiveParkingSessionSerializer(session).data,
        }
    )


@api_view(["POST"])
@transaction.atomic
def enter_spot(request, spot_id):
    telegram_user_id, error_response = require_approved_user(request)
    if error_response:
        return error_response

    spot = (
        ParkingSpot.objects
        .select_for_update()
        .select_related("unit")
        .filter(id=spot_id, is_active=True, unit__is_active=True)
        .first()
    )

    if not spot:
        return Response(
            {
                "success": False,
                "message": "جایگاه پارکینگ پیدا نشد.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    user_active_session = ParkingSession.objects.select_for_update().filter(
        telegram_user_id=telegram_user_id,
        exited_at__isnull=True,
    ).first()

    if user_active_session:
        return Response(
            {
                "success": False,
                "message": "شما هم‌اکنون یک جایگاه فعال دارید. ابتدا خروج را ثبت کنید.",
            },
            status=status.HTTP_409_CONFLICT,
        )

    spot_active_session = ParkingSession.objects.select_for_update().filter(
        spot=spot,
        exited_at__isnull=True,
    ).first()

    if spot_active_session:
        return Response(
            {
                "success": False,
                "message": "این جایگاه قبلاً اشغال شده است.",
            },
            status=status.HTTP_409_CONFLICT,
        )

    try:
        session = ParkingSession.objects.create(
            telegram_user_id=telegram_user_id,
            unit=spot.unit,
            spot=spot,
        )
    except IntegrityError:
        return Response(
            {
                "success": False,
                "message": "ثبت ورود امکان‌پذیر نیست. وضعیت جایگاه تغییر کرده است.",
            },
            status=status.HTTP_409_CONFLICT,
        )

    return Response(
        {
            "success": True,
            "message": "ورود شما با موفقیت ثبت شد.",
            "session": ActiveParkingSessionSerializer(session).data,
        },
        status=status.HTTP_201_CREATED,
    )


@api_view(["POST"])
@transaction.atomic
def exit_active_session(request):
    telegram_user_id, error_response = require_approved_user(request)
    if error_response:
        return error_response

    session = (
        ParkingSession.objects
        .select_for_update()
        .select_related("unit", "spot")
        .filter(
            telegram_user_id=telegram_user_id,
            exited_at__isnull=True,
        )
        .first()
    )

    if not session:
        return Response(
            {
                "success": False,
                "message": "هیچ جایگاه فعالی برای شما ثبت نشده است.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    session.exited_at = timezone.now()
    session.save(update_fields=["exited_at"])

    return Response(
        {
            "success": True,
            "message": "خروج شما با موفقیت ثبت شد.",
        }
    )


# =========================
# Food Helpers
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

DAY_OFFSETS = {
    "شنبه": 0,
    "یکشنبه": 1,
    "دوشنبه": 2,
    "سه شنبه": 3,
    "سه‌شنبه": 3,
    "چهارشنبه": 4,
    "پنج شنبه": 5,
    "پنج‌شنبه": 5,
}

PORTION_META = {
    "full": {
        "label": "پرس کامل",
        "qty": 1,
    },
    "half": {
        "label": "نیم پرس",
        "qty": 0.5,
    },
    "khorak": {
        "label": "خوراک",
        "qty": 1,
    },
}

DEFAULT_FOOD_MODIFY_CUTOFF_HOUR = 19
DEFAULT_FOOD_MODIFY_CUTOFF_MINUTE = 0


def get_food_modify_cutoff():
    settings_row = (
        FoodReservationSettings.objects
        .filter(is_active=True)
        .order_by("-id")
        .first()
    )

    if not settings_row:
        return DEFAULT_FOOD_MODIFY_CUTOFF_HOUR, DEFAULT_FOOD_MODIFY_CUTOFF_MINUTE

    cutoff_hour = int(settings_row.cutoff_hour)
    cutoff_minute = int(settings_row.cutoff_minute)

    if cutoff_hour < 0 or cutoff_hour > 23:
        cutoff_hour = DEFAULT_FOOD_MODIFY_CUTOFF_HOUR

    if cutoff_minute < 0 or cutoff_minute > 59:
        cutoff_minute = DEFAULT_FOOD_MODIFY_CUTOFF_MINUTE

    return cutoff_hour, cutoff_minute


def normalize_day(value):
    return str(value or "").replace("‌", " ").strip()


def parse_date_value(value):
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    if isinstance(value, str):
        try:
            return date.fromisoformat(value)
        except ValueError:
            return None

    return None


def get_current_week_start():
    """
    هفته غذایی از شنبه شروع می‌شود.

    Python weekday:
    Monday=0
    Tuesday=1
    Wednesday=2
    Thursday=3
    Friday=4
    Saturday=5
    Sunday=6
    """
    today = timezone.localdate()
    days_since_saturday = (today.weekday() - 5) % 7
    return today - timedelta(days=days_since_saturday)


def get_default_food_week_start():
    """
    انتخاب هفته پیش‌فرض برای غذا.

    اولویت:
    1. هفته فعلی، اگر در دیتابیس منو دارد.
    2. آخرین هفته گذشته یا فعلی.
    3. اگر فقط هفته آینده ثبت شده بود، همان هفته آینده به عنوان fallback.
    """
    current_week_start = get_current_week_start()

    current_week_exists = WeekMenu.objects.filter(
        week_start_date=current_week_start
    ).exists()

    if current_week_exists:
        return current_week_start

    previous_or_current_week = (
        WeekMenu.objects
        .filter(week_start_date__lte=current_week_start)
        .order_by("-week_start_date")
        .values_list("week_start_date", flat=True)
        .first()
    )

    if previous_or_current_week:
        return previous_or_current_week

    fallback_week = (
        WeekMenu.objects
        .order_by("week_start_date")
        .values_list("week_start_date", flat=True)
        .first()
    )

    return fallback_week


def resolve_week_start(request):
    week_start = (
        request.GET.get("week_start_date")
        or request.data.get("weekStartDate")
        or request.data.get("week_start_date")
    )

    if week_start:
        return week_start

    return get_default_food_week_start()


def sort_week_menu_rows(rows):
    return sorted(
        rows,
        key=lambda item: DAY_ORDER.get(normalize_day(item.day_of_week), 99),
    )


def get_food_from_menu(menu_item, food_slot):
    if food_slot == "f1":
        return menu_item.food1

    if food_slot == "f2":
        return menu_item.food2
    if food_slot == "f3":
        return menu_item.food3

    return None


def get_food_target_date(week_start_date, day_of_week):
    parsed_week_start = parse_date_value(week_start_date)
    normalized_day = normalize_day(day_of_week)

    if not parsed_week_start:
        return None

    offset = DAY_OFFSETS.get(normalized_day)

    if offset is None:
        return None

    return parsed_week_start + timedelta(days=offset)


def get_food_modify_deadline(week_start_date, day_of_week):
    target_date = get_food_target_date(week_start_date, day_of_week)

    if not target_date:
        return None

    cutoff_hour, cutoff_minute = get_food_modify_cutoff()
    deadline_date = target_date - timedelta(days=1)

    naive_deadline = datetime.combine(
        deadline_date,
        time(hour=cutoff_hour, minute=cutoff_minute),
    )

    return timezone.make_aware(
        naive_deadline,
        timezone.get_current_timezone(),
    )

def can_modify_food_reservation(week_start_date, day_of_week):
    target_date = get_food_target_date(week_start_date, day_of_week)

    if not target_date:
        return False

    now = timezone.localtime(timezone.now())
    today = now.date()

    # روزهای گذشته همیشه بسته‌اند
    if target_date < today:
        return False

    # روزهای آینده باز هستند
    if target_date > today:
        return True

    # امروز فقط تا قبل از ساعت cutoff باز است
    deadline = get_food_modify_deadline(week_start_date, day_of_week)

    if not deadline:
        return False

    return now < deadline


def get_food_deadline_message(day_of_week):
    cutoff_hour, cutoff_minute = get_food_modify_cutoff()
    cutoff = f"{cutoff_hour:02d}:{cutoff_minute:02d}"

    return (
        f"مهلت ثبت، ویرایش یا لغو غذای روز {day_of_week} تمام شده است. "
        f"رزرو هر روز فقط تا ساعت {cutoff} روز قبل قابل تغییر است."
    )


# =========================
# Food APIs
# =========================

@api_view(["GET"])
def food_week_menu(request):
    telegram_user_id, error_response = require_approved_user(request)
    if error_response:
        return error_response

    week_start = request.GET.get("week_start_date") or get_default_food_week_start()

    if week_start:
        queryset = WeekMenu.objects.filter(week_start_date=week_start)
    else:
        queryset = WeekMenu.objects.none()

    rows = sort_week_menu_rows(list(queryset))
    serializer = WeekMenuSerializer(rows, many=True)

    menu_data = list(serializer.data)

    for index, row in enumerate(rows):
        deadline = get_food_modify_deadline(
            row.week_start_date,
            row.day_of_week,
        )

        menu_data[index]["canModify"] = can_modify_food_reservation(
            row.week_start_date,
            row.day_of_week,
        )

        menu_data[index]["modifyDeadline"] = (
            deadline.isoformat() if deadline else None
        )

        menu_data[index]["weekStartDate"] = str(row.week_start_date)

    return Response(
        {
            "success": True,
            "weekStartDate": str(week_start) if week_start else None,
            "menu": menu_data,
        }
    )


@api_view(["GET"])
def my_food_reservations(request):
    telegram_user_id, error_response = require_approved_user(request)
    if error_response:
        return error_response

    week_start = request.GET.get("week_start_date") or get_default_food_week_start()

    queryset = FoodReservation.objects.filter(
        telegram_user_id=str(telegram_user_id),
    )

    if week_start:
        queryset = queryset.filter(week_start_date=week_start)

    reservations = list(queryset.order_by("week_start_date", "id"))
    reservations.sort(
        key=lambda item: DAY_ORDER.get(normalize_day(item.day_of_week), 99)
    )

    serializer = FoodReservationSerializer(reservations, many=True)

    return Response(
        {
            "success": True,
            "weekStartDate": str(week_start) if week_start else None,
            "reservations": serializer.data,
        }
    )


@api_view(["POST"])
@transaction.atomic
def upsert_food_reservation(request):
    telegram_user_id, error_response = require_approved_user(request)
    if error_response:
        return error_response

    day_of_week = normalize_day(
        request.data.get("dayOfWeek") or request.data.get("day_of_week")
    )

    food_slot = request.data.get("foodSlot") or request.data.get("food_slot")

    portion_type = (
        request.data.get("portionType")
        or request.data.get("portion_type")
        or "full"
    )

    week_start = resolve_week_start(request)

    if not week_start:
        return Response(
            {
                "success": False,
                "message": "برای این هفته برنامه غذایی ثبت نشده است.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if not day_of_week:
        return Response(
            {
                "success": False,
                "message": "روز هفته ارسال نشده است.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if food_slot not in ("f1", "f2", "f3"):
        return Response(
            {
                "success": False,
                "message": "انتخاب غذا نامعتبر است.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    if portion_type not in PORTION_META:
        return Response(
            {
                "success": False,
                "message": "نوع پرس نامعتبر است.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # روزهای قبل و امروز بعد از ساعت cutoff قابل ثبت/ویرایش نیستند.
    if not can_modify_food_reservation(week_start, day_of_week):
        return Response(
            {
                "success": False,
                "message": get_food_deadline_message(day_of_week),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    menu_item = None

    for item in WeekMenu.objects.filter(week_start_date=week_start):
        if normalize_day(item.day_of_week) == day_of_week:
            menu_item = item
            break

    if not menu_item:
        return Response(
            {
                "success": False,
                "message": "برای این روز منوی غذایی ثبت نشده است.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    selected_food = get_food_from_menu(menu_item, food_slot)

    if not selected_food:
        return Response(
            {
                "success": False,
                "message": "غذای انتخاب‌شده برای این روز ثبت نشده است.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    portion = PORTION_META[portion_type]

    existing_qs = FoodReservation.objects.select_for_update().filter(
        telegram_user_id=str(telegram_user_id),
        week_start_date=week_start,
        day_of_week=menu_item.day_of_week,
    ).order_by("id")

    reservation = existing_qs.first()

    if reservation:
        reservation.food = selected_food
        reservation.food_slot = food_slot
        reservation.portion_type = portion_type
        reservation.portion_label = portion["label"]
        reservation.portion_qty = portion["qty"]
        reservation.reserved_at = timezone.now()

        reservation.save(
            update_fields=[
                "food",
                "food_slot",
                "portion_type",
                "portion_label",
                "portion_qty",
                "reserved_at",
            ]
        )

        duplicate_ids = list(existing_qs.values_list("id", flat=True))[1:]

        if duplicate_ids:
            FoodReservation.objects.filter(id__in=duplicate_ids).delete()

        message = "رزرو غذا با موفقیت ویرایش شد."
    else:
        reservation = FoodReservation.objects.create(
            telegram_user_id=str(telegram_user_id),
            week_start_date=week_start,
            day_of_week=menu_item.day_of_week,
            food_slot=food_slot,
            food=selected_food,
            portion_type=portion_type,
            portion_label=portion["label"],
            portion_qty=portion["qty"],
            reserved_at=timezone.now(),
        )

        message = "رزرو غذا با موفقیت ثبت شد."

    return Response(
        {
            "success": True,
            "message": message,
            "weekStartDate": str(week_start),
            "reservation": FoodReservationSerializer(reservation).data,
        }
    )


@api_view(["POST"])
@transaction.atomic
def cancel_food_reservation(request):
    telegram_user_id, error_response = require_approved_user(request)
    if error_response:
        return error_response

    day_of_week = normalize_day(
        request.data.get("dayOfWeek") or request.data.get("day_of_week")
    )

    week_start = resolve_week_start(request)

    if not week_start:
        return Response(
            {
                "success": False,
                "message": "هفته موردنظر پیدا نشد.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    if not day_of_week:
        return Response(
            {
                "success": False,
                "message": "روز هفته ارسال نشده است.",
            },
            status=status.HTTP_400_BAD_REQUEST,
        )

    # روزهای قبل و امروز بعد از ساعت cutoff قابل لغو نیستند.
    if not can_modify_food_reservation(week_start, day_of_week):
        return Response(
            {
                "success": False,
                "message": get_food_deadline_message(day_of_week),
            },
            status=status.HTTP_403_FORBIDDEN,
        )

    queryset = FoodReservation.objects.filter(
        telegram_user_id=str(telegram_user_id),
        week_start_date=week_start,
    )

    matching_ids = [
        item.id
        for item in queryset
        if normalize_day(item.day_of_week) == day_of_week
    ]

    if not matching_ids:
        return Response(
            {
                "success": False,
                "message": "برای این روز رزروی ثبت نشده است.",
            },
            status=status.HTTP_404_NOT_FOUND,
        )

    FoodReservation.objects.filter(id__in=matching_ids).delete()

    return Response(
        {
            "success": True,
            "message": f"رزرو روز {day_of_week} لغو شد.",
            "weekStartDate": str(week_start),
        }
    )