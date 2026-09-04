import { useEffect, useRef } from "react";
import type { RefObject } from "react";

// Fecha algo (ex: dropdown) quando um clique cai fora do elemento referenciado.
// O listener só fica anexado enquanto `enabled` for true, espelhando o
// comportamento anterior de cada dropdown (que só ouvia mousedown enquanto aberto).
export function useClickOutside(
  refs: RefObject<HTMLElement> | RefObject<HTMLElement>[],
  onOutsideClick: () => void,
  enabled: boolean = true
) {
  const callbackRef = useRef(onOutsideClick);
  useEffect(() => {
    callbackRef.current = onOutsideClick;
  });
  // guarda a lista de refs atual sem entrar nas deps do efeito abaixo — um
  // array literal `[a, b]` passado inline mudaria de identidade a cada
  // render e reanexaria o listener sem necessidade.
  const refsRef = useRef(refs);
  refsRef.current = refs;

  useEffect(() => {
    if (!enabled) return;
    const onOutside = (e: MouseEvent) => {
      // aceita 2+ refs (ex: trigger + lista renderizada via portal, fora da
      // subárvore do trigger no DOM) — só fecha se o clique cair fora de TODAS.
      const refList = Array.isArray(refsRef.current) ? refsRef.current : [refsRef.current];
      const inside = refList.some((r) => r.current && r.current.contains(e.target as Node));
      if (!inside) callbackRef.current();
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [enabled]);
}
