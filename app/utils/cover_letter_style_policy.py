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
import re
import unicodedata
from typing import Any, Dict, Iterable, List, Optional, Tuple

from .language_policy import normalize_language_code


COVER_LETTER_STYLE_ANALYSIS_KEY = "cover_letter_generation_style"

VALID_STYLE_MODES = {
    "technical_precision",
    "leadership_impact",
    "client_business",
    "balanced_professional",
}

_GENERIC_COVER_LETTER_PHRASES = (
    "solutions technologiques impactantes",
    "qualite irreprochable",
    "passion pour les solutions",
    "je suis passionne",
    "environnement dynamique",
    "mettre mes competences au service",
    "contribuer a vos projets",
    "strong passion",
    "impactful technological solutions",
    "high-quality solutions",
    "documented background",
    "practical approach to execution",
    "highly in that concrete context",
    "I would approach those expectations",
    "my profile is aligned",
    "my background gives me a basis",
    "experience I can bring to the role",
    "priorities described in this role",
    "where I worked with",
)

_TERM_STOPWORDS = {
    "about",
    "against",
    "after",
    "also",
    "are",
    "avec",
    "candidate",
    "candidat",
    "candidats",
    "candidates",
    "collaborative",
    "company",
    "dans",
    "des",
    "dynamic",
    "for",
    "from",
    "hiring",
    "highly",
    "job",
    "les",
    "location",
    "notre",
    "our",
    "poste",
    "remote",
    "role",
    "seeking",
    "skilled",
    "summary",
    "team",
    "the",
    "this",
    "useful",
    "what",
    "will",
    "vous",
    "with",
    "your",
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


def _term_key(value: Any) -> str:
    text = unicodedata.normalize("NFKD", str(value or "").lower())
    text = "".join(char for char in text if not unicodedata.combining(char))
    chars = [char if char.isalnum() else " " for char in text]
    return " ".join("".join(chars).split())


def _collect_present_terms(
    corpus: str,
    candidates: Iterable[str],
    *,
    max_items: int = 14,
) -> List[str]:
    normalized_corpus = _term_key(corpus)
    if not normalized_corpus:
        return []
    present: List[str] = []
    for raw in candidates:
        term = str(raw or "").strip()
        if len(term) < 2:
            continue
        normalized_term = _term_key(term)
        if not normalized_term:
            continue
        if normalized_term in normalized_corpus:
            present.append(term)
            if len(present) >= max_items:
                break
    return _dedup_preserve(present)


def _looks_like_signal_term(value: Any) -> bool:
    text = str(value or "").strip(" \t\r\n,;:.()[]{}")
    if not text or len(text) < 2:
        return False
    normalized = _term_key(text)
    if not normalized or normalized in _TERM_STOPWORDS:
        return False
    tokens = normalized.split()
    if len(tokens) > 5:
        return False
    if any(token in _TERM_STOPWORDS for token in tokens):
        return False
    if len(tokens) >= 2:
        return True
    if text.isupper() and len(text) >= 2:
        return True
    if any(char.isdigit() for char in text):
        return True
    if any(char in text for char in "+#./-"):
        return True
    if any(char.isupper() for char in text[1:]):
        return True
    return bool(text[:1].isupper() and len(text) >= 3)


def _extract_signal_terms_from_text(value: Any, *, max_items: int = 18) -> List[str]:
    text = str(value or "")
    if not text.strip():
        return []
    raw_chunks = []
    raw_chunks.extend(re.split(r"[,;|•·\n\r\t]+", text))
    raw_chunks.extend(
        match.group(0)
        for match in re.finditer(
            r"\b[A-Za-z][A-Za-z0-9+#./-]*(?:\s+[A-Za-z][A-Za-z0-9+#./-]*){0,3}\b",
            text,
        )
    )
    output: List[str] = []
    seen: set[str] = set()
    for chunk in raw_chunks:
        candidate = str(chunk or "").strip(" -–—:;,.()[]{}")
        if not _looks_like_signal_term(candidate):
            continue
        key = _term_key(candidate)
        if not key or key in seen:
            continue
        seen.add(key)
        output.append(candidate)
        if len(output) >= max_items:
            break
    return output


def _build_cover_letter_quality_rules(
    *,
    language_code: str,
    company: Any,
    job_title: Any,
    offer_text: Any,
    keywords: List[str],
    profile_block: Any,
) -> str:
    offer_corpus = f"{offer_text or ''}\n" + " | ".join(keywords)
    profile_corpus = str(profile_block or "")
    extracted_offer_terms = _dedup_preserve(
        [
            *[str(item) for item in keywords if str(item).strip()],
            *_extract_signal_terms_from_text(offer_corpus, max_items=24),
        ]
    )
    offer_signals = _collect_present_terms(
        offer_corpus,
        extracted_offer_terms,
        max_items=16,
    )
    extracted_profile_terms = _dedup_preserve(
        [
            *_extract_signal_terms_from_text(profile_corpus, max_items=24),
            *offer_signals,
        ]
    )
    profile_signals = _collect_present_terms(
        profile_corpus,
        extracted_profile_terms,
        max_items=18,
    )
    generic_phrases = ", ".join(_GENERIC_COVER_LETTER_PHRASES[:7])
    offer_signal_text = ", ".join(offer_signals[:12]) or (
        "none detected" if language_code == "en" else "aucun detecte"
    )
    profile_signal_text = ", ".join(profile_signals[:12]) or (
        "none detected" if language_code == "en" else "aucun detecte"
    )
    company_text = str(company or "").strip() or (
        "the target company" if language_code == "en" else "l'entreprise cible"
    )
    job_text = str(job_title or "").strip() or (
        "the target role" if language_code == "en" else "le poste cible"
    )

    if language_code != "fr":
        return f"""
COVER LETTER QUALITY RULES:
- Formal hygiene: output exactly one Subject line, one greeting, 2-3 dense body paragraphs, one closing, and one signature.
- Company spelling: write `{company_text}` exactly as provided; never recase acronyms, product names, tool names, or official company casing.
- Evidence-first structure: every body paragraph must connect a strong requirement of `{job_text}` to a concrete profile-backed proof.
- Role vocabulary: when grounded by profile evidence, surface high-signal offer terms such as {offer_signal_text}; do not replace them with vague wording.
- Motivation wording: never use a raw keyword list as the object of motivation. Let the contribution wording be induced from the candidate evidence and the offer's responsibilities; do not rely on fixed role-category formulas.
- Project usage: if a profile project overlaps the offer, explain what it does and which source-backed practice, result, or workflow it proves; do not reduce it to "project with tool A and tool B".
- Preserve concrete evidence: do not simplify away source-backed tools, methods, projects, workflows, or review practices when they explain why the candidate fits the role.
- Shared specialized requirements: when both the offer and candidate data support a concrete method, tool, workflow, review practice, or domain requirement, integrate it naturally in the target language without forcing fixed profession-specific examples.
- Offer-only terms may appear as target contribution or projection, never as past achievements unless the profile supports them.
- Certifications and soft skills are secondary; use them only after stronger technical, operational, business, or domain proof.
- Avoid generic filler, especially: {generic_phrases}.
- Forbidden weak phrasings include: "documented background", "practical approach to execution", "highly in that concrete context", "I would approach those expectations", "my profile is aligned", "my background gives me a basis", "experience I can bring to the role", and "priorities described in this role".
- Profile-backed signals available in the candidate data include: {profile_signal_text}.
""".strip()

    return f"""
REGLES QUALITE LETTRE:
- Hygiene formelle: produire exactement une ligne Objet, une salutation, 2-3 paragraphes denses, une formule de politesse et une signature.
- Orthographe entreprise: ecrire `{company_text}` exactement comme dans l'offre; ne jamais recaser les acronymes, noms de produit, noms d'outils ou la casse officielle d'une entreprise.
- Structure par preuves: chaque paragraphe de corps doit relier une exigence forte de `{job_text}` a une preuve concrete issue du profil.
- Vocabulaire du role: quand le profil le justifie, faire apparaitre les termes forts de l'offre comme {offer_signal_text}; ne pas les remplacer par des formulations vagues.
- Formulation de la motivation: ne jamais utiliser une liste brute de mots-clés comme objet de motivation. Laisser la formulation de contribution être induite par les preuves candidat et les responsabilités de l'offre; ne pas s'appuyer sur des catégories métier fixes.
- Usage des projets: si un projet du profil chevauche l'offre, expliquer ce qu'il fait et quelle pratique, resultat ou maniere de travailler sourcee il prouve; ne pas le reduire a "projet avec outil A et outil B".
- Préservation des preuves concrètes: ne pas simplifier au point de supprimer les outils, méthodes, projets, workflows ou pratiques de revue sourcés quand ils expliquent le fit du candidat.
- Exigences specialisees partagees: quand l'offre et les donnees candidat soutiennent toutes les deux une methode, un outil, un workflow, une pratique de revue ou une exigence metier concrete, l'integrer naturellement dans la langue cible sans forcer d'exemples propres a un metier.
- Les termes presents uniquement dans l'offre peuvent servir a la projection vers le poste, jamais a decrire une realisation passee sans preuve profil.
- Certifications et soft skills sont secondaires; les utiliser seulement apres les preuves techniques, operationnelles, business ou metier plus fortes.
- Eviter le remplissage generique, notamment: {generic_phrases}.
- Formulations faibles interdites: "documented background", "practical approach to execution", "highly in that concrete context", "I would approach those expectations", "my profile is aligned", "my background gives me a basis", "experience I can bring to the role" et "priorities described in this role".
- Signaux deja visibles dans les donnees candidat: {profile_signal_text}.
""".strip()


def _trim_text(value: Any, max_chars: int) -> str:
    text = str(value or "").strip()
    if len(text) <= max_chars:
        return text
    if max_chars <= 0:
        return ""
    return text[: max_chars - 3].rstrip() + "..."


def _normalize_language(value: Optional[str]) -> str:
    return normalize_language_code(value)


def _language_display_name(language_code: Optional[str]) -> str:
    names = {
        "en": "English",
        "fr": "French",
        "de": "German",
        "es": "Spanish",
        "it": "Italian",
        "pt": "Portuguese",
        "nl": "Dutch",
        "ja": "Japanese",
        "zh": "Chinese",
        "ko": "Korean",
        "ar": "Arabic",
        "ru": "Russian",
        "el": "Greek",
    }
    code = _normalize_language(language_code)
    return names.get(code, code.upper())


def _localized_letter_terms(language_code: str) -> Dict[str, str]:
    code = _normalize_language(language_code)
    profiles = {
        "en": {
            "subject": "Subject",
            "application": "Application",
            "greeting": "Dear Hiring Team,",
            "closing": "Sincerely,",
        },
        "fr": {
            "subject": "Objet",
            "application": "Candidature",
            "greeting": "Madame, Monsieur,",
            "closing": "Cordialement,",
        },
        "es": {
            "subject": "Asunto",
            "application": "Solicitud",
            "greeting": "Estimado equipo de contratación,",
            "closing": "Atentamente,",
        },
        "de": {
            "subject": "Betreff",
            "application": "Bewerbung",
            "greeting": "Sehr geehrtes Hiring-Team,",
            "closing": "Mit freundlichen Grüßen,",
        },
        "it": {
            "subject": "Oggetto",
            "application": "Candidatura",
            "greeting": "Gentile team di selezione,",
            "closing": "Cordiali saluti,",
        },
        "pt": {
            "subject": "Assunto",
            "application": "Candidatura",
            "greeting": "Prezada equipe de recrutamento,",
            "closing": "Atenciosamente,",
        },
        "nl": {
            "subject": "Betreft",
            "application": "Sollicitatie",
            "greeting": "Geacht wervingsteam,",
            "closing": "Met vriendelijke groet,",
        },
        "ja": {
            "subject": "件名",
            "application": "応募",
            "greeting": "採用ご担当者様",
            "closing": "敬具",
        },
        "zh": {
            "subject": "主题",
            "application": "申请",
            "greeting": "尊敬的招聘团队：",
            "closing": "此致",
        },
        "ko": {
            "subject": "제목",
            "application": "지원",
            "greeting": "채용 담당자님께",
            "closing": "감사합니다,",
        },
        "ar": {
            "subject": "الموضوع",
            "application": "طلب",
            "greeting": "إلى فريق التوظيف المحترم،",
            "closing": "مع خالص التحية،",
        },
        "ru": {
            "subject": "Тема",
            "application": "Заявка",
            "greeting": "Уважаемая команда по подбору персонала,",
            "closing": "С уважением,",
        },
    }
    return profiles.get(code, profiles["en"])


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


def _extract_mode_from_user_instruction(
    user_instruction: Optional[str],
) -> Optional[str]:
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
                "methodes",
                "methods",
                "systemes",
                "systems",
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
        "method",
        "methode",
        "outils",
        "technical",
        "technique",
        "system",
        "systeme",
        "tooling",
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

    extracted_signal_density = len(_extract_signal_terms_from_text(corpus, max_items=12))
    technical_score = _score_markers(corpus, technical_markers) + min(
        4,
        extracted_signal_density // 2,
    )
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

    if language_code != "fr":
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
    elif language_code == "fr":
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
    language_code: Optional[str] = None,
    user_instruction: Optional[str] = None,
    freeze_previous_style: bool = False,
) -> Dict[str, Any]:
    """Build a style-aware cover letter generation payload."""
    offer_payload = offer_data if isinstance(offer_data, dict) else {}
    analysis = offer_payload.get("analysis")
    analysis = analysis if isinstance(analysis, dict) else {}

    keywords = _collect_offer_keywords(analysis)
    language = language_code or analysis.get("language") or preferred_language or "fr"
    language_code = _normalize_language(language)
    target_language_name = _language_display_name(language_code)
    other_language_name = "any other language"
    placeholder = (
        "[TO COMPLETE]"
        if language_code == "en"
        else "[A COMPLETER]"
        if language_code == "fr"
        else f"[TO COMPLETE IN {target_language_name.upper()}]"
    )
    localized_terms = _localized_letter_terms(language_code)

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
    quality_rules = _build_cover_letter_quality_rules(
        language_code=language_code,
        company=company,
        job_title=job_title,
        offer_text=offer_text,
        keywords=keywords,
        profile_block=profile_block,
    )
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
        prompt = f"""
TARGET OUTPUT LANGUAGE: {language_code} ({target_language_name}) [selected generation language]
GENERATION STYLE: {style_profile["label"]} ({style_profile["mode"]})
UI TEMPLATE CONTEXT: {template_key} ({style_profile["template_hint"]})
STYLE SOURCE: {style_source}

NON-NEGOTIABLE OUTPUT CONTRACT:
- Final answer language: {language_code} ({target_language_name}) from the first line to the signature.
- Output exactly one cover letter, not notes, source data, project lists, CV fragments, or analysis.
- The first non-empty line must be `Subject:`; add a greeting immediately after it.
- Include 2-3 body paragraphs, then a closing formula and signature.
- Include a real motivation for this company using source-backed company context from the offer; do not write a company-agnostic paragraph that could fit any employer.
- Include a real motivation for this role: explain why this position is a coherent next step in the candidate trajectory, not just why the profile matches.
- Do not mention a candidate tool, framework, package, method, employer, metric, or project unless it appears in the candidate data. Offer-only terms may be phrased as target role priorities, not as past achievements.
- Source data below is evidence only: synthesize it into a letter; never copy raw profile, CV, project, or source-letter paragraphs verbatim.

REQUIRED STRUCTURE:
{letter_skeleton}

STYLE DIRECTIONS:
{style_rules}

{quality_rules}
{instruction_block}
TARGET OFFER:
- Job title: {job_title}
- Company: {company}
- Detected keywords: {keywords_text}
- Raw description (trimmed if needed):
{_trim_text(offer_text, 2000 if isinstance(offer_keywords, dict) else 3000)}

OFFER_KEYWORDS_JSON (if available):
{_trim_text(json.dumps(offer_keywords, indent=2, ensure_ascii=False), 1200) if isinstance(offer_keywords, dict) else "N/A"}

CANDIDATE DATA (detailed profile + source CV + source cover letter if provided):
{profile_block}

MANDATORY OUTPUT RULES (plain text only, no Markdown):
- Use EXACTLY one language throughout the whole letter: {language_code} ({target_language_name}).
- Write the subject, greeting, body, closing, and signature in {target_language_name} from the very first draft.
- The first non-empty line must be a `Subject:` line.
- Add a greeting immediately after the subject.
- Include at least one body paragraph between the greeting and the closing.
- End with a closing formula and signature; do not omit them.
- Do not output the skeleton placeholders literally.
- Do NOT mix {target_language_name} and {other_language_name} anywhere in the generated prose.
- Translate every generated sentence into {target_language_name}. Only proper nouns, official company/product names, established acronyms, and tool names may remain untranslated when necessary.
- Make the letter motivation-driven: one paragraph must show why the candidate wants this specific company, and another sentence must show why this specific role fits the candidate's next step.
- Use active phrasing such as "I want to contribute", "I have learned to", "I see this role as", "I can bring"; avoid weak filler such as "my profile is aligned".
- In motivation sentences, do not write "work involving A, B, C" or any raw keyword list. Derive the contribution wording from the candidate evidence and offer responsibilities instead of using fixed role-category formulas.
- If a candidate project is relevant, explain what it does and which source-backed practice, result, or workflow it proves; never write only "I developed X with Y".
- Do not flatten the letter into generic cleanliness: keep source-backed tools, methods, projects, workflows, and review practices when they make the application more convincing.
- If both the offer and candidate data support a concrete specialized requirement, integrate it naturally in the selected language; do not force fixed profession-specific examples.
- Do not use weak filler phrases such as "documented background", "practical approach to execution", "highly in that concrete context", "I would approach those expectations", "my background gives me a basis", "experience I can bring to the role", or "priorities described in this role".
- Do not dump raw keywords or analysis labels. Integrate tools, methods, role priorities, and company context into grammatical sentences.
- Use only facts present in the candidate data (otherwise {placeholder}).
- Reuse offer keywords only when justified by the profile.
- Keep the tone aligned with the selected generation style.
- If USER INSTRUCTION is provided, follow it without inventing facts.
- Length: maximum 1 page.

STRUCTURE:
{letter_skeleton}
""".strip()
    elif language_code == "fr":
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
LANGUE DE SORTIE OBLIGATOIRE: {language_code} ({target_language_name}) [langue de generation selectionnee]
STYLE DE GENERATION (contenu): {style_profile["label"]} ({style_profile["mode"]})
STYLE CONTEXTE (template UI): {template_key} ({style_profile["template_hint"]})
STYLE SOURCE: {style_source}

