import { useEffect } from "react";
import { SingleSelectDropdown } from "../FilterDropdown";
import { hasCoordinatorAccess, useAuthStore } from "../../store/useAuthStore";
import { useMyHoursStore } from "../../store/useMyHoursStore";

const ME = "__me__";

/** Seletor "de quem são as horas" do Dashboard de horas — só gerente e
 * coordenador (o backend barra o resto: `/my-hours?employee_id=` responde
 * 403 pra colaborador e 404 pra quem não é de engenharia). A lista vem de
 * `/my-hours/employees`: engenharia (CAD+CAE) com apontamento recente. */
export function EmployeePicker() {
  const canPick = useAuthStore((s) => hasCoordinatorAccess(s.user));
  const employeeId = useMyHoursStore((s) => s.employeeId);
  const employees = useMyHoursStore((s) => s.employees);
  const employeesError = useMyHoursStore((s) => s.employeesError);
  const loadEmployees = useMyHoursStore((s) => s.loadEmployees);
  const setEmployee = useMyHoursStore((s) => s.setEmployee);

  useEffect(() => {
    if (canPick) loadEmployees();
  }, [canPick, loadEmployees]);

  if (!canPick) return null;

  const names = new Map(employees.map((e) => [e.employee_id, e.name]));
  const options = [ME, ...employees.map((e) => e.employee_id)];

  return (
    <div className="myh-employee-picker">
      <SingleSelectDropdown
        label="Colaborador"
        options={options}
        value={employeeId ?? ME}
        labelFor={(opt) => (opt === ME ? "Minhas horas" : names.get(opt) ?? opt)}
        onChange={(opt) => setEmployee(opt === ME ? null : opt)}
        searchPlaceholder="Buscar colaborador..."
        className="myh-employee-dropdown"
      />
      {employeesError && <span className="error-text">{employeesError}</span>}
    </div>
  );
}
