from django.db import transaction, IntegrityError
from django.utils import timezone
from rest_framework.decorators import api_view
from rest_framework.response import Response
from rest_framework import status
import json
import hmac
import hashlib
from urllib.parse import parse_qsl

from django.conf import settings
from .models import EmployeeUser, ParkingUnit, ParkingSpot, ParkingSession
from .serializers import (
    ParkingUnitSerializer,
    ParkingSpotSerializer,
    ActiveParkingSessionSerializer,
)


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


def get_telegram_user_id(request):
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

    active_sessions = {
        session.spot_id: session.telegram_user_id
        for session in ParkingSession.objects.filter(
            unit=unit,
            exited_at__isnull=True,
        )
    }

    serializer = ParkingSpotSerializer(
        spots,
        many=True,
        context={
            "telegram_user_id": telegram_user_id,
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