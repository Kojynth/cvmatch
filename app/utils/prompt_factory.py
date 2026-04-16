"""Prompt builder helpers for LLM stages."""

from __future__ import annotations

from typing import Any, Dict, List


def collect_offer_prompt_keywords(analysis: Dict[str, Any] | None) -> List[str]:
    keywords: List[str] = []
    if not isinstance(analysis, dict):
        return keywords
    for key in ("keywords", "skills", "tech_keywords", "soft_keywords", "tools", "lexical_field"):
        value = analysis.get(key)
        if isinstance(value, list):
            keywords.extend(str(item) for item in value)
        elif isinstance(value, str):
            keywords.extend(part.strip() for part in value.split(",") if part.strip())
    families = analysis.get("keyword_families")
    if isinstance(families, dict):
        for value in families.values():
            if isinstance(value, list):
                keywords.extend(str(item) for item in value)
            elif isinstance(value, str):
                keywords.extend(part.strip() for part in value.split(",") if part.strip())
    return keywords


def get_cover_letter_style_hint(template_key: str) -> str:
    return {
        "modern": "Ton moderne et direct, phrases courtes, tres specifique.",
        "classic": "Ton formel et corporate, vocabulaire sobre.",
        "tech": "Ton technique/pro: concret, oriente realisations et stack verifiable.",
        "creative": "Ton dynamique, orientation projets/impact, mais professionnel.",
    }.get(template_key, "Ton professionnel et specifique.")


def build_offer_keywords_messages(
    *,
    language_code: str,
    job_title: str,
    company: str,
    offer_text: str,
) -> Dict[str, str]:
    system_prompt = (
        "You analyze job offers. Return JSON only matching the schema. "
        "Extract concise, high-signal keywords and requirements. "
        "Do not invent information not present in the offer."
    )

    user_prompt = f"""
LANGUAGE: {language_code}
JOB_TITLE: {job_title}
COMPANY: {company}
JOB_OFFER_TEXT:
{offer_text}

  OUTPUT RULES:
  - Return JSON only.
  - Keep lists short (max 12 items per list).
  - Only extract items that are clearly supported by JOB_OFFER_TEXT; do not pad lists to meet a minimum count.
  - Aim for keywords>=8, skills>=4, tools>=2 only when the offer text clearly provides that many distinct items.
  - Use short noun phrases (2-5 words).
  - skills = hard skills/tech stack only.
  - soft_skills = interpersonal traits only.
  - responsibilities = action verbs or short duties.
  - lexical_field = vocabulary used in this profession/role in the offer language.
  - keyword_families = map key requirement -> close terms/synonyms/acronyms used in this domain.
  - keyword_families values must stay factual and aligned with JOB_OFFER_TEXT.
  - For each keyword family, provide 2-6 close terms max, no generic fluff.
  - language must match LANGUAGE; translate if the offer is in another language.
  - Do not mix languages inside the same extracted item.
  - job_title/company should mirror JOB_TITLE/COMPANY when provided.
  """.strip()

    return {"system": system_prompt, "user": user_prompt}


