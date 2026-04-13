# Incremental Migration Plan

1. Public-repo hygiene and validation baselines
2. `domain/infra/integrations` package skeletons with safe shims
3. Persistence and secret-store hardening
4. Extraction unification on `cvextractor.pipeline`
5. Generation runtime decomposition
6. `mass_apply` source recovery and bounded-context migration

Never remove legacy behaviour before the replacement is versioned and tested.
