# Quick Operating Notes

- Read `AGENTS.md` first.
- This repo is not greenfield. Preserve working flows and migrate incrementally.
- Keep `mass_apply` in scope even if parts of its source are missing in this
  clone. Do not remove it.
- Keep UI/workers thin. New logic goes to `app/domain`, `app/infra`, or
  `app/integrations`.
- Never break:
  - profile JSON round-trip
  - CV JSON contracts
  - history/export consistency
  - deterministic generation fallback
  - PII-safe logging
  - one-page CV output via prioritized content -> HTML render -> measured
    fit -> controlled compression -> PDF export; `ONE_PAGE_PRINT_CSS`
    must keep a single print block with A4 margins, no forced `body`
    height, no `overflow: hidden`, and `break-inside: avoid` on structured
    entries; `_enforce_single_page_budget` remains the experience-density
    backstop in `cv_postprocessing.py`
  - header render contract: actionable contacts are explicit links
    (`mailto:`, `tel:`, LinkedIn, GitHub, portfolio), placeholder labels
    like `Lien 1` are forbidden, and the target subtitle must read as a
    candidature target (`Poste vise` / `Target role`) rather than an
    employer label
  - one-page content allocation contract: real summary (max 3 short lines),
    3-5 credible technical skills, a natural positioning sentence appended
    to the summary when grounded offer/company signal exists, 2-3 impacts
    per role chosen from the strongest action-led evidence, one featured
    project, compact certifications, and no fallback to a vague
    `additional relevant details` blob when structured sections exist;
    never truncate final rendered sentences with `...` / `…`, select whole
    grounded sentences instead
  - positioning-sentence word-sourcing hierarchy:
    **Generation > Offer-skill > Profile-verbatim**, with hard-reject of
    verbs, prepositions, adverbs, and generic field nouns (see
    `collect_targeted_offer_terms` + `_skillish_score` in
    `cv_summary_adaptation.py`)
  - photo presence in rendered CV (user HTML edits preserved by
    non-destructive injection via `ensure_photo_in_raw_html` in
    `app/utils/cv_html_photo_inject.py`, NOT by bypass-regenerate —
    photo is a product invariant, independent of user edits)
  - positioning-sentence phrase preference: multi-word phrases over bare
    tokens; blocklist rejects bare verbs (`believe`, `build`, `work`),
    pronouns (`us`, `we`, `you`), and generic task nouns (`tasks`,
    `things`, `items`); multi-word scoring bonus is `+2` in
    `_skillish_score`
  - clip-repair-at-source: `_polish_experience_fragment` strips trailing
    `…` / `...` / dangling connectors on entry; orchestrator
    alignment-retry loop includes a final
    `_repair_clipped_bullets` + `_dedup_fuzzy_highlights` pass before
    returning success
- final experience dedup contract: every final payload path must run
  cross-entry dedup before one-page budgeting/export, but dedup may only
  merge retries with compatible normalized periods; same company/title with
  conflicting periods must survive as distinct stints
- targeted-summary candidate contract: the positioning sentence must inspect
  profile-backed aligned skills/talents first, not just
  `missing_summary_terms`; cross-domain offer-only terms are allowed, but
  they must not evict better grounded aligned signal
- positioning render contract: when present, the positioning sentence stays
  in the final rendered summary as its closing sentence and should read
  naturally, not as a raw keyword dump
- offer-only term placement contract: pure offer-only vocabulary belongs only
  in the natural positioning sentence; do not surface unsupported offer-only
  terms as proven skills or experience facts unless profile evidence supports
  a coherent implicit inference
- experience render-selection contract: rendered experience details prefer
  the 2-3 most offer-aligned action/impact sentences; company-description
  prose is only weak sector context and usually should not appear in the CV
- sector/industry signal contract: sector hints are allowed only as a minor
  ranking/vocabulary bonus, never as a hard gate and never over stronger
  offer-skill/profile evidence
- offer-keyword extraction contract: prioritize requirement-heavy sections
  (`Role summary`, responsibilities, `About you`, stack/tools, ideal profile)
  over company marketing, benefits, remote policy, or hiring-process text
