import { VIEW_ACCESS, VIEW_ORDER, VIEW_TITLES, type AppView, type NavAccess } from "../appView";
import { matchesQuery, normalizeForSearch } from "./search";

export type CommandGroup = "Ir para" | "Guias abertas" | "Ações";

export type Command = {
  id: string;
  label: string;
  group: CommandGroup;
  /** Palavras extras que também encontram o comando (sinônimos). */
  keywords?: string;
  /** Texto pequeno à direita (ex.: "tela atual"). */
  hint?: string;
  run: () => void;
};

export type PaletteContext = {
  isManager: boolean;
  isCoordinator: boolean;
  currentView: AppView;
  /** "Minhas revisões" só aparece pra quem tem (ou já teve) relatório atribuído — como no menu. */
  hasAssignedReviews: boolean;
  tabs: { id: string; label: string }[];
  activeTabId: string;
  navigate: (view: AppView) => void;
  switchTab: (id: string) => void;
  newReport: () => void;
  logout: () => void;
};

/** Mesma regra do menu lateral: "all" = todo mundo; "coordinator" = gerente ou coordenador; "manager" = só gerente.
 * Só esconde opção — quem barra de verdade é o backend. */
export function canAccess(access: NavAccess, user: { isManager: boolean; isCoordinator: boolean }): boolean {
  return access === "all" || (access === "manager" ? user.isManager : user.isManager || user.isCoordinator);
}

const VIEW_KEYWORDS: Partial<Record<AppView, string>> = {
  report: "gerar relatório importar xlsx pdf editar",
  dashboard: "minhas horas dashboard apontamentos calendário",
  management: "gerência kpi painel faturado performance",
  diagnostics: "diagnóstico amostras enviados fechados",
  analytics: "analytics métricas relatórios gerados",
  history: "histórico versões arquivos auditoria apagar",
  "analytics-chat": "chat analítico perguntar ia",
  "auto-generation": "geração automática rascunhos rodada mês revisão",
  "my-reviews": "revisões revisar pendentes",
};

/** Comandos disponíveis pra quem está logado, na ordem em que aparecem com a busca vazia. */
export function buildCommands(ctx: PaletteContext): Command[] {
  const commands: Command[] = [];
  for (const view of VIEW_ORDER) {
    if (!canAccess(VIEW_ACCESS[view], ctx)) continue;
    if (view === "my-reviews" && !ctx.hasAssignedReviews && ctx.currentView !== "my-reviews") continue;
    commands.push({
      id: `view:${view}`,
      label: VIEW_TITLES[view],
      group: "Ir para",
      keywords: VIEW_KEYWORDS[view],
      hint: view === ctx.currentView ? "tela atual" : undefined,
      run: () => ctx.navigate(view),
    });
  }
  for (const tab of ctx.tabs) {
    commands.push({
      id: `tab:${tab.id}`,
      label: tab.label,
      group: "Guias abertas",
      keywords: "guia relatório aberto",
      hint: tab.id === ctx.activeTabId && ctx.currentView === "report" ? "guia atual" : undefined,
      run: () => {
        ctx.navigate("report");
        ctx.switchTab(tab.id);
      },
    });
  }
  commands.push(
    {
      id: "action:new-report",
      label: "Novo relatório",
      group: "Ações",
      keywords: "criar nova guia",
      run: ctx.newReport,
    },
    {
      id: "action:logout",
      label: "Sair",
      group: "Ações",
      keywords: "logout desconectar encerrar sessão",
      run: ctx.logout,
    },
  );
  return commands;
}

/** Filtra e ordena: título que COMEÇA com a busca vem antes do que só contém; dentro de cada um, a ordem original.
 * Busca vazia devolve tudo. Sem acento, sem diferenciar maiúsculas, várias palavras em qualquer ordem. */
export function filterCommands(commands: Command[], query: string): Command[] {
  const q = query.trim();
  if (!q) return commands;
  const normalized = normalizeForSearch(q);
  const matching = commands
    .map((command, index) => ({ command, index }))
    .filter(({ command }) => matchesQuery(`${command.label} ${command.keywords ?? ""}`, q));
  const rank = (c: Command) =>
    normalizeForSearch(c.label).startsWith(normalized) ? 0 : matchesQuery(c.label, q) ? 1 : 2;
  return matching.sort((a, b) => rank(a.command) - rank(b.command) || a.index - b.index).map(({ command }) => command);
}
