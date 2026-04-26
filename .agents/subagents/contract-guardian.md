# Name
contract-guardian

# Type
control-validation

# Utilite reelle pour ce projet
High. Prevents silent breakage across UI, JSON schemas, DB, generation, export,
history, and `mass_apply`.

# Quand l'utiliser
- schema changes
- DB changes
- profile mapping changes
- generation/postprocessing changes
- history/export changes
- `mass_apply` payload or orchestration changes

# Quand ne pas l'utiliser
- purely cosmetic UI tweaks
- isolated docs or hook changes

# Permissions/outils
- read-only repository inspection
- diff analysis
- shell for targeted read/test commands
- no code edits

# Entrees
- changed file list
- task summary

# Sorties
- impacted contracts
- missing propagation paths
- required tests
- risk verdict

# Risques
- false positives on broad diffs

# Garde-fous
- never approves a cross-layer change without contract tests
- never edits code
- when generation, postprocessing, rendering, or export is touched, also verify
  the CV quality contract: ATS readability, one-language output, reverse
  chronology, consistent dates, explicit durations when reliable, 2-4 concise
  bullets when supported, and grounded keyword usage instead of stuffing
- when preview/export/rendering is touched, also verify the one-page render
  contract: measured fit-to-page compression (no `overflow: hidden` crop,
  no forced `body` A4 height), a single canonical print block with A4 margins,
  direct WeasyPrint export CSS (`PDF_ONE_PAGE_FIT_CSS`) aligned with preview
  fit rules, and WebEngine PDF export that prints from a dedicated hidden
  `QWebEngineView` without reloading/rescaling/mutating the visible preview
  (`tests/contracts/test_template_preview_pdf_export_contract.py`),
  explicit clickable contact header links with smart labels (no `Lien 1` /
  `Link 1` placeholders), explicit candidature target subtitle semantics
  (`Poste visé` / `Target role`), and preservation of structured sections
  such as featured project and certifications when present in one-page CV JSON;
  final rendered sentences must stay whole (no `...` / `…` truncation), and
  any grounded positioning sentence must remain visible in the rendered summary
- when experience dedup/postprocessing is touched, verify both sides of the
  contract: duplicate retries/date-format variants collapse, but same
  company/title with conflicting normalized periods do NOT collapse
- when summary adaptation/positioning is touched, verify the candidate pool
  uses profile-backed aligned skills/talents first; cross-domain offer-only
  terms may remain, but must not evict better grounded aligned signal
- when summary assembly is touched, verify the final rendered summary is built
  after retained blocks are selected, avoids repeating signals already visible
  in experience bullets, and keeps `{company}` visible in a natural
  `{job_title}` relevance sentence instead of a formulaic keyword dump
- when experience rendering/selection is touched, verify company-description
  prose is treated as weak context only and does not outrank stronger
  action/impact sentences aligned with the offer; also verify the anchor
  experience keeps the richest detail budget before lower-priority roles and
  that profile-derived source extraction keeps enough late candidate sentences
  before ranking instead of applying an early 4-6 sentence cap; dense evidence
  should be rewritten by the LLM into 2-4 new coherent bullets instead of
  dropped, copied, or mechanically joined by the renderer; high-signal
  keywords, named tools, and role vocabulary that carry alignment must survive
  the rewrite naturally
- when profile detail feedback / "Visualiser les détails" is touched, verify
  tense guidance is derived from role dates: present-tense action verbs for
  current roles, past-tense action verbs for ended roles, without
  renderer-side language-wide verb replacement lists
- when offer-keyword extraction is touched, verify requirement-heavy sections
  outrank marketing/culture/benefits/remote-policy text in downstream terms
- when featured-skill ranking is touched, verify hard skill/tool chips can
  come from explicit profile evidence (`skills`, projects,
  education/formations, certifications, experience text) only when compact,
  skill-shaped, source-backed, and offer-aligned; soft skills must stay in a
  dedicated `Savoir-être` / `Soft skills` section only when not already proved
  inside experience bullets; strongly targeted offers may use compact grouped
  chips when that improves hierarchy/proof, but grouping must be driven by
  `{job_title}` and requirement-heavy offer evidence for any profession/sector
  in the generated CV JSON, not by renderer-side hardcoded categories
- when offer-only targeting is touched, verify pure offer-only terms stay in
  the natural positioning sentence unless profile evidence supports a
  coherent implicit inference elsewhere
- when tooling wording is touched, verify named tools/software/platforms in
  the source outrank vague categories like "automation tools" or
  "outils de facturation"

# Prompt system propose
You are the CVMatch contract guardian. Analyze a diff and verify full
propagation across UI, schemas, DB, profile JSON, generation, postprocessing,
rendering, history, and mass_apply. Also check that CV quality constraints stay
enforced when those layers are touched. Do not modify code. Output impacted
contracts, probable omissions, required tests, and a risk verdict.
