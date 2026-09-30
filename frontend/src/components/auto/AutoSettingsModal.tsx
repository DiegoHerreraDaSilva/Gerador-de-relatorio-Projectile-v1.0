import { useEffect, useMemo, useState } from "react";
import { useModal } from "../../hooks/useModal";
import { createPortal } from "react-dom";
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
import { FormatCheckboxes, ReportFormat } from "../FormatCheckboxes";
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
import { describeSchedule, formatScheduleAt } from "../../utils/autoSchedule";
import { Select } from "../Select";
import { MODE_LABELS } from "./format";

/** Padrão geral — o que vale pra todo projeto sem configuração própria. */
export function AutoSettingsModal({ onClose }: { onClose: () => void }) {
  const modalRef = useModal({ onClose });
  const config = useAutoGenerationStore((s) => s.config);
  const schedule = useAutoGenerationStore((s) => s.schedule);
  const loadConfig = useAutoGenerationStore((s) => s.loadConfig);
  const saveConfig = useAutoGenerationStore((s) => s.saveConfig);
  const refresh = useAutoGenerationStore((s) => s.refresh);
  const [form, setForm] = useState<Record<string, unknown> | null>(null);
  const [status, setStatus] = useState("");

  useEffect(() => {
    void loadConfig().catch((e) => setStatus(e instanceof Error ? e.message : String(e)));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  useEffect(() => {
    if (config && !form) setForm({ ...config.effective });
  }, [config, form]);

  const field = (key: string) => (form?.[key] as string | undefined) ?? "";
  const setField = (key: string, value: unknown) => setForm((f) => ({ ...(f ?? {}), [key]: value }));
  const formats = (form?.formats as string[] | undefined) ?? ["xlsx"];

  const save = async () => {
    setStatus("Salvando...");
    try {
      await saveConfig(form ?? {});
      await refresh();
      setStatus("Padrão salvo. Vale pros próximos rascunhos de todo projeto sem configuração própria.");
    } catch (e) {
      setStatus(e instanceof Error ? e.message : String(e));
    }
  };

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div
        ref={modalRef}
        tabIndex={-1}
        className="modal-card auto-settings-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="auto-settings-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="modal-head">
          <h2 id="auto-settings-title">Padrão geral da geração automática</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Fechar">
            <X size={18} strokeWidth={2} />
          </button>
        </div>
        <div className="modal-body">
          {!form && <p className="muted">Carregando...</p>}
          {form && (
            <section className="auto-settings-section">
              <p className="muted">
                Vale pra todo projeto que não tiver configuração própria (botão “Configuração” em cada projeto).
              </p>
              <div className="auto-settings-grid">
                <label>
                  Relatório
                  <Select
                    ariaLabel="Relatório"
                    value={field("mode") || "projeto"}
                    onChange={(v) => setField("mode", v)}
                    options={[
                      { value: "projeto", label: MODE_LABELS.projeto },
                      { value: "pacote", label: MODE_LABELS.pacote },
                    ]}
                  />
                </label>
                <label>
                  Local da data
                  <input type="text" value={field("location")} onChange={(e) => setField("location", e.target.value)} />
                </label>
                <label>
                  Assinante Schwaben
                  <input
                    type="text"
                    value={field("signer1_name")}
                    onChange={(e) => setField("signer1_name", e.target.value)}
                    placeholder="Nome de quem assina"
                  />
                </label>
                <label>
                  Empresa
                  <input
                    type="text"
                    value={field("signer1_company")}
                    onChange={(e) => setField("signer1_company", e.target.value)}
                  />
                </label>
                <label>
                  Assinante do cliente
                  <input
                    type="text"
                    value={field("signer2_name")}
                    onChange={(e) => setField("signer2_name", e.target.value)}
                    placeholder="Nome de quem assina"
                  />
                </label>
                <label>
                  Empresa do cliente
                  <input
                    type="text"
                    value={field("signer2_company")}
                    onChange={(e) => setField("signer2_company", e.target.value)}
                  />
                </label>
                {config?.effective.number_model != null ? (
                  <label>
                    Modelo do número
                    <input
                      type="text"
                      value={field("number_model")}
                      onChange={(e) => setField("number_model", e.target.value)}
                      spellCheck={false}
                      placeholder="SE.##.###"
                    />
                    <span className="auto-field-hint"># = um dígito. “SE.##.###” aceita SE.26.053.</span>
                  </label>
                ) : (
                  <label>
                    Formato do número (avançado)
                    <input
                      type="text"
                      value={field("number_pattern")}
                      onChange={(e) => setField("number_pattern", e.target.value)}
                      spellCheck={false}
                    />
                    <span className="auto-field-hint">Regra escrita à mão (expressão regular).</span>
                  </label>
                )}
                {/* mesmos cartões do rodapé de "Gerar relatório" (Excel/PDF) */}
                <div className="auto-settings-files" role="group" aria-labelledby="auto-settings-files-label">
                  <span id="auto-settings-files-label" className="auto-settings-files-label">
                    Arquivos
                  </span>
                  <div className="auto-settings-files-row">
                    <FormatCheckboxes
                      value={new Set(formats as ReportFormat[])}
                      onChange={(next) => setField("formats", Array.from(next))}
                    />
                  </div>
                </div>
              </div>
              <p className="muted">Assinantes em branco usam os do último relatório aprovado de cada projeto.</p>
              <div className="auto-schedule-block">
                <h3>Geração automática do mês</h3>
                <p className="muted">
                  No dia e na hora escolhidos (horário de São Paulo), o sistema gera sozinho os rascunhos do mês que
                  fechou, junto com os pedidos da geração personalizada. Só gera rascunhos: nada é enviado.
                </p>
                <label className="auto-schedule-toggle">
                  <input
                    type="checkbox"
                    checked={form.schedule_enabled !== false}
                    onChange={(e) => setField("schedule_enabled", e.target.checked)}
                  />
                  <span>Gerar automaticamente todo mês</span>
                </label>
                <div className="auto-schedule-fields">
                  <label>
                    Dia do mês
                    <Select
                      ariaLabel="Dia do mês"
                      value={String(form.schedule_day ?? 1)}
                      disabled={form.schedule_enabled === false}
                      onChange={(v) => setField("schedule_day", Number(v))}
                      options={Array.from({ length: 28 }, (_, i) => ({ value: String(i + 1), label: String(i + 1) }))}
                    />
                  </label>
                  <label>
                    Hora
                    <input
                      type="time"
                      value={field("schedule_time") || "06:00"}
                      disabled={form.schedule_enabled === false}
                      onChange={(e) => setField("schedule_time", e.target.value)}
                    />
                  </label>
                </div>
                {schedule && (
                  <p className="auto-schedule-next" role="status">
                    <CalendarClock size={15} strokeWidth={2} aria-hidden="true" /> {describeSchedule(schedule)}
                  </p>
                )}
              </div>
              <div className="auto-schedule-block">
                <h3>Avisos por e-mail</h3>
                <p className="muted">
                  Enviados pelo Microsoft Graph: o revisor recebe quando um relatório é atribuído a ele ou devolvido com
                  comentário; os gerentes recebem quando um relatório fica aguardando aprovação. O destinatário vem do
                  cadastro do Projectile.
                </p>
                <label className="auto-schedule-toggle">
                  <input
                    type="checkbox"
                    checked={form.notify_email !== false}
                    onChange={(e) => setField("notify_email", e.target.checked)}
                  />
                  <span>Avisar por e-mail</span>
                </label>
              </div>
            </section>
          )}
          {status && (
            <p className="muted" role="status">
              {status}
            </p>
          )}
        </div>
        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose}>
            Fechar
          </button>
          <button type="button" className="primary" onClick={() => void save()} disabled={!form}>
            Salvar padrão
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
