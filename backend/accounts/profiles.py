from io import BytesIO
import warnings
from PIL import Image, ImageOps, UnidentifiedImageError
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q
from django.http import JsonResponse, HttpResponse
from django.shortcuts import get_object_or_404
from django.views.decorators.http import require_GET, require_POST
from .models import Profile, Follow, Identity
from .views import body, fail
from api.models import Listing, Purchase

User = get_user_model()

def card(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return {"id": user.pk, "name": profile.display_name or user.first_name or "AdMint member",
            "avatar": f"/api/profiles/{user.pk}/avatar/?v={profile.updated_at.timestamp()}" if profile.avatar else None}

def surface(item):
    return {"id": item.pk, "title": item.title, "emoji": item.emoji, "type": item.surface_type,
            "price": str(item.price_sol.normalize()), "status": item.status, "duration": item.duration}

@require_GET
def detail(request, user_id):
    user = get_object_or_404(User, pk=user_id, is_active=True)
    result = card(user)
    profile = user.profile
    wallets = list(user.identities.filter(provider="phantom").values_list("subject", flat=True))
    purchases = Purchase.objects.filter(status=Purchase.Status.CONFIRMED).select_related("listing")
    sold = purchases.filter(seller_wallet__in=wallets)
    bought = purchases.filter(buyer_wallet__in=wallets)
    listings = Listing.objects.filter(seller_wallet__in=wallets, deleted_at__isnull=True)
    def history(query):
        return [{**surface(p.listing), "purchaseId": p.pk, "price": str(p.price_sol.normalize()),
                 "date": p.confirmed_at.isoformat() if p.confirmed_at else p.created_at.isoformat()} for p in query[:50]]
    result.update({"bio": profile.bio, "joined": user.date_joined.isoformat(), "wallets": wallets,
        "isOwner": request.user.is_authenticated and request.user.pk == user.pk,
        "isFollowing": request.user.is_authenticated and Follow.objects.filter(follower=request.user, following=user).exists(),
        "counts": {"sold": sold.count(), "bought": bought.count(), "listings": listings.count(),
                   "followers": user.follower_links.count(), "following": user.following_links.count()},
        "sold": history(sold), "bought": history(bought), "listings": [surface(s) for s in listings[:50]],
        "followers": [card(link.follower) for link in user.follower_links.select_related("follower").order_by("-created_at")[:50]],
        "following": [card(link.following) for link in user.following_links.select_related("following").order_by("-created_at")[:50]],
    })
    return JsonResponse(result)

@require_GET
def wallet_profile(request, address):
    identity = get_object_or_404(Identity, provider="phantom", subject=address, user__is_active=True)
    return JsonResponse({"id": identity.user_id})

@require_GET
def avatar(request, user_id):
    profile = get_object_or_404(Profile, user_id=user_id, user__is_active=True)
    if not profile.avatar: return HttpResponse(status=404)
    response = HttpResponse(bytes(profile.avatar), content_type="image/jpeg")
    response["X-Content-Type-Options"] = "nosniff"
    response["Cache-Control"] = "private, max-age=300"
    return response

@require_POST
def update(request):
    if not request.user.is_authenticated: return fail("Log in to edit your profile.", 401)
    name = request.POST.get("name", "").strip()
    bio = request.POST.get("bio", "").strip()
    if not name or len(name) > 80 or len(bio) > 300: return fail("Use a name up to 80 characters and a bio up to 300 characters.")
    image_bytes = None
    image = request.FILES.get("avatar")
    if image:
        if image.size > 5 * 1024 * 1024: return fail("Choose an image smaller than 5 MB.")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", Image.DecompressionBombWarning)
                with Image.open(image) as original:
                    if original.format not in {"JPEG", "PNG", "WEBP"} or original.width * original.height > 16000000:
                        return fail("Use a JPG, PNG or WebP image under 16 megapixels.")
                    original.load()
                    photo = ImageOps.fit(ImageOps.exif_transpose(original).convert("RGB"), (512, 512))
                    output = BytesIO()
                    photo.save(output, "JPEG", quality=88)
                    image_bytes = output.getvalue()
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            return fail("This image could not be read. Choose a valid JPG, PNG or WebP file.")
    with transaction.atomic():
        profile, _ = Profile.objects.get_or_create(user=request.user)
        profile.display_name, profile.bio = name, bio
        if image_bytes is not None: profile.avatar = image_bytes
        if request.POST.get("removeAvatar") == "true": profile.avatar = None
        profile.save()
    return JsonResponse({"ok": True})

@require_POST
def follow(request, user_id):
    if not request.user.is_authenticated: return fail("Log in to follow this member.", 401)
    target = get_object_or_404(User, pk=user_id, is_active=True)
    if target.pk == request.user.pk: return fail("You cannot follow yourself.")
    try:
        data = body(request)
    except ValidationError: return fail("Invalid follow request.")
    if not isinstance(data.get("following"), bool): return fail("Choose follow or unfollow.")
    if data["following"]:
        Follow.objects.get_or_create(follower=request.user, following=target)
    else:
        Follow.objects.filter(follower=request.user, following=target).delete()
    return JsonResponse({"following": data["following"], "followers": target.follower_links.count()})

@require_GET
def search(request):
    query = request.GET.get("q", "").strip()[:100]
    if len(query) < 2:
        return JsonResponse({"results": []})
    users = User.objects.filter(is_active=True).filter(
        Q(profile__display_name__icontains=query) |
        (Q(profile__display_name="") | Q(profile__isnull=True)) & Q(first_name__icontains=query) |
        Q(identities__provider="phantom", identities__subject__icontains=query)
    ).distinct().order_by("id")[:20]
    results = []
    for user in users:
        profile = Profile.objects.filter(user=user).first()
        results.append({"id": user.pk, "name": (profile.display_name if profile else "") or user.first_name or "AdMint member",
            "avatar": f"/api/profiles/{user.pk}/avatar/?v={profile.updated_at.timestamp()}" if profile and profile.avatar else None})
    return JsonResponse({"results": results})
