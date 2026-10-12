"""Generate private deployment configuration once, without printing secrets."""
import argparse
import os
from pathlib import Path
import re
import secrets

def configure(domain, destination):
    if not re.fullmatch(r"(?=.{1,253}$)[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)+", domain):
        raise ValueError("Provide a DNS hostname without a scheme, path or port.")
    values = {
        "DOMAIN": domain.lower(), "DJANGO_SETTINGS_MODULE": "config.production", "DJANGO_DEBUG": "0",
        "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
        "DJANGO_ALLOWED_HOSTS": f"{domain.lower()},backend", "FRONTEND_URL": f"https://{domain.lower()}",
        "CSRF_TRUSTED_ORIGINS": f"https://{domain.lower()}", "CORS_ALLOWED_ORIGINS": f"https://{domain.lower()}",
        "POSTGRES_DB": "admint", "POSTGRES_USER": "admint_admin", "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
        "APP_DATABASE_USER": "admint", "APP_DATABASE_PASSWORD": secrets.token_urlsafe(32),
        "CACHE_URL": "redis://cache:6379/0", "GOOGLE_CLIENT_ID": "", "GOOGLE_CLIENT_SECRET": "",
    }
    # Exclusive creation prevents accidental secret rotation on an existing deployment.
    descriptor = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "w", newline="\n") as output:
        output.write("\n".join(f"{key}={value}" for key,value in values.items()) + "\n")

if __name__ == "__main__":
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("domain")
    args=parser.parse_args()
    try:
        configure(args.domain,Path(__file__).with_name(".env.production"))
    except (ValueError, FileExistsError) as error:
        parser.exit(1, f"Configuration not written: {error}\n")
    print("Created deploy/.env.production with private random secrets. Keep it private.")
