import json
import logging
import os
import math
import re
import secrets
from collections import Counter
from io import BytesIO
from pathlib import Path
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone

from fastapi import Cookie, Depends, FastAPI, Header, HTTPException, Query, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from openai import OpenAI, OpenAIError
from PIL import Image, ImageOps, UnidentifiedImageError
from pydantic import BaseModel, Field as PField
from sqlalchemy import and_, func, or_
from sqlalchemy.exc import IntegrityError
from sqlmodel import Session, select

from database import as_utc, create_db, get_session, iso_utc, utc_now
from models import AuthSession, BatchPublish, Building, Comment, Community, CommunityMember, CommunityProfile, HandoverSlot, Interest, Item, ItemEvent, ItemPassport, ItemView, Need, NeedMatch, NeedReply, PrivateMessage, Reservation, Transaction, UploadedImage, User, UserPreference, UserPresence
from auth import COOKIE_NAME, TOKEN_DAYS, current_user, demo_mode, hash_password, issue_token, optional_current_user, revoke_token, verify_password
from services.ai_pricing_service import pricing_suggestion
from services.item_events import PUBLIC_ACTIVITY_TYPES, activity_data, event_data, record_item_event
from services.need_matching_service import match_need, need_is_active
from services.need_parser_service import parse_need
from services.visual_analysis_service import analyze_batch, analyze_item

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    create_db()
    yield


