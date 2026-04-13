# Repository Rules

## Stage Memory Override Rule (Mandatory)
When adding stage-specific subprocess memory tuning (especially for `cover_letter` and other writer stages), do not blindly preserve inherited environment values and do not blindly overwrite them either. Distinguish generic launcher defaults from explicit host-specific overrides, and normalize numeric env values before comparison so equivalent values like `6.5` and `6.50` are treated identically. If a stage-specific memory profile is introduced, add targeted regression checks covering: generic parent defaults overridden as intended, explicit parent overrides preserved, and numeric-format variants of generic defaults.

## Post-Edit Code Review Rule (Mandatory)
After every code change, perform an explicit code review on the written diff before concluding the task. The review must focus on bugs, regressions, bad assumptions, and missing validation or tests in the modified paths. Report findings first when any exist; if none are found, state that explicitly.

## Post-Edit Security Review Rule (Mandatory)
After every code change, perform an explicit security review on the written diff before concluding the task. Check at minimum for unsafe subprocess or environment handling, path or file-write risks, unsafe deserialization, prompt or data leakage, PII or secret exposure in logs, and any new trust boundary violations. Report concrete findings when present; otherwise state explicitly that no security issues were found in the modified scope.

## CV Writing Quality Rule (Mandatory)
When generating, adapting, reviewing, or postprocessing CV content, enforce these output-quality constraints by default unless the user explicitly requests otherwise: keep experiences and projects in reverse chronological order; include an explicit duration for each role or project when reliable dates allow it (for example `2 ans` or `6 mois`); keep the CV to one page; keep core sections present with at least `Coordonnees`, `Experience` and/or `Projets`, `Formation`, and `Hobbies` when the source profile supports them; preserve ATS-compatible formatting with simple, parseable structure; use one consistent date format across the whole CV; and keep each role to 2-4 concise bullet points.

## CV Language And Impact Rule (Mandatory)
For CV wording quality, require correct grammar and spelling, use present tense for the current role and past tense for former roles, avoid first-person pronouns (`je`, `moi`, `mon`), remove cliche terms and filler intensifiers, keep punctuation style consistent, start bullets with strong action verbs, vary verbs so the same one is not repeated more than twice when avoidable, and favor direct, concrete phrasing. When facts support it, structure bullets as `verbe d'action + ce qui a ete fait + resultat/impact`, include quantitative evidence (team size, percentages, volumes, users, revenue, time saved, and similar metrics), and mention the target company name to reinforce personalization without inventing facts.
