import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

def assign_existing_owners(apps, schema_editor):
    Listing = apps.get_model("api", "Listing")
    Identity = apps.get_model("accounts", "Identity")
    alias = schema_editor.connection.alias
    for identity in Identity.objects.using(alias).filter(provider="phantom").iterator():
        Listing.objects.using(alias).filter(owner_account__isnull=True, seller_wallet=identity.subject).update(owner_account_id=identity.user_id)

class Migration(migrations.Migration):
    dependencies = [("api", "0001_initial"), ("accounts", "0002_profile_follow"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]
    operations = [
        migrations.AddField(model_name="listing", name="owner_account", field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="owned_surfaces", to=settings.AUTH_USER_MODEL)),
        migrations.RunPython(assign_existing_owners, migrations.RunPython.noop),
    ]
