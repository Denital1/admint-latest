"""Run backend tests against an isolated file DB, including SQLite contention."""
import os, sys
from pathlib import Path
root=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(root/"backend"))
os.environ.setdefault("DJANGO_SETTINGS_MODULE","config.settings")
import django
from django.conf import settings
test_path=root/"qa"/"test-backend-isolated.sqlite3"
if test_path.exists():
    raise SystemExit("Isolated test database already exists; inspect it before reusing.")
settings.DATABASES["default"].setdefault("TEST",{})["NAME"]=str(test_path)
django.setup()
from django.test.utils import get_runner
sys.exit(bool(get_runner(settings)(verbosity=1,interactive=False).run_tests(sys.argv[1:] or ["accounts","api"])))
