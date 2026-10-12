from django.test import TestCase, override_settings
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from accounts.models import Identity
from api.models import Listing, Purchase

@override_settings(DEMO_VIDEO_SELLER_WALLET='demo-seller')
class VideoDemoTests(TestCase):
    def setUp(self):
        self.buyer = get_user_model().objects.create_user(username='test-video-buyer')
        self.seller = get_user_model().objects.create_user(username='test-video-seller')
        Identity.objects.create(user=self.buyer, provider='phantom', subject='demo-buyer')
        self.listing = Listing.objects.create(title='ARM Shop Window', owner_account=self.seller,
            seller_wallet='demo-seller', duration='7 days', price_sol='0.01')
        self.client = APIClient()
        self.client.force_authenticate(user=self.buyer)

    def prepare(self, cluster):
        return self.client.post('/api/purchases/prepare/', {'listing_id':self.listing.pk,
            'buyer_wallet':'demo-buyer', 'cluster':cluster}, format='json')

    def test_devnet_can_prepare(self):
        response = self.prepare('devnet')
        self.assertEqual(response.status_code, 201, response.data)
        self.assertEqual(Purchase.objects.get().cluster, 'devnet')

    def test_mainnet_blocked_before_reservation(self):
        response = self.prepare('mainnet')
        self.assertEqual(response.status_code, 400, response.data)
        self.assertIn('Devnet', response.data['detail'])
        self.assertFalse(Purchase.objects.exists())
        self.listing.refresh_from_db()
        self.assertEqual(self.listing.status, 'available')

    def test_same_account_still_blocked(self):
        self.listing.owner_account = self.buyer
        self.listing.save()
        self.assertEqual(self.prepare('devnet').status_code, 400)
        self.assertFalse(Purchase.objects.exists())
