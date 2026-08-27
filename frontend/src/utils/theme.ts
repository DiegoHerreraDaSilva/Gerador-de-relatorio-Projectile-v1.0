export const THEME_ICONS = {
  sun: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" aria-hidden="true"><circle cx="12" cy="12" r="4.4"/><path d="M12 3v1.8M12 19.2V21M3 12h1.8M19.2 12H21M5.3 5.3l1.3 1.3M17.4 17.4l1.3 1.3M18.7 5.3l-1.3 1.3M6.6 17.4l-1.3 1.3"/></svg>',
  moon: '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M15.2 5.2A7.2 7.2 0 1 0 18.9 17 5.6 5.6 0 1 1 15.2 5.2Z"/></svg>',
};

export type Theme = "light" | "dark";

export function getInitialTheme(): Theme {
  const saved = localStorage.getItem("theme") as Theme | null;
  if (saved === "light" || saved === "dark") return saved;
  return window.matchMedia("(prefers-color-scheme: light)").matches ? "light" : "dark";
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("theme", theme);
}
