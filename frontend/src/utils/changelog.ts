export type Role = "manager" | "coordinator" | "collaborator";

export type ChangelogItem = {
  text: string;
  /** Só aparece pra estes papéis; ausente = todos. */
  roles?: Role[];
};

export type ChangelogEntry = {
  /** Identifica a versão (data da entrega); o que já foi visto é guardado por ela. */
  version: string;
  title: string;
  items: ChangelogItem[];
};

/** Novidades do app, da mais nova pra mais antiga. Entrega nova = entrada nova no TOPO (a pessoa vê uma vez). */
export const CHANGELOG: ChangelogEntry[] = [
  {
    version: "2026-09-30",
    title: "Atalhos, avisos e telas mais rápidas",
    items: [
      { text: "Ctrl+K (ou “/”) abre a paleta de comandos: vá para qualquer tela, guia ou ação digitando." },
      { text: "Ctrl+Z desfaz a última edição no relatório (fora dos campos de texto)." },
      { text: "Avisos no canto da tela confirmam o que aconteceu ao gerar, enviar ou apagar." },
      { text: "Todo filtro e lista suspensa tem busca e uma dica instantânea com o valor completo." },
      { text: "As telas abrem mais rápido: cada uma só é carregada quando você entra nela." },
      { text: "No período de vários meses agora dá para escolher também o ano inicial e o final." },
      {
        text: "No Diagnóstico, o filtro já abre no mês passado e há um resumo das pendências de envio por cliente.",
        roles: ["manager", "coordinator"],
      },
      { text: "O Painel de Gerência exporta para Excel e mostra a variação sobre o mês anterior.", roles: ["manager"] },
      {
        text: "Novo botão “Resumo do mês” no Painel: um texto de gerência com os números do mês, redigido pela IA (com todo número conferido) ou automático.",
        roles: ["manager"],
      },
      {
        text: "O Histórico ordena por coluna e apaga vários relatórios de uma vez: eles vão para a Lixeira (30 dias para restaurar) e o aviso tem o botão Desfazer.",
        roles: ["manager"],
      },
      { text: "Projeto ou cliente fechado no Diagnóstico sai sozinho da geração automática.", roles: ["manager"] },
      {
        text: "Novo no Padrão geral: lembretes por e-mail de relatório parado (desligado por padrão; você escolhe depois de quantos dias).",
        roles: ["manager"],
      },
    ],
  },
];

export function roleOf(user: { isManager: boolean; isCoordinator: boolean }): Role {
  return user.isManager ? "manager" : user.isCoordinator ? "coordinator" : "collaborator";
}

/** As entradas que a pessoa ainda não viu, com os itens do papel dela (entrada sem item pra ela some).
 * `seenVersion` nulo = primeira vez: mostra só a mais recente, não o histórico inteiro. Versão vista que não está
 * mais na lista (removida) também mostra só a mais recente. */
export function unseenEntries(
  seenVersion: string | null,
  role: Role,
  changelog: ChangelogEntry[] = CHANGELOG,
): ChangelogEntry[] {
  const seenIndex = seenVersion ? changelog.findIndex((e) => e.version === seenVersion) : -1;
  const candidates = seenIndex >= 0 ? changelog.slice(0, seenIndex) : changelog.slice(0, 1);
  return entriesFor(role, candidates);
}

/** Todas as entradas, filtradas pelo papel (abertura manual: "Ver novidades"). */
export function entriesFor(role: Role, changelog: ChangelogEntry[] = CHANGELOG): ChangelogEntry[] {
  return changelog
    .map((entry) => ({ ...entry, items: entry.items.filter((item) => !item.roles || item.roles.includes(role)) }))
    .filter((entry) => entry.items.length > 0);
}

const STORAGE_PREFIX = "relatorio-horas:novidades:visto:";

/** Última versão que ESTA pessoa viu neste navegador (por login: outro usuário no mesmo navegador tem a sua). */
export function readSeenVersion(login: string): string | null {
  try {
    return localStorage.getItem(STORAGE_PREFIX + login.toLowerCase());
  } catch {
    return null;
  }
}

export function markSeen(login: string, version: string = CHANGELOG[0]?.version ?? ""): void {
  try {
    if (version) localStorage.setItem(STORAGE_PREFIX + login.toLowerCase(), version);
  } catch {
    // localStorage indisponível (modo privado): só volta a aparecer na próxima visita
  }
}