def build_cv_json_messages(
    *,
    language_code: str,
    job_title: str,
    company: str,
    offer_text: str,
    profile_block: str,
    offer_keywords_block: str = "",
    priority_terms_block: str = "",
    matched_keywords_block: str = "",
    critic_block: str = "",
    retry_guidance_block: str = "",
    section_guidance_block: str = "",
    previous_cv_block: str = "",
    user_instruction_block: str = "",
    evidence_policy_block: str = "",
    stage: str = "draft",
) -> Dict[str, str]:
    system_prompt = (
        "You are a CV generator. Return JSON only that matches the schema. "
        "JOB_OFFER_TEXT and OFFER_KEYWORDS_JSON define the target positioning, vocabulary, and priorities. "
        "PROFILE_JSON constrains identity, chronology, evidence, and contact facts, but not wording. "
        "Rewrite supported facts with the job-offer terminology whenever it stays truthful. "
        "Do not invent data. "
        "Use empty strings for unknown scalar fields and empty lists for missing sections. "
        "All text must be in LANGUAGE; do not mix languages. "
        "Translate any source-language profile fragments fully into LANGUAGE except proper nouns, official product names, and established acronyms. "
        "Select the most relevant items for the job offer. "
        "Avoid decorative or bullet characters inside field text. "
        "CRITIC_JSON is feedback, not content. Do not quote or paraphrase it."
    )

    user_prompt = f"""
LANGUAGE: {language_code}
JOB_TITLE: {job_title}
COMPANY: {company}
JOB_OFFER_TEXT:
{offer_text}

PROFILE_JSON (source of truth):
{profile_block}
{offer_keywords_block}
{priority_terms_block}
{matched_keywords_block}
{critic_block}
{retry_guidance_block}
{section_guidance_block}
{previous_cv_block}
{user_instruction_block}
{evidence_policy_block}

OUTPUT RULES:
- Return JSON only.
- Keep required sections even if empty lists.
- Align content with job offer (keywords, order, relevance).
- JOB_OFFER_TEXT and PRIORITY_OFFER_TERMS are the editorial target. PROFILE_JSON is the factual boundary.
- Do not copy PROFILE_JSON sentences verbatim; rewrite with concise recruiter wording while preserving facts.
- Prefer the offer vocabulary over the original profile wording when both describe the same evidence.
- Use the same lexical field as JOB_OFFER_TEXT when evidence exists in PROFILE_JSON.
- Do not add facts not present in PROFILE_JSON.
- contact fields must be copied from PROFILE_JSON.personal_info when available.
- target_company and target_job_title should reflect the offer; use empty strings if missing.
- Never use placeholders (no [A COMPLETER], [TO COMPLETE], or bracketed tokens).
- In field text, never use decorative special characters like • « » ^ {{ }} [ ].
- Skills items must be short noun phrases (no sentences, no "candidate should/must").
- ats_keywords must be a list of strings from the job offer or OFFER_KEYWORDS_JSON.
- If OFFER_KEYWORDS_JSON is present, prioritize it for relevance and ATS terms.
- If OFFER_KEYWORDS_JSON.keyword_families or lexical_field is present, reuse that domain vocabulary in summary/skills/experience when factual.
- Keyword coverage target: include at least 8 high-signal offer terms across summary/skills/experience when facts support them.
  Exact offer terms are preferred; professional synonyms/acronyms are allowed when they stay factual.
- render_hints.notes can be freeform guidance for rendering.
- render_hints.section_order/emphasis/tone are structured hints.
- Do not include review or instruction text in any field (no critique, no "this CV needs", no "should").
- Summary must be candidate-focused (role, strengths, impact). Do not describe employer mission/history.
- If MATCHED_KEYWORDS is present, ensure those terms appear in summary/skills/experience when relevant.
- If RETRY_GUIDANCE is present, treat it as high-priority rewrite direction.
- MANDATORY for each experience item: rewrite entirely — never copy source description text verbatim.
  * summary: 1 compact sentence (scope + context, offer-aligned vocabulary).
  * highlights: 2-4 short plain strings; each must start with a strong action verb,
    express one main idea, and include at least one term from PRIORITY_OFFER_TERMS
    or JOB_OFFER_TEXT when factual.
  * highlights must not start with '-', '*', digits, or decorative bullet glyphs.
  * If source description is a long paragraph or dash-separated list, condense it into these 2-4 ATS-safe highlights.
- If PROFILE_JSON text is in another language, translate it to LANGUAGE (keep proper nouns, tools, company names).
- Do not leave mixed-language clauses such as English headings with French verbs or nouns in the same sentence.
- Keep output compact:
  * experience <= 4 items, highlights <= 4 each.
  * skills <= 4 categories, items <= 6 each, ordered by relevance to JOB_OFFER_TEXT.
  * education <= 3 items.
  * projects <= 3 items.
  * languages <= 4 items.
  * certifications <= 3 items.
  * ats_keywords <= 15 items.
- Structure and ordering:
  * Experience and projects must be in reverse chronological order (most recent first).
  * For each experience item, include a duration field when reliable start/end dates are available.
  * For each project item, set the duration field when source evidence supports it (e.g. "2 ans", "6 mois", "3 ans"); do not invent dates.
  * Use a single consistent date format across the entire CV (prefer MM/YYYY or YYYY only; never mix formats).
- Writing quality — apply to all free-text fields:
  * Never use first-person pronouns (je, moi, mon, nous, notre, j'); start every bullet with a conjugated action verb or an infinitive.
  * Use present tense for the current or ongoing role; use past tense (passé composé or imparfait) for all former roles.
  * Avoid cliché adjectives and filler intensifiers: do not use passionné, dynamique, motivé, polyvalent, rigoureux, très, vraiment, extrêmement, or similar; replace with concrete evidence instead.
  * Vary action verbs — do not repeat the same verb more than twice across all highlights and summary combined.
  * Use consistent punctuation style: if bullets end without a period, apply that to all; never mix styles.
  * Prefer direct, concrete phrasing; remove decorative filler.
- Impact and personalization:
  * Bullet structure preference when facts support it: "action verb + what was done + measurable result/impact".
  * Include quantitative evidence when available: team size, percentages, user count, volumes, time saved, revenue figures.
  * Mention the target company (COMPANY) at least once — in summary or in a highlight — to reinforce personalization; do not invent facts.
""".strip()

    if stage == "final":
        user_prompt += (
            "\n\nRevise using CRITIC_JSON guidance. "
            "Use SECTION_KEYWORD_GUIDANCE to route missing offer terms to the best sections. "
            "If PREVIOUS_CV_JSON is provided, improve it rather than starting over. "
            "Include must_keep_facts, but also use other relevant facts from PROFILE_JSON. "
            "Do not include critique or instructions in any field."
        )

    return {"system": system_prompt, "user": user_prompt}


