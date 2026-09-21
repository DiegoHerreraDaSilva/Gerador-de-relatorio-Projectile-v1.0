"""Trava `generator.parse_period_label` — o parser da label de PERÍODO
("Julho a Novembro/2026") que a busca "Buscar do Projectile" com intervalo
de meses produz (ver `FileUpload.tsx` `buildPeriodLabel`) e que
`main._resolve_month_range`/`email_ingest.process_new_emails` precisam ler
de volta. `parse_month_label` (mês único) já é testado indiretamente pelos
testes de `resolve_total_hours`/`read_pdf_report_data` em
`test_email_ingest.py` — aqui é só o caminho de período, que não existia
antes desta feature."""
from __future__ import annotations

from backend.app.generator import parse_period_label


def test_same_year_period():
    assert parse_period_label("Julho a Novembro/2026") == ((2026, 7), (2026, 11))


def test_crossing_year_period():
    assert parse_period_label("Dezembro/2025 a Fevereiro/2026") == ((2025, 12), (2026, 2))


def test_english_and_german_month_names():
    assert parse_period_label("July a November/2026") == ((2026, 7), (2026, 11))
    assert parse_period_label("Dezember/2025 a Februar/2026") == ((2025, 12), (2026, 2))


def test_single_month_is_not_a_period():
    """Mês único (sem " a ") não é período — quem chama tenta
    `parse_month_label` primeiro, este parser nunca deveria "roubar" esse
    caso; confirma que não há falso positivo."""
    assert parse_period_label("Julho/2026") is None


def test_end_before_start_is_invalid():
    assert parse_period_label("Novembro a Julho/2026") is None


def test_garbage_text_is_invalid():
    assert parse_period_label("não é uma competência") is None
    assert parse_period_label("") is None


def test_same_month_as_start_and_end_still_parses():
    """Não é bem o caso de uso (o frontend colapsa isso pra mês único antes
    de mandar), mas não deve quebrar se acontecer."""
    assert parse_period_label("Julho a Julho/2026") == ((2026, 7), (2026, 7))
