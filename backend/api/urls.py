from django.urls import path

from . import views, commerce

urlpatterns = [
    path("listings/<int:listing_id>/delete/", commerce.delete_listing),
    path("listings/<int:listing_id>/details/", commerce.details),
    path("listings/<int:listing_id>/photo/", commerce.photo),
    path("listings/<int:listing_id>/save/", commerce.save_listing),
    path("listings/<int:listing_id>/report/", commerce.report),
    path("saved/", commerce.saved),
    path("orders/", commerce.orders),
    path("orders/<int:purchase_id>/", commerce.order_detail),
    path("orders/<int:purchase_id>/file/<str:kind>/", commerce.order_file),
    path("orders/<int:purchase_id>/messages/", commerce.message),
    path("orders/<int:purchase_id>/review/", commerce.review),
    path("health/", views.health, name="health"),
    path("ready/", views.readiness, name="readiness"),
    path("listings/", views.listings, name="listings"),
    path("listings/<int:listing_id>/", views.listing_detail, name="listing-detail"),
    path("purchases/", views.purchases, name="purchases"),
    path("purchases/prepare/", views.prepare_purchase, name="purchase-prepare"),
    path("purchases/<int:purchase_id>/confirm/", views.confirm_purchase, name="purchase-confirm"),
    path("purchases/<int:purchase_id>/cancel/", views.cancel_purchase, name="purchase-cancel"),
    path("ad-rights/", views.ad_rights, name="ad-rights"),
]
