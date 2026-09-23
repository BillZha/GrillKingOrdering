import time
import os
import re
import requests
import xml.sax.saxutils as saxutils
import json
from pathlib import Path

import base64
from PIL import Image, ImageDraw, ImageFont
import io


KITCHEN_ORDERS_URL = (
    "https://grillkingordering.onrender.com/kitchen/print-orders/"
)

PRINT_API_TOKEN = os.environ.get("PRINT_API_TOKEN", "")
PRINTER_URL = (
    "http://192.168.1.85/cgi-bin/epos/service.cgi"
    "?devid=local_printer&timeout=10000"
)

FEEDBACK_URL = (
    "https://grillkingordering.onrender.com/"
    "kitchen/print-feedback/"
)

FEEDBACK_PRINTED_URL = (
    "https://grillkingordering.onrender.com/"
    "kitchen/feedback/{}/printed/"
)

CHECK_INTERVAL = 3

PRINTED_ORDERS_FILE = Path("printed_orders.json")

def comment_to_epos_image(comment):
    font_path = r"C:\Windows\Fonts\msyh.ttc"

    width = 520
    padding = 20
    font_size = 34
    line_spacing = 12

    font = ImageFont.truetype(
        font_path,
        font_size
    )

    temp_image = Image.new(
        "1",
        (width, 100),
        1
    )

    draw = ImageDraw.Draw(temp_image)

    max_width = width - padding * 2

    # 中文按字，英文按完整单词处理
    tokens = re.findall(
        r"[A-Za-z0-9]+(?:['’-][A-Za-z0-9]+)*|\s+|.",
        comment
    )

    lines = []
    current_line = ""

    for token in tokens:
        if not current_line and token.isspace():
            continue

        test_line = current_line + token

        bbox = draw.textbbox(
            (0, 0),
            test_line,
            font=font
        )

        text_width = bbox[2] - bbox[0]

        if text_width <= max_width:
            current_line = test_line
            continue

        if current_line.strip():
            lines.append(
                current_line.rstrip()
            )

        current_line = ""

        bbox = draw.textbbox(
            (0, 0),
            token,
            font=font
        )

        token_width = bbox[2] - bbox[0]

        # 超长单词才允许拆开
        if token_width > max_width:
            for char in token:
                test_line = current_line + char

                bbox = draw.textbbox(
                    (0, 0),
                    test_line,
                    font=font
                )

                char_width = bbox[2] - bbox[0]

                if char_width > max_width:
                    if current_line:
                        lines.append(
                            current_line.rstrip()
                        )

                    current_line = char

                else:
                    current_line = test_line

        else:
            current_line = token.lstrip()

    if current_line.strip():
        lines.append(
            current_line.rstrip()
        )

    if not lines:
        lines = ["No comment"]

    bbox = draw.textbbox(
        (0, 0),
        "测试Test",
        font=font
    )

    line_height = bbox[3] - bbox[1]

    height = (
        padding * 2
        + len(lines) * line_height
        + (len(lines) - 1) * line_spacing
    )

    image = Image.new(
        "1",
        (width, height),
        1
    )

    draw = ImageDraw.Draw(image)

    y = padding

    for line in lines:
        bbox = draw.textbbox(
            (0, 0),
            line,
            font=font
        )

        text_width = bbox[2] - bbox[0]

        x = (width - text_width) // 2

        draw.text(
            (x, y),
            line,
            font=font,
            fill=0
        )

        y += line_height + line_spacing

    bytes_per_row = (width + 7) // 8

    raw = bytearray()

    pixels = image.load()

    for y in range(height):
        for byte_x in range(bytes_per_row):
            value = 0

            for bit in range(8):
                x = byte_x * 8 + bit

                value <<= 1

                if (
                    x < width
                    and pixels[x, y] == 0
                ):
                    value |= 1

            raw.append(value)

    encoded = base64.b64encode(
        raw
    ).decode("ascii")

    return (
        f'<image '
        f'width="{width}" '
        f'height="{height}" '
        f'color="color_1" '
        f'mode="mono">'
        f'{encoded}'
        f'</image>'
    )

