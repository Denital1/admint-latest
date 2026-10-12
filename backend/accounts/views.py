import base64
import hashlib
import json
import secrets
from datetime import timedelta
from urllib.parse import urlencode

import base58
import requests
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from django.conf import settings
from django.contrib.auth import authenticate, get_user_model, login, logout
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import JsonResponse, HttpResponseRedirect
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST
from django.core.cache import cache
from django.views.decorators.cache import never_cache
from google.auth.exceptions import GoogleAuthError
from google.auth.transport.requests import Request
from google.oauth2.id_token import verify_oauth2_token
from .models import Challenge, Identity, LoginEvent, Profile

User = get_user_model()

def fail(message, status=400):
    return JsonResponse({"detail": message}, status=status)

def body(request):
    try:
        data = json.loads(request.body)
        if not isinstance(data, dict):
            raise ValueError()
        return data
    except (ValueError, UnicodeDecodeError):
        raise ValidationError("Invalid JSON request.")

def limited(request):
    key = "auth:" + hashlib.sha256(request.META.get("REMOTE_ADDR", "").encode()).hexdigest()
    cache.add(key, 0, 60)
    return cache.incr(key) > 30

def user_data(user):
    profile, _ = Profile.objects.get_or_create(user=user)
    return {"id": user.pk, "name": profile.display_name or user.first_name or "AdMint member", "email": user.email,
            "wallets": list(user.identities.filter(provider="phantom").values_list("subject", flat=True))}

def start_session(request, user, provider):
    login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    LoginEvent.objects.create(user=user, provider=provider)
    return JsonResponse({"user": user_data(user), "csrfToken": get_token(request)})

@require_GET
@never_cache
def session(request):
    return JsonResponse({"user": user_data(request.user) if request.user.is_authenticated else None,
                         "csrfToken": get_token(request), "googleEnabled": bool(settings.GOOGLE_CLIENT_ID and settings.GOOGLE_CLIENT_SECRET)})

@require_POST
def signup(request):
    if limited(request): return fail("Too many attempts. Try again in a minute.", 429)
    try:
        data = body(request)
        email = str(data.get("email", "")).strip().lower()
        password = data.get("password", "")
        name = str(data.get("name", "")).strip()[:80]
        validate_email(email)
        if len(email) > 254 or not isinstance(password, str) or len(password) > 128:
            raise ValidationError("Invalid email or password length.")
        user = User(username="email:" + hashlib.sha256(email.encode()).hexdigest(), email=email, first_name=name)
        validate_password(password, user=user)
        with transaction.atomic():
            user.set_password(password)
            user.save()
            Identity.objects.create(user=user, provider="email", subject=email)
        return start_session(request, user, "email")
    except ValidationError as exc: return fail(" ".join(exc.messages))
    except IntegrityError: return fail("An account with this email already exists. Log in instead.", 409)

@require_POST
def password_login(request):
    if limited(request): return fail("Too many attempts. Try again in a minute.", 429)
    try:
        data = body(request)
        email = str(data.get("email", "")).strip().lower()
        password = data.get("password", "")
        if not isinstance(password, str) or len(password) > 128: return fail("Invalid email or password.", 401)
        user = authenticate(request, username="email:" + hashlib.sha256(email.encode()).hexdigest(), password=password)
        if user is None: return fail("Invalid email or password.", 401)
        return start_session(request, user, "email")
    except ValidationError as exc: return fail(" ".join(exc.messages))

@require_POST
def signout(request):
    logout(request)
    return JsonResponse({"ok": True, "csrfToken": get_token(request)})

@require_POST
def wallet_challenge(request):
    if limited(request): return fail("Too many attempts. Try again in a minute.", 429)
    try:
        data = body(request)
        wallet = str(data.get("wallet", ""))
        if len(wallet) > 64 or len(base58.b58decode(wallet)) != 32: return fail("Invalid Solana wallet.")
        if not request.session.session_key: request.session.create()
        token = secrets.token_hex(32)
        expires = timezone.now() + timedelta(minutes=5)
        message = (f"Sign in to AdMint\nWebsite: {settings.FRONTEND_URL}\nWallet: {wallet}\n"
                   f"Nonce: {token}\nExpires: {expires.isoformat()}\n"
                   "This signature only verifies ownership. It does not authorize a transaction.")
        Challenge.objects.create(token=token, session_key=request.session.session_key, wallet=wallet, message=message, expires_at=expires)
        return JsonResponse({"challenge": token, "message": message})
    except (ValidationError, ValueError) as exc: return fail("Invalid wallet challenge request.")

