"""Geração automática de relatórios (aba "Geração automática", só gerente).

Um rascunho por (competência, projeto) é montado no servidor a partir do
Projectile, com o que o gerente/revisor ajustou no mês anterior da mesma
família de projeto (`memory`); é revisado no editor de sempre e só vira
relatório do histórico (`reports_db`) na aprovação, quando o número do
relatório já foi digitado. Regras e decisões na seção "Geração automática"
do CLAUDE.md."""
