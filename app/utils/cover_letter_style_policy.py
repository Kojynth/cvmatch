"""
Cover-letter style policy and prompt builder.

This module centralizes content-style inference so llm_worker stays focused on
pipeline orchestration.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Iterable, List, Optional, Tuple


COVER_LETTER_STYLE_ANALYSIS_KEY = "cover_letter_generation_style"

VALID_STYLE_MODES = {
    "technical_precision",
    "leadership_impact",
    "client_business",
    "balanced_professional",
}


def _dedup_preserve(items: Iterable[str]) -> List[str]:
    seen = set()
    output: List[str] = []
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        output.append(text)
    return output


def _trim_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    return text[: max_chars - 3].rstrip() + "..."


def _normalize_language(value: Optional[str]) -> str:
    normalized = str(value or "").strip().lower()
    if normalized.startswith("en"):
        return "en"
    return "fr"


def _normalize_template_name(value: Optional[str]) -> str:
    key = str(value or "").strip().lower()
    if key in {"modern", "classic", "tech", "creative", "minimal"}:
        return key
    return "modern"


def _collect_offer_keywords(analysis: Dict[str, Any]) -> List[str]:
    keywords: List[str] = []
    for key in (
        "keywords",
        "skills",
        "tech_keywords",
        "soft_keywords",
        "tools",
        "responsibilities",
        "certifications",
    ):
        value = analysis.get(key)
        if isinstance(value, list):
            keywords.extend(str(item) for item in value)
        elif isinstance(value, str):
            keywords.extend(part.strip() for part in value.split(",") if part.strip())
    return _dedup_preserve(keywords)


def _score_markers(text: str, markers: Tuple[str, ...]) -> int:
    lowered = str(text or "").lower()
    if not lowered:
        return 0
    return sum(1 for marker in markers if marker in lowered)


def _instruction_requests_style_change(user_instruction: Optional[str]) -> bool:
    text = str(user_instruction or "").strip().lower()
    if not text:
        return False
    markers = (
        "style",
        "tone",
        "ton",
        "formal",
        "formel",
        "technical",
        "technique",
        "business",
        "commercial",
        "leadership",
        "manager",
        "moins",
        "less",
        "plus",
        "more",
    )
    return any(marker in text for marker in markers)


def _mode_marker_patterns() -> Dict[str, Tuple[str, ...]]:
    return {
        "technical_precision": (
            r"\btechnical\b",
            r"\btechnique\b",
            r"\btech\b",
            r"\bstack\b",
            r"\bengineering\b",
            r"\bingenieur\b",
            r"\bcyber\b",
            r"\bdevops\b",
        ),
        "leadership_impact": (
            r"\bleadership\b",
            r"\blead\b",
            r"\bmanager\b",
            r"\bmanagement\b",
            r"\bcoordination\b",
            r"\bpilotage\b",
            r"\bownership\b",
            r"\bstrategy\b",
        ),
        "client_business": (
            r"\bbusiness\b",
            r"\bcommercial\b",
            r"\bclient\b",
            r"\bcustomer\b",
            r"\bsales\b",
            r"\bstakeholder\b",
            r"\bmetier\b",
        ),
        "balanced_professional": (
            r"\bbalanced\b",
            r"\bequilibre\b",
            r"\bneutral\b",
            r"\bneutre\b",
            r"\bprofessional\b",
            r"\bprofessionnel\b",
        ),
    }


def _count_mode_hits_with_negation(text: str, patterns: Tuple[str, ...]) -> Tuple[int, int]:
    positive = 0
    negative = 0
    for pattern in patterns:
        for match in re.finditer(pattern, text, flags=re.IGNORECASE):
            start = match.start()
            end = match.end()
            before = text[max(0, start - 24) : start]
            after = text[end : min(len(text), end + 16)]
            neg_before = re.search(
                r"(?:\b(?:not|no|less|without|pas|moins|sans|non)\b(?:\s+\w+){0,1}\s*)$",
                before,
                flags=re.IGNORECASE,
            )
            neg_after = re.search(
                r"^\s*(?:not|no|less|without|pas|moins|sans|non)\b",
                after,
                flags=re.IGNORECASE,
            )
            if neg_before or neg_after:
                negative += 1
            else:
                positive += 1
    return positive, negative


def _extract_mode_from_user_instruction(user_instruction: Optional[str]) -> Optional[str]:
    text = str(user_instruction or "").strip().lower()
    if not text:
        return None

    mode_patterns = _mode_marker_patterns()
    stats: Dict[str, Dict[str, int]] = {}
    for mode, patterns in mode_patterns.items():
        pos, neg = _count_mode_hits_with_negation(text, patterns)
        stats[mode] = {"pos": pos, "neg": neg, "score": (pos - (2 * neg))}

    best_mode = max(stats, key=lambda key: stats[key]["score"])
    best_score = stats[best_mode]["score"]
    if best_score > 0:
        return best_mode

    # Explicit "less technical" / "moins technique" style requests should not
    # map back to technical_precision. Fall back to a neutral tone.
    negated_mode = max(stats, key=lambda key: stats[key]["neg"])
    if stats[negated_mode]["neg"] > 0 and stats[negated_mode]["pos"] == 0:
        return "balanced_professional"

    return None


def _extract_previous_style_mode(analysis: Dict[str, Any]) -> Optional[str]:
    payload = analysis.get(COVER_LETTER_STYLE_ANALYSIS_KEY)
    mode: Optional[str] = None
    if isinstance(payload, dict):
        raw = payload.get("mode")
        mode = str(raw).strip() if raw else None
    elif isinstance(payload, str):
        mode = payload.strip()
    if mode in VALID_STYLE_MODES:
        return mode
    return None


def _resolve_style_profile(
    *,
    language_code: str,
    template_key: str,
    offer_text: str,
    keywords: List[str],
    forced_mode: Optional[str] = None,
) -> Dict[str, Any]:
    corpus = f"{offer_text}\n" + " | ".join(keywords)
    technical_score = _score_markers(
        corpus,
        (
            "python",
            "sql",
            "cloud",
            "aws",
            "azure",
            "gcp",
            "linux",
            "docker",
            "api",
            "devops",
            "cyber",
            "siem",
            "soc",
            "audit",
            "iso",
            "owasp",
            "incident",
            "architecture",
            "data",
        ),
    )
    leadership_score = _score_markers(
        corpus,
        (
            "manager",
            "lead",
            "leadership",
            "strategy",
            "stakeholder",
            "governance",
            "coordination",
            "budget",
            "roadmap",
        ),
    )
    business_score = _score_markers(
        corpus,
        (
            "client",
            "customer",
            "sales",
            "business",
            "growth",
            "partnership",
            "account",
            "market",
            "revenue",
        ),
    )

    if forced_mode in VALID_STYLE_MODES:
        mode = forced_mode
    elif technical_score >= max(3, leadership_score, business_score):
        mode = "technical_precision"
    elif leadership_score >= max(3, technical_score, business_score):
        mode = "leadership_impact"
    elif business_score >= max(3, technical_score, leadership_score):
        mode = "client_business"
    else:
        mode = "balanced_professional"

    labels = {
        "technical_precision": "Technical precision" if language_code == "en" else "Precision technique",
        "leadership_impact": "Leadership impact" if language_code == "en" else "Impact leadership",
        "client_business": "Client/business value" if language_code == "en" else "Valeur client/metier",
        "balanced_professional": "Balanced professional" if language_code == "en" else "Professionnel equilibre",
    }
    template_hint = {
        "modern": "Ton moderne et direct, phrases courtes, tres specifique.",
        "classic": "Ton formel et corporate, vocabulaire sobre.",
        "tech": "Ton technique/pro: concret, oriente realisations et stack verifiable.",
        "creative": "Ton dynamique, orientation projets/impact, mais professionnel.",
        "minimal": "Ton clair et epure, focalise impact et lisibilite.",
    }.get(template_key, "Ton professionnel et specifique.")
    return {
        "mode": mode,
        "label": labels.get(mode, labels["balanced_professional"]),
        "template_hint": template_hint,
        "scores": {
            "technical": technical_score,
            "leadership": leadership_score,
            "business": business_score,
        },
    }


def build_cover_letter_generation_payload(
    *,
    offer_data: Optional[Dict[str, Any]],
    template: Optional[str],
    preferred_language: Optional[str],
    profile_name: str,
    profile_block: str,
    user_instruction: Optional[str] = None,
    freeze_previous_style: bool = False,
) -> Dict[str, Any]:
    offer_payload = offer_data if isinstance(offer_data, dict) else {}
    analysis = offer_payload.get("analysis")
    analysis = analysis if isinstance(analysis, dict) else {}
    keywords = _collect_offer_keywords(analysis)

    language = analysis.get("language") or preferred_language or "fr"
    language_code = _normalize_language(language)
    placeholder = "[TO COMPLETE]" if language_code == "en" else "[A COMPLETER]"
    template_key = _normalize_template_name(template)
    job_title = offer_payload.get("job_title")
    company = offer_payload.get("company")
    offer_text = offer_payload.get("text")
    offer_keywords = (
        analysis.get("offer_keywords_llm")
        if isinstance(analysis.get("offer_keywords_llm"), dict)
        else None
    )

    previous_mode = _extract_previous_style_mode(analysis)
    instruction_mode = _extract_mode_from_user_instruction(user_instruction)
    style_change_requested = _instruction_requests_style_change(user_instruction)
    forced_mode: Optional[str] = None
    style_source = "auto_offer_analysis"
    freeze_applied = False
    instruction_override = False

    if instruction_mode:
        forced_mode = instruction_mode
        style_source = "user_instruction_override"
        instruction_override = True
    elif freeze_previous_style and previous_mode and not style_change_requested:
        forced_mode = previous_mode
        style_source = "frozen_previous_regeneration"
        freeze_applied = True
    elif style_change_requested:
        style_source = "user_instruction_auto_recompute"

    style_profile = _resolve_style_profile(
        language_code=language_code,
        template_key=template_key,
        offer_text=str(offer_text or ""),
        keywords=keywords,
        forced_mode=forced_mode,
    )

    if language_code == "en":
        skeleton = f"Subject: Application - {job_title} ({company})\n\nDear Hiring Manager,\n\n<Paragraph 1>\n\n<Paragraph 2>\n\n<Paragraph 3>\n\nSincerely,\n\n{profile_name or placeholder}"
    else:
        skeleton = f"Objet: Candidature - {job_title} ({company})\n\nMadame, Monsieur,\n\n<Paragraphe 1>\n\n<Paragraphe 2>\n\n<Paragraphe 3>\n\nJe vous prie d'agreer, Madame, Monsieur, l'expression de mes salutations distinguees.\n\n{profile_name or placeholder}"

    prompt = f"""