def build_critic_messages(
    *,
    job_title: str,
    company: str,
    offer_text: str,
    cv_html_block: str,
) -> Dict[str, str]:
    system_prompt = (
        "You are a strict ATS reviewer. Return JSON only matching the schema. "
        "Analyze the CV HTML against the job offer. Do not invent facts."
    )

    user_prompt = f"""
JOB_TITLE: {job_title}
COMPANY: {company}
JOB_OFFER_TEXT:
{offer_text}

CV_HTML:
{cv_html_block}

SCORECARD RULES:
- All scores are integers 0-100.
- overall = round(ats_keyword_coverage*0.30 + clarity*0.20 + evidence_metrics*0.30 + consistency*0.20)
- Clamp each metric to [0,100] before computing overall.
- If any issue.severity == "blocker", overall = min(overall, 39).
- Bands: 0-39 reject, 40-59 weak, 60-79 acceptable, 80-100 strong.

OUTPUT RULES:
- Return JSON only.
- missing_keywords: only keywords from the job offer not present in CV_HTML.
- must_keep_facts: only facts found in CV_HTML.
- issues: max 6 items, keep each problem/fix concise.
- rewrite_plan: max 8 items, short phrases.
- If contact details appear in CV_HTML, include them in must_keep_facts.
- If the summary describes the employer/company instead of the candidate, add a high severity issue.
""".strip()

    return {"system": system_prompt, "user": user_prompt}


