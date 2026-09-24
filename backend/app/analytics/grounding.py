"""Trava contra número inventado: todo número num texto do Claude precisa
ter vindo do resultado que o backend mandou pra ele. Senão o texto é
descartado e vale o do formatter determinístico. É o que garante "Claude
explica, não calcula" (o planner e o finalizer não recebem banco nenhum,
mas poderiam errar uma conta de cabeça)."""
from __future__ import annotations

import re

# 1.234,5 (milhar com ponto) | 12,5 | 12.5 | 12
_NUMBER_RE = re.compile(r"\d{1,3}(?:\.\d{3})+(?:,\d+)?|\d+,\d+|\d+(?:\.\d+)?")
# inteiros pequenos (dia, "top 3", "2 clientes") nunca são o problema
_ALWAYS_ALLOWED_MAX = 31


def _parse(token: str) -> float:
    if "," in token:
        return float(token.replace(".", "").replace(",", "."))
    if re.fullmatch(r"\d{1,3}(?:\.\d{3})+", token):
        return float(token.replace(".", ""))
    return float(token)


def numbers_in(text: str) -> list[float]:
    return [_parse(token) for token in _NUMBER_RE.findall(text)]


def allowed_numbers(*payloads) -> set[float]:
    found: set[float] = set()

    def walk(value):
        if isinstance(value, bool):
            return
        if isinstance(value, (int, float)):
            number = float(value)
            found.update({number, round(number), round(number, 1), round(number, 2), abs(number)})
        elif isinstance(value, str):
            found.update(numbers_in(value))
        elif isinstance(value, dict):
            for item in value.values():
                walk(item)
        elif isinstance(value, (list, tuple)):
            for item in value:
                walk(item)

    for payload in payloads:
        walk(payload)
    return found


def is_grounded(text: str, allowed: set[float]) -> bool:
    for number in numbers_in(text):
        if number.is_integer() and 0 <= number <= _ALWAYS_ALLOWED_MAX:
            continue
        if not any(abs(number - a) <= max(0.051, abs(a) * 0.001) for a in allowed):
            return False
    return True
