import time
import os
import requests
import xml.sax.saxutils as saxutils
import json
from pathlib import Path

KITCHEN_ORDERS_URL = (
    "https://grillkingordering.onrender.com/kitchen/print-orders/"
)

PRINT_API_TOKEN = os.environ.get("PRINT_API_TOKEN", "")
PRINTER_URL = (
    "http://192.168.1.85/cgi-bin/epos/service.cgi"
    "?devid=local_printer&timeout=10000"
)

CHECK_INTERVAL = 3

PRINTED_ORDERS_FILE = Path("printed_orders.json")


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
        '<text align="left"/>'
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
    except Exception as error:
        print("Error:", error)

    time.sleep(CHECK_INTERVAL)