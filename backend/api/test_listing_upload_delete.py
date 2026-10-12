from io import BytesIO
from PIL import Image
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient
from accounts.models import Identity, Follow, Notification
from api.models import Listing, ListingDetails, Purchase

class ListingUploadDeleteTests(TestCase):
    def setUp(self):
        self.seller = get_user_model().objects.create_user(username='upload-seller')
        self.other = get_user_model().objects.create_user(username='upload-other')
        Identity.objects.create(user=self.seller,provider='phantom',subject='upload-wallet')
        Identity.objects.create(user=self.other,provider='phantom',subject='other-wallet')
        self.client=APIClient(); self.client.force_login(self.seller)
        self.payload=dict(title='New window',owner='@seller',surfaceType='Physical',duration='7 days',
            priceSol='0.01',emoji='x',tagline='Campaign space',accent='warm',seller_wallet='upload-wallet')

    def image(self):
        data=BytesIO();Image.new('RGB',(16,12),'orange').save(data,'PNG')
        return SimpleUploadedFile('window.png',data.getvalue(),content_type='image/png')

    def create(self, **extra):
        return self.client.post('/api/listings/',{**self.payload,**extra},format='multipart')

    def listing(self):
        return Listing.objects.create(title='Existing window',seller_wallet='upload-wallet',owner_account=self.seller,duration='7 days',price_sol='0.01')

    def test_photo_creation_persists_and_serves_jpeg(self):
        Follow.objects.create(follower=self.other,following=self.seller)
        response=self.create(photo=self.image())
        self.assertEqual(response.status_code,201,response.data)
        item=Listing.objects.get(pk=response.data['id'])
        self.assertEqual(item.owner_account,self.seller)
        self.assertTrue(ListingDetails.objects.get(listing=item).photo)
        photo=self.client.get(response.data['photo'])
        self.assertEqual(photo.status_code,200)
        self.assertEqual(photo['Content-Type'],'image/jpeg')
        with Image.open(BytesIO(photo.content)) as image:self.assertEqual(image.format,'JPEG')
        self.assertEqual(Notification.objects.filter(listing=item).count(),1)

    def test_bad_photo_creates_no_partial_listing_or_notification(self):
        Follow.objects.create(follower=self.other,following=self.seller)
        response=self.create(photo=SimpleUploadedFile('bad.png',b'not an image',content_type='image/png'))
        self.assertEqual(response.status_code,400)
        self.assertFalse(Listing.objects.exists());self.assertFalse(Notification.objects.exists())

    def test_oversized_photo_rejected(self):
        response=self.create(photo=SimpleUploadedFile('big.png',b'x'*(5*1024*1024+1),content_type='image/png'))
        self.assertEqual(response.status_code,400);self.assertFalse(Listing.objects.exists())

    def test_creation_without_photo_remains_supported(self):
        response=self.create();self.assertEqual(response.status_code,201,response.data)
        self.assertIsNone(response.data['photo'])

    def test_unverified_wallet_cannot_create(self):
        self.client.force_login(self.other)
        self.assertEqual(self.create(photo=self.image()).status_code,403)
        self.assertFalse(Listing.objects.exists())

    def test_owner_removal_hides_listing_and_preserves_record(self):
        item=self.listing();ListingDetails.objects.create(listing=item,photo=b'jpeg')
        Notification.objects.create(recipient=self.other,listing=item)
        self.assertEqual(self.client.post(f'/api/listings/{item.pk}/delete/',{},format='json').status_code,200)
        item.refresh_from_db();self.assertIsNotNone(item.deleted_at)
        self.assertEqual(self.client.get('/api/listings/').data,[])
        for suffix in ['', 'details/', 'photo/']:
            self.assertEqual(self.client.get(f'/api/listings/{item.pk}/{suffix}').status_code,404)
        self.assertEqual(self.client.get(f'/api/profiles/{self.seller.pk}/').json()['counts']['listings'],0)
        self.client.force_login(self.other)
        self.assertEqual(self.client.get('/api/profiles/notifications/').json()['results'],[])
        response=self.client.post('/api/purchases/prepare/',{'listing_id':item.pk,'cluster':'devnet','buyer_wallet':'other-wallet'},format='json')
        self.assertEqual(response.status_code,404)

    def test_non_owner_and_guest_cannot_delete(self):
        item=self.listing();url=f'/api/listings/{item.pk}/delete/'
        self.client.force_login(self.other)
        self.assertEqual(self.client.post(url,{},format='json').status_code,403)
        self.client.logout();self.assertEqual(self.client.post(url,{},format='json').status_code,401)
        item.refresh_from_db();self.assertIsNone(item.deleted_at)

    def test_active_or_sold_listing_cannot_be_deleted(self):
        item=self.listing();url=f'/api/listings/{item.pk}/delete/'
        for status in ['reserved','sold']:
            item.status=status;item.save()
            self.assertEqual(self.client.post(url,{},format='json').status_code,409)
        item.status='available';item.save()
        Purchase.objects.create(listing=item,buyer_wallet='other-wallet',seller_wallet='upload-wallet',price_sol='0.01',status='pending')
        self.assertEqual(self.client.post(url,{},format='json').status_code,409)
        item.refresh_from_db();self.assertIsNone(item.deleted_at)
