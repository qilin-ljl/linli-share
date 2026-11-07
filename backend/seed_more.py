"""Repeatable extra demo content for browsing, demand matching and handover flows."""

from datetime import timedelta

from sqlmodel import Session, select

from database import utc_now
from models import (BatchPublish, Building, Comment, Community, CommunityMember,
                    HandoverSlot, Interest, Item, ItemEvent, ItemPassport, Need,
                    NeedMatch, NeedReply, Reservation, Transaction, User)
from services.item_events import record_item_event
from services.need_matching_service import match_need, need_is_active


# title, existing product-photo source index, building number, age in hours, lifecycle state
MORE_LISTINGS = {
    "绿荫花园小区": [
        ("暖光书桌台灯", 0, 1, 0.6, "AVAILABLE"),
        ("带盆绿萝", 1, 2, 2, "AVAILABLE"),
        ("四层实木书架", 2, 3, 4, "AVAILABLE"),
        ("奶油色单人沙发", 3, 2, 6, "AVAILABLE"),
        ("三升电饭煲", 5, 1, 9, "AVAILABLE"),
        ("日常不粘锅套装", 7, 3, 15, "RESERVED"),
        ("通勤山地自行车", 8, 1, 25, "AVAILABLE"),
        ("儿童推车含遮阳棚", 9, 2, 40, "AVAILABLE"),
        ("两盆多肉植物", 24, 3, 70, "AVAILABLE"),
        ("木质小书桌", 47, 2, 93, "STALE"),
        ("旧款阅读台灯", 32, 1, 140, "COMPLETED"),
        ("玻璃花瓶", 48, 3, 170, "ARCHIVED"),
    ],
    "云栖花园": [
        ("搬家整理电磁炉", 35, 3, 0.7, "AVAILABLE"),
        ("小容量电饭煲", 5, 3, 0.7, "AVAILABLE"),
        ("一套文学读物", 10, 3, 0.7, "AVAILABLE"),
        ("绿萝盆栽带花盆", 1, 3, 0.7, "AVAILABLE"),
        ("卧室暖光台灯", 0, 1, 1.5, "AVAILABLE"),
        ("原木四层书架", 2, 2, 3, "AVAILABLE"),
        ("布艺单人沙发椅", 3, 2, 4.5, "AVAILABLE"),
        ("四人位实木餐桌", 4, 3, 6, "AVAILABLE"),
        ("轻便双肩旅行包", 6, 1, 7, "AVAILABLE"),
        ("厨房不粘锅三件套", 7, 3, 9, "AVAILABLE"),
        ("城市通勤自行车", 8, 2, 12, "AVAILABLE"),
        ("折叠婴儿推车", 9, 2, 16, "RESERVED"),
        ("手冲咖啡壶和滤杯", 11, 1, 18, "AVAILABLE"),
        ("阳台龟背竹", 13, 1, 23, "AVAILABLE"),
        ("幼儿绘本十本", 14, 3, 26, "AVAILABLE"),
        ("小容量空气炸锅", 16, 3, 29, "AVAILABLE"),
        ("居家瑜伽垫", 17, 2, 31, "AVAILABLE"),
        ("白色双层床头柜", 18, 1, 44, "AVAILABLE"),
        ("分类收纳积木箱", 19, 2, 50, "AVAILABLE"),
        ("马克杯四只", 20, 1, 60, "ARCHIVED"),
        ("机械键盘附连接线", 21, 3, 67, "AVAILABLE"),
        ("多肉组合盆栽", 24, 2, 73, "AVAILABLE"),
        ("桌面料理机", 26, 3, 85, "STALE"),
        ("儿童故事书一组", 28, 1, 90, "COMPLETED"),
        ("小型桌面加湿器", 30, 2, 100, "AVAILABLE"),
        ("露营折叠椅", 31, 3, 130, "AVAILABLE"),
        ("居家健身哑铃", 40, 1, 160, "COMPLETED"),
        ("透明玻璃花瓶", 48, 2, 180, "AVAILABLE"),
    ],
    "湖畔共享办公室": [
        ("办公桌面台灯", 0, 1, 1, "AVAILABLE"),
        ("资料收纳书架", 2, 2, 2.5, "AVAILABLE"),
        ("可升降办公椅", 41, 3, 4, "AVAILABLE"),
        ("小型会议桌", 4, 2, 6, "AVAILABLE"),
        ("茶水间电饭煲", 5, 1, 8, "AVAILABLE"),
        ("商务双肩背包", 6, 3, 12, "AVAILABLE"),
        ("员工通勤自行车", 8, 2, 19, "AVAILABLE"),
        ("咖啡壶和滤杯", 11, 1, 23, "AVAILABLE"),
        ("办公室龟背竹", 13, 3, 29, "AVAILABLE"),
        ("机械键盘", 21, 2, 37, "RESERVED"),
        ("桌面小加湿器", 30, 1, 44, "AVAILABLE"),
        ("原木边几", 29, 3, 52, "AVAILABLE"),
        ("靠背折叠椅", 31, 2, 66, "AVAILABLE"),
        ("小型工作书桌", 47, 3, 84, "AVAILABLE"),
        ("打包用收纳篮", 25, 1, 97, "STALE"),
        ("旧款机械键盘", 21, 2, 120, "COMPLETED"),
        ("办公室小绿植", 1, 1, 145, "AVAILABLE"),
        ("陶瓷水杯四只", 20, 3, 170, "ARCHIVED"),
    ],
}


