/** Tabela que o servidor formata em .xlsx (`POST /analytics/chat/export`, só gerente): não consulta nada, só
 * formata o que o navegador já tem. `column_types`: hours | percent | count | ms | text (número continua número
 * no Excel). `percent` espera o valor em pontos percentuais (12,3 vira "12,3%"). */
export type ExportableTable = {
  title: string;
  columns: string[];
  column_types?: string[] | null;
  rows: (string | number | null)[][];
  totals?: (string | number | null)[] | null;
};

/** Baixa a tabela como Excel. Levanta com mensagem pronta pra tela se o servidor recusar. */
export async function downloadXlsx(table: ExportableTable): Promise<void> {
  const res = await fetch("/analytics/chat/export", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      title: table.title,
      columns: table.columns,
      column_types: table.column_types ?? null,
      rows: table.rows,
      totals: table.totals ?? null,
    }),
  });
  if (!res.ok) throw new Error(res.status === 401 ? "Sessão expirada" : "Falha ao gerar o Excel");
  const blob = await res.blob();
  const disposition = res.headers.get("content-disposition") ?? "";
  const name = /filename="([^"]+)"/.exec(disposition)?.[1] ?? "tabela.xlsx";
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
