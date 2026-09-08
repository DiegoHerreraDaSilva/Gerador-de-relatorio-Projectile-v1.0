import { parseExtraHoursInput } from "../utils/fmt";
import { useRawTextValue } from "../hooks/useRawTextValue";

type Props = {
  value: number | null;
  className?: string;
  placeholder?: string;
  readOnly?: boolean;
  onFocus?: () => void;
  onCommit: (v: number | null) => void;
  onBlur?: () => void;
};

export function ExtraHoursInput({ value, className, placeholder, readOnly, onFocus, onCommit, onBlur }: Props) {
  const { raw, setRaw, parse } = useRawTextValue(value, (v) => (v === null ? "" : String(v)), parseExtraHoursInput);

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
        onCommit(parse(e.target.value));
      }}
    />
  );
}
