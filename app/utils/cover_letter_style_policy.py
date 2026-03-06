"""
Cover letter generation style policy.

This module keeps content-style steering out of llm_worker.py.
It adapts cover letter generation guidance using:
- job offer analysis/keywords
- raw offer text
- selected UI template (as secondary signal)
- preferred language
- optional user instruction
"""

from __future__ import annotations

import json
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


def _extract_previous_style_mode(analysis: Dict[str, Any]) -> Optional[str]:
    stored = analysis.get(COVER_LETTER_STYLE_ANALYSIS_KEY)
    mode: Optional[str] = None
    if isinstance(stored, dict):
        raw = stored.get("mode")
        mode = str(raw).strip() if raw is not None else None
    elif isinstance(stored, str):
        mode = stored.strip()
    if mode in VALID_STYLE_MODES:
        return mode
    return None


def _instruction_requests_style_change(user_instruction: Optional[str]) -> bool:
    text = str(user_instruction or "").strip().lower()
    if not text:
        return False
    markers = (
        "change le style",
        "changer le style",
        "style plus",
        "style moins",
        "change le ton",
        "changer le ton",
        "ton plus",
        "ton moins",
        "plus formel",
        "moins formel",
        "plus technique",
        "moins technique",
        "plus commercial",
        "moins commercial",
        "plus corporate",
        "moins corporate",
        "adapter le ton",
        "adapte le ton",
        "rewrite tone",
        "change tone",
        "change style",
        "more formal",
        "less formal",
        "more technical",
        "less technical",
        "more business",
        "less business",
        "more leadership",
        "less leadership",
    )
    return any(marker in text for marker in markers)


def _extract_mode_from_user_instruction(user_instruction: Optional[str]) -> Optional[str]:
    text = str(user_instruction or "").strip().lower()
    if not text:
        return None
    mode_scores = {
        "technical_precision": _score_markers(
            text,
            (
                "technique",
                "technical",
                "tech",
                "stack",
                "outils",
                "tooling",
                "engineering",
                "ingenieur",
                "cyber",
            ),
        ),
        "leadership_impact": _score_markers(
            text,
            (
                "leadership",
                "manager",
                "managerial",
                "direction",
                "pilotage",
                "ownership",
                "management",
                "coordination",
            ),
        ),
        "client_business": _score_markers(
            text,
            (
                "commercial",
                "business",
                "client",
                "customer",
                "sales",
                "metier",
                "stakeholder",
            ),
        ),
        "balanced_professional": _score_markers(
            text,
            (
                "equilibre",
                "balanced",
                "general",
                "genéral",
                "professionnel",
                "neutral",
                "neutre",
            ),
        ),
    }
    best_mode = max(mode_scores, key=lambda key: mode_scores[key])
    if mode_scores[best_mode] <= 0:
        return None
    return best_mode


