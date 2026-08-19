let packages = []; // [{ key, projectCode, projectName, groupsData: [], collapsedGroups: Set }]
let activePackageIndex = 0;
let hasGeneratedOnce = false;
let headerDataCollapsed = true;
let previewZoom = 100;
let reportMode = "single"; // "single" | "multi"
let currentIssues = [];
let validationCollapsed = false;

// Trechos fixos do texto de cada motivo de issue (definidos em app/parser.py) que
// valem destaque — o resto da mensagem (valores entre aspas) é dado do usuário,
// não o diagnóstico em si.
const ISSUE_HIGHLIGHT_PHRASES = {
  sem_underscore: ['sem "_" separando prefixo e descrição'],
  descricao_vazia: ["prefixo vazio", "descrição vazia"],
  dados_incompletos: ["apontamento incompleto, falta preencher"],
  hs_invalido: ["não é um número válido"],
  pacote_nao_identificado: ["não consegui identificar o projeto"],
};

function renderIssueDetail(issue) {
  const rawDetail = issue.message.replace(/^Linha \d+:\s*/, "");
  let html = escapeHtml(rawDetail);
  for (const phrase of ISSUE_HIGHLIGHT_PHRASES[issue.reason] || []) {
    html = html.split(phrase).join(`<span class="issue-highlight">${phrase}</span>`);
  }
  return html;
}

function renderValidationBanner() {
  const banner = document.getElementById("validationBanner");
  const list = document.getElementById("validationList");
  const countEl = document.getElementById("validationCount");
  if (!banner || !list || !countEl) return;

  if (!currentIssues.length) {
    banner.classList.remove("visible");
    list.innerHTML = "";
    return;
  }

  banner.classList.add("visible");
  banner.classList.toggle("collapsed", validationCollapsed);
  countEl.textContent = currentIssues.length;
  list.innerHTML = currentIssues
    .map((issue) => `<li><span class="issue-row">Linha ${issue.row}</span><span class="issue-detail">${renderIssueDetail(issue)}</span></li>`)
    .join("");
}

document.getElementById("btnToggleValidation").addEventListener("click", (e) => {
  validationCollapsed = !validationCollapsed;
  e.target.textContent = validationCollapsed ? "▸ Expandir" : "▾ Recolher";
  renderValidationBanner();
});

document.getElementById("modeSelect").addEventListener("click", (e) => {
  const btn = e.target.closest(".mode-option");
  if (!btn) return;
  const newMode = btn.dataset.mode;
  if (newMode === reportMode) return;
  reportMode = newMode;
  document.querySelectorAll("#modeSelect .mode-option").forEach((opt) => {
    opt.classList.toggle("active", opt === btn);
  });
  if (packages.length > 0) {
    // Dados já analisados no modo anterior ficariam inconsistentes com o modo novo
    // (single mistura tudo num pacote só, multi separa por Pacote de Trabalho) —
    // força uma reanálise em vez de deixar "Gerar" usar dados de um modo diferente
    // do que está visivelmente selecionado.
    document.getElementById("fileInput").value = "";
    document.getElementById("btnClearFile").style.display = "none";
    document.getElementById("parseStatus").textContent =
      "Modo alterado — selecione o arquivo novamente para reanalisar.";
    resetParsedState();
  }
});

const MESES_PT = [
  "Janeiro", "Fevereiro", "Março", "Abril", "Maio", "Junho",
  "Julho", "Agosto", "Setembro", "Outubro", "Novembro", "Dezembro",
];

function activePackage() {
  return packages[activePackageIndex];
}

function preencherDataEMesAutomaticos() {
  const hoje = new Date();
  const dia = String(hoje.getDate()).padStart(2, "0");
  const mes = String(hoje.getMonth() + 1).padStart(2, "0");
  const ano = hoje.getFullYear();
  document.getElementById("locationDate").value = `Santo André, ${dia}.${mes}.${ano}`;

  // relatório normalmente se refere ao mês anterior ao da emissão
  const mesReferencia = new Date(hoje.getFullYear(), hoje.getMonth() - 1, 1);
  const nomeMes = MESES_PT[mesReferencia.getMonth()];
  document.getElementById("monthLabel").value = `${nomeMes}/${mesReferencia.getFullYear()}`;
}

let fileNameEditedByUser = false;

