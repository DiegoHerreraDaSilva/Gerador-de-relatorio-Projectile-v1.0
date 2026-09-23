"""Importa `backend/data/management_kpi.json` (dados do Painel de Gerência /
Diagnóstico) pras tabelas `mgmt_*` do `reports_db`. Roda uma única vez por
banco; `scripts/atualizar-servidor.bat` chama isto logo depois do
`alembic upgrade head`.

    python -m backend.app.tools.import_management_json [--path CAMINHO]

- Sem arquivo: não há nada a importar (instalação nova) — sai com sucesso.
- Já importado antes (registro em `mgmt_meta`): não faz nada.
- Banco já com dados de gerência sem registro de importação: recusa (sai
  com erro) em vez de misturar. Acontece se o backend novo subir antes da
  importação: o polling de e-mail reprocessa os e-mails e recria as
  amostras SEM as correções manuais que só o JSON tem. Nesse caso, rode com
  `--replace-existing` — descarta o que está no banco e importa o JSON,
  guardando uma cópia do descartado em `mgmt_meta`.
- Sucesso: renomeia o JSON pra `management_kpi.json.migrated-<data>` —
  backup, nunca apagado; a aplicação não lê mais esse arquivo.

Tudo numa transação: se falhar no meio, o banco fica como estava e o JSON
não é renomeado."""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime

from dotenv import load_dotenv


def main(argv: list[str] | None = None) -> int:
    load_dotenv()
    from .. import management
    from ..services.management_store import ManagementStoreError

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--path", default=management.LEGACY_JSON_PATH)
    parser.add_argument(
        "--replace-existing", action="store_true",
        help="descarta dados de gerência já no banco (sem registro de importação) e importa o JSON",
    )
    args = parser.parse_args(argv)

    if not os.path.exists(args.path):
        print(f"Nada a importar: {args.path} não existe.")
        return 0

    with open(args.path, encoding="utf-8") as f:
        raw = json.load(f)

    try:
        result = management.import_legacy_document(
            raw, source_path=os.path.abspath(args.path), replace_existing=args.replace_existing,
        )
    except ManagementStoreError as e:
        print(f"ERRO: {e}", file=sys.stderr)
        return 1

    backup_path = f"{args.path}.migrated-{datetime.now().strftime('%Y%m%d-%H%M%S')}"
    os.replace(args.path, backup_path)

    if result["status"] == "already_imported":
        leftover = {key: len(raw.get(key) or []) for key in ("manual_entries", "project_kpi_samples", "skipped_messages")}
        print(f"Já importado antes; arquivo que sobrou movido pra {backup_path}.")
        if any(leftover.values()):
            # o backend antigo (ainda rodando até o restart) gravou um JSON
            # novo depois da importação — isso NÃO entra no banco sozinho.
            print(
                f"ATENÇÃO: esse arquivo tinha dados gravados depois da importação ({leftover}) "
                "que não estão no reports_db. Confira o backup e refaça essas edições pela tela."
            )
        return 0
    counts = ", ".join(f"{key}={value}" for key, value in result["counts"].items())
    print(f"Importado: {counts}. Backup do JSON em {backup_path}.")
    if "replaced_samples" in result:
        print(
            f"Substituídas {result['replaced_samples']} amostra(s) que já estavam no banco "
            "(cópia guardada em mgmt_meta, chave legacy_json_import)."
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
