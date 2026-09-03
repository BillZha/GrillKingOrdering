from django.urls import path
from . import views

urlpatterns = [
    path('', views.menu, name='menu'),
    path('table/<int:table_number>/', views.menu, name='table_menu'),
    path('place-order/', views.place_order, name='place_order'),
    path('qr-codes/', views.qr_codes, name='qr_codes'),
]
