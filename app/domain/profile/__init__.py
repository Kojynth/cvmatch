"""Profile-domain facade."""

from .date_support import derive_date_support_fields, infer_date_precision
from .artifact_mappers import (
    map_awards,
    map_certifications,
    map_projects,
    map_publications,
    map_references,
    map_volunteering,
    normalize_interests,
)
from .personal_info import (
    extract_personal_info,
    merge_personal_links,
    normalize_link_url,
    normalize_links,
)
from .roundtrip import (
    apply_profile_json_to_profile,
    build_empty_profile_json,
    has_profile_json_content,
    merge_profile_json,
    normalize_profile_json,
)
from .section_mappers import map_education, map_experiences
from .skill_language_mappers import (
    map_languages,
    map_skills,
    map_soft_skills,
    parse_language_string,
)
from .service import (
    build_profile_json_from_source,
)

__all__ = [
    "derive_date_support_fields",
    "infer_date_precision",
    "extract_personal_info",
    "map_awards",
    "map_certifications",
    "map_experiences",
    "map_education",
    "map_languages",
    "map_projects",
    "map_publications",
    "map_references",
    "map_skills",
    "map_soft_skills",
    "map_volunteering",
    "merge_personal_links",
    "normalize_interests",
    "normalize_link_url",
    "normalize_links",
    "parse_language_string",
    "apply_profile_json_to_profile",
    "build_empty_profile_json",
    "build_profile_json_from_source",
    "has_profile_json_content",
    "merge_profile_json",
    "normalize_profile_json",
]
