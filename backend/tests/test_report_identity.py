"""`compute_identity_hash`/`parse_competence_range`
(backend/app/services/snapshot.py) — puramente funcionais, sem banco."""
from __future__ import annotations

from datetime import date

from backend.app.services.snapshot import compute_identity_hash, parse_competence_range


def test_identity_hash_normaliza_espaco_e_maiusculas():
    a = compute_identity_hash("  se.01.002  ", None, "Julho/2026")
    b = compute_identity_hash("SE.01.002", None, "Julho/2026")
    assert a == b


def test_identity_hash_none_e_string_vazia_de_scope_sao_equivalentes():
    a = compute_identity_hash("SE.01.002", None, "Julho/2026")
    b = compute_identity_hash("SE.01.002", "  ", "Julho/2026")
    assert a == b


def test_identity_hash_muda_se_scope_muda():
    a = compute_identity_hash("SE.01.002", None, "Julho/2026")
    b = compute_identity_hash("SE.01.002", "Pacote X", "Julho/2026")
    assert a != b


def test_identity_hash_muda_se_competencia_muda():
    a = compute_identity_hash("SE.01.002", None, "Julho/2026")
    b = compute_identity_hash("SE.01.002", None, "Agosto/2026")
    assert a != b


def test_identity_hash_nao_confunde_relatorios_diferentes_por_concatenacao():
    """Sem separador entre as partes, "AB"+"C" e "A"+"BC" colidiriam — o
    separador de controle (\\x1f) evita isso."""
    a = compute_identity_hash("AB", "C", "Julho/2026")
    b = compute_identity_hash("A", "BC", "Julho/2026")
    assert a != b


def test_parse_competence_range_mes_unico():
    start, end = parse_competence_range("Julho/2026")
    assert start == date(2026, 7, 1)
    assert end == date(2026, 7, 31)


def test_parse_competence_range_periodo_mesmo_ano():
    start, end = parse_competence_range("Julho a Novembro/2026")
    assert start == date(2026, 7, 1)
    assert end == date(2026, 11, 30)


def test_parse_competence_range_periodo_cruzando_ano():
    start, end = parse_competence_range("Dezembro/2025 a Fevereiro/2026")
    assert start == date(2025, 12, 1)
    assert end == date(2026, 2, 28)


def test_parse_competence_range_texto_nao_reconhecido_nao_levanta_excecao():
    start, end = parse_competence_range("texto qualquer sem formato de mês")
    assert (start, end) == (None, None)


def test_parse_competence_range_string_vazia_nao_levanta_excecao():
    assert parse_competence_range("") == (None, None)
