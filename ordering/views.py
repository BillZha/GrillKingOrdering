import json
import base64
import xml.etree.ElementTree as ET
from django.db import models
from datetime import timedelta
from pathlib import Path
from xml.sax import saxutils
from django.http import HttpResponse
from django.views.decorators.csrf import csrf_exempt
from io import BytesIO
import qrcode

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone


from .models import Category, MenuItem, Order, OrderItem
from .models import Feedback
from django.conf import settings
from django.shortcuts import redirect

@ensure_csrf_cookie
def menu(request, table_number=0):
    categories = Category.objects.all()

    items = MenuItem.objects.filter(
        is_active=True
    ).select_related('category')

    return render(request, 'ordering/menu.html', {
        'categories': categories,
        'items': items,
        'table_number': table_number,
    })


@require_POST
def place_order(request):
    try:
        data = json.loads(request.body)

        table_number = int(data.get('table_number', 8))
        cart = data.get('cart', [])

        if not cart:
            return JsonResponse({
                'success': False,
                'error': 'Cart is empty.'
            }, status=400)

        total = 0

        order = Order.objects.create(
            table_number=table_number,
            total_amount=0,
            status='new'
        )

        for item in cart:
            name = item['name']
            price = float(item['price'])
            quantity = int(item['quantity'])
            spicy = item.get('spicy', '')

            total += price * quantity

            menu_item = MenuItem.objects.filter(
                name=name
            ).first()

            OrderItem.objects.create(
                order=order,
                menu_item=menu_item,
                name=name,
                price=price,
                quantity=quantity,
                spicy=spicy
            )

        order.total_amount = total
        order.save()

        return JsonResponse({
            'success': True,
            'order_id': order.id,
            'total': float(order.total_amount)
        })

    except Exception as e:
        return JsonResponse({
            'success': False,
            'error': str(e)
        }, status=500)


def text_to_epos_image(text):
    font_path = (
        Path(__file__).resolve().parent.parent
        / "fonts"
        / "NotoSansSC-VariableFont_wght.ttf"
    )

    width = 520
    padding = 20
    font_size = 34
    line_spacing = 10

    font = ImageFont.truetype(
        str(font_path),
        font_size
    )

    temp_image = Image.new(
        "1",
        (width, 100),
        1
    )

    draw = ImageDraw.Draw(temp_image)

    max_width = width - padding * 2

    lines = []
    current_line = ""

    for char in text:
        test_line = current_line + char

        bbox = draw.textbbox(
            (0, 0),
            test_line,
            font=font
        )

        text_width = bbox[2] - bbox[0]

        if text_width <= max_width:
            current_line = test_line
        else:
            if current_line:
                lines.append(current_line)

            current_line = char

    if current_line:
        lines.append(current_line)

    if not lines:
        lines = [""]

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

def qr_codes(request):
    tables = []

    base_url = settings.PUBLIC_BASE_URL.rstrip("/")

    for table_number in range(1, 21):

        url = f"{base_url}/table/{table_number}/"

        qr = qrcode.make(url)

        buffer = BytesIO()
        qr.save(buffer, format="PNG")

        image_base64 = base64.b64encode(
            buffer.getvalue()
        ).decode("utf-8")

        tables.append({
            "number": table_number,
            "url": url,
            "qr": image_base64,
        })

    return render(request, "ordering/qr_codes.html", {
        "tables": tables
    })

def kitchen(request):
    if not request.session.get("kitchen_authorized"):
        return redirect("kitchen_login")

    return render(request, "ordering/kitchen.html")

def kitchen_login(request):
    error = None

    if request.method == "POST":
        pin = request.POST.get("pin", "")

        if pin == settings.KITCHEN_PIN:
            request.session["kitchen_authorized"] = True
            return redirect("kitchen")

        error = "Incorrect PIN"

    return render(
        request,
        "ordering/kitchen_login.html",
        {
            "error": error
        }
    )

