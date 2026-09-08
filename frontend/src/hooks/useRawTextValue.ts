import { useEffect, useState } from "react";

/** Um input controlado "de verdade" (value = String(número)) reformataria o
 * texto a cada tecla, o que apaga o separador decimal ("," ou ".") antes do
 * usuário conseguir digitar a casa decimal (ex: "0,5" vira só "0"). Guarda o
 * texto exato digitado em estado local, só ressincronizando com o valor
 * externo (undo, chat, mesclar grupo, etc) quando ele muda por um motivo que
 * NÃO foi essa mesma digitação — compartilhado por `ExtraHoursInput`
 * (horas de atividade extra, `number | null`) e `PerformanceInput`
 * (performance do grupo, `number`). */
export function useRawTextValue<T>(value: T, format: (v: T) => string, parse: (raw: string) => T) {
  const [raw, setRaw] = useState(() => format(value));

  useEffect(() => {
    if (parse(raw) !== value) setRaw(format(value));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return {
    raw,
    setRaw,
    parse,
  };
}
