from io import BytesIO
from datetime import date
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.db import transaction
from django.utils import timezone
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST, require_http_methods
from django.core.exceptions import ValidationError
from django.views.decorators.cache import never_cache
from accounts.models import Identity
from accounts.views import fail, body
from .models import Listing, Purchase, ListingDetails, SavedListing, ListingReport, Order, OrderMessage, Review, OrderEvent

def image_bytes(upload):
    if upload.size > 5*1024*1024: raise ValueError("Choose an image smaller than 5 MB.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(upload) as source:
                if source.format not in {"JPEG", "PNG", "WEBP"} or source.width*source.height>16000000:
                    raise ValueError("Use a JPG, PNG or WebP under 16 megapixels.")
                source.load()
                image=ImageOps.exif_transpose(source).convert("RGB")
                image.thumbnail((1600,1600))
                output=BytesIO();image.save(output,"JPEG",quality=88)
                return output.getvalue()
    except (OSError, UnidentifiedImageError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValueError("This image cannot be read.")

def owner(user, listing):
    return user.is_authenticated and (listing.owner_account_id==user.pk or Identity.objects.filter(user=user,provider="phantom",subject=listing.seller_wallet).exists())

def details_data(request, listing):
    d=ListingDetails.objects.filter(listing=listing).first()
    result={key:getattr(d,key,"") or "" for key in ["description","location","dimensions","audience","terms"]}
    result.update({"available_from":str(d.available_from) if d and d.available_from else "", "available_until":str(d.available_until) if d and d.available_until else "", "photo":f"/api/listings/{listing.pk}/photo/" if d and d.photo else None,
        "isOwner":owner(request.user,listing),"saved":request.user.is_authenticated and SavedListing.objects.filter(user=request.user,listing=listing).exists()})
    result["reviews"]=[{"id":r.pk,"name":r.author.first_name or "AdMint member","rating":r.rating,"text":r.text} for r in Review.objects.filter(order__purchase__listing__owner_account=listing.owner_account).select_related("author").order_by("-id")[:30]] if listing.owner_account_id else []
    return result

@require_http_methods(["GET","POST"])
@transaction.atomic
def details(request, listing_id):
    queryset = Listing.objects.select_for_update() if request.method == "POST" else Listing.objects.all()
    listing=get_object_or_404(queryset,pk=listing_id,deleted_at__isnull=True)
    if request.method=="POST":
        if not owner(request.user,listing):return fail("Only the seller can edit this surface.",403)
        if listing.status!="available":return fail("Details cannot change after a surface is reserved or sold.",409)
        values={}
        for key,limit in [("description",3000),("location",160),("dimensions",160),("audience",240),("terms",2000)]:
            values[key]=request.POST.get(key,"").strip()
            if len(values[key])>limit:return fail(f"{key} is too long.")
        try:
            for key in ["available_from","available_until"]:values[key]=date.fromisoformat(request.POST[key]) if request.POST.get(key) else None
            if values["available_from"] and values["available_until"] and values["available_until"]<values["available_from"]:raise ValueError("End date must follow the start date.")
            if request.FILES.get("photo"):values["photo"]=image_bytes(request.FILES["photo"])
        except ValueError as e:return fail(str(e))
        ListingDetails.objects.update_or_create(listing=listing,defaults=values)
    return JsonResponse(details_data(request,listing))

@require_GET
def photo(request, listing_id):
    item=get_object_or_404(ListingDetails,listing_id=listing_id,listing__deleted_at__isnull=True)
    if not item.photo:return HttpResponse(status=404)
    response=HttpResponse(bytes(item.photo),content_type="image/jpeg");response["X-Content-Type-Options"]="nosniff"
    return response

@require_POST
def save_listing(request,listing_id):
    if not request.user.is_authenticated:return fail("Log in to save a surface.",401)
    listing=get_object_or_404(Listing,pk=listing_id,deleted_at__isnull=True)
    try:data=body(request)
    except ValidationError:return fail("Invalid request.")
    if type(data.get("saved")) is not bool:return fail("Choose save or unsave.")
    if data["saved"]:SavedListing.objects.get_or_create(user=request.user,listing=listing)
    else:SavedListing.objects.filter(user=request.user,listing=listing).delete()
    return JsonResponse({"saved":data["saved"]})

@require_GET
def saved(request):
    if not request.user.is_authenticated:return fail("Log in to view saved surfaces.",401)
    return JsonResponse({"ids":list(SavedListing.objects.filter(user=request.user,listing__deleted_at__isnull=True).values_list("listing_id",flat=True))})

@require_POST
def report(request,listing_id):
    if not request.user.is_authenticated:return fail("Log in to report a surface.",401)
    listing=get_object_or_404(Listing,pk=listing_id,deleted_at__isnull=True)
    try:data=body(request)
    except ValidationError:return fail("Invalid request.")
    reason=data.get("reason","")
    if not isinstance(reason,str) or not 10<=len(reason.strip())<=1000:return fail("Explain the issue in 10–1000 characters.")
    ListingReport.objects.update_or_create(user=request.user,listing=listing,resolved=False,defaults={"reason":reason.strip()})
    return JsonResponse({"ok":True})

def participant(user,purchase):
    if not user.is_authenticated:return None
    if owner(user,purchase.listing):return "seller"
    if Identity.objects.filter(user=user,provider="phantom",subject=purchase.buyer_wallet).exists():return "buyer"
    return None

def order_data(request,order):
    p=order.purchase
    return {"id":p.pk,"listingId":p.listing_id,"title":p.listing.title,"price":str(p.price_sol.normalize()),"role":participant(request.user,p),"status":order.status,"brief":order.brief,"issue":order.issue,"resolution":order.resolution,
        "creative":f"/api/orders/{p.pk}/file/creative/" if order.creative else None,"proof":f"/api/orders/{p.pk}/file/proof/" if order.proof else None,"reviewed":Review.objects.filter(order=order).exists(),
        "messages":[{"id":m.pk,"text":m.text,"mine":m.sender_id==request.user.pk,"name":m.sender.first_name or "AdMint member","createdAt":m.created_at.isoformat()} for m in order.messages.select_related("sender").order_by("-id")[:100]][::-1]}

@require_GET
@never_cache
def orders(request):
    if not request.user.is_authenticated:return fail("Log in to view orders.",401)
    wallets=Identity.objects.filter(user=request.user,provider="phantom").values_list("subject",flat=True)
    purchases=Purchase.objects.filter(status="confirmed").filter(Q(listing__owner_account=request.user)|Q(seller_wallet__in=wallets)|Q(buyer_wallet__in=wallets)).select_related("listing")
    return JsonResponse({"results":[{"id":p.pk,"title":p.listing.title,"role":participant(request.user,p),"status":getattr(getattr(p,"order",None),"status","awaiting_creative"),"price":str(p.price_sol.normalize())} for p in purchases[:100]]})

@require_http_methods(["GET","POST"])
@never_cache
def order_detail(request,purchase_id):
    if not request.user.is_authenticated:return fail("Log in to view this order.",401)
    p=get_object_or_404(Purchase.objects.select_related("listing"),pk=purchase_id,status="confirmed")
    role=participant(request.user,p)
    if not role:return fail("This order is private.",403)
    # Creation owns its short atomic insert; an outer read transaction would
    # make concurrent first visits attempt conflicting SQLite lock upgrades.
    order,_=Order.objects.get_or_create(purchase=p)
    if request.method=="GET":
        return JsonResponse(order_data(request,order))
    with transaction.atomic():
        order=Order.objects.select_for_update().get(pk=order.pk)
        if request.method=="POST":
            action=request.POST.get("action","")
            previous_status=order.status
            try:
                if action=="creative":
                    if role!="buyer" or order.status not in {"awaiting_creative","creative_submitted"}:return fail("Creative cannot be changed at this stage.",409)
                    brief=request.POST.get("brief","").strip()
                    if not 1<=len(brief)<=3000:return fail("Add a brief up to 3000 characters.")
                    if request.FILES.get("file"):order.creative=image_bytes(request.FILES["file"])
                    order.brief=brief;order.status="creative_submitted"
                elif action=="accept":
                    if role!="seller" or order.status!="creative_submitted":return fail("This action is not available.",409)
                    order.status="in_progress"
                elif action=="deliver":
                    if role!="seller" or order.status!="in_progress":return fail("This action is not available.",409)
                    if not request.FILES.get("file"):return fail("Upload a photo proving delivery.")
                    order.proof=image_bytes(request.FILES["file"]);order.status="delivered"
                elif action=="complete":
                    if role!="buyer" or order.status!="delivered":return fail("This action is not available.",409)
                    order.status="completed"
                elif action in {"dispute","refund_request"}:
                    if order.status in {"disputed","refund_requested"}:return fail("An issue is already open.",409)
                    if action=="refund_request" and role!="buyer":return fail("Only the buyer can request a refund.",403)
                    issue=request.POST.get("issue","").strip()
                    if not 10<=len(issue)<=2000:return fail("Describe the issue in 10–2000 characters.")
                    order.paused_status=order.status;order.resolution=""
                    order.issue=issue;order.status="disputed" if action=="dispute" else "refund_requested"
                else:return fail("Unknown action.")
            except ValueError as e:return fail(str(e))
            order.save()
            OrderEvent.objects.create(order=order,actor=request.user,action=action,previous_status=previous_status,status=order.status,note=order.issue if action in {"dispute","refund_request"} else "")
    return JsonResponse(order_data(request,order))

@require_GET
@never_cache
def order_file(request,purchase_id,kind):
    if not request.user.is_authenticated:return fail("Log in to view this file.",401)
    order=get_object_or_404(Order.objects.select_related("purchase__listing"),purchase_id=purchase_id, purchase__status="confirmed")
    if not participant(request.user,order.purchase):return fail("This file is private.",403)
    if kind not in {"creative","proof"}:return HttpResponse(status=404)
    content=getattr(order,kind)
    if not content:return HttpResponse(status=404)
    response=HttpResponse(bytes(content),content_type="image/jpeg");response["Cache-Control"]="private, no-store";response["X-Content-Type-Options"]="nosniff"
    return response

@require_POST
def message(request,purchase_id):
    if not request.user.is_authenticated:return fail("Log in to send a message.",401)
    p=get_object_or_404(Purchase.objects.select_related("listing"),pk=purchase_id,status="confirmed")
    if not participant(request.user,p):return fail("This conversation is private.",403)
    try:data=body(request)
    except ValidationError:return fail("Invalid request.")
    text=data.get("text","")
    if not isinstance(text,str) or not 1<=len(text.strip())<=2000:return fail("Use 1–2000 characters.")
    from django.core.cache import cache
    key=f"chat:{request.user.pk}";cache.add(key,0,60)
    if cache.incr(key)>30:return fail("Please wait before sending another message.",429)
    order,_=Order.objects.get_or_create(purchase=p)
    OrderMessage.objects.create(order=order,sender=request.user,text=text.strip())
    return JsonResponse({"ok":True})

@require_POST
def review(request,purchase_id):
    if not request.user.is_authenticated:return fail("Log in to leave a review.",401)
    order=get_object_or_404(Order.objects.select_related("purchase__listing"),purchase_id=purchase_id, purchase__status="confirmed")
    if participant(request.user,order.purchase)!="buyer":return fail("Only the buyer can review this order.",403)
    if order.status!="completed":return fail("Complete the order before reviewing it.",409)
    try:data=body(request)
    except ValidationError:return fail("Invalid request.")
    rating=data.get("rating");text=data.get("text","")
    if type(rating) is not int or not 1<=rating<=5 or not isinstance(text,str) or len(text)>1000:return fail("Choose 1–5 stars and up to 1000 characters.")
    _,created=Review.objects.get_or_create(order=order,defaults={"author":request.user,"rating":rating,"text":text.strip()})
    if not created:return fail("This order already has a review.",409)
    return JsonResponse({"ok":True})

@require_POST
@transaction.atomic
def delete_listing(request, listing_id):
    if not request.user.is_authenticated:
        return fail("Log in to delete your listing.", 401)
    listing = get_object_or_404(Listing.objects.select_for_update(), pk=listing_id)
    if not owner(request.user, listing):
        return fail("Only the seller can delete this listing.", 403)
    if listing.deleted_at:
        return JsonResponse({"ok": True})
    if listing.status != Listing.Status.AVAILABLE or listing.purchases.filter(status__in=[Purchase.Status.PENDING, Purchase.Status.CONFIRMED]).exists():
        return fail("A listing with an active purchase or completed sale cannot be deleted.", 409)
    listing.deleted_at = timezone.now()
    listing.save(update_fields=["deleted_at", "updated_at"])
    return JsonResponse({"ok": True})