def kitchen_print_orders(request):
    token = request.headers.get("X-Print-Token")

    if not token or token != settings.PRINT_API_TOKEN:
        return JsonResponse(
            {"error": "Unauthorized"},
            status=403
        )

    orders = Order.objects.exclude(
        status="completed"
    ).prefetch_related("items").order_by("created_at")

    data = []

    for order in orders:
        data.append({
            "id": order.id,
            "table_number": order.table_number,
            "status": order.status,
            "created_at": timezone.localtime(
                order.created_at
            ).strftime("%I:%M %p"),
            "items": [
                {
                    "name": item.name,
                    "quantity": item.quantity,
                    "spicy": item.spicy,
                }
                for item in order.items.all()
            ]
        })

    return JsonResponse({
        "orders": data
    })

def kitchen_orders(request):
    if not request.session.get("kitchen_authorized"):
        return JsonResponse(
             {"error": "Unauthorized"},
              status=403
        )

    orders = Order.objects.exclude(
        status="completed"
    ).prefetch_related("items").order_by("created_at")

    data = []

    for order in orders:
        elapsed_minutes = max(
            0,
            int(
                (timezone.now() - order.created_at).total_seconds() // 60
            )
        )

        is_addon = Order.objects.filter(
             table_number=order.table_number,
             created_at__lt=order.created_at
        ).exclude(
             status="completed"
        ).exists()

        data.append({
            "id": order.id,
            "table_number": order.table_number,
            "status": order.status,
            "created_at": timezone.localtime(
                order.created_at
            ).strftime("%I:%M %p"),
            "elapsed_minutes": elapsed_minutes,
            "is_addon": is_addon,
            "items": [
                {
                    "name": item.name,
                    "quantity": item.quantity,
                    "spicy": item.spicy,
                }
                for item in order.items.all()
            ]
        })

    return JsonResponse({
        "orders": data
    })

@require_POST
def update_order_status(request, order_id):
    if not request.session.get("kitchen_authorized"):
        return JsonResponse(
            {"error": "Unauthorized"},
            status=403
        )

    order = get_object_or_404(Order, id=order_id)

    new_status = request.POST.get("status")

    allowed_statuses = [
        "new",
        "preparing",
        "ready",
        "completed",
    ]

    if new_status not in allowed_statuses:
        return JsonResponse(
            {
                "success": False,
                "error": "Invalid status"
            },
            status=400
        )

    order.status = new_status
    order.save(update_fields=["status"])

    return JsonResponse({
        "success": True,
        "status": order.status
    })

def print_test(request):
    return render(request, "ordering/print_test.html")

@require_POST
def submit_feedback(request):
    try:
        data = json.loads(request.body)

        table_number = data.get("table_number")
        category = data.get("category")
        rating = data.get("rating")
        comment = data.get("comment", "").strip()

        valid_categories = {
            "service",
            "food",
            "speed",
            "atmosphere",
        }

        if category not in valid_categories:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid category",
                },
                status=400,
            )

        try:
            rating = int(rating)
        except (TypeError, ValueError):
            return JsonResponse(
                {
                    "success": False,
                    "error": "Invalid rating",
                },
                status=400,
            )

        if rating < 1 or rating > 5:
            return JsonResponse(
                {
                    "success": False,
                    "error": "Rating must be between 1 and 5",
                },
                status=400,
            )

        try:
            table_number = int(table_number)
        except (TypeError, ValueError):
            table_number = None

        Feedback.objects.create(
            table_number=table_number,
            category=category,
            rating=rating,
            comment=comment,
        )

        return JsonResponse(
            {
                "success": True,
                "message": "Thank you for your feedback!",
            }
        )

    except Exception as e:
        print("Feedback error:", e)

        return JsonResponse(
            {
                "success": False,
                "error": "Unable to submit feedback",
            },
            status=500,
        )

