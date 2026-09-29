"""Configuração em duas camadas: padrão global → família de projeto.

A família só guarda o que DIFERE do padrão (campo ausente = herda). Tudo que
entra aqui vem do gerente pela API e é validado por `GlobalConfig`/`FamilyRule`
(`extra="forbid"`), nunca aceito cru."""
from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

DEFAULT_NUMBER_PATTERN = r"^SE\.\d{2}\.\d{3}$"

DEFAULTS: dict = {
    "enabled": True,
    # "projeto" = um relatório pro projeto inteiro (padrão, decisão do
    # usuário em 2026-09-28); "pacote" = um por pacote de trabalho
    "mode": "projeto",
    "signer1_name": "",
    "signer1_company": "Schwaben Engineering",
    "signer2_name": "",
    "signer2_company": "Mercedes-Benz do Brasil",
    "include_performance": False,
    "formats": ["xlsx"],
    # revisor que o rascunho já recebe ao nascer ("" = o do mês anterior, se houver)
    "reviewer_login": "",
    "reviewer_name": "",
    # só no padrão global
    "location": "Santo André",
    "number_pattern": DEFAULT_NUMBER_PATTERN,
    # agendador da rodada mensal (`scheduler.py`): gera os rascunhos do mês que
    # fechou no dia e na hora (America/Sao_Paulo). Decisão do usuário,
    # 2026-09-29: ligado, dia 1, 06:00. Só no padrão global (não é por família).
    "schedule_enabled": True,
    "schedule_day": 1,
    "schedule_time": "06:00",
}

_Text = Field(default=None, max_length=200)

# modelo do número na tela: `#` = um dígito, o resto é literal ("SE.##.###")


def model_to_pattern(model: str) -> str:
    r""""SE.##.###" → `^SE\.\d{2}\.\d{3}$` (o formato que o backend confere)."""
    out, i = [], 0
    while i < len(model):
        if model[i] == "#":
            j = i
            while j < len(model) and model[j] == "#":
                j += 1
            out.append(r"\d" if j - i == 1 else rf"\d{{{j - i}}}")
            i = j
        else:
            out.append(re.escape(model[i]))
            i += 1
    return "^" + "".join(out) + "$"


def pattern_to_model(pattern: str) -> str | None:
    """O caminho inverso — `None` quando a regra não é de modelo (foi
    escrita à mão como expressão regular)."""
    match = re.fullmatch(r"\^(.*)\$", pattern or "")
    if not match:
        return None
    body, model, i = match.group(1), [], 0
    while i < len(body):
        digits = re.match(r"\\d(?:\{(\d+)\})?", body[i:])
        if digits:
            model.append("#" * int(digits.group(1) or 1))
            i += digits.end()
        elif body[i] == "\\" and i + 1 < len(body) and not body[i + 1].isalnum():
            model.append(body[i + 1])
            i += 2
        elif body[i] not in ".^$*+?{}[]\\|()":
            model.append(body[i])
            i += 1
        else:
            return None
    return "".join(model)


class FamilyRule(BaseModel):
    """O que uma família sobrescreve do padrão (tudo opcional)."""
    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = None
    mode: Literal["pacote", "projeto"] | None = None
    signer1_name: str | None = _Text
    signer1_company: str | None = _Text
    signer2_name: str | None = _Text
    signer2_company: str | None = _Text
    include_performance: bool | None = None
    formats: list[Literal["xlsx", "pdf"]] | None = Field(default=None, min_length=1, max_length=2)
    # o nome NUNCA vem do cliente: `service.set_family_rule` resolve o login na
    # lista do Projectile e grava o nome de lá
    reviewer_login: str | None = Field(default=None, max_length=100)
    reviewer_name: str | None = Field(default=None, max_length=255)


class GlobalConfig(FamilyRule):
    location: str | None = Field(default=None, max_length=100)
    number_pattern: str | None = Field(default=None, max_length=200)
    # o que a tela manda: "SE.##.###" (`#` = dígito) — vira `number_pattern`
    number_model: str | None = Field(default=None, min_length=1, max_length=60)
    schedule_enabled: bool | None = None
    # 1–28: existe em todo mês (o "mês que fechou" é sempre o anterior)
    schedule_day: int | None = Field(default=None, ge=1, le=28)
    schedule_time: str | None = Field(default=None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")

    @field_validator("number_pattern")
    @classmethod
    def _valid_regex(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                re.compile(value)
            except re.error as e:
                raise ValueError(f"expressão regular inválida: {e}") from e
        return value


def _set_fields(model: BaseModel) -> dict:
    return {k: v for k, v in model.model_dump().items() if v is not None}


def validate_global(raw: dict) -> dict:
    fields = _set_fields(GlobalConfig.model_validate(raw))
    model = fields.pop("number_model", None)
    if model is not None:
        if "#" not in model:
            raise ValueError("o modelo do número precisa de pelo menos um # (dígito)")
        fields["number_pattern"] = model_to_pattern(model.strip())
    return fields


def validate_rule(raw: dict) -> dict:
    return _set_fields(FamilyRule.model_validate(raw))


def effective(global_config: dict | None, family_rule: dict | None) -> dict:
    """Configuração que vale pra uma família. Dado salvo antes de uma mudança
    de campo é revalidado aqui — um valor que não passa mais cai no padrão."""
    result = dict(DEFAULTS)
    for layer, validate in ((global_config, validate_global), (family_rule, validate_rule)):
        if layer:
            try:
                result.update(validate(layer))
            except ValueError:
                continue
    # o modelo legível ("SE.##.###") pra tela; None = regra escrita à mão
    result["number_model"] = pattern_to_model(result.get("number_pattern") or DEFAULT_NUMBER_PATTERN)
    return result
