"""Photo-invariant HTML helpers.

Product invariant: the profile photo must appear in the rendered CV regardless
of user HTML edits, template choice, or history reopen. When raw_html is
saved from the user's in-editor HTML (`raw_html_is_user_edited=True`) and the
embedded photo is missing, we must **inject** the photo without discarding
the user's other edits — never regenerate from template, as that would
destroy authorial control.

Reference incident: Mistral AI 2026-04-21 shipped a CV without its photo
because the prior preview bypass was turned off (correctly, to preserve user
edits) but there was no non-destructive alternative to re-inject the photo.
See AGENTS.md invariants and CLAUDE.md `Never break:` list.
"""

from __future__ import annotations

import re
from typing import Any


_PROFILE_IMG_PATTERN = re.compile(
    r"<img[^>]*class\s*=\s*['\"][^'\"]*profile-photo[^'\"]*['\"][^>]*>",
    re.IGNORECASE,
)
_PROFILE_IMG_SRC_PATTERN = re.compile(
    r"src\s*=\s*['\"]([^'\"]+)['\"]",
    re.IGNORECASE,
)
_CV_HEADER_OPEN_TAG = re.compile(
    r'(<(?:div\s+[^>]*class\s*=\s*"[^"]*cv-header[^"]*"[^>]*|header\b[^>]*)>)',
    re.IGNORECASE,
)
_BODY_OPEN_TAG = re.compile(r"(<body\b[^>]*>)", re.IGNORECASE)


def raw_html_has_embedded_profile_photo(raw_html: Any) -> bool:
    """Return True when raw_html already contains a data-URI profile photo."""
    text = str(raw_html or "")
    if not text:
        return False
    match = _PROFILE_IMG_PATTERN.search(text)
    if not match:
        return False
    src_match = _PROFILE_IMG_SRC_PATTERN.search(match.group(0))
    if not src_match:
        return False
    return str(src_match.group(1) or "").strip().lower().startswith("data:image/")


def ensure_photo_in_raw_html(raw_html: Any, photo_base64: Any) -> str:
    """Inject profile photo into user-edited HTML if missing.

    Non-destructive: returns raw_html unchanged when photo is already embedded,
    when photo_base64 is empty, or when no suitable injection point exists.
    Preserves every other byte of user HTML.

    Injection priority:
      1. First `<div class="cv-header …">` or `<header …>` tag — template-idiomatic.
      2. Fallback: right after `<body …>` opening tag.
      3. Identity pass: malformed HTML with no insertion point — return as-is
         rather than corrupt the markup.
    """
    raw = str(raw_html or "")
    if not raw:
        return raw
    photo = str(photo_base64 or "").strip()
    if not photo:
        return raw
    if raw_html_has_embedded_profile_photo(raw):
        return raw

    img_tag = (
        f'<img src="data:image/jpeg;base64,{photo}" '
        f'alt="Photo de profil" class="profile-photo" />'
    )

    injected = _CV_HEADER_OPEN_TAG.sub(r"\1" + img_tag, raw, count=1)
    if injected != raw:
        return injected

    injected = _BODY_OPEN_TAG.sub(r"\1" + img_tag, raw, count=1)
    if injected != raw:
        return injected

    return raw