def build_generic_cv_messages(
    *,
    language_code: str,
    profile_block: str,
    evidence_policy_block: str = "",
    culture_hint: str = "",
) -> Dict[str, str]:
    """Build LLM messages for generic CV generation (no specific job offer).

    Produces a standalone professional CV from a profile, without adapting to
    any particular job offer. Reuses quality rules from build_cv_json_messages
    but drops job-offer targeting, ats_keywords, and company personalisation.

    Args:
        language_code: ISO 639-1 target language code (e.g. "fr", "en", "ja").
        profile_block: JSON-serialised profile dict (source of truth).
        evidence_policy_block: Optional EVIDENCE_POLICY prompt block.
        culture_hint: Optional cultural CV-writing directives for the target
            language/country. Advisory only — never suppresses profile data.
    """
    _culture_section = (
        f"\n\nCULTURE_AND_FORMAT_CONVENTIONS:\n{culture_hint.strip()}"
        if culture_hint and culture_hint.strip()
        else ""
    )
    system_prompt = (
        "You are a professional CV writer. Return JSON only that matches the schema. "
        "PROFILE_JSON is the single source of truth: identity, chronology, evidence, and contact facts. "
        "Rewrite supported facts with recruiter-quality wording. "
        "Do not invent data not present in PROFILE_JSON. "
        "Use empty strings for unknown scalar fields and empty lists for missing sections. "
        "All text must be in LANGUAGE; do not mix languages. "
        "Translate any source-language profile fragments fully into LANGUAGE except proper nouns, "
        "official product names, and established acronyms. "
        "Avoid decorative or bullet characters inside field text."
        + _culture_section
    )

    user_prompt = f"""
LANGUAGE: {language_code}
ADAPT the presentation of PROFILE_JSON facts to the cultural conventions above when provided.
Do not invent new facts; reuse only what is present in PROFILE_JSON.

PROFILE_JSON (source of truth):
{profile_block}
{evidence_policy_block}

OUTPUT RULES:
- Return JSON only.
- Keep required sections even if empty lists.
- Do not copy PROFILE_JSON sentences verbatim; rewrite with concise recruiter wording while preserving facts.
- Do not add facts not present in PROFILE_JSON.
- contact fields must be copied from PROFILE_JSON.personal_info when available.
- target_company and target_job_title must be empty strings (no specific offer).
- ats_keywords must be an empty list.
- Never use placeholders (no [A COMPLETER], [TO COMPLETE], or bracketed tokens).
- In field text, never use decorative special characters like \u2022 \u00ab \u00bb ^ {{}} [ ].
- Skills items must be short noun phrases (no sentences).
- Structure and ordering:
  * Experience and projects must be in reverse chronological order (most recent first).
  * Use a single consistent date format across the entire CV (prefer MM/YYYY or YYYY only).
  * For each experience item, include a duration field when reliable start/end dates are available.
  * For each project item, set the duration field when source evidence supports it; do not invent dates.
- Keep output compact:
  * experience <= 5 items, highlights <= 4 each.
  * skills <= 4 categories, items <= 8 each.
  * education <= 3 items.
  * projects <= 3 items.
  * languages <= 6 items.
  * certifications <= 4 items.
- Writing quality:
  * Never use first-person pronouns; start every bullet with a strong action verb.
  * Use present tense for current/ongoing role; past tense for former roles.
  * Avoid cliche adjectives: passionné, dynamique, motivé, polyvalent, rigoureux, très, vraiment.
  * Vary action verbs across all highlights and summary.
  * Bullet structure preference when facts support it: action verb + what + measurable result/impact.
  * Include quantitative evidence when available in PROFILE_JSON.
- Summary: candidate-focused (role, strengths, key achievements). Do not describe employer.
- Generate the best standalone professional CV from this profile.
""".strip()

    return {"system": system_prompt, "user": user_prompt}


def build_cover_letter_prompt(
    *,
    language_code: str,
    template: str,
    style_hint: str,
    job_title: str,
    company: str,
    keywords_text: str,
    offer_text: str,
    offer_keywords_json: str,
    profile_block: str,
    placeholder: str,
    candidate_signature: str,
) -> str:
    if language_code == "en":
        letter_skeleton = f"""Subject: Application - {job_title} ({company})

Dear Hiring Manager,

<Paragraph 1: hook + why this role/company (specific)>

<Paragraph 2: 2-3 proof points (experience/projects) + verified skills + impact>

<Paragraph 3: motivation + projection + interview availability>

Sincerely,

{candidate_signature}"""
    else:
        letter_skeleton = f"""Objet: Candidature - {job_title} ({company})

Madame, Monsieur,

<Paragraphe 1: accroche + pourquoi ce poste/entreprise (specifique)>

<Paragraphe 2: 2-3 preuves de fit (experiences/projets) + competences cles verifiables + impact>

<Paragraphe 3: motivation + projection + disponibilite pour entretien>

Je vous prie d'agreer, Madame, Monsieur, l'expression de mes salutations distinguees.

{candidate_signature}"""

    return f"""
LANGUE: {language_code}
STYLE (template): {template} ({style_hint})

OFFRE CIBLE:
- Poste: {job_title}
- Entreprise: {company}
- Mots-cles detectes: {keywords_text}
- Description (brut, tronquee si besoin):
{offer_text}

OFFER_KEYWORDS_JSON (si disponible):
{offer_keywords_json}

DONNEES CANDIDAT (Profil detaille + CV de reference + lettre type si fournie):
{profile_block}

SORTIE OBLIGATOIRE (texte uniquement, pas de Markdown):
- Respecte STRICTEMENT la structure ci-dessous.
- Utilise UNE SEULE langue: {language_code} (pas de melange FR/EN).
- Utilise uniquement les faits presents dans les donnees candidat (sinon {placeholder}).
- Mots-cles ATS: tu peux reprendre les termes de l'offre OU des synonymes/termes equivalents, tant que le fond reste vrai.
- Reprends aussi le champ lexical metier d'OFFER_KEYWORDS_JSON (keyword_families/lexical_field) si pertinent.
- Couvre au minimum 4 mots-cles de l'offre dans le corps de la lettre (terme exact prefere, synonyme/acronyme metier accepte).
- Longueur: maximum 1 page.

STRUCTURE:
{letter_skeleton}
""".strip()