CONTRAT DE SORTIE NON NEGOCIABLE:
- Langue finale: {language_code} ({target_language_name}) de la premiere ligne a la signature.
- Produire exactement une lettre de motivation, pas des notes, donnees source, listes de projets, fragments de CV ou analyse.
- La premiere ligne non vide doit etre `Objet:`; ajouter une salutation juste apres.
- Inclure 2-3 paragraphes de corps, puis une formule de politesse et une signature.
- Inclure une vraie motivation pour cette entreprise avec du contexte source dans l'offre; ne pas ecrire un paragraphe interchangeable avec n'importe quel employeur.
- Inclure une vraie motivation pour ce poste: expliquer pourquoi il represente une etape coherente dans la trajectoire du candidat, pas seulement pourquoi le profil correspond.
- Ne jamais attribuer au candidat un outil, framework, package, methode, employeur, metrique ou projet absent des donnees candidat. Les termes presents seulement dans l'offre peuvent servir a decrire les priorites du poste, pas une realisation passee.
- Les donnees source ci-dessous sont des preuves: les synthetiser en lettre; ne jamais recopier brut les paragraphes de profil, CV, projets ou lettre type.

STRUCTURE OBLIGATOIRE:
{letter_skeleton}

DIRECTIVES STYLE:
{style_rules}