app = FastAPI(title="NeighLoop API", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[origin.strip() for origin in os.getenv("CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",")],
    allow_credentials=True,
    allow_methods=["GET", "POST", "PATCH", "DELETE"],
    allow_headers=["*"],
)

CATEGORIES = ["家居", "家电", "图书", "绿植", "母婴", "运动", "生活用品"]
TRADE_TYPES = {"FREE", "NEGOTIABLE", "FIXED_PRICE"}
UPLOAD_DIR = Path(os.getenv("UPLOAD_DIR", str(Path(__file__).resolve().parent / "uploads")))
IMAGE_TYPES = {"image/jpeg": ("jpg", b"\xff\xd8\xff"), "image/png": ("png", b"\x89PNG\r\n\x1a\n"),
               "image/webp": ("webp", b"RIFF")}
MAX_IMAGE_BYTES = 12 * 1024 * 1024


class SlotInput(BaseModel):
    starts_at: datetime
    ends_at: datetime


class ItemInput(BaseModel):
    title: str = PField(min_length=2, max_length=60)
    description: str = PField(min_length=4, max_length=1000)
    category: str = PField(min_length=1, max_length=30)
    condition: str = PField(min_length=2, max_length=30)
    trade_type: str
    price: int | None = PField(default=None, ge=0, le=100000)
    original_price: int | None = PField(default=None, ge=0, le=100000)
    building_id: int
    image_key: int = PField(default=0, ge=0, le=999999999999)
    brand: str | None = PField(default=None, max_length=60)
    model_name: str | None = PField(default=None, max_length=60)
    disposal_goal: str = "BALANCED"
    handover_location: str | None = PField(default=None, max_length=100)
    handover_slots: list[SlotInput] = PField(default_factory=list, max_length=5)
    selected_price_strategy: str | None = None
    selected_price_source: str | None = None


class VisualEstimateInput(BaseModel):
    image_keys: list[int] = PField(min_length=2, max_length=5)
    disposal_goal: str = "BALANCED"
    functional_confirmed: bool = False
    no_hidden_defects_confirmed: bool = False


class BatchRecognizeInput(BaseModel):
    image_keys: list[int] = PField(min_length=2, max_length=20)
    disposal_goal: str = "BALANCED"


class BatchPublishInput(BaseModel):
    items: list[ItemInput] = PField(min_length=1, max_length=20)
    confirmed: bool = False


class NeedInput(BaseModel):
    raw_text: str = PField(min_length=2, max_length=500)
    category: str | None = PField(default=None, max_length=30)
    keywords: list[str] = PField(default_factory=list, max_length=8)
    budget_min: int | None = PField(default=None, ge=0, le=100000)
    budget_max: int | None = PField(default=None, ge=0, le=100000)
    building_id: int | None = None
    expires_at: datetime | None = None


class NeedUpdateInput(BaseModel):
    status: str


class NeedReplyInput(BaseModel):
    body: str = PField(min_length=1, max_length=500)
    item_id: int | None = None


class CommentInput(BaseModel):
    body: str = PField(min_length=1, max_length=500)


class PrivateMessageInput(BaseModel):
    other_user_id: int
    body: str = PField(min_length=1, max_length=500)


class FaqInput(BaseModel):
    other_user_id: int
    question: str = PField(min_length=2, max_length=200)


class CompleteInput(BaseModel):
    recipient_id: int


class ReservationInput(BaseModel):
    slot_id: int


class PickupInput(BaseModel):
    pickup_code: str = PField(min_length=4, max_length=4)


class HandoverStatusInput(BaseModel):
    status: str


class DescriptionInput(BaseModel):
    title: str = PField(min_length=2, max_length=60)
    rough_description: str = PField(min_length=4, max_length=500)
    condition: str = PField(min_length=2, max_length=30)


class PriceInput(BaseModel):
    title: str = PField(min_length=2, max_length=60)
    description: str = PField(min_length=4, max_length=500)
    category: str
    condition: str = PField(min_length=2, max_length=30)
    original_price: int | None = PField(default=None, ge=0, le=100000)


class PricingStrategyInput(PriceInput):
    disposal_goal: str = "BALANCED"


class CommunityInput(BaseModel):
    name: str = PField(min_length=2, max_length=50)
    kind: str
    city: str = PField(min_length=2, max_length=50)
    district: str = PField(default="", max_length=50)
    address: str | None = PField(default=None, max_length=120)
    location_names: list[str] = PField(min_length=1, max_length=8)
    is_public: bool = False
    latitude: float | None = PField(default=None, ge=-90, le=90)
    longitude: float | None = PField(default=None, ge=-180, le=180)


class JoinCommunityInput(BaseModel):
    join_code: str = PField(min_length=4, max_length=20)
    building_id: int


class RegisterInput(BaseModel):
    email: str = PField(min_length=5, max_length=254)
    password: str = PField(min_length=8, max_length=128)


class LoginInput(BaseModel):
    email: str
    password: str


class DemoLoginInput(BaseModel):
    user_id: int


class PreferenceInput(BaseModel):
    goals: list[str] = PField(default_factory=list, max_length=3)
    categories: list[str] = PField(default_factory=list, max_length=10)
    trade_preferences: list[str] = PField(default_factory=list, max_length=4)
    use_distance: bool = False


class MyCommunityInput(BaseModel):
    community_id: int
    building_id: int | None = None
    join_code: str | None = None


class LocationInput(BaseModel):
    latitude: float = PField(ge=-90, le=90)
    longitude: float = PField(ge=-180, le=180)
    accuracy: float | None = PField(default=None, ge=0)


class ProfileInput(BaseModel):
    nickname: str = PField(min_length=1, max_length=24)


def current_community_id(
    request: Request,
    x_community_id: int = Header(default=1),
    session: Session = Depends(get_session),
    user: User | None = Depends(optional_current_user),
) -> int:
    if not session.get(Community, x_community_id):
        raise HTTPException(404, "社区不存在")
    membership = session.exec(select(CommunityMember).where(
        CommunityMember.community_id == x_community_id, CommunityMember.user_id == user.id
    )).first() if user else None
    if request.method == "GET":
        profile = session.exec(select(CommunityProfile).where(CommunityProfile.community_id == x_community_id)).first()
        if membership or (profile and profile.is_public):
            return x_community_id
        raise HTTPException(403, "请先加入这个社区")
    if not user:
        raise HTTPException(401, "请先登录")
    if not membership:
        raise HTTPException(403, "你尚未加入这个社区")
    return x_community_id


def request_location(x_location_latitude: float | None = Header(default=None),
                     x_location_longitude: float | None = Header(default=None)) -> tuple[float, float] | None:
    if x_location_latitude is None or x_location_longitude is None:
        return None
    if not -90 <= x_location_latitude <= 90 or not -180 <= x_location_longitude <= 180:
        return None
    return x_location_latitude, x_location_longitude


def building_distance(session: Session, building: Building,
                      location: tuple[float, float] | None) -> int | None:
    if not location:
        return None
    latitude, longitude = building.latitude, building.longitude
    if latitude is None or longitude is None:
        profile = session.exec(select(CommunityProfile).where(CommunityProfile.community_id == building.community_id)).first()
        latitude = profile.latitude if profile else None
        longitude = profile.longitude if profile else None
    if latitude is None or longitude is None:
        return None
    return approximate_distance_meters(location[0], location[1], latitude, longitude)


def community_data(session: Session, community: Community, user_id: int | None) -> dict:
    profile = session.exec(select(CommunityProfile).where(CommunityProfile.community_id == community.id)).first()
    membership = session.exec(select(CommunityMember).where(
        CommunityMember.community_id == community.id, CommunityMember.user_id == user_id
    )).first() if user_id else None
    buildings = session.exec(select(Building).where(Building.community_id == community.id).order_by(Building.id)).all()
    return {
        "id": community.id, "name": community.name,
        "kind": profile.kind if profile else "NEIGHBORHOOD",
        "city": profile.city if profile else "", "district": profile.district if profile else "",
        "address": profile.address if profile else None,
        "is_public": profile.is_public if profile else False,
        "joined": bool(membership), "role": membership.role if membership else None,
        "member_building_id": membership.building_id if membership else None,
        "join_code": profile.join_code if membership and profile else None,
        "buildings": [{"id": b.id, "name": b.name, "map_key": b.map_key,
                       "map_x": b.map_x, "map_y": b.map_y} for b in buildings],
    }


def get_item_or_404(session: Session, item_id: int, community_id: int) -> Item:
    item = session.get(Item, item_id)
    if not item or session.get(Building, item.building_id).community_id != community_id:
        raise HTTPException(404, "物品不存在")
    return item


def get_reservation_or_404(session: Session, reservation_id: int, community_id: int) -> tuple[Reservation, Item]:
    reservation = session.get(Reservation, reservation_id)
    if not reservation:
        raise HTTPException(404, "预约不存在")
    item = get_item_or_404(session, reservation.item_id, community_id)
    return reservation, item


def ensure_passport(session: Session, item: Item) -> ItemPassport:
    if item.passport_id:
        return session.get(ItemPassport, item.passport_id)
    passport = session.exec(select(ItemPassport).where(ItemPassport.root_item_id == item.id)).first()
    if not passport:
        passport = ItemPassport(root_item_id=item.id, passport_code=f"NL-{item.id:05d}",
                                created_at=item.created_at)
        session.add(passport)
        session.flush()
    item.passport_id = passport.id
    session.add(item)
    return passport


def cancel_reservation_record(session: Session, reservation: Reservation, item: Item,
                              actor_id: int, reason: str) -> None:
    was_confirmed = reservation.status == "CONFIRMED"
    reservation.status = "CANCELLED"
    reservation.pickup_code = None
    if was_confirmed:
        item.status = "AVAILABLE"
        session.add(item)
    session.add(reservation)
    record_item_event(session, item.id, "RESERVATION_CANCELLED", actor_id,
                      {"reservation_id": reservation.id, "reason": reason})
    other_id = reservation.buyer_id if actor_id == reservation.seller_id else reservation.seller_id
    private_notice(session, item.id, actor_id, other_id, "这次预约已取消，物品状态已更新。", "RESERVATION")


def user_data(user: User) -> dict:
    return {"id": user.id, "display_name": user.display_name, "building_id": user.building_id, "avatar_color": user.avatar_color}


def auth_user_data(user: User) -> dict:
    return {**user_data(user), "email": user.email, "nickname": user.nickname or user.display_name,
            "avatar_url": user.avatar_url, "community_id": user.community_id,
            "onboarding_completed": user.onboarding_completed,
            "product_tour_completed": user.product_tour_completed}


def preference_data(preference: UserPreference | None) -> dict:
    return {"goals": preference.goals if preference else [],
            "categories": preference.categories if preference else [],
            "trade_preferences": preference.trade_preferences if preference else [],
            "use_distance": preference.use_distance if preference else False}


def effective_status(item: Item) -> str:
    if item.status in {"RESERVED", "COMPLETED", "ARCHIVED"}:
        return item.status
    confirmed = item.last_confirmed_at or item.created_at
    return "UNCONFIRMED" if utc_now() - as_utc(confirmed) > timedelta(hours=72) else "AVAILABLE"


def slot_data(slot: HandoverSlot) -> dict:
    return {"id": slot.id, "starts_at": iso_utc(slot.starts_at), "ends_at": iso_utc(slot.ends_at)}


def reservation_data(session: Session, reservation: Reservation, viewer_id: int) -> dict:
    slot = session.get(HandoverSlot, reservation.slot_id)
    buyer = session.get(User, reservation.buyer_id)
    now = utc_now()
    starts_at = as_utc(slot.starts_at)
    overdue_at = starts_at + timedelta(minutes=15)
    if reservation.wait_until and as_utc(reservation.wait_until) > overdue_at:
        overdue_at = as_utc(reservation.wait_until)
    return {
        "id": reservation.id, "item_id": reservation.item_id,
        "buyer": user_data(buyer), "seller_id": reservation.seller_id,
        "slot": slot_data(slot), "status": reservation.status,
        "pickup_code": reservation.pickup_code if viewer_id == reservation.buyer_id and reservation.status == "CONFIRMED" else None,
        "created_at": iso_utc(reservation.created_at),
        "confirmed_at": iso_utc(reservation.confirmed_at),
        "completed_at": iso_utc(reservation.completed_at),
        "handover_status": reservation.handover_status or "WAITING",
        "arrived_at": iso_utc(reservation.arrived_at),
        "delay_minutes": reservation.delay_minutes or 0,
        "wait_until": iso_utc(reservation.wait_until),
        "overdue": reservation.status == "CONFIRMED" and now >= overdue_at,
        "minutes_past_slot": max(0, int((now - starts_at).total_seconds() // 60)),
    }


def validate_slots(slots: list[SlotInput]) -> list[tuple[datetime, datetime]]:
    if len(slots) > 5:
        raise HTTPException(422, "最多添加 5 个交接时间")
    normalized = []
    for slot in slots:
        if slot.starts_at.tzinfo is None or slot.ends_at.tzinfo is None:
            raise HTTPException(422, "交接时间需要包含时区")
        start = slot.starts_at.astimezone(timezone.utc)
        end = slot.ends_at.astimezone(timezone.utc)
        if start <= utc_now() or end <= start or end - start > timedelta(hours=3):
            raise HTTPException(422, "请选择未来的有效交接时间，单个时段不超过 3 小时")
        normalized.append((start, end))
    normalized.sort()
    for previous, current in zip(normalized, normalized[1:]):
        if current[0] < previous[1]:
            raise HTTPException(422, "交接时间段不能重叠")
    return normalized


def item_base(item: Item, owner: User, building: Building, interest_count: int,
              interested: bool, next_slot_at: datetime | None = None,
              scheduled_handover_at: datetime | None = None,
              distance_meters: int | None = None) -> dict:
    return {
        "id": item.id,
        "owner": user_data(owner),
        "building_id": item.building_id,
        "building_name": building.name,
        "title": item.title,
        "description": item.description,
        "category": item.category,
        "condition": item.condition,
        "brand": item.brand,
        "model_name": item.model_name,
        "trade_type": item.trade_type,
        "price": item.price,
        "original_price": item.original_price,
        "image_key": item.image_key,
        "status": effective_status(item),
        "stored_status": item.status,
        "disposal_goal": item.disposal_goal,
        "last_confirmed_at": iso_utc(item.last_confirmed_at or item.created_at),
        "public_location": item.public_location or f"{building.name}附近",
        "visible_location": item.public_location or f"{building.name}附近",
        "handover_location": None,
        "passport_code": None,
        "distance_meters": distance_meters,
        "next_slot_at": iso_utc(next_slot_at),
        "scheduled_handover_at": iso_utc(scheduled_handover_at),
        "created_at": iso_utc(item.created_at),
        "completed_at": iso_utc(item.completed_at),
        "interest_count": interest_count,
        "viewer_interested": interested,
    }


def item_data(session: Session, item: Item, viewer_id: int | None = None,
              location: tuple[float, float] | None = None) -> dict:
    owner = session.get(User, item.owner_id)
    building = session.get(Building, item.building_id)
    count = session.exec(select(func.count(Interest.id)).where(Interest.item_id == item.id)).one()
    interested = bool(viewer_id and session.exec(
        select(Interest.id).where(Interest.item_id == item.id, Interest.user_id == viewer_id)
    ).first())
    next_slot = session.exec(select(HandoverSlot).where(HandoverSlot.item_id == item.id,
                    HandoverSlot.starts_at > utc_now()).order_by(HandoverSlot.starts_at)).first()
    confirmed = session.exec(select(Reservation).where(Reservation.item_id == item.id,
                              Reservation.status == "CONFIRMED")).first()
    booked_slot = session.get(HandoverSlot, confirmed.slot_id) if confirmed else None
    result = item_base(item, owner, building, count, interested, next_slot.starts_at if next_slot else None,
                       booked_slot.starts_at if booked_slot else None, building_distance(session, building, location))
    if viewer_id == item.owner_id:
        result["handover_location"] = item.handover_location
        result["visible_location"] = item.handover_location or f"{building.name}公共区域"
    elif viewer_id:
        reservation = session.exec(select(Reservation).where(Reservation.item_id == item.id,
            Reservation.buyer_id == viewer_id, Reservation.status.in_(["PENDING", "CONFIRMED"]))).first()
        if reservation:
            result["visible_location"] = f"{building.name}公共区域"
            if reservation.status == "CONFIRMED":
                result["handover_location"] = item.handover_location
                result["visible_location"] = item.handover_location or f"{building.name}公共区域"
    if item.passport_id:
        passport = session.get(ItemPassport, item.passport_id)
        result["passport_code"] = passport.passport_code if passport else None
        latest = session.exec(select(Item).where(Item.passport_id == item.passport_id)
                              .order_by(Item.created_at.desc(), Item.id.desc())).first()
        transaction = session.exec(select(Transaction).where(Transaction.item_id == item.id)).first()
        result["viewer_can_relist"] = bool(viewer_id and latest and latest.id == item.id and
                                           item.status == "COMPLETED" and transaction and
                                           transaction.recipient_id == viewer_id)
    else:
        result["viewer_can_relist"] = False
    return result


def items_data(session: Session, items: list[Item], viewer_id: int | None = None,
               location: tuple[float, float] | None = None) -> list[dict]:
    if not items:
        return []
    item_ids = [item.id for item in items]
    owner_ids = {item.owner_id for item in items}
    building_ids = {item.building_id for item in items}
    owners = {owner.id: owner for owner in session.exec(select(User).where(User.id.in_(owner_ids))).all()}
    buildings = {building.id: building for building in session.exec(select(Building).where(Building.id.in_(building_ids))).all()}
    counts = dict(session.exec(
        select(Interest.item_id, func.count(Interest.id)).where(Interest.item_id.in_(item_ids)).group_by(Interest.item_id)
    ).all())
    interested_ids = set()
    if viewer_id:
        interested_ids = set(session.exec(
            select(Interest.item_id).where(Interest.item_id.in_(item_ids), Interest.user_id == viewer_id)
        ).all())
    slots = session.exec(select(HandoverSlot).where(HandoverSlot.item_id.in_(item_ids),
                         HandoverSlot.starts_at > utc_now()).order_by(HandoverSlot.starts_at)).all()
    next_slots: dict[int, datetime] = {}
    for slot in slots:
        next_slots.setdefault(slot.item_id, slot.starts_at)
    reservations = session.exec(select(Reservation).where(Reservation.item_id.in_(item_ids),
                                 Reservation.status == "CONFIRMED")).all()
    booked_slots = {slot.id: slot for slot in session.exec(select(HandoverSlot).where(
        HandoverSlot.id.in_([reservation.slot_id for reservation in reservations]))).all()} if reservations else {}
    scheduled = {reservation.item_id: booked_slots[reservation.slot_id].starts_at for reservation in reservations
                 if reservation.slot_id in booked_slots}
    return [item_base(item, owners[item.owner_id], buildings[item.building_id],
                      counts.get(item.id, 0), item.id in interested_ids, next_slots.get(item.id),
                      scheduled.get(item.id), building_distance(session, buildings[item.building_id], location)) for item in items]


def validate_item_input(data: ItemInput, session: Session, community_id: int, user_id: int) -> None:
    if not data.category.strip():
        raise HTTPException(422, "请填写物品类别")
    if data.condition.strip() == "待确认":
        raise HTTPException(422, "请确认物品实际成色后再发布")
    if data.image_key > 35:
        image = session.get(UploadedImage, data.image_key)
        if not image or image.owner_id != user_id or image.community_id != community_id:
            raise HTTPException(422, "请选择自己在当前社区上传的照片")
    if data.trade_type not in TRADE_TYPES:
        raise HTTPException(422, "无效的交易方式")
    if data.trade_type == "FIXED_PRICE" and (data.price is None or data.price <= 0):
        raise HTTPException(422, "标价物品需要填写大于 0 的价格")
    if data.disposal_goal not in {"FAST", "BALANCED", "PRICE_FIRST"}:
        raise HTTPException(422, "无效的处理目标")
    if data.selected_price_strategy and data.selected_price_strategy not in {"FAST", "BALANCED", "PRICE_FIRST"}:
        raise HTTPException(422, "无效的定价策略")
    if data.selected_price_strategy and data.trade_type != "FIXED_PRICE":
        raise HTTPException(422, "选择定价策略后需要使用标价转让")
    if data.selected_price_source and data.selected_price_source not in {"DEEPSEEK", "RULE_FALLBACK"}:
        raise HTTPException(422, "无效的建议来源")
    if data.handover_location is not None and not data.handover_location.strip():
        raise HTTPException(422, "交接地点不能为空")
    if data.handover_location and re.search(r"\d{2,4}\s*(?:室|房|号房)", data.handover_location):
        raise HTTPException(422, "请使用大厅、门口或物业等公共交接点，不填写住宅门牌")
    building = session.get(Building, data.building_id)
    if not building or building.community_id != community_id:
        raise HTTPException(422, "请选择有效楼栋")


@app.get("/api/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/uploads/images", status_code=201)
async def upload_image(request: Request, session: Session = Depends(get_session),
                       user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    mime_type = request.headers.get("content-type", "").split(";", 1)[0].lower()
    if mime_type not in IMAGE_TYPES:
        raise HTTPException(415, "仅支持 JPG、PNG 或 WebP 照片")
    data = bytearray()
    async for chunk in request.stream():
        data.extend(chunk)
        if len(data) > MAX_IMAGE_BYTES:
            raise HTTPException(413, "照片不能超过 12 MB")
    _, signature = IMAGE_TYPES[mime_type]
    if not data.startswith(signature) or (mime_type == "image/webp" and data[8:12] != b"WEBP"):
        raise HTTPException(422, "图片内容与文件类型不符")
    try:
        with Image.open(BytesIO(data)) as source:
            if source.format not in {"JPEG", "PNG", "WEBP"} or source.width * source.height > 50_000_000:
                raise HTTPException(422, "图片格式或尺寸不受支持")
            image = ImageOps.exif_transpose(source)
            image.thumbnail((4096, 4096))
            cleaned = BytesIO()
            image.convert("RGB").save(cleaned, format="JPEG", quality=90, optimize=True)
            data = cleaned.getvalue()
    except (UnidentifiedImageError, OSError, ValueError):
        raise HTTPException(422, "图片文件无法读取") from None
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    image_key = 100_000_000_000 + secrets.randbelow(900_000_000_000)
    while session.get(UploadedImage, image_key):
        image_key = 100_000_000_000 + secrets.randbelow(900_000_000_000)
    filename = f"{image_key}.jpg"
    path = UPLOAD_DIR / filename
    path.write_bytes(data)
    try:
        session.add(UploadedImage(id=image_key, owner_id=user.id, community_id=community_id,
                                  filename=filename, mime_type="image/jpeg"))
        session.commit()
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return {"image_key": image_key, "url": f"/api/uploads/images/{image_key}"}


@app.get("/api/uploads/images/{image_key}")
def get_uploaded_image(image_key: int, session: Session = Depends(get_session),
                       user: User | None = Depends(optional_current_user)) -> FileResponse:
    image = session.get(UploadedImage, image_key)
    if not image:
        raise HTTPException(404, "图片不存在")
    profile = session.exec(select(CommunityProfile).where(CommunityProfile.community_id == image.community_id)).first()
    if not profile or not profile.is_public:
        member = session.exec(select(CommunityMember.id).where(CommunityMember.community_id == image.community_id,
                                                         CommunityMember.user_id == user.id)).first() if user else None
        if not member:
            raise HTTPException(403, "请先加入社区查看照片")
    path = UPLOAD_DIR / image.filename
    if not path.is_file():
        raise HTTPException(404, "图片文件不存在")
    return FileResponse(path, media_type=image.mime_type,
                        headers={"Cache-Control": "public, max-age=86400", "X-Content-Type-Options": "nosniff"})


def set_login_cookie(response: Response, token: str) -> None:
    response.set_cookie(COOKIE_NAME, token, httponly=True, secure=os.getenv("ENVIRONMENT") == "production",
                        samesite="lax", max_age=TOKEN_DAYS * 86400, path="/")


PUBLIC_DEMO_LABELS = {
    "test@example.com": "新用户引导",
    "returning@example.com": "已加入社区",
    "seller@neighloop.demo": "发布者",
    "buyer@neighloop.demo": "领取者",
}


def public_demo_enabled() -> bool:
    return os.getenv("NEIGHLOOP_PUBLIC_DEMO_MODE", "false").lower() == "true"


@app.get("/api/auth/demo-accounts")
def list_demo_accounts(session: Session = Depends(get_session)) -> list[dict]:
    if not public_demo_enabled():
        return []
    accounts = session.exec(select(User).where(User.email.in_(PUBLIC_DEMO_LABELS))).all()
    by_email = {user.email: user for user in accounts}
    return [{"id": by_email[email].id, "display_name": by_email[email].display_name, "role": role}
            for email, role in PUBLIC_DEMO_LABELS.items() if email in by_email]


@app.post("/api/auth/demo-login")
def demo_login(data: DemoLoginInput, request: Request, response: Response,
               token: str | None = Cookie(default=None, alias=COOKIE_NAME),
               session: Session = Depends(get_session)) -> dict:
    if not public_demo_enabled():
        raise HTTPException(404, "演示账号入口未启用")
    if request.headers.get("X-NeighLoop-Request") != "1":
        raise HTTPException(403, "缺少受保护的请求标记")
    user = session.get(User, data.user_id)
    if not user or user.email not in PUBLIC_DEMO_LABELS:
        raise HTTPException(403, "仅可切换到公开演示账号")
    revoke_token(session, token)
    issued = issue_token(session, user)
    set_login_cookie(response, issued)
    preference = session.exec(select(UserPreference).where(UserPreference.user_id == user.id)).first()
    return {"user": auth_user_data(user), "preferences": preference_data(preference)}


@app.post("/api/auth/register", status_code=201)
def register(data: RegisterInput, response: Response, session: Session = Depends(get_session)) -> dict:
    email = data.email.strip().lower()
    if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
        raise HTTPException(422, "请填写有效邮箱")
    if session.exec(select(User.id).where(User.email == email)).first():
        raise HTTPException(409, "这个邮箱已经注册")
    nickname = email.split("@", 1)[0][:24]
    user = User(email=email, password_hash=hash_password(data.password), display_name=nickname,
                nickname=nickname, avatar_color="#dbead9", building_id=None,
                onboarding_completed=False, product_tour_completed=False)
    try:
        session.add(user)
        session.flush()
        session.add(UserPreference(user_id=user.id))
        token = issue_token(session, user)
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "这个邮箱已经注册") from None
    set_login_cookie(response, token)
    return {"user": auth_user_data(user), "preferences": preference_data(None)}


@app.post("/api/auth/login")
def login(data: LoginInput, response: Response, session: Session = Depends(get_session)) -> dict:
    user = session.exec(select(User).where(User.email == data.email.strip().lower())).first()
    if not user or not user.password_hash or not verify_password(user.password_hash, data.password):
        raise HTTPException(401, "邮箱或密码不正确")
    token = issue_token(session, user)
    set_login_cookie(response, token)
    preference = session.exec(select(UserPreference).where(UserPreference.user_id == user.id)).first()
    return {"user": auth_user_data(user), "preferences": preference_data(preference)}


@app.post("/api/auth/logout")
def logout(request: Request, response: Response, session: Session = Depends(get_session),
           token: str | None = Cookie(default=None, alias=COOKIE_NAME),
           authorization: str | None = Header(default=None)) -> dict:
    if request.headers.get("X-NeighLoop-Request") != "1":
        raise HTTPException(403, "缺少受保护的请求标记")
    revoke_token(session, token or (authorization.removeprefix("Bearer ") if authorization and authorization.startswith("Bearer ") else None))
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@app.get("/api/auth/me")
def auth_me(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    preference = session.exec(select(UserPreference).where(UserPreference.user_id == user.id)).first()
    return {"user": auth_user_data(user), "preferences": preference_data(preference)}


@app.get("/api/me/preferences")
def get_preferences(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    return preference_data(session.exec(select(UserPreference).where(UserPreference.user_id == user.id)).first())


@app.patch("/api/me/profile")
def update_profile(data: ProfileInput, user: User = Depends(current_user),
                   session: Session = Depends(get_session)) -> dict:
    nickname = data.nickname.strip()
    if not nickname:
        raise HTTPException(422, "昵称不能为空")
    user.nickname = nickname
    user.display_name = nickname
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    return auth_user_data(user)


@app.patch("/api/me/preferences")
def update_preferences(data: PreferenceInput, user: User = Depends(current_user),
                       session: Session = Depends(get_session)) -> dict:
    allowed_goals = {"CLEAR", "FIND", "GIVE", "NEED", "MOVE", "BROWSE"}
    allowed_trades = {"FREE", "LOW_PRICE", "NEGOTIABLE", "ANY"}
    if not set(data.goals) <= allowed_goals or not set(data.trade_preferences) <= allowed_trades:
        raise HTTPException(422, "偏好选项无效")
    categories = [category.strip() for category in data.categories if category.strip()]
    if len(categories) != len(data.categories) or any(len(category) > 30 for category in categories):
        raise HTTPException(422, "物品兴趣类别无效")
    preference = session.exec(select(UserPreference).where(UserPreference.user_id == user.id)).first()
    if not preference:
        preference = UserPreference(user_id=user.id)
    preference.goals = list(dict.fromkeys(data.goals))
    preference.categories = list(dict.fromkeys(categories))
    preference.trade_preferences = list(dict.fromkeys(data.trade_preferences))
    preference.use_distance = data.use_distance
    preference.updated_at = utc_now()
    session.add(preference)
    session.commit()
    return preference_data(preference)


@app.patch("/api/me/community")
def update_my_community(data: MyCommunityInput, user: User = Depends(current_user),
                        session: Session = Depends(get_session)) -> dict:
    community = session.get(Community, data.community_id)
    if not community:
        raise HTTPException(404, "社区不存在")
    building = session.get(Building, data.building_id) if data.building_id else None
    if building and building.community_id != data.community_id:
        raise HTTPException(422, "请选择该社区的楼栋")
    profile = session.exec(select(CommunityProfile).where(CommunityProfile.community_id == community.id)).first()
    membership = session.exec(select(CommunityMember).where(CommunityMember.community_id == community.id,
                                                       CommunityMember.user_id == user.id)).first()
    if not membership:
        if not profile or (not profile.is_public and (data.join_code or "").strip().upper() != profile.join_code):
            raise HTTPException(403, "此社区需要正确的加入码")
        session.add(CommunityMember(community_id=community.id, user_id=user.id,
                                    building_id=data.building_id, role="MEMBER"))
    else:
        membership.building_id = data.building_id
        session.add(membership)
    user.community_id = community.id
    user.building_id = data.building_id
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    return {"user": auth_user_data(user), "community": community_data(session, community, user.id)}


@app.post("/api/me/onboarding/complete")
def complete_onboarding(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    user.onboarding_completed = True
    user.updated_at = utc_now()
    session.add(user)
    session.commit()
    return auth_user_data(user)


@app.post("/api/me/product-tour/complete")
def complete_product_tour(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    user.product_tour_completed = True
    session.add(user)
    session.commit()
    return auth_user_data(user)


@app.post("/api/me/product-tour/reset")
def reset_product_tour(user: User = Depends(current_user), session: Session = Depends(get_session)) -> dict:
    user.product_tour_completed = False
    session.add(user)
    session.commit()
    return auth_user_data(user)


@app.get("/api/bootstrap")
def bootstrap(
    x_community_id: int = Header(default=1), session: Session = Depends(get_session),
    user: User | None = Depends(optional_current_user),
) -> dict:
    memberships = session.exec(select(CommunityMember).where(CommunityMember.user_id == user.id).order_by(CommunityMember.id)).all() if user else []
    joined_ids = [member.community_id for member in memberships]
    requested = session.get(Community, x_community_id)
    requested_profile = session.exec(select(CommunityProfile).where(CommunityProfile.community_id == x_community_id)).first() if requested else None
    selected_id = x_community_id if requested and (x_community_id in joined_ids or (requested_profile and requested_profile.is_public)) else (joined_ids[0] if joined_ids else None)
    if selected_id is None:
        public_profile = session.exec(select(CommunityProfile).where(CommunityProfile.is_public == True).order_by(CommunityProfile.community_id)).first()  # noqa: E712
        selected_id = public_profile.community_id if public_profile else None
    community = session.get(Community, selected_id) if selected_id else None
    buildings = session.exec(select(Building).where(Building.community_id == selected_id).order_by(Building.id)).all() if selected_id else []
    users = session.exec(select(User).where(User.email == None).order_by(User.id)).all() if demo_mode() else []  # noqa: E711
    selected_members = session.exec(select(CommunityMember).where(
        CommunityMember.community_id == selected_id)).all() if selected_id else []
    member_by_user = {member.user_id: member for member in selected_members}
    demo_users = []
    for demo_user in users:
        membership = member_by_user.get(demo_user.id)
        location_id = membership.building_id if membership and membership.building_id else demo_user.building_id
        location = session.get(Building, location_id)
        demo_users.append({**user_data(demo_user), "location_name": location.name if location else "社区成员"})
    community_categories = session.exec(select(Item.category).join(Building, Building.id == Item.building_id)
                                        .where(Building.community_id == selected_id).distinct()).all() if selected_id else []
    community_needs = session.exec(select(Need).where(Need.community_id == selected_id,
                           Need.status == "ACTIVE")).all() if selected_id else []
    return {
        "community": community_data(session, community, user.id if user else None) if community else None,
        "communities": [community_data(session, session.get(Community, cid), user.id if user else None) for cid in joined_ids],
        "buildings": [{"id": b.id, "name": b.name, "map_key": b.map_key,
                       "map_x": b.map_x, "map_y": b.map_y} for b in buildings],
        "users": demo_users,
        "categories": CATEGORIES + sorted(category for category in set(community_categories) if category not in CATEGORIES),
        "need_categories": sorted({need.category for need in community_needs
                                   if need.category and need_is_active(need, utc_now())}),
    }


@app.get("/api/communities")
def list_communities(q: str = "", keyword: str = "", session: Session = Depends(get_session),
                     user: User | None = Depends(optional_current_user)) -> list[dict]:
    statement = select(Community)
    search = (keyword or q).strip()
    if search:
        matching_profiles = session.exec(select(CommunityProfile.community_id).where(or_(
            CommunityProfile.city.ilike(f"%{search}%"), CommunityProfile.district.ilike(f"%{search}%")
        ))).all()
        statement = statement.where(or_(Community.name.ilike(f"%{search}%"),
                                        Community.id.in_(matching_profiles)))
    communities = session.exec(statement.order_by(Community.id.desc()).limit(50)).all()
    return [community_data(session, community, user.id if user else None) for community in communities]


def approximate_distance_meters(latitude: float, longitude: float, target_latitude: float,
                                target_longitude: float) -> int:
    lat1, lat2 = math.radians(latitude), math.radians(target_latitude)
    delta_lat = lat2 - lat1
    delta_lon = math.radians(target_longitude - longitude)
    value = math.sin(delta_lat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2) ** 2
    value = min(1.0, max(0.0, value))
    meters = 6371000 * 2 * math.atan2(math.sqrt(value), math.sqrt(1 - value))
    return max(0, round(meters / 10) * 10)


@app.post("/api/location/resolve-community")
def resolve_community(data: LocationInput, session: Session = Depends(get_session)) -> dict:
    profiles = session.exec(select(CommunityProfile).where(CommunityProfile.is_public == True,
        CommunityProfile.latitude != None, CommunityProfile.longitude != None)).all()  # noqa: E711,E712
    distances = [(approximate_distance_meters(data.latitude, data.longitude, profile.latitude,
                                              profile.longitude), profile) for profile in profiles]
    if not distances:
        return {"matched": False}
    distance, profile = min(distances, key=lambda pair: pair[0])
    if distance > 3000:
        return {"matched": False}
    community = session.get(Community, profile.community_id)
    return {"matched": True, "community_id": community.id, "community_name": community.name,
            "distance_meters": distance, "accuracy_meters": round(data.accuracy) if data.accuracy else None}


@app.get("/api/communities/nearby")
def nearby_communities(latitude: float = Query(ge=-90, le=90), longitude: float = Query(ge=-180, le=180),
                       session: Session = Depends(get_session),
                       user: User | None = Depends(optional_current_user)) -> list[dict]:
    profiles = session.exec(select(CommunityProfile).where(CommunityProfile.latitude != None,
                                                            CommunityProfile.longitude != None)).all()  # noqa: E711
    results = []
    for profile in profiles:
        if not profile.is_public and not (user and session.exec(select(CommunityMember.id).where(
            CommunityMember.community_id == profile.community_id, CommunityMember.user_id == user.id
        )).first()):
            continue
        distance = approximate_distance_meters(latitude, longitude, profile.latitude, profile.longitude)
        if distance <= 3000:
            results.append({**community_data(session, session.get(Community, profile.community_id),
                                              user.id if user else None), "distance_m": distance})
    return sorted(results, key=lambda entry: entry["distance_m"])[:8]


@app.post("/api/communities", status_code=201)
def create_community(
    data: CommunityInput, session: Session = Depends(get_session), user: User = Depends(current_user)
) -> dict:
    if data.kind not in {"NEIGHBORHOOD", "BUILDING", "OFFICE"}:
        raise HTTPException(422, "无效的社区类型")
    name = data.name.strip()
    if session.exec(select(Community).where(Community.name == name)).first():
        raise HTTPException(409, "这个社区名称已存在")
    locations = [value.strip() for value in data.location_names if value.strip()]
    if not locations or len(locations) != len(set(locations)):
        raise HTTPException(422, "请填写不重复的楼栋或区域名称")
    community = Community(name=name)
    session.add(community)
    session.flush()
    code = secrets.token_hex(4).upper()
    while session.exec(select(CommunityProfile).where(CommunityProfile.join_code == code)).first():
        code = secrets.token_hex(4).upper()
    session.add(CommunityProfile(community_id=community.id, kind=data.kind, city=data.city.strip(),
                                 district=data.district.strip(), address=data.address.strip() if data.address else None,
                                 join_code=code, created_by_id=user.id,
                                 is_public=data.is_public, latitude=data.latitude, longitude=data.longitude))
    map_positions = [(24, 35), (50, 18), (78, 34), (31, 66), (65, 66), (84, 58), (18, 55), (50, 80)]
    buildings = [Building(community_id=community.id, name=location, map_key=f"c{community.id}-b{index}",
                          map_x=map_positions[index - 1][0], map_y=map_positions[index - 1][1])
                 for index, location in enumerate(locations, start=1)]
    session.add_all(buildings)
    session.flush()
    session.add(CommunityMember(community_id=community.id, user_id=user.id,
                                building_id=buildings[0].id, role="ADMIN"))
    user.community_id = community.id
    user.building_id = buildings[0].id
    session.add(user)
    session.commit()
    return community_data(session, community, user.id)


@app.post("/api/communities/{community_id}/join")
def join_community(
    community_id: int, data: JoinCommunityInput,
    session: Session = Depends(get_session), user: User = Depends(current_user),
) -> dict:
    community = session.get(Community, community_id)
    profile = session.exec(select(CommunityProfile).where(CommunityProfile.community_id == community_id)).first()
    if not community or not profile:
        raise HTTPException(404, "社区不存在")
    if not profile.is_public and profile.join_code != data.join_code.strip().upper():
        raise HTTPException(403, "加入码不正确")
    building = session.get(Building, data.building_id)
    if not building or building.community_id != community_id:
        raise HTTPException(422, "请选择该社区内的楼栋或区域")
    existing = session.exec(select(CommunityMember).where(
        CommunityMember.community_id == community_id, CommunityMember.user_id == user.id
    )).first()
    if not existing:
        session.add(CommunityMember(community_id=community_id, user_id=user.id,
                                    building_id=building.id, role="MEMBER"))
    user.community_id = community.id
    user.building_id = building.id
    session.add(user)
    session.commit()
    return community_data(session, community, user.id)


@app.get("/api/items")
def list_items(
    q: str = "",
    trade_type: str | None = None,
    category: str | None = None,
    condition: str | None = None,
    building_id: int | None = None,
    min_price: int | None = Query(default=None, ge=0, le=100000),
    max_price: int | None = Query(default=None, ge=0, le=100000),
    freshness_hours: int | None = None,
    sort_by: str = "NEWEST",
    status: str = "ACTIVE",
    limit: int = Query(default=60, ge=1, le=100),
    session: Session = Depends(get_session),
    user: User | None = Depends(optional_current_user),
    community_id: int = Depends(current_community_id),
    location: tuple[float, float] | None = Depends(request_location),
) -> list[dict]:
    if status not in {"ACTIVE", "AVAILABLE", "UNCONFIRMED", "RESERVED", "COMPLETED", "ARCHIVED", "ALL"}:
        raise HTTPException(422, "无效状态")
    if sort_by not in {"NEWEST", "PRICE_ASC", "PRICE_DESC", "MOST_WANTED"}:
        raise HTTPException(422, "无效排序方式")
    if freshness_hours not in {None, 24, 72, 168}:
        raise HTTPException(422, "无效上架时间范围")
    if min_price is not None and max_price is not None and min_price > max_price:
        raise HTTPException(422, "最低价格不能高于最高价格")
    statement = select(Item).join(Building).where(Building.community_id == community_id)
    if status == "ACTIVE":
        statement = statement.where(Item.status.in_(["AVAILABLE", "RESERVED"]))
    elif status in {"AVAILABLE", "UNCONFIRMED"}:
        statement = statement.where(Item.status == "AVAILABLE")
    elif status != "ALL":
        statement = statement.where(Item.status == status)
    if q.strip():
        pattern = f"%{q.strip()}%"
        statement = statement.where(or_(Item.title.ilike(pattern), Item.description.ilike(pattern)))
    if trade_type:
        statement = statement.where(Item.trade_type == trade_type)
    if category:
        statement = statement.where(Item.category == category)
    if condition:
        statement = statement.where(Item.condition == condition)
    if building_id:
        statement = statement.where(Item.building_id == building_id)
    if min_price is not None or max_price is not None:
        statement = statement.where(Item.trade_type == "FIXED_PRICE")
        if min_price is not None:
            statement = statement.where(Item.price >= min_price)
        if max_price is not None:
            statement = statement.where(Item.price <= max_price)
    if freshness_hours:
        statement = statement.where(Item.created_at >= utc_now() - timedelta(hours=freshness_hours))
    items = session.exec(statement).all()
    if status in {"AVAILABLE", "UNCONFIRMED"}:
        items = [item for item in items if effective_status(item) == status]
    if sort_by == "MOST_WANTED" and items:
        ids = [item.id for item in items]
        counts = dict(session.exec(select(Interest.item_id, func.count(Interest.id)).where(
            Interest.item_id.in_(ids)
        ).group_by(Interest.item_id)).all())
        items.sort(key=lambda item: (counts.get(item.id, 0), item.created_at), reverse=True)
    elif sort_by == "PRICE_ASC":
        items.sort(key=lambda item: (item.trade_type == "NEGOTIABLE", 0 if item.trade_type == "FREE" else item.price or 0, -item.created_at.timestamp()))
    elif sort_by == "PRICE_DESC":
        items.sort(key=lambda item: (item.trade_type != "FIXED_PRICE", -(item.price or 0), -item.created_at.timestamp()))
    else:
        items.sort(key=lambda item: item.created_at, reverse=True)
    items = items[:limit]
    return items_data(session, items, user.id if user else None, location)


@app.get("/api/recommendations")
def recommendations(
    mode: str = "FOR_YOU",
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=12, ge=1, le=40),
    session: Session = Depends(get_session),
    user: User | None = Depends(optional_current_user),
    community_id: int = Depends(current_community_id),
    location: tuple[float, float] | None = Depends(request_location),
) -> dict:
    if mode not in {"FOR_YOU", "NEW", "FREE", "NEARBY"}:
        raise HTTPException(422, "无效的推荐模式")
    all_items = session.exec(select(Item).join(Building).where(
        Building.community_id == community_id, Item.status.in_(["AVAILABLE", "RESERVED"])
    )).all()
    membership = session.exec(select(CommunityMember).where(
        CommunityMember.community_id == community_id, CommunityMember.user_id == user.id
    )).first() if user else None
    local_building_id = membership.building_id if membership else None
    candidates = [item for item in all_items if not user or item.owner_id != user.id]
    if mode == "FREE":
        candidates = [item for item in candidates if item.trade_type == "FREE"]
    if mode == "NEARBY":
        candidates = [item for item in candidates if item.building_id == local_building_id]

    preference = session.exec(select(UserPreference).where(UserPreference.user_id == user.id)).first() if user else None
    chosen_categories = set(preference.categories) if preference else set()
    chosen_trades = set(preference.trade_preferences) if preference else set()
    received_categories = Counter()
    if user:
        history = session.exec(select(Item.category).join(Transaction, Transaction.item_id == Item.id)
                               .where(Transaction.recipient_id == user.id)).all()
        received_categories.update(history)

    def score(item: Item) -> int:
        return (min(9, received_categories[item.category] * 3) + (4 if item.category in chosen_categories else 0) + (2 if item.trade_type == "FREE" and "FREE" in chosen_trades else 0) + (2 if item.trade_type == "NEGOTIABLE" and "NEGOTIABLE" in chosen_trades else 0) + (2 if item.trade_type == "FIXED_PRICE" and "LOW_PRICE" in chosen_trades else 0) + (1 if preference and preference.use_distance and item.building_id == local_building_id else 0))

    if mode == "FOR_YOU":
        candidates.sort(key=lambda item: (score(item), -(item.price or 0) if item.trade_type == "FIXED_PRICE" and "LOW_PRICE" in chosen_trades else item.created_at.timestamp(), item.created_at.timestamp()), reverse=True)
    else:
        candidates.sort(key=lambda item: (item.created_at, item.id), reverse=True)
    page = candidates[offset:offset + limit]
    serialized = items_data(session, page, user.id if user else None, location)
    for item, payload in zip(page, serialized):
        if mode == "NEW":
            reason = "刚刚上架"
        elif mode == "FREE":
            reason = "免费分享"
        elif mode == "NEARBY":
            reason = "同楼栋邻居"
        elif received_categories[item.category]:
            reason = f"根据你曾领过的{item.category}好物"
        elif item.category in chosen_categories:
            reason = f"你选择的{item.category}兴趣"
        elif item.trade_type == "FREE" and "FREE" in chosen_trades:
            reason = "你选择的免费分享偏好"
        elif item.trade_type == "FIXED_PRICE" and "LOW_PRICE" in chosen_trades:
            reason = "你选择的邻里低价偏好"
        elif preference and preference.use_distance and item.building_id == local_building_id:
            reason = "你选择的同楼栋优先"
        else:
            reason = "社区新发现"
        payload["recommendation_reason"] = reason
    return {"mode": mode, "total": len(candidates), "items": serialized}


@app.post("/api/items/{item_id}/view")
def record_view(item_id: int, session: Session = Depends(get_session), user: User = Depends(current_user),
                community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if item.owner_id == user.id:
        return {"ok": True}
    existing = session.exec(select(ItemView).where(ItemView.item_id == item_id, ItemView.user_id == user.id)).first()
    if not existing:
        session.add(ItemView(item_id=item_id, user_id=user.id))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()
    return {"ok": True}


@app.get("/api/my/items")
def my_items(
    status: str = "ALL", session: Session = Depends(get_session), user: User = Depends(current_user),
    community_id: int = Depends(current_community_id),
) -> list[dict]:
    statement = select(Item).join(Building).where(Item.owner_id == user.id, Building.community_id == community_id)
    if status == "ACTIVE":
        statement = statement.where(Item.status.in_(["AVAILABLE", "RESERVED"]))
    elif status in {"COMPLETED", "ARCHIVED"}:
        statement = statement.where(Item.status == status)
    items = session.exec(statement.order_by(Item.created_at.desc())).all()
    return items_data(session, items, user.id)


@app.get("/api/my/summary")
def my_summary(session: Session = Depends(get_session), user: User = Depends(current_user),
               community_id: int = Depends(current_community_id)) -> dict:
    community_items = session.exec(select(Item).join(Building).where(Building.community_id == community_id)).all()
    own_items = [item for item in community_items if item.owner_id == user.id]
    own_ids = [item.id for item in own_items]
    community_ids = [item.id for item in community_items]
    interests = session.exec(select(Interest).where(Interest.item_id.in_(own_ids))).all() if own_ids else []
    transactions = session.exec(select(Transaction).where(Transaction.item_id.in_(own_ids))).all() if own_ids else []
    reservations = session.exec(select(Reservation).where(Reservation.buyer_id == user.id,
        Reservation.item_id.in_(community_ids), Reservation.status.in_(["PENDING", "CONFIRMED"]))).all() if community_ids else []
    activity_count = session.exec(select(func.count(ItemEvent.id)).where(
        ItemEvent.item_id.in_(community_ids), ItemEvent.user_id == user.id)).one() if community_ids else 0
    return {"published_count": len(own_items),
            "active_count": sum(item.status in {"AVAILABLE", "RESERVED"} for item in own_items),
            "reserved_count": sum(item.status == "RESERVED" for item in own_items),
            "unconfirmed_count": sum(effective_status(item) == "UNCONFIRMED" for item in own_items),
            "completed_count": sum(item.status == "COMPLETED" for item in own_items),
            "received_interests": len(interests),
            "helped_neighbors": len({transaction.recipient_id for transaction in transactions}),
            "my_reservation_count": len(reservations), "activity_count": activity_count}


@app.get("/api/my/reservations")
def my_reservations(limit: int = Query(default=8, ge=1, le=30), session: Session = Depends(get_session),
                    user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> list[dict]:
    rows = session.exec(select(Reservation, Item).join(Item, Item.id == Reservation.item_id)
                        .join(Building, Building.id == Item.building_id)
                        .where(Building.community_id == community_id, Reservation.buyer_id == user.id,
                               Reservation.status.in_(["PENDING", "CONFIRMED"]))
                        .order_by(Reservation.created_at.desc()).limit(limit)).all()
    return [{**reservation_data(session, reservation, user.id), "item": item_data(session, item, user.id)}
            for reservation, item in rows]


@app.get("/api/my/activity")
def my_activity(limit: int = Query(default=6, ge=1, le=30), session: Session = Depends(get_session),
                user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> list[dict]:
    rows = session.exec(select(ItemEvent, Item).join(Item, Item.id == ItemEvent.item_id)
                        .join(Building, Building.id == Item.building_id)
                        .where(Building.community_id == community_id,
                               or_(ItemEvent.user_id == user.id, Item.owner_id == user.id))
                        .order_by(ItemEvent.created_at.desc(), ItemEvent.id.desc()).limit(limit)).all()
    return [{**event_data(event, item, user.id), "item_title": item.title, "image_key": item.image_key}
            for event, item in rows]


@app.get("/api/items/{item_id}")
def item_detail(item_id: int, session: Session = Depends(get_session), user: User | None = Depends(optional_current_user),
                community_id: int = Depends(current_community_id),
                location: tuple[float, float] | None = Depends(request_location)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    comments = session.exec(select(Comment).where(Comment.item_id == item_id).order_by(Comment.created_at)).all()
    interests = session.exec(select(Interest).where(Interest.item_id == item_id).order_by(Interest.created_at)).all()
    transaction = session.exec(select(Transaction).where(Transaction.item_id == item_id)).first()
    viewer_id = user.id if user else None
    result = item_data(session, item, viewer_id, location)
    result["comments"] = [
        {"id": c.id, "body": c.body, "created_at": iso_utc(c.created_at), "user": user_data(session.get(User, c.user_id))}
        for c in comments
    ]
    result["interested_users"] = [user_data(session.get(User, interest.user_id)) for interest in interests] if viewer_id == item.owner_id else []
    result["recipient_id"] = transaction.recipient_id if transaction and viewer_id == item.owner_id else None
    slots = session.exec(select(HandoverSlot).where(HandoverSlot.item_id == item_id).order_by(HandoverSlot.starts_at)).all()
    result["handover_slots"] = [slot_data(slot) for slot in slots if as_utc(slot.starts_at) > utc_now()]
    reservations = session.exec(select(Reservation).where(Reservation.item_id == item_id).order_by(Reservation.created_at.desc())).all()
    result["reservations"] = [reservation_data(session, reservation, viewer_id) for reservation in reservations
                              if viewer_id == item.owner_id and reservation.status in {"PENDING", "CONFIRMED"}]
    mine = next((reservation for reservation in reservations if reservation.buyer_id == viewer_id
                 and reservation.status in {"PENDING", "CONFIRMED"}), None)
    result["my_reservation"] = reservation_data(session, mine, viewer_id) if mine else None
    return result


def chat_partner(session: Session, item: Item, user: User, other_user_id: int, community_id: int) -> User:
    other = session.get(User, other_user_id)
    if not other or not session.exec(select(CommunityMember.id).where(
        CommunityMember.community_id == community_id, CommunityMember.user_id == other_user_id
    )).first():
        raise HTTPException(404, "对方不是当前社区成员")
    if user.id == other_user_id or item.owner_id not in {user.id, other_user_id}:
        raise HTTPException(403, "只能与这件物品的发布者或咨询邻居私聊")
    if user.id == item.owner_id:
        has_context = any([
            session.exec(select(Interest.id).where(Interest.item_id == item.id, Interest.user_id == other_user_id)).first(),
            session.exec(select(Reservation.id).where(Reservation.item_id == item.id, Reservation.buyer_id == other_user_id)).first(),
            session.exec(select(Comment.id).where(Comment.item_id == item.id, Comment.user_id == other_user_id)).first(),
            session.exec(select(PrivateMessage.id).where(PrivateMessage.item_id == item.id,
                or_(PrivateMessage.sender_id == other_user_id, PrivateMessage.recipient_id == other_user_id))).first(),
        ])
        if not has_context:
            raise HTTPException(403, "这位邻居还没有与你的物品互动")
    elif item.status in {"COMPLETED", "ARCHIVED"} and not session.exec(
        select(PrivateMessage.id).where(PrivateMessage.item_id == item.id,
            or_(PrivateMessage.sender_id == user.id, PrivateMessage.recipient_id == user.id))
    ).first() and not session.exec(select(Reservation.id).where(
        Reservation.item_id == item.id, Reservation.buyer_id == user.id
    )).first():
        raise HTTPException(403, "已结束流转的物品不能发起新私聊")
    return other


def private_message_data(message: PrivateMessage) -> dict:
    return {"id": message.id, "item_id": message.item_id, "sender_id": message.sender_id,
            "recipient_id": message.recipient_id, "body": message.body,
            "message_type": message.message_type, "is_ai": message.is_ai,
            "read_at": iso_utc(message.read_at),
            "created_at": iso_utc(message.created_at)}


def private_notice(session: Session, item_id: int, sender_id: int, recipient_id: int,
                   body: str, message_type: str = "SYSTEM", is_ai: bool = False) -> None:
    session.add(PrivateMessage(item_id=item_id, sender_id=sender_id, recipient_id=recipient_id,
                               body=body, message_type=message_type, is_ai=is_ai))


FAQ_QUESTIONS = ["还在吗？", "可以预约什么时间？", "成色怎么样？", "多少钱，怎么交接？", "可以看更多细节吗？"]


def chat_slot_label(starts_at: datetime) -> str:
    aware = starts_at if starts_at.tzinfo else starts_at.replace(tzinfo=timezone.utc)
    return aware.astimezone(timezone(timedelta(hours=8))).strftime("%m月%d日 %H:%M")


def item_faq_answer(session: Session, item: Item, question: str) -> str:
    slots = session.exec(select(HandoverSlot).where(HandoverSlot.item_id == item.id,
                         HandoverSlot.starts_at > utc_now()).order_by(HandoverSlot.starts_at).limit(3)).all()
    facts = {"title": item.title, "description": item.description, "condition": item.condition,
             "status": effective_status(item), "trade_type": item.trade_type, "price": item.price,
             "public_location": item.public_location,
             "available_slots_beijing_time": [{"start": chat_slot_label(slot.starts_at),
                                               "end": chat_slot_label(slot.ends_at)} for slot in slots]}
    if facts["status"] != "AVAILABLE":
        fallback = "目前这件物品暂不可新预约，请等发布者确认最新状态。"
    elif "时间" in question or "预约" in question:
        fallback = "目前可预约时间（北京时间）：" + ("、".join(chat_slot_label(slot.starts_at) for slot in slots) if slots else "暂无可选时间，请等发布者补充") + "。"
    elif "钱" in question or "价格" in question:
        fallback = "这件物品" + ("免费分享" if item.trade_type == "FREE" else f"标价 ¥{item.price}" if item.trade_type == "FIXED_PRICE" else "价格可商量") + f"，交接范围是{item.public_location or '当前社区'}。"
    elif "成色" in question or "细节" in question:
        fallback = f"发布者标注成色为{item.condition}。其他细节请等发布者本人确认。"
    else:
        fallback = "发布者最近确认物品仍在架，可从详情页选择时间预约；其他细节请等发布者本人确认。"
    try:
        result = deepseek_json(
            "你是 NeighLoop 的 AI 邻里助手，不是发布者。只根据 JSON 事实回答，语气亲切简短。"
            "绝不能编造具体交接地址、额外时间、价格优惠或物品品质；无法确定时请等发布者确认。"
            '只返回 JSON：{"answer":"..."}。',
            f"物品事实：{json.dumps(facts, ensure_ascii=False)}\n邻居问题：{question}")
        answer = result.get("answer")
        if isinstance(answer, str) and 3 <= len(answer) <= 220:
            return answer.strip()
    except HTTPException:
        pass
    return fallback


@app.get("/api/messages/threads")
def message_threads(session: Session = Depends(get_session), user: User = Depends(current_user),
                    community_id: int = Depends(current_community_id)) -> list[dict]:
    rows = session.exec(select(PrivateMessage, Item).join(Item, Item.id == PrivateMessage.item_id)
                        .join(Building, Building.id == Item.building_id)
                        .where(Building.community_id == community_id,
                               or_(PrivateMessage.sender_id == user.id, PrivateMessage.recipient_id == user.id))
                        .order_by(PrivateMessage.created_at.desc(), PrivateMessage.id.desc())).all()
    threads: dict[tuple[int, int], dict] = {}
    for message, item in rows:
        other_id = message.recipient_id if message.sender_id == user.id else message.sender_id
        key = (item.id, other_id)
        if key not in threads:
            other = session.get(User, other_id)
            if not other:
                continue
            threads[key] = {"item": {"id": item.id, "title": item.title, "image_key": item.image_key,
                                      "owner_id": item.owner_id, "status": item.status},
                            "other_user": user_data(other), "last_message": private_message_data(message),
                            "unread_count": 0, "reservation_status": None}
        if message.recipient_id == user.id and not message.read_at:
            threads[key]["unread_count"] += 1
    for (item_id, other_id), thread in threads.items():
        item = session.get(Item, item_id)
        buyer_id = other_id if item.owner_id == user.id else user.id
        reservation = session.exec(select(Reservation).where(Reservation.item_id == item_id,
            Reservation.buyer_id == buyer_id).order_by(Reservation.created_at.desc(), Reservation.id.desc())).first()
        if reservation:
            thread["reservation_status"] = reservation.status
    return list(threads.values())


@app.get("/api/my/interests")
def my_interests(session: Session = Depends(get_session), user: User = Depends(current_user),
                 community_id: int = Depends(current_community_id)) -> list[dict]:
    items = session.exec(select(Item).join(Interest, Interest.item_id == Item.id)
                         .join(Building, Building.id == Item.building_id)
                         .where(Interest.user_id == user.id, Building.community_id == community_id)
                         .order_by(Interest.created_at.desc())).all()
    return items_data(session, items, user.id)


@app.post("/api/presence/heartbeat")
def presence_heartbeat(session: Session = Depends(get_session), user: User = Depends(current_user)) -> dict:
    presence = session.get(UserPresence, user.id) or UserPresence(user_id=user.id)
    presence.last_seen_at = utc_now()
    session.add(presence)
    session.commit()
    return {"ok": True}


@app.get("/api/items/{item_id}/faq")
def item_faq(item_id: int, session: Session = Depends(get_session),
             community_id: int = Depends(current_community_id)) -> dict:
    get_item_or_404(session, item_id, community_id)
    return {"questions": FAQ_QUESTIONS}


@app.post("/api/items/{item_id}/faq", status_code=201)
def ask_item_faq(item_id: int, data: FaqInput, session: Session = Depends(get_session),
                 user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    chat_partner(session, item, user, data.other_user_id, community_id)
    if user.id == item.owner_id:
        raise HTTPException(403, "发布者不能向自己的助手提问")
    question = data.question.strip()
    private_notice(session, item_id, user.id, item.owner_id, question, "QUESTION")
    answer = item_faq_answer(session, item, question)
    reply = PrivateMessage(item_id=item_id, sender_id=item.owner_id, recipient_id=user.id,
                           body=answer, message_type="AI_REPLY", is_ai=True)
    session.add(reply)
    session.commit()
    session.refresh(reply)
    return private_message_data(reply)


@app.post("/api/items/{item_id}/messages/read")
def read_item_messages(item_id: int, other_user_id: int, session: Session = Depends(get_session),
                       user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    chat_partner(session, item, user, other_user_id, community_id)
    rows = session.exec(select(PrivateMessage).where(PrivateMessage.item_id == item_id,
        PrivateMessage.sender_id == other_user_id, PrivateMessage.recipient_id == user.id,
        PrivateMessage.read_at == None)).all()  # noqa: E711
    for message in rows:
        message.read_at = utc_now()
        session.add(message)
    session.commit()
    return {"read": len(rows)}


@app.get("/api/items/{item_id}/conversations")
def item_conversations(item_id: int, session: Session = Depends(get_session),
                       user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> list[dict]:
    item = get_item_or_404(session, item_id, community_id)
    if item.owner_id != user.id:
        raise HTTPException(403, "只有发布者可以查看咨询列表")
    ids = {row.user_id for row in session.exec(select(Interest).where(Interest.item_id == item_id)).all()}
    ids.update(row.buyer_id for row in session.exec(select(Reservation).where(Reservation.item_id == item_id)).all())
    ids.update(row.user_id for row in session.exec(select(Comment).where(Comment.item_id == item_id)).all())
    messages = session.exec(select(PrivateMessage).where(PrivateMessage.item_id == item_id)
                            .order_by(PrivateMessage.created_at.desc(), PrivateMessage.id.desc())).all()
    ids.update(message.sender_id if message.sender_id != user.id else message.recipient_id for message in messages)
    ids.discard(user.id)
    last_by_user = {}
    for message in messages:
        other_id = message.sender_id if message.sender_id != user.id else message.recipient_id
        last_by_user.setdefault(other_id, message)
    return [{"user": user_data(session.get(User, other_id)),
             "last_message": private_message_data(last_by_user[other_id]) if other_id in last_by_user else None}
            for other_id in sorted(ids, key=lambda value: (
                last_by_user[value].created_at.isoformat() if value in last_by_user else ""
            ), reverse=True) if session.get(User, other_id)]


@app.get("/api/items/{item_id}/messages")
def item_messages(item_id: int, other_user_id: int,
                  session: Session = Depends(get_session), user: User = Depends(current_user),
                  community_id: int = Depends(current_community_id)) -> list[dict]:
    item = get_item_or_404(session, item_id, community_id)
    chat_partner(session, item, user, other_user_id, community_id)
    messages = session.exec(select(PrivateMessage).where(PrivateMessage.item_id == item_id,
        or_(and_(PrivateMessage.sender_id == user.id, PrivateMessage.recipient_id == other_user_id),
            and_(PrivateMessage.sender_id == other_user_id, PrivateMessage.recipient_id == user.id)))
        .order_by(PrivateMessage.created_at, PrivateMessage.id)).all()
    return [private_message_data(message) for message in messages]


@app.post("/api/items/{item_id}/messages", status_code=201)
def send_item_message(item_id: int, data: PrivateMessageInput,
                      session: Session = Depends(get_session), user: User = Depends(current_user),
                      community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    chat_partner(session, item, user, data.other_user_id, community_id)
    message = PrivateMessage(item_id=item_id, sender_id=user.id, recipient_id=data.other_user_id,
                             body=data.body.strip())
    if not message.body:
        raise HTTPException(422, "消息不能为空")
    session.add(message)
    if user.id != item.owner_id:
        presence = session.get(UserPresence, item.owner_id)
        last_seen = presence.last_seen_at if presence else None
        if not last_seen or (utc_now() - (last_seen if last_seen.tzinfo else last_seen.replace(tzinfo=timezone.utc))) > timedelta(minutes=2):
            private_notice(session, item_id, item.owner_id, user.id,
                           item_faq_answer(session, item, message.body), "AI_REPLY", is_ai=True)
    session.commit()
    session.refresh(message)
    return private_message_data(message)


@app.get("/api/items/{item_id}/events")
def item_events(item_id: int, session: Session = Depends(get_session),
                user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if item.owner_id != user.id:
        raise HTTPException(403, "只有发布者可以查看完整流转记录")
    events = session.exec(select(ItemEvent).where(ItemEvent.item_id == item_id)
                          .order_by(ItemEvent.created_at, ItemEvent.id)).all()
    minutes = round((item.completed_at - item.created_at).total_seconds() / 60) if item.completed_at else None
    return {"events": [event_data(event, item, user.id,
                                  session.get(User, event.user_id).display_name if event.user_id and session.get(User, event.user_id) else None)
                       for event in events],
            "total_minutes": minutes}


@app.get("/api/activity")
def activity_feed(limit: int = Query(default=10, ge=1, le=30),
                  session: Session = Depends(get_session), community_id: int = Depends(current_community_id)) -> list[dict]:
    rows = session.exec(select(ItemEvent, Item).join(Item, Item.id == ItemEvent.item_id)
                        .join(Building, Building.id == Item.building_id)
                        .where(Building.community_id == community_id,
                               ItemEvent.event_type.in_(PUBLIC_ACTIVITY_TYPES))
                        .order_by(ItemEvent.created_at.desc(), ItemEvent.id.desc()).limit(limit)).all()
    return [activity_data(session, event, item) for event, item in rows]


def need_data(session: Session, need: Need) -> dict:
    building = session.get(Building, need.building_id) if need.building_id else None
    author = session.get(User, need.user_id)
    return {"id": need.id, "community_id": need.community_id, "building_id": need.building_id,
            "building_name": building.name if building else "社区", "raw_text": need.raw_text,
            "user": user_data(author),
            "category": need.category, "keywords": need.keywords,
            "budget_min": need.budget_min, "budget_max": need.budget_max,
            "status": "EXPIRED" if need.status == "ACTIVE" and not need_is_active(need, utc_now()) else need.status,
            "created_at": iso_utc(need.created_at), "expires_at": iso_utc(need.expires_at),
            "reply_count": 0, "has_listing_reply": False}


def record_matching_needs(session: Session, item: Item, community_id: int) -> list[NeedMatch]:
    needs = session.exec(select(Need).where(Need.community_id == community_id,
                                           Need.status == "ACTIVE")).all()
    added = []
    for need in needs:
        if not need_is_active(need, utc_now()):
            continue
        reasons = match_need(item, need)
        if not reasons:
            continue
        existing = session.exec(select(NeedMatch.id).where(NeedMatch.need_id == need.id,
                                                            NeedMatch.item_id == item.id)).first()
        if not existing:
            match = NeedMatch(need_id=need.id, item_id=item.id, reasons=reasons)
            session.add(match)
            added.append(match)
    return added


@app.post("/api/ai/parse-need")
def parse_need_text(data: dict, _: User = Depends(current_user)) -> dict:
    raw_text = str(data.get("raw_text", "")).strip()
    if not 2 <= len(raw_text) <= 500:
        raise HTTPException(422, "请用一句话描述你在找什么")
    return parse_need(raw_text, deepseek_json)


@app.post("/api/needs", status_code=201)
def create_need(data: NeedInput, session: Session = Depends(get_session),
                user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    if not (data.category and data.category.strip()) and not any(len(word.strip()) >= 2 for word in data.keywords):
        raise HTTPException(422, "请先写明想找的物品类别或至少一个具体物品关键词")
    if data.budget_min is not None and data.budget_max is not None and data.budget_min > data.budget_max:
        raise HTTPException(422, "最低预算不能高于最高预算")
    if data.building_id:
        building = session.get(Building, data.building_id)
        if not building or building.community_id != community_id:
            raise HTTPException(422, "请选择当前社区的楼栋")
    if data.expires_at and as_utc(data.expires_at) <= utc_now():
        raise HTTPException(422, "过期时间必须在未来")
    need = Need(user_id=user.id, community_id=community_id,
                building_id=data.building_id,
                raw_text=data.raw_text.strip(), category=data.category.strip() if data.category else None,
                keywords=list(dict.fromkeys(word.strip() for word in data.keywords if word.strip())),
                budget_min=data.budget_min, budget_max=data.budget_max, expires_at=data.expires_at)
    session.add(need)
    session.flush()
    items = session.exec(select(Item).join(Building).where(Building.community_id == community_id,
                                  Item.status.in_(["AVAILABLE", "RESERVED"]))).all()
    for item in items:
        reasons = match_need(item, need)
        if reasons:
            session.add(NeedMatch(need_id=need.id, item_id=item.id, reasons=reasons))
    session.commit()
    return need_data(session, need)


@app.get("/api/needs")
def list_needs(status: str = "ACTIVE", building_id: int | None = None,
               q: str = Query(default="", max_length=100), category: str = Query(default="", max_length=30),
               reply_state: str = "ALL", sort_by: str = "NEWEST", budget_only: bool = False,
               limit: int = Query(default=60, ge=1, le=100), session: Session = Depends(get_session),
               community_id: int = Depends(current_community_id),
               user: User | None = Depends(optional_current_user)) -> list[dict]:
    if status not in {"ACTIVE", "MATCHED", "CLOSED", "EXPIRED", "ALL"}:
        raise HTTPException(422, "无效需求状态")
    if reply_state not in {"ALL", "UNANSWERED", "WITH_LISTING"} or sort_by not in {"NEWEST", "MOST_DISCUSSED"}:
        raise HTTPException(422, "无效需求筛选条件")
    statement = select(Need).where(Need.community_id == community_id)
    if building_id:
        statement = statement.where(Need.building_id == building_id)
    if category:
        statement = statement.where(Need.category == category)
    if budget_only:
        statement = statement.where(Need.budget_max.is_not(None))
    needs = session.exec(statement).all()
    needle = q.strip().casefold()
    if needle:
        needs = [need for need in needs if needle in need.raw_text.casefold()
                 or needle in (need.category or "").casefold()
                 or any(needle in word.casefold() for word in need.keywords)]
    if status != "ALL":
        needs = [need for need in needs if need_data(session, need)["status"] == status]
    ids = [need.id for need in needs]
    replies = session.exec(select(NeedReply).where(NeedReply.need_id.in_(ids))).all() if ids else []
    reply_counts = Counter(reply.need_id for reply in replies)
    listing_replies = {reply.need_id for reply in replies if reply.item_id is not None}
    if reply_state == "UNANSWERED":
        needs = [need for need in needs if reply_counts[need.id] == 0]
    elif reply_state == "WITH_LISTING":
        needs = [need for need in needs if need.id in listing_replies]
    needs.sort(key=lambda need: (reply_counts[need.id], need.created_at, need.id)
               if sort_by == "MOST_DISCUSSED" else (need.created_at, need.id), reverse=True)
    return [{**need_data(session, need), "viewer_owned": bool(user and need.user_id == user.id),
             "reply_count": reply_counts[need.id], "has_listing_reply": need.id in listing_replies}
            for need in needs[:limit]]


def need_reply_data(session: Session, reply: NeedReply) -> dict:
    item = session.get(Item, reply.item_id) if reply.item_id else None
    return {"id": reply.id, "need_id": reply.need_id, "body": reply.body,
            "user": user_data(session.get(User, reply.user_id)),
            "item": {"id": item.id, "title": item.title, "image_key": item.image_key,
                     "status": item.status} if item else None, "created_at": iso_utc(reply.created_at)}


@app.get("/api/needs/{need_id}/replies")
def list_need_replies(need_id: int, session: Session = Depends(get_session),
                      community_id: int = Depends(current_community_id)) -> list[dict]:
    need = session.get(Need, need_id)
    if not need or need.community_id != community_id:
        raise HTTPException(404, "需求不存在")
    replies = session.exec(select(NeedReply).where(NeedReply.need_id == need_id)
                           .order_by(NeedReply.created_at, NeedReply.id)).all()
    return [need_reply_data(session, reply) for reply in replies]


@app.post("/api/needs/{need_id}/replies", status_code=201)
def create_need_reply(need_id: int, data: NeedReplyInput, session: Session = Depends(get_session),
                      user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    need = session.get(Need, need_id)
    if not need or need.community_id != community_id:
        raise HTTPException(404, "需求不存在")
    if not need_is_active(need, utc_now()):
        raise HTTPException(409, "这条需求已结束")
    item = get_item_or_404(session, data.item_id, community_id) if data.item_id else None
    if item and (item.owner_id != user.id or effective_status(item) != "AVAILABLE"):
        raise HTTPException(403, "只能附上自己当前在架的物品")
    reply = NeedReply(need_id=need_id, user_id=user.id, body=data.body.strip(), item_id=data.item_id)
    if not reply.body:
        raise HTTPException(422, "回复不能为空")
    session.add(reply)
    session.commit()
    session.refresh(reply)
    return need_reply_data(session, reply)


@app.patch("/api/needs/{need_id}")
def update_need(need_id: int, data: NeedUpdateInput, session: Session = Depends(get_session),
                user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    need = session.get(Need, need_id)
    if not need or need.community_id != community_id:
        raise HTTPException(404, "需求不存在")
    if need.user_id != user.id:
        raise HTTPException(403, "只能修改自己的需求")
    if data.status not in {"ACTIVE", "MATCHED", "CLOSED"}:
        raise HTTPException(422, "无效需求状态")
    need.status = data.status
    session.add(need)
    session.commit()
    return need_data(session, need)


@app.get("/api/communities/{community_id}/need-summary")
def community_need_summary(community_id: int, session: Session = Depends(get_session),
                           active_community: int = Depends(current_community_id)) -> dict:
    if community_id != active_community:
        raise HTTPException(404, "社区不存在")
    buildings = session.exec(select(Building).where(Building.community_id == community_id)).all()
    needs = session.exec(select(Need).where(Need.community_id == community_id, Need.status == "ACTIVE")).all()
    active = [need for need in needs if need_is_active(need, utc_now())]
    return {"community_id": community_id, "total": len(active), "buildings": [
        {"building_id": building.id, "name": building.name,
         "count": sum(need.building_id == building.id for need in active),
         "categories": [{"category": category, "count": count} for category, count in Counter(
             need.category or "其他" for need in active if need.building_id == building.id
         ).most_common(4)]} for building in buildings]}


@app.get("/api/items/{item_id}/matching-needs")
def item_matching_needs(item_id: int, session: Session = Depends(get_session),
                        community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if item.status in {"COMPLETED", "ARCHIVED"}:
        return {"count": 0, "budget_count": 0, "matches": []}
    rows = session.exec(select(NeedMatch, Need).join(Need, Need.id == NeedMatch.need_id)
                        .where(NeedMatch.item_id == item.id)).all()
    active = [(match, need) for match, need in rows if need_is_active(need, utc_now())]
    return {"count": len(active), "budget_count": sum(need.budget_max is not None for _, need in active),
            "matches": [{"need_id": need.id, "summary": need.raw_text[:100], "reasons": match.reasons,
                         "budget_max": need.budget_max} for match, need in active[:8]]}


@app.get("/api/passports/{code}")
def passport_detail(code: str, session: Session = Depends(get_session),
                    community_id: int = Depends(current_community_id)) -> dict:
    passport = session.exec(select(ItemPassport).where(ItemPassport.passport_code == code)).first()
    if not passport:
        raise HTTPException(404, "物品护照不存在")
    items = session.exec(select(Item).where(Item.passport_id == passport.id)
                         .order_by(Item.created_at, Item.id)).all()
    if not items or session.get(Building, items[0].building_id).community_id != community_id:
        raise HTTPException(404, "物品护照不存在")
    ids = [item.id for item in items]
    transactions = {row.item_id: row for row in session.exec(select(Transaction).where(
        Transaction.item_id.in_(ids))).all()}
    events = session.exec(select(ItemEvent).where(ItemEvent.item_id.in_(ids),
                        ItemEvent.event_type.in_(["ITEM_CREATED", "ITEM_RELISTED", "TRANSACTION_COMPLETED"]))
                          .order_by(ItemEvent.created_at, ItemEvent.id)).all()
    item_by_id = {item.id: item for item in items}
    timeline = []
    for event in events:
        item = item_by_id[event.item_id]
        building = session.get(Building, item.building_id)
        if event.event_type == "TRANSACTION_COMPLETED":
            recipient = session.get(User, transactions[item.id].recipient_id) if item.id in transactions else None
            recipient_building = session.get(Building, recipient.building_id) if recipient and recipient.building_id else None
            label = f"流转给{recipient_building.name if recipient_building else '社区'}邻居"
        elif event.event_type == "ITEM_RELISTED":
            label = f"{building.name}邻居再次发布"
        else:
            label = f"{building.name}邻居发布"
        timeline.append({"id": event.id, "item_id": item.id, "type": event.event_type,
                         "text": label, "created_at": iso_utc(event.created_at)})
    people = {item.owner_id for item in items} | {row.recipient_id for row in transactions.values()}
    latest = items[-1]
    passport_created = as_utc(passport.created_at)
    return {"passport_code": passport.passport_code, "title": latest.title, "category": latest.category,
            "image_key": latest.image_key, "status": latest.status,
            "current_item_id": latest.id, "completed_count": len(transactions),
            "neighbor_count": len(people),
            "days_in_community": max(0, (utc_now() - passport_created).days),
            "timeline": timeline}


@app.post("/api/items/{item_id}/relist", status_code=201)
def relist_item(item_id: int, data: ItemInput, session: Session = Depends(get_session),
                user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    previous = get_item_or_404(session, item_id, community_id)
    if previous.status != "COMPLETED":
        raise HTTPException(409, "只有已完成流转的物品可以再次发布")
    passport = ensure_passport(session, previous)
    items = session.exec(select(Item).where(Item.passport_id == passport.id)
                         .order_by(Item.created_at.desc(), Item.id.desc())).all()
    if not items or items[0].id != previous.id:
        raise HTTPException(409, "请从当前最新的流转记录再次发布")
    transaction = session.exec(select(Transaction).where(Transaction.item_id == previous.id)).first()
    if not transaction or transaction.recipient_id != user.id:
        raise HTTPException(403, "只有这件物品的当前拥有者可以再次发布")
    if data.image_key <= 35 or data.image_key == previous.image_key:
        raise HTTPException(422, "再次发布请上传当前状态的实物照片")
    validate_item_input(data, session, community_id, user.id)
    times = validate_slots(data.handover_slots)
    if not times:
        now = utc_now()
        times = [(now + timedelta(hours=hours), now + timedelta(hours=hours, minutes=30)) for hours in (2, 4, 26)]
    values = data.model_dump(exclude={"handover_slots", "selected_price_strategy", "selected_price_source"})
    values["category"] = data.category.strip()
    values["public_location"] = f"{session.get(Building, data.building_id).name}附近"
    values["handover_location"] = data.handover_location.strip() if data.handover_location else f"{session.get(Building, data.building_id).name}大厅"
    if data.trade_type != "FIXED_PRICE":
        values["price"] = None
    item = Item(**values, owner_id=user.id, passport_id=passport.id, status="AVAILABLE", last_confirmed_at=utc_now())
    session.add(item)
    session.flush()
    session.add_all([HandoverSlot(item_id=item.id, starts_at=start, ends_at=end) for start, end in times])
    record_item_event(session, item.id, "ITEM_RELISTED", user.id, {"previous_item_id": previous.id})
    matched = record_matching_needs(session, item, community_id)
    session.commit()
    return {**item_data(session, item, user.id), "matching_needs_count": len(matched)}


@app.post("/api/items", status_code=201)
def create_item(data: ItemInput, session: Session = Depends(get_session), user: User = Depends(current_user),
                community_id: int = Depends(current_community_id)) -> dict:
    validate_item_input(data, session, community_id, user.id)
    times = validate_slots(data.handover_slots)
    if not times:
        now = utc_now()
        times = [(now + timedelta(hours=hours), now + timedelta(hours=hours, minutes=30)) for hours in (2, 4, 26)]
    values = data.model_dump(exclude={"handover_slots", "selected_price_strategy", "selected_price_source"})
    values["category"] = data.category.strip()
    values["public_location"] = f"{session.get(Building, data.building_id).name}附近"
    if data.trade_type != "FIXED_PRICE":
        values["price"] = None
    values["handover_location"] = data.handover_location.strip() if data.handover_location else f"{session.get(Building, data.building_id).name}大厅"
    item = Item(**values, owner_id=user.id, status="AVAILABLE", last_confirmed_at=utc_now())
    session.add(item)
    session.flush()
    session.add_all([HandoverSlot(item_id=item.id, starts_at=start, ends_at=end) for start, end in times])
    record_item_event(session, item.id, "ITEM_CREATED", user.id, created_at=item.created_at)
    if data.selected_price_strategy:
        record_item_event(session, item.id, "PRICE_STRATEGY_SELECTED", user.id,
                          {"strategy": data.selected_price_strategy, "price": item.price,
                           "source": data.selected_price_source or "RULE_FALLBACK"})
    matched = record_matching_needs(session, item, community_id)
    session.commit()
    session.refresh(item)
    return {**item_data(session, item, user.id), "matching_needs_count": len(matched)}


@app.post("/api/items/batch", status_code=201)
def publish_batch(data: BatchPublishInput, session: Session = Depends(get_session),
                  user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    if not data.confirmed:
        raise HTTPException(422, "请逐件核对并确认后再批量发布")
    normalized = []
    for entry in data.items:
        validate_item_input(entry, session, community_id, user.id)
        times = validate_slots(entry.handover_slots)
        if not times:
            now = utc_now()
            times = [(now + timedelta(hours=hours), now + timedelta(hours=hours, minutes=30)) for hours in (2, 4, 26)]
        normalized.append((entry, times))
    batch = BatchPublish(user_id=user.id, community_id=community_id)
    session.add(batch)
    session.flush()
    created = []
    match_total = 0
    for entry, times in normalized:
        building = session.get(Building, entry.building_id)
        values = entry.model_dump(exclude={"handover_slots", "selected_price_strategy", "selected_price_source"})
        values["category"] = entry.category.strip()
        values["public_location"] = f"{building.name}附近"
        values["handover_location"] = entry.handover_location.strip() if entry.handover_location else f"{building.name}大厅"
        if entry.trade_type != "FIXED_PRICE":
            values["price"] = None
        item = Item(**values, owner_id=user.id, batch_id=batch.id, status="AVAILABLE",
                    last_confirmed_at=utc_now())
        session.add(item)
        session.flush()
        session.add_all([HandoverSlot(item_id=item.id, starts_at=start, ends_at=end) for start, end in times])
        record_item_event(session, item.id, "ITEM_CREATED", user.id, created_at=item.created_at)
        match_total += len(record_matching_needs(session, item, community_id))
        created.append(item)
    session.commit()
    return {"batch_id": batch.id, "count": len(created), "matching_needs_count": match_total,
            "items": items_data(session, created, user.id)}


@app.patch("/api/items/{item_id}")
def update_item(
    item_id: int, data: ItemInput, session: Session = Depends(get_session), user: User = Depends(current_user),
    community_id: int = Depends(current_community_id),
) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if item.owner_id != user.id:
        raise HTTPException(403, "只有发布者可以编辑")
    if item.status != "AVAILABLE":
        raise HTTPException(409, "已预约或已完成的物品不能编辑")
    if session.exec(select(Reservation.id).where(Reservation.item_id == item_id,
                                                 Reservation.status.in_(["PENDING", "CONFIRMED"]))).first():
        raise HTTPException(409, "已有预约申请，暂时不能编辑")
    validate_item_input(data, session, community_id, user.id)
    times = validate_slots(data.handover_slots)
    previous_price, previous_goal = item.price, item.disposal_goal
    for key, value in data.model_dump(exclude={"handover_slots", "selected_price_strategy", "selected_price_source"}).items():
        setattr(item, key, value)
    item.category = data.category.strip()
    item.public_location = f"{session.get(Building, data.building_id).name}附近"
    if not item.handover_location:
        item.handover_location = f"{session.get(Building, item.building_id).name}大厅"
    if item.trade_type != "FIXED_PRICE":
        item.price = None
    if data.selected_price_strategy and (item.price != previous_price or item.disposal_goal != previous_goal):
        record_item_event(session, item.id, "PRICE_STRATEGY_SELECTED", user.id,
                          {"strategy": data.selected_price_strategy, "price": item.price,
                           "source": data.selected_price_source or "RULE_FALLBACK"})
    if times:
        old_slots = session.exec(select(HandoverSlot).where(HandoverSlot.item_id == item_id)).all()
        if session.exec(select(Reservation.id).where(Reservation.item_id == item_id)).first():
            raise HTTPException(409, "已有预约历史，不能修改交接时间")
        for slot in old_slots:
            session.delete(slot)
        session.add_all([HandoverSlot(item_id=item_id, starts_at=start, ends_at=end) for start, end in times])
    for match in session.exec(select(NeedMatch).where(NeedMatch.item_id == item.id)).all():
        session.delete(match)
    session.flush()
    matched = record_matching_needs(session, item, community_id)
    session.add(item)
    session.commit()
    session.refresh(item)
    return {**item_data(session, item, user.id), "matching_needs_count": len(matched)}


@app.post("/api/items/{item_id}/interest")
def add_interest(item_id: int, session: Session = Depends(get_session), user: User = Depends(current_user),
                 community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if effective_status(item) != "AVAILABLE":
        raise HTTPException(409, "请等待发布者确认在架后再预约")
    if item.owner_id == user.id:
        raise HTTPException(403, "不能对自己的物品表达意向")
    existing = session.exec(select(Interest).where(Interest.item_id == item_id, Interest.user_id == user.id)).first()
    if not existing:
        session.add(Interest(item_id=item_id, user_id=user.id))
        record_item_event(session, item_id, "WANT_CREATED", user.id)
        session.commit()
    return {"ok": True}


@app.patch("/api/items/{item_id}/confirm-active")
def confirm_active(item_id: int, session: Session = Depends(get_session), user: User = Depends(current_user),
                   community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if item.owner_id != user.id:
        raise HTTPException(403, "只有发布者可以确认在架")
    if item.status != "AVAILABLE":
        raise HTTPException(409, "只有待流转物品可以确认在架")
    item.last_confirmed_at = utc_now()
    session.add(item)
    record_item_event(session, item.id, "ACTIVE_CONFIRMED", user.id)
    session.commit()
    session.refresh(item)
    return item_data(session, item, user.id)


@app.post("/api/items/{item_id}/archive")
def archive_item(item_id: int, session: Session = Depends(get_session), user: User = Depends(current_user),
                 community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if item.owner_id != user.id:
        raise HTTPException(403, "只有发布者可以归档")
    if item.status != "AVAILABLE":
        raise HTTPException(409, "已预约或已完成的物品不能直接归档")
    pending = session.exec(select(Reservation).where(Reservation.item_id == item_id, Reservation.status == "PENDING")).all()
    for reservation in pending:
        reservation.status = "CANCELLED"
        session.add(reservation)
        record_item_event(session, item.id, "RESERVATION_CANCELLED", user.id,
                          {"reservation_id": reservation.id, "reason": "item_archived"})
    item.status = "ARCHIVED"
    session.add(item)
    record_item_event(session, item.id, "ITEM_ARCHIVED", user.id)
    session.commit()
    return item_data(session, item, user.id)


@app.delete("/api/items/{item_id}/interest")
def remove_interest(item_id: int, session: Session = Depends(get_session), user: User = Depends(current_user),
                    community_id: int = Depends(current_community_id)) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if item.status in {"COMPLETED", "ARCHIVED"}:
        raise HTTPException(409, "这件物品已结束流转")
    existing = session.exec(select(Interest).where(Interest.item_id == item_id, Interest.user_id == user.id)).first()
    if existing:
        session.delete(existing)
        session.commit()
    return {"ok": True}


@app.post("/api/items/{item_id}/comments", status_code=201)
def add_comment(
    item_id: int, data: CommentInput, session: Session = Depends(get_session), user: User = Depends(current_user),
    community_id: int = Depends(current_community_id),
) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if item.status in {"COMPLETED", "ARCHIVED"}:
        raise HTTPException(409, "已结束流转的物品不可留言")
    comment = Comment(item_id=item_id, user_id=user.id, body=data.body.strip())
    if not comment.body:
        raise HTTPException(422, "留言不能为空")
    session.add(comment)
    session.commit()
    session.refresh(comment)
    return {"id": comment.id, "body": comment.body, "created_at": iso_utc(comment.created_at), "user": user_data(user)}


@app.post("/api/items/{item_id}/complete")
def complete_item(
    item_id: int, data: CompleteInput, session: Session = Depends(get_session), user: User = Depends(current_user),
    community_id: int = Depends(current_community_id),
) -> dict:
    get_item_or_404(session, item_id, community_id)
    raise HTTPException(409, "请通过预约和领取码完成交接")


@app.post("/api/items/{item_id}/reservations", status_code=201)
def create_reservation(
    item_id: int, data: ReservationInput, session: Session = Depends(get_session),
    user: User = Depends(current_user), community_id: int = Depends(current_community_id),
) -> dict:
    item = get_item_or_404(session, item_id, community_id)
    if item.owner_id == user.id:
        raise HTTPException(403, "不能预约自己的物品")
    if effective_status(item) != "AVAILABLE":
        raise HTTPException(409, "物品当前不可预约，请查看在架状态")
    slot = session.get(HandoverSlot, data.slot_id)
    if not slot or slot.item_id != item_id or as_utc(slot.starts_at) <= utc_now():
        raise HTTPException(422, "请选择有效的未来交接时间")
    older_pending = session.exec(select(Reservation).where(Reservation.item_id == item_id,
                       Reservation.buyer_id == user.id, Reservation.status == "PENDING")).all()
    for older in older_pending:
        older_slot = session.get(HandoverSlot, older.slot_id)
        if as_utc(older_slot.starts_at) <= utc_now():
            older.status = "EXPIRED"
            session.add(older)
            record_item_event(session, item_id, "RESERVATION_CANCELLED", user.id,
                              {"reservation_id": older.id, "reason": "slot_expired"})
    session.flush()
    if session.exec(select(Reservation.id).where(Reservation.item_id == item_id,
                                                  Reservation.buyer_id == user.id,
                                                  Reservation.status == "PENDING")).first():
        raise HTTPException(409, "你已经提交过待确认预约")
    if session.exec(select(Reservation.id).where(Reservation.item_id == item_id,
                                                  Reservation.status == "CONFIRMED")).first():
        raise HTTPException(409, "这件物品已有确认的预约")
    reservation = Reservation(item_id=item_id, buyer_id=user.id, seller_id=item.owner_id,
                              slot_id=slot.id, status="PENDING")
    session.add(reservation)
    session.flush()
    if not session.exec(select(Interest.id).where(Interest.item_id == item_id, Interest.user_id == user.id)).first():
        session.add(Interest(item_id=item_id, user_id=user.id))
        record_item_event(session, item_id, "WANT_CREATED", user.id)
    record_item_event(session, item_id, "RESERVATION_CREATED", user.id,
                      {"reservation_id": reservation.id, "actor_name": user.display_name})
    private_notice(session, item_id, user.id, item.owner_id,
                   f"我预约了北京时间 {chat_slot_label(slot.starts_at)} 的交接时间，请确认。", "RESERVATION")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "预约已存在，请刷新页面") from None
    session.refresh(reservation)
    return reservation_data(session, reservation, user.id)


@app.post("/api/reservations/{reservation_id}/confirm")
def confirm_reservation(
    reservation_id: int, session: Session = Depends(get_session),
    user: User = Depends(current_user), community_id: int = Depends(current_community_id),
) -> dict:
    reservation, item = get_reservation_or_404(session, reservation_id, community_id)
    if reservation.seller_id != user.id:
        raise HTTPException(403, "只有发布者可以接受预约")
    if reservation.status != "PENDING" or effective_status(item) != "AVAILABLE":
        raise HTTPException(409, "当前预约或物品状态不允许接受")
    slot = session.get(HandoverSlot, reservation.slot_id)
    if as_utc(slot.starts_at) <= utc_now():
        reservation.status = "EXPIRED"
        session.add(reservation)
        record_item_event(session, item.id, "RESERVATION_CANCELLED", user.id,
                          {"reservation_id": reservation.id, "reason": "slot_expired"})
        session.commit()
        raise HTTPException(409, "所选交接时间已过，请让邻居重新预约")
    reservation.status = "CONFIRMED"
    reservation.confirmed_at = utc_now()
    reservation.pickup_code = str(secrets.randbelow(9000) + 1000)
    item.status = "RESERVED"
    session.add(reservation)
    session.add(item)
    record_item_event(session, item.id, "RESERVATION_CONFIRMED", user.id,
                      {"reservation_id": reservation.id})
    private_notice(session, item.id, user.id, reservation.buyer_id,
                   f"预约已确认：北京时间 {chat_slot_label(slot.starts_at)}。请在私聊中沟通交接，领取码仅你可见。", "RESERVATION")
    other_pending = session.exec(select(Reservation).where(
        Reservation.item_id == item.id, Reservation.id != reservation.id, Reservation.status == "PENDING"
    )).all()
    for other in other_pending:
        other.status = "CANCELLED"
        session.add(other)
        record_item_event(session, item.id, "RESERVATION_CANCELLED", user.id,
                          {"reservation_id": other.id, "reason": "other_booking_confirmed"})
        private_notice(session, item.id, user.id, other.buyer_id, "这件物品已由其他邻居预约，你的申请已结束。", "RESERVATION")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "这件物品已有确认的预约") from None
    return reservation_data(session, reservation, user.id)


@app.post("/api/reservations/{reservation_id}/reject")
def reject_reservation(
    reservation_id: int, session: Session = Depends(get_session),
    user: User = Depends(current_user), community_id: int = Depends(current_community_id),
) -> dict:
    reservation, item = get_reservation_or_404(session, reservation_id, community_id)
    if reservation.seller_id != user.id:
        raise HTTPException(403, "只有发布者可以拒绝预约")
    if reservation.status != "PENDING":
        raise HTTPException(409, "只能拒绝待确认预约")
    cancel_reservation_record(session, reservation, item, user.id, "seller_rejected")
    session.commit()
    return reservation_data(session, reservation, user.id)


@app.post("/api/reservations/{reservation_id}/cancel")
def cancel_reservation(
    reservation_id: int, session: Session = Depends(get_session),
    user: User = Depends(current_user), community_id: int = Depends(current_community_id),
) -> dict:
    reservation, item = get_reservation_or_404(session, reservation_id, community_id)
    if user.id not in {reservation.buyer_id, reservation.seller_id}:
        raise HTTPException(403, "只有预约双方可以取消")
    if reservation.status not in {"PENDING", "CONFIRMED"}:
        raise HTTPException(409, "这个预约已结束")
    cancel_reservation_record(session, reservation, item, user.id, "user_cancelled")
    session.commit()
    return reservation_data(session, reservation, user.id)


@app.post("/api/reservations/{reservation_id}/complete")
def complete_reservation(
    reservation_id: int, data: PickupInput, session: Session = Depends(get_session),
    user: User = Depends(current_user), community_id: int = Depends(current_community_id),
) -> dict:
    reservation, item = get_reservation_or_404(session, reservation_id, community_id)
    if reservation.seller_id != user.id:
        raise HTTPException(403, "只有发布者可以确认交接")
    if reservation.status != "CONFIRMED" or item.status != "RESERVED":
        raise HTTPException(409, "这个预约尚未确认或已经完成")
    if not secrets.compare_digest(reservation.pickup_code or "", data.pickup_code):
        raise HTTPException(422, "领取码不正确")
    now = utc_now()
    reservation.status = "COMPLETED"
    reservation.completed_at = now
    item.status = "COMPLETED"
    item.completed_at = now
    ensure_passport(session, item)
    session.add(reservation)
    session.add(item)
    session.add(Transaction(item_id=item.id, recipient_id=reservation.buyer_id, completed_at=now))
    record_item_event(session, item.id, "TRANSACTION_COMPLETED", user.id,
                      {"reservation_id": reservation.id})
    private_notice(session, item.id, user.id, reservation.buyer_id, "交接已完成，感谢让好物继续流转。", "HANDOVER")
    try:
        session.commit()
    except IntegrityError:
        session.rollback()
        raise HTTPException(409, "这件物品已完成流转") from None
    return {"reservation": reservation_data(session, reservation, user.id), "item": item_data(session, item, user.id),
            "hours_to_complete": round((now - as_utc(item.created_at)).total_seconds() / 3600, 2)}


@app.post("/api/reservations/{reservation_id}/handover-status")
def update_handover_status(
    reservation_id: int, data: HandoverStatusInput, session: Session = Depends(get_session),
    user: User = Depends(current_user), community_id: int = Depends(current_community_id),
) -> dict:
    reservation, item = get_reservation_or_404(session, reservation_id, community_id)
    if reservation.buyer_id != user.id:
        raise HTTPException(403, "只有预约买家可以更新交接状态")
    if reservation.status != "CONFIRMED" or item.status != "RESERVED":
        raise HTTPException(409, "只有已确认的预约可以更新交接状态")
    if data.status not in {"DEPARTED", "ARRIVED", "DELAYED"}:
        raise HTTPException(422, "无效的交接状态")
    if reservation.handover_status == data.status:
        return reservation_data(session, reservation, user.id)
    if reservation.handover_status == "ARRIVED":
        raise HTTPException(409, "已到达后不能改回出发或晚到")
    reservation.handover_status = data.status
    metadata = {"reservation_id": reservation.id, "actor_name": user.display_name}
    if data.status == "ARRIVED":
        reservation.arrived_at = utc_now()
        event_type = "BUYER_ARRIVED"
    elif data.status == "DELAYED":
        reservation.delay_minutes = 10
        metadata["delay_minutes"] = 10
        event_type = "BUYER_DELAYED"
    else:
        event_type = "BUYER_DEPARTED"
    session.add(reservation)
    record_item_event(session, item.id, event_type, user.id, metadata)
    private_notice(session, item.id, user.id, reservation.seller_id,
                   {"DEPARTED": "我已出发，稍后见。", "ARRIVED": "我已到达约定地点。", "DELAYED": "我会晚到约 10 分钟。"}[data.status], "HANDOVER")
    session.commit()
    return reservation_data(session, reservation, user.id)


@app.post("/api/reservations/{reservation_id}/wait")
def wait_for_buyer(
    reservation_id: int, session: Session = Depends(get_session),
    user: User = Depends(current_user), community_id: int = Depends(current_community_id),
) -> dict:
    reservation, item = get_reservation_or_404(session, reservation_id, community_id)
    if reservation.seller_id != user.id:
        raise HTTPException(403, "只有发布者可以延长等待")
    if reservation.status != "CONFIRMED" or not reservation_data(session, reservation, user.id)["overdue"]:
        raise HTTPException(409, "预约尚未超过等待时间")
    reservation.wait_until = utc_now() + timedelta(minutes=10)
    session.add(reservation)
    record_item_event(session, item.id, "SELLER_WAIT_EXTENDED", user.id,
                      {"reservation_id": reservation.id, "minutes": 10})
    session.commit()
    return reservation_data(session, reservation, user.id)


@app.post("/api/reservations/{reservation_id}/release")
def release_reservation(
    reservation_id: int, session: Session = Depends(get_session),
    user: User = Depends(current_user), community_id: int = Depends(current_community_id),
) -> dict:
    reservation, item = get_reservation_or_404(session, reservation_id, community_id)
    if reservation.seller_id != user.id:
        raise HTTPException(403, "只有发布者可以释放预约")
    if reservation.status != "CONFIRMED" or not reservation_data(session, reservation, user.id)["overdue"]:
        raise HTTPException(409, "预约尚未超过等待时间")
    cancel_reservation_record(session, reservation, item, user.id, "seller_released_after_timeout")
    session.commit()
    return reservation_data(session, reservation, user.id)


@app.get("/api/community/map")
def community_map(trade_type: str | None = None, session: Session = Depends(get_session),
                  community_id: int = Depends(current_community_id),
                  location: tuple[float, float] | None = Depends(request_location)) -> dict:
    if trade_type and trade_type not in TRADE_TYPES:
        raise HTTPException(422, "无效的交易方式")
    buildings = session.exec(select(Building).where(Building.community_id == community_id).order_by(Building.id)).all()
    result = []
    for building in buildings:
        statement = select(Item).where(Item.building_id == building.id, Item.status.in_(["AVAILABLE", "RESERVED"]))
        if trade_type:
            statement = statement.where(Item.trade_type == trade_type)
        items = session.exec(statement.order_by(Item.created_at.desc())).all()
        result.append({
            "id": building.id,
            "name": building.name,
            "map_key": building.map_key,
            "map_x": building.map_x,
            "map_y": building.map_y,
            "active_count": len(items),
            "items": items_data(session, items[:4], location=location),
        })
    return {"buildings": result}


def month_start(value: datetime) -> datetime:
    return datetime(value.year, value.month, 1, tzinfo=timezone.utc)


def shift_month(value: datetime, offset: int) -> datetime:
    month_index = value.year * 12 + value.month - 1 + offset
    return datetime(month_index // 12, month_index % 12 + 1, 1, tzinfo=timezone.utc)


@app.get("/api/community/stats")
def community_stats(session: Session = Depends(get_session), community_id: int = Depends(current_community_id)) -> dict:
    now = utc_now()
    start = month_start(now)
    items = session.exec(select(Item).join(Building).where(Building.community_id == community_id)).all()
    item_ids = [item.id for item in items]
    interests = session.exec(select(Interest).where(Interest.item_id.in_(item_ids))).all() if item_ids else []
    interest_counts: dict[int, int] = {}
    for interest in interests:
        interest_counts[interest.item_id] = interest_counts.get(interest.item_id, 0) + 1
    completed = [item for item in items if item.status == "COMPLETED" and item.completed_at]
    active_items = [item for item in items if item.status in {"AVAILABLE", "RESERVED"}]
    completed_ids = [item.id for item in completed]
    structured_ids = set(session.exec(select(Reservation.item_id).where(
        Reservation.item_id.in_(completed_ids), Reservation.status == "COMPLETED"
    )).all()) if completed_ids else set()
    average_hours = (sum((as_utc(item.completed_at) - as_utc(item.created_at)).total_seconds() / 3600
                         for item in completed) / len(completed)) if completed else 0
    fastest = sorted(completed, key=lambda item: as_utc(item.completed_at) - as_utc(item.created_at))[:3]
    wanted = sorted(
        [item for item in items if item.status in {"AVAILABLE", "RESERVED"}],
        key=lambda item: (interest_counts.get(item.id, 0), item.created_at), reverse=True,
    )[:3]
    trends = []
    for offset in range(-5, 1):
        left = shift_month(start, offset)
        right = shift_month(start, offset + 1)
        trends.append({
            "month": f"{left.month}月",
            "published": sum(left <= as_utc(item.created_at) < right for item in items),
            "completed": sum(left <= as_utc(item.completed_at) < right for item in completed),
        })
    views = session.exec(select(ItemView).where(ItemView.item_id.in_(item_ids))).all() if item_ids else []
    publish_dates = Counter(item.created_at.date() for item in items)
    complete_dates = Counter(item.completed_at.date() for item in completed)
    view_dates = Counter(view.viewed_at.date() for view in views)
    daily_trend = []
    for days_ago in range(29, -1, -1):
        day = (now - timedelta(days=days_ago)).date()
        daily_trend.append({"date": day.isoformat(), "label": f"{day.month}/{day.day}",
                            "published": publish_dates[day], "completed": complete_dates[day],
                            "views": view_dates[day]})
    month_items = [item for item in items if as_utc(item.created_at) >= start]
    category_counts = Counter(item.category for item in month_items)
    category_distribution = [{"category": category, "count": count,
                              "percentage": round(count / len(month_items) * 100, 1)}
                             for category, count in category_counts.most_common()] if month_items else []
    buildings = session.exec(select(Building).where(Building.community_id == community_id).order_by(Building.id)).all()
    last30 = now - timedelta(days=30)
    building_heat = []
    for building in buildings:
        building_items = [item for item in items if item.building_id == building.id]
        building_heat.append({"building_id": building.id, "name": building.name,
                              "active_count": sum(item.status in {"AVAILABLE", "RESERVED"} for item in building_items),
                              "completed_count": sum(item.status == "COMPLETED" for item in building_items),
                              "last30_activity": sum(as_utc(item.created_at) >= last30 for item in building_items)
                              + sum(item.completed_at is not None and as_utc(item.completed_at) >= last30 for item in building_items)})
    building_heat.sort(key=lambda row: (row["last30_activity"], row["active_count"]), reverse=True)
    completion_base = len(completed) + len(active_items)
    needs = session.exec(select(Need).where(Need.community_id == community_id)).all()
    recent_needs = [need for need in needs if as_utc(need.created_at) >= now - timedelta(days=7)]
    need_ids = [need.id for need in recent_needs]
    matched_need_ids = set(session.exec(select(NeedMatch.need_id).where(NeedMatch.need_id.in_(need_ids))).all()) if need_ids else set()
    passport_ids = {item.passport_id for item in completed if item.passport_id}
    passports = {passport.id: passport for passport in session.exec(select(ItemPassport).where(
        ItemPassport.id.in_(passport_ids))).all()} if passport_ids else {}
    return {
        "month_published": sum(as_utc(item.created_at) >= start for item in items),
        "month_completed": sum(as_utc(item.completed_at) >= start for item in completed),
        "active_count": sum(item.status in {"AVAILABLE", "RESERVED"} for item in items),
        "total_completed": len(completed),
        "avg_transfer_hours": round(average_hours, 1),
        "no_chat_completion_rate": round(len(structured_ids) / len(completed) * 100, 1) if completed else 0,
        "fastest": [{**serialized, "hours_to_complete": round((as_utc(item.completed_at) - as_utc(item.created_at)).total_seconds() / 3600, 2)} for item, serialized in zip(fastest, items_data(session, fastest))],
        "most_wanted": items_data(session, wanted),
        "trend": trends,
        "daily_trend": daily_trend,
        "category_distribution": category_distribution,
        "building_heat": building_heat,
        "last30_completed": sum(as_utc(item.completed_at) >= last30 for item in completed),
        "completion_share": round(len(completed) / completion_base * 100, 1) if completion_base else 0,
        "week_need_count": len(recent_needs),
        "week_matched_need_count": len(matched_need_ids),
        "month_batch_items": sum(item.batch_id is not None and as_utc(item.created_at) >= start for item in items),
        "relisted_completed_count": sum(item.passport_id in passports and
            passports[item.passport_id].root_item_id != item.id for item in completed),
    }


def deepseek_json(system_prompt: str, user_prompt: str, *, fast: bool = False,
                  required_key: str | None = None) -> dict:
    key = os.getenv("DEEPSEEK_API_KEY")
    if not key:
        raise HTTPException(503, "尚未配置 DeepSeek API Key，请手工填写后继续发布")
    try:
        client = OpenAI(api_key=key, base_url="https://api.deepseek.com",
                        timeout=45.0 if fast else 20.0, max_retries=1 if fast else 0)
        failure = "empty_content"
        for _ in range(2 if fast else 1):
            response = client.chat.completions.create(
                model=os.getenv("DEEPSEEK_MODEL", "deepseek-flash"),
                messages=[{"role": "system", "content": system_prompt}, {"role": "user", "content": user_prompt}],
                response_format={"type": "json_object"},
                max_tokens=1200 if fast else 1600,
                **({"extra_body": {"thinking": {"type": "disabled"}}} if fast else {}),
            )
            content = response.choices[0].message.content
            if not content:
                continue
            try:
                result = json.loads(content)
            except json.JSONDecodeError:
                failure = "invalid_json"
                continue
            if not isinstance(result, dict):
                failure = "invalid_shape"
                continue
            if required_key:
                value = result.get(required_key)
                if not isinstance(value, str) or not 4 <= len(value.strip()) <= 500:
                    failure = "invalid_required_text"
                    continue
            return result
        raise ValueError(failure)
    except (OpenAIError, ValueError, json.JSONDecodeError, IndexError) as exc:
        logger.warning("DeepSeek JSON request failed: mode=%s error=%s status=%s",
                       "description" if fast else "general", type(exc).__name__,
                       getattr(exc, "status_code", None))
        detail = "DeepSeek 暂时没有返回可用描述，已自动重试，请稍后再试" if fast else "AI 建议暂时不可用，请稍后重试或手工填写"
        raise HTTPException(502, detail) from exc


@app.post("/api/ai/optimize-description")
def optimize_description(data: DescriptionInput, _: User = Depends(current_user)) -> dict:
    result = deepseek_json(
        "你是小区闲置转让助手。根据用户输入写一段约120至180字、自然有趣且有吸引力的中文物品描述。"
        "可用温暖的邻里语气，具体说明已提供的成色、使用感受和适合的使用场景，结尾给出轻松的沟通邀请。"
        "只能整理用户明确提供的事实，不可编造品牌、功能、购买时间、保修、瑕疵或价格；资料不足时宁可写短一些。"
        '仅返回JSON对象，格式：{"description":"..."}。',
        f"标题：{data.title}\n成色：{data.condition}\n原描述：{data.rough_description}\n请输出JSON。",
        fast=True, required_key="description",
    )
    description = result.get("description")
    if not isinstance(description, str) or not 4 <= len(description.strip()) <= 500:
        raise HTTPException(502, "AI 返回的描述格式无效")
    return {"description": description.strip()}


@app.post("/api/ai/suggest-price")
def suggest_price(
    data: PriceInput, session: Session = Depends(get_session), _: User = Depends(current_user),
    community_id: int = Depends(current_community_id),
) -> dict:
    comparable_items = session.exec(
        select(Item).join(Building).where(
            Building.community_id == community_id,
            Item.category == data.category,
            Item.trade_type == "FIXED_PRICE",
            Item.status == "COMPLETED",
            Item.price.is_not(None),
        ).order_by(Item.completed_at.desc()).limit(6)
    ).all()
    comparable = [{"title": item.title, "condition": item.condition, "price": item.price} for item in comparable_items]
    result = deepseek_json(
        "你是社区二手物品定价助手。价格单位是人民币元。参考同社区的历史标价，"
        "但历史标价不等于真实成交价；不要声称已验证市场行情。资料不足时给宽范围并说明不确定性。"
        "只输出JSON对象，格式："
        '{"min_price":20,"max_price":50,"reason":"...","suggest_free":false}。',
        f"物品：{data.title}\n类别：{data.category}\n成色：{data.condition}\n描述：{data.description}"
        f"\n原价：{data.original_price}\n同社区已送出物品的历史标价：{json.dumps(comparable, ensure_ascii=False)}\n请输出JSON。",
    )
    low, high, reason, free = (result.get(k) for k in ("min_price", "max_price", "reason", "suggest_free"))
    if not isinstance(low, int) or not isinstance(high, int) or not 0 <= low <= high <= 100000:
        raise HTTPException(502, "AI 返回的价格格式无效")
    if not isinstance(reason, str) or not 3 <= len(reason) <= 300 or not isinstance(free, bool):
        raise HTTPException(502, "AI 返回的建议格式无效")
    return {"min_price": low, "max_price": high, "reason": reason, "suggest_free": free, "comparable_count": len(comparable)}


@app.post("/api/ai/pricing-suggestion")
def suggest_pricing_strategy(
    data: PricingStrategyInput, session: Session = Depends(get_session),
    _: User = Depends(current_user), community_id: int = Depends(current_community_id),
) -> dict:
    if data.disposal_goal not in {"FAST", "BALANCED", "PRICE_FIRST"}:
        raise HTTPException(422, "无效的处理目标")
    comparable_items = session.exec(select(Item).join(Building).where(
        Building.community_id == community_id, Item.category == data.category,
        Item.trade_type == "FIXED_PRICE", Item.status == "COMPLETED", Item.price.is_not(None),
    ).order_by(Item.completed_at.desc()).limit(8)).all()
    comparable = [{"title": item.title, "condition": item.condition, "price": item.price} for item in comparable_items]
    return pricing_suggestion(
        title=data.title, description=data.description, condition=data.condition,
        disposal_goal=data.disposal_goal, category=data.category,
        original_price=data.original_price, comparables=comparable, invoke_json=deepseek_json,
    )


def owned_photo_data(session: Session, image_keys: list[int], user_id: int, community_id: int) -> list[tuple[bytes, str]]:
    if len(set(image_keys)) != len(image_keys):
        raise HTTPException(422, "请上传不同角度的照片")
    photos = []
    for image_key in image_keys:
        image = session.get(UploadedImage, image_key)
        if not image or image.owner_id != user_id or image.community_id != community_id:
            raise HTTPException(403, "只能分析自己在当前社区上传的照片")
        path = UPLOAD_DIR / image.filename
        if not path.is_file():
            raise HTTPException(404, "照片文件不存在，请重新上传")
        photos.append((path.read_bytes(), image.mime_type))
    return photos


def visual_pricing(session: Session, community_id: int, analysis: dict, disposal_goal: str,
                   functional_confirmed: bool = False, no_hidden_defects_confirmed: bool = False) -> dict | None:
    if not analysis.get("product_type") or not analysis.get("category"):
        return None
    condition = {"NEW": "外观近新", "GOOD": "外观良好", "FAIR": "有使用痕迹",
                 "WORN": "磨损明显", "UNKNOWN": "外观待确认"}[analysis["condition"]]
    visible = [f"可见瑕疵：{'、'.join(analysis['visible_defects'])}" if analysis["visible_defects"] else "照片中未识别到明显瑕疵",
               f"可见配件：{'、'.join(analysis['visible_accessories'])}" if analysis["visible_accessories"] else "配件情况待确认",
               "发布者确认功能正常" if functional_confirmed else "功能状态尚未由发布者确认",
               "发布者确认无隐藏故障" if no_hidden_defects_confirmed else "隐藏故障无法从照片判断"]
    comparables = session.exec(select(Item).join(Building).where(
        Building.community_id == community_id, Item.category == analysis["category"],
        Item.trade_type == "FIXED_PRICE", Item.status == "COMPLETED", Item.price.is_not(None)
    ).order_by(Item.completed_at.desc()).limit(8)).all()
    prices = [{"title": item.title, "condition": item.condition, "price": item.price} for item in comparables]
    result = pricing_suggestion(title=analysis["product_type"], description="；".join(visible),
                                condition=condition, disposal_goal=disposal_goal,
                                category=analysis["category"], original_price=None,
                                comparables=prices, invoke_json=deepseek_json,
                                condition_source="照片可见外观")
    result["factors"] = [f"照片识别物品：{analysis['product_type']}", *result["factors"],
                         *visible[1:]]
    return result


@app.post("/api/ai/visual-estimate")
def visual_estimate(data: VisualEstimateInput, session: Session = Depends(get_session),
                    user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    if data.disposal_goal not in {"FAST", "BALANCED", "PRICE_FIRST"}:
        raise HTTPException(422, "无效的处理目标")
    images = owned_photo_data(session, data.image_keys, user.id, community_id)
    analysis = analyze_item(images)
    pricing = visual_pricing(session, community_id, analysis, data.disposal_goal,
                             data.functional_confirmed, data.no_hidden_defects_confirmed)
    return {"analysis": analysis, "pricing": pricing,
            "note": "照片只能判断可见信息；功能、购买年份和隐藏故障需要发布者确认。"}


@app.post("/api/ai/batch-recognize")
def batch_recognize(data: BatchRecognizeInput, session: Session = Depends(get_session),
                    user: User = Depends(current_user), community_id: int = Depends(current_community_id)) -> dict:
    if data.disposal_goal not in {"FAST", "BALANCED", "PRICE_FIRST"}:
        raise HTTPException(422, "无效的处理目标")
    images = owned_photo_data(session, data.image_keys, user.id, community_id)
    result = analyze_batch(images)
    drafts = []
    for index, analysis in enumerate(result["items"], 1):
        pricing = visual_pricing(session, community_id, analysis, data.disposal_goal)
        drafts.append({"temp_id": index, "image_keys": [data.image_keys[position] for position in analysis["photo_indices"]],
                       "analysis": analysis, "pricing": pricing,
                       "title": analysis["product_type"] or f"待确认物品 {index}",
                       "category": analysis["category"] or "其他",
                       "condition": {"NEW": "全新未使用", "GOOD": "九成新", "FAIR": "有使用痕迹",
                                     "WORN": "七成新", "UNKNOWN": "待确认"}[analysis["condition"]],
                       "suggested_price": pricing["balanced_price"] if pricing else None})
    return {"items": drafts, "source": result["source"],
            "note": "每件物品都需要发布者确认后才能批量发布；未识别内容不会被当作已确认事实。"}
