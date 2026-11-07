"""Create a coherent, repeatable demo neighborhood without overwriting user-created data."""

from datetime import timedelta
import secrets
import os

from sqlmodel import Session, select

from database import as_utc, create_db, engine, utc_now
from models import BatchPublish, Building, Comment, Community, CommunityMember, CommunityProfile, HandoverSlot, Interest, Item, ItemEvent, ItemPassport, ItemView, Need, Reservation, Transaction, User, UserPreference
from auth import demo_mode, hash_password
from services.item_events import record_item_event
from seed_more import ensure_more_demo_data


# title, category, condition, trade type, price, image key, description
ITEMS = [
    ("北欧风台灯", "家居", "九成新", "FREE", None, 0, "灯光柔和，放在书桌或床头都合适，搬家整理转给邻居。"),
    ("绿萝盆栽", "绿植", "长势良好", "FIXED_PRICE", 20, 1, "已经换好盆，叶片茂盛，适合放在客厅明亮处。"),
    ("原木书架", "家居", "八成新", "FIXED_PRICE", 80, 2, "四层收纳空间，结构稳固，需上门自提。"),
    ("单人沙发椅", "家居", "九成新", "NEGOTIABLE", None, 3, "布面干净，坐垫柔软，家中调整布局转出。"),
    ("实木餐桌", "家居", "八成新", "FIXED_PRICE", 180, 4, "适合两到四人使用，桌面有轻微使用痕迹。"),
    ("迷你电饭煲", "家电", "九成新", "FIXED_PRICE", 55, 5, "容量适合一到两人，功能正常，已清洁。"),
    ("户外双肩包", "运动", "九成新", "NEGOTIABLE", None, 6, "多隔层设计，拉链和肩带都完好。"),
    ("不粘锅三件套", "家居", "八成新", "FIXED_PRICE", 45, 7, "锅具功能正常，适合日常做饭。"),
    ("城市通勤自行车", "运动", "八成新", "FIXED_PRICE", 240, 8, "刹车和车灯正常，可在小区内试骑。"),
    ("轻便婴儿推车", "母婴", "八成新", "FIXED_PRICE", 120, 9, "可折叠，轮子顺畅，已擦洗干净。"),
    ("文学书籍一套", "图书", "九成新", "FREE", None, 10, "六本小说和散文，书页整洁，适合喜欢阅读的邻居。"),
    ("手冲咖啡壶", "生活用品", "九成新", "FIXED_PRICE", 35, 11, "玻璃壶身和滤杯保存完好，周末可约自提。"),
    ("暖光落地灯", "家居", "八成新", "FIXED_PRICE", 65, 0, "暖光灯泡，适合客厅角落，开关正常。"),
    ("龟背竹盆栽", "绿植", "长势良好", "NEGOTIABLE", None, 1, "盆栽健康，因阳台空间有限寻找新主人。"),
    ("儿童绘本十本", "图书", "八成新", "FREE", None, 10, "适合学龄前阅读，边角有正常翻阅痕迹。"),
    ("折叠晾衣架", "生活用品", "九成新", "FIXED_PRICE", 25, 2, "可折叠收纳，展开稳固，适合阳台使用。"),
    ("小型空气炸锅", "家电", "八成新", "FIXED_PRICE", 90, 5, "工作正常，内胆已清洁，容量适合小家庭。"),
    ("瑜伽垫", "运动", "九成新", "FREE", None, 6, "厚度适中，清洗后收好，适合居家拉伸。"),
    ("白色床头柜", "家居", "九成新", "FIXED_PRICE", 45, 2, "双层收纳，抽屉顺畅，需到楼下自提。"),
    ("儿童积木箱", "母婴", "八成新", "NEGOTIABLE", None, 9, "积木已分类装箱，适合亲子搭建。"),
    ("马克杯四只", "生活用品", "九成新", "FREE", None, 11, "四只杯子完好，搬家整理一起送。"),
    ("机械键盘", "家电", "八成新", "FIXED_PRICE", 85, 5, "按键功能正常，已清洁，附连接线。"),
    ("羽毛球拍一对", "运动", "八成新", "FIXED_PRICE", 40, 8, "两支拍子可正常使用，附拍套。"),
    ("儿童平衡车", "母婴", "八成新", "FIXED_PRICE", 75, 9, "车身稳固，适合儿童在空地练习。"),
    ("多肉植物组合", "绿植", "长势良好", "FIXED_PRICE", 18, 1, "三盆多肉植物，带花盆一起转。"),
    ("收纳篮三只", "生活用品", "九成新", "FREE", None, 2, "大小不同，适合衣柜和书桌分类收纳。"),
    ("料理机", "家电", "八成新", "FIXED_PRICE", 70, 5, "搅拌功能正常，杯体和刀头已清洗。"),
    ("旅行背包", "运动", "八成新", "FIXED_PRICE", 60, 6, "肩带完好，容量适合短途出行。"),
    ("儿童故事书", "图书", "九成新", "FREE", None, 10, "适合睡前阅读，页面完整无涂画。"),
    ("原木边几", "家居", "八成新", "FIXED_PRICE", 55, 4, "可放沙发旁，有少量正常使用痕迹。"),
    ("桌面加湿器", "家电", "九成新", "FIXED_PRICE", 30, 11, "小巧不占地方，出雾正常。"),
    ("露营折叠椅", "运动", "九成新", "FIXED_PRICE", 65, 3, "展开收起方便，收纳袋还在。"),
    ("复古阅读灯", "家居", "八成新", "FIXED_PRICE", 48, 0, "灯罩和底座完好，适合阅读角。"),
    ("薄荷盆栽", "绿植", "长势良好", "FREE", None, 1, "阳台种的薄荷，连盆送给愿意照顾的邻居。"),
    ("儿童餐椅", "母婴", "八成新", "FIXED_PRICE", 95, 9, "餐盘可拆卸，使用功能正常。"),
    ("电磁炉", "家电", "九成新", "FIXED_PRICE", 68, 5, "加热和按键正常，适合小户型。"),
    ("两人位布艺沙发", "家居", "八成新", "FIXED_PRICE", 260, 3, "布面干净，坐垫有正常使用痕迹。"),
    ("植物养护工具", "绿植", "九成新", "FREE", None, 1, "小铲子和喷壶，整理阳台时发现闲置。"),
    ("儿童英语绘本", "图书", "八成新", "FIXED_PRICE", 25, 10, "五本一套，内页完整。"),
    ("陶瓷餐盘六只", "生活用品", "九成新", "FIXED_PRICE", 35, 7, "六只同款餐盘，无缺口。"),
    ("健身哑铃一对", "运动", "八成新", "FIXED_PRICE", 45, 8, "适合居家基础训练，表面有少量磨痕。"),
    ("办公转椅", "家居", "八成新", "FIXED_PRICE", 110, 3, "升降和滚轮正常，需要上门自提。"),
    ("宝宝爬行垫", "母婴", "九成新", "FREE", None, 9, "折叠方便，已经擦拭消毒。"),
    ("一人份电煮锅", "家电", "八成新", "FIXED_PRICE", 42, 5, "加热正常，适合煮面和简单料理。"),
    ("经典科普读物", "图书", "九成新", "FREE", None, 10, "三本科普书，保存整洁。"),
    ("手工编织收纳筐", "生活用品", "九成新", "FIXED_PRICE", 22, 2, "适合放杂志、毛毯或玩具。"),
    ("周末野餐垫", "运动", "八成新", "FREE", None, 6, "折叠轻便，适合公园野餐。"),
    ("小型书桌", "家居", "八成新", "FIXED_PRICE", 135, 4, "桌面平整，有少量使用痕迹。"),
    ("玻璃花瓶两只", "生活用品", "九成新", "FREE", None, 11, "高低两只花瓶，均无磕碰。"),
    ("室内绿植架", "绿植", "八成新", "FIXED_PRICE", 50, 2, "多层摆放植物，需自行搬运。"),
]