{quality_rules}
{instruction_block}
OFFRE CIBLE:
- Poste: {job_title}
- Entreprise: {company}
- Mots-cles detectes: {keywords_text}
- Description (brut, tronquee si besoin):
{_trim_text(offer_text, 2000 if isinstance(offer_keywords, dict) else 3000)}

OFFER_KEYWORDS_JSON (si disponible):
{_trim_text(json.dumps(offer_keywords, indent=2, ensure_ascii=False), 1200) if isinstance(offer_keywords, dict) else "N/A"}

DONNEES CANDIDAT (profil detaille + CV de reference + lettre type si fournie):
{profile_block}

SORTIE OBLIGATOIRE (texte uniquement, pas de Markdown):
- Respecte STRICTEMENT la structure ci-dessous.
- Utilise EXACTEMENT une seule langue dans toute la lettre: {language_code} ({target_language_name}).
- Redige l'objet, la salutation, les paragraphes, la formule de politesse et la signature en {target_language_name} des le premier jet.
- La premiere ligne non vide doit etre une ligne `Objet:`.
- Ajoute une salutation juste apres l'objet.
- Inclut au moins un paragraphe de corps entre la salutation et la formule de politesse.
- Termine par une formule de politesse et une signature; ne les omets pas.
- N'affiche jamais les placeholders du squelette tels quels.
- Ne melange jamais {target_language_name} et {other_language_name} dans le texte genere.
- Traduis chaque phrase generee en {target_language_name}. Seuls les noms propres, noms officiels d'entreprise/produit, acronymes etablis et noms d'outils peuvent rester non traduits si necessaire.
- La lettre doit porter une motivation explicite: un paragraphe doit montrer pourquoi le candidat veut rejoindre cette entreprise precise, et une phrase doit montrer pourquoi ce poste precis correspond a sa prochaine etape.
- Utilise des formulations actives comme "je souhaite contribuer", "j'ai appris a", "je vois ce poste comme", "je peux apporter"; evite les formules faibles du type "mon profil est aligne".
- Dans les phrases de motivation, n'écris pas "travaux impliquant A, B, C" ni aucune liste brute de mots-clés. Dérive la formulation de contribution depuis les preuves candidat et les responsabilités de l'offre, sans utiliser de catégories métier fixes.
- Si un projet candidat est pertinent, explique ce qu'il fait et quelle pratique, resultat ou maniere de travailler sourcee il prouve; ne te limite jamais a "j'ai developpe X avec Y".
- Ne pas aplatir la lettre en formulation propre mais generique: conserver les outils, methodes, projets, workflows et pratiques de revue sources quand ils rendent la candidature plus convaincante.
- Si l'offre et les donnees candidat soutiennent toutes les deux une exigence specialisee concrete, integre-la naturellement dans la langue selectionnee; ne force pas d'exemples propres a un metier.
- N'utilise pas les formulations faibles "documented background", "practical approach to execution", "highly in that concrete context", "I would approach those expectations", "my background gives me a basis", "experience I can bring to the role" ou "priorities described in this role".
- Ne deverse pas de mots-cles bruts ni de labels d'analyse. Integre les outils, methodes, priorites du poste et contexte entreprise dans des phrases grammaticales.
- Utilise uniquement les faits presents dans les donnees candidat (sinon {placeholder}).
- Reprends en priorite les mots-cles de l'offre qui sont justifiables par le profil.
- Conserve un ton adapte au style de generation selectionne.
- Si INSTRUCTION UTILISATEUR est fournie, l'appliquer sans inventer de faits.
- Longueur: maximum 1 page.