@require_GET
def kitchen_print_feedback(request):
    token = request.headers.get("X-Print-Token")

    if (
        not settings.PRINT_API_TOKEN
        or token != settings.PRINT_API_TOKEN
    ):
        return JsonResponse(
            {"error": "Unauthorized"},
            status=403,
        )

    feedbacks = Feedback.objects.filter(
        printed=False
    ).order_by("created_at")

    data = []

    for feedback in feedbacks:
        data.append({
            "id": feedback.id,
            "table_number": feedback.table_number,
            "category": feedback.get_category_display(),
            "rating": feedback.rating,
            "comment": feedback.comment,
            "created_at": feedback.created_at.strftime(
                "%I:%M %p"
            ),
        })

    return JsonResponse({
        "feedbacks": data
    })


@csrf_exempt
@require_POST
def mark_feedback_printed(request, feedback_id):
    token = request.headers.get("X-Print-Token")

    if (
        not settings.PRINT_API_TOKEN
        or token != settings.PRINT_API_TOKEN
    ):
        return JsonResponse(
            {"error": "Unauthorized"},
            status=403,
        )

    try:
        feedback = Feedback.objects.get(
            id=feedback_id
        )
    except Feedback.DoesNotExist:
        return JsonResponse(
            {"error": "Feedback not found"},
            status=404,
        )

    feedback.printed = True
    feedback.save(
        update_fields=["printed"]
    )

    return JsonResponse({
        "success": True
    })