# Additional product sprite sheets keep the sample photo aligned with its title.
IMAGE_OVERRIDES = {
    "折叠晾衣架": 12, "小型空气炸锅": 13, "瑜伽垫": 14, "白色床头柜": 15,
    "儿童积木箱": 16, "马克杯四只": 17, "机械键盘": 18, "羽毛球拍一对": 19,
    "儿童平衡车": 20, "收纳篮三只": 30, "料理机": 21, "原木边几": 24,
    "桌面加湿器": 22, "露营折叠椅": 25, "儿童餐椅": 27, "电磁炉": 28,
    "植物养护工具": 35, "陶瓷餐盘六只": 26, "健身哑铃一对": 23,
    "宝宝爬行垫": 29, "手工编织收纳筐": 30, "周末野餐垫": 31,
    "小型书桌": 34, "玻璃花瓶两只": 32, "室内绿植架": 33,
}

USERS = [
    ("林小雨", 0, "#d8ead7"), ("陈同学", 1, "#dbe9f4"), ("王思思", 2, "#f5dddc"),
    ("张先生", 0, "#f2e5ca"), ("邻居小鹿", 1, "#e5dff3"), ("刘阿姨", 2, "#e6edc7"),
    ("李然", 0, "#dcebe6"), ("赵可可", 1, "#f4e1d7"), ("周晨", 2, "#dce4f1"),
    ("孙宁", 0, "#f0e3dd"),
]

