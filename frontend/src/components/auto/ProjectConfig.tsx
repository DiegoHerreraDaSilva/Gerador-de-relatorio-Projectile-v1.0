import { useEffect, useMemo, useState } from "react";
import {
  CalendarClock,
  ChevronDown,
  Download,
  FilePen,
  Play,
  Plus,
  RefreshCw,
  RotateCcw,
  Search,
  Settings,
  SkipForward,
  SlidersHorizontal,
  Send,
  Trash2,
  Undo2,
  UserRound,
  X,
} from "lucide-react";
import {
  CUSTOM_KEY,
  EDITABLE_STATUSES,
  useAutoGenerationStore,
  AutoItem,
  AutoStatus,
  CustomConfigValues,
  CustomRequestItem,
  CustomUnit,
  EffectiveConfig,
  PreviewProject,
  ProjectRule,
} from "../../store/useAutoGenerationStore";
import { Select } from "../Select";
import { MODE_LABELS } from "./format";

/** Configuração individual do projeto — só o que difere do padrão geral
 * (campo vazio = usa o padrão). Guardada pela família: vale também nos
 * próximos meses do mesmo trabalho ("… Estribo 08.2026" → "… 09.2026"). */
export function ProjectConfig({
  familyKey,
  rule,
  effective,
  item,
  onRegenerate,
  custom,
}: {
  familyKey: string;
  rule: ProjectRule;
  effective: EffectiveConfig;
  item?: AutoItem;
  onRegenerate?: () => void;
  // configuração PRÓPRIA de um personalizado (pedido agendado ou já gerado): sem "Gerar relatório
  // deste projeto", "Relatório" = o `package_unit`, e o que fica em branco herda o projeto e, sem ele, o padrão geral
  custom?: { unit: CustomUnit; onSave: (form: ProjectRule) => Promise<void>; savedMessage: string };
}) {
  const saveRule = useAutoGenerationStore((s) => s.saveRule);
  const [form, setForm] = useState<ProjectRule>(rule ?? {});
  const [status, setStatus] = useState("");
  const [saved, setSaved] = useState(false);
  useEffect(() => setForm(rule ?? {}), [rule]);

  const set = <K extends keyof ProjectRule>(key: K, value: ProjectRule[K] | undefined) =>
    setForm((f) => {
      const next = { ...f };
      if (value === undefined || value === "") delete next[key];
      else next[key] = value;
      return next;
    });
  // o que vale sem a regra deste projeto (pra mostrar o "Padrão: …")
  const inherited = (key: keyof ProjectRule) => (rule && key in rule ? undefined : effective[key]);
  const placeholder = (key: "signer1_name" | "signer1_company" | "signer2_name" | "signer2_company") => {
    const value = inherited(key) as string | undefined;
    if (custom) return value ? `Do projeto ou padrão: ${value}` : "Do projeto ou do padrão geral";
    return value ? `Padrão: ${value}` : key.endsWith("name") ? "Padrão: último relatório aprovado" : "Padrão";
  };
  const fallback = custom ? "Do projeto ou padrão" : "Padrão";
  const formatsValue = form.formats ? form.formats.slice().sort().join("+") : "";

  const save = async () => {
    setStatus("Salvando...");
    try {
      if (custom) {
        await custom.onSave(form);
        setStatus(custom.savedMessage);
      } else {
        await saveRule(familyKey, form);
        setStatus("Salvo. Vale pros próximos rascunhos deste projeto, inclusive nos próximos meses.");
      }
      setSaved(true);
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  };

  return (
    <div className="auto-config">
      <div className="auto-config-grid">
        {custom ? (
          <p className="auto-field-hint auto-config-hint">
            Campo em branco: vale a configuração do projeto e, sem ela, o padrão geral.
          </p>
        ) : (
          <label className="include-performance-checkbox auto-config-enabled">
            <input
              type="checkbox"
              checked={form.enabled !== false}
              onChange={(e) => set("enabled", e.target.checked ? undefined : false)}
            />
            <span>Gerar relatório deste projeto</span>
          </label>
        )}
        <label>
          Relatório
          <Select
            ariaLabel="Relatório"
            value={custom ? (form.mode ?? custom.unit) : (form.mode ?? "")}
            onChange={(v) => set("mode", (v || undefined) as ProjectRule["mode"])}
            options={[
              ...(custom
                ? []
                : [
                    {
                      value: "",
                      label: `Padrão (${MODE_LABELS[(inherited("mode") as "projeto" | "pacote") ?? "projeto"] ?? "—"})`,
                    },
                  ]),
              { value: "projeto", label: MODE_LABELS.projeto },
              { value: "pacote", label: MODE_LABELS.pacote },
            ]}
          />
        </label>
        <label>
          Arquivos
          <Select
            ariaLabel="Arquivos"
            value={formatsValue}
            onChange={(v) => set("formats", v ? (v.split("+") as Array<"xlsx" | "pdf">) : undefined)}
            options={[
              {
                value: "",
                label: `${fallback} (${((inherited("formats") as string[] | undefined) ?? ["xlsx"]).map((f) => f.toUpperCase()).join(" + ")})`,
              },
              { value: "xlsx", label: "XLSX" },
              { value: "pdf", label: "PDF" },
              { value: "pdf+xlsx", label: "XLSX + PDF" },
            ]}
          />
        </label>
        <label>
          Assinante Schwaben
          <input
            type="text"
            value={form.signer1_name ?? ""}
            placeholder={placeholder("signer1_name")}
            onChange={(e) => set("signer1_name", e.target.value)}
          />
        </label>
        <label>
          Empresa
          <input
            type="text"
            value={form.signer1_company ?? ""}
            placeholder={placeholder("signer1_company")}
            onChange={(e) => set("signer1_company", e.target.value)}
          />
        </label>
        <label>
          Assinante do cliente
          <input
            type="text"
            value={form.signer2_name ?? ""}
            placeholder={placeholder("signer2_name")}
            onChange={(e) => set("signer2_name", e.target.value)}
          />
        </label>
        <label>
          Empresa do cliente
          <input
            type="text"
            value={form.signer2_company ?? ""}
            placeholder={placeholder("signer2_company")}
            onChange={(e) => set("signer2_company", e.target.value)}
          />
        </label>
      </div>
      <div className="auto-config-actions">
        {status && (
          <span className="muted" role="status">
            {status}
          </span>
        )}
        {saved && onRegenerate && item && (
          <button type="button" className="btn-secondary" onClick={onRegenerate}>
            <RefreshCw size={14} strokeWidth={2} /> Regenerar este rascunho com a configuração nova
          </button>
        )}
        <button
          type="button"
          className="btn-secondary"
          onClick={() => setForm({})}
          disabled={!Object.keys(form).length}
        >
          Voltar ao padrão
        </button>
        <button type="button" className="primary" onClick={() => void save()}>
          Salvar configuração
        </button>
      </div>
    </div>
  );
}
