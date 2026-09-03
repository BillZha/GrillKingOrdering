from django.contrib import admin
from .models import Category, MenuItem, Order, OrderItem


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'sort_order',
    )

    ordering = (
        'sort_order',
    )


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    list_display = (
        'name',
        'category',
        'price',
        'is_popular',
        'is_sold_out',
        'is_active',
    )

    list_filter = (
        'category',
        'is_popular',
        'is_sold_out',
        'is_active',
    )

    search_fields = (
        'name',
        'description',
    )


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0

    readonly_fields = (
        'name',
        'price',
        'quantity',
        'spicy',
    )


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'table_number',
        'total_amount',
        'status',
        'created_at',
    )

    list_filter = (
        'status',
        'created_at',
    )

    ordering = (
        '-created_at',
    )

    inlines = [
        OrderItemInline,
    ]


@admin.register(OrderItem)
class OrderItemAdmin(admin.ModelAdmin):
    list_display = (
        'order',
        'name',
        'quantity',
        'price',
        'spicy',
    )