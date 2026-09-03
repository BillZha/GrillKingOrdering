import json
import base64
from io import BytesIO
import qrcode

from django.http import JsonResponse
from django.shortcuts import render
from django.views.decorators.http import require_POST

from .models import Category, MenuItem, Order, OrderItem


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

def qr_codes(request):
    tables = []

    for table_number in range(1, 21):

        url = request.build_absolute_uri(
            f'/table/{table_number}/'
        )

        qr = qrcode.make(url)

        buffer = BytesIO()
        qr.save(buffer, format='PNG')

        image_base64 = base64.b64encode(
            buffer.getvalue()
        ).decode('utf-8')

        tables.append({
            'number': table_number,
            'url': url,
            'qr': image_base64,
        })

    return render(request, 'ordering/qr_codes.html', {
        'tables': tables
    })