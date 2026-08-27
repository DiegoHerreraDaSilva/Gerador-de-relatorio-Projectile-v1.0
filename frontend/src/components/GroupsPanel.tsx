import { useReportStore } from "../store/useReportStore";
import { computeGroupTotals } from "../utils/calc";
import { fmtNum, parseLocaleNumber, parseExtraHoursInput } from "../utils/fmt";

export function GroupsPanel() {
  const activePkg = useReportStore((s) => s.packages.find((p) => p.id === s.activePackageId) ?? null);
  const addGroup = useReportStore((s) => s.addGroup);
  const removeGroup = useReportStore((s) => s.removeGroup);
  const addActivity = useReportStore((s) => s.addActivity);
  const removeActivities = useReportStore((s) => s.removeActivities);
  const updateGroupName = useReportStore((s) => s.updateGroupName);
  const updatePerformance = useReportStore((s) => s.updatePerformance);
  const updateDescription = useReportStore((s) => s.updateDescription);
  const updateExtraHours = useReportStore((s) => s.updateExtraHours);
  const pushUndo = useReportStore((s) => s.pushUndo);
  const toggleCollapsed = useReportStore((s) => s.toggleGroupCollapsed);

  if (!activePkg) return null;

  return (
    <div className="card">
      <h2>Grupos e horas</h2>
      <div id="groupsContainer">
        {activePkg.groups.map((group, gIdx) => {
          const { resultado, hasRealActivities } = computeGroupTotals(group);
          const isCollapsed = activePkg.collapsedGroupIds.has(group.id);
          const { bruto } = computeGroupTotals(group);
          return (
            <div key={group.id} className={`group ${isCollapsed ? "collapsed" : ""}`}>
              <div className="group-header" onClick={() => toggleCollapsed(group.id)}>
                <span className="chevron">▾</span>
                <span className="idx-badge">{gIdx + 1}</span>
                <span className="group-title">{group.name}</span>
                <span className="group-hours">{hasRealActivities ? fmtNum(resultado) + " h" : ""}</span>
                <button
                  type="button"
                  className="remove-group"
                  title="Remover grupo"
                  aria-label="Remover grupo"
                  onClick={(e) => {
                    e.stopPropagation();
                    removeGroup(group.id);
                  }}
                />
              </div>
              <div className="group-body">
                <div className="perf-card">
                  <label>Performance</label>
                  <input
                    type="number"
                    step="0.01"
                    value={group.performance}
                    onFocus={() => pushUndo()}
                    onChange={(e) => updatePerformance(group.id, parseFloat(e.target.value) || 0)}
                  />
                  <div className="perf-breakdown">
                    {hasRealActivities ? (
                      <span>
                        Bruto <strong>{fmtNum(bruto)}h</strong> × Performance <strong>{fmtNum(group.performance)}</strong> ={" "}
                        <strong>{fmtNum(resultado)}h</strong>
                      </span>
                    ) : (
                      "Sem horas apontadas neste grupo ainda."
                    )}
                  </div>
                </div>
                <div className="activities">
                  {group.activities.length === 0 && <p className="muted">Nenhuma atividade neste grupo.</p>}
                  {group.activities.map((activity, aIdx) => {
                    const isExtra = activity.hours === null || activity.hours === undefined;
                    return (
                      <div key={activity.id} className="activity-row">
                        <span className="idx-badge">{aIdx + 1}</span>
                        <input
                          className="desc"
                          type="text"
                          value={activity.description}
                          onFocus={() => pushUndo()}
                          onChange={(e) => updateDescription(group.id, activity.id, e.target.value)}
                        />
                        <input
                          className="hours"
                          type="text"
                          value={isExtra ? (activity.hours === null ? "" : String(activity.hours)) : fmtNum(activity.hours as number)}
                          placeholder="horas"
                          readOnly={!isExtra}
                          onFocus={() => {
                            if (isExtra) pushUndo();
                          }}
                          onChange={(e) => {
                            if (isExtra) updateExtraHours(group.id, activity.id, parseExtraHoursInput(e.target.value));
                          }}
                        />
                        <button
                          type="button"
                          className="remove-activity"
                          title="Remover atividade"
                          aria-label="Remover atividade"
                          onClick={() => removeActivities(activePkg.id, [{ groupId: group.id, activityId: activity.id }])}
                        >
                          ×
                        </button>
                      </div>
                    );
                  })}
                </div>
                <button className="add-activity" onClick={() => addActivity(group.id)}>
                  + adicionar atividade extra (sem horas)
                </button>
              </div>
            </div>
          );
        })}
      </div>
      <button type="button" className="btn-secondary" style={{ marginTop: 12 }} onClick={() => addGroup()}>
        + Novo grupo
      </button>
    </div>
  );
}
