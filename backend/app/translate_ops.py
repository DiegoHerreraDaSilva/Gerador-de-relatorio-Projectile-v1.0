"""Prompt e schema do botão "EN" do preview — traduz nomes de grupo e
descrições de atividade do relatório para inglês.

Separado de chat_ops.py de propósito: aqui a tarefa é sempre a mesma (traduzir
uma lista de textos), nunca uma "operação" aberta escolhida pela IA — então o
schema fica mais simples, e o casamento de cada item é por `id` (estável,
nunca ambíguo), em vez do casamento por nome/descrição ATUAL que chat_ops.py
precisa fazer pra localizar o alvo de operações abertas. Casar por texto aqui
seria frágil justamente porque é o texto que está mudando.

O campo `id` de cada item pode ser tanto o id de um GRUPO quanto de uma
ATIVIDADE (mesmo gerador de id em ambos, `genId()` no frontend, espaços de
uso disjuntos — nunca colidem) — a IA não precisa saber a diferença, só
traduzir o texto de cada item e devolver com o mesmo id.
"""
from __future__ import annotations

TRANSLATE_TOOL_NAME = "translate_report_texts"

TRANSLATE_SYSTEM_PROMPT = """Você traduz textos de um relatório de horas de engenharia, \
do português para o inglês técnico — tanto NOMES DE GRUPO (categorias de trabalho, ex: \
"Geral", "Encapsulamento Estrutural") quanto DESCRIÇÕES DE ATIVIDADE.

Você recebe uma lista de itens `{id, text}`. Devolva a tradução de CADA texto \
para inglês, mantendo o `id` original de cada item — a lista de saída precisa \
ter exatamente um item para cada id recebido.

Regras:
1. Traduza só o texto que está lá — não resuma, não invente informação nova,
   não explique a atividade.
2. Preserve exatamente como estão: siglas/códigos técnicos (ex: "CAD", "ENG",
   "QA" — inclusive quando a sigla É o próprio nome do grupo, não só dentro
   de uma descrição), números, nomes próprios de projeto/cliente/pessoa.
3. Se o texto já estiver em inglês, ou vier vazio, devolva sem mudar.
4. Nunca pule um id da lista recebida.
"""

TRANSLATE_TOOL_SCHEMA = {
    "name": TRANSLATE_TOOL_NAME,
    "description": "Devolve a tradução para inglês de cada texto (nome de grupo ou descrição de atividade) recebido.",
    "input_schema": {
        "type": "object",
        "properties": {
            "translations": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "string", "description": "Mesmo id recebido na entrada, sem alterar."},
                        "text": {"type": "string", "description": "Tradução do texto para inglês."},
                    },
                    "required": ["id", "text"],
                },
            },
        },
        "required": ["translations"],
    },
}