def _resolve_style_profile(
    *,
    language_code: str,
    template_key: str,
    offer_text: str,
    keywords: List[str],
    forced_mode: Optional[str] = None,
) -> Dict[str, Any]:
    corpus = f"{offer_text}\n" + " | ".join(keywords)

    technical_markers = (
        "python",
        "sql",
        "cloud",
        "aws",
        "azure",
        "gcp",
        "linux",
        "kubernetes",
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
    )
    leadership_markers = (
        "manager",
        "lead",
        "leadership",
        "pilot",
        "strategy",
        "stakeholder",
        "governance",
        "coordination",
        "budget",
        "roadmap",
    )
    business_markers = (
        "client",
        "customer",
        "sales",
        "business",
        "growth",
        "partnership",
        "account",
        "market",
        "revenue",
    )

    technical_score = _score_markers(corpus, technical_markers)
    leadership_score = _score_markers(corpus, leadership_markers)
    business_score = _score_markers(corpus, business_markers)

    mode = forced_mode if forced_mode in VALID_STYLE_MODES else None
    if mode is None:
        if technical_score >= max(3, leadership_score, business_score):
            mode = "technical_precision"
        elif leadership_score >= max(3, technical_score, business_score):
            mode = "leadership_impact"
        elif business_score >= max(3, technical_score, leadership_score):
            mode = "client_business"
        else:
            mode = "balanced_professional"

    template_hint = {
        "modern": "Ton moderne et direct, phrases courtes, tres specifique.",
        "classic": "Ton formel et corporate, vocabulaire sobre.",
        "tech": "Ton technique/pro: concret, oriente realisations et stack verifiable.",
        "creative": "Ton dynamique, orientation projets/impact, mais professionnel.",
        "minimal": "Ton clair et epure, focalise impact et lisibilite.",
    }.get(template_key, "Ton professionnel et specifique.")

    if language_code == "en":
        labels = {
            "technical_precision": "Technical precision",
            "leadership_impact": "Leadership impact",
            "client_business": "Client/business value",
            "balanced_professional": "Balanced professional",
        }
        rules = {
            "technical_precision": [
                "Prioritize verifiable technical details (tools, methods, systems).",
                "Use concrete outcomes and measurable impact when available.",
                "Keep tone factual and ATS-friendly.",
            ],
            "leadership_impact": [
                "Emphasize ownership, coordination, and decision impact.",
                "Show how work aligned teams, priorities, or delivery quality.",
                "Keep claims grounded in profile facts.",
            ],
            "client_business": [
                "Emphasize business context, stakeholder value, and execution.",
                "Show concrete contribution to client/user outcomes.",
                "Keep language professional, concise, and actionable.",
            ],
            "balanced_professional": [
                "Balance fit motivation, evidence, and role projection.",
                "Use specific examples without overloading details.",
                "Keep structure clean and easy to scan.",
            ],
        }
    else:
        labels = {
            "technical_precision": "Precision technique",
            "leadership_impact": "Impact leadership",
            "client_business": "Valeur client/metier",
            "balanced_professional": "Professionnel equilibre",
        }
        rules = {
            "technical_precision": [
                "Prioriser les details techniques verifiables (outils, methodes, systemes).",
                "Donner des resultats concrets et mesurables quand disponibles.",
                "Conserver un ton factuel, clair et ATS-friendly.",
            ],
            "leadership_impact": [
                "Mettre en avant ownership, coordination et impact decisionnel.",
                "Montrer l'alignement equipes/priorites/qualite de delivery.",
                "Rester strictement ancre sur les faits du profil.",
            ],
            "client_business": [
                "Mettre en avant contexte metier, valeur parties prenantes et execution.",
                "Montrer la contribution aux resultats client/utilisateur.",
                "Conserver un style pro, concis et orient actions.",
            ],
            "balanced_professional": [
                "Equilibrer motivation, preuves et projection sur le poste.",
                "Utiliser des exemples concrets sans surcharger.",
                "Garder une structure lisible et directe.",
            ],
        }

    return {
        "mode": mode,
        "label": labels.get(mode, labels["balanced_professional"]),
        "template_hint": template_hint,
        "rules": rules.get(mode, rules["balanced_professional"]),
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
    """Build a style-aware cover letter generation payload."""
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
    style_change_requested = _instruction_requests_style_change(user_instruction)
    instruction_mode = _extract_mode_from_user_instruction(user_instruction)

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

    keywords_text = ", ".join(str(k) for k in keywords[:15] if str(k).strip())
    if not keywords_text:
        keywords_text = "None" if language_code == "en" else "Aucun"

    style_rules = "\n".join(f"- {rule}" for rule in style_profile["rules"])
    instruction_text = _trim_text(user_instruction, 800)

    if language_code == "en":
        letter_skeleton = f"""Subject: Application - {job_title} ({company})

Dear Hiring Manager,

<Paragraph 1: hook + why this role/company (specific)>

<Paragraph 2: 2-3 proof points (experience/projects) + verified skills + impact>

<Paragraph 3: motivation + projection + interview availability>

Sincerely,

{profile_name or placeholder}"""
        instruction_block = (
            f"\nUSER INSTRUCTION (apply if consistent with profile facts):\n{instruction_text}\n"
            if instruction_text
            else ""
        )
    else:
        letter_skeleton = f"""Objet: Candidature - {job_title} ({company})

Madame, Monsieur,

<Paragraphe 1: accroche + pourquoi ce poste/entreprise (specifique)>

<Paragraphe 2: 2-3 preuves de fit (experiences/projets) + competences cles verifiables + impact>

<Paragraphe 3: motivation + projection + disponibilite pour entretien>

Je vous prie d'agreer, Madame, Monsieur, l'expression de mes salutations distinguees.

{profile_name or placeholder}"""
        instruction_block = (
            f"\nINSTRUCTION UTILISATEUR (a appliquer si compatible avec les faits du profil):\n{instruction_text}\n"
            if instruction_text
            else ""
        )

    prompt = f"""
LANGUE: {language_code}
STYLE DE GENERATION (contenu): {style_profile["label"]} ({style_profile["mode"]})
STYLE CONTEXTE (template UI): {template_key} ({style_profile["template_hint"]})
STYLE SOURCE: {style_source}

DIRECTIVES STYLE:
{style_rules}
{instruction_block}
OFFRE CIBLE:
- Poste: {job_title}
- Entreprise: {company}
- Mots-cles detectes: {keywords_text}
- Description (brut, tronquee si besoin):
{_trim_text(offer_text, 2000 if isinstance(offer_keywords, dict) else 3000)}

OFFER_KEYWORDS_JSON (si disponible):
{_trim_text(json.dumps(offer_keywords, indent=2, ensure_ascii=False), 1200) if isinstance(offer_keywords, dict) else "N/A"}

DONNEES CANDIDAT (Profil detaille + CV de reference + lettre type si fournie):
{profile_block}

SORTIE OBLIGATOIRE (texte uniquement, pas de Markdown):
- Respecte STRICTEMENT la structure ci-dessous.
- Utilise uniquement les faits presents dans les donnees candidat (sinon {placeholder}).
- Reprends en priorite les mots-cles de l'offre qui sont justifiables par le profil.
- Conserve un ton adapte au style de generation selectionne.
- Si INSTRUCTION UTILISATEUR est fournie, l'appliquer sans inventer de faits.
- Longueur: maximum 1 page.

STRUCTURE:
{letter_skeleton}
""".strip()

    style_payload = {
        "mode": style_profile.get("mode"),
        "label": style_profile.get("label"),
        "source": style_source,
        "freeze_applied": freeze_applied,
        "instruction_override": instruction_override,
        "template_hint": style_profile.get("template_hint"),
        "scores": dict(style_profile.get("scores") or {}),
    }

    return {
        "prompt": prompt,
        "style_profile": style_payload,
        "style_mode": style_payload.get("mode"),
        "style_source": style_payload.get("source"),
        "freeze_applied": freeze_applied,
        "instruction_override": instruction_override,
        "language_code": language_code,
        "template_key": template_key,
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
    """Build a style-aware cover letter generation prompt."""
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

