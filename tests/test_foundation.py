import django
from django.apps import apps
from django.conf import settings

from heavychat.asgi import application


def test_django_foundation_settings_resolve():
    assert apps.ready
    assert django.VERSION[:2] == (5, 1)
    assert callable(application)
    assert settings.ASGI_APPLICATION == "heavychat.asgi.application"
    assert settings.DATABASES["default"]["ENGINE"] == "django.db.backends.sqlite3"
    assert isinstance(settings.SECRET_KEY, str) and settings.SECRET_KEY
    assert isinstance(settings.DEBUG, bool)
    assert isinstance(settings.OPENAI_PROXY_KEY, str)
    assert settings.LITECHAT_PROXY_BASE_URL.startswith("https://")