@require_POST
def wallet_verify(request):
    if limited(request): return fail("Too many attempts. Try again in a minute.", 429)
    try:
        data = body(request)
        with transaction.atomic():
            challenge = Challenge.objects.get(token=str(data.get("challenge", "")), session_key=request.session.session_key, used=False, expires_at__gt=timezone.now())
            signature = base64.b64decode(data.get("signature", ""), validate=True)
            Ed25519PublicKey.from_public_bytes(base58.b58decode(challenge.wallet)).verify(signature, challenge.message.encode())
            if not Challenge.objects.filter(pk=challenge.pk, used=False).update(used=True): return fail("Challenge already used.", 401)
            identity = Identity.objects.filter(provider="phantom", subject=challenge.wallet).select_related("user").first()
            if request.user.is_authenticated:
                user = request.user
                if identity and identity.user_id != user.pk: return fail("This wallet belongs to another account. Log out first.", 409)
            elif identity:
                user = identity.user
            else:
                user = User.objects.create_user(username="wallet:" + challenge.wallet, first_name="Phantom member")
                user.set_unusable_password()
                user.save(update_fields=["password"])
            if not user.is_active: return fail("Account is inactive.", 403)
            if not identity: Identity.objects.create(user=user, provider="phantom", subject=challenge.wallet)
            from api.models import WalletProfile
            WalletProfile.objects.get_or_create(wallet_address=challenge.wallet)
        return start_session(request, user, "phantom")
    except (Challenge.DoesNotExist, ValueError, InvalidSignature, ValidationError, TypeError):
        return fail("Invalid, expired, or already used wallet signature. Please try again.", 401)
    except IntegrityError: return fail("Wallet sign-in is already being processed. Please try again.", 409)

@require_GET
def google_start(request):
    if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_CLIENT_SECRET:
        return HttpResponseRedirect(settings.FRONTEND_URL + "/login?error=google_not_configured")
    state, nonce, verifier = secrets.token_urlsafe(32), secrets.token_urlsafe(32), secrets.token_urlsafe(48)
    request.session["google_oauth"] = {"state": state, "nonce": nonce, "verifier": verifier, "created": timezone.now().timestamp(), "user_id": request.user.pk if request.user.is_authenticated else None}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).decode().rstrip("=")
    return HttpResponseRedirect("https://accounts.google.com/o/oauth2/v2/auth?" + urlencode({
        "client_id": settings.GOOGLE_CLIENT_ID, "redirect_uri": settings.FRONTEND_URL + "/api/auth/google/callback/",
        "response_type": "code", "scope": "openid email profile", "state": state, "nonce": nonce,
        "code_challenge": challenge, "code_challenge_method": "S256", "prompt": "select_account"}))

@require_GET
def google_callback(request):
    flow = request.session.pop("google_oauth", None)
    if not flow or not secrets.compare_digest(str(request.GET.get("state", "")), flow["state"]) or timezone.now().timestamp() - flow["created"] > 600:
        return HttpResponseRedirect(settings.FRONTEND_URL + "/login?error=google_failed")
    if flow["user_id"] != (request.user.pk if request.user.is_authenticated else None):
        return HttpResponseRedirect(settings.FRONTEND_URL + "/login?error=google_failed")
    try:
        response = requests.post("https://oauth2.googleapis.com/token", data={
            "code": request.GET.get("code", ""), "client_id": settings.GOOGLE_CLIENT_ID,
            "client_secret": settings.GOOGLE_CLIENT_SECRET, "redirect_uri": settings.FRONTEND_URL + "/api/auth/google/callback/",
            "grant_type": "authorization_code", "code_verifier": flow["verifier"]}, timeout=12)
        response.raise_for_status()
        claims = verify_oauth2_token(response.json()["id_token"], Request(), settings.GOOGLE_CLIENT_ID)
        if claims.get("nonce") != flow["nonce"] or claims.get("email_verified") is not True: raise ValueError("Invalid identity")
        with transaction.atomic():
            identity = Identity.objects.filter(provider="google", subject=claims["sub"]).select_related("user").first()
            if request.user.is_authenticated:
                user = request.user
                if identity and identity.user_id != user.pk: raise ValueError("Already linked")
            elif identity:
                user = identity.user
            else:
                user = User.objects.create_user(username="google:" + claims["sub"], email=claims.get("email", ""), first_name=claims.get("given_name", "Google member")[:80])
                user.set_unusable_password()
                user.save(update_fields=["password"])
            if not user.is_active: raise ValueError("Inactive")
            if not identity: Identity.objects.create(user=user, provider="google", subject=claims["sub"])
        start_session(request, user, "google")
        return HttpResponseRedirect(settings.FRONTEND_URL + "/login?success=google")
    except (requests.RequestException, GoogleAuthError, ValueError, KeyError, IntegrityError):
        return HttpResponseRedirect(settings.FRONTEND_URL + "/login?error=google_failed")
