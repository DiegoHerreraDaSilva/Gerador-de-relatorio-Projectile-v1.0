"""Prompt e schema do botão "EN" do preview — traduz descrições de atividade
do relatório para inglês.

Separado de chat_ops.py de propósito: aqui a tarefa é sempre a mesma (traduzir
uma lista de textos), nunca uma "operação" aberta escolhida pela IA — então o
schema fica mais simples, e o casamento de cada item é por `id` (estável,
nunca ambíguo), em vez do casamento por nome/descrição ATUAL que chat_ops.py
precisa fazer pra localizar o alvo de operações abertas. Casar por descrição
aqui seria frágil justamente porque é a descrição que está mudando.
"""
from __future__ import annotations

TRANSLATE_TOOL_NAME = "translate_activity_descriptions"

TRANSLATE_SYSTEM_PROMPT = """Você traduz descrições de atividades de um relatório de horas de \
engenharia, do português para o inglês técnico.

Você recebe uma lista de itens `{id, description}`. Devolva a tradução de CADA \
descrição para inglês, mantendo o `id` original de cada item — a lista de saída \
precisa ter exatamente um item para cada id recebido.

Regras:
1. Traduza só o texto que está lá — não resuma, não invente informação nova,
   não explique a atividade.
2. Preserve exatamente como estão: siglas/códigos técnicos (ex: "CAD", "ENG",
   "QA"), números, nomes próprios de projeto/cliente/pessoa.
3. Se a descrição já estiver em inglês, ou vier vazia, devolva sem mudar.
4. Nunca pule um id da lista recebida.
"""

TRANSLATE_TOOL_SCHEMA = {
    "name": TRANSLATE_TOOL_NAME,
    "description": "Devolve a tradução para inglês de cada descrição de atividade recebida.",
    "input_schema": {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Mesmo id recebido na entrada, sem alterar."},
                        "description": {"type": "string", "description": "Tradução da descrição para inglês."},
                    },
                    "required": ["id", "description"],
                },
            },
        },
        "required": ["translations"],
    },
}
