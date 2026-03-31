# Repository Rules

## Stage Memory Override Rule (Mandatory)
When adding stage-specific subprocess memory tuning (especially for `cover_letter` and other writer stages), do not blindly preserve inherited environment values and do not blindly overwrite them either. Distinguish generic launcher defaults from explicit host-specific overrides, and normalize numeric env values before comparison so equivalent values like `6.5` and `6.50` are treated identically. If a stage-specific memory profile is introduced, add targeted regression checks covering: generic parent defaults overridden as intended, explicit parent overrides preserved, and numeric-format variants of generic defaults.

## Post-Edit Code Review Rule (Mandatory)
After every code change, perform an explicit code review on the written diff before concluding the task. The review must focus on bugs, regressions, bad assumptions, and missing validation or tests in the modified paths. Report findings first when any exist; if none are found, state that explicitly.

## Post-Edit Security Review Rule (Mandatory)
After every code change, perform an explicit security review on the written diff before concluding the task. Check at minimum for unsafe subprocess or environment handling, path or file-write risks, unsafe deserialization, prompt or data leakage, PII or secret exposure in logs, and any new trust boundary violations. Report concrete findings when present; otherwise state explicitly that no security issues were found in the modified scope.
