import json
import base64
from io import BytesIO
import qrcode

from django.http import JsonResponse
from django.shortcuts import render, get_object_or_404
from django.views.decorators.http import require_POST
from django.views.decorators.csrf import ensure_csrf_cookie
from django.utils import timezone

from .models import Category, MenuItem, Order, OrderItem
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

from django.conf import settings


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