def print_feedback(feedback):
    table_number = str(
        feedback.get("table_number") or "--"
    ).zfill(2)

    category = saxutils.escape(
        str(feedback.get("category", "Feedback")).upper()
    )

    comment = saxutils.escape(
        feedback.get("comment", "") or "No comment"
    )

    rating = int(feedback.get("rating", 0))

    stars = ("*" * rating) + ("-" * (5 - rating))

    attention_xml = ""

    if rating <= 2:
        attention_xml = (
            '<text width="1" height="2"/>'
            '<text em="true"/>'
            '<text>*** ATTENTION ***&#10;</text>'
            '<feed line="1"/>'
        )

    comment_text = (
        feedback.get("comment", "")
        or "No comment"
    )

    comment_xml = comment_to_epos_image(
        comment_text
    )

    xml = (
    '<s:Envelope '
    'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
    '<s:Body>'
    '<epos-print '
    'xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">'

    '<text align="center"/>'

    '<text width="2" height="2"/>'
    '<text em="true"/>'
    '<text>GRILL KING&#10;</text>'

    '<text width="1" height="2"/>'
    '<text>FEEDBACK&#10;</text>'

    '<feed line="1"/>'

    '<text width="2" height="2"/>'
    f'<text>TABLE {table_number}&#10;</text>'

    '<text width="1" height="1"/>'
    '<text em="false"/>'
    f'<text>{feedback["created_at"]}&#10;</text>'

    '<feed line="1"/>'
    '<text>--------------------------------&#10;</text>'
    '<feed line="1"/>'

    '<text width="1" height="2"/>'
    '<text em="true"/>'
    f'<text>{category}&#10;</text>'

    '<text width="1" height="2"/>'
    '<text em="false"/>'
    f'<text>RATING: {stars} ({rating}/5)&#10;</text>'

    '<feed line="1"/>'

    + attention_xml +

    '<text align="center"/>'

    + comment_xml +

    '<feed line="2"/>'

    '<text align="center"/>'
    '<text>--------------------------------&#10;</text>'

    '<feed line="6"/>'
    '<cut type="feed"/>'

    '</epos-print>'
    '</s:Body>'
    '</s:Envelope>'
)

    response = requests.post(
        PRINTER_URL,
        data=xml.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": '""',
        },
        timeout=10,
    )

    if 'success="true"' in response.text:
        print(
            f"Printed feedback #{feedback['id']}"
        )
        return True

    print(
        f"Printer error for feedback #{feedback['id']}:"
    )
    print(response.text)

    return False


def check_feedback():
    response = requests.get(
        FEEDBACK_URL,
        headers={
            "X-Print-Token": PRINT_API_TOKEN
        },
        timeout=10,
    )

    response.raise_for_status()

    data = response.json()

    for feedback in data["feedbacks"]:
        if print_feedback(feedback):

            mark_url = FEEDBACK_PRINTED_URL.format(
                feedback["id"]
            )

            mark_response = requests.post(
                mark_url,
                headers={
                    "X-Print-Token":
                        PRINT_API_TOKEN
                },
                timeout=10,
            )

            mark_response.raise_for_status()

def load_printed_orders():
    if not PRINTED_ORDERS_FILE.exists():
        return set()

    try:
        data = json.loads(
            PRINTED_ORDERS_FILE.read_text(
                encoding="utf-8"
            )
        )

        return set(data)

    except Exception:
        return set()


def save_printed_orders():
    PRINTED_ORDERS_FILE.write_text(
        json.dumps(
            sorted(printed_orders)
        ),
        encoding="utf-8"
    )


printed_orders = load_printed_orders()


