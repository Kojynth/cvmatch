from __future__ import annotations

import importlib.util


def test_new_domain_and_infra_modules_have_specs() -> None:
    required_modules = (
        "app.domain.profile.service",
        "app.domain.generation.orchestrator",
        "app.domain.generation.postprocessing",
        "app.domain.mass_apply.contracts",
        "app.infra.persistence.database",
        "app.infra.model_runtime.qwen_manager",
        "app.infra.security.secret_store",
        "app.integrations.linkedin",
        "app.integrations.job_sources",
    )

    for module_name in required_modules:
        assert importlib.util.find_spec(module_name) is not None, module_name
