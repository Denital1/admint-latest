from django.contrib import admin

from .models import AdRight, Listing, Purchase, WalletProfile


@admin.register(WalletProfile)
class WalletProfileAdmin(admin.ModelAdmin):
    list_display = ("wallet_address", "display_name", "created_at")
    search_fields = ("wallet_address", "display_name")


@admin.register(Listing)
class ListingAdmin(admin.ModelAdmin):
    list_display = ("id", "title", "surface_type", "price_sol", "status", "seller_wallet", "created_at")
    list_filter = ("surface_type", "status")
    search_fields = ("title", "seller_wallet", "buyer_wallet")


@admin.register(Purchase)
class PurchaseAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "buyer_wallet", "price_sol", "status", "created_at", "confirmed_at")
    list_filter = ("status",)
    search_fields = ("buyer_wallet", "seller_wallet", "tx_signature", "mint_address")


@admin.register(AdRight)
class AdRightAdmin(admin.ModelAdmin):
    list_display = ("id", "listing", "owner_wallet", "mint_address", "acquired_at")
    search_fields = ("owner_wallet", "mint_address", "transaction_signature")

from .models import ListingReport, Order, OrderMessage, Review, ListingDetails, OrderEvent
@admin.register(ListingReport)
class ReportAdmin(admin.ModelAdmin):
    list_display=("id","listing","user","resolved","created_at")
    list_filter=("resolved",)
class EventInline(admin.TabularInline):
    model=OrderEvent
    extra=0
    readonly_fields=("actor","action","previous_status","status","note","created_at")
    can_delete=False
    def has_add_permission(self,request,obj=None):return False

@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display=("id","purchase","status","updated_at")
    list_filter=("status",)
    readonly_fields=("purchase","status","brief","creative","proof","issue","paused_status")
    inlines=(EventInline,)
    actions=("resolve_issue",)
    @admin.action(description="Resolve documented issue and resume order (no money transfer)")
    def resolve_issue(self,request,queryset):
        from django.db import transaction
        count=0
        with transaction.atomic():
            for order in queryset.select_for_update().filter(status__in=["disputed","refund_requested"]):
                if not order.resolution.strip():continue
                previous=order.status
                order.status=order.paused_status or ("delivered" if order.proof else "creative_submitted" if order.brief else "awaiting_creative")
                order.save()
                OrderEvent.objects.create(order=order,actor=request.user,action="issue_resolved",previous_status=previous,status=order.status,note=order.resolution)
                count+=1
        self.message_user(request,f"Resumed {count} orders with resolution notes. No funds were transferred.")
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
admin.site.register(Review)