function sanitizeForFileName(text) {
  return (text || "").replace(/[\\/:*?"<>|]/g, "-").trim();
}

function computeDefaultFileName() {
  const monthLabel = document.getElementById("monthLabel").value || "";
  const mesAno = monthLabel.replace(/\//g, ".").trim();
  if (packages.length === 1) {
    const codigo = sanitizeForFileName(packages[0].projectCode);
    const projeto = sanitizeForFileName(packages[0].projectName);
    const prefixo = codigo ? `${codigo}_` : "";
    return `${prefixo}Relatório_Horas-${mesAno}-${projeto}`;
  }
  return `Relatórios_Horas-${mesAno}`;
}

function updateDefaultFileName() {
  const label = document.getElementById("fileNameLabel");
  if (label) label.textContent = packages.length > 1 ? "Nome do arquivo (.zip)" : "Nome do arquivo";
  if (!fileNameEditedByUser) {
    const input = document.getElementById("fileName");
    input.value = computeDefaultFileName();
    input.title = input.value;
    input.scrollLeft = input.scrollWidth;
  }
  renderPackageFileNameField();
}

// Nome de arquivo individual de CADA pacote (usado dentro do .zip no modo múltiplo).
// Cada pacote guarda seu próprio valor (pkg.fileName) e se já foi editado à mão
// (pkg.fileNameEdited) — mesmo padrão do nome de arquivo global do modo único.
function computeDefaultFileNameFor(pkg) {
  const monthLabel = document.getElementById("monthLabel").value || "";
  const mesAno = monthLabel.replace(/\//g, ".").trim();
  const codigo = sanitizeForFileName(pkg.projectCode);
  const projeto = sanitizeForFileName(pkg.projectName);
  const prefixo = codigo ? `${codigo}_` : "";
  return `${prefixo}Relatório_Horas-${mesAno}-${projeto}`;
}

function renderPackageFileNameField() {
  const row = document.getElementById("packageFileNameRow");
  const input = document.getElementById("packageFileName");
  if (!row || !input) return;
  const pkg = activePackage();
  if (packages.length <= 1 || !pkg) {
    row.classList.remove("visible");
    return;
  }
  row.classList.add("visible");
  if (!pkg.fileNameEdited) {
    pkg.fileName = computeDefaultFileNameFor(pkg);
  }
  input.value = pkg.fileName;
  input.title = pkg.fileName;
}

document.getElementById("packageFileName").addEventListener("input", (e) => {
  const pkg = activePackage();
  if (!pkg) return;
  pkg.fileNameEdited = true;
  pkg.fileName = e.target.value;
  e.target.title = e.target.value;
});

document.addEventListener("DOMContentLoaded", () => {
  preencherDataEMesAutomaticos();
  updateDefaultFileName();
  updateHeaderDataVisibility();
  ["projectCode", "projectName", "locationDate", "monthLabel"].forEach((id) => {
    document.getElementById(id).addEventListener("input", (e) => {
      if ((id === "projectCode" || id === "projectName") && activePackage()) {
        activePackage()[id] = e.target.value;
      }
      updateDefaultFileName();
      renderPreview();
    });
  });
  document.getElementById("fileName").addEventListener("input", (e) => {
    fileNameEditedByUser = true;
    e.target.title = e.target.value;
  });
  renderPreview();
});

function fmtNum(value) {
  return (Math.round(value * 100) / 100).toString().replace(".", ",");
}

// parseFloat sozinho para no primeiro caractere que não reconhece, então
// parseFloat("4,5") == 4 (trunca silenciosamente na vírgula) em vez de 4.5 — e como
// todo o resto do app mostra números com vírgula decimal (fmtNum), é natural o
// usuário digitar assim num campo editável. Espelha o parser.py (_parse_hs_value):
// só troca vírgula por ponto quando não há ponto já presente (evita interpretar
// errado um separador de milhar).
function parseLocaleNumber(value) {
  if (typeof value !== "string") return parseFloat(value);
  const trimmed = value.trim();
  if (trimmed.includes(",") && !trimmed.includes(".")) {
    return parseFloat(trimmed.replace(",", "."));
  }
  return parseFloat(trimmed);
}

// Usado especificamente nos campos de horas de atividade "extra" (sem apontamento
// real ainda — activity.hours === null). Se o texto digitado não vira um número
// válido (ex: "abc", ou só um "-" no meio de digitar "-5"), tem que voltar pra null
// em vez de NaN: um activity.hours numérico (mesmo que NaN) faz isExtra virar false
// na próxima renderização, trocando o campo pra readonly SEM listener — trancando a
// atividade com "NaN" escrito nela, sem nenhum jeito de corrigir a não ser apagar e
// recriar a atividade inteira. Voltando pra null, o campo continua editável.
function parseExtraHoursInput(value) {
  if (value === "") return null;
  const parsed = parseLocaleNumber(value);
  return Number.isFinite(parsed) ? parsed : null;
}

function escapeHtml(text) {
  const div = document.createElement("div");
  div.textContent = text ?? "";
  return div.innerHTML;
}

// Igual a escapeHtml, mas também escapa aspas — necessário sempre que o valor
// for inserido dentro de um atributo HTML (value="..."), não apenas como texto solto.
function escapeAttr(text) {
  return escapeHtml(text).replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

// Cálculo de bruto/performance/resultado de UM grupo. Fatorado para ser usado
// tanto no rebuild completo do preview quanto nas atualizações pontuais feitas
// a partir dos inputs editáveis do preview (evita as duas fórmulas divergirem).
function computeGroupTotals(group) {
  const realActivities = group.activities.filter((a) => a.hours !== null && a.hours !== undefined);
  const bruto = realActivities.reduce((sum, a) => sum + (parseFloat(a.hours) || 0), 0);
  const performance = parseFloat(group.performance) || 0;
  const resultado = bruto * performance;
  return { bruto, performance, resultado, hasRealActivities: realActivities.length > 0 };
}

function computeGrandTotalFor(groupsData) {
  return groupsData.reduce((sum, group) => {
    const { resultado, hasRealActivities } = computeGroupTotals(group);
    return hasRealActivities ? sum + resultado : sum;
  }, 0);
}

function computeGrandTotal() {
  const pkg = activePackage();
  return pkg ? computeGrandTotalFor(pkg.groupsData) : 0;
}

function computeGrandBruto() {
  const pkg = activePackage();
  if (!pkg) return 0;
  return pkg.groupsData.reduce((sum, group) => sum + computeGroupTotals(group).bruto, 0);
}

// --- Stepper / resumo / abas de pacote / dados do cabeçalho compacto ---
// Todos derivados só de packages + valor atual dos inputs, sem estado próprio
// (exceto hasGeneratedOnce, que reflete "gerou o relatório desde a última edição?").

function renderStepper() {
  const el = document.getElementById("stepper");
  if (!el) return;

  const importDone = packages.length > 0;
  const headerFieldsFilled = ["projectCode", "projectName", "locationDate", "monthLabel"].every(
    (id) => (document.getElementById(id).value || "").trim() !== ""
  );
  const dataDone = importDone && headerFieldsFilled;
  const readyToGenerate = importDone && dataDone;

  const steps = [
    { label: "Importar", state: importDone ? "done" : "active" },
    { label: "Dados", state: !importDone ? "pending" : dataDone ? "done" : "active" },
    { label: "Revisar", state: !readyToGenerate ? "pending" : hasGeneratedOnce ? "done" : "active" },
    { label: "Gerar", state: hasGeneratedOnce ? "done" : readyToGenerate ? "active" : "pending" },
  ];
  const icon = { done: "✓", active: "●", pending: "○" };

  el.innerHTML = steps
    .map(
      (step, i) => `
        ${i > 0 ? '<span class="arrow">→</span>' : ""}
        <div class="step ${step.state}">
          <span class="dot">${icon[step.state]}</span>
          <span class="label">${step.label}</span>
        </div>`
    )
    .join("");
}

function renderPackageTabs() {
  const nav = document.getElementById("packageTabs");
  if (!nav) return;

  if (packages.length <= 1) {
    nav.classList.remove("visible");
    nav.innerHTML = "";
    return;
  }

  nav.classList.add("visible");
  nav.innerHTML = packages
    .map((pkg, i) => {
      const total = computeGrandTotalFor(pkg.groupsData);
      return `
        <button type="button" class="package-tab ${i === activePackageIndex ? "active" : ""}" data-pindex="${i}">
          ${escapeHtml(pkg.key)}
          <span class="tab-hours">${fmtNum(total)}h</span>
        </button>`;
    })
    .join("");

  nav.querySelectorAll(".package-tab").forEach((btn) => {
    btn.addEventListener("click", () => switchActivePackage(Number(btn.dataset.pindex)));
  });
}

function switchActivePackage(index) {
  if (index === activePackageIndex || !packages[index]) return;
  activePackageIndex = index;
  loadActivePackageHeaderIntoForm();
  renderPackageTabs();
  renderPackageFileNameField();
  renderGroups();
  renderPreview();
}

function loadActivePackageHeaderIntoForm() {
  const pkg = activePackage();
  if (!pkg) return;
  document.getElementById("projectCode").value = pkg.projectCode || "";
  document.getElementById("projectName").value = pkg.projectName || "";
}

function renderSummaryBar() {
  const el = document.getElementById("summaryBar");
  const row = document.getElementById("summaryRow");
  if (!el) return;

  const pkg = activePackage();
  if (!pkg) {
    if (row) row.classList.remove("visible");
    el.innerHTML = "";
    const totalEl = document.getElementById("generateTotal");
    if (totalEl) totalEl.innerHTML = "";
    return;
  }

  const total = computeGrandTotal();
  const groupsCount = pkg.groupsData.length;
  const activitiesCount = pkg.groupsData.reduce((sum, g) => sum + g.activities.length, 0);

  if (row) row.classList.add("visible");
  el.innerHTML = `
    ${
      packages.length > 1
        ? `<div class="summary-stat"><span class="summary-value">${activePackageIndex + 1}/${packages.length}</span><span class="summary-label">Pacote</span></div>`
        : ""
    }
    <div class="summary-stat"><span class="summary-value">${fmtNum(total)} h</span><span class="summary-label">Total de horas</span></div>
    <div class="summary-stat"><span class="summary-value">${groupsCount}</span><span class="summary-label">Grupo${groupsCount === 1 ? "" : "s"}</span></div>
    <div class="summary-stat"><span class="summary-value">${activitiesCount}</span><span class="summary-label">Atividade${activitiesCount === 1 ? "" : "s"}</span></div>
  `;

  const totalEl = document.getElementById("generateTotal");
  if (totalEl) {
    const grandTotalAll = packages.reduce((sum, p) => sum + computeGrandTotalFor(p.groupsData), 0);
    totalEl.innerHTML =
      packages.length > 1
        ? `Total geral: <strong>${fmtNum(grandTotalAll)} horas</strong> em ${packages.length} relatórios`
        : `Total: <strong>${fmtNum(total)} horas</strong>`;
  }
}

function renderHeaderDataSummary() {
  const el = document.getElementById("headerDataSummary");
  if (!el) return;
  const fields = [
    ["Código", document.getElementById("projectCode").value],
    ["Nome", document.getElementById("projectName").value],
    ["Local/Data", document.getElementById("locationDate").value],
    ["Mês", document.getElementById("monthLabel").value],
  ];
  el.innerHTML = fields
    .map(
      ([label, value]) => `
        <div class="field">
          <span class="field-label">${escapeHtml(label)}</span>
          <span class="field-value">${escapeHtml(value) || "—"}</span>
        </div>`
    )
    .join("");
}

function updateProjectCodeValidation() {
  const input = document.getElementById("projectCode");
  if (!input) return;
  input.classList.toggle("field-missing", input.value.trim() === "");
}

function updateHeaderDataVisibility() {
  document.getElementById("headerDataExpanded").style.display = headerDataCollapsed ? "none" : "block";
  document.getElementById("headerDataSummary").style.display = headerDataCollapsed ? "flex" : "none";
  document.getElementById("btnToggleHeaderData").textContent = headerDataCollapsed ? "✎ Editar dados" : "▾ Recolher";
  if (headerDataCollapsed) renderHeaderDataSummary();
}

document.getElementById("btnToggleHeaderData").addEventListener("click", () => {
  headerDataCollapsed = !headerDataCollapsed;
  updateHeaderDataVisibility();
});

// Chamado no fim de renderPreview()/renderGroups() — atualiza tudo que é derivado
// do estado atual, sem nunca reescrever o innerHTML do preview ou do formulário.
function refreshDerivedUI() {
  renderStepper();
  renderPackageTabs();
  renderSummaryBar();
  updateProjectCodeValidation();
  if (headerDataCollapsed) renderHeaderDataSummary();
}

function updatePerfBreakdown(gIndex) {
  const pkg = activePackage();
  const group = pkg && pkg.groupsData[gIndex];
  const el = document.getElementById(`perf-breakdown-${gIndex}`);
  if (!group || !el) return;
  const { bruto, performance, resultado, hasRealActivities } = computeGroupTotals(group);
  el.innerHTML = hasRealActivities
    ? `Bruto <strong>${fmtNum(bruto)}h</strong> × Performance <strong>${fmtNum(performance)}</strong> = <strong>${fmtNum(resultado)}h</strong>`
    : "Sem horas apontadas neste grupo ainda.";
}

// Recalcula e atualiza (via textContent, nunca via innerHTML) só os números
// derivados de UM grupo no preview, mais o total geral. Seguro para ser chamado
// a partir de um input que vive dentro do próprio #previewContainer.
function updatePreviewGroupDerivedValues(gIndex) {
  const pkg = activePackage();
  const group = pkg && pkg.groupsData[gIndex];
  if (!group) return;
  const { bruto, resultado, hasRealActivities } = computeGroupTotals(group);

  const hoursEl = document.getElementById(`pv-hours-${gIndex}`);
  if (hoursEl) hoursEl.textContent = hasRealActivities ? fmtNum(resultado) : "";

  const brutoEl = document.getElementById(`pv-bruto-${gIndex}`);
  if (brutoEl) brutoEl.textContent = bruto ? fmtNum(bruto) : "";

  const resultEl = document.getElementById(`pv-result-${gIndex}`);
  if (resultEl) resultEl.textContent = hasRealActivities ? fmtNum(resultado) : "";

  const totalEl = document.getElementById("pv-total-value");
  if (totalEl) totalEl.textContent = fmtNum(computeGrandTotal());
}

// --- Handlers dos inputs editáveis DENTRO do #previewContainer ---
// Regra de ouro: nenhuma dessas funções pode fazer previewContainer.innerHTML = ...
// nem chamar renderPreview(). Elas só: (a) atualizam a activePackage()/o .value do
// campo espelho no formulário, (b) atualizam textContent de elementos derivados
// específicos, e (c) opcionalmente chamam renderGroups({ skipPreviewRebuild: true })
// para sincronizar o formulário (subárvore diferente de #previewContainer, seguro).

function handlePreviewHeaderInput(formFieldId, newValue) {
  document.getElementById(formFieldId).value = newValue;
  if ((formFieldId === "projectCode" || formFieldId === "projectName") && activePackage()) {
    activePackage()[formFieldId] = newValue;
  }
  if (formFieldId === "projectName" || formFieldId === "projectCode") updateDefaultFileName();
  renderStepper();
  renderPackageTabs();
  updateProjectCodeValidation();
  if (headerDataCollapsed) renderHeaderDataSummary();
}

function handlePreviewMonthLabelInput(newValue) {
  document.getElementById("monthLabel").value = newValue;
  updateDefaultFileName();
  const display = newValue || "Mês/AAAA";
  const bannerEl = document.getElementById("pv-banner-text");
  if (bannerEl) bannerEl.textContent = `Relatório de horas referentes ao mês de ${display}`;
  const totalLabelEl = document.getElementById("pv-total-label");
  if (totalLabelEl) totalLabelEl.textContent = `Total de horas ${display}:`;
  renderStepper();
  if (headerDataCollapsed) renderHeaderDataSummary();
}

function handlePreviewPerformanceInput(gIndex, newValue) {
  const pkg = activePackage();
  const group = pkg && pkg.groupsData[gIndex];
  if (!group) return;
  group.performance = parseLocaleNumber(newValue) || 0;
  updatePreviewGroupDerivedValues(gIndex);
  renderGroups({ skipPreviewRebuild: true });
}

function handlePreviewGroupNameInput(gIndex, newValue) {
  const pkg = activePackage();
  const group = pkg && pkg.groupsData[gIndex];
  if (!group) return;
  group.name = newValue;
  renderGroups({ skipPreviewRebuild: true });
}

function handlePreviewDescriptionInput(gIndex, aIndex, newValue) {
  const pkg = activePackage();
  const group = pkg && pkg.groupsData[gIndex];
  const activity = group && group.activities[aIndex];
  if (!activity) return;
  activity.description = newValue;
  renderGroups({ skipPreviewRebuild: true });
}

function handlePreviewExtraHoursInput(gIndex, aIndex, newValue) {
  const pkg = activePackage();
  const group = pkg && pkg.groupsData[gIndex];
  const activity = group && group.activities[aIndex];
  if (!activity) return;
  activity.hours = parseExtraHoursInput(newValue);
  updatePreviewGroupDerivedValues(gIndex);
  renderGroups({ skipPreviewRebuild: true });
}

function attachPreviewListeners(container) {
  const codeInput = container.querySelector("#pv-projectCode");
  if (codeInput) codeInput.addEventListener("input", (e) => handlePreviewHeaderInput("projectCode", e.target.value));

  const dateInput = container.querySelector("#pv-locationDate");
  if (dateInput) dateInput.addEventListener("input", (e) => handlePreviewHeaderInput("locationDate", e.target.value));

  const nameInput = container.querySelector("#pv-projectName");
  if (nameInput) nameInput.addEventListener("input", (e) => handlePreviewHeaderInput("projectName", e.target.value));

  const monthInput = container.querySelector("#pv-monthLabel");
  if (monthInput) monthInput.addEventListener("input", (e) => handlePreviewMonthLabelInput(e.target.value));

  container.querySelectorAll(".pv-group-name").forEach((input) => {
    input.addEventListener("input", (e) => {
      handlePreviewGroupNameInput(Number(e.target.dataset.gindex), e.target.value);
    });
  });

  container.querySelectorAll(".pv-perf").forEach((input) => {
    input.addEventListener("input", (e) => {
      handlePreviewPerformanceInput(Number(e.target.dataset.gindex), e.target.value);
    });
  });

  container.querySelectorAll(".pv-desc").forEach((input) => {
    input.addEventListener("input", (e) => {
      handlePreviewDescriptionInput(Number(e.target.dataset.gindex), Number(e.target.dataset.aindex), e.target.value);
    });
  });

  container.querySelectorAll(".pv-hours-extra").forEach((input) => {
    input.addEventListener("input", (e) => {
      handlePreviewExtraHoursInput(Number(e.target.dataset.gindex), Number(e.target.dataset.aindex), e.target.value);
    });
  });
}

function renderPreview() {
  hasGeneratedOnce = false;
  refreshDerivedUI();

  const container = document.getElementById("previewContainer");
  if (!container) return;

  const pkg = activePackage();

  const rawProjectCode = document.getElementById("projectCode").value || "";
  const rawProjectName = document.getElementById("projectName").value || "";
  const rawLocationDate = document.getElementById("locationDate").value || "";
  const rawMonthLabel = document.getElementById("monthLabel").value || "";
  const monthLabelDisplay = rawMonthLabel || "Mês/AAAA";
  const signer1Company = "Schwaben Engineering";
  const signer2Company = "Mercedes-Benz do Brasil";

  if (!pkg || !pkg.groupsData.length) {
    container.innerHTML = `<p class="preview-empty">Analise um arquivo do Projectile para ver o preview.</p>`;
    return;
  }

  const groupsData = pkg.groupsData;

  const groupsHtml = groupsData
    .map((group, gIndex) => {
      const { bruto, resultado, hasRealActivities } = computeGroupTotals(group);

      const indexedActivities = group.activities.map((activity, aIndex) => {
        const isExtra = activity.hours === null || activity.hours === undefined;
        return { activity, aIndex, isExtra };
      });
      const realActivities = indexedActivities.filter((item) => !item.isExtra);
      const extraActivities = indexedActivities.filter((item) => item.isExtra);

      const activityRows = [...realActivities, ...extraActivities]
        .map(
          ({ activity, aIndex, isExtra }) => `
            <div class="preview-activity">
              <input class="pv-input pv-desc" type="text" value="${escapeAttr(activity.description)}" data-gindex="${gIndex}" data-aindex="${aIndex}" />
              ${
                isExtra
                  ? `<input class="pv-input pv-hours-extra" type="text" value="" placeholder="horas" data-gindex="${gIndex}" data-aindex="${aIndex}" />`
                  : ""
              }
            </div>`
        )
        .join("");

      return `
        <div class="preview-group-row">
          <div class="preview-group">
            <div class="preview-group-header"><input class="pv-input pv-group-name" type="text" value="${escapeAttr(group.name)}" data-gindex="${gIndex}" /></div>
            <div class="preview-group-body">
              <div class="preview-group-main">
                ${activityRows}
              </div>
              <div class="preview-hours-col" id="pv-hours-${gIndex}">${hasRealActivities ? fmtNum(resultado) : ""}</div>
            </div>
          </div>
          <div class="preview-side-box">
            <div class="preview-side-header"><span>Bruto</span><span>Performance</span></div>
            <div class="preview-side-values">
              <span class="bruto" id="pv-bruto-${gIndex}">${bruto ? fmtNum(bruto) : ""}</span>
              <span class="perf"><input class="pv-input pv-perf" type="text" value="${escapeAttr(group.performance)}" data-gindex="${gIndex}" /></span>
            </div>
            <div class="preview-side-plain" id="pv-result-${gIndex}">${hasRealActivities ? fmtNum(resultado) : ""}</div>
          </div>
        </div>`;
    })
    .join("");

  const totalHoras = computeGrandTotal();

  container.innerHTML = `
    <div class="preview-top">
      <div class="preview-title">RELATÓRIO DE HORAS</div>
      <img src="logo-light.png" alt="Schwaben Engineering" class="preview-logo" />
    </div>
    <div class="preview-meta">
      <div class="code"><input class="pv-input pv-header" id="pv-projectCode" type="text" value="${escapeAttr(rawProjectCode)}" placeholder="SE.XX.XXX" /></div>
      <div class="right">
        <div><strong><input class="pv-input pv-header" id="pv-locationDate" type="text" value="${escapeAttr(rawLocationDate)}" placeholder="Local, DD.MM.AAAA" /></strong></div>
        <div><input class="pv-input pv-header" id="pv-projectName" type="text" value="${escapeAttr(rawProjectName)}" placeholder="Nome do projeto" /></div>
        <div><input class="pv-input pv-header" id="pv-monthLabel" type="text" value="${escapeAttr(rawMonthLabel)}" placeholder="Mês/AAAA" /></div>
      </div>
    </div>
    <div class="preview-banner-row">
      <div class="preview-banner" id="pv-banner-text">Relatório de horas referentes ao mês de ${escapeHtml(monthLabelDisplay)}</div>
      <div class="preview-banner-side"></div>
    </div>
    <div class="preview-cols"><div class="c1">Descritivo de Atividades</div><div class="c2">Horas</div></div>
    ${groupsHtml}
    <div class="preview-total">
      <div class="label" id="pv-total-label">Total de horas ${escapeHtml(monthLabelDisplay)}:</div>
      <div class="value" id="pv-total-value">${fmtNum(totalHoras)}</div>
      <div class="spacer"></div>
    </div>
    <div class="preview-signatures">
      <div class="sig"><div class="line"></div><strong>${escapeHtml(signer1Company)}</strong></div>
      <div class="sig"><div class="line"></div><strong>${escapeHtml(signer2Company)}</strong></div>
    </div>
  `;

  attachPreviewListeners(container);
  applyZoom();
}

document.getElementById("fileInput").addEventListener("change", (e) => {
  document.getElementById("btnClearFile").style.display = e.target.files.length ? "flex" : "none";
});

// Reseta todo o estado derivado de um parse (pacotes, issues, abas, nome de arquivo).
// Usado tanto ao remover o arquivo quanto ao trocar de modo com dados já analisados.
function resetParsedState() {
  packages = [];
  activePackageIndex = 0;
  currentIssues = [];
  document.getElementById("step2").classList.remove("visible");
  document.getElementById("generateSection").classList.remove("visible");
  document.getElementById("groupsContainer").innerHTML = "";
  document.getElementById("packageTabs").classList.remove("visible");
  document.getElementById("packageTabs").innerHTML = "";
  fileNameEditedByUser = false;
  document.getElementById("fileName").value = "";
  renderValidationBanner();
  renderPreview();
}

document.getElementById("btnClearFile").addEventListener("click", () => {
  const fileInput = document.getElementById("fileInput");
  fileInput.value = "";
  document.getElementById("btnClearFile").style.display = "none";
  document.getElementById("parseStatus").textContent = "";

  document.getElementById("step1").style.display = "block";

  resetParsedState();
});

document.getElementById("btnChangeFile").addEventListener("click", () => {
  document.getElementById("step1").style.display = "block";
});

document.getElementById("btnParse").addEventListener("click", async () => {
  const fileInput = document.getElementById("fileInput");
  const status = document.getElementById("parseStatus");
  if (!fileInput.files.length) {
    status.textContent = "Selecione um arquivo .xlsx primeiro.";
    return;
  }
  status.textContent = "Analisando...";
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  formData.append("mode", reportMode);

  try {
    const res = await fetch("/parse", { method: "POST", body: formData });
    if (!res.ok) throw new Error(await res.text());
    const data = await res.json();

    packages = data.packages.map((p) => ({
      key: p.key,
      projectCode: "",
      projectName: p.project_name || p.key,
      groupsData: p.groups.map((g) => ({
        name: g.name,
        performance: 1,
        activities: g.activities.map((a) => ({ description: a.description, hours: a.hours })),
      })),
      collapsedGroups: new Set(p.groups.map((_, i) => i)),
      fileName: "",
      fileNameEdited: false,
    }));
    activePackageIndex = 0;

    currentIssues = data.issues || [];
    renderValidationBanner();

    if (packages.length === 0) {
      // Planilha válida, mas nenhuma linha virou grupo/atividade (ex: só apontamentos
      // incompletos ou vazios) — não dá pra deixar "Gerar relatório final" clicável
      // sem nada pra gerar, então mantém o step1 visível em vez de avançar. Importante
      // esconder step2/generateSection explicitamente aqui (em vez de só confiar no
      // estado já estar assim): se um parse ANTERIOR bem-sucedido já tinha deixado
      // tudo visível, esse parse novo (que zerou os grupos) precisa recolher de volta,
      // senão "Gerar relatório final" continua clicável mostrando dados do arquivo
      // anterior.
      status.textContent =
        "Nenhum grupo de atividades encontrado nesta planilha. Confira o aviso de validação acima (se houver) ou o arquivo enviado.";
      document.getElementById("step2").classList.remove("visible");
      document.getElementById("generateSection").classList.remove("visible");
      document.getElementById("groupsContainer").innerHTML = "";
      document.getElementById("packageTabs").classList.remove("visible");
      document.getElementById("packageTabs").innerHTML = "";
      renderPackageFileNameField();
      renderPreview();
      return;
    }

    loadActivePackageHeaderIntoForm();
    updateDefaultFileName();

    renderPackageTabs();
    renderGroups();
    renderPreview();
    document.getElementById("step2").classList.add("visible");
    document.getElementById("generateSection").classList.add("visible");

    const totalGroups = packages.reduce((sum, p) => sum + p.groupsData.length, 0);
    status.textContent =
      packages.length > 1
        ? `Encontrados ${packages.length} pacotes de trabalho (${totalGroups} grupo(s) no total).`
        : `Encontrados ${totalGroups} grupo(s).`;

    document.getElementById("step1").style.display = "none";
  } catch (err) {
    status.textContent = "Erro ao analisar: " + err.message;
  }
});

function renderGroups(options = {}) {
  hasGeneratedOnce = false;
  const { skipPreviewRebuild = false } = options;
  const pkg = activePackage();
  const container = document.getElementById("groupsContainer");
  container.innerHTML = "";

  if (!pkg) {
    refreshDerivedUI();
    return;
  }

  const groupsData = pkg.groupsData;
  const collapsedGroups = pkg.collapsedGroups;

  groupsData.forEach((group, gIndex) => {
    const { resultado, hasRealActivities } = computeGroupTotals(group);
    const div = document.createElement("div");
    div.className = "group" + (collapsedGroups.has(gIndex) ? " collapsed" : "");
    div.innerHTML = `
      <div class="group-header" data-gindex="${gIndex}">
        <span class="chevron">▾</span>
        <span class="group-title">${escapeHtml(group.name)}</span>
        <span class="group-hours">${hasRealActivities ? fmtNum(resultado) + " h" : ""}</span>
      </div>
      <div class="group-body">
        <div class="perf-card">
          <label>Performance</label>
          <input type="number" step="0.01" value="${escapeAttr(group.performance)}" data-role="performance" data-gindex="${gIndex}" />
          <div class="perf-breakdown" id="perf-breakdown-${gIndex}"></div>
        </div>
        <div class="activities" data-gindex="${gIndex}"></div>
        <button class="add-activity" data-gindex="${gIndex}">+ adicionar atividade extra (sem horas)</button>
      </div>
    `;
    container.appendChild(div);

    const activitiesDiv = div.querySelector(".activities");
    group.activities.forEach((activity, aIndex) => {
      activitiesDiv.appendChild(renderActivityRow(group, gIndex, activity, aIndex));
    });
    if (group.activities.length === 0) {
      const empty = document.createElement("p");
      empty.className = "muted";
      empty.textContent = "Nenhuma atividade neste grupo.";
      activitiesDiv.appendChild(empty);
    }
    updatePerfBreakdown(gIndex);
  });

  container.querySelectorAll(".group-header").forEach((header) => {
    header.addEventListener("click", () => {
      const gIndex = Number(header.dataset.gindex);
      if (collapsedGroups.has(gIndex)) collapsedGroups.delete(gIndex);
      else collapsedGroups.add(gIndex);
      header.closest(".group").classList.toggle("collapsed");
    });
  });

  container.querySelectorAll("[data-role=performance]").forEach((input) => {
    input.addEventListener("input", (e) => {
      const gIndex = Number(e.target.dataset.gindex);
      groupsData[gIndex].performance = parseFloat(e.target.value) || 0;
      updatePerfBreakdown(gIndex);
      renderPreview();
    });
  });

  container.querySelectorAll(".add-activity").forEach((btn) => {
    btn.addEventListener("click", () => {
      const gIndex = btn.dataset.gindex;
      groupsData[gIndex].activities.push({ description: "", hours: null });
      renderGroups();
      renderPreview();
    });
  });

  if (!skipPreviewRebuild) {
    renderPreview();
  } else {
    refreshDerivedUI();
  }
}

function renderActivityRow(group, gIndex, activity, aIndex) {
  const row = document.createElement("div");
  row.className = "activity-row";
  const isExtra = activity.hours === null || activity.hours === undefined;
  row.innerHTML = `
    <input class="desc" type="text" value="${escapeAttr(activity.description)}" />
    <input class="hours" type="text" value="${isExtra ? "" : escapeAttr(fmtNum(activity.hours))}" placeholder="horas" ${isExtra ? "" : "readonly"} />
    <button type="button" class="remove-activity" title="Remover atividade" aria-label="Remover atividade">×</button>
  `;
  const descInput = row.querySelector(".desc");
  const hoursInput = row.querySelector(".hours");
  const removeBtn = row.querySelector(".remove-activity");
  descInput.addEventListener("input", (e) => {
    activity.description = e.target.value;
    renderPreview();
  });
  if (isExtra) {
    hoursInput.addEventListener("input", (e) => {
      activity.hours = parseExtraHoursInput(e.target.value);
      renderPreview();
    });
  }
  removeBtn.addEventListener("click", () => {
    const pkg = activePackage();
    pkg.groupsData[gIndex].activities.splice(aIndex, 1);
    renderGroups();
    renderPreview();
  });
  return row;
}

document.getElementById("btnGenerate").addEventListener("click", async () => {
  const status = document.getElementById("generateStatus");
  const sharedLocationDate = document.getElementById("locationDate").value;
  const sharedMonthLabel = document.getElementById("monthLabel").value;

  const payload = {
    packages: packages.map((pkg) => ({
      header: {
        project_code: pkg.projectCode,
        project_name: pkg.projectName,
        location_date: sharedLocationDate,
        month_label: sharedMonthLabel,
      },
      groups: pkg.groupsData.map((g) => ({
        name: g.name,
        performance: g.performance,
        activities: g.activities.map((a) => ({ description: a.description, hours: a.hours })),
      })),
      // Recalcula o nome padrão na hora de gerar em vez de confiar no pkg.fileName
      // "cacheado" — ele é preenchido sempre que a aba desse pacote é renderizada
      // (renderPackageFileNameField), então uma edição do mês/campo compartilhado
      // feita com OUTRA aba ativa nunca chegaria a atualizar esse cache. Só usa o
      // valor salvo quando o usuário realmente editou esse campo à mão.
      file_name: packages.length > 1 ? (pkg.fileNameEdited ? pkg.fileName : computeDefaultFileNameFor(pkg)) : undefined,
    })),
  };

  status.textContent = "Gerando...";
  try {
    const res = await fetch("/generate", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await res.text());
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const isZip = packages.length !== 1; // espelha a regra do backend (== 1 -> xlsx, senão zip)
    let fileName = document.getElementById("fileName").value.trim() || computeDefaultFileName();
    const wantedExt = isZip ? ".zip" : ".xlsx";
    if (!fileName.toLowerCase().endsWith(wantedExt)) fileName += wantedExt;
    const a = document.createElement("a");
    a.href = url;
    a.download = fileName;
    document.body.appendChild(a);
    a.click();
    a.remove();
    status.textContent = "";
    hasGeneratedOnce = true;
    renderStepper();
  } catch (err) {
    status.textContent = "Erro ao gerar: " + err.message;
  }
});

document.getElementById("btnTogglePreviewFloating").addEventListener("click", (e) => {
  const columns = document.querySelector(".app-body");
  const previewColumn = document.getElementById("previewColumn");
  const isCollapsing = !previewColumn.classList.contains("fade-out");

  if (isCollapsing) {
    previewColumn.classList.add("fade-out");
    e.target.textContent = "« Mostrar preview";
    setTimeout(() => {
      previewColumn.classList.add("hidden");
      columns.classList.add("preview-collapsed");
    }, 220);
  } else {
    previewColumn.classList.remove("hidden");
    columns.classList.remove("preview-collapsed");
    void previewColumn.offsetWidth; // força reflow para o fade-in animar
    previewColumn.classList.remove("fade-out");
    e.target.textContent = "Recolher preview »";
  }
});

// --- Zoom e tela cheia do preview ---

function applyZoom() {
  const container = document.getElementById("previewContainer");
  const label = document.getElementById("zoomLabel");
  if (container) container.style.zoom = previewZoom + "%";
  if (label) label.textContent = previewZoom + "%";
}

document.getElementById("btnZoomOut").addEventListener("click", () => {
  previewZoom = Math.max(50, previewZoom - 10);
  applyZoom();
});

document.getElementById("btnZoomIn").addEventListener("click", () => {
  previewZoom = Math.min(150, previewZoom + 10);
  applyZoom();
});

document.getElementById("btnFullscreen").addEventListener("click", () => {
  const wrap = document.getElementById("previewSheetWrap");
  if (document.fullscreenElement === wrap) {
    document.exitFullscreen();
  } else {
    wrap.requestFullscreen().catch(() => {});
  }
});

document.addEventListener("fullscreenchange", () => {
  const wrap = document.getElementById("previewSheetWrap");
  const btn = document.getElementById("btnFullscreen");
  if (btn) btn.textContent = document.fullscreenElement === wrap ? "⛶ Sair da tela cheia" : "⛶ Tela cheia";
});