STRUCTURE:
{letter_skeleton}
""".strip()
    else:
        subject_label = localized_terms["subject"]
        application_label = localized_terms["application"]
        greeting = localized_terms["greeting"]
        closing = localized_terms["closing"]
        letter_skeleton = f"""{subject_label}: {application_label} - {job_title} ({company})

{greeting}

<Paragraph 1 in {target_language_name}: specific motivation for this company and this role>

<Paragraph 2 in {target_language_name}: 2-3 source-backed proof points from experience/projects, with verified skills and impact>

<Paragraph 3 in {target_language_name}: professional trajectory, concrete contribution, and interview availability>

{closing}

{profile_name or placeholder}"""
        instruction_block = (
            f"\nUSER INSTRUCTION (apply only if consistent with profile facts):\n{instruction_text}\n"
            if instruction_text
            else ""
        )
        prompt = f"""
TARGET OUTPUT LANGUAGE: {language_code} ({target_language_name}) [selected generation language]
GENERATION STYLE: {style_profile["label"]} ({style_profile["mode"]})
UI TEMPLATE CONTEXT: {template_key} ({style_profile["template_hint"]})
STYLE SOURCE: {style_source}

NON-NEGOTIABLE OUTPUT CONTRACT:
- Final answer language: {language_code} ({target_language_name}) from the first line to the signature.
- Output exactly one cover letter, not notes, source data, project lists, CV fragments, or analysis.
- Use a localized subject/application line in {target_language_name}. The first non-empty line should follow this shape: `{subject_label}: {application_label} - {job_title} ({company})`.
- Add a greeting in {target_language_name} immediately after the subject line.
- Include 2-3 body paragraphs, then a closing formula and signature in {target_language_name}.
- Include a real motivation for this company using source-backed company context from the offer; do not write a company-agnostic paragraph that could fit any employer.
- Include a real motivation for this role: explain why this position is a coherent next step in the candidate trajectory, not just why the profile matches.
- Do not mention a candidate tool, framework, package, method, employer, metric, or project unless it appears in the candidate data. Offer-only terms may be phrased as target role priorities, not as past achievements.
- Source data below is evidence only: synthesize it into a letter; never copy raw profile, CV, project, or source-letter paragraphs verbatim.

