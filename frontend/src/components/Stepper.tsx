import { useReportStore } from "../store/useReportStore";

export function Stepper() {
  const packages = useReportStore((s) => s.packages);
  const header = useReportStore((s) => s.header);
  const hasGeneratedOnce = useReportStore((s) => s.hasGeneratedOnce);
  const activeId = useReportStore((s) => s.activePackageId);
  const activePkg = packages.find((p) => p.id === activeId);

  const importDone = packages.length > 0;
  const headerFieldsFilled = Boolean(
    (activePkg?.projectCode || "").trim() &&
    (activePkg?.projectName || "").trim() &&
    (header.locationDate || "").trim() &&
    (header.monthLabel || "").trim()
  );
  // Also check global header: legacy checks projectCode, projectName (per package via active), locationDate, monthLabel
  const dataDone = importDone && headerFieldsFilled;
  const readyToGenerate = importDone && dataDone;

  const steps = [
    { label: "Importar", state: importDone ? "done" as const : "active" as const },
    { label: "Dados", state: !importDone ? "pending" as const : dataDone ? "done" as const : "active" as const },
    { label: "Revisar", state: !readyToGenerate ? "pending" as const : hasGeneratedOnce ? "done" as const : "active" as const },
    { label: "Gerar", state: hasGeneratedOnce ? "done" as const : readyToGenerate ? "active" as const : "pending" as const },
  ];

  return (
    <nav className="stepper">
      {steps.map((step, i) => (
        <span key={step.label} className="step-wrap">
          {i > 0 && <span className={`rail ${steps[i - 1].state === "done" ? "done" : ""}`} aria-hidden="true" />}
          <div className={`step ${step.state}`}>
            <span className="dot">{step.state === "done" ? "✓" : String(i + 1).padStart(2, "0")}</span>
            <span className="label">{step.label}</span>
          </div>
        </span>
      ))}
    </nav>
  );
}
