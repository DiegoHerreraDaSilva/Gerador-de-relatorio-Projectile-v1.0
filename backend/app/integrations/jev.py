"""Cliente do Jev (TypeSafe AI) — decisões estruturadas com probabilidade,
não texto. `POST https://api.typesafe.ai/v1/systemone` (API oficial da
TypeSafe, `Authorization: Bearer <TYPESAFE_API_KEY>`) com
`{state, model, questions}`; cada pergunta é `choice` (até 255 opções, descritas em
`criteria`), `score` ou `noul` (sim/não). Resposta:
`answers.<nome>.{type, choice|noul, confidence, probabilities}`.
O Jev só ESCOLHE entre opções — não extrai datas, nomes nem números
livres, não calcula e não gera texto.

Nunca recebe credencial nem acesso a banco: só o texto da pergunta e as
listas de opções montadas pelo backend. Os endereços são fixos aqui, não
configuráveis: a pergunta e as listas de clientes/colaboradores só podem ir
pra esse endereço. Sem chave, fica desligado e o Claude classifica."""

from __future__ import annotations

from dataclasses import dataclass

import requests

from ..core.config import get_settings

TYPESAFE_URL = "https://api.typesafe.ai/v1/systemone"
MAX_CHOICE_OPTIONS = 255


class ClassifierUnavailableError(RuntimeError):
    """Sem chave, timeout, erro HTTP ou resposta fora do formato — quem
    chama cai no Claude pra interpretar a pergunta."""


@dataclass(frozen=True)
class Answer:
    choice: str
    confidence: float
    probabilities: dict[str, float]


def _endpoint(settings) -> tuple[str, str] | None:
    """(url, chave) da API oficial da TypeSafe; `None` sem chave."""
    if settings.typesafe_api_key:
        return TYPESAFE_URL, settings.typesafe_api_key
    return None


def is_enabled() -> bool:
    return _endpoint(get_settings()) is not None


def choice(instructions: str, criteria: dict[str, str]) -> dict:
    if not 2 <= len(criteria) <= MAX_CHOICE_OPTIONS:
        raise ValueError(f"Pergunta de escolha precisa de 2 a {MAX_CHOICE_OPTIONS} opções (veio {len(criteria)}).")
    return {"type": "choice", "instructions": instructions, "criteria": criteria}


def noul(instructions: str) -> dict:
    return {"type": "noul", "instructions": instructions}


def ask(state: str, questions: dict[str, dict]) -> dict[str, Answer]:
    """Uma chamada, todas as perguntas juntas. `noul` vira escolha entre
    "yes"/"no", com confiança = distância do meio-termo (0,5), dobrada."""
    settings = get_settings()
    endpoint = _endpoint(settings)
    if endpoint is None:
        raise ClassifierUnavailableError("TYPESAFE_API_KEY não configurada.")
    url, key = endpoint
    headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    try:
        response = requests.post(
            url, headers=headers, json={"state": state, "model": settings.jev_model, "questions": questions}, timeout=settings.jev_timeout_seconds
        )
        response.raise_for_status()
        answers = response.json()["answers"]
    except (requests.RequestException, ValueError, KeyError, TypeError) as e:
        raise ClassifierUnavailableError(f"Falha ao consultar o Jev: {e}") from e

    parsed: dict[str, Answer] = {}
    for name, answer in answers.items():
        if name not in questions or not isinstance(answer, dict):
            continue
        if answer.get("type") == "noul":
            value = float(answer.get("noul") or 0.0)
            parsed[name] = Answer(choice="yes" if value >= 0.5 else "no", confidence=abs(value - 0.5) * 2, probabilities={"yes": value, "no": 1 - value})
        elif answer.get("type") == "choice" and isinstance(answer.get("choice"), str):
            parsed[name] = Answer(
                choice=answer["choice"],
                confidence=float(answer.get("confidence") or 0.0),
                probabilities={str(k): float(v) for k, v in (answer.get("probabilities") or {}).items()},
            )
    return parsed
