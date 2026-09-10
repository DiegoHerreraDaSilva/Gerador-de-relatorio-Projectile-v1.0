export type Activity = {
  id: string;
  description: string;
  hours: number | null;
  // fixo desde a criação (não recalculado a partir de `hours`): true pra
  // atividade adicionada manualmente ("+ Nova atividade"), false pra atividade
  // vinda do import/Projectile. Precisa ser independente do valor atual de
  // `hours` — senão, no instante em que o usuário digita o primeiro número
  // válido, `hours` deixa de ser null e o campo editável desapareceria no
  // meio da digitação (bug real que já aconteceu).
  extra: boolean;
};

export type Group = {
  id: string;
  name: string;
  performance: number;
  activities: Activity[];
};

export type WorkPackage = {
  id: string;
  key: string;
  projectCode: string;
  projectName: string;
  groups: Group[];
  collapsedGroupIds: Set<string>;
  fileName: string;
  fileNameEdited: boolean;
  chartBar: boolean;
  chartPie: boolean;
  // null = este pacote representa o projeto inteiro; string = representa só
  // esse pacote de trabalho — vira uma marca oculta no .xlsx gerado (ver
  // generator.py), pro Painel de Gerência não marcar o projeto inteiro como
  // "Enviado" quando só 1 pacote foi mandado por e-mail.
  pacoteScope: string | null;
  // idioma dos rótulos fixos do arquivo gerado pra ESTE pacote — "pt" por
  // padrão, vira "en" quando o botão "EN" do preview traduz esse pacote
  // (nomes de grupo + descrições de atividade via IA, e os rótulos fixos —
  // título, "Bruto"/"Performance", "Total de horas..." — no backend, ver
  // generator._LABELS). Undo reverte junto (é campo do pacote, entra no
  // snapshot igual a tudo mais).
  language: "pt" | "en";
};

export type RowIssue = {
  row: number;
  reason: string;
  message: string;
  // valor bruto da linha descartada, quando confiável (ver backend
  // `RowIssue`/`ValidationBanner`) — permite oferecer "Adicionar como
  // atividade" sem o usuário precisar redigitar o que já se sabe.
  raw_hours: number | null;
  raw_description: string | null;
};

export type ReportHeader = {
  locationDate: string;
  monthLabel: string;
  signer1Name: string;
  signer1Company: string;
  signer2Name: string;
  signer2Company: string;
};

export type ParseResponse = {
  packages: Array<{
    key: string;
    project_name: string;
    groups: Array<{
      name: string;
      total_hours: number;
      activities: Array<{ description: string; hours: number }>;
    }>;
  }>;
  issues: RowIssue[];
};

export type GeneratePackagePayload = {
  header: {
    project_code: string;
    project_name: string;
    location_date: string;
    month_label: string;
    signer1_name: string;
    signer1_company: string;
    signer2_name: string;
    signer2_company: string;
  };
  groups: Array<{
    name: string;
    performance: number;
    activities: Array<{ description: string; hours: number | null }>;
  }>;
  file_name?: string;
};

export type ChatStatePayload = {
  packages: Array<{
    key: string;
    projectCode: string;
    projectName: string;
    groups: Array<{
      name: string;
      performance: number;
      activities: Array<{ description: string; hours: number | null }>;
    }>;
  }>;
  activePackageIndex: number;
  locationDate: string;
  monthLabel: string;
  signer1Name: string;
  signer1Company: string;
  signer2Name: string;
  signer2Company: string;
};
