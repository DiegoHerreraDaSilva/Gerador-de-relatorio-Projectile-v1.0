"""Configuração da geração automática: padrão geral, regra por família de projeto e override explícito."""

from __future__ import annotations

import logging

from ...services import auto_generation_store as store
from .. import families, rules

# `_resolve_reviewer` é importado DENTRO do set_family_rule de propósito:
# reviews→drafts→custom_flow→views fecharia ciclo de import no topo.

logger = logging.getLogger(__name__)


def get_configuration() -> dict:
    config = store.get_config()
    rule_list = []
    labels = _family_labels()
    for family_key, cfg in sorted(store.get_rules().items()):
        rule_list.append({"family_key": family_key, "label": labels.get(family_key, family_key), "config": cfg})
    return {"defaults": rules.DEFAULTS, "config": config, "effective": rules.effective(config, None), "rules": rule_list}


def set_global_config(raw: dict, actor: dict) -> dict:
    config = rules.validate_global(raw)
    with store.write_session() as s:
        s.set_config(config)
    return config


def set_family_rule(family_key: str, raw: dict | None, actor: dict) -> dict:
    config = rules.validate_rule(raw or {})
    config.pop("reviewer_name", None)
    if config.get("reviewer_login", "").strip():
        from .reviews import _resolve_reviewer  # local: ver comentário no topo

        reviewer = _resolve_reviewer(config["reviewer_login"])
        config["reviewer_login"], config["reviewer_name"] = reviewer["login"], reviewer["name"]
    else:
        config.pop("reviewer_login", None)
    with store.write_session() as s:
        s.set_rule(family_key, config, actor.get("login", ""))
    return config


def set_family_override(project_id: str, family_key: str | None, actor: dict) -> None:
    with store.write_session() as s:
        s.set_family_override(project_id, family_key, actor.get("login", ""))


def _family_labels() -> dict[str, str]:
    labels: dict[str, str] = {}
    for run in store.list_runs():
        for item in store.list_reports(run["competence"]):
            labels.setdefault(item["family_key"], families.family_label(item["project_name"]))
    return labels


def _family_for(project: dict, overrides: dict[str, str]) -> str:
    return overrides.get(project["project_id"]) or families.family_key(project["client"], project["name"])
