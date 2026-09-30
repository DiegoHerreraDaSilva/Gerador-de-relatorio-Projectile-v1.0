"""Política de falha de cada store — DECLARADA, não convenção implícita.

O projeto tem duas posturas deliberadas e opostas:

- `FAIL_OPEN`: infraestrutura secundária nunca bloqueia o fluxo principal —
  `/generate` e `/send-report` seguem gerando o arquivo mesmo com o
  `reports_db` fora (histórico/auditoria são acompanhamento, não o produto);
- `FAIL_CLOSED`: dado primário (correções manuais de gerência, rascunhos da
  geração automática) não pode divergir em silêncio — banco fora do ar vira
  502 com mensagem genérica.

Cada módulo de store declara `FAILURE_POLICY`; `test_failure_policies.py`
falha se um store novo esquecer de declarar ou se a política for trocada sem
decisão explícita (a lista esperada de lá é o registro da decisão). Para
adicionar um store: declare aqui/nele, mude a lista do teste e explique o
porquê no docstring do módulo — como os stores atuais já fazem.
"""

from __future__ import annotations

from enum import StrEnum


class FailurePolicy(StrEnum):
    FAIL_OPEN = "fail_open"
    FAIL_CLOSED = "fail_closed"
