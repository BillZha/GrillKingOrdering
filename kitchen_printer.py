import time
import os
import requests
import xml.sax.saxutils as saxutils

KITCHEN_ORDERS_URL = (
    "https://grillkingordering.onrender.com/kitchen/print-orders/"
)

PRINT_API_TOKEN = os.environ.get("PRINT_API_TOKEN", "")
PRINTER_URL = (
    "http://192.168.1.85/cgi-bin/epos/service.cgi"
    "?devid=local_printer&timeout=10000"
)

CHECK_INTERVAL = 3

printed_orders = set()


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
    receipt = build_receipt(order)

    xml = f"""
    <s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">
        <s:Body>
            <epos-print
                xmlns="http://www.epson-pos.com/schemas/2011/03/epos-print">

                <text align="center"/>
                <text width="2" height="2">GRILL KING&#10;</text>

                <text width="1" height="1"/>
                <text>TABLE {str(order['table_number']).zfill(2)}&#10;</text>
                <text>ORDER #{order['id']}&#10;</text>
                <text>{order['created_at']}&#10;</text>
                <text>------------------------------&#10;</text>

                <text align="left"/>
                <text>{receipt}</text>

                <cut type="feed"/>

            </epos-print>
        </s:Body>
    </s:Envelope>
    """

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
        f"Printer error for order #{order['id']}:",
        response.text,
    )

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


print("GRILL KING Kitchen Printer Started")
print("Watching for new orders...")

while True:
    try:
        check_orders()
    except Exception as error:
        print("Error:", error)

    time.sleep(CHECK_INTERVAL)