PREFERRED_CATEGORIES = [
    {"家居", "绿植"}, {"家电", "图书"}, {"母婴", "家居"}, {"运动", "家电"},
    {"绿植", "生活用品"}, {"图书", "家居"}, {"运动", "生活用品"},
    {"母婴", "图书"}, {"家电", "运动"}, {"生活用品", "绿植"},
]


def seed_views(session: Session, users: list[User], items: list[Item]) -> int:
    if session.exec(select(ItemView.id)).first() is not None:
        return 0
    total = 0
    for index, user in enumerate(users):
        matches = [item for item in items if item.status == "AVAILABLE" and item.owner_id != user.id
                   and item.category in PREFERRED_CATEGORIES[index % len(PREFERRED_CATEGORIES)]]
        for item in matches[:9]:
            session.add(ItemView(item_id=item.id, user_id=user.id, viewed_at=item.created_at + timedelta(minutes=35)))
            total += 1
    session.commit()
    return total


def ensure_demo_membership(session: Session, community: Community, users: list[User]) -> None:
    if not session.exec(select(CommunityProfile).where(CommunityProfile.community_id == community.id)).first():
        session.add(CommunityProfile(community_id=community.id, kind="NEIGHBORHOOD", city="演示城市",
                                     district="示例区域", join_code="DEMO2026", is_public=True,
                                     created_by_id=users[0].id))
    existing = {member.user_id for member in session.exec(
        select(CommunityMember).where(CommunityMember.community_id == community.id)
    ).all()}
    for user in users:
        if user.id not in existing:
            session.add(CommunityMember(community_id=community.id, user_id=user.id,
                                        building_id=user.building_id, role="ADMIN" if user.id == users[0].id else "MEMBER"))
    session.flush()


def ensure_demo_reservations(session: Session, community: Community) -> None:
    items = session.exec(select(Item).join(Building).where(Building.community_id == community.id).order_by(Item.id)).all()
    completed = [item for item in items if item.status == "COMPLETED"][:13]
    for item in completed:
        if session.exec(select(Reservation.id).where(Reservation.item_id == item.id)).first():
            continue
        transaction = session.exec(select(Transaction).where(Transaction.item_id == item.id)).first()
        if not transaction:
            continue
        slot_start = max(item.created_at + timedelta(minutes=12), transaction.completed_at - timedelta(minutes=10))
        slot = HandoverSlot(item_id=item.id, starts_at=slot_start, ends_at=slot_start + timedelta(minutes=30))
        session.add(slot)
        session.flush()
        session.add(Reservation(item_id=item.id, buyer_id=transaction.recipient_id, seller_id=item.owner_id,
            slot_id=slot.id, status="COMPLETED", pickup_code=None,
            created_at=item.created_at + timedelta(minutes=2),
            confirmed_at=item.created_at + timedelta(minutes=5),
            completed_at=transaction.completed_at, handover_status="ARRIVED",
            arrived_at=transaction.completed_at - timedelta(minutes=2)))

    reserved = next((item for item in items if item.title == "原木书架" and item.status == "AVAILABLE"), None)
    if reserved and not session.exec(select(Reservation.id).where(Reservation.item_id == reserved.id)).first():
        slot = session.exec(select(HandoverSlot).where(HandoverSlot.item_id == reserved.id).order_by(HandoverSlot.starts_at)).first()
        buyer = session.exec(select(User).where(User.id != reserved.owner_id).order_by(User.id)).first()
        if slot and buyer:
            now = utc_now()
            reserved.status = "RESERVED"
            reserved.last_confirmed_at = now - timedelta(minutes=15)
            session.add(reserved)
            session.add(Reservation(item_id=reserved.id, buyer_id=buyer.id, seller_id=reserved.owner_id,
                slot_id=slot.id, status="CONFIRMED", pickup_code=str(secrets.randbelow(9000) + 1000),
                created_at=now - timedelta(minutes=12), confirmed_at=now - timedelta(minutes=8),
                handover_status="DEPARTED"))
            if not session.exec(select(Interest.id).where(Interest.item_id == reserved.id, Interest.user_id == buyer.id)).first():
                session.add(Interest(item_id=reserved.id, user_id=buyer.id, created_at=now - timedelta(minutes=13)))
    session.commit()