MORE_NEEDS = {
    "绿荫花园小区": [
        (1, 1, "想找能放在书桌上的台灯，50元以内。", "家居", ["台灯"], 50),
        (2, 3, "求一套能做饭的不粘锅，预算80元。", "家居", ["不粘锅"], 80),
        (3, 2, "刚搬家想找一个小书桌，150元以内。", "家居", ["书桌"], 150),
        (4, 1, "想找电饭煲，一到两个人用，100元以内。", "家电", ["电饭煲"], 100),
        (5, 2, "有没有多肉或绿萝，30元以内？", "绿植", ["多肉", "绿萝"], 30),
        (6, 3, "找儿童绘本，最好免费送。", "图书", ["绘本"], 0),
        (7, 1, "想找通勤自行车，可试骑，300元以内。", "运动", ["自行车"], 300),
        (8, 2, "需要一个收纳篮，搬家整理用。", "生活用品", ["收纳篮"], None),
    ],
    "湖畔共享办公室": [
        (1, 2, "找一把办公椅，升降功能正常，150元以内。", "家居", ["办公椅"], 150),
        (2, 1, "想找机械键盘，100元以内。", "家电", ["机械键盘"], 100),
        (3, 3, "办公区需要几盆绿植。", "绿植", ["绿植"], None),
        (4, 2, "找一个放资料的书架，100元以内。", "家居", ["书架"], 100),
        (5, 1, "茶水间想找咖啡壶。", "生活用品", ["咖啡壶"], None),
        (6, 3, "需要桌面台灯，照明正常。", "家居", ["台灯"], None),
        (1, 1, "有没有小加湿器，60元以内。", "家电", ["加湿器"], 60),
        (2, 2, "找轻便双肩包用于通勤。", "运动", ["双肩包"], None),
    ],
}


