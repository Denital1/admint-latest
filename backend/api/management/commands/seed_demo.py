from django.core.management.base import BaseCommand

from api.models import Listing


class Command(BaseCommand):
    help = "Create the six AdMint demo listings if they do not already exist."

    DEMO = [
        {
            "title": "Hackathon Laptop Lid",
            "owner": "@giorgi",
            "surface_type": "Physical",
            "duration": "Until demo ends",
            "price_sol": "0.25",
            "emoji": "💻",
            "tagline": "Your logo. My laptop. Everyone stares.",
            "accent": "from-violet-500/30 to-fuchsia-500/5",
        },
        {
            "title": "@creator X Banner",
            "owner": "@creator",
            "surface_type": "Digital",
            "duration": "7 days",
            "price_sol": "0.80",
            "emoji": "𝕏",
            "tagline": "Rent the first thing my followers see.",
            "accent": "from-sky-500/25 to-cyan-500/5",
        },
        {
            "title": "Garage Wall",
            "owner": "@houseowner",
            "surface_type": "Physical",
            "duration": "30 days",
            "price_sol": "2.50",
            "emoji": "🏠",
            "tagline": "A blank wall is just wasted inventory.",
            "accent": "from-orange-500/20 to-amber-500/5",
        },
        {
            "title": "Hoodie Front",
            "owner": "@builder",
            "surface_type": "Physical",
            "duration": "Tonight only",
            "price_sol": "0.15",
            "emoji": "👕",
            "tagline": "Yes. The hoodie is monetizable.",
            "accent": "from-pink-500/25 to-rose-500/5",
        },
        {
            "title": "Stream Overlay",
            "owner": "@streamer",
            "surface_type": "Digital",
            "duration": "24 hours",
            "price_sol": "0.40",
            "emoji": "🎥",
            "tagline": "Own a piece of the live screen.",
            "accent": "from-emerald-500/20 to-teal-500/5",
        },
        {
            "title": "Conference Badge Back",
            "owner": "@attendee",
            "surface_type": "Physical",
            "duration": "1 event day",
            "price_sol": "0.10",
            "emoji": "🎫",
            "tagline": "If people can see it, it can be inventory.",
            "accent": "from-indigo-500/25 to-violet-500/5",
        },
    ]

    def handle(self, *args, **options):
        # Showcase listings intentionally use a valid-looking placeholder owner
        # only for display; the UI will treat them as non-purchasable because
        # their seller wallet is empty.
        created = 0
        for item in self.DEMO:
            _, was_created = Listing.objects.get_or_create(
                title=item["title"],
                defaults={**item, "seller_wallet": ""},
            )
            created += int(was_created)
        self.stdout.write(self.style.SUCCESS(f"Demo seed complete. Created {created} listings."))