def build_receipt(order):
    lines = []

    lines.append("GRILL KING")
    lines.append(
        f"TABLE {str(order['table_number']).zfill(2)}"
    )
    lines.append(f"ORDER #{order['id']}")
    lines.append(order["created_at"])
    lines.append("-" * 30)

    for item in order["items"]:
        line = f"{item['quantity']} x {item['name']}"

        if item.get("spicy") and item["spicy"] != "Not Spicy":
            line += f" - {item['spicy']}"

        lines.append(line)

    lines.append("-" * 30)

    receipt_text = "\n".join(lines) + "\n\n\n"

    return saxutils.escape(receipt_text)


def print_order(order):
    items_xml = ""

    for item in order["items"]:
        name = saxutils.escape(item["name"])
        quantity = item["quantity"]

        # 菜名稍微放大
        items_xml += '<text width="1" height="2"/>'
        items_xml += '<text em="true"/>'
        items_xml += (
            f'<text>{quantity} x {name}&#10;</text>'
        )

        spicy = item.get("spicy")

        if spicy and spicy != "Not Spicy":
            safe_spicy = saxutils.escape(
                spicy.upper()
            )

            items_xml += '<text width="1" height="1"/>'
            items_xml += (
                f'<text>    *** {safe_spicy} ***&#10;</text>'
            )

        # 每道菜之间留一点空间
        items_xml += '<feed line="1"/>'

    addon_xml = ""

    if order.get("is_addon"):
        addon_xml = (
            '<text width="2" height="2"/>'
            '<text em="true"/>'
            '<text>*** ADD-ON ***&#10;</text>'
            '<feed line="1"/>'
        )

    table_number = str(
        order["table_number"]
    ).zfill(2)

    xml = (
        '<s:Envelope '
        'xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">'
        '<s:Body>'

        '<epos-print '
        'xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">'

        '<text align="center"/>'

        # Restaurant
        '<text width="2" height="2"/>'
        '<text em="true"/>'
        '<text>GRILL KING&#10;</text>'

        '<feed line="1"/>'

        # Table number - biggest
        '<text width="2" height="2"/>'
        f'<text>TABLE {table_number}&#10;</text>'

        # Order number + time
        '<text width="1" height="1"/>'
        '<text em="false"/>'
        f'<text>ORDER #{order["id"]}   '
        f'{order["created_at"]}&#10;</text>'

        '<feed line="1"/>'

        + addon_xml +

        '<text>--------------------------------&#10;</text>'

        '<feed line="1"/>'

        # Items
        '<text align="center"/>'
        + items_xml +

        '<text align="center"/>'
        '<text width="1" height="1"/>'
        '<text em="false"/>'

        '<text>--------------------------------&#10;</text>'
        '<text>END ORDER&#10;</text>'

        # 关键：底部固定留白
        '<feed line="9"/>'

        '<cut type="feed"/>'

        '</epos-print>'
        '</s:Body>'
        '</s:Envelope>'
    )

    response = requests.post(
        PRINTER_URL,
        data=xml.encode("utf-8"),
        headers={
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": '""',
        },
        timeout=10,
    )

    if 'success="true"' in response.text:
        print(f"Printed order #{order['id']}")
        return True

    print(
        f"Printer error for order #{order['id']}:"
    )
    print(response.text)

    return False

def check_orders():
    response = requests.get(
        KITCHEN_ORDERS_URL,
        headers={
            "X-Print-Token": PRINT_API_TOKEN
        },
        timeout=10,
    )

    response.raise_for_status()

    data = response.json()

    for order in data["orders"]:

        if order["status"] != "new":
            continue

        if order["id"] in printed_orders:
            continue

        if print_order(order):
            printed_orders.add(order["id"])
            save_printed_orders()


print("GRILL KING Kitchen Printer Started")
print("Watching for new orders...")

while True:
    try:
        check_orders()
        check_feedback()

    except Exception as error:
        print("Error:", error)

    time.sleep(CHECK_INTERVAL)