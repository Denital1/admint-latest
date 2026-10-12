import base64
from datetime import timedelta
from unittest.mock import Mock, patch
from urllib.parse import parse_qs, urlparse
import base58
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase, Client, override_settings
from django.utils import timezone
from .models import Challenge, Identity, LoginEvent

class AuthenticationTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = Client(enforce_csrf_checks=True)
        self.private = Ed25519PrivateKey.generate()
        self.wallet = base58.b58encode(self.private.public_key().public_bytes(Encoding.Raw, PublicFormat.Raw)).decode()

    def post(self, path, data):
        csrf = self.client.get("/api/auth/session/").json()["csrfToken"]
        return self.client.post("/api/auth/" + path + "/", data, content_type="application/json", HTTP_X_CSRFTOKEN=csrf)

    def challenge(self):
        return self.post("wallet/challenge", {"wallet": self.wallet}).json()

    def signature(self, challenge, key=None):
        return base64.b64encode((key or self.private).sign(challenge["message"].encode())).decode()

    def test_email_signup_login_logout_and_hash(self):
        data = {"email": "Member@example.com", "password": "Long!unique-pass-7294", "name": "Test Member"}
        r = self.post("signup", data)
        self.assertEqual(r.status_code, 200)
        user = get_user_model().objects.get(pk=r.json()["user"]["id"])
        self.assertNotEqual(user.password, data["password"])
        self.assertTrue(user.check_password(data["password"]))
        self.assertEqual(self.client.get("/api/auth/session/").json()["user"]["id"], user.pk)
        self.assertEqual(self.post("logout", {}).status_code, 200)
        self.assertIsNone(self.client.get("/api/auth/session/").json()["user"])
        self.assertEqual(self.post("login", data).status_code, 200)
        self.assertEqual(LoginEvent.objects.count(), 2)
        self.assertEqual(self.post("signup", data).status_code, 409)

    def test_bad_password_and_weak_signup(self):
        self.assertEqual(self.post("login", {"email": "missing@example.com", "password": "wrong"}).status_code, 401)
        self.assertEqual(self.post("signup", {"email": "bad", "password": "123"}).status_code, 400)
        self.assertEqual(self.post("signup", {"email": "x@example.com", "password": "1234567890"}).status_code, 400)

    def test_missing_csrf_rejected(self):
        self.assertEqual(self.client.post("/api/auth/login/", {}, content_type="application/json").status_code, 403)

    def test_wallet_login_and_replay_rejected(self):
        c = self.challenge()
        data = {"challenge": c["challenge"], "signature": self.signature(c)}
        r = self.post("wallet/verify", data)
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["user"]["wallets"], [self.wallet])
        self.assertEqual(self.post("wallet/verify", data).status_code, 401)
        self.post("logout", {})
        c = self.challenge()
        r2 = self.post("wallet/verify", {"challenge": c["challenge"], "signature": self.signature(c)})
        self.assertEqual(r2.json()["user"]["id"], r.json()["user"]["id"])
        self.assertEqual(get_user_model().objects.count(), 1)

    def test_wrong_signature_expiry_and_session_rejected(self):
        c = self.challenge()
        self.assertEqual(self.post("wallet/verify", {"challenge": c["challenge"], "signature": self.signature(c, Ed25519PrivateKey.generate())}).status_code, 401)
        other = Client()
        self.assertEqual(other.post("/api/auth/wallet/verify/", {"challenge": c["challenge"], "signature": self.signature(c)}, content_type="application/json").status_code, 401)
        Challenge.objects.filter(token=c["challenge"]).update(expires_at=timezone.now()-timedelta(seconds=1))
        self.assertEqual(self.post("wallet/verify", {"challenge": c["challenge"], "signature": self.signature(c)}).status_code, 401)

    def test_wallet_link_to_email_account(self):
        self.post("signup", {"email": "test@example.com", "password": "Long!unique-pass-7294"})
        c = self.challenge()
        self.assertEqual(self.post("wallet/verify", {"challenge": c["challenge"], "signature": self.signature(c)}).status_code, 200)
        self.assertEqual(get_user_model().objects.count(), 1)
        self.assertEqual(Identity.objects.count(), 2)

    def test_private_marketplace_requires_authenticated_wallet(self):
        self.assertEqual(self.client.get("/api/purchases/?wallet=" + self.wallet).status_code, 401)
        self.assertEqual(self.client.post("/api/purchases/prepare/", {"listing_id": 1, "buyer_wallet": self.wallet}, content_type="application/json").status_code, 401)
        self.post("signup", {"email": "test@example.com", "password": "Long!unique-pass-7294"})
        self.assertEqual(self.client.get("/api/purchases/?wallet=" + self.wallet).status_code, 403)

    @override_settings(GOOGLE_CLIENT_ID="test-client", GOOGLE_CLIENT_SECRET="test-secret")
    def test_google_flow_and_replay(self):
        r = self.client.get("/api/auth/google/start/")
        params = parse_qs(urlparse(r.url).query)
        self.assertEqual(params["code_challenge_method"], ["S256"])
        response = Mock()
        response.json.return_value = {"id_token": "verified-by-google-library"}
        claims = {"sub": "google-user", "nonce": params["nonce"][0], "email_verified": True, "email": "g@example.com", "given_name": "Google Member"}
        with patch("accounts.views.requests.post", return_value=response), patch("accounts.views.verify_oauth2_token", return_value=claims):
            r = self.client.get("/api/auth/google/callback/", {"state": params["state"][0], "code": "authorization-code"})
        self.assertIn("success=google", r.url)
        self.assertEqual(Identity.objects.get().provider, "google")
        self.assertIn("google_failed", self.client.get("/api/auth/google/callback/", {"state": params["state"][0], "code": "authorization-code"}).url)

    @override_settings(GOOGLE_CLIENT_ID="test-client", GOOGLE_CLIENT_SECRET="test-secret")
    def test_google_wrong_state_and_nonce(self):
        self.client.get("/api/auth/google/start/")
        with patch("accounts.views.requests.post") as exchange:
            r = self.client.get("/api/auth/google/callback/", {"state": "wrong"})
            self.assertIn("google_failed", r.url)
            exchange.assert_not_called()
        r = self.client.get("/api/auth/google/start/")
        state = parse_qs(urlparse(r.url).query)["state"][0]
        response = Mock()
        response.json.return_value = {"id_token": "token"}
        with patch("accounts.views.requests.post", return_value=response), patch("accounts.views.verify_oauth2_token", return_value={"nonce": "wrong", "email_verified": True}):
            self.assertIn("google_failed", self.client.get("/api/auth/google/callback/", {"state": state, "code": "code"}).url)
        self.assertEqual(get_user_model().objects.count(), 0)

    @override_settings(GOOGLE_CLIENT_ID="", GOOGLE_CLIENT_SECRET="")
    def test_google_missing_configuration(self):
        self.assertFalse(self.client.get("/api/auth/session/").json()["googleEnabled"])
        self.assertIn("google_not_configured", self.client.get("/api/auth/google/start/").url)


