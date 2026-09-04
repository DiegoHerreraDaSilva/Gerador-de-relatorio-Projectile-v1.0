/** Skeleton com a geometria EXATA da página final.
 *
 * O ponto não é decorar a espera: é a página não saltar quando o dado chega.
 * O layout antigo mostrava uma frase "Carregando..." dentro de um card
 * pequeno e depois trocava por seis cards, movendo tudo de lugar.
 *
 * O pulso é desligado sob `prefers-reduced-motion` (ver index.css). */
export function MyHoursSkeleton() {
  return (
    <div className="myh-grid" aria-hidden="true">
      <div className="myh-card myh-col-12">
        <div className="skel skel-title" />
        <div className="skel skel-bullet" />
      </div>
      <div className="myh-card myh-col-7">
        <div className="skel skel-title" />
        <div className="skel skel-calendar" />
      </div>
      <div className="myh-col-5 myh-stack">
        <div className="myh-card">
          <div className="skel skel-title" />
          <div className="skel skel-line" />
          <div className="skel skel-line" />
        </div>
        <div className="myh-card">
          <div className="skel skel-title" />
          <div className="skel skel-line" />
          <div className="skel skel-line" />
        </div>
      </div>
      <div className="myh-card myh-col-7">
        <div className="skel skel-title" />
        <div className="skel skel-chart" />
      </div>
      <div className="myh-card myh-col-5">
        <div className="skel skel-title" />
        <div className="skel skel-line" />
        <div className="skel skel-line" />
        <div className="skel skel-line" />
      </div>
      <div className="myh-card myh-col-12">
        <div className="skel skel-title" />
        {Array.from({ length: 8 }, (_, i) => (
          <div className="skel skel-row" key={i} />
        ))}
      </div>
    </div>
  );
}
