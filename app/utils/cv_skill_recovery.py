"""Helpers to recover a robust skills section from profile data."""

from __future__ import annotations

import re
import unicodedata
from typing import Any, Dict, Iterable, List, Sequence, Tuple

from .cv_offer_term_routing import route_term_to_section
from .cv_skill_evidence import (
    classify_skill_bucket,
    collect_supported_skill_terms,
    looks_like_noise_skill_term,
    should_keep_skill_term,
    skills_section_has_supported_signal,
)
from .cv_skill_ranking import rank_skill_blocks_by_relevance
from .keyword_alignment import normalize_keyword_for_match, normalized_term_in_probe

try:
    from ..domain.generation.tool_signals import collect_named_tool_hints
except Exception:
    collect_named_tool_hints = None

_GENERIC_SKILL_LABELS = {
    "skill",
    "skills",
    "competence",
    "competences",
    "technical skill",
    "technical skills",
    "soft skill",
    "soft skills",
    "tool",
    "tools",
    "technology",
    "technologies",
}

_ROLE_LIKE_SKILL_TOKENS = {
    "ingenieur",
    "engineer",
    "developpeur",
    "developer",
    "consultant",
    "manager",
    "architecte",
    "architect",
    "analyste",
    "analyst",
    "stagiaire",
    "intern",
}


def _dedup_preserve(items: Iterable[Any]) -> List[str]:
    output: List[str] = []
    seen: set[str] = set()
    for raw in items or []:
        text = str(raw or "").strip()
        if not text:
            continue
        norm = normalize_keyword_for_match(text)
        if not norm or norm in seen:
            continue
        seen.add(norm)
        output.append(text)
    return output


def _normalize_role_text(value: Any) -> str:
    text = str(value or "").strip().casefold()
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = re.sub(r"[^\w]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _clean_skill_candidate(
    value: Any,
    profile_json: Dict[str, Any] | None = None,
) -> str:
    if not isinstance(value, str):
        return ""
    cleaned = re.sub(r"\s+", " ", value).strip(" ,;:-")
    if not cleaned or len(cleaned) > 80:
        return ""
    if any(mark in cleaned for mark in ("!", "?", "\n")):
        return ""

    compact = cleaned.strip()
    if "." in compact:
        dotted_tech = bool(
            re.fullmatch(r"(?:[A-Za-z0-9+#]+(?:\.[A-Za-z0-9+#]+)+)", compact)
        )
        if not dotted_tech and (re.search(r"\.\s", compact) or compact.endswith(".")):
            return ""

    norm = normalize_keyword_for_match(cleaned)
    if not norm or norm in _GENERIC_SKILL_LABELS:
        return ""
    if looks_like_noise_skill_term(cleaned):
        return ""

    role_norm = _normalize_role_text(cleaned)
    tokens = [tok for tok in role_norm.split() if tok]
    if not tokens or len(tokens) > 6:
        return ""
    if len(tokens) <= 3 and all(tok in _ROLE_LIKE_SKILL_TOKENS for tok in tokens):
        return ""
    if not should_keep_skill_term(cleaned, profile_json):
        return ""

    return cleaned


def _split_list_like_skill_string(value: str) -> List[str]:
    text = re.sub(r"\s+", " ", str(value or "").strip())
    if not text:
        return []
    if not re.search(r"[,;|·•\n]", str(value or "")):
        return []
    return [
        item.strip(" ,;:.-")
        for item in re.split(r"\s*(?:,|;|\||·|•|\n)\s*", str(value or ""))
        if item.strip(" ,;:.-")
    ]


def skills_section_low_signal(
    skills_section: Any,
    profile_json: Dict[str, Any] | None = None,
) -> bool:
    if not isinstance(skills_section, list) or not skills_section:
        return True
    valid_items = 0
    for block in skills_section:
        if not isinstance(block, dict):
            continue
        items = block.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            if _clean_skill_candidate(str(item or "")):
                valid_items += 1
    if valid_items < 2:
        return True
    if isinstance(profile_json, dict) and profile_json:
        supported, plausible, hard_unsupported = skills_section_has_supported_signal(
            skills_section, profile_json
        )
        if supported + plausible < 2:
            return True
        if hard_unsupported > max(2, supported + plausible):
            return True
    return False


