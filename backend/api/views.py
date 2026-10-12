from datetime import timedelta

from functools import wraps
from django.db import transaction, IntegrityError, connection
from django.core.cache import cache
from django.conf import settings
from django.shortcuts import get_object_or_404
from django.views.decorators.cache import never_cache
from django.http import JsonResponse
from django.utils import timezone
from rest_framework import status
from rest_framework.decorators import api_view, authentication_classes
from rest_framework.response import Response

from .models import AdRight, Listing, Purchase, WalletProfile
from .serializers import (
    AdRightSerializer,
    ListingSerializer,
    PurchaseConfirmSerializer,
    PurchasePrepareSerializer,
    PurchaseSerializer,
)
from .solana import verify_purchase_transaction
from accounts.models import Identity, Follow, Notification

def wallet_access(request, wallet):
    if not request.user.is_authenticated:
        return Response({"detail": "Log in and verify your Phantom wallet first."}, status=401)
    if not Identity.objects.filter(user=request.user, provider="phantom", subject=wallet).exists():
        return Response({"detail": "Verify this Phantom wallet on your account page first."}, status=403)
    return None


def is_own_surface(user, listing):
    return listing.owner_account_id == user.pk or Identity.objects.filter(
        user=user, provider="phantom", subject=listing.seller_wallet
    ).exists()


