import { useEffect, useState } from "react";
import { parseExtraHoursInput } from "../utils/fmt";

type Props = {
  value: number | null;
  className?: string;
  placeholder?: string;
  readOnly?: boolean;
  onFocus?: () => void;
  onCommit: (v: number | null) => void;
  onBlur?: () => void;
};

// Um input controlado "de verdade" (value = String(número)) reformataria o
// texto a cada tecla, o que apaga o "," que o usuário acabou de digitar antes
// dele conseguir digitar a casa decimal (ex: "0,5" vira só "0"). Guarda o
// texto exato digitado em estado local, só ressincronizando com o valor
// externo (undo, chat, mesclar grupo, etc) quando ele muda por um motivo que
// NÃO foi essa mesma digitação.
export function ExtraHoursInput({ value, className, placeholder, readOnly, onFocus, onCommit, onBlur }: Props) {
  const [raw, setRaw] = useState(value === null ? "" : String(value));

  useEffect(() => {
    if (parseExtraHoursInput(raw) !== value) {
      setRaw(value === null ? "" : String(value));
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  return (
    <input
      className={className}
      type="text"
      value={raw}
      placeholder={placeholder ?? "horas"}
      readOnly={readOnly}
      onFocus={onFocus}
      onBlur={onBlur}
      onChange={(e) => {
        setRaw(e.target.value);
        onCommit(parseExtraHoursInput(e.target.value));
      }}
    />
  );
}
