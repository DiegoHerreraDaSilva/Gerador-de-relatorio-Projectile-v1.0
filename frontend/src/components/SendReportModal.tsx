import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { X, Send, Check, AlertTriangle } from "lucide-react";
import { useAuthStore } from "../store/useAuthStore";
import { useReportStore } from "../store/useReportStore";
import { computeDefaultFileNameFor } from "../utils/fileName";
import { drawGroupsChart } from "../utils/chart";
import { FormatCheckboxes, type ReportFormat } from "./FormatCheckboxes";
import type { WorkPackage, ReportHeader } from "../api/types";

function chartPng(groups: WorkPackage["groups"], type: "bar" | "pie"): string {
  const canvas = document.createElement("canvas");
  drawGroupsChart(canvas, groups, type);
  return canvas.toDataURL("image/png").replace(/^data:image\/png;base64,/, "");
}

type SendStatus = "idle" | "sending" | "sent" | "error";

export function SendReportModal({ onClose }: { onClose: () => void }) {
  const user = useAuthStore((s) => s.user);
  const packages = useReportStore((s) => s.packages);
  const header = useReportStore((s) => s.header);

  const [selected, setSelected] = useState<Set<string>>(() => new Set(packages.length === 1 ? [packages[0].id] : []));
  const [oneEmail, setOneEmail] = useState(true);
  const [formats, setFormats] = useState<Set<ReportFormat>>(() => new Set(["xlsx"]));
  const [to, setTo] = useState("");
  const [subject, setSubject] = useState("");
  const [message, setMessage] = useState("");
  const [subjectEdited, setSubjectEdited] = useState(false);
  const [messageEdited, setMessageEdited] = useState(false);
  const [statusByPackage, setStatusByPackage] = useState<Record<string, { status: SendStatus; error?: string }>>({});
  const [batchError, setBatchError] = useState("");
  const [sending, setSending] = useState(false);

  // Esc fecha o modal — convenção padrão de teclado, igual clicar fora ou no
  // X. Trava enquanto `sending` (mesma condição que já desabilita o botão
  // "Cancelar"), pra não abandonar um envio no meio.
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape" && !sending) onClose();
    };
    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, [sending, onClose]);

  // assunto/mensagem padrão recalculados enquanto o usuário não editar à mão —
  // muda conforme a seleção (nome do projeto some do texto se tiver mais de
  // um pacote marcado, já que um só assunto vai valer pros dois e-mails).
  useEffect(() => {
    const selectedPkgs = packages.filter((p) => selected.has(p.id));
    const projectPart = selectedPkgs.length === 1 ? ` - ${selectedPkgs[0].projectName}` : "";
    if (!subjectEdited) setSubject(`Relatório de Horas${projectPart} - ${header.monthLabel}`);
    if (!messageEdited) {
      setMessage(
        selectedPkgs.length > 1
          ? `Segue em anexo o relatório de horas referente a ${header.monthLabel}.`
          : `Segue em anexo o relatório de horas${selectedPkgs[0] ? ` do projeto ${selectedPkgs[0].projectName}` : ""} referente a ${header.monthLabel}.`
      );
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selected]);

  const togglePackage = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const buildPackagePayload = (pkg: WorkPackage, h: ReportHeader) => ({
    header: {
      project_code: pkg.projectCode,
      project_name: pkg.projectName,
      location_date: h.locationDate,
      month_label: h.monthLabel,
      signer1_name: h.signer1Name,
      signer1_company: h.signer1Company,
      signer2_name: h.signer2Name,
      signer2_company: h.signer2Company,
    },
    groups: pkg.groups.map((g) => ({
      name: g.name,
      performance: g.performance,
      activities: g.activities.map((a) => ({ description: a.description, hours: a.hours })),
    })),
    file_name: packages.length > 1 ? (pkg.fileNameEdited ? pkg.fileName : computeDefaultFileNameFor(pkg, h.monthLabel)) : undefined,
    chart_image_bar: pkg.chartBar ? chartPng(pkg.groups, "bar") : undefined,
    chart_image_pie: pkg.chartPie ? chartPng(pkg.groups, "pie") : undefined,
    pacote_scope: pkg.pacoteScope,
  });

  const sendOne = async (pkgs: WorkPackage[]) => {
    const res = await fetch("/send-report", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        packages: pkgs.map((pkg) => buildPackagePayload(pkg, header)),
        to: to.trim(),
        subject,
        message,
        formats: Array.from(formats),
      }),
    });
    if (!res.ok) {
      const detail = await res.text().catch(() => "");
      throw new Error(detail || `Erro ${res.status}`);
    }
  };

  const handleSend = async () => {
    const selectedPkgs = packages.filter((p) => selected.has(p.id));
    if (selectedPkgs.length === 0 || !to.trim()) return;

    const missingCode = selectedPkgs.find((pkg) => !pkg.projectCode.trim());
    if (missingCode) {
      setBatchError(`Preencha o número do relatório (SE.XX.XXX) de "${missingCode.projectName}" antes de enviar.`);
      return;
    }
    if (!header.signer1Name.trim() || !header.signer2Name.trim()) {
      setBatchError("Preencha o nome de quem assina (Schwaben e cliente) antes de enviar.");
      return;
    }

    setSending(true);
    setBatchError("");

    // um só e-mail com todos os anexos, ou um e-mail separado por pacote —
    // escolha do usuário (checkbox "Enviar tudo num só e-mail").
    if (oneEmail && selectedPkgs.length > 1) {
      setStatusByPackage(Object.fromEntries(selectedPkgs.map((p) => [p.id, { status: "sending" as SendStatus }])));
      try {
        await sendOne(selectedPkgs);
        setStatusByPackage(Object.fromEntries(selectedPkgs.map((p) => [p.id, { status: "sent" as SendStatus }])));
      } catch (err) {
        const errMsg = err instanceof Error ? err.message : String(err);
        setBatchError(errMsg);
        setStatusByPackage(
          Object.fromEntries(selectedPkgs.map((p) => [p.id, { status: "error" as SendStatus, error: errMsg }]))
        );
      }
    } else {
      for (const pkg of selectedPkgs) {
        setStatusByPackage((prev) => ({ ...prev, [pkg.id]: { status: "sending" } }));
        try {
          await sendOne([pkg]);
          setStatusByPackage((prev) => ({ ...prev, [pkg.id]: { status: "sent" } }));
        } catch (err) {
          setStatusByPackage((prev) => ({
            ...prev,
            [pkg.id]: { status: "error", error: err instanceof Error ? err.message : String(err) },
          }));
        }
      }
    }
    setSending(false);
  };

  const selectedCount = selected.size;
  const allSent = selectedCount > 0 && [...selected].every((id) => statusByPackage[id]?.status === "sent");

  return createPortal(
    <div className="modal-backdrop" onClick={onClose}>
      <div className="modal-card send-report-modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <h2>Enviar Relatório</h2>
          <button type="button" className="modal-close" onClick={onClose} aria-label="Fechar">
            <X size={18} strokeWidth={2} />
          </button>
        </div>

        <div className="modal-body">
        <p className="muted send-report-sender">
          Enviando como <strong>{user?.email || "—"}</strong> · cópia automática pra{" "}
          <strong>agente.reunioes@schwaben.com.br</strong>
        </p>

        {allSent && (
          <p className="send-report-success">
            <Check size={16} strokeWidth={2.5} />
            {selectedCount > 1
              ? oneEmail
                ? "Relatórios enviados com sucesso, num único e-mail!"
                : "Relatórios enviados com sucesso, um e-mail por relatório!"
              : "Relatório enviado com sucesso!"}
          </p>
        )}

        {batchError && <p className="send-report-bad">{batchError}</p>}

        {packages.length > 1 && (
          <div className="send-report-packages">
            <span className="mgmt-filter-label">Relatórios a enviar</span>
            {packages.map((pkg) => {
              const st = statusByPackage[pkg.id];
              return (
                <label key={pkg.id} className="send-report-package-option">
                  <input
                    type="checkbox"
                    checked={selected.has(pkg.id)}
                    onChange={() => togglePackage(pkg.id)}
                    disabled={sending}
                  />
                  <span>{pkg.projectName}</span>
                  {st?.status === "sending" && <span className="muted">enviando...</span>}
                  {st?.status === "sent" && <Check size={15} className="send-report-ok" />}
                  {st?.status === "error" && (
                    <span title={st.error}>
                      <AlertTriangle size={15} className="send-report-bad" />
                    </span>
                  )}
                </label>
              );
            })}
          </div>
        )}

        {selectedCount > 1 && (
          <label className="send-report-one-email">
            <input type="checkbox" checked={oneEmail} onChange={(e) => setOneEmail(e.target.checked)} disabled={sending} />
            <span>Enviar tudo num só e-mail (cada relatório vira um anexo separado, sem zip)</span>
          </label>
        )}

        <label className="send-report-field">
          <span>Formato</span>
          <FormatCheckboxes value={formats} onChange={setFormats} disabled={sending} />
        </label>

        <label className="send-report-field">
          <span>Destinatário</span>
          <input
            type="email"
            placeholder="cliente@empresa.com"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            disabled={sending}
          />
        </label>

        <label className="send-report-field">
          <span>Assunto</span>
          <input
            type="text"
            value={subject}
            onChange={(e) => {
              setSubject(e.target.value);
              setSubjectEdited(true);
            }}
            disabled={sending}
          />
        </label>

        <label className="send-report-field">
          <span>Mensagem</span>
          <textarea
            rows={4}
            value={message}
            onChange={(e) => {
              setMessage(e.target.value);
              setMessageEdited(true);
            }}
            disabled={sending}
          />
        </label>

        {packages.length === 1 && statusByPackage[packages[0].id]?.status === "error" && (
          <p className="send-report-bad">{statusByPackage[packages[0].id].error}</p>
        )}
        </div>

        <div className="modal-actions">
          <button type="button" className="btn-secondary" onClick={onClose} disabled={sending}>
            {allSent ? "Fechar" : "Cancelar"}
          </button>
          <button
            type="button"
            className="primary"
            onClick={handleSend}
            disabled={sending || selectedCount === 0 || !to.trim() || !subject.trim()}
          >
            <Send size={14} strokeWidth={2} />
            {sending ? "Enviando..." : `Enviar${selectedCount > 1 ? ` (${selectedCount})` : ""}`}
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
