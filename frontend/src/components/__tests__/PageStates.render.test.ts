import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { createElement } from "react";
import { EmptyState, ErrorState, LoadingState } from "../PageStates";

/** Os três estados de tela renderizam o que importa (HTML estático, sem navegador). */
describe("PageStates", () => {
  it("vazio: título, descrição e a próxima ação quando existe", () => {
    const html = renderToStaticMarkup(
      createElement(EmptyState, {
        title: "Nenhum relatório no histórico ainda",
        description: "Eles aparecem aqui quando forem gerados.",
        action: { label: "Limpar busca", onClick: () => {} },
      }),
    );
    expect(html).toContain("Nenhum relatório no histórico ainda");
    expect(html).toContain("Eles aparecem aqui quando forem gerados.");
    expect(html).toContain("Limpar busca");
  });

  it("vazio sem ação não desenha botão nenhum", () => {
    const html = renderToStaticMarkup(createElement(EmptyState, { title: "Nada por aqui" }));
    expect(html).not.toContain("<button");
  });

  it("erro: é um alerta e só oferece 'Tentar de novo' se houver o que refazer", () => {
    const withRetry = renderToStaticMarkup(createElement(ErrorState, { message: "Falhou", onRetry: () => {} }));
    expect(withRetry).toContain('role="alert"');
    expect(withRetry).toContain("Falhou");
    expect(withRetry).toContain("Tentar de novo");
    const without = renderToStaticMarkup(createElement(ErrorState, { message: "Falhou" }));
    expect(without).not.toContain("Tentar de novo");
  });

  it("erro em nova tentativa desabilita o botão", () => {
    const html = renderToStaticMarkup(createElement(ErrorState, { message: "x", onRetry: () => {}, busy: true }));
    expect(html).toContain("disabled");
  });

  it("carregando: aria-busy, rótulo só para leitor de tela e N linhas de esqueleto", () => {
    const html = renderToStaticMarkup(createElement(LoadingState, { label: "Carregando relatórios...", rows: 3 }));
    expect(html).toContain('aria-busy="true"');
    expect(html).toContain("sr-only");
    expect(html).toContain("Carregando relatórios...");
    expect(html.match(/skel-line/g)).toHaveLength(3);
  });
});
