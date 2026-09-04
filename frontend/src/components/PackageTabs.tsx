import { useRef } from "react";
import { useReportStore } from "../store/useReportStore";
import { computeGrandTotalFor } from "../utils/calc";
import { fmtNum } from "../utils/fmt";

export function PackageTabs() {
  const packages = useReportStore((s) => s.packages);
  const activeId = useReportStore((s) => s.activePackageId);
  const setActive = useReportStore((s) => s.setActivePackageId);
  const removePackage = useReportStore((s) => s.removePackage);
  const mergePackages = useReportStore((s) => s.mergePackages);
  const draggedId = useReportStore((s) => s.draggedPackageId);
  const setDragged = useReportStore((s) => s.setDraggedPackageId);

  if (packages.length <= 1) return null;

  return (
    <nav className="package-tabs visible" id="packageTabs">
      {packages.map((pkg) => {
        const total = computeGrandTotalFor(pkg.groups);
        const isActive = pkg.id === activeId;
        return (
          <PackageTabWrap
            key={pkg.id}
            pkgId={pkg.id}
            label={pkg.projectName || pkg.key}
            total={fmtNum(total)}
            isActive={isActive}
            draggedId={draggedId}
            onActivate={() => setActive(pkg.id)}
            onRemove={() => removePackage(pkg.id)}
            onDragStart={(e) => {
              setDragged(pkg.id);
              e.dataTransfer.effectAllowed = "move";
              e.dataTransfer.setData("text/plain", pkg.id);
            }}
            onDragEnd={() => setDragged(null)}
            onDrop={(sourceId) => {
              if (sourceId && sourceId !== pkg.id) mergePackages(sourceId, pkg.id);
            }}
          />
        );
      })}
    </nav>
  );
}

function PackageTabWrap({
  pkgId,
  label,
  total,
  isActive,
  draggedId,
  onActivate,
  onRemove,
  onDragStart,
  onDragEnd,
  onDrop,
}: {
  pkgId: string;
  label: string;
  total: string;
  isActive: boolean;
  draggedId: string | null;
  onActivate: () => void;
  onRemove: () => void;
  onDragStart: (e: React.DragEvent) => void;
  onDragEnd: () => void;
  onDrop: (sourceId: string) => void;
}) {
  const wrapRef = useRef<HTMLSpanElement>(null);
  const countRef = useRef(0);

  return (
    <span
      ref={wrapRef}
      className="package-tab-wrap"
      onDragEnter={() => {
        if (draggedId && draggedId !== pkgId) {
          countRef.current += 1;
          wrapRef.current?.classList.add("drop-target");
        }
      }}
      onDragLeave={() => {
        countRef.current = Math.max(0, countRef.current - 1);
        if (countRef.current === 0) wrapRef.current?.classList.remove("drop-target");
      }}
      onDragOver={(e) => e.preventDefault()}
      onDrop={(e) => {
        e.preventDefault();
        countRef.current = 0;
        wrapRef.current?.classList.remove("drop-target");
        const source = e.dataTransfer.getData("text/plain") || draggedId || "";
        onDrop(source);
      }}
    >
      <button
        type="button"
        className={`package-tab ${isActive ? "active" : ""}`}
        draggable
        onClick={onActivate}
        onDragStart={(e) => {
          (e.currentTarget as HTMLElement).classList.add("dragging");
          onDragStart(e);
        }}
        onDragEnd={(e) => {
          (e.currentTarget as HTMLElement).classList.remove("dragging");
          onDragEnd();
        }}
      >
        {label}
        <span className="tab-hours">{total}h</span>
      </button>
      <button
        type="button"
        className="package-tab-remove"
        title="Remover este relatório"
        aria-label="Remover este relatório"
        onClick={(e) => {
          e.stopPropagation();
          onRemove();
        }}
      />
    </span>
  );
}