@csrf_exempt
@require_POST
def epson_direct_print(request):
    connection_type = request.POST.get(
        "ConnectionType",
        ""
    )

    printer_id = request.POST.get(
        "ID",
        ""
    )

    if printer_id != "grillking-kitchen":
        return HttpResponse(
            "",
            status=403
        )

    # =====================================
    # Epson 请求新的打印任务
    # =====================================
    if connection_type == "GetRequest":

        retry_before = (
            timezone.now()
            - timedelta(seconds=60)
        )

        order = (
            Order.objects
            .filter(
                status="new",
                direct_printed=False,
            )
            .filter(
                models.Q(
                    direct_print_sent_at__isnull=True
                )
                |
                models.Q(
                    direct_print_sent_at__lte=retry_before
                )
            )
            .order_by("created_at")
            .first()
        )
        print(
            "DIRECT PRINT ORDER:",
            order.id if order else "NONE"
        )
    # 没有新订单
    if not order:
        print("DIRECT PRINT ORDER: NONE")

        xml = (
            '<?xml version="1.0" encoding="utf-8"?>'
            '<PrintRequestInfo Version="2.00">'
            '</PrintRequestInfo>'
        )

        print(
            "DIRECT PRINT XML LENGTH:",
            len(xml)
        )

        return HttpResponse(
            xml,
            content_type="text/xml; charset=utf-8"
        )

        # 记录发送时间，避免瞬间重复
        order.direct_print_sent_at = timezone.now()

        order.save(
            update_fields=[
                "direct_print_sent_at"
            ]
        )

        job_id = f"order-{order.id}"

        print(
           "DIRECT PRINT ORDER:",
            order.id
        )

        print(
            "DIRECT PRINT JOB:",
            job_id
        )

        table_number = str(
            order.table_number
        ).zfill(2)

        order_time = timezone.localtime(
            order.created_at
        ).strftime(
            "%Y-%m-%d  %I:%M %p"
        )

        # =====================================
        # 菜品
        # =====================================
        items_xml = ""

        for item in order.items.select_related(
            "menu_item"
        ).all():

            quantity = item.quantity

            # 有中文名 -> 转图片打印
            if (
                item.menu_item
                and item.menu_item.name_zh
            ):
                kitchen_name = (
                    item.menu_item.name_zh
                )

                item_line = (
                    f"{quantity} × {kitchen_name}"
                )

                items_xml += text_to_epos_image(
                    item_line
                )

                items_xml += (
                    '<feed line="1"/>'
                )

            # 没中文名 -> 继续打印英文
            else:
                kitchen_name = item.name

                safe_name = saxutils.escape(
                    str(kitchen_name)
                )

                items_xml += (
                    '<text width="1" height="2"/>'
                    '<text em="true"/>'
                    f'<text>{quantity} x '
                    f'{safe_name}&#10;</text>'
                )

            # 辣度
            spicy = getattr(
                item,
                "spicy",
                ""
            )

            if (
                spicy
                and spicy != "Not Spicy"
            ):
                safe_spicy = saxutils.escape(
                    str(spicy).upper()
                )

                items_xml += (
                    '<text width="1" height="1"/>'
                    '<text em="true"/>'
                    f'<text>   *** '
                    f'{safe_spicy} ***'
                    '&#10;</text>'
                )

            items_xml += (
                '<feed line="1"/>'
            )

        # =====================================
        # Epson 小票主体
        # =====================================
        print_data = (
            '<epos-print '
            'xmlns="http://www.epson-pos.com/'
            'schemas/2011/03/epos-print">'

            '<text align="center"/>'

            '<text width="2" height="2"/>'
            '<text em="true"/>'
            '<text>GRILL KING&#10;</text>'

            '<feed line="1"/>'

            '<text width="2" height="2"/>'
            f'<text>TABLE '
            f'{table_number}&#10;</text>'

            '<text width="1" height="1"/>'
            '<text em="false"/>'

            f'<text>ORDER #{order.id}&#10;</text>'
            f'<text>{order_time}&#10;</text>'

            '<feed line="1"/>'

            '<text>'
            '--------------------------------'
            '&#10;</text>'

            '<feed line="1"/>'

            '<text align="left"/>'

            + items_xml +

            '<text align="center"/>'

            '<text width="1" height="1"/>'
            '<text em="false"/>'

            '<text>'
            '--------------------------------'
            '&#10;</text>'

            '<text>END ORDER&#10;</text>'

            '<feed line="6"/>'

            '<cut type="feed"/>'

            '</epos-print>'
        )

        # =====================================
        # Server Direct Print XML
        # =====================================
        xml = (
            '<?xml version="1.0" '
            'encoding="utf-8"?>'

            '<PrintRequestInfo '
            'Version="2.00">'

            '<ePOSPrint>'

            '<Parameter>'

            '<devid>'
            'local_printer'
            '</devid>'

            '<timeout>'
            '10000'
            '</timeout>'

            f'<printjobid>'
            f'{job_id}'
            f'</printjobid>'

            '</Parameter>'

            '<PrintData>'

            + print_data +

            '</PrintData>'

            '</ePOSPrint>'

            '</PrintRequestInfo>'
        )

        return HttpResponse(
            xml,
            content_type=(
                "text/xml; charset=utf-8"
            )
        )

    # =====================================
    # Epson 回传打印结果
    # =====================================
    if connection_type == "SetResponse":

        response_file = request.POST.get(
            "ResponseFile",
            ""
        )

        print("EPSON RESPONSE:", response_file)

        if not response_file:
            return HttpResponse("")

        try:
            root = ET.fromstring(
                response_file
            )

            job_id = None
            success = False

            for element in root.iter():

                tag = element.tag.split(
                    "}"
                )[-1]

                if tag == "printjobid":
                    job_id = (
                        element.text or ""
                    )

                if tag == "response":
                    success = (
                        element.attrib.get(
                            "success"
                        )
                        == "true"
                    )

            if (
                job_id
                and job_id.startswith(
                    "order-"
                )
            ):
                order_id = int(
                    job_id.replace(
                        "order-",
                        ""
                    )
                )

                order = (
                    Order.objects
                    .filter(id=order_id)
                    .first()
                )

                if order:
                    if success:
                        order.direct_printed = (
                            True
                        )

                        order.save(
                            update_fields=[
                                "direct_printed"
                            ]
                        )

                    else:
                        order.direct_print_sent_at = (
                            None
                        )

                        order.save(
                            update_fields=[
                                "direct_print_sent_at"
                            ]
                        )

        except Exception as error:
            print(
                "Epson SetResponse error:",
                error
            )

        return HttpResponse("")

    return HttpResponse("")