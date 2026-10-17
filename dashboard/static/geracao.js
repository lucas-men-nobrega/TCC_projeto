/* =========================================================================
   Painel de Geração — lógica do front-end (unidades geradoras liberadas, ANEEL)
   ========================================================================= */
(() => {
  "use strict";

  // ----------------------------------------------------------------- estado
  const state = {
    meta: null,
    ufs: new Set(),
    muns: new Set(),
    munPorLabel: new Map(),
    munPorCodigo: new Map(),
    anoIni: "",
    anoFim: "",
    sel: { tipo: new Set(), sistema: new Set(), comerc: new Set() },
    all: { tipo: [], sistema: [], comerc: [] },
  };

  const $ = (id) => document.getElementById(id);
  const CORES = {
    UFV: "#f59e0b", EOL: "#10b981", UHE: "#3b82f6", PCH: "#60a5fa",
    CGH: "#93c5fd", UTE: "#94a3b8", UTN: "#a855f7",
  };
  const cor = (t) => CORES[t] || "#cbd5e1";
  const R_MIN = 6, R_MAX = 46;
  const NOMES_SISTEMA = { "Sistema Interligado Nacional": "SIN" };

  // -------------------------------------------------------------- formatação
  const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

  function fmtPot(mw) {
    const v = Math.abs(mw || 0);
    if (v >= 1e3) return `${nf2.format(mw / 1e3)} GW`;
    if (v >= 1) return `${nf1.format(mw)} MW`;
    return `${nf0.format(mw * 1e3)} kW`;
  }
  const fmtInt = (n) => nf0.format(n || 0);
  const fmtCompact = (n) => new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(n || 0);
  const fmtPct = (v, total) => `${nf1.format(total ? (v / total) * 100 : 0)}%`;
  const somaDados = (chart) => chart.data.datasets[0].data.reduce((s, v) => s + (v || 0), 0);
  const nomeTipo = (t) => state.meta?.tipos.find((d) => d.sigla === t)?.nome || t;

  // ---------------------------------------------------------------- UI utils
  function setStatus(txt, kind = "") {
    $("status-text").textContent = txt;
    $("status-pill").className = `status ${kind}`;
  }
  let toastTimer;
  function toast(msg) {
    const el = $("toast");
    el.textContent = msg;
    el.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => el.classList.remove("show"), 6000);
  }

  // --------------------------------------------------------------------- API
  function filtrosQuery() {
    const p = new URLSearchParams();
    if (state.ufs.size) p.set("uf", [...state.ufs].join(","));
    if (state.muns.size) p.set("mun", [...state.muns].join(","));
    if (state.anoIni) p.set("ano_ini", state.anoIni);
    if (state.anoFim) p.set("ano_fim", state.anoFim);
    for (const k of ["tipo", "sistema", "comerc"]) {
      const sel = state.sel[k], all = state.all[k];
      if (sel.size === all.length) continue;            // todos -> sem filtro
      p.set(k, sel.size ? [...sel].join(",") : "__nenhum__");
    }
    return p;
  }

  let controller;
  async function api(rota, params) {
    if (rota === "resumo") { controller?.abort(); controller = new AbortController(); }
    const r = await fetch(`/api/ger/${rota}?${params.toString()}`, { signal: rota === "resumo" ? controller.signal : undefined });
    // Resposta não-JSON (ex.: 404 em HTML) = rota inexistente, em geral servidor desatualizado
    if (!(r.headers.get("Content-Type") || "").includes("json")) {
      throw new Error(r.status === 404
        ? `o servidor não reconhece /api/ger/${rota}. Reinicie o server.py para carregar a versão atual.`
        : `resposta inesperada do servidor (HTTP ${r.status}).`);
    }
    const j = await r.json();
    if (!r.ok) throw new Error(j.erro || r.statusText);
    return j;
  }

  // --------------------------------------------------------------------- MAPA
  const map = L.map("map", { preferCanvas: true, zoomControl: false, minZoom: 3 }).setView([-14.5, -52], 4);
  L.control.zoom({ position: "topleft" }).addTo(map);

  const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
  const attrEsri = "Tiles &copy; Esri · Dados: ANEEL";
  const basemaps = {
    "Escuro (Esri)": L.layerGroup([
      L.tileLayer(`${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, { attribution: attrEsri, maxZoom: 19, maxNativeZoom: 16 }),
      L.tileLayer(`${ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 19, maxNativeZoom: 16, pane: "overlayPane", opacity: 0.85 }),
    ]),
    "Claro (Esri)": L.layerGroup([
      L.tileLayer(`${ESRI}/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`, { attribution: attrEsri, maxZoom: 19, maxNativeZoom: 16 }),
      L.tileLayer(`${ESRI}/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, { maxZoom: 19, maxNativeZoom: 16, pane: "overlayPane" }),
    ]),
    "Ruas (OpenStreetMap)": L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · Dados: ANEEL', maxZoom: 19,
    }),
  };
  basemaps["Escuro (Esri)"].addTo(map);
  L.control.layers(basemaps, null, { position: "topright", collapsed: true }).addTo(map);

  const camada = L.layerGroup().addTo(map);

  function tooltipUF(d) {
    const linhas = d.por_tipo.slice(0, 4).map((t) =>
      `<span class="tt-row"><i style="background:${cor(t.chave)}"></i>${t.chave} · ${fmtPot(t.mw)} (${nf0.format((100 * t.mw) / d.mw)}%)</span>`).join("");
    return `<b>${d.estado} (${d.sigla}) · ${fmtPot(d.mw)}</b><span>${fmtInt(d.usinas)} usinas · ${fmtInt(d.ugs)} UGs</span>${linhas}`;
  }

  function desenharMapa(ufs) {
    camada.clearLayers();
    if (!ufs.length) { $("map-info").textContent = "Nenhuma usina no filtro atual"; atualizarLegenda(0); return; }
    const max = ufs[0].mw || 1;
    // Maiores primeiro → as menores ficam por cima
    for (const d of ufs) {
      const t = Math.sqrt(Math.max(d.mw, 0) / max);       // raiz -> área ∝ potência
      const c = cor(d.tipo_dom);
      L.circleMarker([d.lat, d.lon], {
        radius: R_MIN + (R_MAX - R_MIN) * t, color: c, weight: 1.5, fillColor: c, fillOpacity: 0.35 + 0.25 * t,
      })
        .bindTooltip(tooltipUF(d), { className: "tt", direction: "top", offset: [0, -4] })
        .on("click", () => (d.mun ? alternarMunicipio(d.mun) : alternarEstado(d.sigla)))
        .addTo(camada);
    }
    const porMun = !!ufs[0].mun, n = ufs.length;
    $("map-info").textContent = porMun
      ? `${n} município${n > 1 ? "s" : ""} com usina · clique numa bolha para remover da seleção`
      : `${n} estado${n > 1 ? "s" : ""} · clique numa bolha para adicionar ou remover da seleção`;
    atualizarLegenda(max);
  }

  function atualizarLegenda(max) {
    const box = $("legend-bubbles");
    box.innerHTML = "";
    if (!max) return;
    for (const f of [0.05, 0.3, 1]) {
      const d = Math.round((R_MIN + (R_MAX - R_MIN) * Math.sqrt(f)) * 2 * 0.6);
      box.insertAdjacentHTML("beforeend",
        `<div class="lb"><span class="c" style="width:${d}px;height:${d}px;background:#cbd5e133;border-color:#cbd5e1"></span>${fmtPot(max * f)}</div>`);
    }
  }

  // ------------------------------------------------------------------ GRÁFICOS
  Chart.defaults.color = "#94a3b8";
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.borderColor = "rgba(148,163,184,0.08)";

  const tooltipCfg = {
    backgroundColor: "rgba(15,18,32,0.95)", borderColor: "rgba(148,163,184,0.25)", borderWidth: 1,
    padding: 10, cornerRadius: 10, titleFont: { family: "Outfit", size: 13, weight: "600" },
  };

  const chartTipo = new Chart($("chart-tipo"), {
    type: "doughnut",
    data: { labels: [], datasets: [{ data: [], backgroundColor: [], borderWidth: 2, borderColor: "rgba(15,18,32,0.9)", hoverOffset: 8 }] },
    options: {
      maintainAspectRatio: false, cutout: "68%", animation: { duration: 700 },
      plugins: {
        legend: { display: false },
        tooltip: { ...tooltipCfg, callbacks: { title: (c) => nomeTipo(c[0].label), label: (c) => ` ${fmtPot(c.raw)} · ${fmtPct(c.raw, somaDados(c.chart))}` } },
      },
      onClick: (_, els) => { if (els.length) soEsteValor("tipo", chartTipo.data.labels[els[0].index]); },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
    },
  });

  // Legenda HTML da rosca: categoria · % do total · valor absoluto (clique filtra a categoria)
  function renderLegendaRosca(el, chart, fmt, grupo, titulo = (l) => l) {
    const ds = chart.data.datasets[0], total = somaDados(chart);
    const cores = [].concat(ds.backgroundColor);
    el.innerHTML = chart.data.labels.map((l, i) => `
      <li data-v="${l}" title="${titulo(l)}">
        <span class="nm"><i class="dot" style="background:${cores[i % cores.length]}"></i>${l}</span>
        <span class="pct">${fmtPct(ds.data[i], total)}</span>
        <span class="val">${fmt(ds.data[i])}</span>
      </li>`).join("");
    el.querySelectorAll("li").forEach((li) => li.addEventListener("click", () => soEsteValor(grupo, li.dataset.v)));
  }

  const chartAno = new Chart($("chart-ano"), {
    type: "bar",
    data: { labels: [], datasets: [] },
    options: {
      maintainAspectRatio: false, animation: { duration: 500 },
      plugins: {
        legend: { display: false },
        tooltip: {
          ...tooltipCfg, mode: "index", filter: (i) => i.raw > 0,
          callbacks: {
            label: (c) => ` ${c.dataset.label} · ${fmtPot(c.raw)}`,
            footer: (its) => `Total ${fmtPot(its.reduce((s, i) => s + i.raw, 0))}`,
          },
        },
      },
      scales: {
        x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 0, autoSkip: true, autoSkipPadding: 10 } },
        y: { stacked: true, ticks: { maxTicksLimit: 5, callback: (v) => (v >= 1e3 ? `${fmtCompact(v / 1e3)} GW` : `${fmtCompact(v)} MW`) },
             grid: { color: "rgba(148,163,184,0.06)" } },
      },
    },
  });

  // -------------------------------------------------------------------- RESUMO
  async function atualizarTudo(enquadrar = false) {
    setStatus("Atualizando…");
    document.querySelectorAll(".kpi-value").forEach((el) => el.classList.add("updating"));
    try {
      const r = await api("resumo", filtrosQuery());
      $("kpi-mw").textContent = fmtPot(r.mw);
      $("kpi-mw-sub").textContent = `${nf0.format(r.mw)} MW em operação comercial`;
      $("kpi-usinas").textContent = fmtInt(r.usinas);
      $("kpi-ugs").textContent = fmtInt(r.ugs);
      $("kpi-ugs-sub").textContent = r.usinas ? `${nf1.format(r.ugs / r.usinas)} UGs por usina` : " ";
      $("kpi-renov").textContent = r.pct_renov == null ? "—" : `${nf1.format(r.pct_renov)}%`;

      chartTipo.data.labels = r.por_tipo.map((d) => d.chave);
      chartTipo.data.datasets[0].data = r.por_tipo.map((d) => d.mw);
      chartTipo.data.datasets[0].backgroundColor = r.por_tipo.map((d) => cor(d.chave));
      chartTipo.update();
      renderLegendaRosca($("legend-tipo"), chartTipo, fmtPot, "tipo", nomeTipo);

      chartAno.data.labels = r.por_ano.rotulos;
      chartAno.data.datasets = Object.entries(r.por_ano.series)
        .filter(([, v]) => v.some((x) => x > 0))
        .map(([t, v]) => ({ label: t, data: v, backgroundColor: cor(t), borderRadius: 2, borderSkipped: false,
          categoryPercentage: 0.94, barPercentage: 0.92 }));
      chartAno.update();

      desenharMapa(r.por_uf);
      renderRanking(r.top_usinas);

      if (enquadrar) {
        if (r.bounds) map.fitBounds(r.bounds, { padding: [40, 40], maxZoom: r.nivel_mapa === "mun" ? 9 : 6 });
        else map.setView([-14.5, -52], 4);
      }
      setStatus("Dados atualizados", "ok");
    } catch (e) {
      if (e.name !== "AbortError") { toast(`Erro ao carregar o resumo: ${e.message}`); setStatus("Erro", "err"); }
    } finally {
      document.querySelectorAll(".kpi-value").forEach((el) => el.classList.remove("updating"));
    }
  }

  function renderRanking(lista) {
    const ol = $("ranking");
    if (!lista.length) { ol.innerHTML = `<li class="empty">Sem dados para o filtro atual</li>`; return; }
    const max = lista[0].mw || 1;
    ol.innerHTML = lista.map((u, i) => {
      const anos = u.ano_ini === u.ano_fim ? u.ano_ini : `${u.ano_ini}–${u.ano_fim}`;
      return `
      <li data-uf="${u.sigla}" data-mun="${u.mun || ""}" class="${state.muns.has(u.mun) ? "sel" : ""}"
          title="${u.nome} · ${nomeTipo(u.tipo)} · ${fmtInt(u.ugs)} UGs · liberada em ${anos}&#10;${u.ceg}${u.municipio ? `&#10;Clique para ${state.muns.has(u.mun) ? "remover" : "adicionar"} ${u.municipio} ${state.muns.has(u.mun) ? "da" : "à"} seleção` : ""}">
        <span class="pos">${i + 1}</span>
        <span class="nm"><i class="dot" style="background:${cor(u.tipo)}"></i>${u.nome}<small>${u.tipo} · ${u.municipio ? `${u.municipio}/` : ""}${u.sigla}</small></span>
        <span class="val">${fmtPot(u.mw)}</span>
        <span class="bar" style="width:${(u.mw / max) * 100}%"></span>
      </li>`;
    }).join("");
    ol.querySelectorAll("li[data-uf]").forEach((li) =>
      li.addEventListener("click", () => (li.dataset.mun ? alternarMunicipio(li.dataset.mun) : alternarEstado(li.dataset.uf))));
  }

  // ------------------------------------------------------------------ FILTROS
  function montarChips(grupo, valores, rotulo = (v) => v, comCor = false) {
    const box = $(`chips-${grupo}`);
    state.all[grupo] = valores.map((v) => (typeof v === "object" ? v.sigla : v));
    state.sel[grupo] = new Set(state.all[grupo]);
    box.innerHTML = "";
    valores.forEach((v) => {
      const val = typeof v === "object" ? v.sigla : v;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip active";
      b.dataset.valor = val;
      if (typeof v === "object" && v.nome) b.title = v.nome;
      if (comCor) b.insertAdjacentHTML("beforeend", `<i class="dot" style="background:${cor(val)}"></i>`);
      b.append(rotulo(v));
      b.addEventListener("click", () => {
        const s = state.sel[grupo];
        s.has(val) ? s.delete(val) : s.add(val);
        b.classList.toggle("active", s.has(val));
        atualizarTudo();
      });
      box.appendChild(b);
    });
  }

  function sincronizarChips(grupo) {
    document.querySelectorAll(`#chips-${grupo} .chip`).forEach((b) =>
      b.classList.toggle("active", state.sel[grupo].has(b.dataset.valor)));
  }

  function soEsteValor(grupo, valor) {
    const s = state.sel[grupo];
    state.sel[grupo] = s.size === 1 && s.has(valor) ? new Set(state.all[grupo]) : new Set([valor]);
    sincronizarChips(grupo);
    atualizarTudo();
  }

  document.querySelectorAll("[data-toggle-all]").forEach((btn) =>
    btn.addEventListener("click", () => {
      const g = btn.dataset.toggleAll;
      const todos = state.sel[g].size === state.all[g].length;
      state.sel[g] = todos ? new Set() : new Set(state.all[g]);
      sincronizarChips(g);
      atualizarTudo();
    }));

  // ------------------------------------------------- ESTADOS E MUNICÍPIOS
  // Seleção múltipla, como no painel de consumo: o painel soma os locais selecionados e os
  // municípios refinam os estados (com municípios escolhidos, só as usinas deles entram).
  const nomeUf = (s) => state.meta.ufs.find((u) => u.sigla === s);

  function popularEstados() {
    const sel = $("sel-uf");
    sel.querySelectorAll("option").forEach((o) => { if (o.value) o.disabled = state.ufs.has(o.value); });
    sel.value = "";
  }

  function popularMunicipios() {
    const dl = $("lista-mun");
    state.munPorLabel.clear();
    const frag = document.createDocumentFragment();
    for (const m of state.meta.municipios) {
      if (state.ufs.size && !state.ufs.has(m.sigla)) continue;
      if (state.muns.has(m.mun)) continue;
      const label = `${m.nome} (${m.sigla})`;
      state.munPorLabel.set(label.toLowerCase(), m.mun);
      const o = document.createElement("option");
      o.value = label;
      frag.appendChild(o);
    }
    dl.innerHTML = "";
    dl.appendChild(frag);
  }

  function tag(rotulo, titulo, aoRemover) {
    const el = document.createElement("span");
    el.className = "tag";
    el.title = titulo;
    el.innerHTML = `<span>${rotulo}</span><button type="button" aria-label="Remover ${titulo}">×</button>`;
    el.querySelector("button").addEventListener("click", aoRemover);
    return el;
  }

  function renderSelecao() {
    $("tags-uf").replaceChildren(...[...state.ufs].map((s) =>
      tag(s, nomeUf(s)?.estado || s, () => removerEstado(s))));
    $("tags-mun").replaceChildren(...[...state.muns].map((cod) => {
      const m = state.munPorCodigo.get(cod);
      return tag(`${m.nome} <small>${m.sigla}</small>`, `${m.nome} (${m.sigla})`, () => removerMunicipio(cod));
    }));
    $("btn-clear-uf").hidden = !state.ufs.size;
    $("btn-clear-mun").hidden = !state.muns.size;
    popularEstados();
    popularMunicipios();
    atualizarBotaoComparar();
  }

  function mudouSelecao() { renderSelecao(); atualizarTudo(true); }

  function adicionarEstado(s) {
    if (!s || state.ufs.has(s)) return;
    state.ufs.add(s);
    mudouSelecao();
  }
  function removerEstado(s) {
    state.ufs.delete(s);
    for (const cod of [...state.muns]) if (state.munPorCodigo.get(cod)?.sigla === s) state.muns.delete(cod);
    mudouSelecao();
  }
  function adicionarMunicipio(cod) {
    const m = state.munPorCodigo.get(cod);
    if (!m || state.muns.has(cod)) return;
    state.muns.add(cod);
    if (state.ufs.size && !state.ufs.has(m.sigla)) state.ufs.add(m.sigla);  // mantém o filtro de estados coerente
    mudouSelecao();
  }
  function removerMunicipio(cod) {
    state.muns.delete(cod);
    mudouSelecao();
  }
  const alternarEstado = (s) => (state.ufs.has(s) ? removerEstado : adicionarEstado)(s);
  const alternarMunicipio = (cod) => (state.muns.has(cod) ? removerMunicipio : adicionarMunicipio)(cod);

  $("sel-uf").addEventListener("change", (e) => adicionarEstado(e.target.value));
  $("inp-mun").addEventListener("input", (e) => {
    const cod = state.munPorLabel.get(e.target.value.trim().toLowerCase());
    if (cod) { e.target.value = ""; adicionarMunicipio(cod); }
  });
  $("btn-clear-uf").addEventListener("click", () => { state.ufs.clear(); state.muns.clear(); mudouSelecao(); });
  $("btn-clear-mun").addEventListener("click", () => { state.muns.clear(); mudouSelecao(); });

  // --------------------------------------------------------------- COMPARAÇÃO
  // Compara os municípios selecionados; sem municípios, compara os estados.
  function nivelComparacao() {
    if (state.muns.size >= 2) return "mun";
    if (!state.muns.size && state.ufs.size >= 2) return "uf";
    return null;
  }

  function atualizarBotaoComparar() {
    const nivel = nivelComparacao();
    $("btn-comparar").disabled = !nivel;
    $("btn-comparar-txt").textContent = !nivel ? "Comparar"
      : nivel === "mun" ? `Comparar ${state.muns.size} municípios` : `Comparar ${state.ufs.size} estados`;
    $("compare-hint").textContent = nivel ? "Os demais filtros (tipo, ano, sistema e comercialização) também valem na comparação."
      : state.muns.size === 1 ? "Adicione outro município para comparar."
      : "Selecione 2 ou mais estados (ou municípios) para comparar.";
  }

  const CORES_PERIODO = ["#64748b", "#60a5fa", "#8b5cf6", "#22d3ee"];
  const comp = { dados: null, modo: "pct", charts: {} };
  const rotuloLocal = (i) => `${i.nome} (${i.sigla})`;

  // Barras horizontais empilhadas: uma por local, segmentos = categorias (% do local ou MW)
  function graficoComposicao(id, itens, campo, categorias, corDe) {
    comp.charts[id]?.destroy();
    $(id).parentElement.style.height = `${Math.max(150, 60 + itens.length * 34)}px`;
    const pct = comp.modo === "pct";
    comp.charts[id] = new Chart($(id), {
      type: "bar",
      data: {
        labels: itens.map(rotuloLocal),
        datasets: categorias.map((c, k) => ({
          label: c, backgroundColor: corDe(c, k), borderRadius: 2, borderSkipped: false,
          categoryPercentage: 0.8, barPercentage: 0.95,
          data: itens.map((i) => { const v = i[campo][c] || 0; return pct ? (i.mw ? (100 * v) / i.mw : 0) : v; }),
        })),
      },
      options: {
        indexAxis: "y", maintainAspectRatio: false, animation: { duration: 500 },
        plugins: {
          legend: { position: "top", align: "start", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, color: "#cbd5e1", padding: 12 } },
          tooltip: {
            ...tooltipCfg, mode: "index", filter: (t) => t.raw > 0,
            callbacks: {
              label: (c) => {
                const i = itens[c.dataIndex], abs = i[campo][c.dataset.label] || 0;
                return ` ${c.dataset.label} · ${fmtPct(abs, i.mw)} · ${fmtPot(abs)}`;
              },
            },
          },
        },
        scales: {
          x: { stacked: true, max: pct ? 100 : undefined, grid: { color: "rgba(148,163,184,0.06)" },
               ticks: { maxTicksLimit: 6, callback: (v) => (pct ? `${v}%` : fmtPot(v).replace(/,0+ /, " ")) } },
          y: { stacked: true, grid: { display: false }, ticks: { color: "#cbd5e1", font: { weight: "600" } } },
        },
      },
    });
  }

  function desenharComparacao() {
    const { nivel, itens, periodos } = comp.dados;
    const total = itens.reduce((s, i) => s + i.mw, 0);
    const max = itens[0]?.mw || 1;
    $("comp-th-mun").hidden = nivel === "mun";
    $("comp-tbody").innerHTML = itens.map((i) => `
      <tr>
        <td class="l"><strong>${i.nome}</strong> <small>${i.sigla}</small></td>
        <td><span class="cell-val">${i.mw ? fmtPot(i.mw) : "sem usinas no filtro"}</span><span class="cell-bar"><i style="width:${(i.mw / max) * 100}%"></i></span></td>
        <td>${fmtPct(i.mw, total)}</td>
        <td>${fmtInt(i.usinas)}</td>
        <td>${fmtInt(i.ugs)}</td>
        <td>${i.pct_renov == null ? "—" : `${nf1.format(i.pct_renov)}%`}</td>
        ${nivel === "mun" ? "" : `<td>${fmtInt(i.municipios)}</td>`}
      </tr>`).join("");
    const tipos = state.meta.tipos.map((t) => t.sigla).filter((t) => itens.some((i) => i.por_tipo[t]));
    graficoComposicao("comp-tipo", itens, "por_tipo", tipos, (t) => cor(t));
    graficoComposicao("comp-periodo", itens, "por_periodo", periodos.filter((p) => itens.some((i) => i.por_periodo[p])),
      (p) => CORES_PERIODO[periodos.indexOf(p)]);
  }

  async function abrirComparacao() {
    const nivel = nivelComparacao();
    if (!nivel) return;
    const n = nivel === "mun" ? state.muns.size : state.ufs.size;
    $("comp-titulo").textContent = `Comparação entre ${n} ${nivel === "mun" ? "municípios" : "estados"}`;
    $("comp-sub").textContent = "Potência liberada para operação comercial, com os filtros de tipo, ano, sistema e comercialização aplicados.";
    $("comp-th-mun").hidden = nivel === "mun";
    $("comp-tbody").innerHTML = `<tr><td class="l" colspan="7">Carregando…</td></tr>`;
    $("comp-graficos").hidden = true;
    $("modal-comp").hidden = false;
    document.body.classList.add("modal-open");
    carregarPrevisao();
    comp.dados = null;
    try {
      comp.dados = await api("comparar", filtrosQuery());
      $("comp-graficos").hidden = false;
      desenharComparacao();
    } catch (e) {
      $("comp-tbody").innerHTML = `<tr><td class="l erro" colspan="7">Não foi possível carregar a comparação: ${e.message}</td></tr>`;
    }
  }

  // ---------------------------------------------- PREVISÃO DE EXPANSÃO (T3)
  // Modelo final da Tarefa 3: probabilidade de o local receber nova geração centralizada em
  // 2026–2030 e MW esperados. Independe dos filtros de tipo/ano (prevê qualquer nova usina).
  const prev = { chart: null };
  const fmtProb = (p) => `${nf1.format(100 * p)}%`;
  const medidor = (p) => `<span class="meter"><i style="width:${Math.min(100, 100 * p)}%"></i></span>`;

  async function carregarPrevisao() {
    $("prev-result").hidden = true;
    $("prev-status").className = "prev-status";
    $("prev-status").innerHTML = `<span class="spinner sm"></span> Carregando a previsão…`;
    const p = new URLSearchParams();
    if (state.muns.size) p.set("mun", [...state.muns].join(","));
    else p.set("uf", [...state.ufs].join(","));
    try {
      desenharPrevisao(await api("previsao", p));
      $("prev-status").innerHTML = "";
    } catch (e) {
      $("prev-status").className = "prev-status erro";
      $("prev-status").textContent = `Previsão indisponível: ${e.message}`;
    }
  }

  function desenharPrevisao(r) {
    const m = r.modelo, uf = r.nivel === "uf";
    $("prev-result").hidden = false;  // visível antes de criar o gráfico (oculto, o canvas nasce com tamanho 0)
    $("prev-badge").textContent = `${m.nome} · AUC-PR ${nf2.format(m.auc_pr)} (base ${fmtProb(m.prevalencia)}) · AUC-ROC ${nf2.format(m.auc_roc)}`;
    $("prev-head").innerHTML = uf
      ? `<th class="l">Estado</th><th>Prob. média dos municípios</th><th title="Soma das probabilidades dos municípios">Municípios esperados</th>
         <th>Municípios com prob. ≥ 50%</th><th>MW esperados</th><th title="Usinas em obra no SIGA, sem UG liberada (validação externa)">Em obra (SIGA)</th>`
      : `<th class="l">Município</th><th>Prob. de receber nova geração</th><th>Percentil nacional</th>
         <th>MW esperados</th><th title="Recebeu potência liberada em 2021–2025">Recebeu 2021–2025</th><th title="Usinas em obra no SIGA, sem UG liberada (validação externa)">Em obra (SIGA)</th>`;
    const validos = r.itens.filter((i) => !i.sem_previsao);
    $("prev-tbody").innerHTML = r.itens.map((i) => i.sem_previsao
      ? `<tr><td class="l"><strong>${i.nome}</strong> <small>${i.sigla}</small></td><td colspan="5">sem previsão para este local</td></tr>`
      : uf ? `
      <tr>
        <td class="l"><strong>${i.nome}</strong> <small>${i.sigla}</small>
          <span class="sub">${fmtInt(i.municipios)} municípios · maiores chances: ${i.top.map((t) => `${t.nome} (${fmtProb(t.prob)})`).join(", ")}</span></td>
        <td>${medidor(i.prob)}${fmtProb(i.prob)}</td>
        <td class="destaque">${nf1.format(i.muns_esperados)}</td>
        <td>${fmtInt(i.muns_prob_50)}</td>
        <td>${fmtPot(i.mw_esperado)} <small class="muted">${fmtPct(i.mw_esperado, r.mw_esperado_brasil)} do país</small></td>
        <td>${i.mw_obra ? fmtPot(i.mw_obra) : "—"}</td>
      </tr>` : `
      <tr>
        <td class="l"><strong>${i.nome}</strong> <small>${i.sigla}</small></td>
        <td class="destaque">${medidor(i.prob)}${fmtProb(i.prob)}</td>
        <td>${i.percentil >= 0.5 ? `entre os ${nf0.format(Math.max(1, 100 * (1 - i.percentil)))}% maiores` : `metade inferior`}</td>
        <td>${fmtPot(i.mw_esperado)}</td>
        <td>${i.recebeu ? "sim" : "não"}</td>
        <td>${i.mw_obra ? fmtPot(i.mw_obra) : "—"}</td>
      </tr>`).join("");

    prev.chart?.destroy();
    $("prev-chart").parentElement.style.height = `${Math.max(140, 60 + validos.length * 40)}px`;
    prev.chart = new Chart($("prev-chart"), {
      type: "bar",
      data: {
        labels: validos.map(rotuloLocal),
        datasets: [
          { label: "MW esperados 2026–2030 (modelo)", data: validos.map((i) => i.mw_esperado), backgroundColor: "#22d3ee",
            borderRadius: 4, borderSkipped: false, categoryPercentage: 0.75, barPercentage: 0.9 },
          { label: "Em obra no SIGA (referência)", data: validos.map((i) => i.mw_obra), backgroundColor: "hsl(38 96% 58% / .55)",
            borderColor: "#f59e0b", borderWidth: 1, borderRadius: 4, borderSkipped: false, categoryPercentage: 0.75, barPercentage: 0.9 },
        ],
      },
      options: {
        indexAxis: "y", maintainAspectRatio: false, animation: { duration: 500 },
        plugins: {
          legend: { position: "top", align: "start", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, color: "#cbd5e1", padding: 12 } },
          tooltip: { ...tooltipCfg, callbacks: { label: (c) => ` ${c.dataset.label}: ${fmtPot(c.raw)}` } },
        },
        scales: {
          x: { grid: { color: "rgba(148,163,184,0.06)" }, ticks: { maxTicksLimit: 6, callback: (v) => fmtPot(v).replace(/,0+ /, " ") } },
          y: { grid: { display: false }, ticks: { color: "#cbd5e1", font: { weight: "600" } } },
        },
      },
    });

    $("prev-nota").innerHTML =
      `<strong>Como ler:</strong> a probabilidade é calibrada (isotônica) e vale para <em>qualquer</em> nova potência liberada ` +
      `para operação comercial em ${m.horizonte}; a média nacional é cerca de 8%. ` +
      `MW esperados = probabilidade × mediana dos MW recebidos pelos municípios da UF que receberam em 2021–2025: ` +
      `<strong>ordem de grandeza</strong>, não projeção de leilão. ` +
      (uf ? "Nos estados, \"municípios esperados\" é a soma das probabilidades dos municípios. " : "") +
      `As obras do SIGA não entram no modelo e servem de validação externa: entre os 50 municípios de maior probabilidade, ` +
      `${nf0.format(100 * m.obras_precisao_top50)}% têm usina em obra (AUC-PR ${nf2.format(m.obras_auc_pr)}, contra ` +
      `${nf2.format(m.obras_auc_pr_persistencia)} de quem só repete o passado). Os filtros de tipo, ano, sistema e comercialização não afetam esta seção.`;
  }

  function fecharComparacao() {
    $("modal-comp").hidden = true;
    document.body.classList.remove("modal-open");
  }

  $("btn-comparar").addEventListener("click", abrirComparacao);
  $("btn-fechar-comp").addEventListener("click", fecharComparacao);
  $("modal-comp").addEventListener("click", (e) => { if (e.target.id === "modal-comp") fecharComparacao(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("modal-comp").hidden) fecharComparacao(); });
  $("comp-modo").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    comp.modo = b.dataset.modo;
    $("comp-modo").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    if (comp.dados) desenharComparacao();
  }));


  function definirAnos(ini, fim) {
    state.anoIni = ini === String(state.meta.ano_min) ? "" : ini;
    state.anoFim = fim === String(state.meta.ano_max) ? "" : fim;
    $("sel-ano-ini").value = ini;
    $("sel-ano-fim").value = fim;
    atualizarTudo();
  }
  $("sel-ano-ini").addEventListener("change", (e) => {
    const fim = $("sel-ano-fim").value;
    definirAnos(e.target.value, +e.target.value > +fim ? e.target.value : fim);
  });
  $("sel-ano-fim").addEventListener("change", (e) => {
    const ini = $("sel-ano-ini").value;
    definirAnos(+e.target.value < +ini ? e.target.value : ini, e.target.value);
  });
  $("btn-2014").addEventListener("click", () => definirAnos("2014", String(state.meta.ano_max)));

  $("btn-reset").addEventListener("click", () => {
    state.ufs.clear(); state.muns.clear();
    $("inp-mun").value = "";
    renderSelecao();
    state.anoIni = state.anoFim = "";
    $("sel-ano-ini").value = state.meta.ano_min; $("sel-ano-fim").value = state.meta.ano_max;
    for (const g of ["tipo", "sistema", "comerc"]) { state.sel[g] = new Set(state.all[g]); sincronizarChips(g); }
    atualizarTudo(true);
  });

  // ---------------------------------------------------------------- INÍCIO
  async function iniciar() {
    try {
      const meta = await api("meta", new URLSearchParams());
      state.meta = meta;
      $("data-base").textContent = meta.data_base ? `base de ${meta.data_base}` : "";

      meta.ufs.forEach(({ sigla, estado }) =>
        $("sel-uf").insertAdjacentHTML("beforeend", `<option value="${sigla}">${sigla} — ${estado}</option>`));
      meta.municipios.forEach((m) => state.munPorCodigo.set(m.mun, m));
      renderSelecao();
      for (const id of ["sel-ano-ini", "sel-ano-fim"]) {
        const sel = $(id);
        for (let a = meta.ano_min; a <= meta.ano_max; a++) sel.insertAdjacentHTML("beforeend", `<option value="${a}">${a}</option>`);
      }
      $("sel-ano-ini").value = meta.ano_min;
      $("sel-ano-fim").value = meta.ano_max;

      montarChips("tipo", meta.tipos, (t) => t.sigla, true);
      montarChips("sistema", meta.sistemas, (s) => NOMES_SISTEMA[s] || s);
      montarChips("comerc", meta.comercs);
      $("legend-tipos").innerHTML = meta.tipos.map((t) =>
        `<span><i class="dot" style="background:${cor(t.sigla)}"></i>${t.nome}</span>`).join("");

      atualizarTudo(false);
    } catch (e) {
      setStatus("Servidor indisponível", "err");
      toast(`Não foi possível carregar os metadados: ${e.message}`);
    }
  }
  iniciar();
})();
