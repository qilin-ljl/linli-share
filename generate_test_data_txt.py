"""Write the evaluation guide from the repository's seeded demo data."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

from seed import ITEMS, USERS  # noqa: E402
from seed_more import MORE_LISTINGS, MORE_NEEDS  # noqa: E402


def price_label(trade_type: str, price: int | None) -> str:
    return {"FREE": "免费送", "NEGOTIABLE": "随便给"}.get(trade_type, f"标价 ¥{price}")


def extra_status(lifecycle: str) -> str:
    return {"AVAILABLE": "在架", "RESERVED": "已预约", "COMPLETED": "已完成",
            "ARCHIVED": "已归档", "STALE": "待确认"}[lifecycle]


def main() -> None:
    lines = [
        "NeighLoop 测试数据、账号及密码",
        "=" * 38,
        "适用范围：提交文件夹首次运行并初始化演示数据库后的预置数据。",
        "物品 ID、发布时间、预约时段和统计数字由运行时间决定，操作后状态也会改变。",
        "本文件不包含开发机后来手动创建的账号、社区或物品。",
        "",
        "一、邮箱测试账号（可在登录页输入）",
        "- test@example.com / NeighLoopDemo2026! —— 新用户，首次配置尚未完成，适合演示注册后的引导。",
        "- returning@example.com / NeighLoopDemo2026! —— 已完成首次配置，适合直接测试登录后的浏览。",
        "这两个密码来自 seed.py 的默认 NEIGHLOOP_SEED_PASSWORD；提交版 .env 未覆盖此变量。",
        "没有预置的管理员网页登录密码。其他自己注册的账号密码不在提交包内。",
        "",
        "二、顶部演示身份（无需输入密码）",
        "本地 Demo 模式下，在页面顶部“切换演示用户”选择。正式账号登录时先退出再切换。",
    ]
    for index, (name, building_index, _) in enumerate(USERS, 1):
        lines.append(f"{index:02d}. {name} —— 绿荫花园小区 {building_index + 1}号楼；免密码演示身份")
    lines.extend([
        "",
        "三、预置社区与加入码（加入码不是登录密码）",
        "- 绿荫花园小区：DEMO2026；1号楼、2号楼、3号楼。",
        "- 云栖花园：YUNQI2026；1号楼、2号楼、3号楼。",
        "- 湖畔共享办公室：OFFICE2026；一层、二层、三层。",
        "",
        "四、快速测试路线",
        "1. 用林小雨发布一件新物品，填写标题、描述和未来可领取时段；可试描述润色与三档定价。",
        "2. 切王思思，在市集搜索该物品，点“想要”、公开留言并预约未来时段。",
        "3. 切回林小雨，在“消息→我的预约”接受；再切王思思查看领取码并点“我出发了”“我到了”。",
        "4. 林小雨输入买家视角显示的四位领取码，确认交接；在“我的→已结束”和社区数据面板检查记录。",
        "5. 需求讨论可附的物品仅限当前演示身份自己发布、当前仍在架的物品；没有物品时先发布。",
        "演示物品的未来时段由本地启动入口自动补齐。旧物品若显示“待确认”，须由发布者确认还在。",
        "",
        "五、全量预置物品清单",
        f"核心市集：{len(ITEMS)} 件。前 32 件数据库状态初始在架，后 18 件初始已完成；“原木书架”会被设置为已预约。超过 72 小时未确认的在架物品会显示“待确认”。",
    ])
    for index, (title, category, _, trade_type, price, _, _) in enumerate(ITEMS, 1):
        status = "已预约" if title == "原木书架" else "在架" if index <= 32 else "已完成"
        lines.append(f"{index:02d}. {title}｜{category}｜{price_label(trade_type, price)}｜{status}")
    lines.extend([
        "",
        "护照演示：北欧风台灯另有两次已完成流转记录，分别标价 ¥35 和 ¥25。",
        "",
    ])
    extra_total = sum(len(specs) for specs in MORE_LISTINGS.values())
    lines.append(f"补充商品：{extra_total} 件，按社区列出。")
    for community_name, specs in MORE_LISTINGS.items():
        lines.append(f"[{community_name}] {len(specs)} 件")
        for index, (title, source_index, building_number, _, lifecycle) in enumerate(specs, 1):
            _, category, _, trade_type, price, _, _ = ITEMS[source_index]
            location = f"第{building_number}层" if "办公室" in community_name else f"{building_number}号楼"
            lines.append(f"  {index:02d}. {title}｜{location}｜{category}｜"
                         f"{price_label(trade_type, price)}｜{extra_status(lifecycle)}")
        lines.append("")

    lines.extend([
        "六、全量预置需求文本",
        "[绿荫花园小区]",
    ])
    for index, (_, building, text, _, _, budget) in enumerate(MORE_NEEDS["绿荫花园小区"], 1):
        lines.append(f"  {index:02d}. {building}号楼：{text}（最高预算：{budget if budget is not None else '未填写'}）")
    lines.extend([
        "[云栖花园]",
        "  01. 3号楼：刚搬家，想找电磁炉或者电饭锅，100块以内。",
        "  02. 3号楼：想找能做饭的小家电，电磁炉优先，80元以内。",
        "  03. 3号楼：希望找一个小电饭煲，预算100元。",
        "  04. 3号楼：找电磁炉，功能正常，最多120元。",
        "  05. 1号楼：想找一盏台灯，50元以内。",
        "  06. 2号楼：想要绿萝或者多肉，免费或低价。",
        "[湖畔共享办公室]",
    ])
    for index, (_, floor, text, _, _, budget) in enumerate(MORE_NEEDS["湖畔共享办公室"], 1):
        lines.append(f"  {index:02d}. 第{floor}层：{text}（最高预算：{budget if budget is not None else '未填写'}）")
    lines.extend([
        "",
        "七、其他凭据与动态数据",
        "- 交接领取码不是固定密码；卖家接受预约后由系统生成，仅在买家视角显示。",
        "- DeepSeek API Key 已放在 backend/.env，仅供后端本地演示；本 TXT 不重复写明密钥。",
        "- 意向、公开留言、私聊、预约和成交记录由种子脚本或实际操作写入；ID 与时间随首次运行变化。",
        "- “text”等开发机自行注册的账号不在干净提交包中，密码未知，不属于预置测试账号。",
        "",
    ])
    output = ROOT / "submission" / "TEST_DATA_AND_PASSWORDS.txt"
    output.write_text("\n".join(lines), encoding="utf-8-sig")
    print(f"Created {output.name}: {len(lines)} lines")


if __name__ == "__main__":
    main()
