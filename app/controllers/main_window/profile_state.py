"""Profile state management coordinator."""

from __future__ import annotations

from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional, Tuple

from app.config import DEFAULT_PII_CONFIG
from app.logging.safe_logger import get_safe_logger
from app.models.database import get_session
from app.models.user_profile import UserProfile

from .base import Coordinator, SimpleCoordinator
from .view_models import ProfileSnapshot, ProfileSummary

logger = get_safe_logger(__name__, cfg=DEFAULT_PII_CONFIG)


@dataclass(slots=True)
class ProfileFormData:
    """Represents the editable fields of a user profile."""

    name: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    linkedin_url: Optional[str] = None
    preferred_template: Optional[str] = None
    preferred_language: Optional[str] = None
    learning_enabled: Optional[bool] = None


SessionFactory = Callable[[], AbstractContextManager]


class ProfileStateCoordinator(SimpleCoordinator, Coordinator):
    """Handles profile persistence and field updates."""

    __slots__ = ("_session_factory",)

    _PROFILE_ATTRS = (
        "name",
        "email",
        "phone",
        "linkedin_url",
        "preferred_template",
        "preferred_language",
        "learning_enabled",
    )

    def __init__(self, session_factory: SessionFactory | None = None) -> None:
        super().__init__()
        self._session_factory: SessionFactory = session_factory or get_session

    def list_profiles(self) -> List[ProfileSummary]:
        """Return lightweight summaries of available profiles."""

        with self._session_factory() as session:
            profiles = (
                session.query(UserProfile)
                .order_by(UserProfile.updated_at.desc())
                .all()
            )

        return [
            ProfileSummary(
                id=profile.id,
                name=profile.name,
                email=profile.email,
                updated_at=getattr(profile, "updated_at", None),
            )
            for profile in profiles
            if profile.id is not None
        ]

    def load_profile(self, profile_id: int) -> Optional[UserProfile]:
        """Return the persisted profile for the given identifier."""

        with self._session_factory() as session:
            profile = session.get(UserProfile, profile_id)
            if profile is None:
                return None
            session.expunge(profile)
            return profile

    def save_profile(
        self,
        profile: UserProfile,
        form_data: ProfileFormData,
        *,
        validate: bool = True,
        coalesce: bool = False,
    ) -> Tuple[bool, Optional[str]]:
        """Persist profile updates, returning success flag and optional error."""

        snapshot = self._snapshot(profile)
        self._apply_form_data(profile, form_data, coalesce=coalesce)

        if validate:
            if not profile.name or not profile.email:
                self._restore(profile, snapshot)
                return False, "Le nom et l'email sont obligatoires."
            if "@" not in (profile.email or ""):
                self._restore(profile, snapshot)
                return False, "L'adresse email n'est pas valide."

        personal_snapshot = dict(getattr(profile, "extracted_personal_info", None) or {})
        self._sync_extracted_personal_info(profile)

        try:
            with self._session_factory() as session:
                session.merge(profile)
                session.commit()
        except Exception as exc:  # pragma: no cover - commits are integration tested
            self._restore(profile, snapshot)
            profile.extracted_personal_info = personal_snapshot
            return False, str(exc)

        try:
            from app.utils.profile_json import (
                build_profile_json_from_extracted_profile,
                has_profile_json_content,
                save_profile_json_cache,
            )

            profile_json = build_profile_json_from_extracted_profile(profile)
            if has_profile_json_content(profile_json) and profile.id:
                save_profile_json_cache(profile.id, profile_json)
        except Exception as exc:
            logger.warning("Unable to save profile JSON cache: %s", exc)

        return True, None

    def update_linkedin_pdf(
        self,
        profile: UserProfile,
        *,
        pdf_path: Optional[str],
        checksum: Optional[str],
        uploaded_at,
    ) -> Tuple[bool, Optional[str]]:
        """Persist LinkedIn PDF metadata for the profile."""

        snapshot = self._snapshot_linkedin(profile)
        profile.linkedin_pdf_path = pdf_path
        profile.linkedin_pdf_checksum = checksum
        profile.linkedin_pdf_uploaded_at = uploaded_at

        try:
            with self._session_factory() as session:
                session.merge(profile)
                session.commit()
        except Exception as exc:  # pragma: no cover
            self._restore_linkedin(profile, snapshot)
            return False, str(exc)

        return True, None

    # ------------------------------------------------------------------
    # View-model helpers
    # ------------------------------------------------------------------
    def to_snapshot(self, profile: UserProfile) -> ProfileSnapshot:
        """Convert a full profile into a UI-friendly snapshot."""

        extracted_sections: Dict[str, object] = {}
        for attr, value in profile.__dict__.items():
            if attr.startswith("extracted_"):
                section = attr.replace("extracted_", "")
                extracted_sections[section] = value

        metadata = {
            "total_cvs_generated": getattr(profile, "total_cvs_generated", None),
            "total_cvs_validated": getattr(profile, "total_cvs_validated", None),
            "average_rating": getattr(profile, "average_rating", None),
            "model_version": getattr(getattr(profile, "model_version", None), "value", None),
        }

        return ProfileSnapshot(
            id=getattr(profile, "id", None),
            name=profile.name or "",
            email=profile.email or "",
            phone=getattr(profile, "phone", None),
            linkedin_url=getattr(profile, "linkedin_url", None),
            preferred_template=getattr(profile, "preferred_template", None),
            preferred_language=getattr(profile, "preferred_language", None),
            learning_enabled=getattr(profile, "learning_enabled", None),
            model_version=metadata["model_version"],
            extracted_sections=extracted_sections,
            metadata=metadata,
        )

    def _apply_form_data(
        self,
        profile: UserProfile,
        form_data: ProfileFormData,
        *,
        coalesce: bool,
    ) -> None:
        """Apply form data to the profile, optionally preserving existing values."""

        def assign(attr: str, value):
            if coalesce and (value is None or (isinstance(value, str) and not value.strip())):
                return
            setattr(profile, attr, value)

        assign("name", form_data.name)
        assign("email", form_data.email)
        assign("phone", form_data.phone)
        assign("linkedin_url", form_data.linkedin_url)
        assign("preferred_template", form_data.preferred_template)
        assign("preferred_language", form_data.preferred_language)
        if form_data.learning_enabled is not None:
            assign("learning_enabled", bool(form_data.learning_enabled))

    def _snapshot(self, profile: UserProfile) -> Dict[str, object]:
        """Take a shallow snapshot of profile attributes."""

        return {attr: getattr(profile, attr) for attr in self._PROFILE_ATTRS}

    def _restore(self, profile: UserProfile, snapshot: Dict[str, object]) -> None:
        """Restore profile attributes from a snapshot."""

        for attr, value in snapshot.items():
            setattr(profile, attr, value)

    def _sync_extracted_personal_info(self, profile: UserProfile) -> None:
        personal_info = dict(getattr(profile, "extracted_personal_info", None) or {})

        def _assign(field: str, value: Optional[str]) -> None:
            cleaned = (value or "").strip()
            if cleaned:
                personal_info[field] = cleaned

        _assign("full_name", profile.name)
        _assign("email", profile.email)
        _assign("phone", profile.phone)
        _assign("linkedin_url", profile.linkedin_url)
        profile.extracted_personal_info = personal_info

    def _snapshot_linkedin(self, profile: UserProfile) -> Dict[str, object]:
        """Snapshot LinkedIn-specific attributes."""

        return {
            "linkedin_pdf_path": getattr(profile, "linkedin_pdf_path", None),
            "linkedin_pdf_checksum": getattr(profile, "linkedin_pdf_checksum", None),
            "linkedin_pdf_uploaded_at": getattr(profile, "linkedin_pdf_uploaded_at", None),
        }

    def _restore_linkedin(self, profile: UserProfile, snapshot: Dict[str, object]) -> None:
        """Restore LinkedIn-specific attributes."""

        for attr, value in snapshot.items():
            setattr(profile, attr, value)
