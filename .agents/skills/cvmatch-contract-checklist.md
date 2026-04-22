# Skill: cvmatch-contract-checklist

Use when a change touches schemas, DB models, profile mapping, generation,
history, export, or `mass_apply` payloads.

Checklist:
1. Identify all affected contracts.
2. Verify propagation across UI, JSON, DB, generation, export, history.
3. If render/export is touched, verify the one-page print contract:
   measured fit-to-page compression, a single canonical print block,
   no `overflow: hidden` crop, no forced `body` A4 height, and
   `break-inside: avoid` on structured blocks.
4. If header rendering is touched, verify clickable contacts with explicit
   labels, no `Lien 1` / `Link 1`, and candidature-style target subtitle
   semantics (`Poste vise` / `Target role`).
5. If one-page allocation is touched, verify preservation of structured
   sections (summary, skills, experience, featured project, certifications)
   instead of flattening to an `additional relevant details` blob.
6. If experience dedup is touched, verify duplicate retries/date-format
   variants collapse while same company/title with conflicting periods stay
   distinct.
7. If summary adaptation/positioning is touched, verify the phrase surfaces
   profile-backed aligned skills/talents first and does not rely on
   `missing_summary_terms` alone.
8. Run `tests/contracts` plus the smallest targeted rendering/export scope.
9. Record skipped scope explicitly.
