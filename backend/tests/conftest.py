"""Garante a raiz do repo no sys.path mesmo se pytest for invocado de um jeito
que não respeite `pythonpath` do pytest.ini (ex: um runner de IDE que ignora
o ini). Idempotente e barato — checagem redundante de propósito com
`pytest.ini:pythonpath`, não um substituto dele."""
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))
