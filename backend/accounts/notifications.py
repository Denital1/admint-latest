from django.http import JsonResponse
from django.views.decorators.http import require_GET, require_POST
from django.utils import timezone
from django.core.exceptions import ValidationError
from .models import Notification
from .views import body, fail

@require_GET
def inbox(request):
    if not request.user.is_authenticated: return fail("Log in to see notifications.", 401)
    items = Notification.objects.filter(recipient=request.user, listing__deleted_at__isnull=True)
    try: before = int(request.GET.get("before", "0"))
    except ValueError: return fail("Invalid cursor.")
    page = items.filter(id__lt=before) if before else items
    page = list(page.select_related("listing__owner_account", "listing__owner_account__profile")[:31])
    results = []
    for item in page[:30]:
        listing = item.listing
        owner = listing.owner_account
        profile = getattr(owner, "profile", None)
        results.append({"id": item.pk, "listingId": listing.pk, "title": listing.title,
            "price": str(listing.price_sol.normalize()), "status": listing.status,
            "ownerId": owner.pk if owner else None,
            "ownerName": (profile.display_name if profile else "") or (owner.first_name if owner else "") or "AdMint member",
            "createdAt": item.created_at.isoformat(), "read": item.read_at is not None})
    return JsonResponse({"results": results, "unreadCount": items.filter(read_at__isnull=True).count(),
        "nextCursor": page[29].pk if len(page)>30 else None})

@require_POST
def mark_read(request):
    if not request.user.is_authenticated: return fail("Log in to see notifications.", 401)
    try: data = body(request)
    except ValidationError: return fail("Invalid request.")
    ids = data.get("ids")
    if not isinstance(ids, list) or len(ids)>100 or any(type(value) is not int for value in ids):
        return fail("Choose up to 100 notifications.")
    Notification.objects.filter(recipient=request.user, pk__in=ids, read_at__isnull=True).update(read_at=timezone.now())
    return JsonResponse({"ok": True})
