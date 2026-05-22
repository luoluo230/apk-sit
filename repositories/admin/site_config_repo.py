"""Site-config repository wrappers."""

from __future__ import annotations

from services.company_profile import get_company_profile, save_company_profile
from services.portal_content import (
    get_dev_portal_content,
    get_player_portal_content,
    save_dev_portal_content,
    save_player_portal_content,
)


def get_company():
    return get_company_profile()


def save_company(payload):
    save_company_profile(payload)


def get_player_portal():
    return get_player_portal_content()


def get_dev_portal():
    return get_dev_portal_content()


def save_player_portal(payload):
    save_player_portal_content(payload)


def save_dev_portal(payload):
    save_dev_portal_content(payload)
