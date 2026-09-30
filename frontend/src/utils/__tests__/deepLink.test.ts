import { describe, expect, it } from "vitest";
import { BASE_TITLE, parseDeepLink, titleWithPending } from "../deepLink";

describe("titleWithPending", () => {
  it("sem pendência devolve o título base", () => {
    expect(titleWithPending(null)).toBe(BASE_TITLE);
    expect(titleWithPending({ to_review: 0, awaiting_approval: 0 })).toBe(BASE_TITLE);
  });

  it("soma revisões e aprovações no contador", () => {
    expect(titleWithPending({ to_review: 2, awaiting_approval: 3 })).toBe(`(5) ${BASE_TITLE}`);
    expect(titleWithPending({ to_review: 1, awaiting_approval: null })).toBe(`(1) ${BASE_TITLE}`);
  });
});

describe("parseDeepLink", () => {
  it("lê view e report válidos", () => {
    expect(parseDeepLink("?view=my-reviews&report=R1")).toEqual({ view: "my-reviews", reportId: "R1" });
    expect(parseDeepLink("?view=auto-generation&report=R1")).toEqual({ view: "auto-generation", reportId: "R1" });
  });

  it("ignora view desconhecida e report vazio", () => {
    expect(parseDeepLink("?view=hack&report=")).toEqual({ view: null, reportId: null });
    expect(parseDeepLink("")).toEqual({ view: null, reportId: null });
  });
});
