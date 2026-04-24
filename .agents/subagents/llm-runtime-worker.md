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
- preserve deterministic minimum-schema fallback
- do not change DB or UI contracts unless explicitly coordinated
- do not expose a new model without registry/runtime/test coherence
- when CV generation or adaptation quality is in scope, enforce ATS-first
  structure, one-language output, reverse chronology, consistent dates,
  explicit durations when reliable, 2-4 concise bullets per role when the
  profile supports bullets, and grounded keyword usage rather than lexical
  stuffing
- when runtime changes can affect final CV rendering, preserve the one-page
  **fit-to-page** contract end to end: prioritized content allocation,
  measured rendered height, controlled compression tiers, then PDF export
  (never rely on CSS clipping or crop-to-page)
- preserve the header render contract for generated CVs: actionable contact
  methods render as explicit links (`mailto:`, `tel:`, LinkedIn, GitHub,
  portfolio URL), placeholder labels like `Lien 1` / `Link 1` are forbidden,
  and the target subtitle must read as a candidature target
  (`Poste vise` / `Target role`) rather than an employer label
- preserve one-page section allocation: summary (max 3 short lines), up to 10
  compact credible skill/tool chips when layout allows, a natural grounded positioning sentence appended
  to the summary when available, 2-3 concrete impacts per role chosen from
  the strongest action-led evidence, one featured project when present,
  compact certifications, and no fallback to a vague `additional relevant
  details` blob when structured data exists
- when summary assembly is in scope, build the final rendered summary after
  retained experience/project/certification blocks are selected, avoid
  repeating the same signals already visible in rendered experience bullets,
  and keep the natural company-targeting sentence present
- when experience rendering is in scope, preserve asymmetric detail budgets:
  protect the most aligned anchor role first, then compress lower-priority
  roles
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
- if profile or offer evidence includes concrete named tools/software/
  platforms/systems, prefer naming them explicitly over vague tooling wording
- generic tool categories are fallback only; if named products are present in
  source evidence, surface the named products instead
- featured skill chips must come from the profile `skills` pool first;
  experience/project evidence may reprioritize or compactly rewrite those
  labels, but must not create extra chips from narrative bullets alone
- do not backfill weak/noisy skill chips purely to hit the visible chip cap
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
