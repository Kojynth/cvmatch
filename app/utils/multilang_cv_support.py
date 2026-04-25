"""
Multilingual CV support utilities
==================================

Provides:
- Language name → ISO 639-1 code mappings (covering common profile inputs in FR/EN)
- ISO code → display label for UI combos
- extract_profile_language_options(): build a combo list from profile["languages"]
- get_cv_culture_hint(): return cultural CV-writing directives for the LLM system prompt

Design principles:
- No dependency on language_policy.py (which is fr/en only and must not be changed).
- Culture hints guide tone, section order, date format, and emphasis only.
  They never suppress profile data — the profile_block remains the sole source of truth.
- The visual template chosen by the user (modern/tech/classic/…) is unaffected;
  hints only shape the generated JSON content.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Language name → ISO 639-1 code
# Keys are lowercase, accent-stripped variants of common profile inputs.
# ---------------------------------------------------------------------------

LANGUAGE_NAME_TO_ISO: Dict[str, str] = {
    # Français / French
    "francais": "fr",
    "français": "fr",
    "french": "fr",
    "fr": "fr",
    # Anglais / English
    "anglais": "en",
    "english": "en",
    "en": "en",
    # Allemand / German
    "allemand": "de",
    "german": "de",
    "deutsch": "de",
    "de": "de",
    # Espagnol / Spanish
    "espagnol": "es",
    "spanish": "es",
    "espanol": "es",
    "español": "es",
    "es": "es",
    # Italien / Italian
    "italien": "it",
    "italian": "it",
    "italiano": "it",
    "it": "it",
    # Portugais / Portuguese
    "portugais": "pt",
    "portuguese": "pt",
    "portugues": "pt",
    "português": "pt",
    "pt": "pt",
    # Néerlandais / Dutch
    "neerlandais": "nl",
    "néerlandais": "nl",
    "dutch": "nl",
    "nederlands": "nl",
    "nl": "nl",
    # Japonais / Japanese
    "japonais": "ja",
    "japanese": "ja",
    "日本語": "ja",
    "ja": "ja",
    # Chinois / Chinese
    "chinois": "zh",
    "chinese": "zh",
    "中文": "zh",
    "mandarin": "zh",
    "cantonais": "zh",
    "cantonese": "zh",
    "zh": "zh",
    # Coréen / Korean
    "coreen": "ko",
    "coréen": "ko",
    "korean": "ko",
    "한국어": "ko",
    "ko": "ko",
    # Arabe / Arabic
    "arabe": "ar",
    "arabic": "ar",
    "العربية": "ar",
    "ar": "ar",
    # Russe / Russian
    "russe": "ru",
    "russian": "ru",
    "русский": "ru",
    "ru": "ru",
    # Hindi
    "hindi": "hi",
    "हिंदी": "hi",
    "hi": "hi",
    # Polonais / Polish
    "polonais": "pl",
    "polish": "pl",
    "polski": "pl",
    "pl": "pl",
    # Turc / Turkish
    "turc": "tr",
    "turkish": "tr",
    "türkçe": "tr",
    "turkce": "tr",
    "tr": "tr",
    # Suédois / Swedish
    "suedois": "sv",
    "suédois": "sv",
    "swedish": "sv",
    "svenska": "sv",
    "sv": "sv",
    # Norvégien / Norwegian
    "norvegien": "no",
    "norvégien": "no",
    "norwegian": "no",
    "norsk": "no",
    "no": "no",
    # Danois / Danish
    "danois": "da",
    "danish": "da",
    "dansk": "da",
    "da": "da",
    # Finnois / Finnish
    "finnois": "fi",
    "finnish": "fi",
    "suomi": "fi",
    "fi": "fi",
    # Grec / Greek
    "grec": "el",
    "greek": "el",
    "ελληνικά": "el",
    "el": "el",
    # Tchèque / Czech
    "tcheque": "cs",
    "tchèque": "cs",
    "czech": "cs",
    "čeština": "cs",
    "cs": "cs",
    # Roumain / Romanian
    "roumain": "ro",
    "romanian": "ro",
    "română": "ro",
    "ro": "ro",
    # Hongrois / Hungarian
    "hongrois": "hu",
    "hungarian": "hu",
    "magyar": "hu",
    "hu": "hu",
}

# ---------------------------------------------------------------------------
# ISO 639-1 code → display label (shown in the UI combo)
# ---------------------------------------------------------------------------

ISO_TO_DISPLAY_LABEL: Dict[str, str] = {
    "fr": "Français",
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "it": "Italiano",
    "pt": "Português",
    "nl": "Nederlands",
    "ja": "日本語 (Japanese)",
    "zh": "中文 (Chinese)",
    "ko": "한국어 (Korean)",
    "ar": "العربية (Arabic)",
    "ru": "Русский (Russian)",
    "hi": "हिंदी (Hindi)",
    "pl": "Polski",
    "tr": "Türkçe",
    "sv": "Svenska",
    "no": "Norsk",
    "da": "Dansk",
    "fi": "Suomi",
    "el": "Ελληνικά (Greek)",
    "cs": "Čeština (Czech)",
    "ro": "Română",
    "hu": "Magyar (Hungarian)",
}

_FALLBACK_LANGUAGES: List[Tuple[str, str]] = [("fr", "Français"), ("en", "English")]


def _strip_accents_simple(text: str) -> str:
    """Lightweight accent normalization without unicodedata dependency.

    Covers the most common accented characters found in French/Spanish language names.
    """
    replacements = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a", "ä": "a",
        "î": "i", "ï": "i",
        "ô": "o", "ö": "o",
        "ù": "u", "û": "u", "ü": "u",
        "ç": "c",
        "ñ": "n",
    }
    result = text.lower()
    for accented, plain in replacements.items():
        result = result.replace(accented, plain)
    return result


def _language_name_to_iso(name: str) -> Optional[str]:
    """Convert a free-text language name to an ISO 639-1 code.

    Tries exact match first (after normalization), then prefix match.
    Returns None if no mapping is found.
    """
    if not name or not str(name).strip():
        return None

    normalized = _strip_accents_simple(str(name).strip())

    # Exact match (normalized)
    if normalized in LANGUAGE_NAME_TO_ISO:
        return LANGUAGE_NAME_TO_ISO[normalized]

    # Exact match (original, for non-latin scripts like 日本語, 한국어…)
    raw = str(name).strip()
    if raw in LANGUAGE_NAME_TO_ISO:
        return LANGUAGE_NAME_TO_ISO[raw]

    # Prefix match on normalized key (e.g. "anglai" → "anglais" → "en")
    for key, code in LANGUAGE_NAME_TO_ISO.items():
        if len(normalized) >= 3 and key.startswith(normalized):
            return code
        if len(normalized) >= 3 and normalized.startswith(key):
            return code

    return None


def extract_profile_language_options(
    profile_json: Dict[str, Any],
    *,
    fallback: bool = True,
) -> List[Tuple[str, str]]:
    """Build a combo list from profile_json["languages"].

    Returns a deduplicated list of (iso_code, display_label) tuples in profile order.
    Falls back to [("fr", "Français"), ("en", "English")] if the profile has no
    recognizable languages.

    Args:
        profile_json: The full profile dict (as returned by profile_json.py).
        fallback: When False, return only languages explicitly declared in the
            profile instead of adding the default FR/EN choices.

    Returns:
        List of (iso_code, display_label) tuples for use in a QComboBox.
    """
    if not isinstance(profile_json, dict):
        if not fallback:
            return []
        return _FALLBACK_LANGUAGES[:]

    languages_raw = profile_json.get("languages")
    if not isinstance(languages_raw, list) or not languages_raw:
        if not fallback:
            return []
        return _FALLBACK_LANGUAGES[:]

    seen: set = set()
    result: List[Tuple[str, str]] = []

    for item in languages_raw:
        # Support both dict items and bare strings
        if isinstance(item, dict):
            lang_name = str(item.get("language") or item.get("name") or "").strip()
        elif isinstance(item, str):
            lang_name = item.strip()
        else:
            continue

        if not lang_name:
            continue

        iso = _language_name_to_iso(lang_name)
        if iso is None:
            continue

        if iso in seen:
            continue
        seen.add(iso)

        # Use the canonical display label when available, otherwise use the raw name
        label = ISO_TO_DISPLAY_LABEL.get(iso, lang_name)
        result.append((iso, label))

    if result:
        return result
    return _FALLBACK_LANGUAGES[:] if fallback else []


# ---------------------------------------------------------------------------
# Culture hints — advisory directives for the LLM system prompt
#
# These hints guide TONE, SECTION ORDER, DATE FORMAT, and EMPHASIS only.
# They NEVER suppress profile data. The profile_block remains the sole
# source of truth. The visual template (HTML/CSS) is unaffected.
# ---------------------------------------------------------------------------

_CULTURE_HINTS: Dict[str, str] = {
    "fr": (
        "CV cultural conventions for France:\n"
        "- Preferred section order: accroche/profil, expériences professionnelles, "
        "formation, compétences, langues, centres d'intérêt (if present in profile).\n"
        "- Date format: MM/YYYY.\n"
        "- Accroche (summary): 2–4 lines, focused on the target role and 2 key strengths "
        "drawn from the profile.\n"
        "- Tone: professional, concise, no first-person pronouns.\n"
        "- Compétences: group by category (e.g. Langages, Outils, Méthodes).\n"
        "- Avoid clichés (dynamique, rigoureux, passionné) — use concrete profile facts instead."
    ),
    "en": (
        "CV cultural conventions (English — Western / US / UK / Australia):\n"
        "- Preferred section order: professional summary, work experience, education, "
        "skills, certifications, languages.\n"
        "- Start every experience bullet with a strong action verb; quantify impact "
        "when the profile provides metrics or outcomes.\n"
        "- Professional summary: 2–3 lines; candidate-focused (role, key strength, top achievement).\n"
        "- Skills section: group by category (e.g. Languages & Frameworks, Tools, Methodologies).\n"
        "- Use consistent date format across the CV (prefer MM/YYYY or YYYY).\n"
        "- Tone: confident, direct, achievement-oriented; no first-person pronouns."
    ),
    "de": (
        "CV cultural conventions for Germany (Lebenslauf):\n"
        "- Strict reverse chronological order; precise dates (MM.YYYY) are mandatory for every entry.\n"
        "- Section order: Persönliche Daten, Berufserfahrung, Ausbildung, Kenntnisse, "
        "Sprachen, Interessen (if present in profile).\n"
        "- If the profile contains vocational training (Ausbildung), include it as a dedicated section.\n"
        "- Tone: formal, precise, fact-based. Avoid subjective adjectives; let facts speak.\n"
        "- Keep descriptions concise; German recruiters expect density over narrative.\n"
        "- If the profile shows date gaps, note them neutrally (e.g. Elternzeit, Weiterbildung)."
    ),
    "es": (
        "CV cultural conventions for Spain / Latin America (Currículum Vítae):\n"
        "- Preferred section order: datos personales, perfil profesional, experiencia laboral, "
        "formación académica, idiomas, habilidades, otros (if present in profile).\n"
        "- Date format: MM/AAAA.\n"
        "- Perfil profesional: 2–4 lines summarising the candidate's main strengths from the profile.\n"
        "- Tone: formal but approachable; use usted register; no first-person pronouns.\n"
        "- Skills: list technical and soft skills in separate subsections."
    ),
    "it": (
        "CV cultural conventions for Italy (Curriculum Vitae):\n"
        "- Preferred section order: dati personali, profilo professionale, esperienze lavorative, "
        "formazione, competenze, lingue, interessi (if present in profile).\n"
        "- Date format: MM/AAAA.\n"
        "- Profilo professionale: 2–4 lines drawn from profile strengths and key achievements.\n"
        "- Tone: formal and precise; avoid excessive superlatives.\n"
        "- Competenze: group technical skills by category."
    ),
    "pt": (
        "CV cultural conventions for Portugal / Brazil (Currículo):\n"
        "- Preferred section order: dados pessoais, objetivo profissional, experiências, "
        "formação académica, competências, idiomas, outros (if present in profile).\n"
        "- Date format: MM/AAAA.\n"
        "- Objetivo profissional: 1–2 lines expressing the candidate's career goal.\n"
        "- Tone: formal; avoid first-person; lead bullets with action verbs."
    ),
    "ja": (
        "CV cultural conventions for Japan:\n"
        "- Tone must be formal and humble (丁寧語); avoid self-promotion superlatives.\n"
        "- Preferred section order: 自己PR (self-introduction), 学歴 (education), "
        "職歴 (work history), 資格・免許 (certifications), 趣味・特技 (if present in profile).\n"
        "- Date format: YYYY年MM月 (use Western year; Japanese era is optional).\n"
        "- 自己PR: write with modest, concrete achievements; start with the candidate's "
        "core strength, then 2–3 proof points drawn from the profile.\n"
        "- If hobbies or interests are in the profile, include them in a 趣味・特技 section.\n"
        "- Use consistent Japanese script (漢字/ひらがな/カタカナ) for all narrative fields; "
        "keep technical product names and company names in their original script."
    ),
    "zh": (
        "CV cultural conventions for China (简历 style):\n"
        "- If the candidate is a recent graduate: put education first; "
        "otherwise work experience first.\n"
        "- Date format: YYYY年MM月.\n"
        "- Highlight academic background, research output, awards, and notable projects "
        "from the profile.\n"
        "- Include a 个人技能 (personal skills) section grouping technical skills from the profile.\n"
        "- If the profile contains awards or honors, surface them in a 获奖情况 section.\n"
        "- Summary: concise 求职意向 (job objective) followed by a brief 个人简介.\n"
        "- Keep narrative tight: prefer short, factual bullet points over long paragraphs."
    ),
    "ko": (
        "CV cultural conventions for Korea (이력서 style):\n"
        "- Preferred section order: 인적사항 (personal info), 학력 (education), "
        "경력 (work history), 자격증 (certifications), 어학 (language scores), "
        "자기소개서 (self-introduction).\n"
        "- Education (학력): include exact admission and graduation dates (YYYY.MM).\n"
        "- Work history (경력): include company name, department, position, and period.\n"
        "- Include a 자기소개서 paragraph drawing on the profile: growth background, "
        "core strength, motivation. Keep it sincere and achievement-focused.\n"
        "- Language scores (e.g. TOEIC, TOEFL, HSK) should be listed prominently "
        "if present in the profile.\n"
        "- Tone: formal, sincere, concrete. Avoid inflated claims not supported by the profile."
    ),
    "ar": (
        "CV cultural conventions for Arab countries (السيرة الذاتية):\n"
        "- Right-to-left text direction; all narrative fields in Arabic script.\n"
        "- Section order: البيانات الشخصية, الهدف الوظيفي, الخبرات العملية, "
        "المؤهلات العلمية, المهارات, اللغات.\n"
        "- Include a brief هدف وظيفي (career objective) drawn from the profile summary.\n"
        "- Language proficiency (Arabic, English, French) should be listed explicitly with levels.\n"
        "- Tone: formal and respectful; use standard Modern Standard Arabic (الفصحى) for all text.\n"
        "- Certifications and training courses should be listed prominently if in the profile."
    ),
    "ru": (
        "CV cultural conventions for Russia (Резюме):\n"
        "- Preferred section order: личные данные, цель, опыт работы, образование, "
        "навыки, языки, дополнительно (if present in profile).\n"
        "- Date format: MM.YYYY.\n"
        "- Цель (objective): 1–2 lines expressing the candidate's job target.\n"
        "- Опыт работы: list in reverse chronological order with precise dates.\n"
        "- Tone: formal and professional; bullet facts concisely."
    ),
}

_DEFAULT_CULTURE_HINT = (
    "CV cultural conventions (international standard):\n"
    "- Maintain a clear professional structure: summary, experience, education, skills, languages.\n"
    "- Use reverse chronological order for experience and education.\n"
    "- Avoid first-person pronouns; start bullets with strong action verbs.\n"
    "- Keep content factual and achievement-oriented, drawing only from the profile data.\n"
    "- Adapt date format to the target language's norms "
    "(e.g. YYYY-MM for ISO, MM/YYYY for European)."
)


def get_cv_culture_hint(language_code: str) -> str:
    """Return LLM-ready cultural CV-writing directives for the given ISO 639-1 code.

    These are advisory guidelines for tone, section order, date format, and emphasis.
    They never instruct the LLM to suppress or invent profile data.

    Args:
        language_code: ISO 639-1 code (e.g. "ja", "ko", "en", "fr").

    Returns:
        A multi-line string suitable for injection into the LLM system prompt.
    """
    return _CULTURE_HINTS.get(str(language_code or "").lower().strip(), _DEFAULT_CULTURE_HINT)