def ensure_more_demo_data(session: Session, users: list[User], source_items: list[tuple],
                          image_overrides: dict[str, int]) -> dict[str, int]:
    """Insert only missing seed keys; never rewrite a user-created item."""
    if not users:
        return {"items": 0, "needs": 0, "replies": 0}
    now = utc_now()
    existing_keys = {event.metadata_json.get("seed_key") for event in session.exec(
        select(ItemEvent).where(ItemEvent.event_type == "ITEM_CREATED")).all()
        if event.metadata_json and event.metadata_json.get("seed_key")}
    added_items = added_needs = added_replies = 0
    for community_name, specs in MORE_LISTINGS.items():
        community = session.exec(select(Community).where(Community.name == community_name)).first()
        if not community:
            continue
        buildings = session.exec(select(Building).where(Building.community_id == community.id)
                                 .order_by(Building.id)).all()
        if len(buildings) < 3:
            continue
        members = session.exec(select(CommunityMember).where(CommunityMember.community_id == community.id)).all()
        for index, user in enumerate(users[:6]):
            if user.id not in {member.user_id for member in members}:
                member = CommunityMember(community_id=community.id, user_id=user.id,
                                         building_id=buildings[index % 3].id, role="MEMBER")
                session.add(member)
                members.append(member)
        session.flush()
        owners_by_building = {building.id: [session.get(User, member.user_id) for member in members
                                            if member.building_id == building.id and member.user_id in {u.id for u in users}]
                              for building in buildings}
        need_users = users if community_name == "绿荫花园小区" else users[:6]
        for need_index, building_number, text, category, keywords, budget in MORE_NEEDS.get(community_name, []):
            if session.exec(select(Need.id).where(Need.community_id == community.id,
                                                  Need.raw_text == text)).first():
                continue
            session.add(Need(user_id=need_users[need_index % len(need_users)].id, community_id=community.id,
                             building_id=buildings[building_number - 1].id, raw_text=text,
                             category=category, keywords=keywords, budget_max=budget,
                             created_at=now - timedelta(hours=3 + need_index * 2)))
            added_needs += 1
        session.flush()
        needs = session.exec(select(Need).where(Need.community_id == community.id, Need.status == "ACTIVE")).all()
        existing_items = session.exec(select(Item).join(Building).where(Building.community_id == community.id,
                                     Item.status == "AVAILABLE")).all()
        existing_matches = {(match.need_id, match.item_id) for match in session.exec(select(NeedMatch)).all()}
        for old_item in existing_items:
            for need in needs:
                if (need.id, old_item.id) in existing_matches or not need_is_active(need, now):
                    continue
                reasons = match_need(old_item, need)
                if reasons:
                    session.add(NeedMatch(need_id=need.id, item_id=old_item.id, reasons=reasons))
                    existing_matches.add((need.id, old_item.id))
        batch = None
        if community_name == "云栖花园" and any(
            f"more-2026-{community.id}-{index}" not in existing_keys for index in range(4)
        ):
            batch_time = now - timedelta(minutes=42)
            batch = BatchPublish(user_id=users[2].id, community_id=community.id,
                                 created_at=batch_time, confirmed_at=batch_time)
            session.add(batch)
            session.flush()
        for index, (title, source_index, building_number, age_hours, lifecycle) in enumerate(specs):
            seed_key = f"more-2026-{community.id}-{index}"
            if seed_key in existing_keys:
                continue
            source_title, category, condition, trade_type, price, image_key, description = source_items[source_index]
            building = buildings[building_number - 1]
            possible_owners = owners_by_building[building.id]
            owner = users[2] if community_name == "云栖花园" and index < 4 else possible_owners[index % len(possible_owners)]
            created_at = now - timedelta(hours=age_hours)
            completed_at = created_at + timedelta(hours=min(8, max(1, age_hours / 4))) if lifecycle == "COMPLETED" else None
            item = Item(owner_id=owner.id, building_id=building.id, title=title, description=description,
                        category=category, condition=condition, trade_type=trade_type, price=price,
                        image_key=image_overrides.get(source_title, image_key),
                        status="AVAILABLE" if lifecycle == "STALE" else lifecycle,
                        disposal_goal="FAST" if index % 5 == 0 else "BALANCED",
                        public_location=f"{building.name}附近", handover_location=f"{building.name}大厅",
                        last_confirmed_at=created_at if lifecycle == "STALE" else now - timedelta(hours=min(age_hours, 5)),
                        created_at=created_at, completed_at=completed_at,
                        batch_id=batch.id if batch and index < 4 else None)
            session.add(item)
            session.flush()
            record_item_event(session, item.id, "ITEM_CREATED", owner.id, {"seed_key": seed_key}, created_at)
            other_users = [candidate for candidate in users[:6] if candidate.id != owner.id]
            for interest_index, candidate in enumerate(other_users[:1 + index % 4]):
                interest_time = created_at + timedelta(minutes=3 + interest_index * 6)
                if completed_at and interest_time >= completed_at:
                    interest_time = created_at + timedelta(minutes=1)
                session.add(Interest(item_id=item.id, user_id=candidate.id, created_at=interest_time))
                record_item_event(session, item.id, "WANT_CREATED", candidate.id, created_at=interest_time)
            if lifecycle in {"AVAILABLE", "STALE", "RESERVED"}:
                start = now + timedelta(hours=2 + index % 3)
                slot = HandoverSlot(item_id=item.id, starts_at=start,
                                    ends_at=start + timedelta(minutes=30))
                session.add(slot)
                session.flush()
                if lifecycle == "RESERVED":
                    buyer = other_users[0]
                    session.add(Reservation(item_id=item.id, buyer_id=buyer.id, seller_id=owner.id,
                                            slot_id=slot.id, status="CONFIRMED", pickup_code="4826",
                                            created_at=now - timedelta(hours=1),
                                            confirmed_at=now - timedelta(minutes=35)))
                    record_item_event(session, item.id, "RESERVATION_CREATED", buyer.id,
                                      created_at=now - timedelta(hours=1))
                    record_item_event(session, item.id, "RESERVATION_CONFIRMED", owner.id,
                                      created_at=now - timedelta(minutes=35))
            if lifecycle == "COMPLETED":
                buyer = other_users[0]
                slot = HandoverSlot(item_id=item.id, starts_at=completed_at - timedelta(minutes=25),
                                    ends_at=completed_at + timedelta(minutes=5))
                session.add(slot)
                session.flush()
                session.add(Reservation(item_id=item.id, buyer_id=buyer.id, seller_id=owner.id,
                                        slot_id=slot.id, status="COMPLETED", pickup_code=None,
                                        created_at=created_at + timedelta(minutes=20),
                                        confirmed_at=created_at + timedelta(minutes=35),
                                        completed_at=completed_at))
                session.add(Transaction(item_id=item.id, recipient_id=buyer.id, completed_at=completed_at))
                passport = ItemPassport(root_item_id=item.id, passport_code=f"NL-{item.id:05d}",
                                        created_at=created_at)
                session.add(passport)
                session.flush()
                item.passport_id = passport.id
                session.add(item)
                record_item_event(session, item.id, "TRANSACTION_COMPLETED", owner.id,
                                  created_at=completed_at)
            if lifecycle == "ARCHIVED":
                record_item_event(session, item.id, "ITEM_ARCHIVED", owner.id,
                                  created_at=created_at + timedelta(hours=2))
            if index % 3 == 0 and lifecycle not in {"COMPLETED", "ARCHIVED"}:
                session.add(Comment(item_id=item.id, user_id=other_users[0].id,
                                    body="请问还在吗？可以在楼下自提吗？",
                                    created_at=created_at + timedelta(minutes=9)))
            if item.status == "AVAILABLE" and lifecycle != "STALE":
                for need in needs:
                    if need_is_active(need, now):
                        reasons = match_need(item, need)
                        if reasons:
                            session.add(NeedMatch(need_id=need.id, item_id=item.id, reasons=reasons))
            added_items += 1
            existing_keys.add(seed_key)
        session.flush()
    demo_discussions = [
        ("想找能放在书桌上的台灯，50元以内。", "暖光书桌台灯", users[0].id,
         "我这盏暖光书桌台灯还在架，成色和可领取时间写在物品详情里，可以先看看。"),
        ("想找电饭煲，一到两个人用，100元以内。", "迷你电饭煲", users[5].id,
         "我有一台适合一两个人用的迷你电饭煲，正在社区里分享，欢迎点开看看。"),
    ]
    for need_text, item_title, author_id, body in demo_discussions:
        need = session.exec(select(Need).where(Need.raw_text == need_text)).first()
        item = session.exec(select(Item).where(Item.title == item_title, Item.owner_id == author_id,
                                               Item.status == "AVAILABLE")).first()
        if not need or not item or need.community_id != session.get(Building, item.building_id).community_id:
            continue
        if session.exec(select(NeedReply.id).where(NeedReply.need_id == need.id,
                                                    NeedReply.user_id == author_id,
                                                    NeedReply.item_id == item.id)).first():
            continue
        session.add(NeedReply(need_id=need.id, user_id=author_id, body=body, item_id=item.id,
                              created_at=now - timedelta(minutes=18 - added_replies * 5)))
        added_replies += 1
    session.commit()
    return {"items": added_items, "needs": added_needs, "replies": added_replies}
