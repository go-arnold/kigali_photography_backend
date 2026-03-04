"""Pytest / Django test configuration.
Ensures Django settings are loaded before any test runs.
"""

import django
from django.conf import settings


def pytest_configure():
    import os

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
