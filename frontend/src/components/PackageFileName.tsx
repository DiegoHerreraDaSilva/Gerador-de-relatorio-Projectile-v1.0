import { useReportStore } from "../store/useReportStore";
import { computeDefaultFileNameFor } from "../utils/fileName";

export function PackageFileName() {
  const packages = useReportStore((s) => s.packages);
  const activeId = useReportStore((s) => s.activePackageId);
  const header = useReportStore((s) => s.header);
  const setPackageFileName = useReportStore((s) => s.setPackageFileName);

  if (packages.length <= 1) return null;
  const pkg = packages.find((p) => p.id === activeId);
  if (!pkg) return null;

  const displayName = pkg.fileNameEdited ? pkg.fileName : computeDefaultFileNameFor(pkg, header.monthLabel);

  return (
    <div className="package-filename-row visible">
      <label htmlFor="packageFileName">Nome do arquivo deste relatório (.xlsx)</label>
      <input
        type="text"
        id="packageFileName"
        value={displayName}
        title={displayName}
        onChange={(e) => setPackageFileName(pkg.id, e.target.value)}
      />
    </div>
  );
}
