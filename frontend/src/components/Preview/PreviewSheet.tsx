import { useEffect, useRef } from "react";
import { useReportStore } from "../../store/useReportStore";
import { computeGroupTotals, computeGrandTotalFor } from "../../utils/calc";
import { fmtNum, parseLocaleNumber, parseExtraHoursInput } from "../../utils/fmt";

type Props = { paneId: string; packageId: string };

export function PreviewSheet({ paneId, packageId }: Props) {
  const pkg = useReportStore((s) => s.packages.find((p) => p.id === packageId) ?? null);
  const header = useReportStore((s) => s.header);
  const setHeaderField = useReportStore((s) => s.setHeaderField);
  const updateProjectCode = useReportStore((s) => s.updateProjectCode);
  const updateProjectName = useReportStore((s) => s.updateProjectName);
  const updateGroupName = useReportStore((s) => s.updateGroupName);
  const updatePerformance = useReportStore((s) => s.updatePerformance);
  const updateDescription = useReportStore((s) => s.updateDescription);
  const updateExtraHours = useReportStore((s) => s.updateExtraHours);
  const addGroup = useReportStore((s) => s.addGroup);
  const addActivity = useReportStore((s) => s.addActivity);
  const removeGroup = useReportStore((s) => s.removeGroup);
  const removeActivities = useReportStore((s) => s.removeActivities);
  const moveActivitiesToGroup = useReportStore((s) => s.moveActivitiesToGroup);
  const moveGroupToPackage = useReportStore((s) => s.moveGroupToPackage);
  const draggedActivities = useReportStore((s) => s.draggedActivities);
  const setDraggedActivities = useReportStore((s) => s.setDraggedActivities);
  const draggedGroup = useReportStore((s) => s.draggedGroup);
  const setDraggedGroup = useReportStore((s) => s.setDraggedGroup);
  const selectedByPane = useReportStore((s) => s.selectedByPane[paneId] ?? new Set<string>());
  const toggleSelected = useReportStore((s) => s.toggleSelected);
  const setSelected = useReportStore((s) => s.setSelected);
  const clearSelected = useReportStore((s) => s.clearSelected);
  const pushUndo = useReportStore((s) => s.pushUndo);

  const containerRef = useRef<HTMLDivElement>(null);

  // marquee selection (Ctrl+drag area)
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const DRAG_THRESHOLD = 4;
    let startPoint: { x: number; y: number } | null = null;
    let baseSelection: Set<string> | null = null;
    let marqueeBox: HTMLDivElement | null = null;

    function boxFromPoints(a: { x: number; y: number }, b: { x: number; y: number }) {
      return { left: Math.min(a.x, b.x), right: Math.max(a.x, b.x), top: Math.min(a.y, b.y), bottom: Math.max(a.y, b.y) };
    }
    function applySelectionForBox(box: { left: number; right: number; top: number; bottom: number }) {
      el!.querySelectorAll<HTMLDivElement>(".preview-activity").forEach((row) => {
        const r = row.getBoundingClientRect();
        const intersects = r.left < box.right && r.right > box.left && r.top < box.bottom && r.bottom > box.top;
        const key = `${row.dataset.gid}:${row.dataset.aid}`;
        const shouldSelect = baseSelection!.has(key) || intersects;
        row.classList.toggle("selected", shouldSelect);
        // sync store
        const cur = useReportStore.getState().selectedByPane[paneId] ?? new Set<string>();
        const next = new Set(cur);
        if (shouldSelect) next.add(key);
        else next.delete(key);
        useReportStore.getState().setSelected(paneId, next);
      });
    }
    function onMouseMove(e: MouseEvent) {
      if (!startPoint) return;
      const point = { x: e.clientX, y: e.clientY };
      if (!marqueeBox) {
        if (Math.abs(point.x - startPoint.x) < DRAG_THRESHOLD && Math.abs(point.y - startPoint.y) < DRAG_THRESHOLD) return;
        baseSelection = new Set(useReportStore.getState().selectedByPane[paneId] ?? []);
        marqueeBox = document.createElement("div");
        marqueeBox.className = "activity-marquee";
        document.body.appendChild(marqueeBox);
      }
      const box = boxFromPoints(startPoint, point);
      marqueeBox.style.left = box.left + "px";
      marqueeBox.style.top = box.top + "px";
      marqueeBox.style.width = box.right - box.left + "px";
      marqueeBox.style.height = box.bottom - box.top + "px";
      applySelectionForBox(box);
    }
    function endMarquee() {
      if (marqueeBox) marqueeBox.remove();
      marqueeBox = null;
      startPoint = null;
      baseSelection = null;
      document.removeEventListener("mousemove", onMouseMove);
    }
    const onMouseDown = (e: MouseEvent) => {
      if (!(e.ctrlKey || e.metaKey) || e.button !== 0) return;
      // only if clicking on preview sheet background, not inputs?
      startPoint = { x: e.clientX, y: e.clientY };
      document.addEventListener("mousemove", onMouseMove);
      document.addEventListener("mouseup", endMarquee, { once: true });
    };
    el.addEventListener("mousedown", onMouseDown as unknown as EventListener);
    return () => el.removeEventListener("mousedown", onMouseDown as unknown as EventListener);
  }, [paneId]);

  if (!pkg) return <p className="preview-empty">Analise um arquivo do Projectile para ver o preview.</p>;

  const monthLabelDisplay = header.monthLabel || "Mês/AAAA";
  const totalHoras = computeGrandTotalFor(pkg.groups);

  const handleHeaderInput = (field: string, value: string) => {
    if (field === "projectCode") updateProjectCode(value, pkg.id);
    else if (field === "projectName") updateProjectName(value, pkg.id);
    else setHeaderField(field as keyof typeof header, value);
  };

  return (
    <div ref={containerRef} className="preview-sheet" data-pane={paneId}>
      <div className="preview-top">
        <div className="preview-title">RELATÓRIO DE HORAS</div>
        <img src="logo-light.png" alt="Schwaben Engineering" className="preview-logo" />
      </div>
      <div className="preview-meta">
        <div className="code">
          <input
            className="pv-input pv-header"
            data-pv="projectCode"
            type="text"
            value={pkg.projectCode}
            placeholder="SE.XX.XXX"
            onFocus={() => pushUndo()}
            onChange={(e) => handleHeaderInput("projectCode" as any, e.target.value)}
          />
        </div>
        <div className="right">
          <div>
            <strong>
              <input
                className="pv-input pv-header"
                data-pv="locationDate"
                type="text"
                value={header.locationDate}
                placeholder="Local, DD.MM.AAAA"
                onFocus={() => pushUndo()}
                onChange={(e) => handleHeaderInput("locationDate" as any, e.target.value)}
              />
            </strong>
          </div>
          <div>
            <input
              className="pv-input pv-header"
              data-pv="projectName"
              type="text"
              value={pkg.projectName}
              placeholder="Nome do projeto"
              onFocus={() => pushUndo()}
              onChange={(e) => handleHeaderInput("projectName" as any, e.target.value)}
            />
          </div>
          <div>
            <input
              className="pv-input pv-header"
              data-pv="monthLabel"
              type="text"
              value={header.monthLabel}
              placeholder="Mês/AAAA"
              onFocus={() => pushUndo()}
              onChange={(e) => {
                setHeaderField("monthLabel", e.target.value);
              }}
            />
          </div>
        </div>
      </div>

      <div className="preview-banner-row">
        <div className="preview-banner">Relatório de horas referentes ao mês de {monthLabelDisplay}</div>
        <div className="preview-banner-side" />
      </div>
      <div className="preview-cols">
        <div className="c1">Descritivo de Atividades</div>
        <div className="c2">Horas</div>
      </div>

      {pkg.groups.map((group, gIdx) => {
        const { bruto, resultado, hasRealActivities } = computeGroupTotals(group);
        const isSelectedGroup = false;
        return (
          <div
            key={group.id}
            className="preview-group-row"
            data-gid={group.id}
            onDragEnter={(e) => {
              // group drop target for activities
              if (draggedActivities && draggedActivities.items.some((it) => draggedActivities.fromPackageId !== packageId || it.groupId !== group.id)) {
                (e.currentTarget.querySelector(".preview-group") as HTMLElement)?.classList.add("drop-target");
              }
            }}
            onDragLeave={(e) => {
              (e.currentTarget.querySelector(".preview-group") as HTMLElement)?.classList.remove("drop-target");
            }}
            onDragOver={(e) => {
              if (!draggedActivities) return;
              e.preventDefault();
            }}
            onDrop={(e) => {
              if (!draggedActivities) return;
              e.preventDefault();
              (e.currentTarget.querySelector(".preview-group") as HTMLElement)?.classList.remove("drop-target");
              moveActivitiesToGroup(draggedActivities.fromPackageId, draggedActivities.items, packageId, group.id);
              setDraggedActivities(null);
            }}
          >
            <div
              className="preview-group"
              data-gindex={gIdx}
              onDragEnter={(e) => {
                // needed for group handle? handled via pane
              }}
            >
              <div className="preview-group-header">
                <span
                  className="pv-group-handle"
                  draggable
                  title="Arrastar grupo para o outro painel (split view)"
                  onDragStart={(e) => {
                    setDraggedGroup({ fromPackageId: packageId, groupId: group.id });
                    e.dataTransfer.effectAllowed = "move";
                    e.dataTransfer.setData("text/plain", "group");
                    (e.currentTarget.closest(".preview-group") as HTMLElement)?.classList.add("dragging");
                  }}
                  onDragEnd={(e) => {
                    setDraggedGroup(null);
                    document.querySelectorAll(".preview-group.dragging").forEach((el) => el.classList.remove("dragging"));
                  }}
                >
                  ⠿
                </span>
                <span className="pv-idx">{gIdx + 1}</span>
                <input
                  className="pv-input pv-group-name"
                  type="text"
                  value={group.name}
                  onFocus={() => pushUndo()}
                  onChange={(e) => updateGroupName(group.id, e.target.value, packageId)}
                />
                <button type="button" className="pv-remove-group" title="Remover grupo" aria-label="Remover grupo" onClick={() => removeGroup(group.id, packageId)} />
              </div>
              <div className="preview-group-body">
                <div className="preview-group-main">
                  {group.activities.map((activity, aIdx) => {
                    const isExtra = activity.hours === null || activity.hours === undefined;
                    const key = `${group.id}:${activity.id}`;
                    const isSelected = selectedByPane.has(key);
                    return (
                      <div
                        key={activity.id}
                        className={`preview-activity ${isSelected ? "selected" : ""}`}
                        data-gid={group.id}
                        data-aid={activity.id}
                        data-gindex={gIdx}
                        data-aindex={aIdx}
                        onMouseDown={(e) => {
                          if (e.ctrlKey || e.metaKey) {
                            e.preventDefault();
                            toggleSelected(paneId, key);
                            return;
                          }
                          if ((e.target as HTMLElement).closest(".pv-remove-activity")) return;
                          if (selectedByPane.size) clearSelected(paneId);
                        }}
                      >
                        <span className="pv-idx">{aIdx + 1}</span>
                        <input
                          className="pv-input pv-desc"
                          type="text"
                          value={activity.description}
                          onFocus={() => pushUndo()}
                          onChange={(e) => updateDescription(group.id, activity.id, e.target.value, packageId)}
                        />
                        {isExtra && (
                          <input
                            className="pv-input pv-hours-extra"
                            type="text"
                            value={activity.hours === null ? "" : String(activity.hours)}
                            placeholder="horas"
                            onFocus={() => pushUndo()}
                            onChange={(e) => updateExtraHours(group.id, activity.id, parseExtraHoursInput(e.target.value), packageId)}
                          />
                        )}
                        <button
                          type="button"
                          className="pv-remove-activity"
                          draggable
                          title="Remover atividade (ou arraste para outro grupo — Ctrl+clique para selecionar várias)"
                          aria-label="Remover atividade"
                          onClick={(e) => {
                            if (e.ctrlKey || e.metaKey) return;
                            const isMulti = selectedByPane.size > 1 && selectedByPane.has(key);
                            const items = isMulti
                              ? Array.from(selectedByPane).map((k) => {
                                  const [g, a] = k.split(":");
                                  return { groupId: g, activityId: a };
                                })
                              : [{ groupId: group.id, activityId: activity.id }];
                            removeActivities(packageId, items);
                          }}
                          onDragStart={(e) => {
                            const isMulti = selectedByPane.size > 1 && selectedByPane.has(key);
                            const items = isMulti
                              ? Array.from(selectedByPane).map((k) => {
                                  const [g, a] = k.split(":");
                                  return { groupId: g, activityId: a };
                                })
                              : [{ groupId: group.id, activityId: activity.id }];
                            setDraggedActivities({ fromPackageId: packageId, items });
                            e.dataTransfer.effectAllowed = "move";
                            e.dataTransfer.setData("text/plain", "activity");
                            // add dragging class
                            requestAnimationFrame(() => {
                              items.forEach(({ groupId, activityId }) => {
                                const el = document.querySelector(`.preview-activity[data-gid="${groupId}"][data-aid="${activityId}"]`);
                                el?.classList.add("dragging");
                              });
                            });
                          }}
                          onDragEnd={() => {
                            setDraggedActivities(null);
                            document.querySelectorAll(".preview-activity.dragging").forEach((el) => el.classList.remove("dragging"));
                          }}
                        />
                      </div>
                    );
                  })}
                  <button type="button" className="pv-add-activity" onClick={() => addActivity(group.id, packageId)}>
                    + Adicionar atividade
                  </button>
                </div>
                <div className="preview-hours-col">{hasRealActivities ? fmtNum(resultado) : ""}</div>
              </div>
            </div>

            <div className="preview-side-box">
              <div className="preview-side-header">
                <span>Bruto</span>
                <span>Performance</span>
              </div>
              <div className="preview-side-values">
                <span className="bruto">{bruto ? fmtNum(bruto) : ""}</span>
                <span className="perf">
                  <input
                    className="pv-input pv-perf"
                    type="text"
                    value={group.performance}
                    onFocus={() => pushUndo()}
                    onChange={(e) => updatePerformance(group.id, parseLocaleNumber(e.target.value) || 0, packageId)}
                  />
                </span>
              </div>
              <div className="preview-side-plain">{hasRealActivities ? fmtNum(resultado) : ""}</div>
            </div>
          </div>
        );
      })}

      <button type="button" className="pv-add-group" onClick={() => addGroup(packageId)}>
        + Novo grupo
      </button>

      <div className="preview-total">
        <div className="label">Total de horas {monthLabelDisplay}:</div>
        <div className="value">{fmtNum(totalHoras)}</div>
        <div className="spacer" />
      </div>

      <div className="preview-signatures">
        <div className="sig">
          <div className="line" />
          <input
            className="pv-input pv-header pv-signer-name"
            type="text"
            value={header.signer1Name}
            placeholder="Nome do engenheiro"
            onFocus={() => pushUndo()}
            onChange={(e) => setHeaderField("signer1Name", e.target.value)}
          />
          <input
            className="pv-input pv-header pv-signer-company"
            type="text"
            value={header.signer1Company}
            placeholder="Empresa"
            onFocus={() => pushUndo()}
            onChange={(e) => setHeaderField("signer1Company", e.target.value)}
          />
        </div>
        <div className="sig">
          <div className="line" />
          <input
            className="pv-input pv-header pv-signer-name"
            type="text"
            value={header.signer2Name}
            placeholder="Nome do engenheiro"
            onFocus={() => pushUndo()}
            onChange={(e) => setHeaderField("signer2Name", e.target.value)}
          />
          <input
            className="pv-input pv-header pv-signer-company"
            type="text"
            value={header.signer2Company}
            placeholder="Empresa"
            onFocus={() => pushUndo()}
            onChange={(e) => setHeaderField("signer2Company", e.target.value)}
          />
        </div>
      </div>
    </div>
  );
}
