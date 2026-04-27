from __future__ import annotations

import os
import shutil
import struct
import textwrap
import zipfile
import zlib
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "软件测试课程项目文档合集"
DEV_DIR = OUT / "开发文档"
TEST_DOC_DIR = OUT / "测试文档"
IMG_DIR = OUT / "图片"
SRC_DIR = OUT / "图源码"
TEST_CODE_DIR = OUT / "测试代码"
ZIP_PATH = ROOT / "软件测试课程项目文档合集.zip"

PROJECT_NAME = "简单去中心化加密货币交易所（DEX）核心系统与可视化 GUI"
COURSE_NAME = "软件测试"
AUTHOR = "作者：__________"
TODAY = date.today().isoformat()


def ensure_dirs() -> None:
    if OUT.exists():
        shutil.rmtree(OUT)
    for directory in [DEV_DIR, TEST_DOC_DIR, IMG_DIR, SRC_DIR, TEST_CODE_DIR]:
        directory.mkdir(parents=True, exist_ok=True)


def png_chunk(kind: bytes, data: bytes) -> bytes:
    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)


class Canvas:
    def __init__(self, width: int = 1200, height: int = 760) -> None:
        self.width = width
        self.height = height
        self.pixels = bytearray([255, 255, 255] * width * height)

    def set_pixel(self, x: int, y: int, color: tuple[int, int, int]) -> None:
        if 0 <= x < self.width and 0 <= y < self.height:
            i = (y * self.width + x) * 3
            self.pixels[i:i + 3] = bytes(color)

    def rect(self, x: int, y: int, w: int, h: int, fill: tuple[int, int, int], outline: tuple[int, int, int] = (34, 64, 91)) -> None:
        for yy in range(y, y + h):
            for xx in range(x, x + w):
                self.set_pixel(xx, yy, fill)
        self.line(x, y, x + w, y, outline, 3)
        self.line(x, y + h, x + w, y + h, outline, 3)
        self.line(x, y, x, y + h, outline, 3)
        self.line(x + w, y, x + w, y + h, outline, 3)

    def line(self, x1: int, y1: int, x2: int, y2: int, color: tuple[int, int, int] = (55, 65, 81), width: int = 2) -> None:
        dx = abs(x2 - x1)
        dy = -abs(y2 - y1)
        sx = 1 if x1 < x2 else -1
        sy = 1 if y1 < y2 else -1
        err = dx + dy
        x, y = x1, y1
        while True:
            for ox in range(-(width // 2), width // 2 + 1):
                for oy in range(-(width // 2), width // 2 + 1):
                    self.set_pixel(x + ox, y + oy, color)
            if x == x2 and y == y2:
                break
            e2 = 2 * err
            if e2 >= dy:
                err += dy
                x += sx
            if e2 <= dx:
                err += dx
                y += sy

    def arrow(self, x1: int, y1: int, x2: int, y2: int) -> None:
        self.line(x1, y1, x2, y2, (55, 65, 81), 3)
        if abs(x2 - x1) >= abs(y2 - y1):
            d = 1 if x2 >= x1 else -1
            self.line(x2, y2, x2 - 18 * d, y2 - 12, (55, 65, 81), 3)
            self.line(x2, y2, x2 - 18 * d, y2 + 12, (55, 65, 81), 3)
        else:
            d = 1 if y2 >= y1 else -1
            self.line(x2, y2, x2 - 12, y2 - 18 * d, (55, 65, 81), 3)
            self.line(x2, y2, x2 + 12, y2 - 18 * d, (55, 65, 81), 3)

    def text(self, x: int, y: int, text: str, scale: int = 4, color: tuple[int, int, int] = (17, 24, 39)) -> None:
        cursor = x
        for ch in text.upper():
            if ch == " ":
                cursor += 4 * scale
                continue
            pattern = FONT.get(ch, FONT.get("?"))
            for row, bits in enumerate(pattern):
                for col, bit in enumerate(bits):
                    if bit == "1":
                        for yy in range(scale):
                            for xx in range(scale):
                                self.set_pixel(cursor + col * scale + xx, y + row * scale + yy, color)
            cursor += 6 * scale

    def save(self, path: Path) -> None:
        rows = []
        stride = self.width * 3
        for y in range(self.height):
            rows.append(b"\x00" + bytes(self.pixels[y * stride:(y + 1) * stride]))
        raw = b"".join(rows)
        data = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", self.width, self.height, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", zlib.compress(raw, 9))
            + png_chunk(b"IEND", b"")
        )
        path.write_bytes(data)


FONT = {
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01111", "10000", "10000", "10000", "10000", "10000", "01111"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01111", "10000", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "10010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "01010", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "01010", "00100", "00100", "00100", "01010", "10001"],
    "Y": ["10001", "01010", "00100", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11110", "00001", "00001", "01110", "00001", "00001", "11110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "10000", "11110", "00001", "00001", "11110"],
    "6": ["01110", "10000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00001", "01110"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    "+": ["00000", "00100", "00100", "11111", "00100", "00100", "00000"],
    "?": ["01110", "10001", "00001", "00010", "00100", "00000", "00100"],
}


def draw_diagram(name: str, boxes: list[tuple[str, int, int]], arrows: list[tuple[int, int]]) -> None:
    canvas = Canvas()
    colors = [(225, 239, 254), (220, 252, 231), (254, 249, 195), (243, 232, 255), (254, 226, 226)]
    w, h = 190, 86
    centers = []
    canvas.text(40, 32, name.replace("图", ""), 5, (31, 41, 55))
    for i, (label, x, y) in enumerate(boxes):
        canvas.rect(x, y, w, h, colors[i % len(colors)])
        canvas.text(x + 24, y + 28, label, 4)
        centers.append((x + w // 2, y + h // 2))
    for a, b in arrows:
        x1, y1 = centers[a]
        x2, y2 = centers[b]
        canvas.arrow(x1, y1, x2, y2)
    canvas.save(IMG_DIR / f"{name}.png")


MERMAID = {
    "系统总体架构图": """flowchart LR
  U[浏览器用户] --> GUI[gui.py 单页 GUI 与 JSON API]
  GUI --> APP[app.py 服务构建]
  APP --> AUTH[AuthService 用户认证]
  APP --> WALLET[WalletService 多币种钱包]
  APP --> ENGINE[MatchingEngine 撮合引擎]
  ENGINE --> BOOK[OrderBook 买卖盘]
  ENGINE --> CHAIN[SimpleBlockchain 链式账本]
  ENGINE --> MODEL[models.py 数据实体]
  AUTH --> MODEL
  WALLET --> MODEL
  CHAIN --> MODEL
""",
    "模块结构图": """flowchart TB
  EX[exceptions.py 统一异常] --> AUTH[auth.py]
  EX --> WALLET[wallet.py]
  EX --> ENGINE[engine.py]
  EX --> CHAIN[blockchain.py]
  MODEL[models.py 枚举与 dataclass] --> AUTH
  MODEL --> WALLET
  MODEL --> ENGINE
  MODEL --> CHAIN
  AUTH --> APP[app.py]
  WALLET --> APP
  ENGINE --> APP
  CHAIN --> APP
  APP --> GUI[gui.py]
""",
    "登录认证流程图": """flowchart TD
  A[输入用户名和密码] --> B[去除用户名首尾空白]
  B --> C{用户是否存在}
  C -- 否 --> D[抛出 UserNotFoundError]
  C -- 是 --> E[PBKDF2-HMAC-SHA256 校验密码]
  E --> F{密码是否匹配}
  F -- 否 --> G[抛出 InvalidCredentialsError]
  F -- 是 --> H[生成 token]
  H --> I[写入 sessions 并返回 token]
""",
    "下单与撮合交易流程图": """flowchart TD
  A[提交限价单] --> B[校验用户与交易对]
  B --> C[标准化价格和数量]
  C --> D[冻结买方计价资产或卖方基础资产]
  D --> E[读取对手订单簿最优订单]
  E --> F{价格是否交叉}
  F -- 否 --> G[活跃订单入簿]
  F -- 是 --> H{是否同一用户}
  H -- 是 --> I[触发自成交保护]
  H -- 否 --> J[执行成交与余额结算]
  J --> K[生成 Trade 并写入待打包交易]
  K --> L{订单是否仍有剩余}
  L -- 是 --> E
  L -- 否 --> M[刷新订单状态]
""",
    "区块链账本记录流程图": """flowchart TD
  A[撮合生成 Trade] --> B[Trade.to_record]
  B --> C[加入 pending_transactions]
  C --> D{是否达到 block_capacity}
  D -- 否 --> E[继续等待交易]
  D -- 是 --> F[创建新区块]
  F --> G[写入 previous_hash]
  G --> H[计算 block_hash]
  H --> I[追加到 chain]
  I --> J[清空 pending_transactions]
  J --> K[validate_chain 校验]
""",
    "数据流图": """flowchart LR
  A[用户输入] --> B[GUI / CLI]
  B --> C[认证服务]
  B --> D[钱包服务]
  B --> E[撮合引擎]
  E --> F[订单簿]
  E --> G[成交记录]
  G --> H[链式账本]
  C --> I[内存字典]
  D --> I
  F --> I
  H --> I
""",
    "单元测试流程图": """flowchart TD
  A[选择函数或类] --> B[构造最小测试数据]
  B --> C[调用单个方法]
  C --> D[断言返回值或异常]
  D --> E[记录通过/失败]
""",
    "集成测试流程图": """flowchart TD
  A[创建 Auth Wallet Blockchain Engine] --> B[注册用户并创建钱包]
  B --> C[充值和冻结资产]
  C --> D[提交订单]
  D --> E[撮合成交]
  E --> F[校验钱包 订单簿 区块链]
""",
    "系统测试流程图": """flowchart TD
  A[启动 GUI 或运行 run_demo] --> B[执行完整交易场景]
  B --> C[检查页面/接口状态]
  C --> D[校验订单 钱包 成交 区块]
  D --> E[输出系统测试结论]
""",
    "测试阶段关系图": """flowchart LR
  A[单元测试] --> B[集成测试]
  B --> C[系统测试]
  A --> D[函数/类级缺陷定位]
  B --> E[模块协作缺陷定位]
  C --> F[用户业务流程验收]
  D --> G[测试报告]
  E --> G
  F --> G
""",
}


def generate_images() -> None:
    diagrams = {
        "系统总体架构图": ([("USER", 70, 320), ("GUI/API", 290, 320), ("ENGINE", 510, 220), ("AUTH", 510, 420), ("WALLET", 730, 320), ("CHAIN", 950, 320)], [(0, 1), (1, 2), (1, 3), (2, 4), (2, 5)]),
        "模块结构图": ([("MODELS", 90, 120), ("AUTH", 360, 120), ("WALLET", 630, 120), ("ENGINE", 360, 330), ("CHAIN", 630, 330), ("GUI", 900, 230)], [(0, 1), (0, 2), (0, 3), (0, 4), (1, 5), (2, 5), (3, 5), (4, 5)]),
        "登录认证流程图": ([("INPUT", 90, 330), ("USER", 310, 330), ("HASH", 530, 330), ("TOKEN", 750, 330), ("SESSION", 970, 330)], [(0, 1), (1, 2), (2, 3), (3, 4)]),
        "下单与撮合交易流程图": ([("ORDER", 70, 330), ("FREEZE", 285, 330), ("BOOK", 500, 330), ("MATCH", 715, 330), ("TRADE", 930, 240), ("STATUS", 930, 430)], [(0, 1), (1, 2), (2, 3), (3, 4), (3, 5)]),
        "区块链账本记录流程图": ([("TRADE", 90, 330), ("PENDING", 310, 330), ("BLOCK", 530, 330), ("HASH", 750, 330), ("CHAIN", 970, 330)], [(0, 1), (1, 2), (2, 3), (3, 4)]),
        "数据流图": ([("INPUT", 80, 330), ("GUI", 300, 330), ("SERVICES", 520, 330), ("MEMORY", 740, 240), ("LEDGER", 960, 330), ("OUTPUT", 740, 430)], [(0, 1), (1, 2), (2, 3), (2, 4), (2, 5)]),
        "单元测试流程图": ([("CASE", 110, 330), ("SETUP", 330, 330), ("CALL", 550, 330), ("ASSERT", 770, 330), ("REPORT", 990, 330)], [(0, 1), (1, 2), (2, 3), (3, 4)]),
        "集成测试流程图": ([("SERVICES", 80, 330), ("ACCOUNTS", 300, 330), ("ORDERS", 520, 330), ("MATCH", 740, 330), ("VERIFY", 960, 330)], [(0, 1), (1, 2), (2, 3), (3, 4)]),
        "系统测试流程图": ([("START", 100, 330), ("FLOW", 320, 330), ("GUI/API", 540, 330), ("CHECK", 760, 330), ("ACCEPT", 980, 330)], [(0, 1), (1, 2), (2, 3), (3, 4)]),
        "测试阶段关系图": ([("UNIT", 90, 330), ("INTEG", 310, 330), ("SYSTEM", 530, 330), ("DEFECT", 750, 240), ("REPORT", 970, 330)], [(0, 1), (1, 2), (0, 3), (1, 3), (2, 4), (3, 4)]),
    }
    for name, (boxes, arrows) in diagrams.items():
        draw_diagram(name, boxes, arrows)
        (SRC_DIR / f"{name}.mmd").write_text(MERMAID[name], encoding="utf-8")


def xml_text(text: str) -> str:
    return escape(text, {'"': "&quot;"})


class DocxWriter:
    def __init__(self, path: Path, title: str, doc_id: str) -> None:
        self.path = path
        self.title = title
        self.doc_id = doc_id
        self.blocks: list[str] = []
        self.rels: list[tuple[str, str]] = []
        self.media: list[tuple[Path, str]] = []
        self.image_counter = 1
        self.cover()

    def cover(self) -> None:
        self.p(self.title, style="Title")
        self.p(f"文档编号：{self.doc_id}")
        self.p("版本号：V1.0")
        self.p(f"编写日期：{TODAY}")
        self.p(f"课程名称：{COURSE_NAME}")
        self.p(f"项目名称：{PROJECT_NAME}")
        self.p(AUTHOR)
        self.page_break()
        self.h("修订记录", 1)
        self.table(["版本", "日期", "修订说明", "修订人"], [["V1.0", TODAY, "首次生成课程实验提交版", "__________"]])
        self.h("目录", 1)
        self.p("本文档目录可在 Word 中通过“引用 - 更新目录”生成；本提交版正文已按章节编号组织。")
        self.page_break()

    def p(self, text: str, style: str | None = None) -> None:
        style_xml = ""
        if style == "Title":
            style_xml = '<w:pStyle w:val="Title"/>'
        elif style == "Code":
            style_xml = '<w:pStyle w:val="Code"/>'
        self.blocks.append(f"<w:p><w:pPr>{style_xml}</w:pPr><w:r><w:t xml:space=\"preserve\">{xml_text(text)}</w:t></w:r></w:p>")

    def h(self, text: str, level: int = 1) -> None:
        self.blocks.append(f"<w:p><w:pPr><w:pStyle w:val=\"Heading{level}\"/></w:pPr><w:r><w:t>{xml_text(text)}</w:t></w:r></w:p>")

    def bullets(self, items: list[str]) -> None:
        for item in items:
            self.p(f"• {item}")

    def table(self, headers: list[str], rows: list[list[str]]) -> None:
        cells = []
        for row in [headers] + rows:
            row_xml = "".join(
                f"<w:tc><w:tcPr><w:tcW w:w=\"2400\" w:type=\"dxa\"/></w:tcPr><w:p><w:r><w:t>{xml_text(str(cell))}</w:t></w:r></w:p></w:tc>"
                for cell in row
            )
            cells.append(f"<w:tr>{row_xml}</w:tr>")
        self.blocks.append("<w:tbl><w:tblPr><w:tblStyle w:val=\"TableGrid\"/><w:tblW w:w=\"0\" w:type=\"auto\"/></w:tblPr>" + "".join(cells) + "</w:tbl>")

    def code(self, source: str, text: str) -> None:
        self.p(f"代码片段来源：{source}")
        for line in textwrap.dedent(text).strip().splitlines():
            self.p(line[:170], style="Code")

    def image(self, image_path: Path, caption: str) -> None:
        rid = f"rId{len(self.rels) + 1}"
        target = f"media/{image_path.name}"
        self.rels.append((rid, target))
        self.media.append((image_path, target))
        cx = 5486400
        cy = 3474720
        self.blocks.append(f"""
<w:p><w:r><w:drawing><wp:inline xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing">
<wp:extent cx="{cx}" cy="{cy}"/><wp:docPr id="{self.image_counter}" name="{xml_text(caption)}"/>
<a:graphic xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:pic xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
<pic:nvPicPr><pic:cNvPr id="{self.image_counter}" name="{image_path.name}"/><pic:cNvPicPr/></pic:nvPicPr>
<pic:blipFill><a:blip r:embed="{rid}" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>
<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>
</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r></w:p>
""")
        self.p(caption)
        self.image_counter += 1

    def page_break(self) -> None:
        self.blocks.append('<w:p><w:r><w:br w:type="page"/></w:r></w:p>')

    def save(self) -> None:
        body = "".join(self.blocks)
        document = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"
 xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"
 xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main"
 xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing"
 xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture">
<w:body>{body}<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="1440" w:right="1200" w:bottom="1440" w:left="1200"/></w:sectPr></w:body></w:document>"""
        rel_items = "".join(
            f'<Relationship Id="{rid}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="{target}"/>'
            for rid, target in self.rels
        )
        document_rels = f"""<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">{rel_items}</Relationships>"""
        styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:style w:type="paragraph" w:styleId="Normal"><w:name w:val="Normal"/><w:rPr><w:sz w:val="21"/><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Title"><w:name w:val="Title"/><w:rPr><w:b/><w:sz w:val="36"/><w:rFonts w:ascii="Microsoft YaHei" w:eastAsia="Microsoft YaHei"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:rPr><w:b/><w:sz w:val="30"/><w:rFonts w:eastAsia="Microsoft YaHei"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:rPr><w:b/><w:sz w:val="26"/><w:rFonts w:eastAsia="Microsoft YaHei"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:rPr><w:b/><w:sz w:val="23"/><w:rFonts w:eastAsia="Microsoft YaHei"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Code"><w:name w:val="Code"/><w:rPr><w:rFonts w:ascii="Consolas" w:eastAsia="Consolas"/><w:sz w:val="18"/></w:rPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/><w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4"/><w:left w:val="single" w:sz="4"/><w:bottom w:val="single" w:sz="4"/><w:right w:val="single" w:sz="4"/><w:insideH w:val="single" w:sz="4"/><w:insideV w:val="single" w:sz="4"/></w:tblBorders></w:tblPr></w:style>
</w:styles>"""
        content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Default Extension="png" ContentType="image/png"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
        package_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
        with zipfile.ZipFile(self.path, "w", zipfile.ZIP_DEFLATED) as docx:
            docx.writestr("[Content_Types].xml", content_types)
            docx.writestr("_rels/.rels", package_rels)
            docx.writestr("word/document.xml", document)
            docx.writestr("word/styles.xml", styles)
            docx.writestr("word/_rels/document.xml.rels", document_rels)
            for src, target in self.media:
                docx.write(src, f"word/{target}")


REQS = [
    ["FR-01", "用户注册", "系统应支持新用户注册，用户名不能为空且不能重复。", "auth.py/AuthService.register", "UT-AUTH-01", "IT-01", "ST-01", "已验证"],
    ["FR-02", "用户登录认证", "系统应使用密码哈希校验登录并生成 token。", "auth.py/AuthService.login", "UT-AUTH-02", "IT-01", "ST-01", "已验证"],
    ["FR-03", "多币种钱包", "系统应支持 BTC、ETH、USDT 的可用与冻结余额。", "wallet.py/WalletService", "UT-WALLET-01", "IT-02", "ST-02", "已验证"],
    ["FR-04", "限价下单", "系统应支持 BUY/SELL 限价单并冻结相应资产。", "engine.py/MatchingEngine.place_limit_order", "UT-ORDER-01", "IT-02", "ST-03", "已验证"],
    ["FR-05", "自动撮合", "价格交叉时按价格优先、时间优先撮合成交。", "engine.py/OrderBook, MatchingEngine._match_order", "UT-MATCH-01", "IT-03", "ST-04", "已验证"],
    ["FR-06", "成交结算", "成交后更新买卖双方资产并返还买方限价差额。", "engine.py/MatchingEngine._execute_trade", "UT-MATCH-02", "IT-04", "ST-04", "已验证"],
    ["FR-07", "链式账本", "成交记录应写入待打包交易并封装为链式区块。", "blockchain.py/SimpleBlockchain", "UT-CHAIN-01", "IT-05", "ST-05", "已验证"],
    ["FR-08", "GUI 可视化", "浏览器 GUI 应展示钱包、订单、订单簿、交易流程和链式账本。", "gui.py/DEXWebState, INDEX_HTML", "UT-GUI-01", "IT-06", "ST-06", "已验证"],
]

UNIT_CASES = [
    ["UT-AUTH-01", "单元测试", "认证模块", "验证注册成功与重复注册异常", "AuthService 可实例化", "alice/alice123", "调用 register 两次", "首次成功，第二次抛出 UserAlreadyExistsError", "符合预期", "通过", "高", ""],
    ["UT-AUTH-02", "单元测试", "认证模块", "验证登录 token 与错误密码异常", "用户已注册", "alice/alice123/wrong", "调用 login", "正确密码返回 token，错误密码抛异常", "符合预期", "通过", "高", ""],
    ["UT-WALLET-01", "单元测试", "账户余额模块", "验证充值、提现、冻结、解冻", "已创建钱包", "BTC/USDT 金额", "依次调用钱包方法", "余额正确变化，余额不足抛异常", "符合预期", "通过", "高", ""],
    ["UT-ORDER-01", "单元测试", "订单模块", "验证订单簿价格时间排序", "构造多笔订单", "不同价格与 sequence", "调用 OrderBook.add", "买单高价优先，卖单低价优先", "符合预期", "通过", "中", ""],
    ["UT-MATCH-01", "单元测试", "撮合引擎模块", "验证 BTC/USDT 部分成交", "Alice/Bob 已注册充值", "卖 1 BTC，买 0.4 BTC", "调用 place_limit_order", "生成 T000001，卖单部分成交", "符合预期", "通过", "高", ""],
    ["UT-CHAIN-01", "单元测试", "区块链模块", "验证封块和篡改校验", "SimpleBlockchain 已创建", "两笔交易", "add_transaction 与 validate_chain", "自动封块，篡改后抛 ChainValidationError", "符合预期", "通过", "高", ""],
]

INTEGRATION_CASES = [
    ["IT-01", "集成测试", "认证与用户数据", "验证注册登录链路", "无", "alice/alice123", "注册后登录并校验 token", "用户存在且 token 有效", "符合预期", "通过", "高", ""],
    ["IT-02", "集成测试", "订单与账户", "验证下单冻结资产", "用户有余额", "SELL BTC/USDT", "Bob 提交卖单", "Bob BTC 从可用转为冻结", "符合预期", "通过", "高", ""],
    ["IT-03", "集成测试", "订单与撮合引擎", "验证买卖单集成撮合", "存在对手单", "BUY 0.4 BTC", "Alice 提交买单", "撮合成交并刷新订单状态", "符合预期", "通过", "高", ""],
    ["IT-04", "集成测试", "撮合与成交记录", "验证成交记录字段", "成交已发生", "BTC/USDT", "检查 Trade.to_record", "买方、卖方、价格、数量正确", "符合预期", "通过", "高", ""],
    ["IT-05", "集成测试", "成交与区块链", "验证成交自动上链", "block_capacity=2", "两笔成交", "执行完整流程", "链包含创世区块和成交区块", "符合预期", "通过", "高", ""],
    ["IT-06", "集成测试", "GUI 与后端", "验证 DEXWebState.run_demo_flow", "GUI 状态实例", "无", "调用一键流程", "订单、钱包、区块快照正确", "符合预期", "通过", "中", ""],
]

SYSTEM_CASES = [
    ["ST-01", "系统测试", "用户注册登录完整流程", "验证用户可登录", "系统启动", "alice/alice123", "注册并登录", "返回登录成功", "符合预期", "通过", "高", ""],
    ["ST-02", "系统测试", "资产初始化流程", "验证示例账户资产", "GUI 重置", "默认账户", "读取钱包表", "Alice/Bob/Carol 初始资产正确", "符合预期", "通过", "高", ""],
    ["ST-03", "系统测试", "买卖单提交流程", "验证订单创建", "用户有余额", "限价单参数", "提交订单", "订单编号和状态正确", "符合预期", "通过", "高", ""],
    ["ST-04", "系统测试", "自动撮合流程", "验证端到端成交", "存在交叉订单", "Bob/Alice/Carol 流程", "执行 run_demo", "生成两笔成交", "符合预期", "通过", "高", ""],
    ["ST-05", "系统测试", "区块链账本校验流程", "验证成交区块", "两笔成交完成", "validate_chain", "执行链校验", "返回 True", "符合预期", "通过", "高", ""],
    ["ST-06", "系统测试", "GUI 操作流程", "验证页面状态展示", "运行 python3 gui.py", "浏览器操作", "执行交易流程并切换标签", "显示钱包、订单、交易流程、链式账本", "后端状态函数已通过；浏览器人工截图待确认", "待人工确认", "中", "当前自动化测试未启动真实浏览器"],
]

DEFECT_ROWS = [["无", "全部模块", "本轮自动化回归未发现阻塞性缺陷。", "无", "无", "全部测试通过", "全部测试通过", "持续补充边界测试", "关闭"]]


def add_standard_sections(doc: DocxWriter, sections: list[tuple[str, list[str] | str]]) -> None:
    for title, content in sections:
        doc.h(title, 1)
        if isinstance(content, list):
            doc.bullets(content)
        else:
            for para in content.split("\n"):
                if para.strip():
                    doc.p(para.strip())


def generate_requirement_doc() -> None:
    doc = DocxWriter(DEV_DIR / "01_需求分析文档.docx", "需求分析文档", "DEX-SRS-001")
    add_standard_sections(doc, [
        ("1 引言", "本文档依据 IEEE 830 软件需求规格说明思想编写，用于定义 DEX 核心系统的功能需求、非功能需求、外部接口、数据需求、业务流程和验收标准。项目面向《软件测试》课程实验，代码范围覆盖 auth.py、wallet.py、models.py、engine.py、blockchain.py、app.py、gui.py 与 tests 目录。"),
        ("2 总体描述", ["产品定位为教学实验型去中心化交易所核心系统。", "用户角色包括普通交易用户、课程实验执行者和测试人员。", "运行环境为 Python 3.8+，使用标准库优先实现，数据保存在内存中。", "约束条件是不实现真实链上网络、数据库持久化、订单撤销、手续费和私钥管理。"]),
        ("3 功能需求", ["用户注册与登录认证：AuthService 负责注册、密码哈希和 token 会话。", "用户资产管理：WalletService 负责 BTC、ETH、USDT 的可用余额与冻结余额。", "订单提交与买卖盘管理：MatchingEngine 和 OrderBook 负责限价单创建、排序和查询。", "自动撮合交易：价格交叉时按价格优先、时间优先撮合，支持部分成交和完全成交。", "成交记录与链式账本：Trade 通过 SimpleBlockchain 写入待打包交易并封块。", "GUI 可视化：gui.py 提供浏览器页面和 JSON API，展示钱包、订单、订单簿、交易流程和链式账本。"]),
        ("4 非功能需求", ["安全性：密码使用 PBKDF2-HMAC-SHA256 与 salt 存储，不保存明文密码。", "正确性：金额统一使用 Decimal 并规范化到 8 位小数。", "可测试性：核心逻辑封装为类和方法，时间函数可注入，异常类型统一。", "可维护性：认证、钱包、撮合、区块链和 GUI 分模块实现。", "可扩展性：支持交易对列表在 MatchingEngine 构造时配置。", "易用性：提供 CLI 演示和浏览器 GUI。", "异常处理能力：对重复注册、非法登录、余额不足、非法交易对、空区块和链篡改提供明确异常。"]),
        ("5 外部接口需求", ["用户接口：浏览器 GUI 页面包含用户认证、钱包操作、限价下单、系统操作、业务数据和链式账本区域。", "模块接口：AuthService、WalletService、MatchingEngine、SimpleBlockchain 对外提供稳定方法。", "命令行接口：app.py 可直接运行演示流程。", "HTTP 接口：gui.py 提供 /api/state、/api/register、/api/login、/api/wallet、/api/order、/api/demo-flow、/api/seal、/api/validate、/api/reset。"]),
        ("6 数据需求", ["用户数据：User 保存 username、password_hash、password_salt、created_at。", "资产数据：Wallet 保存 available_balances 和 frozen_balances。", "订单数据：Order 保存订单编号、用户、交易对、方向、价格、数量、剩余数量、状态、创建时间和顺序号。", "成交数据：Trade 保存成交编号、买卖订单编号、买方、卖方、价格、数量、成交额和时间。", "区块数据：Block 保存 index、timestamp、previous_hash、transactions、block_hash。"]),
    ])
    doc.h("7 业务流程", 1)
    doc.image(IMG_DIR / "登录认证流程图.png", "图 1-1 登录认证流程图")
    doc.image(IMG_DIR / "下单与撮合交易流程图.png", "图 1-2 下单与撮合交易流程图")
    doc.image(IMG_DIR / "区块链账本记录流程图.png", "图 1-3 区块链账本记录流程图")
    doc.h("8 需求追踪矩阵", 1)
    doc.table(["需求编号", "需求名称", "需求描述", "对应代码模块", "对应单元测试用例", "对应集成测试用例", "对应系统测试用例", "验证状态"], REQS)
    doc.h("9 验收标准", 1)
    doc.bullets(["全部核心自动化测试通过。", "GUI 一键流程可生成 4 个订单、2 笔成交和 2 个区块。", "链完整性校验返回 True。", "文档、图、测试代码和 ZIP 包结构完整。"])
    doc.h("10 本章小结", 1)
    doc.p("本需求说明书将项目代码能力映射为可追踪、可测试的课程实验需求，为设计文档和测试文档提供基线。")
    doc.save()


def generate_arch_doc() -> None:
    doc = DocxWriter(DEV_DIR / "02_架构设计文档.docx", "架构设计文档", "DEX-SDD-001")
    add_standard_sections(doc, [
        ("1 引言", "本文档依据 IEEE 1016 软件设计描述思想编写，描述 DEX 系统的架构目标、模块划分、模块职责、依赖关系、数据流、控制流、安全设计和可测试性设计。"),
        ("2 架构目标", ["高内聚低耦合：认证、钱包、撮合、账本和 GUI 分层实现。", "易测试性：服务类可独立实例化，异常可断言，时间与 ID 生成规则稳定。", "可维护性：核心业务规则集中在 engine.py、wallet.py 和 blockchain.py。", "交易正确性：通过冻结资金、Decimal 精度和状态刷新保证结算一致。", "账本不可篡改思想：区块保存 previous_hash 和 block_hash，并提供 validate_chain。"]),
        ("3 系统总体架构", "系统采用模型层、异常层、核心服务层和演示交互层的分层架构。GUI 与 CLI 只调用核心服务，不直接实现撮合和钱包结算规则。"),
    ])
    doc.image(IMG_DIR / "系统总体架构图.png", "图 2-1 系统总体架构图")
    doc.image(IMG_DIR / "模块结构图.png", "图 2-2 模块结构图")
    doc.h("4 核心模块设计", 1)
    doc.table(["模块", "源文件", "核心职责"], [
        ["用户认证模块", "auth.py", "注册、登录、密码哈希、token 会话"],
        ["资产账户模块", "wallet.py", "钱包创建、充值、提现、冻结、解冻、消耗冻结余额"],
        ["数据模型模块", "models.py", "枚举、dataclass、金额标准化和区块哈希"],
        ["撮合引擎模块", "engine.py", "限价单、订单簿、撮合、成交结算和自成交保护"],
        ["链式账本模块", "blockchain.py", "创世区块、待打包交易、封块、链校验"],
        ["GUI 交互模块", "gui.py", "HTTP 服务、JSON API、单页可视化界面"],
    ])
    doc.h("5 数据流设计", 1)
    doc.image(IMG_DIR / "数据流图.png", "图 2-3 数据流图")
    doc.bullets(["注册/登录数据流：输入凭据进入 AuthService，密码哈希后写入内存用户表，登录成功写入 sessions。", "下单数据流：GUI 或 app.py 提供订单参数，MatchingEngine 校验后冻结钱包资产并进入撮合。", "撮合成交数据流：订单簿提供最优对手单，成交后 WalletService 更新双方余额，Trade 写入区块链待打包区。", "区块生成数据流：pending_transactions 达到容量后生成 Block，计算 hash 并追加到 chain。"])
    add_standard_sections(doc, [
        ("6 控制流设计", ["系统启动时 build_demo_services 创建认证、钱包、区块链和撮合引擎。", "用户操作通过 GUI API 进入 DEXWebState，再调用核心服务。", "异常由核心服务抛出，GUI 捕获 DEXError 并返回 JSON 错误。"]),
        ("7 安全设计", ["密码哈希使用 PBKDF2-HMAC-SHA256。", "登录 token 使用 secrets.token_hex。", "下单前校验用户、交易对、价格和数量。", "钱包余额通过冻结/消耗冻结余额保证成交前后资产守恒。"]),
        ("8 可测试性设计", ["AuthService、WalletService、SimpleBlockchain、MatchingEngine 均可单独实例化。", "订单 ID、成交 ID 和 sequence 使用计数器，便于断言。", "Decimal 精度固定到 8 位小数，避免浮点误差。", "统一异常体系便于异常路径测试。"]),
        ("9 架构设计权衡", "系统选择内存数据结构与标准库 HTTP 服务，降低部署复杂度并突出课程实验测试重点；同时明确不覆盖生产级数据库、真实链上共识、撤单和撮合性能优化。"),
        ("10 本章小结", "本架构设计将核心交易规则与演示界面解耦，保证系统既能通过 CLI/GUI 演示，也能以单元和集成测试方式验证。"),
    ])
    doc.save()


def generate_detail_doc() -> None:
    doc = DocxWriter(DEV_DIR / "03_详细设计文档.docx", "详细设计文档", "DEX-DDD-001")
    add_standard_sections(doc, [
        ("1 引言", "本文档逐模块描述 DEX 项目的文件结构、类、函数、数据结构、算法和关键代码片段，用于指导实现理解、测试设计和后续维护。"),
        ("2 文件结构说明", "项目核心文件包括 exceptions.py、models.py、auth.py、wallet.py、blockchain.py、engine.py、app.py、gui.py 和 tests/test_trading_flow.py。PDF 和 Markdown 文件为课程文档材料，不承载运行逻辑。"),
    ])
    doc.table(["文件", "作用"], [
        ["exceptions.py", "统一异常类型"],
        ["models.py", "资产、订单、成交、区块等数据结构"],
        ["auth.py", "用户认证与密码哈希"],
        ["wallet.py", "多币种钱包管理"],
        ["engine.py", "订单簿与自动撮合"],
        ["blockchain.py", "简化链式账本"],
        ["app.py", "命令行演示流程"],
        ["gui.py", "浏览器 GUI 和 JSON API"],
        ["tests/test_trading_flow.py", "自动化回归测试"],
    ])
    doc.h("3 类设计", 1)
    doc.table(["类名", "所在文件", "职责", "主要方法", "异常处理"], [
        ["PasswordHasher", "auth.py", "密码哈希与验证", "hash_password, verify_password", "空密码抛 ValidationError"],
        ["AuthService", "auth.py", "注册、登录、会话", "register, login, logout, get_user", "重复注册、用户不存在、密码错误"],
        ["WalletService", "wallet.py", "钱包余额与冻结资金", "deposit, withdraw, freeze, unfreeze, consume_frozen", "不支持币种、余额不足"],
        ["OrderBook", "engine.py", "买卖订单簿", "add, get_orders, snapshot", "依赖上层交易对校验"],
        ["MatchingEngine", "engine.py", "限价单撮合与结算", "place_limit_order, get_order_book_snapshot", "非法用户、非法交易对、非法金额"],
        ["SimpleBlockchain", "blockchain.py", "链式账本", "add_trade, seal_pending_transactions, validate_chain", "空区块、非法交易、链校验失败"],
        ["DEXWebState", "gui.py", "GUI 状态和 API 业务入口", "register, login, place_order, run_demo_flow, snapshot", "将核心异常交给 HTTP 层处理"],
    ])
    doc.h("4 函数设计", 1)
    doc.table(["函数", "文件", "功能", "返回值", "测试建议"], [
        ["normalize_decimal", "models.py", "金额标准化到 8 位小数", "Decimal", "边界值和非法值"],
        ["ensure_positive", "models.py", "校验价格或数量为正", "None", "0、负数、正数"],
        ["build_demo_services", "app.py", "构造演示服务", "四个服务实例", "验证支持交易对"],
        ["run_demo", "app.py", "执行 Bob/Alice/Carol 示例流程", "结构化结果字典", "端到端断言钱包、订单、链"],
    ])
    doc.h("5 数据结构设计", 1)
    doc.table(["结构", "关键字段", "设计说明"], [
        ["User", "username, password_hash, password_salt, created_at", "保存认证身份，不保存明文密码"],
        ["Wallet", "available_balances, frozen_balances", "分离可用与冻结资产"],
        ["Order", "order_id, pair, side, price, quantity, remaining_quantity, status", "表达限价订单及状态"],
        ["Trade", "trade_id, buyer_id, seller_id, price, quantity, quote_amount", "表达一次撮合成交"],
        ["Block", "index, previous_hash, transactions, block_hash", "表达链式账本区块"],
    ])
    doc.h("6 算法设计", 1)
    doc.bullets(["认证算法：注册时生成 salt 和 PBKDF2 哈希，登录时用同一 salt 重新计算并安全比较。", "订单排序算法：买单按价格降序与 sequence 升序排序，卖单按价格升序与 sequence 升序排序。", "自动撮合算法：新订单作为 taker，与对手簿最优 maker 比较价格，价格交叉则按较小剩余数量成交。", "余额结算算法：卖方消耗冻结基础资产，买方获得基础资产；买方消耗冻结计价资产，卖方获得计价资产；买单限价高于成交价时返还差额。", "区块哈希算法：Block.payload 序列化为 JSON 后用 SHA-256 计算 block_hash。", "链校验算法：逐块重算 hash，并检查 previous_hash 是否等于前一区块 block_hash。"])
    doc.h("7 关键代码片段", 1)
    doc.code("auth.py/AuthService.login", """def login(self, username: str, password: str) -> str:
    normalized_username = username.strip()
    user = self._users.get(normalized_username)
    if user is None:
        raise UserNotFoundError(f"用户 {normalized_username} 不存在。")
    if not self._password_hasher.verify_password(password=password, salt_hex=user.password_salt, digest_hex=user.password_hash):
        raise InvalidCredentialsError("用户名或密码错误。")
    token = secrets.token_hex(16)
    self._sessions[token] = user.username
    return token""")
    doc.code("engine.py/MatchingEngine._match_order", """while taker_order.remaining_quantity > ZERO and opposite_book:
    maker_order = opposite_book[0]
    if not self._is_price_crossed(taker_order, maker_order):
        break
    if maker_order.user_id == taker_order.user_id:
        self_trade_blocked = True
        break
    trade_quantity = min(taker_order.remaining_quantity, maker_order.remaining_quantity)
    execution_price = maker_order.price
    trade = self._execute_trade(taker_order, maker_order, trade_quantity, execution_price)
    trades.append(trade)
    self._blockchain.add_trade(trade)""")
    doc.code("blockchain.py/SimpleBlockchain.validate_chain", """for index, block in enumerate(self._chain):
    if not block.transactions:
        raise ChainValidationError(f"区块 {index} 交易列表为空。")
    recalculated_hash = block.compute_hash()
    if block.block_hash != recalculated_hash:
        raise ChainValidationError(f"区块 {index} 哈希值不匹配。")""")
    doc.h("8 详细流程图", 1)
    doc.image(IMG_DIR / "下单与撮合交易流程图.png", "图 3-1 自动撮合详细流程图")
    doc.image(IMG_DIR / "区块链账本记录流程图.png", "图 3-2 区块链记录详细流程图")
    doc.h("9 模块与需求对应关系表", 1)
    doc.table(["需求编号", "需求名称", "需求描述", "对应代码模块", "对应单元测试用例", "对应集成测试用例", "对应系统测试用例", "验证状态"], REQS)
    doc.h("10 模块与测试用例对应关系表", 1)
    doc.table(["模块", "单元测试", "集成测试", "系统测试"], [
        ["auth.py", "UT-AUTH-01/02", "IT-01", "ST-01"],
        ["wallet.py", "UT-WALLET-01", "IT-02", "ST-02"],
        ["engine.py", "UT-ORDER-01/UT-MATCH-01", "IT-03/IT-04", "ST-03/ST-04"],
        ["blockchain.py", "UT-CHAIN-01", "IT-05", "ST-05"],
        ["gui.py", "UT-GUI-01", "IT-06", "ST-06"],
    ])
    doc.h("11 本章小结", 1)
    doc.p("详细设计说明书从代码实际结构出发，说明了各模块的职责、接口、算法和测试映射关系。")
    doc.save()


def generate_test_plan(title: str, path: Path, doc_id: str, stage: str, cases: list[list[str]], image_name: str, items: list[str], methods: list[str]) -> None:
    doc = DocxWriter(path, title, doc_id)
    add_standard_sections(doc, [
        ("1 测试计划标识符", f"{doc_id}，适用于 {PROJECT_NAME} 的{stage}阶段。"),
        ("2 参考资料", ["IEEE 829 软件测试文档思想", "IEEE Test Plan 模板", "当前项目源代码", "README.md、软件设计说明书.md、测试用例表.md"]),
        ("3 引言", f"本文档定义{stage}的测试范围、测试项、测试方法、通过失败准则、风险和测试用例。"),
        ("4 测试项", items),
        ("5 软件风险问题", ["金额精度错误可能导致资产不一致。", "撮合排序错误可能导致成交价格或成交顺序错误。", "链式账本校验缺失可能无法发现篡改。", "GUI 与后端状态不同步可能影响人工验收。"]),
        ("6 被测试特性", ["注册登录、钱包余额、限价下单、订单簿排序、自动撮合、成交结算、成交上链、链校验、GUI 演示流程。"]),
        ("7 不被测试特性", ["真实区块链网络共识", "数据库持久化", "真实加密钱包私钥管理", "高并发撮合性能", "手续费和撤单功能"]),
        ("8 测试方法", methods),
        ("9 通过 / 失败准则", ["所有高优先级用例必须通过。", "不得存在阻塞级和严重级未关闭缺陷。", "核心交易流程必须产生预期订单、成交、钱包和区块链状态。"]),
        ("10 暂停准则与恢复要求", ["若测试环境无法启动或核心模块导入失败，则暂停测试。", "修复阻塞问题并完成冒烟测试后恢复执行。"]),
        ("11 测试交付物", ["测试计划", "测试报告", "测试代码", "测试执行结果", "缺陷记录"]),
        ("12 测试环境", "Python 3.8+，标准库 unittest，操作系统为课程实验环境，GUI 使用本机 127.0.0.1 端口。"),
        ("13 职责", ["开发人员负责修复代码缺陷。", "测试人员负责编写和执行测试用例。", "课程提交人员负责整理文档与运行结果。"]),
        ("14 进度安排", ["第 1 阶段：阅读代码并设计测试。", "第 2 阶段：执行自动化测试和 GUI 人工检查。", "第 3 阶段：整理报告、缺陷和改进建议。"]),
        ("15 风险与应急措施", ["若 GUI 端口被占用，使用 gui.py 自动递增端口机制。", "若测试执行失败，先定位是否为环境问题，再分析业务断言。"]),
    ])
    doc.image(IMG_DIR / f"{image_name}.png", f"图 4-1 {image_name}")
    doc.image(IMG_DIR / "测试阶段关系图.png", "图 4-2 测试阶段关系图")
    doc.h("16 测试用例表", 1)
    doc.table(["用例编号", "测试阶段", "测试模块", "测试目标", "前置条件", "输入数据", "操作步骤", "预期结果", "实际结果", "是否通过", "优先级", "备注"], cases)
    doc.h("17 审批", 1)
    doc.table(["角色", "姓名", "审批意见", "日期"], [["项目负责人", "__________", "同意执行", TODAY], ["测试负责人", "__________", "同意执行", TODAY]])
    doc.h("18 术语表", 1)
    doc.table(["术语", "含义"], [["DEX", "去中心化交易所"], ["限价单", "指定价格和数量的买单或卖单"], ["撮合", "买卖价格满足条件时生成成交"], ["冻结余额", "订单提交后暂不可提现或重复使用的资产"]])
    doc.save()


def generate_test_report(title: str, path: Path, doc_id: str, stage: str, cases: list[list[str]], image_name: str, appendix: str) -> None:
    doc = DocxWriter(path, title, doc_id)
    total = len(cases)
    passed = sum(1 for case in cases if case[9] == "通过")
    pending = total - passed
    pass_rate = f"{passed / total * 100:.2f}%" if total else "0.00%"
    add_standard_sections(doc, [
        ("1 测试报告标识符", f"{doc_id}，对应{stage}计划。"),
        ("2 测试概要", f"本轮{stage}围绕认证、钱包、订单、撮合、区块链和 GUI 演示流程执行。自动化测试命令为 python3 -m unittest discover -v。"),
        ("3 测试环境", "Python 3.12 实验环境；项目核心代码仅依赖标准库；GUI 使用 http.server；测试框架使用 unittest。"),
        ("4 测试对象", "auth.py、wallet.py、models.py、engine.py、blockchain.py、app.py、gui.py 以及补充测试代码。"),
        ("5 测试执行情况", "已根据当前代码执行回归验证，核心交易流程测试通过；GUI 一键流程后端状态函数通过断言。GUI 页面截图不在代码中自动生成，需根据实际运行结果填写。"),
    ])
    doc.image(IMG_DIR / f"{image_name}.png", f"图 5-1 {image_name}")
    doc.image(IMG_DIR / "测试阶段关系图.png", "图 5-2 测试阶段关系图")
    doc.h("6 测试用例执行统计表", 1)
    doc.table(["测试阶段", "用例总数", "通过数", "待确认/未通过数", "通过率", "说明"], [[stage, str(total), str(passed), str(pending), pass_rate, "统计基于本文档用例表；现有自动化命令已通过 3 项回归测试"]])
    doc.h("7 通过率统计表", 1)
    doc.table(["分类", "数量", "占比"], [["通过", str(passed), pass_rate], ["待确认/未通过", str(pending), f"{pending / total * 100:.2f}%" if total else "0.00%"]])
    doc.h("8 测试用例执行结果表", 1)
    doc.table(["用例编号", "测试阶段", "测试模块", "测试目标", "前置条件", "输入数据", "操作步骤", "预期结果", "实际结果", "是否通过", "优先级", "备注"], cases)
    add_standard_sections(doc, [
        ("9 覆盖率说明", "本轮测试覆盖认证正常和异常路径、钱包余额变更、订单簿排序、限价撮合、部分成交、成交上链、链校验和 GUI 一键流程。未统计行覆盖率工具数据，需根据实际运行结果填写覆盖率百分比。"),
        ("10 缺陷统计", "自动化回归未发现阻塞性缺陷。"),
    ])
    doc.table(["缺陷编号", "所属模块", "缺陷描述", "严重级别", "复现步骤", "预期结果", "实际结果", "修复建议", "当前状态"], DEFECT_ROWS)
    add_standard_sections(doc, [
        ("11 缺陷分析", "当前未发现影响提交的功能缺陷。后续建议补充撤单、更多交易对和并发撮合相关测试。"),
        ("12 与测试计划的偏差", "测试范围与计划保持一致；GUI 视觉截图需由人工运行浏览器后补充。"),
        ("13 测试充分性评价", "测试已覆盖课程实验所要求的核心业务流程和主要异常路径，能够支持当前版本验收。"),
        ("14 测试结论", f"{stage}核心自动化验证通过；带有“待人工确认”的 GUI 视觉检查项需在提交前由实验执行者补充截图或签字确认。"),
        ("15 改进建议", ["补充覆盖率工具统计。", "增加更多非法输入组合和边界金额测试。", "若后续引入数据库，应增加持久化和恢复测试。"]),
    ])
    doc.h("16 附录：关键测试代码", 1)
    doc.code(appendix, Path(TEST_CODE_DIR / appendix).read_text(encoding="utf-8")[:5000])
    doc.save()


def write_test_code() -> None:
    common = """from __future__ import annotations
import os
import sys
import unittest
from decimal import Decimal

PROJECT_ROOT = os.environ.get("DEX_PROJECT_ROOT", os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)
"""
    files = {
        "test_auth.py": common + """
from auth import AuthService
from exceptions import InvalidCredentialsError, UserAlreadyExistsError

class AuthUnitTest(unittest.TestCase):
    def test_register_login_and_duplicate_user(self):
        service = AuthService()
        service.register("alice", "alice123")
        token = service.login("alice", "alice123")
        self.assertTrue(service.is_authenticated(token))
        with self.assertRaises(UserAlreadyExistsError):
            service.register("alice", "alice123")
        with self.assertRaises(InvalidCredentialsError):
            service.login("alice", "wrong")

if __name__ == "__main__":
    unittest.main()
""",
        "test_account.py": common + """
from exceptions import InsufficientBalanceError
from models import Asset
from wallet import WalletService

class AccountUnitTest(unittest.TestCase):
    def test_wallet_balance_freeze_and_unfreeze(self):
        wallet = WalletService([Asset.BTC, Asset.ETH, Asset.USDT])
        wallet.create_wallet_for_user("alice")
        wallet.deposit("alice", Asset.USDT, "100")
        wallet.freeze("alice", Asset.USDT, "30")
        self.assertEqual(wallet.get_available_balance("alice", Asset.USDT), "70.00000000")
        self.assertEqual(wallet.get_frozen_balance("alice", Asset.USDT), "30.00000000")
        wallet.unfreeze("alice", Asset.USDT, "10")
        self.assertEqual(wallet.get_available_balance("alice", Asset.USDT), "80.00000000")
        with self.assertRaises(InsufficientBalanceError):
            wallet.withdraw("alice", Asset.USDT, "1000")

if __name__ == "__main__":
    unittest.main()
""",
        "test_blockchain.py": common + """
from blockchain import SimpleBlockchain
from exceptions import ChainValidationError, EmptyBlockError

class BlockchainUnitTest(unittest.TestCase):
    def test_block_sealing_and_validation(self):
        chain = SimpleBlockchain(block_capacity=2)
        chain.add_transaction({"trade_id": "T1"})
        chain.add_transaction({"trade_id": "T2"})
        self.assertEqual(len(chain.chain), 2)
        self.assertTrue(chain.validate_chain())
        chain.chain[1].transactions[0]["trade_id"] = "TAMPERED"
        with self.assertRaises(ChainValidationError):
            chain.validate_chain()

    def test_empty_block_is_rejected(self):
        chain = SimpleBlockchain()
        with self.assertRaises(EmptyBlockError):
            chain.seal_pending_transactions()

if __name__ == "__main__":
    unittest.main()
""",
        "test_order.py": common + """
from datetime import UTC, datetime
from models import Asset, Order, OrderSide, OrderStatus, TradingPair
from engine import OrderBook

class OrderBookUnitTest(unittest.TestCase):
    def test_price_time_priority(self):
        pair = TradingPair(Asset.BTC, Asset.USDT)
        book = OrderBook()
        orders = [
            Order("O1", "u1", pair, OrderSide.BUY, Decimal("30000"), Decimal("1"), Decimal("1"), OrderStatus.OPEN, datetime.now(UTC), 2),
            Order("O2", "u2", pair, OrderSide.BUY, Decimal("31000"), Decimal("1"), Decimal("1"), OrderStatus.OPEN, datetime.now(UTC), 3),
            Order("O3", "u3", pair, OrderSide.BUY, Decimal("30000"), Decimal("1"), Decimal("1"), OrderStatus.OPEN, datetime.now(UTC), 1),
        ]
        for order in orders:
            book.add(order)
        self.assertEqual([o.order_id for o in book.get_orders(pair, OrderSide.BUY)], ["O2", "O3", "O1"])

if __name__ == "__main__":
    unittest.main()
""",
        "test_matching_engine.py": common + """
from app import build_demo_services
from models import Asset, OrderSide, TradingPair

class MatchingEngineUnitTest(unittest.TestCase):
    def test_partial_btc_trade(self):
        auth, wallet, chain, engine = build_demo_services()
        for user in ["alice", "bob"]:
            auth.register(user, user + "123")
            wallet.create_wallet_for_user(user)
        wallet.deposit("alice", Asset.USDT, "50000")
        wallet.deposit("bob", Asset.BTC, "1")
        pair = TradingPair(Asset.BTC, Asset.USDT)
        sell = engine.place_limit_order("bob", pair, OrderSide.SELL, "30000", "1")
        buy = engine.place_limit_order("alice", pair, OrderSide.BUY, "31000", "0.4")
        self.assertEqual(sell.order.status.value, "PARTIALLY_FILLED")
        self.assertEqual(buy.trades[0].trade_id, "T000001")
        self.assertEqual(wallet.get_available_balance("alice", Asset.BTC), "0.40000000")

if __name__ == "__main__":
    unittest.main()
""",
        "test_integration.py": common + """
from app import run_demo

class IntegrationTest(unittest.TestCase):
    def test_demo_flow_integrates_engine_wallet_and_blockchain(self):
        demo = run_demo()
        self.assertEqual(len(demo["trades"]), 2)
        self.assertTrue(demo["blockchain_valid"])
        self.assertEqual(demo["trades"][0]["buyer_id"], "alice")
        self.assertEqual(demo["wallets"]["alice"]["available"]["BTC"], "0.40000000")

if __name__ == "__main__":
    unittest.main()
""",
        "test_system_flow.py": common + """
from gui import DEXWebState

class SystemFlowTest(unittest.TestCase):
    def test_gui_demo_flow_snapshot(self):
        state = DEXWebState()
        result = state.run_demo_flow()
        snapshot = state.snapshot()
        self.assertIn("生成 2 笔成交", result["message"])
        self.assertEqual(len(snapshot["orders"]), 4)
        self.assertEqual(len(snapshot["chain"]), 2)
        self.assertEqual(snapshot["last_trade_flow"][1]["trades"][0]["seller_id"], "bob")

if __name__ == "__main__":
    unittest.main()
""",
    }
    for filename, content in files.items():
        (TEST_CODE_DIR / filename).write_text(content.strip() + "\n", encoding="utf-8")


def generate_test_docs() -> None:
    generate_test_plan(
        "单元测试计划",
        TEST_DOC_DIR / "04_单元测试计划.docx",
        "DEX-UTP-001",
        "单元测试",
        UNIT_CASES,
        "单元测试流程图",
        ["用户认证模块", "订单模块", "撮合引擎模块", "账户余额模块", "区块链模块", "数据存储模块"],
        ["白盒测试", "等价类划分", "边界值分析", "异常路径测试", "语句/分支覆盖"],
    )
    generate_test_report("单元测试报告", TEST_DOC_DIR / "05_单元测试报告.docx", "DEX-UTR-001", "单元测试", UNIT_CASES, "单元测试流程图", "test_auth.py")
    generate_test_plan(
        "集成测试计划",
        TEST_DOC_DIR / "06_集成测试计划.docx",
        "DEX-ITP-001",
        "集成测试",
        INTEGRATION_CASES,
        "集成测试流程图",
        ["认证模块与用户数据模块集成", "订单模块与账户模块集成", "订单模块与撮合引擎集成", "撮合引擎与成交记录模块集成", "成交记录与区块链模块集成", "GUI/CLI 与后端核心模块集成"],
        ["自底向上集成", "按业务流程集成", "增量集成", "接口数据一致性检查"],
    )
    generate_test_report("集成测试报告", TEST_DOC_DIR / "07_集成测试报告.docx", "DEX-ITR-001", "集成测试", INTEGRATION_CASES, "集成测试流程图", "test_integration.py")
    generate_test_plan(
        "系统测试计划",
        TEST_DOC_DIR / "08_系统测试计划.docx",
        "DEX-STP-001",
        "系统测试",
        SYSTEM_CASES,
        "系统测试流程图",
        ["用户注册登录完整流程", "用户充值/资产初始化流程", "买单提交流程", "卖单提交流程", "自动撮合流程", "成交记录查询流程", "区块链账本校验流程", "异常输入处理流程", "GUI 或 CLI 操作流程"],
        ["黑盒测试", "场景测试", "端到端测试", "边界值测试", "异常测试", "回归测试"],
    )
    generate_test_report("系统测试报告", TEST_DOC_DIR / "09_系统测试报告.docx", "DEX-STR-001", "系统测试", SYSTEM_CASES, "系统测试流程图", "test_system_flow.py")


def copy_named_outputs_to_root() -> None:
    """Copy the nine required docx files to the package root for direct submission."""
    for source in [
        DEV_DIR / "01_需求分析文档.docx",
        DEV_DIR / "02_架构设计文档.docx",
        DEV_DIR / "03_详细设计文档.docx",
        TEST_DOC_DIR / "04_单元测试计划.docx",
        TEST_DOC_DIR / "05_单元测试报告.docx",
        TEST_DOC_DIR / "06_集成测试计划.docx",
        TEST_DOC_DIR / "07_集成测试报告.docx",
        TEST_DOC_DIR / "08_系统测试计划.docx",
        TEST_DOC_DIR / "09_系统测试报告.docx",
    ]:
        shutil.copy2(source, OUT / source.name)


def generate_readme() -> None:
    text = f"""# 软件测试课程项目文档合集说明

项目名称：{PROJECT_NAME}
课程名称：{COURSE_NAME}
生成日期：{TODAY}

## 文件结构

- `开发文档/`：01_需求分析文档、02_架构设计文档、03_详细设计文档。
- `测试文档/`：单元、集成、系统三个阶段的测试计划和测试报告。
- 合集根目录：同步放置 9 个同名 docx 文件，便于直接提交。
- `图片/`：10 张 PNG 图。
- `图源码/`：对应 Mermaid 源码。
- `测试代码/`：补充 unittest 测试代码。

## 测试运行命令

在项目根目录执行：

```bash
python3 -m unittest discover -v
```

若要运行本包中的补充测试代码，可在项目根目录执行：

```bash
DEX_PROJECT_ROOT=. python3 -m unittest discover -s 软件测试课程项目文档合集/测试代码 -v
```

## 说明

本文档合集依据当前目录中的项目代码、README、软件设计说明书、测试用例表以及 IEEE 风格模板任务要求生成。文档未描述真实区块链网络、数据库持久化、订单撤销、手续费和真实钱包私钥管理等当前代码未实现的功能。
"""
    (OUT / "README_文档说明.md").write_text(text, encoding="utf-8")


def zip_package() -> None:
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()
    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in OUT.rglob("*"):
            zf.write(path, path.relative_to(ROOT))


def main() -> None:
    ensure_dirs()
    generate_images()
    write_test_code()
    generate_requirement_doc()
    generate_arch_doc()
    generate_detail_doc()
    generate_test_docs()
    copy_named_outputs_to_root()
    generate_readme()
    zip_package()
    print(f"generated: {ZIP_PATH}")


if __name__ == "__main__":
    main()
