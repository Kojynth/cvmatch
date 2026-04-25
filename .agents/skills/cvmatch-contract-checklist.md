# Skill: cvmatch-contract-checklist

Use when a change touches schemas, DB models, profile mapping, generation,
history, export, or `mass_apply` payloads.

Checklist:
1. Identify all affected contracts.
2. Verify propagation across UI, JSON, DB, generation, export, history.
3. If render/export is touched, verify the one-page print contract:
   measured fit-to-page compression, a single canonical print block,
   no `overflow: hidden` crop, no forced `body` A4 height, and
   `break-inside: avoid` on structured blocks; also verify no renderer-side
   ellipsis/clamp truncation is used as a fit-to-page shortcut. For direct
   PDF export, verify WeasyPrint applies `PDF_ONE_PAGE_FIT_CSS` as well as
   template CSS; preview-only CSS is not sufficient.
4. If header rendering is touched, verify clickable contacts with explicit
   labels, no `Lien 1` / `Link 1`, and candidature-style target subtitle
   semantics (`Poste vise` / `Target role`).
5. If one-page allocation is touched, verify preservation of structured
   sections (summary, skills, experience, featured project, certifications)
   instead of flattening to an `additional relevant details` blob, and verify
   the summary may keep one short natural positioning sentence while
   experience blocks prefer action/impact sentences over company-description
   text, and compact skill chips may stay visible up to roughly 10 items when
   the row-wrap remains clean.
6. If summary assembly is touched, verify the final rendered summary is built
   after retained blocks are selected, avoids repeating signals already
   visible in rendered experience bullets, and keeps the company-targeting
   sentence present.
7. If experience rendering/selection is touched, verify the anchor experience
   keeps the richest detail budget before lower-priority roles compress, while
   visible role order itself stays reverse-chronological. Also verify source
   extraction keeps a rich candidate pool before scoring instead of dropping
   late profile evidence with an early 4-6 sentence cap, and that dense source
   evidence is fused into 2-4 coherent bullets rather than expanded into too
   many bullets.
8. If featured-skill ranking is touched, verify hard skill/tool chips may come
   from explicit profile evidence (`skills`, projects, education/formations,
   certifications, experience text) only when the extracted label is compact,
   skill-shaped, source-backed, and offer-aligned. Keep soft skills in a
   dedicated `Savoir-être` / `Soft skills` section only when those behaviours
   are not already proved inside experience bullets.
   Vague comparative skills can become labels such as
   `Benchmark Playwright / Cypress / Selenium` when source evidence names the
   tools. Prefer compact grouped chips for strongly targeted offers when they
   clarify hierarchy/proof. Do not backfill weak/noisy chips just to reach the
   visible cap.
9. If experience dedup is touched, verify duplicate retries/date-format
   variants collapse while same company/title with conflicting periods stay
   distinct.
10. If summary adaptation/positioning is touched, verify the phrase surfaces
   profile-backed aligned skills/talents first, does not rely on
   `missing_summary_terms` alone, reads naturally in final render, uses
   sector/industry only as a very weak bonus rather than a gate, and does not
   blindly preserve a worse stored positioning sentence when the recomputed
   candidate is more aligned.
11. If offer-keyword extraction or prompt preparation is touched, verify
   requirement-heavy sections outrank marketing/culture/benefits/remote text,
   and verify pure offer-only vocabulary stays confined to the natural
   positioning sentence unless profile evidence supports a coherent implicit
   inference elsewhere.
12. If company-description suppression is touched, verify true employer-intro
   lines are filtered while action/impact bullets with early colon or dash
   remain eligible for rendering.
11. If tooling wording is touched, verify named products/platforms from the
   source outrank vague categories like `automation tools` or
   `outils de facturation`.
12. Run `tests/contracts` plus the smallest targeted rendering/export scope.
13. Record skipped scope explicitly.