def purchase_conflict(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        try:
            return view(*args, **kwargs)
        except IntegrityError:
            return Response({"detail": "This transaction or Ad Right is already assigned to a purchase."}, status=409)
    return wrapped


def _release_expired_reservations():
    Listing.objects.filter(
        status=Listing.Status.RESERVED,
        reserved_until__lte=timezone.now(),
    ).exclude(pk__in=Purchase.objects.filter(status=Purchase.Status.PENDING, tx_signature__isnull=False).values("listing_id")).update(
        status=Listing.Status.AVAILABLE,
        reserved_by="",
        reserved_until=None,
        updated_at=timezone.now(),
    )


@api_view(["GET"])
def health(request):
    return JsonResponse({"ok": True, "service": "AdMint API"})


@api_view(["GET"])
@authentication_classes([])
@never_cache
def readiness(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            cursor.fetchone()
        cache.get("admint:readiness")
    except Exception:
        return JsonResponse({"ok": False, "service": "AdMint API"}, status=503)
    return JsonResponse({"ok": True, "service": "AdMint API"})


@api_view(["GET", "POST"])
def listings(request):
    if request.method == "GET":
        _release_expired_reservations()
        queryset = Listing.objects.select_related("details").filter(deleted_at__isnull=True)
        surface_type = request.query_params.get("type")
        if surface_type in {Listing.SurfaceType.PHYSICAL, Listing.SurfaceType.DIGITAL}:
            queryset = queryset.filter(surface_type=surface_type)
        return Response(ListingSerializer(queryset, many=True).data)

    serializer = ListingSerializer(data=request.data, context={"request": request})
    serializer.is_valid(raise_exception=True)
    denied = wallet_access(request, serializer.validated_data["seller_wallet"].strip())
    if denied is not None: return denied
    photo = None
    if request.FILES.get("photo"):
        from .commerce import image_bytes
        try:
            photo = image_bytes(request.FILES["photo"])
        except ValueError as error:
            return Response({"detail": str(error)}, status=400)
    with transaction.atomic():
        listing = serializer.save(owner_account=request.user)
        if photo is not None:
            from .models import ListingDetails
            ListingDetails.objects.create(listing=listing, photo=photo)
        Notification.objects.bulk_create([
            Notification(recipient_id=follower_id, listing=listing)
            for follower_id in Follow.objects.filter(following=request.user).exclude(follower=request.user).values_list("follower_id", flat=True)
        ])
    return Response(ListingSerializer(listing).data, status=status.HTTP_201_CREATED)


@api_view(["GET"])
def listing_detail(request, listing_id: int):
    _release_expired_reservations()
    try:
        listing = Listing.objects.get(pk=listing_id, deleted_at__isnull=True)
    except Listing.DoesNotExist:
        return Response({"detail": "Listing not found."}, status=status.HTTP_404_NOT_FOUND)
    return Response(ListingSerializer(listing).data)


@api_view(["POST"])
def prepare_purchase(request):
    serializer = PurchasePrepareSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    listing_id = serializer.validated_data["listing_id"]
    buyer_wallet = serializer.validated_data["buyer_wallet"].strip()
    denied = wallet_access(request, buyer_wallet)
    if denied is not None: return denied

    with transaction.atomic():
        _release_expired_reservations()
        listing = get_object_or_404(Listing.objects.select_for_update(), pk=listing_id, deleted_at__isnull=True)

        demo_wallet = getattr(settings, "DEMO_VIDEO_SELLER_WALLET", "")
        if demo_wallet and listing.seller_wallet == demo_wallet and serializer.validated_data["cluster"] != "devnet":
            return Response({"detail": "Video demo listings can only be purchased on Devnet with test SOL."}, status=400)

        if listing.seller_wallet == buyer_wallet or is_own_surface(request.user, listing):
            return Response(
                {"detail": "You cannot buy a surface owned by your account, even with another wallet."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        if listing.status != Listing.Status.AVAILABLE:
            return Response(
                {"detail": "This surface is no longer available."},
                status=status.HTTP_409_CONFLICT,
            )

        WalletProfile.objects.get_or_create(wallet_address=buyer_wallet)
        purchase = Purchase.objects.create(
            listing=listing,
            buyer_wallet=buyer_wallet,
            seller_wallet=listing.seller_wallet,
            price_sol=listing.price_sol,
            cluster=serializer.validated_data["cluster"],
            verification_version=2,
        )
        listing.status = Listing.Status.RESERVED
        listing.reserved_by = buyer_wallet
        listing.reserved_until = timezone.now() + timedelta(minutes=5)
        listing.save(
            update_fields=[
                "status",
                "reserved_by",
                "reserved_until",
                "updated_at",
            ]
        )

    return Response(PurchaseSerializer(purchase).data, status=status.HTTP_201_CREATED)


@api_view(["POST"])
@purchase_conflict
def confirm_purchase(request, purchase_id: int):
    serializer = PurchaseConfirmSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    tx_signature = serializer.validated_data["tx_signature"].strip()
    mint_address = serializer.validated_data["mint_address"].strip()
    cluster = serializer.validated_data["cluster"]

    with transaction.atomic():
        try:
            purchase = Purchase.objects.select_for_update().select_related("listing").get(
                pk=purchase_id
            )
        except Purchase.DoesNotExist:
            return Response(
                {"detail": "Purchase not found."}, status=status.HTTP_404_NOT_FOUND
            )

        denied = wallet_access(request, purchase.buyer_wallet)
        if denied is not None: return denied
        if is_own_surface(request.user, purchase.listing):
            return Response(
                {"detail": "You cannot buy a surface owned by your account, even with another wallet."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if purchase.status == Purchase.Status.CONFIRMED:
            return Response(PurchaseSerializer(purchase).data)

        if cluster != purchase.cluster:
            return Response({"detail": "Use the Solana network selected when this purchase was prepared."}, status=400)
        if purchase.status != Purchase.Status.PENDING:
            return Response({"detail": "This purchase is no longer pending."}, status=409)
        if Purchase.objects.filter(listing_id=purchase.listing_id, pk__gt=purchase.pk).exists():
            return Response({"detail": "A newer purchase already exists for this surface."}, status=409)
        if Purchase.objects.filter(tx_signature=tx_signature).exclude(pk=purchase.pk).exists() or AdRight.objects.filter(mint_address=mint_address).exists():
            return Response({"detail": "This transaction or Ad Right is already assigned to a purchase."}, status=409)
        if purchase.tx_signature and purchase.tx_signature != tx_signature:
            return Response({"detail": "Retry using the original transaction signature."}, status=409)

        listing = Listing.objects.select_for_update().get(pk=purchase.listing_id)

        if listing.status not in {
            Listing.Status.RESERVED,
            Listing.Status.AVAILABLE,
        }:
            return Response(
                {"detail": "Listing is no longer available for confirmation."},
                status=status.HTTP_409_CONFLICT,
            )

        if listing.reserved_by and listing.reserved_by != purchase.buyer_wallet:
            return Response(
                {"detail": "Listing is reserved by another buyer."},
                status=status.HTTP_409_CONFLICT,
            )

        verification = verify_purchase_transaction(
            signature=tx_signature,
            cluster=cluster,
            buyer_wallet=purchase.buyer_wallet,
            seller_wallet=purchase.seller_wallet,
            price_sol=purchase.price_sol,
            mint_address=mint_address,
            not_before=purchase.created_at if purchase.verification_version == 1 else None,
            purchase_id=purchase.pk if purchase.verification_version >= 2 else None,
        )
        if not verification["confirmed"] and verification.get("retryable"):
            purchase.tx_signature = tx_signature
            purchase.mint_address = mint_address
            purchase.verification_message = verification["message"][:240]
            purchase.save(update_fields=["tx_signature", "mint_address", "verification_message"])
            listing.status = Listing.Status.RESERVED
            listing.reserved_by = purchase.buyer_wallet
            listing.save(update_fields=["status", "reserved_by", "updated_at"])
            return Response({"detail": verification["message"]}, status=503)
        if not verification["confirmed"]:
            purchase.status = Purchase.Status.FAILED
            purchase.verification_message = verification["message"][:240]
            purchase.tx_signature = tx_signature
            purchase.save(
                update_fields=[
                    "status",
                    "verification_message",
                    "tx_signature",
                ]
            )
            listing.status = Listing.Status.AVAILABLE
            listing.reserved_by = ""
            listing.reserved_until = None
            listing.save(
                update_fields=[
                    "status",
                    "reserved_by",
                    "reserved_until",
                    "updated_at",
                ]
            )
            return Response(
                {"detail": verification["message"]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        purchase.status = Purchase.Status.CONFIRMED
        purchase.tx_signature = tx_signature
        purchase.mint_address = mint_address
        purchase.verification_message = verification["message"][:240]
        purchase.confirmed_at = timezone.now()
        purchase.save(
            update_fields=[
                "status",
                "tx_signature",
                "mint_address",
                "verification_message",
                "confirmed_at",
            ]
        )

        listing.status = Listing.Status.SOLD
        listing.buyer_wallet = purchase.buyer_wallet
        listing.tx_signature = tx_signature
        listing.mint_address = mint_address
        listing.reserved_by = ""
        listing.reserved_until = None
        listing.save(
            update_fields=[
                "status",
                "buyer_wallet",
                "tx_signature",
                "mint_address",
                "reserved_by",
                "reserved_until",
                "updated_at",
            ]
        )

        ad_right, _ = AdRight.objects.get_or_create(
            listing=listing,
            defaults={
                "purchase": purchase,
                "owner_wallet": purchase.buyer_wallet,
                "mint_address": mint_address,
                "transaction_signature": tx_signature,
            },
        )
        if ad_right.purchase_id != purchase.id:
            ad_right.purchase = purchase
            ad_right.owner_wallet = purchase.buyer_wallet
            ad_right.mint_address = mint_address
            ad_right.transaction_signature = tx_signature
            ad_right.save()

    return Response(PurchaseSerializer(purchase).data)


@api_view(["POST"])
def cancel_purchase(request, purchase_id: int):
    with transaction.atomic():
        try:
            purchase = Purchase.objects.select_for_update().select_related("listing").get(
                pk=purchase_id
            )
        except Purchase.DoesNotExist:
            return Response(
                {"detail": "Purchase not found."}, status=status.HTTP_404_NOT_FOUND
            )

        denied = wallet_access(request, purchase.buyer_wallet)
        if denied is not None: return denied
        if purchase.status != Purchase.Status.PENDING:
            return Response(PurchaseSerializer(purchase).data)

        if purchase.tx_signature:
            return Response({"detail": "A transaction was submitted. Retry confirmation before cancelling."}, status=409)
        listing = Listing.objects.select_for_update().get(pk=purchase.listing_id)
        latest_purchase = not Purchase.objects.filter(listing_id=purchase.listing_id, pk__gt=purchase.pk).exists()
        purchase.status = Purchase.Status.CANCELLED
        purchase.save(update_fields=["status"])
        if latest_purchase and listing.status == Listing.Status.RESERVED and listing.reserved_by == purchase.buyer_wallet:
            listing.status = Listing.Status.AVAILABLE
            listing.reserved_by = ""
            listing.reserved_until = None
            listing.save(
                update_fields=[
                    "status",
                    "reserved_by",
                    "reserved_until",
                    "updated_at",
                ]
            )

    return Response(PurchaseSerializer(purchase).data)


@api_view(["GET"])
@never_cache
def purchases(request):
    wallet = request.query_params.get("wallet", "").strip()
    denied = wallet_access(request, wallet)
    if denied is not None: return denied
    queryset = Purchase.objects.select_related("listing")
    if wallet:
        queryset = queryset.filter(buyer_wallet=wallet)
    return Response(PurchaseSerializer(queryset, many=True).data)


@api_view(["GET"])
@never_cache
def ad_rights(request):
    wallet = request.query_params.get("wallet", "").strip()
    denied = wallet_access(request, wallet)
    if denied is not None: return denied
    queryset = AdRight.objects.select_related("listing")
    if wallet:
        queryset = queryset.filter(owner_wallet=wallet)
    return Response(AdRightSerializer(queryset, many=True).data)
