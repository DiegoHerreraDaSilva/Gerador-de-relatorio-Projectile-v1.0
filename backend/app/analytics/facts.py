"""Carrega, uma vez por pergunta e só se a pergunta precisar, as linhas que
a consulta cruzada agrega. Nenhuma consulta nova ao Projectile: tudo vem do
mesmo cache de 15 min do Painel de Gerência (`management._get_cached_rows`)
e da mesma função do Diagnóstico (`management.compute_monthly_kpis`).

A janela é a do Painel (do dia 1 de N-1 meses atrás até o fim do mês
corrente, como `management._resolve_period(meses)`) — mesmas datas = mesma chave de
cache, então o chat e o Painel/Diagnóstico não buscam duas vezes.

Funções externas referenciadas via atributo do módulo (`management.x`,
`management_store.x`) pra os testes poderem trocar por dados fixos."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from .. import management
from ..repositories import engineering_hours_repository
from ..repositories.engineering_hours_repository import HoursRow
from ..services import management_store
from .periods import add_months


@dataclass(frozen=True)
class BilledSample:
    project_id: str
    month: str  # "YYYY-MM"
    billed_hours: float


@dataclass(frozen=True)
class SendStatusRow:
    project_id: str
    project: str
    client: str
    month: str
    status: str  # sent | partial | none | closed


class DataSources:
    def __init__(self, today: date, window_months: int):
        self.today = today
        self.window_months = window_months
        # mesma fórmula de `management._resolve_period(meses)` (dia 1 de N-1
        # meses atrás até o fim do mês corrente), mas a partir do `today`
        # recebido — mesma chave de cache do Painel em produção
        current = date(today.year, today.month, 1)
        self.window_start = add_months(current, -(window_months - 1))
        self.window_end = add_months(current, 1) - timedelta(days=1)
        self._hours: list[HoursRow] | None = None
        self._document: dict | None = None
        self._send_status: list[SendStatusRow] | None = None
        self._project_info: dict[str, dict] | None = None

    # --- horas ----------------------------------------------------------
    def hours(self) -> list[HoursRow]:
        if self._hours is None:
            self._hours = engineering_hours_repository.load_rows(self.window_start, self.window_end)
        return self._hours


    # --- faturado --------------------------------------------------------
    def _management_document(self) -> dict:
        if self._document is None:
            self._document = management_store.load_document()
        return self._document

    def billed_samples(self) -> list[BilledSample]:
        """Amostras de faturado (e-mail ou manuais), sem as duplicadas — a
        mesma regra de soma do Painel (`compute_monthly_kpis`)."""
        samples = []
        for sample in self._management_document().get("project_kpi_samples", []):
            if sample.get("is_duplicate") or not sample.get("project_id") or not sample.get("month"):
                continue
            samples.append(BilledSample(
                project_id=str(sample["project_id"]),
                month=str(sample["month"]),
                billed_hours=float(sample.get("billed_hours") or 0),
            ))
        return samples

    def manual_billed_by_month(self) -> dict[str, float]:
        """Ajuste manual do gerente (total do TIME no mês) — tem prioridade
        sobre as amostras, mas só vale pro total mensal sem recorte de
        cliente/projeto (não tem dimensão de projeto)."""
        return {
            month: float(entry["billed_hours"])
            for month, entry in (self._management_document().get("manual_entries") or {}).items()
            if entry and entry.get("billed_hours") is not None
        }

    def project_info(self) -> dict[str, dict]:
        """`project_id -> {"name", "client"}` pra todo projeto que aparece nas
        horas ou nas amostras de faturado (projeto com relatório recebido mas
        sem hora na janela ainda precisa de nome e cliente)."""
        if self._project_info is None:
            info = {r.project_id: {"name": r.project, "client": r.client} for r in self.hours() if r.project_id}
            missing = sorted({s.project_id for s in self.billed_samples()} - set(info))
            info.update(engineering_hours_repository.project_details(missing))
            self._project_info = info
        return self._project_info

    # --- status de envio ------------------------------------------------
    def send_status(self) -> list[SendStatusRow]:
        if self._send_status is None:
            kpis = management.compute_monthly_kpis(months=self.window_months)
            self._send_status = [
                SendStatusRow(
                    project_id=str(row["project_id"]),
                    project=row.get("project_name") or "Sem nome",
                    client=row.get("client") or "Sem cliente",
                    month=row["month"],
                    status=row["status"],
                )
                for row in kpis.get("project_send_status", [])
            ]
        return self._send_status
