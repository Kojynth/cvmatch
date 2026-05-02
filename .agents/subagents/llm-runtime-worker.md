# Name
llm-runtime-worker

# Type
execution

# Utilite reelle pour ce projet
High. The LLM runtime is the main source of memory, fallback, and regression
risk.

# Quand l'utiliser
- `llm_worker`
- `qwen_manager`
- stage subprocess helpers
- model routing or memory policy
- deterministic fallback or critic/final stages

# Quand ne pas l'utiliser
- extraction-only changes
- simple docs, hooks, or UI edits

# Permissions/outils
- may edit `app/workers/*`, `app/domain/generation/*`,
  `app/infra/model_runtime/*`, and related tests
- may run targeted tests and compile checks

# Entrees
- issue summary
- invariant to preserve
- changed-path scope

# Sorties
- minimal patch
- tests executed
- residual runtime risk note

# Risques
- GPU/RAM regressions
- subprocess timeout regressions

# Garde-fous
- diagnose and analyze before editing: reproduce or inspect the runtime issue,
  identify the impacted fallback/model contract, and ask a concise clarifying
  question when ambiguity cannot be resolved safely from repository context
- preserve deterministic minimum-schema fallback
- do not change DB or UI contracts unless explicitly coordinated
- do not expose a new model without registry/runtime/test coherence
- when CV generation or adaptation quality is in scope, enforce ATS-first
  structure, one-language output, reverse chronology, consistent dates,
  explicit durations when reliable, 2-4 concise bullets per role when the
  profile supports bullets, and grounded keyword usage rather than lexical
  stuffing
- keep deterministic generation helpers profession-agnostic,
  company-agnostic, profile-agnostic, and language-agnostic: runtime code,
  fallback builders, validators, renderers, and postprocessors may enforce
  neutral structure, filters, source collection, and retry/critic rules, but
  must not hardcode reader-facing role/company/profile-specific prose or fixed
  profession/sector contribution formulas. Specific CV or cover-letter wording
  belongs in source-backed LLM prompting/generation for the selected language.
- when runtime changes can affect final CV rendering, preserve the one-page
  **fit-to-page** contract end to end: prioritized content allocation,
  measured rendered height, controlled compression tiers, then PDF export
  (never rely on CSS clipping or crop-to-page); direct WeasyPrint exports must
  keep `PDF_ONE_PAGE_FIT_CSS` aligned with the preview print contract
- if runtime output changes flow into preview/export, verify WebEngine PDF
  export still prints from a dedicated hidden `QWebEngineView` and does not
  reload, rescale, or mutate the visible preview during export
- preserve the header render contract for generated CVs: actionable contact
  methods render as explicit links (`mailto:`, `tel:`, LinkedIn, GitHub,
  portfolio URL), placeholder labels like `Lien 1` / `Link 1` are forbidden,
  and the target subtitle must read as a candidature target
  (`Poste visé` / `Target role`) rather than an employer label
- preserve one-page section allocation: summary (max 3 short lines), up to 10
  compact credible skill/tool chips when layout allows, a natural grounded positioning sentence appended
  to the summary when available, 2-3 concrete impacts per role chosen from
  the strongest action-led evidence, one featured project when present,
  compact certifications, and no fallback to a vague `additional relevant
  details` blob when structured data exists
- when summary assembly is in scope, build the final rendered summary after
  retained experience/project/certification blocks are selected, avoid
  repeating the same signals already visible in rendered experience bullets,
  and keep `{company}` visible in a natural `{job_title}` relevance sentence;
  preserve an
  existing sentence only when it still beats or matches the recomputed
  candidate in alignment quality
- when experience rendering is in scope, preserve asymmetric detail budgets:
  protect the most aligned anchor role first, then compress lower-priority
  roles; have the LLM rewrite dense source evidence into 2-4 new coherent
  bullets instead of dropping useful proof, copying source fragments, or
  mechanically joining them in the renderer; preserve high-signal keywords,
  named tools, and role vocabulary that carry offer/profile alignment
- when profile detail feedback / "Visualiser les détails" is in scope, keep
  date-driven tense guidance visible: present-tense action verbs for current
  roles, past-tense action verbs for ended roles, without renderer-side
  language-wide verb replacement lists
- keep rendered role order reverse-chronological; relevance decides detail
  density, not visible role order
- do not rely on renderer-side sentence clipping with `...` / `…`; if output
  quality affects render density, prefer better sentence selection upstream
- treat sector/industry hints only as minor ranking/vocabulary bonuses; they
  must never override stronger offer-skill/profile evidence or justify
  invented content
- pure offer-only vocabulary may appear in the summary's natural positioning
  sentence, but must not be emitted elsewhere as proven skill/experience fact
  unless the profile supports a coherent implicit inference
- company targeting must keep `{company}` visible in a natural `{job_title}`
  relevance sentence; avoid keyword-dump patterns like "Profil pertinent pour
  COMPANY grace a A, B, C"
- if profile or offer evidence includes concrete named tools/software/
  platforms/systems, prefer naming them explicitly over vague tooling wording
- generic tool categories are fallback only; if named products are present in
  source evidence, surface the named products instead
- featured skill chips must come from the profile `skills` pool first;
  experience/project evidence may reprioritize or compactly rewrite those
  labels, but must not create extra chips from narrative bullets alone; compact
  grouped chips are acceptable for strongly targeted offers when they clarify
  hierarchy/proof and are driven by `{job_title}` plus requirement-heavy offer
  evidence in the generated CV JSON, not by a hardcoded
  company/profile/tech-only renderer taxonomy
- thematic fallback rows such as `QA & tests`, `API & data`, `Automation`,
  `AI & software quality`, `Data & BI`, or future profession groups are
  quality helpers, not global priorities. Preserve them when source-backed,
  but rank their order and survival by target-offer score. A QA profile should
  still produce a strong QA CV for a QA offer; for non-QA offers, better
  aligned profile/project evidence must be able to outrank QA. Use a generic
  role-aligned block for strongly offer-aligned profile skills that do not fit
  existing themes. Keep 4 fallback skill blocks by default; allow 5 only when
  an offer exists, at least two experience/project sources are aligned, and
  the fifth block has a positive offer score while preserving one-page fit.
- do not backfill weak/noisy skill chips purely to hit the visible chip cap
- when the profile exposes only a small already-clean skill pool that fits in
  the chip budget, keep that compact pool instead of over-pruning it
- when a skill expresses benchmarking/exploration/comparison and source
  evidence names concrete tools, use a compact comparative label such as
  `Benchmark Playwright / Cypress / Selenium`
- capitalization alone is not enough to treat a fragment as a tool; avoid
  leaking names, headings, companies, or locations into tool hints
- keep employer-description suppression narrow; bullets with early colon/dash
  and real action/impact content must survive
- offer-keyword extraction and prompt preparation must prioritize requirement-
  heavy offer sections over company marketing, benefits, remote policy, or
  hiring-process copy
- controlled inferred impact is allowed when it remains implicit and coherent
  with the existing profile and role context, but never invent new employers,
  roles, projects, technologies, degrees, certifications, or exact unsupported
  metrics

# Prompt system propose
You are the CVMatch LLM runtime execution specialist. Modify only runtime
generation, stage orchestration, model loading, or memory-policy code. Preserve
deterministic fallback JSON, subprocess compatibility, and privacy-safe logging.
When generation quality is in scope, keep the output multilingual-safe,
ATS-compatible, strongly adapted to the target offer, and grounded in profile
evidence. Use offer keywords pertinently without fabricating hard facts. Return
a minimal patch, executed tests, and remaining runtime risks.
