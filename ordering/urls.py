from django.urls import path
from . import views

urlpatterns = [
    path('', views.menu, name='menu'),
    path("kitchen/login/", views.kitchen_login, name="kitchen_login"),
    path('table/<int:table_number>/', views.menu, name='table_menu'),
    path("print-test/", views.print_test, name="print_test"),
    path('place-order/', views.place_order, name='place_order'),
    path('qr-codes/', views.qr_codes, name='qr_codes'),
    path("kitchen/", views.kitchen, name="kitchen"),
    path("kitchen/orders/", views.kitchen_orders, name="kitchen_orders"),
    path(
        "kitchen/order/<int:order_id>/status/",
         views.update_order_status,
         name="update_order_status"
     ),
]