def _extend_candidates(
    output: List[str],
    value: Any,
    profile_json: Dict[str, Any] | None = None,
) -> None:
    if isinstance(value, str):
        cleaned = _clean_skill_candidate(value, profile_json)
        if cleaned:
            output.append(cleaned)
            return
        for item in _split_list_like_skill_string(value):
            cleaned_item = _clean_skill_candidate(item, profile_json)
            if cleaned_item:
                output.append(cleaned_item)
        return
    if isinstance(value, list):
        for item in value:
            _extend_candidates(output, item, profile_json)
        return
    if isinstance(value, dict):
        for key in ("name", "skill", "label", "technology", "tool"):
            _extend_candidates(output, value.get(key), profile_json)
        return


def _collect_source_probe(profile_json: Dict[str, Any], extra_items: Iterable[Any]) -> str:
    parts: List[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                parts.append(text)
            return
        if isinstance(value, list):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            for nested in value.values():
                add(nested)

    add(list(extra_items or []))
    for key in (
        "skills",
        "projects",
        "education",
        "certifications",
        "experiences",
        "experience",
    ):
        add((profile_json or {}).get(key))
    return normalize_keyword_for_match(" ".join(parts))


def _collect_source_fragments(profile_json: Dict[str, Any]) -> List[str]:
    fragments: List[str] = []

    def add(value: Any) -> None:
        if isinstance(value, str):
            text = value.strip()
            if text:
                fragments.append(text)
            return
        if isinstance(value, list):
            for item in value:
                add(item)
            return
        if isinstance(value, dict):
            for nested in value.values():
                add(nested)

    for key in (
        "skills",
        "projects",
        "education",
        "certifications",
        "experiences",
        "experience",
    ):
        add((profile_json or {}).get(key))
    return fragments


def _probe_has_any(probe: str, aliases: Iterable[str]) -> bool:
    for alias in aliases or []:
        alias_norm = normalize_keyword_for_match(alias)
        if alias_norm and normalized_term_in_probe(probe, alias_norm):
            return True
    return False


def _localized_skill_label(labels: Tuple[str, str], language_code: str) -> str:
    return labels[1] if str(language_code or "").startswith("en") else labels[0]


_DIRECT_USE_MARKERS = (
    "automated test",
    "automates tests",
    "automatise",
    "automatiser",
    "developed tests",
    "developpe des tests",
    "implemented tests",
    "implemente des tests",
    "script",
    "suite de test",
    "test suite",
    "tests automatises",
    "utilise",
    "utiliser",
    "using",
    "used",
)
_BENCHMARK_CONTEXT_MARKERS = (
    "benchmark",
    "benchmarke",
    "benchmarker",
    "compare",
    "comparatif",
    "evaluation",
    "evaluer",
    "explore",
    "exploration",
)
_AUTOMATION_BENCHMARK_TOOL_SPECS: Tuple[Tuple[Tuple[str, str], Tuple[str, ...]], ...] = (
    (("Playwright", "Playwright"), ("playwright",)),
    (("Cypress", "Cypress"), ("cypress",)),
    (("Selenium", "Selenium"), ("selenium",)),
    (("Agilitest", "Agilitest"), ("agilitest",)),
)


def _tool_has_context(
    source_fragments: Sequence[str],
    tool_aliases: Iterable[str],
    markers: Iterable[str],
) -> bool:
    for fragment in source_fragments:
        fragment_norm = normalize_keyword_for_match(fragment)
        if not fragment_norm:
            continue
        if not _probe_has_any(fragment_norm, tool_aliases):
            continue
        if _probe_has_any(fragment_norm, markers):
            return True
    return False


def _benchmark_only_tool_labels(
    profile_json: Dict[str, Any],
    *,
    language_code: str = "fr",
) -> List[str]:
    profile_probe = _collect_source_probe(profile_json, ())
    source_fragments = _collect_source_fragments(profile_json)
    explicit_skill_probe = _collect_source_probe(
        {"skills": (profile_json or {}).get("skills") or []},
        (),
    )

    def profile_has(*aliases: str) -> bool:
        return _probe_has_any(profile_probe, aliases)

    def explicit_skill_has(*aliases: str) -> bool:
        return _probe_has_any(explicit_skill_probe, aliases)

    labels: List[str] = []
    for localized_labels, aliases in _AUTOMATION_BENCHMARK_TOOL_SPECS:
        if not profile_has(*aliases):
            continue
        if explicit_skill_has(*aliases):
            continue
        if _tool_has_context(source_fragments, aliases, _DIRECT_USE_MARKERS):
            continue
        if _tool_has_context(source_fragments, aliases, _BENCHMARK_CONTEXT_MARKERS):
            labels.append(_localized_skill_label(localized_labels, language_code))
    return labels


def skills_section_claims_benchmark_only_tools(
    skills_section: Any,
    profile_json: Dict[str, Any],
    *,
    language_code: str = "fr",
) -> bool:
    """Detect direct tool claims when the profile only supports benchmark context."""

    if not isinstance(skills_section, list):
        return False
    benchmark_only = _benchmark_only_tool_labels(
        profile_json,
        language_code=language_code,
    )
    if not benchmark_only:
        return False
    benchmark_norms = {
        normalize_keyword_for_match(label)
        for label in benchmark_only
        if normalize_keyword_for_match(label)
    }
    for block in skills_section:
        if not isinstance(block, dict):
            continue
        for item in block.get("items") or []:
            item_norm = normalize_keyword_for_match(item)
            if not item_norm or item_norm.startswith("benchmark "):
                continue
            if item_norm in benchmark_norms or any(
                normalized_term_in_probe(item_norm, tool_norm)
                for tool_norm in benchmark_norms
            ):
                return True
    return False


def _build_themed_skill_blocks(
    profile_json: Dict[str, Any],
    technical_items: List[str],
    *,
    offer_terms: Iterable[Any],
    language_code: str,
    max_items_per_block: int,
) -> List[Dict[str, Any]]:
    """Build compact source-backed skill themes when a flat dump needs recovery."""

    profile_probe = _collect_source_probe(profile_json, technical_items)
    source_fragments = _collect_source_fragments(profile_json)
    explicit_skill_probe = _collect_source_probe(
        {"skills": (profile_json or {}).get("skills") or []},
        (),
    )
    offer_probe = normalize_keyword_for_match(" ".join(str(term) for term in offer_terms or []))
    combined_probe = " ".join(part for part in (profile_probe, offer_probe) if part)
    if not combined_probe:
        return []

    def profile_has(*aliases: str) -> bool:
        return _probe_has_any(profile_probe, aliases)

    def explicit_skill_has(*aliases: str) -> bool:
        return _probe_has_any(explicit_skill_probe, aliases)

    def offer_has(*aliases: str) -> bool:
        return _probe_has_any(offer_probe, aliases)

    qa_context = profile_has(
        "qa",
        "test",
        "tests",
        "recette",
        "anomalie",
        "plan de test",
        "qualite logicielle",
    )
    data_context = profile_has(
        "sql",
        "base de donnees",
        "database",
        "postman",
        "postgresql",
        "mongodb",
        "sql server",
    )
    automation_context = profile_has(
        "automatisation",
        "automation",
        "python",
        "playwright",
        "cypress",
        "selenium",
        "agilitest",
        "benchmark",
    )
    ai_context = profile_has(
        "ia",
        "ai",
        "llm",
        "machine learning",
        "prompt engineering",
        "pytest",
        "validation des sorties",
        "json",
    )

    automation_specs = [
        (("Python", "Python"), ("python",), (), True),
    ]
    benchmark_only_tools: List[str] = []
    for labels, aliases in _AUTOMATION_BENCHMARK_TOOL_SPECS:
        if not profile_has(*aliases):
            continue
        if explicit_skill_has(*aliases) or _tool_has_context(
            source_fragments,
            aliases,
            _DIRECT_USE_MARKERS,
        ):
            automation_specs.append((labels, aliases, (), True))
        elif _tool_has_context(source_fragments, aliases, _BENCHMARK_CONTEXT_MARKERS):
            benchmark_only_tools.append(_localized_skill_label(labels, language_code))
    if benchmark_only_tools:
        benchmark_label = (
            f"Benchmark {' / '.join(benchmark_only_tools)}",
            f"Benchmark {' / '.join(benchmark_only_tools)}",
        )
        automation_specs.append(
            (
                benchmark_label,
                ("benchmark", "benchmarke", "benchmarker", *benchmark_only_tools),
                ("tool benchmark", "benchmark"),
                automation_context,
            )
        )
    elif profile_has("benchmark", "benchmarke", "benchmarker", "benchmark d outils"):
        automation_specs.append(
            (
                ("Benchmark d'outils", "Tool benchmarking"),
                ("benchmark", "benchmarke", "benchmarker", "benchmark d outils"),
                ("tool benchmark", "benchmark"),
                automation_context,
            )
        )

    group_specs = [
        (
            ("QA & tests", "QA & testing"),
            qa_context,
            [
                (("Plans de test", "Test plans"), ("plan de test", "plans de test", "test plan"), (), True),
                (("Tests fonctionnels", "Functional testing"), ("test fonctionnel", "tests fonctionnels"), ("functional testing",), qa_context),
                (("Tests API", "API testing"), ("test api", "tests api", "postman", "api testing"), ("api testing", "apis"), qa_context or data_context),
                (("Non-régression", "Regression testing"), ("non regression", "non-régression", "regression testing", "xray"), ("regression",), qa_context),
                (("Analyse des risques", "Risk analysis"), ("analyse des risques", "risque", "risques"), ("risk analysis", "risk"), qa_context),
                (("Cas limites", "Edge cases"), ("cas limite", "cas limites", "edge case"), ("edge case", "edge cases"), qa_context),
                (("Qualification d'anomalies", "Defect qualification"), ("qualification d anomalie", "anomalie", "anomalies", "defect"), (), qa_context),
            ],
        ),
        (
            ("API & data", "API & data"),
            data_context,
            [
                (("Postman", "Postman"), ("postman",), (), True),
                (("SQL", "SQL"), ("sql",), (), True),
                (("PostgreSQL", "PostgreSQL"), ("postgresql", "postgres"), (), True),
                (("MongoDB", "MongoDB"), ("mongodb",), (), True),
                (("Microsoft SQL Server", "Microsoft SQL Server"), ("microsoft sql server", "sql server"), (), True),
            ],
        ),
        (
            ("Automatisation", "Automation"),
            automation_context,
            automation_specs,
        ),
        (
            ("IA & qualité logicielle", "AI & software quality"),
            ai_context,
            [
                (("LLM", "LLM"), ("llm", "llms", "large language model"), (), True),
                (("Prompt engineering", "Prompt engineering"), ("prompt engineering",), ("prompt engineering",), ai_context),
                (("Validation de sorties", "Output validation"), ("validation des sorties", "valider les sorties", "sorties produites", "output validation"), ("output validation",), ai_context),
                (("pytest", "pytest"), ("pytest",), (), True),
                (("JSON", "JSON"), ("json",), (), True),
            ],
        ),
        (
            ("Data & BI", "Data & BI"),
            profile_has("tableau", "power bi", "looker", "dashboard", "kpi", "data analytics"),
            [
                (("Tableau", "Tableau"), ("tableau",), (), True),
                (("Power BI", "Power BI"), ("power bi", "powerbi"), (), True),
                (("Looker", "Looker"), ("looker",), (), True),
                (("Dashboards", "Dashboards"), ("dashboard", "dashboards", "tableau de bord"), ("dashboard",), True),
                (("KPI", "KPI"), ("kpi",), (), True),
            ],
        ),
        (
            ("Delivery & collaboration", "Delivery & collaboration"),
            profile_has("jira", "xray", "gherkin", "agile", "scrum", "documentation"),
            [
                (("Jira", "Jira"), ("jira",), (), True),
                (("Xray", "Xray"), ("xray",), (), True),
                (("Gherkin", "Gherkin"), ("gherkin",), (), True),
                (("Documentation QA", "QA documentation"), ("documentation qa", "documentation"), ("documentation",), qa_context),
                (("Agile/Scrum", "Agile/Scrum"), ("agile", "scrum"), (), True),
                (("Suivi d'anomalies", "Defect tracking"), ("suivi d anomalie", "suivi des anomalies", "anomalie"), (), qa_context),
            ],
        ),
    ]

    blocks: List[Dict[str, Any]] = []
    globally_seen: set[str] = set()
    for category_labels, group_context, specs in group_specs:
        if not group_context:
            continue
        items: List[str] = []
        for labels, profile_aliases, offer_aliases, allow_offer_reframe in specs:
            direct = profile_has(*profile_aliases)
            reframed = (
                bool(allow_offer_reframe)
                and bool(offer_aliases)
                and offer_has(*offer_aliases)
            )
            if not direct and not reframed:
                continue
            label = _localized_skill_label(labels, language_code)
            key = normalize_keyword_for_match(label)
            if not key or key in globally_seen:
                continue
            globally_seen.add(key)
            items.append(label)
            if len(items) >= max(1, int(max_items_per_block or 1)):
                break
        if len(items) < 2:
            continue
        blocks.append(
            {
                "category": _localized_skill_label(category_labels, language_code),
                "items": items,
            }
        )

    if not blocks:
        return []

    return blocks[:4]


def build_skill_blocks_from_profile(
    profile_json: Dict[str, Any],
    *,
    offer_terms: Iterable[Any] = (),
    extra_terms: Iterable[Any] = (),
    language_code: str = "fr",
    max_items_per_block: int = 10,
) -> List[Dict[str, Any]]:
    profile = profile_json if isinstance(profile_json, dict) else {}
    technical_candidates: List[str] = []
    soft_candidates: List[str] = []

    for entry in profile.get("skills") or []:
        if isinstance(entry, dict):
            _extend_candidates(technical_candidates, entry.get("name"), profile)
            _extend_candidates(technical_candidates, entry.get("skill"), profile)
            _extend_candidates(technical_candidates, entry.get("items"), profile)
        else:
            _extend_candidates(technical_candidates, entry, profile)

    for entry in profile.get("projects") or []:
        if not isinstance(entry, dict):
            continue
        _extend_candidates(technical_candidates, entry.get("technologies"), profile)
        _extend_candidates(technical_candidates, entry.get("tech_stack"), profile)
        _extend_candidates(technical_candidates, entry.get("skills"), profile)
        _extend_candidates(technical_candidates, entry.get("tools"), profile)

    for entry in profile.get("education") or []:
        if not isinstance(entry, dict):
            continue
        for key in (
            "field_of_study",
            "details",
            "description",
            "courses",
            "modules",
            "specialization",
            "specialisation",
            "skills",
        ):
            _extend_candidates(technical_candidates, entry.get(key), profile)

    for entry in profile.get("certifications") or []:
        if isinstance(entry, dict):
            _extend_candidates(technical_candidates, entry.get("name"), profile)

    for entry in profile.get("soft_skills") or []:
        if isinstance(entry, dict):
            _extend_candidates(soft_candidates, entry.get("name"), profile)
            _extend_candidates(soft_candidates, entry.get("items"), profile)
        else:
            _extend_candidates(soft_candidates, entry, profile)

    if collect_named_tool_hints is not None:
        technical_candidates.extend(collect_named_tool_hints(profile, max_items=24))

    supported_extra_terms = collect_supported_skill_terms(extra_terms, profile)
    technical_candidates.extend(supported_extra_terms.get("technical") or [])
    soft_candidates.extend(supported_extra_terms.get("soft") or [])

    technical_items = _dedup_preserve(technical_candidates)
    soft_items = _dedup_preserve(soft_candidates)

    blocks: List[Dict[str, Any]] = []
    preserve_block_order = False
    themed_blocks = _build_themed_skill_blocks(
        profile,
        technical_items,
        offer_terms=offer_terms,
        language_code=language_code,
        max_items_per_block=max_items_per_block,
    )
    if themed_blocks:
        blocks.extend(themed_blocks)
        preserve_block_order = True
    elif technical_items:
        blocks.append(
            {
                "category": (
                    "Technical Skills"
                    if language_code == "en"
                    else "Competences techniques"
                ),
                "items": technical_items,
            }
        )
    if soft_items:
        blocks.append(
            {
                "category": "Soft Skills" if language_code == "en" else "Qualites",
                "items": soft_items,
            }
        )

    if not blocks:
        return []

    if supported_extra_terms.get("soft"):
        blocks.sort(
            key=lambda block: (
                0
                if classify_skill_bucket(" ".join(block.get("items") or []))
                == "technical"
                else 1
            )
        )

    ranked = [] if preserve_block_order else rank_skill_blocks_by_relevance(
        blocks, list(offer_terms or [])
    )
    selected_blocks = ranked if ranked else blocks

    technical_limit = max(1, int(max_items_per_block))
    soft_limit = max(0, min(6, int(max_items_per_block)))
    clamped: List[Dict[str, Any]] = []
    for block in selected_blocks:
        if not isinstance(block, dict):
            continue
        items = [
            item
            for item in (block.get("items") or [])
            if isinstance(item, str) and item.strip()
        ]
        category_norm = normalize_keyword_for_match(block.get("category") or "")
        is_soft_block = category_norm in {
            "soft skills",
            "soft skill",
            "qualites",
            "qualites personnelles",
            "strengths",
        }
        limit = soft_limit if is_soft_block else technical_limit
        if limit <= 0:
            continue
        next_block = dict(block)
        next_block["items"] = items[:limit]
        if next_block["items"]:
            clamped.append(next_block)

    return clamped if clamped else selected_blocks
