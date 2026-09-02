import { useEffect, useRef } from "react";
import type { RefObject } from "react";

// Fecha algo (ex: dropdown) quando um clique cai fora do elemento referenciado.
// O listener só fica anexado enquanto `enabled` for true, espelhando o
// comportamento anterior de cada dropdown (que só ouvia mousedown enquanto aberto).
export function useClickOutside(
  ref: RefObject<HTMLElement>,
  onOutsideClick: () => void,
  enabled: boolean = true
) {
  const callbackRef = useRef(onOutsideClick);
  useEffect(() => {
    callbackRef.current = onOutsideClick;
  });

  useEffect(() => {
    if (!enabled) return;
    const onOutside = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) callbackRef.current();
    };
    document.addEventListener("mousedown", onOutside);
    return () => document.removeEventListener("mousedown", onOutside);
  }, [enabled, ref]);
}