LANGUE: {language_code}
STYLE DE GENERATION (contenu): {style_profile["label"]} ({style_profile["mode"]})
STYLE SOURCE: {style_source}
STYLE CONTEXTE (template UI): {template_key} ({style_profile["template_hint"]})

OFFRE CIBLE:
- Poste: {job_title}
- Entreprise: {company}
- Description:
{_trim_text(offer_text, 2000 if isinstance(offer_keywords, dict) else 3000)}

OFFER_KEYWORDS_JSON:
{_trim_text(json.dumps(offer_keywords, indent=2, ensure_ascii=False), 1200) if isinstance(offer_keywords, dict) else "N/A"}

DONNEES CANDIDAT:
{profile_block}

INSTRUCTION UTILISATEUR:
{_trim_text(user_instruction, 600)}

SORTIE OBLIGATOIRE:
- Texte brut uniquement (pas de markdown)
- Utilise uniquement des faits presents dans les donnees candidat
- Longueur max: 1 page

STRUCTURE:
{skeleton}
""".strip()

    return {
        "prompt": prompt,
        "style_mode": style_profile["mode"],
        "style_source": style_source,
        "freeze_applied": freeze_applied,
        "instruction_override": instruction_override,
        "style_profile": {
            "mode": style_profile["mode"],
            "label": style_profile["label"],
            "source": style_source,
            "freeze_applied": freeze_applied,
            "instruction_override": instruction_override,
            "template_hint": style_profile["template_hint"],
            "scores": style_profile["scores"],
        },
    }


def build_cover_letter_generation_prompt(
    *,
    offer_data: Optional[Dict[str, Any]],
    template: Optional[str],
    preferred_language: Optional[str],
    profile_name: str,
    profile_block: str,
    user_instruction: Optional[str] = None,
    freeze_previous_style: bool = False,
) -> str:
    payload = build_cover_letter_generation_payload(
        offer_data=offer_data,
        template=template,
        preferred_language=preferred_language,
        profile_name=profile_name,
        profile_block=profile_block,
        user_instruction=user_instruction,
        freeze_previous_style=freeze_previous_style,
    )
    return str(payload.get("prompt") or "")