- explicit tool naming contract: when the profile or offer supports concrete
  named tools/software/platforms/systems, prefer those names over vague
  wording like "automation tools", "billing software", or "outils de
  facturation"
- vague tooling phrase contract: generic tool categories are fallback context
  only; if named products exist in the source, surface the named products
- High-risk files:
  - `app/workers/llm_worker.py`
  - `app/workers/qwen_manager.py`
  - `app/workers/bulk_apply_worker.py`
  - `app/workers/bulk_generation_worker.py`
  - `app/workers/job_fetch_worker.py`
  - `app/utils/profile_json.py`
  - `app/utils/cv_postprocessing.py`
  - `app/utils/cv_quality_audit.py`
  - `app/utils/mass_apply/*`
  - `app/utils/ats/*`
  - `app/models/database.py`
  - `app/controllers/export_manager.py`
  - `app/views/panels/mass_application_panel.py`
  - `app/views/panels/bulk_apply_review_dialog.py`
  - `app/views/profile_details_editor.py`
  - `app/views/generic_cv_export_dialog.py`
  - `app/workers/generic_cv_export_worker.py`
- Profile-domain extraction status:
  - `app/domain/profile/date_support.py` now owns deterministic date-support
    metadata derivation.
  - `app/domain/profile/section_mappers.py` now owns
    `experiences`/`education` mapping.
  - `app/domain/profile/personal_info.py` now owns personal-info extraction and
    link normalization/merge helpers.
  - `app/domain/profile/skill_language_mappers.py` now owns
    `skills`/`soft_skills`/`languages` mapping.
  - `app/domain/profile/artifact_mappers.py` now owns
    `projects`/`certifications`/`publications`/`volunteering`/`awards`/
    `references`/`interests` mapping.
  - `app/utils/profile_json.py` remains the compatibility facade and canonical
    round-trip entrypoint.
- Required validation:
  - `python -m py_compile <touched files>`
  - targeted pytest scope
  - explicit code review
  - explicit security review
- CV generation quality reminders:
  - keep ATS-first, one-language output
  - keep reverse chronology, consistent dates, and explicit durations when
    reliable
  - keep 2-4 concise bullets per role when bullets are available
  - prefer `action + what + impact`, strong verbs, no first-person pronouns,
    no filler or keyword stuffing
  - use offer keywords pertinently by section and company context
  - controlled inferred impact and grounded reframing are allowed when implicit
    in the profile, but do not introduce invented facts, technologies,
    projects, certifications, or exact metrics
  - **Sourcing principle**: every produced sentence, bullet, or skill label
    must be sourced from **either the profile JSON or the job offer data**.
    Product goal = *reformulate profile skills in the offer's vocabulary*.
    Offer-sourced positioning (cross-domain keywords, company framing) is
    legitimate. Ex-nihilo content (neither in profile nor offer) is forbidden.
    When designing a filter, ask: would it reject a legitimate offer-sourced
    reformulation? If yes → too tight.
  - permissive on sourced content, strict on fragment bullets / clipped
    phrases / prefix duplicates — the user can refine a coherent hallucination
    in the editor, but a truncated sentence is garbage that must not ship
  - `CVMATCH_CV_EVIDENCE_MODE=strict_factual|inferred_impact` controls this
    boundary; default runtime behavior is `inferred_impact`
- Generic standalone CV export:
  - `app/views/generic_cv_export_dialog.py` and
    `app/workers/generic_cv_export_worker.py` are now a real path from profile
    editor to PDF export.
  - This path must keep explicit model selection, safe logging, deterministic
    fallback, and the same minimum postprocess/quality gate as the main CV
    pipeline.
- Pytest temp artifacts now live under `runtime/pytest_tmp/`.
- Prefer wrappers and shims over large moves.
- No destructive git commands. No secrets or user data in Git.
- Be lenient when developing. Prefer additive, permissive fixes over new
  filters, stricter thresholds, or narrower allowlists. Every tightening
  ships with a regression test that pins legitimate inputs that must still
  pass (see commit 697ffd5 for the reference incident: short-token filter
  and single-term threshold silently killed valid summary enrichment and
  duplicate-bullet dedup). If a bug can be fixed by repairing the existing
  branch instead of rejecting the input upstream, prefer the repair.
