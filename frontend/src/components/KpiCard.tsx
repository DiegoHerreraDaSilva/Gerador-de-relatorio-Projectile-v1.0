import type { ReactNode } from "react";
import { Gauge } from "./Gauge";

type GaugeProps = {
  value: number | null;
  metaValue: number;
  metaType: "min" | "max";
  gaugeMax: number;
  label: string;
};

type Props = {
  icon: ReactNode;
  title: string;
  metaText: string;
  gauge: GaugeProps;
  /** thead/tbody/tfoot da tabela — cada card tem colunas e regras de KPI
   *  próprias demais (célula editável, matemática de % no tfoot ou não) pra
   *  valer a pena genericizar em headers/rows; o slot deixa cada chamador
   *  escrever sua tabela igual já era, só o card em volta é compartilhado. */
  children: ReactNode;
};

export function KpiCard({ icon, title, metaText, gauge, children }: Props) {
  return (
    <div className="card kpi-card">
      <div className="kpi-card-head">
        {icon}
        <div>
          <h3>{title}</h3>
          <p className="muted">{metaText}</p>
        </div>
      </div>
      <Gauge {...gauge} />
      <div className="kpi-table-wrap">
        <table className="kpi-table">{children}</table>
      </div>
    </div>
  );
}
