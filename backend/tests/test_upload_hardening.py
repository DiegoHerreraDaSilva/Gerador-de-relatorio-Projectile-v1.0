"""Hardening de upload do /parse (GUIA_EVOLUCAO_GERADOR_PROJECTILE.md,
seção 12): tamanho rejeitado ANTES de materializar o arquivo inteiro em
memória, e limite de conteúdo descomprimido (zip bomb)."""
from __future__ import annotations

import io
import zipfile

from fastapi.testclient import TestClient
from openpyxl import Workbook

from backend.app import management
from backend.app.api.routers import parsing as parsing_module
from backend.app.main import app, require_session


def _fake_user() -> dict:
    return {"name": "Diego Herrera", "login": "dherrera", "email": "diego.herrera@schwaben.com.br"}


def _client(monkeypatch) -> TestClient:
    monkeypatch.setattr(management, "MANAGEMENT_PANEL_LOGINS", {"dherrera"})
    app.dependency_overrides[require_session] = _fake_user
    return TestClient(app)


def _valid_xlsx_bytes() -> bytes:
    wb = Workbook()
    ws = wb.active
    ws.append(["Dados", "Horário", "Hs", "Observação", "Projeto", "Pacote de Trabalho"])
    ws.append(["x", "08:00-09:00", "1", "Grupo - Atividade", "Projeto X", "Pacote A"])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def test_parse_endpoint_aceita_upload_dentro_do_limite(monkeypatch):
    client = _client(monkeypatch)
    with client:
        response = client.post(
            "/parse", files={"file": ("planilha.xlsx", _valid_xlsx_bytes(), "application/octet-stream")}
        )
    app.dependency_overrides.pop(require_session, None)
    assert response.status_code == 200
    assert len(response.json()["packages"]) == 1


def test_parse_endpoint_rejeita_upload_maior_que_limite(monkeypatch):
    # baixa o limite pra não precisar gerar 25 MB de verdade no teste
    monkeypatch.setattr(parsing_module, "_MAX_UPLOAD_BYTES", 1024)
    client = _client(monkeypatch)
    big_content = b"x" * 2048
    with client:
        response = client.post(
            "/parse", files={"file": ("planilha.xlsx", big_content, "application/octet-stream")}
        )
    app.dependency_overrides.pop(require_session, None)
    assert response.status_code == 413


def test_stream_upload_to_tempfile_nao_deixa_arquivo_temporario_orfao(monkeypatch, tmp_path):
    """Confirma que abortar por tamanho limpa o arquivo temporário parcial —
    não é só rejeitar a requisição, é não vazar disco a cada tentativa."""
    import os

    monkeypatch.setattr(parsing_module.tempfile, "gettempdir", lambda: str(tmp_path))
    monkeypatch.setattr(parsing_module, "_MAX_UPLOAD_BYTES", 1024)
    client = _client(monkeypatch)
    with client:
        response = client.post(
            "/parse", files={"file": ("planilha.xlsx", b"x" * 2048, "application/octet-stream")}
        )
    app.dependency_overrides.pop(require_session, None)
    assert response.status_code == 413
    assert os.listdir(tmp_path) == []


def test_reject_if_oversized_uncompressed_aceita_zip_pequeno(tmp_path):
    path = tmp_path / "pequeno.xlsx"
    with zipfile.ZipFile(path, "w") as zf:
        zf.writestr("a.txt", "conteudo pequeno de verdade")
    parsing_module._reject_if_oversized_uncompressed(str(path))  # não levanta


def test_reject_if_oversized_uncompressed_ignora_arquivo_invalido(tmp_path):
    """Zip inválido não é rejeitado aqui — parse_projectile_export trata o
    erro de "arquivo inválido" (mesmo contrato de antes da mudança)."""
    path = tmp_path / "invalido.xlsx"
    path.write_bytes(b"isso definitivamente nao e um arquivo zip valido")
    parsing_module._reject_if_oversized_uncompressed(str(path))  # não levanta


def test_is_oversized_uncompressed_respeita_o_limite_exato():
    limit = parsing_module._MAX_UNCOMPRESSED_XLSX_BYTES
    assert parsing_module._is_oversized_uncompressed(limit) is False
    assert parsing_module._is_oversized_uncompressed(limit + 1) is True
