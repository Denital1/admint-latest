import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
from django.core.cache import cache
from django.test import SimpleTestCase, RequestFactory, override_settings
from .middleware import TrustedProxyIPMiddleware
from accounts.views import limited

BACKEND=Path(__file__).resolve().parents[1]

class ProductionSettingsTests(SimpleTestCase):
    def run_config(self,changes=None,code="import django; django.setup()"):
        env={**os.environ,"DJANGO_SETTINGS_MODULE":"config.production","DJANGO_DEBUG":"0",
             "DJANGO_SECRET_KEY":secrets.token_urlsafe(64),"DATABASE_URL":f"postgresql://qa:{secrets.token_urlsafe(32)}@localhost:5432/qa",
             "CACHE_URL":"redis://localhost:6379/0","DJANGO_ALLOWED_HOSTS":"admint.qa.invalid,backend",
             "FRONTEND_URL":"https://admint.qa.invalid","CSRF_TRUSTED_ORIGINS":"https://admint.qa.invalid",
             "CORS_ALLOWED_ORIGINS":"https://admint.qa.invalid"}
        env.update(changes or {})
        return subprocess.run([sys.executable,"-c",code],cwd=BACKEND,env=env,capture_output=True,text=True,timeout=20)

    def test_valid_production_passes_deployment_checks(self):
        result=self.run_config(code="import django; django.setup(); from django.core.management import call_command; call_command('check',deploy=True,fail_level='WARNING')")
        self.assertEqual(result.returncode,0,result.stderr)

    def test_unsafe_production_configuration_is_rejected(self):
        for changes in [
            {"DJANGO_DEBUG":"1"},{"DJANGO_DEBUG":""},
            {"DJANGO_SECRET_KEY":"replace-with-a-unique-random-secret-at-least-50-characters"},
            {"DJANGO_SECRET_KEY":"a"*64},{"DATABASE_URL":"sqlite:///:memory:"},
            {"DATABASE_URL":"postgresql://qa:replace-with-a-database-password@localhost:5432/qa"},
            {"CACHE_URL":""},{"DJANGO_ALLOWED_HOSTS":"*"},
            {"FRONTEND_URL":"http://admint.qa.invalid"},
            {"FRONTEND_URL":"https://attacker.invalid"},
            {"CSRF_TRUSTED_ORIGINS":"http://admint.qa.invalid"},
        ]:
            with self.subTest(fields=list(changes)):
                result=self.run_config(changes)
                self.assertNotEqual(result.returncode,0)
                self.assertIn("ImproperlyConfigured",result.stderr)

    def test_https_redirect_host_validation_and_csrf_enforcement(self):
        code="""
import django
django.setup()
from django.test import Client
c=Client(enforce_csrf_checks=True)
assert c.get('/api/health/',HTTP_HOST='admint.qa.invalid').status_code==301
assert c.get('/api/health/',HTTP_HOST='attacker.invalid',secure=True).status_code==400
r=c.get('/api/auth/session/',HTTP_HOST='admint.qa.invalid',secure=True)
assert r.status_code==200
assert r.cookies['csrftoken']['secure']
assert c.post('/api/auth/logout/',HTTP_HOST='admint.qa.invalid',secure=True).status_code==403
assert c.get('/api/health/',HTTP_HOST='backend',HTTP_X_FORWARDED_PROTO='https').status_code==200
"""
        result=self.run_config(code=code)
        self.assertEqual(result.returncode,0,result.stderr)

class ProxyAddressTests(SimpleTestCase):
    def setUp(self):
        cache.clear()
        self.factory=RequestFactory()
        self.middleware=TrustedProxyIPMiddleware(lambda request:None)

    def test_development_ignores_spoofed_proxy_header(self):
        request=self.factory.get('/',REMOTE_ADDR='127.0.0.1',HTTP_X_ADMINT_CLIENT_IP='203.0.113.1')
        self.middleware.process_request(request)
        self.assertEqual(request.META['REMOTE_ADDR'],'127.0.0.1')

    @override_settings(TRUST_PROXY_CLIENT_IP=True)
    def test_production_rate_limits_distinct_client_addresses(self):
        def request(ip):
            result=self.factory.get('/',REMOTE_ADDR='172.16.0.2',HTTP_X_ADMINT_CLIENT_IP=ip)
            self.middleware.process_request(result)
            return result
        for _ in range(30):self.assertFalse(limited(request('203.0.113.1')))
        self.assertTrue(limited(request('203.0.113.1')))
        self.assertFalse(limited(request('203.0.113.2')))
        for invalid in ['', 'not-an-ip', '203.0.113.1, 203.0.113.2']:
            self.assertEqual(request(invalid).META['REMOTE_ADDR'],'172.16.0.2')

class ProductionGeneratorTests(SimpleTestCase):
    def test_generator_uses_private_secrets_and_never_overwrites(self):
        import importlib.util
        spec=importlib.util.spec_from_file_location('deployment_configure',BACKEND.parent/'deploy'/'configure.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        with tempfile.TemporaryDirectory(prefix='admint-config-test-') as directory:
            path=Path(directory)/'.env.production'
            for domain in ['https://example.com','example.com/path','localhost','bad.com\nDJANGO_DEBUG=1']:
                with self.assertRaises(ValueError):module.configure(domain,path)
                self.assertFalse(path.exists())
            module.configure('admint.qa.invalid',path)
            original=path.read_bytes()
            with self.assertRaises(FileExistsError):module.configure('another.qa.invalid',path)
            self.assertEqual(path.read_bytes(),original)
            from dotenv import dotenv_values
            values=dotenv_values(path)
            self.assertGreaterEqual(len(values['DJANGO_SECRET_KEY']),50)
            self.assertGreaterEqual(len(values['POSTGRES_PASSWORD']),40)
            self.assertGreaterEqual(len(values['APP_DATABASE_PASSWORD']),40)
            self.assertNotEqual(values['POSTGRES_PASSWORD'],values['APP_DATABASE_PASSWORD'])
            self.assertNotEqual(values['POSTGRES_USER'],values['APP_DATABASE_USER'])
            self.assertEqual(values['DJANGO_DEBUG'],'0')
