"""Rotas de "Minhas revisões" (`/my-reviews/*`): qualquer usuário logado,
mas só enxerga os relatórios da geração automática atribuídos A ELE — de
outra pessoa é 404 (`service._load_assigned`), nunca 403, pra não revelar
que existe. O revisor edita o conteúdo e manda pra aprovação; número,
arquivos e aprovação continuam do gerente (`/auto-generation/*`)."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.concurrency import run_in_threadpool

from ...auto_generation import service
from ...auto_generation.schemas import CommentRequest, SaveDraftRequest
from .. import period_access
from ..dependencies import is_manager, require_session
from .auto_generation import _call

router = APIRouter()


def _from(user: dict) -> str | None:
    """1º mês da janela de quem não é gerente ("AAAA-MM"); None = sem corte."""
    limits = period_access.window_for(user)
    return limits[0].strftime("%Y-%m") if limits else None


@router.get("/my-reviews")
async def my_reviews_endpoint(_user: dict = Depends(require_session)):
    return await run_in_threadpool(_call, service.my_reviews, _user, _from(_user))


@router.get("/my-reviews/summary")
async def my_reviews_summary_endpoint(_user: dict = Depends(require_session)):
    """Contadores da sidebar (revisões pendentes; pro gerente, também o que
    aguarda a aprovação dele)."""
    return await run_in_threadpool(_call, service.review_summary, _user, is_manager(_user), _from(_user))


@router.get("/my-reviews/{report_id}")
async def my_review_endpoint(report_id: str, _user: dict = Depends(require_session)):
    return await run_in_threadpool(_call, service.review_detail, report_id, _user, _from(_user))


@router.put("/my-reviews/{report_id}/draft")
async def my_review_save_endpoint(report_id: str, body: SaveDraftRequest, _user: dict = Depends(require_session)):
    version = await run_in_threadpool(_call, service.review_save, report_id, body.draft, body.draft_version, _user, _from(_user))
    return {"draft_version": version}


@router.post("/my-reviews/{report_id}/submit")
async def my_review_submit_endpoint(report_id: str, body: CommentRequest, _user: dict = Depends(require_session)):
    """Revisão concluída: vai pro gerente aprovar."""
    status = await run_in_threadpool(_call, service.submit_review, report_id, _user, body.comment, _from(_user))
    return {"status": status}
