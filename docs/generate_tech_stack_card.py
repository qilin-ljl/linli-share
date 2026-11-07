"""Render the 16:9 NeighLoop technical-stack card used in the demo video."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont


SCALE = 2
WIDTH, HEIGHT = 1920, 1080
HERE = Path(__file__).resolve().parent
FONT_REGULAR = Path(r"C:\Windows\Fonts\msyh.ttc")
FONT_BOLD = Path(r"C:\Windows\Fonts\msyhbd.ttc")
FONT_LATIN = Path(r"C:\Windows\Fonts\seguisb.ttf")


def s(value: int) -> int:
    return value * SCALE


def font(size: int, *, bold: bool = False, latin: bool = False) -> ImageFont.FreeTypeFont:
    path = FONT_LATIN if latin else FONT_BOLD if bold else FONT_REGULAR
    return ImageFont.truetype(str(path), s(size))


def draw_text(draw: ImageDraw.ImageDraw, xy: tuple[int, int], value: str, size: int,
              color: str, *, bold: bool = False, latin: bool = False) -> None:
    draw.text((s(xy[0]), s(xy[1])), value, font=font(size, bold=bold, latin=latin),
              fill=color, anchor="lt")


def rounded(draw: ImageDraw.ImageDraw, box: tuple[int, int, int, int], radius: int,
            fill: str, outline: str | None = None, width: int = 1) -> None:
    draw.rounded_rectangle(tuple(s(value) for value in box), radius=s(radius),
                           fill=fill, outline=outline, width=s(width))


def main() -> None:
    canvas = Image.new("RGB", (s(WIDTH), s(HEIGHT)), "#f7faf7")
    draw = ImageDraw.Draw(canvas)
    for y in range(s(HEIGHT)):
        tint = int(248 - 6 * y / s(HEIGHT))
        draw.line((0, y, s(WIDTH), y), fill=(tint - 1, tint + 2, tint - 1))

    # Header and title.
    rounded(draw, (80, 68, 157, 145), 21, "#246e49")
    draw_text(draw, (103, 82), "N", 48, "#ffffff", latin=True)
    draw_text(draw, (179, 78), "NeighLoop", 47, "#173e2b", latin=True)
    draw_text(draw, (181, 134), "让闲置在附近重新被需要", 23, "#64806a")
    rounded(draw, (1550, 78, 1840, 132), 27, "#eaf4eb", "#c7dfcb")
    draw_text(draw, (1580, 91), "本地演示 · 技术栈", 25, "#286347", bold=True)
    draw_text(draw, (80, 206), "从浏览到交接，一条完整的全栈链路", 66, "#173d29", bold=True)
    draw_text(draw, (82, 307), "前端负责交互；业务规则、数据写入和大模型请求由后端处理。", 31, "#5c7462")

    cards = [
        ("01", "前端界面", "#2d8054", [
            "React 19 + TypeScript", "Vite · React Router", "Framer Motion", "市集、发布、私聊交互",
        ]),
        ("02", "后端服务", "#3d7797", [
            "Python 3.12 · FastAPI", "Pydantic · REST API", "权限与社区隔离", "预约、交接、成交规则",
        ]),
        ("03", "数据持久化", "#a47548", [
            "SQLModel / SQLAlchemy", "SQLite（本地演示）", "社区、物品、预约", "成交与物品时间线",
        ]),
        ("04", "大模型能力", "#745c9d", [
            "DeepSeek API", "deepseek-flash 模型", "只由服务端调用", "描述润色、定价参考", "物品 FAQ 辅助回复",
        ]),
    ]
    card_width, gap = 420, 27
    for index, (number, title, accent, lines) in enumerate(cards):
        left = 80 + index * (card_width + gap)
        rounded(draw, (left + 3, 420 + 11, left + card_width + 3, 833 + 11),
                28, "#e5eee6")
        rounded(draw, (left, 420, left + card_width, 833), 28, "#ffffff", "#d8e6da")
        rounded(draw, (left + 30, 449, left + 95, 504), 14, accent)
        draw_text(draw, (left + 46, 461), number, 28, "#ffffff", latin=True)
        draw_text(draw, (left + 30, 528), title, 44, "#1d402c", bold=True)
        draw.line((s(left + 30), s(603), s(left + card_width - 30), s(603)),
                  fill="#dce8de", width=s(2))
        for line_index, line in enumerate(lines):
            y = 632 + line_index * (40 if len(lines) > 4 else 46)
            draw.ellipse((s(left + 32), s(y + 15), s(left + 41), s(y + 24)), fill=accent)
            draw_text(draw, (left + 54, y), line, 26 if len(lines) > 4 else 28, "#4a6552")

    # Two actual request paths, separated from the technology inventory.
    rounded(draw, (80, 877, 1840, 1000), 25, "#e9f3ea", "#cfe2d1")
    draw_text(draw, (113, 900), "业务链路", 27, "#286347", bold=True)
    draw_text(draw, (286, 899), "浏览器  →  FastAPI REST API  →  SQLite", 29, "#1c422e", bold=True)
    draw_text(draw, (113, 949), "AI 链路", 27, "#286347", bold=True)
    draw_text(draw, (286, 947), "FastAPI  →  DeepSeek（密钥只放在服务端）", 29, "#1c422e", bold=True)
    draw_text(draw, (81, 1020), "完整数据库 ER 图与技术栈说明另附", 22, "#718875")

    output = HERE / "TECH_STACK_CARD.png"
    canvas.resize((WIDTH, HEIGHT), Image.Resampling.LANCZOS).save(output, optimize=True)
    print(output)


if __name__ == "__main__":
    main()
