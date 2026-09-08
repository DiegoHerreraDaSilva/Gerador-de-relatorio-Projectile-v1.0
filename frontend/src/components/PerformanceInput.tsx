import { parseLocaleNumber } from "../utils/fmt";
import { useRawTextValue } from "../hooks/useRawTextValue";

type Props = {
  value: number;
  className?: string;
  onFocus?: () => void;
  onCommit: (v: number) => void;
};

export function PerformanceInput({ value, className, onFocus, onCommit }: Props) {
  const { raw, setRaw, parse } = useRawTextValue(value, String, (r) => parseLocaleNumber(r) || 0);

  return (
    <input
      className={className}
      type="text"
      value={raw}
      onFocus={onFocus}
      onChange={(e) => {
        setRaw(e.target.value);
        onCommit(parse(e.target.value));
      }}
    />
  );
}