class ProfileTests(TestCase):
    def setUp(self):
        from django.contrib.auth import get_user_model
        self.user = get_user_model().objects.create_user(username="profile-owner", first_name="Profile Owner", email="private@example.com")
        self.other = get_user_model().objects.create_user(username="profile-other", first_name="Other Member")
        self.client = Client(enforce_csrf_checks=True)

    def csrf(self):
        return self.client.get("/api/auth/session/").json()["csrfToken"]

    def test_public_profile_privacy_and_missing_user(self):
        r=self.client.get(f"/api/profiles/{self.user.pk}/")
        self.assertEqual(r.status_code,200)
        self.assertNotIn("email",r.json())
        self.assertNotIn("private@example.com",r.content.decode())
        self.assertFalse(r.json()["isOwner"])
        self.assertEqual(self.client.get("/api/profiles/999999/").status_code,404)

    def test_follow_idempotency_unfollow_and_self_follow(self):
        from .models import Follow
        self.client.force_login(self.user)
        for _ in range(2):
            r=self.client.post(f"/api/profiles/{self.other.pk}/follow/", {"following":True},content_type="application/json",HTTP_X_CSRFTOKEN=self.csrf())
            self.assertEqual(r.status_code,200)
        self.assertEqual(Follow.objects.count(),1)
        data=self.client.get(f"/api/profiles/{self.other.pk}/").json()
        self.assertEqual(data["counts"]["followers"],1)
        self.assertTrue(data["isFollowing"])
        self.assertEqual(data["followers"][0]["id"],self.user.pk)
        self.assertEqual(self.client.post(f"/api/profiles/{self.user.pk}/follow/", {"following":True},content_type="application/json",HTTP_X_CSRFTOKEN=self.csrf()).status_code,400)
        self.client.post(f"/api/profiles/{self.other.pk}/follow/", {"following":False},content_type="application/json",HTTP_X_CSRFTOKEN=self.csrf())
        self.assertEqual(Follow.objects.count(),0)

    def test_follow_login_and_csrf_required(self):
        self.assertEqual(self.client.post(f"/api/profiles/{self.other.pk}/follow/", {"following":True},content_type="application/json",HTTP_X_CSRFTOKEN=self.csrf()).status_code,401)
        self.client.force_login(self.user)
        self.assertEqual(self.client.post(f"/api/profiles/{self.other.pk}/follow/", {"following":True},content_type="application/json").status_code,403)

    def test_profile_edit_avatar_upload_and_removal(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from .models import Profile
        self.client.force_login(self.user)
        output=BytesIO()
        Image.new("RGB",(700,400),(120,80,200)).save(output,"PNG")
        r=self.client.post("/api/profiles/update/", {"name":"Updated Name","bio":"Profile biography","avatar":SimpleUploadedFile("test.png",output.getvalue(),content_type="image/png")},HTTP_X_CSRFTOKEN=self.csrf())
        self.assertEqual(r.status_code,200)
        data=self.client.get(f"/api/profiles/{self.user.pk}/").json()
        self.assertEqual(data["name"],"Updated Name")
        self.assertTrue(data["isOwner"])
        r=self.client.get(data["avatar"])
        self.assertEqual(r["Content-Type"],"image/jpeg")
        self.assertEqual(Image.open(BytesIO(r.content)).size,(512,512))
        self.assertFalse(Profile.objects.filter(user=self.other).exists())
        self.client.post("/api/profiles/update/", {"name":"Updated Name","bio":"","removeAvatar":"true"},HTTP_X_CSRFTOKEN=self.csrf())
        self.assertIsNone(self.client.get(f"/api/profiles/{self.user.pk}/").json()["avatar"])

    def test_invalid_photo_and_oversized_photo_rejected(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.client.force_login(self.user)
        for name,content in [("bad.svg",b"<svg><script>alert(1)</script></svg>"),("huge.png",b"x"*(5*1024*1024+1))]:
            r=self.client.post("/api/profiles/update/", {"name":"Name","bio":"","avatar":SimpleUploadedFile(name,content)},HTTP_X_CSRFTOKEN=self.csrf())
            self.assertEqual(r.status_code,400)

    def test_confirmed_history_and_wallet_profile(self):
        from decimal import Decimal
        from api.models import Listing, Purchase
        Identity.objects.create(user=self.user,provider="phantom",subject="seller-wallet")
        Identity.objects.create(user=self.other,provider="phantom",subject="buyer-wallet")
        listing=Listing.objects.create(title="Real history",seller_wallet="seller-wallet",price_sol=Decimal("0.25"),duration="7 days")
        Purchase.objects.create(listing=listing,buyer_wallet="buyer-wallet",seller_wallet="seller-wallet",price_sol=Decimal("0.25"),status="confirmed",confirmed_at=timezone.now())
        Purchase.objects.create(listing=listing,buyer_wallet="buyer-wallet",seller_wallet="seller-wallet",price_sol=Decimal("0.25"),status="failed")
        seller=self.client.get(f"/api/profiles/{self.user.pk}/").json()
        buyer=self.client.get(f"/api/profiles/{self.other.pk}/").json()
        self.assertEqual(seller["counts"]["sold"],1)
        self.assertEqual(buyer["counts"]["bought"],1)
        self.assertEqual(seller["sold"][0]["title"],"Real history")
        self.assertEqual(self.client.get("/api/profiles/wallet/seller-wallet/").json()["id"],self.user.pk)
        self.assertEqual(self.client.get("/api/profiles/wallet/unknown-wallet/").status_code,404)

    def test_edit_requires_login_and_ignores_target_user(self):
        r=self.client.post("/api/profiles/update/",{"name":"Name","bio":""},HTTP_X_CSRFTOKEN=self.csrf())
        self.assertEqual(r.status_code,401)
        self.client.force_login(self.user)
        self.client.post("/api/profiles/update/",{"name":"Only mine","bio":"","user_id":self.other.pk},HTTP_X_CSRFTOKEN=self.csrf())
        self.assertEqual(self.client.get(f"/api/profiles/{self.other.pk}/").json()["name"],"Other Member")

    def test_public_profile_search_privacy_and_wallet(self):
        from .models import Profile
        Profile.objects.create(user=self.user, display_name="Unique Artist")
        Identity.objects.create(user=self.user, provider="phantom", subject="search-wallet-123")
        for query in ["unique", "search-wallet"]:
            data=self.client.get("/api/profiles/search/", {"q":query}).json()["results"]
            self.assertEqual([item["id"] for item in data], [self.user.pk])
            self.assertEqual(set(data[0]), {"id", "name", "avatar"})
        self.assertEqual(self.client.get("/api/profiles/search/", {"q":self.user.email}).json()["results"], [])
        self.assertEqual(self.client.get("/api/profiles/search/", {"q":"u"}).json()["results"], [])
        self.user.is_active=False
        self.user.save()
        self.assertEqual(self.client.get("/api/profiles/search/", {"q":"unique"}).json()["results"], [])


class NotificationTests(TestCase):
    def test_followed_new_listing_and_private_read_state(self):
        from .models import Follow, Notification
        User=get_user_model()
        seller=User.objects.create_user(username="notification-seller",first_name="Seller")
        follower=User.objects.create_user(username="notification-follower")
        stranger=User.objects.create_user(username="notification-stranger")
        Follow.objects.create(follower=follower,following=seller)
        Identity.objects.create(user=seller,provider="phantom",subject="notification-wallet")
        self.client.force_login(seller)
        response=self.client.post("/api/listings/",{"title":"New surface","surfaceType":"Physical","duration":"day","priceSol":0.1,"seller_wallet":"notification-wallet"},content_type="application/json")
        self.assertEqual(response.status_code,201,response.content)
        self.assertEqual(Notification.objects.count(),1)
        item=Notification.objects.get()
        self.assertEqual(item.recipient,follower)
        self.client.force_login(stranger)
        self.assertEqual(self.client.get("/api/profiles/notifications/").json()["results"],[])
        self.client.post("/api/profiles/notifications/read/",{"ids":[item.pk]},content_type="application/json")
        item.refresh_from_db();self.assertIsNone(item.read_at)
        self.client.force_login(follower)
        data=self.client.get("/api/profiles/notifications/").json()
        self.assertEqual(data["unreadCount"],1)
        self.assertEqual(data["results"][0]["title"],"New surface")
        self.client.post("/api/profiles/notifications/read/",{"ids":[item.pk]},content_type="application/json")
        self.assertEqual(self.client.get("/api/profiles/notifications/").json()["unreadCount"],0)
        self.client.logout()
        self.assertEqual(self.client.get("/api/profiles/notifications/").status_code,401)
