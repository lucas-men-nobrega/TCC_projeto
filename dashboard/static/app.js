/* =========================================================================
   Painel de Consumo Energético — lógica do front-end
   ========================================================================= */
(() => {
  "use strict";

  // ----------------------------------------------------------------- estado
  const state = {
    meta: null,
    uf: "",
    mun: "",
    sel: { fonte: new Set(), gru_ten: new Set(), gru_tar: new Set() },
    all: { fonte: [], gru_ten: [], gru_tar: [] },
    munPorLabel: new Map(),
    munPorCodigo: new Map(),
  };

  const $ = (id) => document.getElementById(id);
  const HEAT = ["#22d3ee", "#6366f1", "#a855f7", "#ec4899", "#f59e0b"];
  const R_MIN = 2.5, R_MAX = 34;

  // -------------------------------------------------------------- formatação
  const nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  const nf1 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 1, minimumFractionDigits: 1 });
  const nf2 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2, minimumFractionDigits: 2 });

  function fmtEnergia(kwh) {
    const v = Math.abs(kwh || 0);
    if (v >= 1e9) return `${nf2.format(kwh / 1e9)} TWh`;
    if (v >= 1e6) return `${nf2.format(kwh / 1e6)} GWh`;
    if (v >= 1e3) return `${nf1.format(kwh / 1e3)} MWh`;
    return `${nf0.format(kwh)} kWh`;
  }
  const fmtInt = (n) => nf0.format(n || 0);
  const fmtCompact = (n) => new Intl.NumberFormat("pt-BR", { notation: "compact", maximumFractionDigits: 1 }).format(n || 0);

  function heatColor(t) {
    t = Math.max(0, Math.min(1, t));
    const pos = t * (HEAT.length - 1);
    const i = Math.min(Math.floor(pos), HEAT.length - 2);
    const f = pos - i;
    const a = hex(HEAT[i]), b = hex(HEAT[i + 1]);
    const c = a.map((v, k) => Math.round(v + (b[k] - v) * f));
    return `rgb(${c[0]},${c[1]},${c[2]})`;
  }
  const hex = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));

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
  const debounce = (fn, ms) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

  // --------------------------------------------------------------------- API
  function filtrosQuery() {
    const p = new URLSearchParams();
    if (state.uf) p.set("uf", state.uf);
    if (state.mun) p.set("mun", state.mun);
    for (const k of ["fonte", "gru_ten", "gru_tar"]) {
      const sel = state.sel[k], all = state.all[k];
      if (sel.size === all.length) continue;            // todos -> sem filtro
      p.set(k, sel.size ? [...sel].join(",") : "__nenhum__");
    }
    return p;
  }

  const controllers = {};
  async function api(rota, params) {
    controllers[rota]?.abort();
    const ctl = (controllers[rota] = new AbortController());
    const r = await fetch(`/api/${rota}?${params.toString()}`, { signal: ctl.signal });
    const j = await r.json();
    if (!r.ok) throw new Error(j.erro || r.statusText);
    return j;
  }

  // --------------------------------------------------------------------- MAPA
  const map = L.map("map", { preferCanvas: true, zoomControl: false, minZoom: 3, worldCopyJump: false })
    .setView([-14.5, -52], 4);
  L.control.zoom({ position: "topleft" }).addTo(map);

  // Mapas base sem necessidade de API key
  const ESRI = "https://server.arcgisonline.com/ArcGIS/rest/services";
  const attrEsri = "Tiles &copy; Esri · Dados: BDGD/ANEEL";
  const basemaps = {
    "Escuro (Esri)": L.layerGroup([
      L.tileLayer(`${ESRI}/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}`, {
        attribution: attrEsri, maxZoom: 19, maxNativeZoom: 16,
      }),
      L.tileLayer(`${ESRI}/Canvas/World_Dark_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, {
        maxZoom: 19, maxNativeZoom: 16, pane: "overlayPane", opacity: 0.85,
      }),
    ]),
    "Claro (Esri)": L.layerGroup([
      L.tileLayer(`${ESRI}/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}`, {
        attribution: attrEsri, maxZoom: 19, maxNativeZoom: 16,
      }),
      L.tileLayer(`${ESRI}/Canvas/World_Light_Gray_Reference/MapServer/tile/{z}/{y}/{x}`, {
        maxZoom: 19, maxNativeZoom: 16, pane: "overlayPane",
      }),
    ]),
    "Ruas (OpenStreetMap)": L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> · Dados: BDGD/ANEEL',
      maxZoom: 19,
    }),
    "Satélite (Esri)": L.tileLayer(`${ESRI}/World_Imagery/MapServer/tile/{z}/{y}/{x}`, {
      attribution: "Imagens &copy; Esri, Maxar, Earthstar · Dados: BDGD/ANEEL", maxZoom: 19, maxNativeZoom: 18,
    }),
  };
  basemaps["Escuro (Esri)"].addTo(map);
  L.control.layers(basemaps, null, { position: "topright", collapsed: true }).addTo(map);

  const renderer = L.canvas({ padding: 0.3 });
  const camada = L.layerGroup().addTo(map);

  function desenharPontos(dados) {
    camada.clearLayers();
    const pts = dados.pontos;
    if (!pts.length) {
      $("map-info").textContent = "Nenhuma unidade com coordenadas no filtro/área atual";
      atualizarLegenda(0);
      return;
    }
    const maxE = pts[0][2] || 1;                         // servidor envia em ordem decrescente
    for (const [lat, lon, ene, n] of pts) {
      const t = Math.sqrt(Math.max(ene, 0) / maxE);       // raiz -> área ∝ energia
      const cor = heatColor(t);
      const m = L.circleMarker([lat, lon], {
        renderer,
        radius: R_MIN + (R_MAX - R_MIN) * t,
        color: cor,
        weight: 1,
        opacity: 0.9,
        fillColor: cor,
        fillOpacity: 0.35 + 0.3 * t,
      });
      m.bindTooltip(
        () => `<b>${fmtEnergia(ene)}</b><span>${fmtInt(n)} UC${n > 1 ? "s" : ""} · média ${fmtEnergia(ene / n)}/UC</span>`,
        { className: "tt", direction: "top", offset: [0, -4] }
      );
      camada.addLayer(m);
    }
    const km = dados.celula_graus * 111;
    const agreg = km < 0.2 ? "coordenadas individuais (~110 m)" : `agregado em células de ~${km >= 10 ? nf0.format(km) : nf1.format(km)} km`;
    $("map-info").textContent =
      `${fmtInt(pts.length)} bolhas · ${agreg}` + (dados.truncado ? ` · exibindo as ${fmtInt(pts.length)} maiores` : "");
    atualizarLegenda(maxE);
  }

  function atualizarLegenda(maxE) {
    const box = $("legend-bubbles");
    box.innerHTML = "";
    if (!maxE) return;
    for (const f of [0.05, 0.3, 1]) {
      const r = R_MIN + (R_MAX - R_MIN) * Math.sqrt(f);
      const d = Math.round(r * 2 * 0.75);
      box.insertAdjacentHTML("beforeend",
        `<div class="lb"><span class="c" style="width:${d}px;height:${d}px;background:${heatColor(Math.sqrt(f))}55;border-color:${heatColor(Math.sqrt(f))}"></span>${fmtEnergia(maxE * f)}</div>`);
    }
  }

  async function carregarPontos() {
    const b = map.getBounds();
    const p = filtrosQuery();
    p.set("bbox", [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()].map((v) => v.toFixed(4)).join(","));
    p.set("zoom", map.getZoom());
    $("map-loading").classList.add("show");
    try {
      desenharPontos(await api("pontos", p));
      setStatus("Dados atualizados", "ok");
    } catch (e) {
      if (e.name !== "AbortError") { toast(`Erro ao carregar o mapa: ${e.message}`); setStatus("Erro", "err"); }
    } finally {
      $("map-loading").classList.remove("show");
    }
  }
  map.on("moveend", debounce(carregarPontos, 250));

  // ------------------------------------------------------------------ GRÁFICOS
  Chart.defaults.color = "#94a3b8";
  Chart.defaults.font.family = "Inter, system-ui, sans-serif";
  Chart.defaults.font.size = 11;
  Chart.defaults.borderColor = "rgba(148,163,184,0.08)";

  const tooltipCfg = {
    backgroundColor: "rgba(15,18,32,0.95)", borderColor: "rgba(148,163,184,0.25)", borderWidth: 1,
    padding: 10, cornerRadius: 10, titleFont: { family: "Outfit", size: 13, weight: "600" },
    callbacks: { label: (c) => ` ${fmtEnergia(c.raw)}` },
  };

  function gradiente(ctx, area) {
    const g = ctx.createLinearGradient(area.left, 0, area.right, 0);
    g.addColorStop(0, "#22d3ee"); g.addColorStop(0.6, "#8b5cf6"); g.addColorStop(1, "#ec4899");
    return g;
  }

  const chartTar = new Chart($("chart-tar"), {
    type: "bar",
    data: { labels: [], datasets: [{ data: [], borderRadius: 6, borderSkipped: false,
      backgroundColor: (c) => (c.chart.chartArea ? gradiente(c.chart.ctx, c.chart.chartArea) : "#6366f1") }] },
    options: {
      indexAxis: "y", maintainAspectRatio: false, animation: { duration: 600 },
      plugins: { legend: { display: false }, tooltip: tooltipCfg },
      scales: {
        x: { ticks: { callback: (v) => fmtCompact(v) }, grid: { color: "rgba(148,163,184,0.06)" } },
        y: { grid: { display: false }, ticks: { color: "#cbd5e1", font: { weight: "600" } } },
      },
      onClick: (_, els) => { if (els.length) soEsteValor("gru_tar", chartTar.data.labels[els[0].index]); },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
    },
  });

  const chartTen = new Chart($("chart-ten"), {
    type: "doughnut",
    data: { labels: [], datasets: [{ data: [], borderWidth: 2, borderColor: "rgba(15,18,32,0.9)", hoverOffset: 8,
      backgroundColor: ["#22d3ee", "#8b5cf6", "#ec4899", "#f59e0b", "#34d399", "#60a5fa", "#f472b6"] }] },
    options: {
      maintainAspectRatio: false, cutout: "68%", animation: { duration: 700 },
      plugins: {
        legend: { position: "right", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, color: "#cbd5e1", padding: 10 } },
        tooltip: tooltipCfg,
      },
      onClick: (_, els) => { if (els.length) soEsteValor("gru_ten", chartTen.data.labels[els[0].index]); },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
    },
  });

  // -------------------------------------------------------------------- RESUMO
  async function carregarResumo(enquadrar) {
    document.querySelectorAll(".kpi-value").forEach((el) => el.classList.add("updating"));
    try {
      const r = await api("resumo", filtrosQuery());
      $("kpi-energia").textContent = fmtEnergia(r.energia_total);
      $("kpi-energia-sub").textContent = `${fmtInt(r.energia_total)} kWh`;
      $("kpi-ucs").textContent = fmtInt(r.ucs);
      $("kpi-ucs-sub").textContent = r.ucs_sem_coord ? `${fmtInt(r.ucs_sem_coord)} sem coordenadas válidas` : "todas georreferenciadas";
      $("kpi-mun").textContent = fmtInt(r.municipios);
      $("kpi-media").textContent = r.ucs ? fmtEnergia(r.energia_total / r.ucs) : "—";

      chartTar.data.labels = r.por_gru_tar.map((d) => d.chave);
      chartTar.data.datasets[0].data = r.por_gru_tar.map((d) => d.ene);
      chartTar.update();
      chartTen.data.labels = r.por_gru_ten.map((d) => d.chave);
      chartTen.data.datasets[0].data = r.por_gru_ten.map((d) => d.ene);
      chartTen.update();

      renderRanking(r.top_municipios);

      if (enquadrar) {
        if (r.bounds && (state.uf || state.mun)) map.fitBounds(r.bounds, { padding: [30, 30], maxZoom: 13 });
        else if (!state.uf && !state.mun) map.setView([-14.5, -52], 4);
      }
    } catch (e) {
      if (e.name !== "AbortError") { toast(`Erro ao carregar o resumo: ${e.message}`); setStatus("Erro", "err"); }
    } finally {
      document.querySelectorAll(".kpi-value").forEach((el) => el.classList.remove("updating"));
    }
  }

  function renderRanking(lista) {
    const ol = $("ranking");
    if (!lista.length) { ol.innerHTML = `<li class="empty">Sem dados para o filtro atual</li>`; return; }
    const max = lista[0].ene || 1;
    ol.innerHTML = lista.map((m, i) => `
      <li data-mun="${m.mun}" title="Filtrar ${m.nome}">
        <span class="pos">${i + 1}</span>
        <span class="nm">${m.nome}<small>${m.uf}</small></span>
        <span class="val">${fmtEnergia(m.ene)}</span>
        <span class="bar" style="width:${(m.ene / max) * 100}%"></span>
      </li>`).join("");
    ol.querySelectorAll("li[data-mun]").forEach((li) =>
      li.addEventListener("click", () => selecionarMunicipio(li.dataset.mun)));
  }

  // ------------------------------------------------------------------ FILTROS
  function atualizarTudo(enquadrar = false) {
    setStatus("Atualizando…");
    carregarResumo(enquadrar);
    if (!enquadrar) carregarPontos();                   // se enquadrar, o moveend dispara
    else setTimeout(carregarPontos, 900);               // garante atualização mesmo sem movimento
  }

  function montarChips(grupo, valores, rotulo = (v) => v) {
    const box = $(`chips-${grupo}`);
    state.all[grupo] = valores.map((v) => (typeof v === "object" ? v.sigla : v));
    state.sel[grupo] = new Set(state.all[grupo]);
    box.innerHTML = "";
    valores.forEach((v) => {
      const val = typeof v === "object" ? v.sigla : v;
      const b = document.createElement("button");
      b.type = "button";
      b.className = "chip active";
      b.textContent = rotulo(v);
      b.dataset.valor = val;
      b.id = `chip-${grupo}-${val}`.replace(/\s+/g, "_");
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

  function popularMunicipios() {
    const dl = $("lista-mun");
    state.munPorLabel.clear();
    const frag = document.createDocumentFragment();
    for (const m of state.meta.municipios) {
      if (state.uf && m.uf !== state.uf) continue;
      const label = `${m.nome} (${m.uf})`;
      state.munPorLabel.set(label.toLowerCase(), m.mun);
      const o = document.createElement("option");
      o.value = label;
      frag.appendChild(o);
    }
    dl.innerHTML = "";
    dl.appendChild(frag);
  }

  function selecionarMunicipio(cod) {
    const m = state.munPorCodigo.get(cod);
    if (!m) return;
    state.mun = cod;
    if (state.uf && state.uf !== m.uf) { state.uf = m.uf; $("sel-uf").value = m.uf; popularMunicipios(); }
    $("inp-mun").value = `${m.nome} (${m.uf})`;
    $("inp-mun").parentElement.classList.add("has-value");
    atualizarTudo(true);
  }

  function limparMunicipio(atualizar = true) {
    $("inp-mun").value = "";
    $("inp-mun").parentElement.classList.remove("has-value");
    if (state.mun) { state.mun = ""; if (atualizar) atualizarTudo(true); }
  }

  $("sel-uf").addEventListener("change", (e) => {
    state.uf = e.target.value;
    limparMunicipio(false);
    popularMunicipios();
    atualizarTudo(true);
  });

  $("inp-mun").addEventListener("input", (e) => {
    const v = e.target.value.trim().toLowerCase();
    e.target.parentElement.classList.toggle("has-value", !!v);
    const cod = state.munPorLabel.get(v);
    if (cod) selecionarMunicipio(cod);
    else if (!v) limparMunicipio();
  });
  $("btn-clear-mun").addEventListener("click", () => limparMunicipio());

  $("btn-reset").addEventListener("click", () => {
    state.uf = ""; $("sel-uf").value = "";
    state.mun = ""; limparMunicipio(false);
    popularMunicipios();
    for (const g of ["fonte", "gru_ten", "gru_tar"]) { state.sel[g] = new Set(state.all[g]); sincronizarChips(g); }
    atualizarTudo(true);
  });

  // ---------------------------------------------------------------- INÍCIO
  async function iniciar() {
    try {
      const meta = await api("meta", new URLSearchParams());
      state.meta = meta;
      meta.municipios.forEach((m) => state.munPorCodigo.set(m.mun, m));

      const sel = $("sel-uf");
      meta.ufs.forEach(({ uf, estado }) => sel.insertAdjacentHTML("beforeend",
        `<option value="${uf}">${uf} — ${estado}</option>`));
      popularMunicipios();

      montarChips("fonte", meta.fontes, (f) => f.nome);
      montarChips("gru_ten", meta.gru_ten);
      montarChips("gru_tar", meta.gru_tar);

      atualizarTudo(false);
    } catch (e) {
      setStatus("Servidor indisponível", "err");
      toast(`Não foi possível carregar os metadados: ${e.message}`);
    }
  }
  iniciar();
})();