def ensure_future_demo_slots(session: Session, community: Community) -> int:
    """Keep demo listings bookable without changing user-created listings or old bookings."""
    if not demo_mode():
        return 0
    core_signatures = {(title, category, condition, trade_type, price, description)
                       for title, category, condition, trade_type, price, _, description in ITEMS}
    core_items = session.exec(select(Item).join(Building).where(Building.community_id == community.id)).all()
    demo_ids = {item.id for item in core_items if
                (item.title, item.category, item.condition, item.trade_type, item.price, item.description)
                in core_signatures}
    for event in session.exec(select(ItemEvent).where(ItemEvent.event_type == "ITEM_CREATED")).all():
        if event.metadata_json and event.metadata_json.get("seed_key"):
            demo_ids.add(event.item_id)
    if not demo_ids:
        return 0

    now = utc_now()
    added = 0
    for item in session.exec(select(Item).where(Item.id.in_(demo_ids), Item.status == "AVAILABLE")).all():
        future = session.exec(select(HandoverSlot).where(HandoverSlot.item_id == item.id)).all()
        starts = [as_utc(slot.starts_at) for slot in future if as_utc(slot.starts_at) > now]
        if len(starts) >= 3:
            continue
        for hours in (2, 4, 26, 28, 50):
            if len(starts) >= 3:
                break
            start = now + timedelta(hours=hours)
            if any(abs((existing - start).total_seconds()) < 1800 for existing in starts):
                continue
            session.add(HandoverSlot(item_id=item.id, starts_at=start,
                                     ends_at=start + timedelta(minutes=30)))
            starts.append(start)
            added += 1
    session.commit()
    return added


def backfill_demo_events(session: Session) -> int:
    items = session.exec(select(Item).order_by(Item.id)).all()
    total = 0
    for item in items:
        if session.exec(select(ItemEvent.id).where(ItemEvent.item_id == item.id)).first():
            continue
        record_item_event(session, item.id, "ITEM_CREATED", item.owner_id, created_at=item.created_at)
        total += 1
        if item.last_confirmed_at and item.last_confirmed_at > item.created_at + timedelta(seconds=1):
            record_item_event(session, item.id, "ACTIVE_CONFIRMED", item.owner_id, created_at=item.last_confirmed_at)
            total += 1
        for interest in session.exec(select(Interest).where(Interest.item_id == item.id)).all():
            record_item_event(session, item.id, "WANT_CREATED", interest.user_id, created_at=interest.created_at)
            total += 1
        for reservation in session.exec(select(Reservation).where(Reservation.item_id == item.id)).all():
            buyer = session.get(User, reservation.buyer_id)
            metadata = {"reservation_id": reservation.id, "actor_name": buyer.display_name}
            record_item_event(session, item.id, "RESERVATION_CREATED", buyer.id, metadata, reservation.created_at)
            total += 1
            if reservation.confirmed_at:
                record_item_event(session, item.id, "RESERVATION_CONFIRMED", reservation.seller_id,
                                  {"reservation_id": reservation.id}, reservation.confirmed_at)
                total += 1
            if reservation.handover_status == "DEPARTED":
                record_item_event(session, item.id, "BUYER_DEPARTED", buyer.id, metadata,
                                  reservation.confirmed_at or reservation.created_at)
                total += 1
            if reservation.arrived_at:
                record_item_event(session, item.id, "BUYER_ARRIVED", buyer.id, metadata, reservation.arrived_at)
                total += 1
        transaction = session.exec(select(Transaction).where(Transaction.item_id == item.id)).first()
        if transaction:
            record_item_event(session, item.id, "TRANSACTION_COMPLETED", transaction.recipient_id,
                              created_at=transaction.completed_at)
            total += 1
    session.commit()
    return total


