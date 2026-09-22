# Plano — modernização de UI/UX

## Objetivo

Aplicar ao projeto a navegação lateral e o fluxo horizontal de geração de relatórios já definidos, preservar os contratos atuais com o backend e levar o mesmo sistema visual para Dashboard de horas, Painel de gerência e Diagnóstico.

## Restrições e decisões

- Preservar as alterações locais existentes; completar e corrigir a implementação atual, sem recomeçar do zero.
- Não alterar contratos das APIs nem regras de cálculo/geração.
- Manter os quatro cards do fluxo Projectile na mesma linha em telas largas; permitir quebra responsiva somente quando faltar espaço.
- Esconder totalmente os controles não aplicáveis ao fluxo escolhido.
- Manter tema claro/escuro, múltiplas guias e permissões de gerente.
- Reaproveitar tokens e componentes existentes para reduzir divergência visual entre páginas.

## Fases

### 1. Consolidar shell e fluxo de importação

- Corrigir tipagem/acessibilidade dos novos radio cards.
- Validar estados condicionais de Arquivo x Projectile e Meu usuário x Buscar cliente.
- Aplicar estado desabilitado correto aos CTAs e mensagens de status acessíveis.
- Refinar largura, densidade, responsividade e sidebar recolhível/drawer.

Critérios de aceite:

- Build TypeScript sem erros.
- Fluxo local mostra fonte, arquivo e organização; não mostra período/cliente.
- Fluxo Projectile mostra fonte, escopo, organização e período; não mostra upload.
- Buscar cliente exige cliente e ao menos um projeto.
- Sidebar funciona expandida, recolhida e no mobile.

### 2. Uniformizar as demais páginas

- Criar cabeçalhos internos compactos com título, contexto e ações úteis.
- Alinhar larguras máximas, espaçamentos, cards, filtros e estados vazios/carregamento.
- Melhorar semântica e nomes acessíveis de filtros, tabelas e ações.
- Garantir que toolbars fixas não conflitem com sidebar/topbar responsiva.

Critérios de aceite:

- Dashboard, Gerência e Diagnóstico usam a mesma hierarquia visual do shell.
- Ações primárias/secundárias e estados de feedback permanecem claros.
- Nenhuma funcionalidade ou permissão existente é removida.

### 3. Verificação

- Rodar testes unitários e build.
- Revisar diff para regressões e alterações fora de escopo.
- Abrir a aplicação em navegador isolado, conferir console, desktop e viewport móvel.
- Validar navegação, foco, seleção condicional e layout das quatro etapas.

## Fora de escopo

- Redesenho do documento/planilha na área de preview.
- Mudanças no backend ou no esquema de autenticação.
- Novas funcionalidades de relatório além das já existentes.
