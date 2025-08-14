"""Constants for use with the Catalyst SD-WAN SSoT app."""

from django.conf import settings


def _read_settings() -> dict:
    config = settings.PLUGINS_CONFIG["nautobot_ssot"]
    return {key[13:]: value for key, value in config.items() if key.startswith("catalyst_sdwan_")}


# Import config vars from nautobot_config.py
PLUGIN_CFG = _read_settings()