def ensure_auth_seed(session: Session, community: Community) -> None:
    if not demo_mode():
        return
    password = os.getenv("NEIGHLOOP_SEED_PASSWORD", "NeighLoopDemo2026!")
    building = session.exec(select(Building).where(Building.community_id == community.id).order_by(Building.id)).first()
    for email, nickname, onboarded in [
        ("test@example.com", "新邻居", False),
        ("returning@example.com", "老邻居", True),
    ]:
        if session.exec(select(User.id).where(User.email == email)).first():
            continue
        user = User(email=email, password_hash=hash_password(password), nickname=nickname,
                    display_name=nickname, building_id=building.id if onboarded else None,
                    community_id=community.id if onboarded else None,
                    avatar_color="#dbead9", onboarding_completed=onboarded,
                    product_tour_completed=onboarded)
        session.add(user)
        session.flush()
        session.add(UserPreference(user_id=user.id, goals=["FIND"] if onboarded else [],
                                   categories=["家居"] if onboarded else [],
                                   trade_preferences=["FREE"] if onboarded else []))
        if onboarded:
            session.add(CommunityMember(community_id=community.id, user_id=user.id,
                                        building_id=building.id, role="MEMBER"))
    session.commit()


def ensure_extended_demo(session: Session, users: list[User]) -> None:
    if not users:
        return
    now = utc_now()
    main_community = session.exec(select(Community).where(Community.name == "绿荫花园小区")).first()
    if main_community:
        main_buildings = session.exec(select(Building).where(Building.community_id == main_community.id)
                                      .order_by(Building.id)).all()
        for building, (x, y) in zip(main_buildings, [(24, 35), (50, 18), (78, 34)]):
            if building.map_x is None:
                building.map_x, building.map_y = x, y
                session.add(building)
    specs = [
        ("云栖花园", "YUNQI2026", 31.2304, 121.4737, ["1号楼", "2号楼", "3号楼"]),
        ("湖畔共享办公室", "OFFICE2026", 31.2380, 121.4820, ["一层", "二层", "三层"]),
    ]
    communities = {}
    for name, code, latitude, longitude, labels in specs:
        community = session.exec(select(Community).where(Community.name == name)).first()
        if not community:
            community = Community(name=name)
            session.add(community)
            session.flush()
            session.add(CommunityProfile(community_id=community.id,
                kind="OFFICE" if "办公室" in name else "NEIGHBORHOOD", city="演示位置",
                district="示例区域", join_code=code, is_public=True,
                latitude=latitude, longitude=longitude, created_by_id=users[0].id))
            points = [(24, 35), (50, 18), (78, 34)]
            session.add_all([Building(community_id=community.id, name=label,
                                      map_key=f"c{community.id}-b{index}",
                                      map_x=points[index - 1][0], map_y=points[index - 1][1])
                             for index, label in enumerate(labels, 1)])
            session.flush()
        communities[name] = community
    yunqi = communities["云栖花园"]
    buildings = session.exec(select(Building).where(Building.community_id == yunqi.id).order_by(Building.id)).all()
    for building, (latitude, longitude) in zip(buildings, [
        (31.2302, 121.4728), (31.2310, 121.4737), (31.2301, 121.4747),
    ]):
        if building.latitude is None:
            building.latitude, building.longitude = latitude, longitude
            session.add(building)
    for index, demo_user in enumerate(users[:6]):
        if not session.exec(select(CommunityMember.id).where(CommunityMember.community_id == yunqi.id,
                                                          CommunityMember.user_id == demo_user.id)).first():
            session.add(CommunityMember(community_id=yunqi.id, user_id=demo_user.id,
                                        building_id=buildings[index % 3].id, role="MEMBER"))
    if not session.exec(select(Need.id).where(Need.community_id == yunqi.id)).first():
        examples = [
            (users[0], buildings[2], "刚搬家，想找电磁炉或者电饭锅，100块以内。", "厨房小家电", ["电磁炉", "电饭锅"], 100),
            (users[1], buildings[2], "想找能做饭的小家电，电磁炉优先，80元以内。", "厨房小家电", ["电磁炉"], 80),
            (users[2], buildings[2], "希望找一个小电饭煲，预算100元。", "厨房小家电", ["电饭煲"], 100),
            (users[3], buildings[2], "找电磁炉，功能正常，最多120元。", "厨房小家电", ["电磁炉"], 120),
            (users[4], buildings[0], "想找一盏台灯，50元以内。", "家居", ["台灯"], 50),
            (users[5], buildings[1], "想要绿萝或者多肉，免费或低价。", "绿植", ["绿萝", "多肉"], 30),
        ]
        session.add_all([Need(user_id=person.id, community_id=yunqi.id, building_id=building.id,
                              raw_text=text, category=category, keywords=keywords, budget_max=budget,
                              created_at=now - timedelta(days=1))
                         for person, building, text, category, keywords, budget in examples])
    root = session.exec(select(Item).where(Item.title == "护照演示：北欧风台灯",
                                           Item.building_id == buildings[0].id)).first()
    if not root:
        root_created = now - timedelta(days=20)
        root_finished = now - timedelta(days=19)
        root = Item(owner_id=users[0].id, building_id=buildings[0].id,
                    title="护照演示：北欧风台灯", description="暖光台灯，外观有正常使用痕迹。",
                    category="家居", condition="九成新", trade_type="FIXED_PRICE", price=35,
                    image_key=0, status="COMPLETED", public_location="1号楼附近",
                    handover_location="1号楼大厅", created_at=root_created, completed_at=root_finished,
                    last_confirmed_at=root_created)
        session.add(root)
        session.flush()
        passport = ItemPassport(root_item_id=root.id, passport_code=f"NL-{root.id:05d}", created_at=root_created)
        session.add(passport)
        session.flush()
        root.passport_id = passport.id
        session.add(root)
        session.add(Transaction(item_id=root.id, recipient_id=users[1].id, completed_at=root_finished))
        record_item_event(session, root.id, "ITEM_CREATED", users[0].id, created_at=root_created)
        record_item_event(session, root.id, "TRANSACTION_COMPLETED", users[0].id, created_at=root_finished)
        second_created = now - timedelta(days=10)
        second_finished = now - timedelta(days=9)
        second = Item(owner_id=users[1].id, building_id=buildings[1].id,
                      title="护照演示：北欧风台灯", description="上一位邻居使用后再次转出，灯光正常。",
                      category="家居", condition="八成新", trade_type="FIXED_PRICE", price=25,
                      image_key=0, status="COMPLETED", passport_id=passport.id,
                      public_location="2号楼附近", handover_location="2号楼大厅",
                      created_at=second_created, completed_at=second_finished,
                      last_confirmed_at=second_created)
        session.add(second)
        session.flush()
        session.add(Transaction(item_id=second.id, recipient_id=users[2].id, completed_at=second_finished))
        record_item_event(session, second.id, "ITEM_RELISTED", users[1].id, created_at=second_created)
        record_item_event(session, second.id, "TRANSACTION_COMPLETED", users[1].id, created_at=second_finished)
    session.commit()


