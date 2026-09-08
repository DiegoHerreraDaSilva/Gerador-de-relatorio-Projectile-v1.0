import { useEffect, useState } from "react";
import { parseLocaleNumber } from "../utils/fmt";

type Props = {
  value: number;
  className?: string;
  onFocus?: () => void;
  onCommit: (v: number) => void;
};

// Mesmo problema do `ExtraHoursInput.tsx`: um input controlado direto pelo
// número (value={performance}) reformata o texto a cada tecla, o que apaga o
// separador decimal ("," ou ".") antes do usuário conseguir digitar a casa
// decimal (ex: "1,5" perdia a vírgula no meio da digitação). Guarda o texto
// exato em estado local, só ressincronizando com o valor externo (undo, chat,
// mesclar grupo, etc) quando ele muda por um motivo que NÃO foi essa mesma
// digitação.
export function PerformanceInput({ value, className, onFocus, onCommit }: Props) {
  const [raw, setRaw] = useState(String(value));

  useEffect(() => {
    if ((parseLocaleNumber(raw) || 0) !== value) {
      setRaw(String(value));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <input
      className={className}
      type="text"
      value={raw}
      onFocus={onFocus}
      onChange={(e) => {
        setRaw(e.target.value);
        onCommit(parseLocaleNumber(e.target.value) || 0);
      }}
    />
  );
}