REQUIRED STRUCTURE:
{letter_skeleton}

STYLE DIRECTIONS:
{style_rules}

{quality_rules}
{instruction_block}
TARGET OFFER:
- Job title: {job_title}
- Company: {company}
- Detected keywords: {keywords_text}
- Raw description (trimmed if needed):
{_trim_text(offer_text, 2000 if isinstance(offer_keywords, dict) else 3000)}

OFFER_KEYWORDS_JSON (if available):
{_trim_text(json.dumps(offer_keywords, indent=2, ensure_ascii=False), 1200) if isinstance(offer_keywords, dict) else "N/A"}

CANDIDATE DATA (detailed profile + source CV + source cover letter if provided):
{profile_block}

MANDATORY OUTPUT RULES (plain text only, no Markdown):
- Use EXACTLY one language throughout the whole letter: {language_code} ({target_language_name}).
- Write the subject, greeting, body, closing, and signature in {target_language_name} from the first draft.
- Do not output English/French labels such as `Subject`, `Objet`, `Dear`, `Madame`, or `Monsieur` unless they are natural in {target_language_name}.
- Do not output the skeleton placeholders literally.
- Do NOT mix {target_language_name} and {other_language_name} anywhere in the generated prose.
- Translate every generated sentence into {target_language_name}. Only proper nouns, official company/product names, established acronyms, and tool names may remain untranslated when necessary.
- Make the letter motivation-driven: one paragraph must show why the candidate wants this specific company, and one sentence must show why this specific role fits the candidate's next step.
- Use active phrasing in {target_language_name}; avoid weak filler equivalent to "my profile is aligned".
- In motivation sentences, do not write a raw keyword list such as "work involving A, B, C". Derive the contribution wording from candidate evidence and offer responsibilities in {target_language_name}, without fixed role-category formulas.
- If a candidate project is relevant, explain in {target_language_name} what it does and which source-backed practice, result, or workflow it proves; never write only "I developed X with Y".
- Do not flatten the letter into generic cleanliness: keep source-backed tools, methods, projects, workflows, and review practices when they make the application more convincing.
- If both the offer and candidate data support a concrete specialized requirement, integrate it naturally in {target_language_name}; do not force fixed profession-specific examples.
- Do not use weak filler equivalent to "documented background", "practical approach to execution", "highly in that concrete context", "I would approach those expectations", "my background gives me a basis", "experience I can bring to the role", or "priorities described in this role".
- Do not dump raw keywords or analysis labels. Integrate tools, methods, role priorities, and company context into grammatical sentences.
- Use only facts present in the candidate data (otherwise {placeholder}).
- Reuse offer keywords only when justified by the profile.
- Keep the tone aligned with the selected generation style.
- If USER INSTRUCTION is provided, follow it without inventing facts.
- Length: maximum 1 page.

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
    language_code: Optional[str] = None,
    user_instruction: Optional[str] = None,
    freeze_previous_style: bool = False,
) -> str:
    """Build a style-aware cover letter generation prompt."""
    payload = build_cover_letter_generation_payload(
        offer_data=offer_data,
        template=template,
        preferred_language=preferred_language,
        language_code=language_code,
        profile_name=profile_name,
        profile_block=profile_block,
        user_instruction=user_instruction,
        freeze_previous_style=freeze_previous_style,
    )
    return str(payload.get("prompt") or "")
