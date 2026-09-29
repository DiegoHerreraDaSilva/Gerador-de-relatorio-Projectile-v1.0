"""Agendador da rodada mensal: a decisão (pura, com fuso e recuperação), o
`tick` com banco e o que a tela mostra. Nada aqui espera o relógio de verdade."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pytest

from backend.app import projectile_db
from backend.app.auto_generation import builder, rules, scheduler, service
from backend.app.services import auto_generation_store as store
from backend.tests.test_custom_generation import _MANAGER, _scope, custom_db  # noqa: F401 — fixture reaproveitada

SP = scheduler.TIMEZONE


def sp(year, month, day, hour=0, minute=0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=SP)


def utc_naive(moment: datetime) -> datetime:
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def run_row(status="done", started_at=None):
    return {"id": "R1", "competence": "2026-09", "status": status, "started_at": started_at or datetime(2026, 10, 1, 9, 0)}


def request(status="agendado"):
    return {"id": "Q1", "status": status}


# --- decide: horário e fuso -----------------------------------------------------------------


def test_so_vence_a_partir_do_horario_do_dia_1_em_sao_paulo():
    assert scheduler.decide(sp(2026, 10, 1, 5, 59), {}, None, [], None) is None
    decision = scheduler.decide(sp(2026, 10, 1, 6, 0), {}, None, [], None)
    assert decision == scheduler.Decision("2026-09", "sem_rodada")


def test_o_fuso_manda_nao_o_utc():
    # 08:59 UTC = 05:59 em São Paulo (UTC-3): ainda não; 09:00 UTC = 06:00: agora
    early = datetime(2026, 10, 1, 8, 59, tzinfo=timezone.utc).astimezone(SP)
    late = datetime(2026, 10, 1, 9, 0, tzinfo=timezone.utc).astimezone(SP)
    assert scheduler.decide(early, {}, None, [], None) is None
    assert scheduler.decide(late, {}, None, [], None).competence == "2026-09"


def test_o_alvo_e_sempre_o_mes_anterior_inclusive_na_virada_do_ano():
    assert scheduler.previous_competence(sp(2027, 1, 1, 6)) == "2026-12"
    assert scheduler.decide(sp(2027, 1, 1, 6), {}, None, [], None).competence == "2026-12"
    assert scheduler.previous_competence(sp(2026, 3, 31)) == "2026-02"


def test_recupera_a_rodada_se_o_servidor_estava_desligado_no_dia():
    # ligou de novo no dia 17: o mês que fechou ainda não rodou
    assert scheduler.decide(sp(2026, 10, 17, 10, 0), {}, None, [], None).reason == "sem_rodada"


def test_dia_e_hora_vem_do_padrao_geral():
    config = {"schedule_day": 15, "schedule_time": "08:30"}
    assert scheduler.decide(sp(2026, 10, 14, 23, 59), config, None, [], None) is None
    assert scheduler.decide(sp(2026, 10, 15, 8, 29), config, None, [], None) is None
    assert scheduler.decide(sp(2026, 10, 15, 8, 30), config, None, [], None).competence == "2026-09"


def test_desligado_nunca_dispara():
    assert scheduler.decide(sp(2026, 10, 1, 7), {"schedule_enabled": False}, None, [], None) is None


# --- decide: o que já existe -------------------------------------------------------------------


def test_rodada_concluida_nao_repete():
    assert scheduler.decide(sp(2026, 10, 2, 9), {}, run_row("done"), [], None) is None


def test_pedido_agendado_dispara_de_novo_mas_pedido_com_erro_sozinho_nao():
    assert scheduler.decide(sp(2026, 10, 2, 9), {}, run_row("done"), [request("agendado")], None).reason == "pedidos_pendentes"
    assert scheduler.decide(sp(2026, 10, 2, 9), {}, run_row("done"), [request("erro")], None) is None


def test_rodada_que_falhou_tenta_de_novo():
    assert scheduler.decide(sp(2026, 10, 1, 9), {}, run_row("failed"), [], None).reason == "rodada_falhou"


def test_rodada_em_andamento_bloqueia_e_a_morta_libera():
    now = sp(2026, 10, 1, 7, 0)
    alive = run_row("running", utc_naive(now) - timedelta(minutes=5))
    dead = run_row("running", utc_naive(now) - timedelta(minutes=31))
    assert scheduler.decide(now, {}, alive, [], None) is None
    assert scheduler.decide(now, {}, dead, [], None).reason == "rodada_falhou"


# --- decide: sem martelar ---------------------------------------------------------------------------


def test_uma_tentativa_por_hora_e_no_maximo_cinco():
    now = sp(2026, 10, 1, 12, 0)

    def state(attempts, minutes_ago, competence="2026-09"):
        return {"competence": competence, "attempts": attempts,
                "last_attempt_at": (utc_naive(now) - timedelta(minutes=minutes_ago)).isoformat()}

    failed = run_row("failed")
    assert scheduler.decide(now, {}, failed, [], state(1, 30)) is None
    assert scheduler.decide(now, {}, failed, [], state(1, 61)).reason == "rodada_falhou"
    assert scheduler.decide(now, {}, failed, [], state(5, 600)) is None
    # tentativas de OUTRA competência não contam
    assert scheduler.decide(now, {}, failed, [], state(5, 1, competence="2026-08")).competence == "2026-09"


# --- regras do padrão geral ----------------------------------------------------------------------------


def test_padrao_ligado_dia_1_as_6():
    effective = rules.effective({}, None)
    assert (effective["schedule_enabled"], effective["schedule_day"], effective["schedule_time"]) == (True, 1, "06:00")


@pytest.mark.parametrize("raw", [
    {"schedule_day": 0}, {"schedule_day": 29}, {"schedule_time": "24:00"}, {"schedule_time": "6:00"},
    {"schedule_time": "06:60"}, {"schedule_enabled": "talvez"},
])
def test_agenda_invalida_e_recusada(raw):
    with pytest.raises(ValueError):
        rules.validate_global(raw)


def test_agenda_valida_e_guardada_e_nao_existe_por_familia():
    saved = rules.validate_global({"schedule_enabled": False, "schedule_day": 28, "schedule_time": "23:59"})
    assert saved == {"schedule_enabled": False, "schedule_day": 28, "schedule_time": "23:59"}
    with pytest.raises(ValueError):
        rules.validate_rule({"schedule_day": 3})


# --- tick com banco -----------------------------------------------------------------------------------------


def test_tick_gera_a_rodada_e_os_pedidos_e_nao_repete(custom_db):
    service.schedule_custom(_scope([{"clients": ["Mercedes"]}], split_by="projeto"), _MANAGER)
    # setembro, dia 1, 06:00 → alvo agosto
    decision = scheduler.tick(sp(2026, 9, 1, 6, 0))
    assert decision == scheduler.Decision("2026-08", "sem_rodada")
    run = store.get_run("2026-08")
    assert run["status"] == "done" and run["triggered_by"] == "sistema"
    assert {i["project_id"] for i in service.competence_view("2026-08")["items"]} == {"E8", "P1", "F1"}
    assert len(store.list_custom()) == 1 and service.custom_view()["requests"] == []
    assert store.get_scheduler_state()["attempts"] == 1
    assert scheduler.tick(sp(2026, 9, 1, 6, 5)) is None           # nada mais a fazer
    assert len(service.competence_view("2026-08")["items"]) == 3


def test_tick_respeita_o_relogio_antes_da_hora(custom_db):
    assert scheduler.tick(sp(2026, 9, 1, 5, 59)) is None
    assert store.get_run("2026-08") is None and store.get_scheduler_state() == {}


def test_rodada_que_falha_e_tentada_de_hora_em_hora_ate_cinco(custom_db, monkeypatch):
    def down(competence):
        raise projectile_db.ProjectileDbError("Projectile fora do ar")

    monkeypatch.setattr(builder, "month_projects", down)
    start = sp(2026, 9, 1, 6, 0)
    assert scheduler.tick(start) is not None and store.get_run("2026-08")["status"] == "failed"
    assert scheduler.tick(start + timedelta(minutes=30)) is None                     # cedo demais
    for attempt in range(2, 6):
        assert scheduler.tick(start + timedelta(hours=attempt)) is not None, attempt
    assert store.get_scheduler_state()["attempts"] == 5
    assert scheduler.tick(start + timedelta(hours=9)) is None                        # esgotou


def test_depois_de_falhar_volta_a_funcionar_quando_o_projectile_volta(custom_db, monkeypatch):
    original = builder.month_projects

    def down(competence):
        raise projectile_db.ProjectileDbError("fora do ar")

    monkeypatch.setattr(builder, "month_projects", down)
    start = sp(2026, 9, 1, 6, 0)
    scheduler.tick(start)
    monkeypatch.setattr(builder, "month_projects", original)
    assert scheduler.tick(start + timedelta(hours=2)).reason == "rodada_falhou"
    assert store.get_run("2026-08")["status"] == "done"
    assert len(service.competence_view("2026-08")["items"]) == 3


def test_outro_processo_rodando_nao_vira_erro(custom_db, monkeypatch):
    def busy(*a, **k):
        raise service.RunInProgress("2026-08")

    monkeypatch.setattr(service, "start_run", busy)
    assert scheduler.tick(sp(2026, 9, 1, 6, 0)) is not None                          # não levanta


def test_rodada_feita_a_mao_antes_nao_e_refeita_pelo_agendador(custom_db):
    service.start_run("2026-08", _MANAGER, background=False)
    assert scheduler.tick(sp(2026, 9, 1, 6, 0)) is None
    assert store.get_scheduler_state() == {}


# --- o que a tela mostra ----------------------------------------------------------------------------------------


def test_informacao_da_proxima_geracao(custom_db):
    before = scheduler.schedule_info(sp(2026, 9, 29, 10, 0))
    assert before["enabled"] is True and before["time"] == "06:00" and before["day"] == 1
    assert before["next_at"] == "2026-10-01T06:00:00-03:00"
    assert before["target"] == "2026-09" and before["target_label"] == "Setembro/2026"
    after = scheduler.schedule_info(sp(2026, 10, 1, 7, 0))
    assert after["next_at"] == "2026-11-01T06:00:00-03:00" and after["target"] == "2026-10"
    december = scheduler.schedule_info(sp(2026, 12, 20))
    assert december["next_at"] == "2027-01-01T06:00:00-03:00" and december["target"] == "2026-12"


def test_informacao_traz_a_rodada_do_mes_que_fechou_e_o_desligado(custom_db):
    service.start_run("2026-08", _MANAGER, background=False)
    info = scheduler.schedule_info(sp(2026, 9, 10, 9))
    assert info["last_run"]["competence"] == "2026-08" and info["last_run"]["status"] == "done"
    with store.write_session() as s:
        s.set_config({"schedule_enabled": False})
    assert scheduler.schedule_info(sp(2026, 9, 10, 9))["enabled"] is False


def test_rotas_de_config_e_competencias_trazem_o_agendamento(custom_db):
    from backend.tests.test_custom_generation import _client

    manager = _client()
    assert manager.get("/auto-generation/config").json()["schedule"]["time"] == "06:00"
    assert "next_at" in manager.get("/auto-generation/competences").json()["schedule"]
    saved = manager.put("/auto-generation/config", json={"schedule_day": 5, "schedule_time": "07:15"})
    assert saved.status_code == 200
    assert manager.get("/auto-generation/config").json()["schedule"]["day"] == 5
    assert manager.put("/auto-generation/config", json={"schedule_day": 31}).status_code == 422
