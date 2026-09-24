"""Rotas de importação de horas (`/parse`, `/parse-db`, `/parse-db-client`)
— extraído de `main.py` na Fase 5."""
from __future__ import annotations

import os
import tempfile
import zipfile
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from ...parser import parse_projectile_export
from ...projectile_db import ProjectileDbError, fetch_employee_hours, fetch_project_details, fetch_project_hours
from ...projectile_db import group_hours, group_hours_by_project
from ..dependencies import require_manager_or_coordinator, require_session
from ..errors import log_and_generic_error
from ..shared import build_parse_response, resolve_month_range

router = APIRouter()

_MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB
_MAX_UNCOMPRESSED_XLSX_BYTES = 200 * 1024 * 1024  # 200 MB
_UPLOAD_CHUNK_BYTES = 1024 * 1024  # 1 MB


async def _stream_upload_to_tempfile(file: UploadFile, max_bytes: int) -> str:
    """Grava o upload em disco em chunks de 1 MB, abortando assim que o
    total ultrapassa `max_bytes` — nunca materializa o arquivo inteiro em
    memória só pra descobrir depois que ele era grande demais (guia
    GUIA_EVOLUCAO_GERADOR_PROJECTILE.md, seção 12). Quem chama é responsável
    por apagar o arquivo temporário devolvido."""
    suffix = os.path.splitext(file.filename or "")[1] or ".xlsx"
    total = 0
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    try:
        while True:
            chunk = await file.read(_UPLOAD_CHUNK_BYTES)
            if not chunk:
                break
            total += len(chunk)
            if total > max_bytes:
                raise HTTPException(413, "Arquivo muito grande. O limite é 25 MB.")
            tmp.write(chunk)
    except Exception:
        tmp.close()
        os.remove(tmp.name)
        raise
    tmp.close()
    return tmp.name


def _is_oversized_uncompressed(total_uncompressed_bytes: int) -> bool:
    """Função pura (testável sem precisar gerar 200 MB de zip de verdade) —
    ver `_reject_if_oversized_uncompressed`."""
    return total_uncompressed_bytes > _MAX_UNCOMPRESSED_XLSX_BYTES


def _reject_if_oversized_uncompressed(tmp_path: str) -> None:
    """Tamanho DESCOMPRIMIDO do conteúdo do zip (.xlsx é um ZIP) — um "zip
    bomb" pode pesar poucos KB no disco e ainda assim descomprimir pra
    gigabytes, derrubando o servidor quando openpyxl carrega o workbook. Lê
    só o diretório central do ZIP (`infolist()`), nunca descompacta nada —
    barato mesmo pra um arquivo grande. Zip inválido não é rejeitado aqui:
    deixa o erro de "arquivo inválido" existente de parse_projectile_export
    tratar. Duplicado de propósito em email_ingest.py pro anexo de e-mail
    (ponto de entrada diferente, bytes já vêm decodificados de base64 lá,
    sem como evitar materializar em memória) — ver CLAUDE.md."""
    try:
        with zipfile.ZipFile(tmp_path) as zf:
            total_uncompressed = sum(info.file_size for info in zf.infolist())
    except zipfile.BadZipFile:
        return

    if _is_oversized_uncompressed(total_uncompressed):
        raise HTTPException(413, "Arquivo .xlsx com conteúdo descomprimido excessivo — recusado por segurança.")


@router.post("/parse")
async def parse_endpoint(
    file: UploadFile = File(...),
    mode: Literal["single", "multi"] = Form("single"),
    _user: dict = Depends(require_session),
):
    tmp_path = await _stream_upload_to_tempfile(file, _MAX_UPLOAD_BYTES)
    try:
        _reject_if_oversized_uncompressed(tmp_path)
        packages, issues = parse_projectile_export(tmp_path, split_by_package=(mode == "multi"))
    except zipfile.BadZipFile:
        raise HTTPException(400, "O arquivo enviado não é um .xlsx válido.")
    except ValueError as e:
        raise HTTPException(400, str(e))
    except KeyError as e:
        raise HTTPException(400, f"Planilha inválida: não encontrei a coluna {e}.")
    finally:
        os.remove(tmp_path)

    return build_parse_response(packages, issues)


class ParseDbRequest(BaseModel):
    month_label: str
    mode: Literal["single", "multi"] = "single"


@router.post("/parse-db")
async def parse_db_endpoint(payload: ParseDbRequest, _user: dict = Depends(require_session)):
    # busca sempre as horas do PRÓPRIO usuário logado — nunca confia em nome de
    # funcionário vindo do cliente, senão qualquer um logado poderia forjar o
    # request e puxar as horas de outra pessoa.
    employee_name = _user["name"]

    start_date, end_date = resolve_month_range(payload.month_label)

    try:
        rows = fetch_employee_hours(
            start_date, end_date, employee_id=_user.get("employee_id"), employee_name=employee_name
        )
    except ProjectileDbError as e:
        raise log_and_generic_error(e)

    if not rows:
        raise HTTPException(
            404,
            f'Nenhum lançamento encontrado pro nome "{employee_name}" em {payload.month_label}. '
            "Confira o nome (a busca é parcial) e o mês.",
        )

    packages, issues = group_hours(rows, split_by_package=(payload.mode == "multi"))
    return build_parse_response(packages, issues)


class ParseDbClientRequest(BaseModel):
    project_ids: list[str] = Field(min_length=1)
    month_label: str
    mode: Literal["pacote", "projeto"] = "pacote"


@router.post("/parse-db-client")
async def parse_db_client_endpoint(payload: ParseDbClientRequest, _user: dict = Depends(require_manager_or_coordinator)):
    start_date, end_date = resolve_month_range(payload.month_label)

    try:
        rows = fetch_project_hours(payload.project_ids, start_date, end_date)
    except ProjectileDbError as e:
        raise log_and_generic_error(e)

    if not rows:
        raise HTTPException(404, f"Nenhum lançamento encontrado pros projetos escolhidos em {payload.month_label}.")

    if payload.mode == "projeto":
        try:
            details = fetch_project_details(payload.project_ids)
        except ProjectileDbError as e:
            raise log_and_generic_error(e)
        project_names = {pid: info["name"] for pid, info in details.items()}
        packages, issues = group_hours_by_project(rows, project_names)
    else:
        packages, issues = group_hours(rows, split_by_package=True)
    return build_parse_response(packages, issues)
