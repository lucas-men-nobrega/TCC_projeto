/* =========================================================================
   Painel de Geração — lógica do front-end (unidades geradoras liberadas, ANEEL)
   ========================================================================= */
(() => {
  "use strict";

  // ----------------------------------------------------------------- estado
  const state = {
    meta: null,
    uf: "",
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
    if (state.uf) p.set("uf", state.uf);
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
        .on("click", () => selecionarUF(state.uf === d.sigla ? "" : d.sigla))
        .addTo(camada);
    }
    $("map-info").textContent = `${ufs.length} estado${ufs.length > 1 ? "s" : ""} · clique numa bolha para filtrar`;
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
        legend: { position: "right", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, color: "#cbd5e1", padding: 10 } },
        tooltip: { ...tooltipCfg, callbacks: { title: (c) => nomeTipo(c[0].label), label: (c) => ` ${fmtPot(c.raw)}` } },
      },
      onClick: (_, els) => { if (els.length) soEsteValor("tipo", chartTipo.data.labels[els[0].index]); },
      onHover: (e, els) => { e.native.target.style.cursor = els.length ? "pointer" : "default"; },
    },
  });

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
        x: { stacked: true, grid: { display: false }, ticks: { maxRotation: 90, autoSkip: true, autoSkipPadding: 4 } },
        y: { stacked: true, ticks: { callback: (v) => `${fmtCompact(v)} MW` }, grid: { color: "rgba(148,163,184,0.06)" } },
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

      chartAno.data.labels = r.por_ano.rotulos;
      chartAno.data.datasets = Object.entries(r.por_ano.series)
        .filter(([, v]) => v.some((x) => x > 0))
        .map(([t, v]) => ({ label: t, data: v, backgroundColor: cor(t), borderRadius: 2, borderSkipped: false }));
      chartAno.update();

      desenharMapa(r.por_uf);
      renderRanking(r.top_usinas);

      if (enquadrar) {
        if (r.bounds) map.fitBounds(r.bounds, { padding: [30, 30], maxZoom: 6 });
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
      <li data-uf="${u.sigla}" title="${u.nome} · ${nomeTipo(u.tipo)} · ${fmtInt(u.ugs)} UGs · liberada em ${anos}&#10;${u.ceg}">
        <span class="pos">${i + 1}</span>
        <span class="nm"><i class="dot" style="background:${cor(u.tipo)}"></i>${u.nome}<small>${u.tipo} · ${u.sigla}</small></span>
        <span class="val">${fmtPot(u.mw)}</span>
        <span class="bar" style="width:${(u.mw / max) * 100}%"></span>
      </li>`;
    }).join("");
    ol.querySelectorAll("li[data-uf]").forEach((li) =>
      li.addEventListener("click", () => selecionarUF(li.dataset.uf)));
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

  function selecionarUF(sigla) {
    state.uf = sigla;
    $("sel-uf").value = sigla;
    atualizarTudo(true);
  }
  $("sel-uf").addEventListener("change", (e) => selecionarUF(e.target.value));

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
    state.uf = ""; $("sel-uf").value = "";
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