def run_seed() -> None:
    create_db()
    with Session(engine) as session:
        existing_community = session.exec(select(Community).where(Community.name == "绿荫花园小区")).first()
        if existing_community:
            users = session.exec(select(User).where(User.email == None).order_by(User.id)).all()  # noqa: E711
            items = session.exec(select(Item).order_by(Item.id)).all()
            ensure_demo_membership(session, existing_community, users)
            count = seed_views(session, users, items)
            ensure_demo_reservations(session, existing_community)
            events = backfill_demo_events(session)
            ensure_auth_seed(session, existing_community)
            ensure_extended_demo(session, users)
            more = ensure_more_demo_data(session, users, ITEMS, IMAGE_OVERRIDES)
            slots = ensure_future_demo_slots(session, existing_community)
            session.commit()
            print(f"Demo community already exists; core seed skipped. Added {count} view signals, {events} lifecycle events, {more['items']} extra listings, {more['needs']} needs, {more['replies']} discussion replies and {slots} future handover slots.")
            return

        community = Community(name="绿荫花园小区")
        session.add(community)
        session.flush()
        buildings = [
            Building(community_id=community.id, name=f"{number}号楼", map_key=f"building{number}")
            for number in (1, 2, 3)
        ]
        session.add_all(buildings)
        session.flush()
        users = [
            User(display_name=name, building_id=buildings[building_index].id, avatar_color=color)
            for name, building_index, color in USERS
        ]
        session.add_all(users)
        session.flush()
        ensure_demo_membership(session, community, users)

        now = utc_now()
        active_ages = [0.15, 0.8, 1.5, 4, 9, 18, 25, 31, 45, 61, 80, 105, 130, 170, 220, 290,
                       370, 480, 620, 800, 1000, 1250, 1500, 1800, 2100, 2500, 2900, 3300, 3700, 4100, 4500, 4900]
        completed_ages = [1, 5, 14, 32, 80, 160, 280, 440, 660, 900, 1200, 1600, 2050, 2550, 3100, 3650, 4200, 4800]
        for index, (title, category, condition, trade_type, price, image_key, description) in enumerate(ITEMS):
            is_active = index < 32
            age_hours = active_ages[index] if is_active else completed_ages[index - 32]
            owner = users[index % len(users)]
            created_at = now - timedelta(hours=age_hours)
            completion_delay = min(age_hours / 2, [1.2, 4, 9, 21, 36][index % 5])
            completed_at = None if is_active else created_at + timedelta(hours=completion_delay)
            item = Item(
                owner_id=owner.id, building_id=owner.building_id, title=title,
                description=description, category=category, condition=condition,
                trade_type=trade_type, price=price, image_key=IMAGE_OVERRIDES.get(title, image_key),
                original_price=price * 3 if price else None,
                status="AVAILABLE" if is_active else "COMPLETED",
                disposal_goal=["FAST", "BALANCED", "PRICE_FIRST"][index % 3],
                last_confirmed_at=created_at,
                handover_location=f"{session.get(Building, owner.building_id).name}大厅",
                created_at=created_at, completed_at=completed_at,
            )
            session.add(item)
            session.flush()
            if is_active:
                for hours in (2, 4, 26):
                    start = now + timedelta(hours=hours)
                    session.add(HandoverSlot(item_id=item.id, starts_at=start, ends_at=start + timedelta(minutes=30)))

            interest_count = 1 + (index * 7) % 5
            interested_users = [u for u in users if u.id != owner.id][:interest_count]
            for position, neighbor in enumerate(interested_users):
                interest_time = created_at + timedelta(minutes=5 + position * 11)
                if completed_at and interest_time >= completed_at:
                    interest_time = created_at + timedelta(minutes=1 + position)
                session.add(Interest(item_id=item.id, user_id=neighbor.id, created_at=interest_time))

            if completed_at:
                session.add(Transaction(item_id=item.id, recipient_id=interested_users[0].id, completed_at=completed_at))
            if index < 25 or index % 3 == 0:
                commenter = interested_users[0]
                session.add(Comment(
                    item_id=item.id, user_id=commenter.id,
                    body="你好，请问这件物品还在吗？" if is_active else "谢谢邻居，已经顺利取到了！",
                    created_at=created_at + timedelta(minutes=12),
                ))
            if index < 12:
                session.add(Comment(
                    item_id=item.id, user_id=owner.id,
                    body="还在的，可以在小区门口或楼下交接。",
                    created_at=created_at + timedelta(minutes=25),
                ))
        session.commit()
        seed_views(session, users, session.exec(select(Item).order_by(Item.id)).all())
        ensure_demo_reservations(session, community)
        backfill_demo_events(session)
        ensure_auth_seed(session, community)
        ensure_extended_demo(session, users)
        more = ensure_more_demo_data(session, users, ITEMS, IMAGE_OVERRIDES)
        slots = ensure_future_demo_slots(session, community)
        print(f"Seeded {len(USERS)} users, {len(ITEMS) + more['items']} items and related interests, comments, transactions; added {slots} future handover slots.")


if __name__ == "__main__":
    run_seed()
