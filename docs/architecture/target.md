# Target Architecture

- `app/domain`: profile, generation, offers, history, `mass_apply`
- `app/infra`: persistence, model runtime, secrets, diagnostics
- `app/integrations`: LinkedIn and job sources
- `cvextractor.pipeline`: canonical extraction path
- `views/controllers/workers`: thin orchestration layers only

Migration is additive. Wrappers and re-exports are preferred over disruptive
moves.
