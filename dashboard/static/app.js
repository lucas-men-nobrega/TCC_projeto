/* =========================================================================
   Painel de Consumo Energético — lógica do front-end
   ========================================================================= */
(() => {
  "use strict";

  // ----------------------------------------------------------------- estado
  const state = {
    meta: null,
    ufs: new Set(),
    muns: new Set(),
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
  const fmtPct = (v, total) => `${nf1.format(total ? (v / total) * 100 : 0)}%`;
  const somaDados = (chart) => chart.data.datasets[0].data.reduce((s, v) => s + (v || 0), 0);

  function heatRGB(t) {
    t = Math.max(0, Math.min(1, t));
    const pos = t * (HEAT.length - 1);
    const i = Math.min(Math.floor(pos), HEAT.length - 2);
    const f = pos - i;
    const a = hex(HEAT[i]), b = hex(HEAT[i + 1]);
    return a.map((v, k) => Math.round(v + (b[k] - v) * f));
  }
  function heatColor(t) {
    const c = heatRGB(t);
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
    if (state.ufs.size) p.set("uf", [...state.ufs].join(","));
    if (state.muns.size) p.set("mun", [...state.muns].join(","));
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
    // Resposta não-JSON (ex.: 404 em HTML) = rota inexistente, em geral servidor desatualizado
    if (!(r.headers.get("Content-Type") || "").includes("json")) {
      throw new Error(r.status === 404
        ? `o servidor não reconhece /api/${rota}. Reinicie o server.py para carregar a versão atual.`
        : `resposta inesperada do servidor (HTTP ${r.status}).`);
    }
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

  /* Camada de bolhas desenhada num único <canvas>: milhares de círculos por quadro,
     sem criar um objeto Leaflet (e um tooltip) por bolha. O hover é resolvido por
     teste de distância sobre as posições projetadas. */
  const PAD = 0.3;                                       // margem desenhada fora da tela (arrasto)
  const LUT = Array.from({ length: 101 }, (_, i) => heatRGB(i / 100));  // cores pré-calculadas

  const CamadaBolhas = L.Layer.extend({
    onAdd(m) {
      this._pts = [];
      this._xy = new Float64Array(0);                    // x, y, raio (coordenadas de layer)
      this._canvas = L.DomUtil.create("canvas", "camada-bolhas leaflet-zoom-hide");
      m.getPane("overlayPane").appendChild(this._canvas);
      this._tip = L.tooltip({ className: "tt", direction: "top", offset: [0, -4] });
      this._hit = -1;
      m.on("moveend resize", this._desenhar, this);
      m.on("mousemove", this._aoMover, this);
      m.on("mouseout zoomstart", this._limparHover, this);
      this._desenhar();
    },
    onRemove(m) {
      this._canvas.remove();
      m.off("moveend resize", this._desenhar, this);
      m.off("mousemove", this._aoMover, this);
      m.off("mouseout zoomstart", this._limparHover, this);
      this._limparHover();
    },
    setDados(pts) {
      this._pts = pts;
      this._limparHover();
      this._desenhar();
    },
    _desenhar() {
      const m = this._map, cv = this._canvas;
      const tam = m.getSize().multiplyBy(1 + 2 * PAD);
      const origem = m.containerPointToLayerPoint(m.getSize().multiplyBy(-PAD)).round();
      const dpr = window.devicePixelRatio || 1;
      L.DomUtil.setPosition(cv, origem);
      cv.width = Math.round(tam.x * dpr);
      cv.height = Math.round(tam.y * dpr);
      cv.style.width = `${tam.x}px`;
      cv.style.height = `${tam.y}px`;
      const ctx = cv.getContext("2d");
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, tam.x, tam.y);

      const pts = this._pts;
      const xy = (this._xy = new Float64Array(pts.length * 3));
      if (!pts.length) return;
      const maxE = pts[0][2] || 1;                       // servidor envia em ordem decrescente
      ctx.lineWidth = 1;
      // Maiores primeiro → as menores ficam por cima e continuam visíveis
      for (let i = 0; i < pts.length; i++) {
        const [lat, lon, ene] = pts[i];
        const t = Math.sqrt(Math.max(ene, 0) / maxE);     // raiz -> área ∝ energia
        const r = R_MIN + (R_MAX - R_MIN) * t;
        const p = m.latLngToLayerPoint([lat, lon]);
        xy[3 * i] = p.x; xy[3 * i + 1] = p.y; xy[3 * i + 2] = r;
        const [cr, cg, cb] = LUT[Math.round(t * 100)];
        ctx.beginPath();
        ctx.arc(p.x - origem.x, p.y - origem.y, r, 0, 2 * Math.PI);
        ctx.fillStyle = `rgba(${cr},${cg},${cb},${0.35 + 0.3 * t})`;
        ctx.fill();
        ctx.strokeStyle = `rgba(${cr},${cg},${cb},0.9)`;
        ctx.stroke();
      }
    },
    _aoMover(e) {
      if (this._raf) return;                             // no máximo um teste por quadro
      const lp = e.layerPoint;
      this._raf = requestAnimationFrame(() => {
        this._raf = 0;
        const xy = this._xy;
        let hit = -1;
        for (let i = xy.length / 3 - 1; i >= 0; i--) {   // de cima (menores) para baixo
          const dx = lp.x - xy[3 * i], dy = lp.y - xy[3 * i + 1], r = xy[3 * i + 2];
          if (dx * dx + dy * dy <= r * r) { hit = i; break; }
        }
        if (hit === this._hit) return;
        this._hit = hit;
        this._map.getContainer().style.cursor = hit >= 0 ? "pointer" : "";
        if (hit < 0) { this._tip.remove(); return; }
        const [lat, lon, ene, n] = this._pts[hit];
        this._tip
          .setLatLng([lat, lon])
          .setContent(`<b>${fmtEnergia(ene)}</b><span>${fmtInt(n)} UC${n > 1 ? "s" : ""} · média ${fmtEnergia(ene / n)}/UC</span>`);
        if (!this._map.hasLayer(this._tip)) this._tip.addTo(this._map);
      });
    },
    _limparHover() {
      this._hit = -1;
      this._tip?.remove();
      if (this._map) this._map.getContainer().style.cursor = "";
    },
  });
  const camada = new CamadaBolhas().addTo(map);

  function desenharPontos(dados) {
    const pts = dados.pontos;
    camada.setDados(pts);
    if (!pts.length) {
      $("map-info").textContent = "Nenhuma unidade com coordenadas no filtro/área atual";
      atualizarLegenda(0);
      return;
    }
    const maxE = pts[0][2] || 1;
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
        legend: { display: false },
        tooltip: { ...tooltipCfg, callbacks: { label: (c) => ` ${fmtEnergia(c.raw)} · ${fmtPct(c.raw, somaDados(c.chart))}` } },
      },
      onClick: (_, els) => { if (els.length) soEsteValor("gru_ten", chartTen.data.labels[els[0].index]); },
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
      renderLegendaRosca($("legend-ten"), chartTen, fmtEnergia, "gru_ten");

      renderRanking(r.top_municipios);

      if (enquadrar) {
        const selecao = state.ufs.size || state.muns.size;
        if (r.bounds && selecao) map.fitBounds(r.bounds, { padding: [30, 30], maxZoom: 13 });
        else if (!selecao) map.setView([-14.5, -52], 4);
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
      <li data-mun="${m.mun}" class="${state.muns.has(m.mun) ? "sel" : ""}"
          title="${state.muns.has(m.mun) ? `Remover ${m.nome} da seleção` : `Adicionar ${m.nome} à seleção`}">
        <span class="pos">${i + 1}</span>
        <span class="nm">${m.nome}<small>${m.sigla}</small></span>
        <span class="val">${fmtEnergia(m.ene)}</span>
        <span class="bar" style="width:${(m.ene / max) * 100}%"></span>
      </li>`).join("");
    ol.querySelectorAll("li[data-mun]").forEach((li) =>
      li.addEventListener("click", () =>
        (state.muns.has(li.dataset.mun) ? removerMunicipio : adicionarMunicipio)(li.dataset.mun)));
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

  // ------------------------------------------------- ESTADOS E MUNICÍPIOS
  // Seleção múltipla: o painel mostra a soma dos locais selecionados. Municípios refinam
  // os estados (filtro "E"): com municípios escolhidos, só eles entram nos números.
  const nomeUf = (uf) => state.meta.ufs.find((u) => u.uf === uf);

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
      if (state.ufs.size && !state.ufs.has(m.uf)) continue;
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
    $("tags-uf").replaceChildren(...[...state.ufs].map((uf) => {
      const u = nomeUf(uf);
      return tag(u?.sigla || uf, u?.estado || uf, () => removerEstado(uf));
    }));
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

  function adicionarEstado(uf) {
    if (!uf || state.ufs.has(uf)) return;
    state.ufs.add(uf);
    mudouSelecao();
  }
  function removerEstado(uf) {
    state.ufs.delete(uf);
    for (const cod of [...state.muns]) if (state.munPorCodigo.get(cod)?.uf === uf) state.muns.delete(cod);
    mudouSelecao();
  }
  function adicionarMunicipio(cod) {
    const m = state.munPorCodigo.get(cod);
    if (!m || state.muns.has(cod)) return;
    state.muns.add(cod);
    if (state.ufs.size && !state.ufs.has(m.uf)) state.ufs.add(m.uf);  // mantém o filtro de estados coerente
    mudouSelecao();
  }
  function removerMunicipio(cod) {
    state.muns.delete(cod);
    mudouSelecao();
  }

  $("sel-uf").addEventListener("change", (e) => adicionarEstado(e.target.value));
  $("inp-mun").addEventListener("input", (e) => {
    const cod = state.munPorLabel.get(e.target.value.trim().toLowerCase());
    if (cod) { e.target.value = ""; adicionarMunicipio(cod); }
  });
  $("btn-clear-uf").addEventListener("click", () => { state.ufs.clear(); state.muns.clear(); mudouSelecao(); });
  $("btn-clear-mun").addEventListener("click", () => { state.muns.clear(); mudouSelecao(); });

  $("btn-reset").addEventListener("click", () => {
    state.ufs.clear(); state.muns.clear();
    $("inp-mun").value = "";
    renderSelecao();
    for (const g of ["fonte", "gru_ten", "gru_tar"]) { state.sel[g] = new Set(state.all[g]); sincronizarChips(g); }
    atualizarTudo(true);
  });

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
    $("compare-hint").textContent = nivel ? "Os demais filtros (base, tensão e tarifa) também valem na comparação."
      : state.muns.size === 1 ? "Adicione outro município para comparar."
      : "Selecione 2 ou mais estados (ou municípios) para comparar.";
  }

  const CORES_COMP = ["#22d3ee", "#8b5cf6", "#ec4899", "#f59e0b", "#34d399", "#60a5fa", "#f472b6", "#a3e635",
    "#fb923c", "#2dd4bf", "#c084fc", "#facc15", "#f87171", "#818cf8", "#4ade80", "#94a3b8"];
  const comp = { dados: null, modo: "pct", charts: {} };

  // Barras horizontais empilhadas: uma por local, segmentos = categorias (% do local ou kWh)
  function graficoComposicao(id, itens, campo, categorias) {
    comp.charts[id]?.destroy();
    $(id).parentElement.style.height = `${Math.max(150, 60 + itens.length * 34)}px`;
    const pct = comp.modo === "pct";
    const valor = (i, c) => {
      const v = i[campo][c] || 0;
      return pct ? (i.ene ? (v / i.ene) * 100 : 0) : v;
    };
    comp.charts[id] = new Chart($(id), {
      type: "bar",
      data: {
        labels: itens.map((i) => `${i.nome} (${i.sigla})`),
        datasets: categorias.map((c, k) => ({
          label: c, data: itens.map((i) => valor(i, c)), backgroundColor: CORES_COMP[k % CORES_COMP.length],
          borderRadius: 2, borderSkipped: false, categoryPercentage: 0.8, barPercentage: 0.95,
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
                return ` ${c.dataset.label} · ${fmtPct(abs, i.ene)} · ${fmtEnergia(abs)}`;
              },
            },
          },
        },
        scales: {
          x: { stacked: true, max: pct ? 100 : undefined, grid: { color: "rgba(148,163,184,0.06)" },
               ticks: { maxTicksLimit: 6, callback: (v) => (pct ? `${v}%` : fmtEnergia(v).replace(/,00 /, " ")) } },
          y: { stacked: true, grid: { display: false }, ticks: { color: "#cbd5e1", font: { weight: "600" } } },
        },
      },
    });
  }

  // Categorias na ordem do metadado; as que só aparecem nos dados (ex.: N/D) vão ao fim
  function categoriasPresentes(itens, campo, ordem) {
    const vistas = new Set(itens.flatMap((i) => Object.keys(i[campo])));
    const base = ordem.filter((c) => vistas.has(c));
    return base.concat([...vistas].filter((c) => !base.includes(c)));
  }

  function desenharComparacao() {
    const { nivel, itens } = comp.dados;
    const total = itens.reduce((s, i) => s + i.ene, 0);
    const max = itens[0]?.ene || 1;
    $("comp-th-mun").hidden = nivel === "mun";
    $("comp-tbody").innerHTML = itens.length ? itens.map((i) => `
      <tr>
        <td class="l"><strong>${i.nome}</strong> <small>${i.sigla}</small></td>
        <td><span class="cell-val">${fmtEnergia(i.ene)}</span><span class="cell-bar"><i style="width:${(i.ene / max) * 100}%"></i></span></td>
        <td>${fmtPct(i.ene, total)}</td>
        <td>${fmtInt(i.n)}</td>
        <td>${i.n ? fmtEnergia(i.ene / i.n) : "—"}</td>
        ${nivel === "mun" ? "" : `<td>${fmtInt(i.municipios)}</td>`}
      </tr>`).join("")
      : `<tr><td class="l" colspan="6">Sem dados para os filtros atuais.</td></tr>`;
    graficoComposicao("comp-ten", itens, "por_gru_ten", categoriasPresentes(itens, "por_gru_ten", state.meta.gru_ten));
    graficoComposicao("comp-tar", itens, "por_gru_tar", categoriasPresentes(itens, "por_gru_tar", state.meta.gru_tar));
  }

  async function abrirComparacao() {
    const nivel = nivelComparacao();
    if (!nivel) return;
    const n = nivel === "mun" ? state.muns.size : state.ufs.size;
    $("comp-titulo").textContent = `Comparação entre ${n} ${nivel === "mun" ? "municípios" : "estados"}`;
    $("comp-sub").textContent = "Consumo anual das UCs ativas, com os filtros de base, tensão e tarifa aplicados.";
    $("comp-th-mun").hidden = nivel === "mun";
    $("comp-tbody").innerHTML = `<tr><td class="l" colspan="6">Carregando…</td></tr>`;
    $("comp-graficos").hidden = true;
    $("modal-comp").hidden = false;
    document.body.classList.add("modal-open");
    iniciarPrevisao();
    comp.dados = null;
    try {
      comp.dados = await api("comparar", filtrosQuery());
      $("comp-graficos").hidden = false;
      desenharComparacao();
    } catch (e) {
      if (e.name === "AbortError") return;
      $("comp-tbody").innerHTML = `<tr><td class="l erro" colspan="6">Não foi possível carregar a comparação: ${e.message}</td></tr>`;
    }
  }

  function fecharComparacao() {
    $("modal-comp").hidden = true;
    document.body.classList.remove("modal-open");
    clearTimeout(prev.espera);
  }

  // ---------------------------------------------------- PREVISÃO DE NOVA UC
  // Mesmo pedido de ligação simulado em cada local comparado (modelo final da Tarefa 1).
  // Campos vazios = valor típico do grupo de tensão (decidido no servidor).
  const prev = { meta: null, g: "BT", chart: null, espera: null, seq: 0 };
  const CAMPOS_PREV = ["gru_tar", "clas_sub", "cnae2", "fas_con", "are_loc", "ten_forn"];
  const fmtKw = (v) => (v == null ? "—" : `${nf1.format(v)} kW`);

  async function apiPrev(rota, params) {
    const r = await fetch(`/api/prev/${rota}?${params.toString()}`);
    if (!(r.headers.get("Content-Type") || "").includes("json")) {
      throw Object.assign(new Error(r.status === 404
        ? "o servidor não reconhece a previsão. Reinicie o server.py para carregar a versão atual."
        : `resposta inesperada do servidor (HTTP ${r.status}).`), { definitivo: true });
    }
    const j = await r.json();
    if (!r.ok) throw Object.assign(new Error(j.erro || r.statusText), { carregando: !!j.carregando });
    return j;
  }

  function statusPrev(txt, tipo = "") {
    const el = $("prev-status");
    el.className = `prev-status ${tipo}`;
    el.innerHTML = txt;
  }

  // Selects: 1ª opção vazia = "padrão do grupo (valor)"; tarifas filtradas pelo grupo (B* em BT, A* em MT/AT)
  function montarFormPrev() {
    const pad = prev.meta.padroes[prev.g];
    for (const campo of CAMPOS_PREV) {
      const sel = $(`pf-${campo}`), atual = sel.value, chave = campo.toUpperCase();
      let ops = prev.meta.opcoes[campo];
      if (campo === "gru_tar") ops = ops.filter((o) => o.valor.startsWith(prev.g === "BT" ? "B" : "A"));
      const padrao = pad[chave] ?? "—";
      const rot = ops.find((o) => o.valor === padrao)?.rotulo || padrao;
      sel.innerHTML = `<option value="">Padrão do grupo (${rot})</option>` +
        ops.map((o) => `<option value="${o.valor}">${o.rotulo}</option>`).join("");
      sel.value = ops.some((o) => o.valor === atual) ? atual : "";
    }
    $("pf-car_inst").placeholder = `padrão: ${fmtKw(pad.CAR_INST)}`;
    $("pf-dem_cont").placeholder = `padrão: ${fmtKw(pad.DEM_CONT)}`;
    $("pf-box-dem").hidden = prev.g === "BT";
    $("pf-gru_ten").querySelectorAll("button").forEach((b) => b.classList.toggle("active", b.dataset.v === prev.g));
  }

  function paramsPrev() {
    const p = new URLSearchParams();
    if (state.muns.size) p.set("mun", [...state.muns].join(","));
    else p.set("uf", [...state.ufs].join(","));
    p.set("gru_ten", prev.g);
    for (const campo of [...CAMPOS_PREV, "car_inst", "dem_cont"]) {
      const v = $(`pf-${campo}`).value.trim();
      if (v && !(campo === "dem_cont" && prev.g === "BT")) p.set(campo, v);
    }
    if ($("pf-livre").checked) p.set("livre", "1");
    if ($("pf-gd").checked) p.set("gd", "1");
    return p;
  }

  async function iniciarPrevisao() {
    clearTimeout(prev.espera);
    if (!prev.meta) {
      $("prev-form").hidden = true;
      $("prev-result").hidden = true;
      statusPrev(`<span class="spinner sm"></span> Carregando o modelo de previsão…`);
      try {
        prev.meta = await apiPrev("meta", new URLSearchParams());
      } catch (e) {
        if (e.carregando && !$("modal-comp").hidden) {     // servidor ainda lendo o modelo: tenta de novo
          statusPrev(`<span class="spinner sm"></span> ${e.message}. A previsão aparece aqui assim que terminar.`);
          prev.espera = setTimeout(iniciarPrevisao, 4000);
        } else statusPrev(`Previsão indisponível: ${e.message}`, "erro");
        return;
      }
      const d = prev.meta.desempenho;
      $("prev-badge").textContent = `${prev.meta.modelo} · R² ${nf2.format(d.r2)} · erro mediano ${nf0.format(d.mdape)}%`;
      montarFormPrev();
    }
    $("prev-form").hidden = false;
    preverUc();
  }

  async function preverUc() {
    const seq = ++prev.seq;
    statusPrev(`<span class="spinner sm"></span> Calculando…`);
    try {
      const r = await apiPrev("uc", paramsPrev());
      if (seq !== prev.seq) return;                       // chegou uma consulta mais nova
      statusPrev("");
      desenharPrevisao(r);
    } catch (e) {
      if (seq === prev.seq) statusPrev(`Não foi possível prever: ${e.message}`, "erro");
    }
  }
  const preverUcDepois = debounce(preverUc, 450);

  function desenharPrevisao(r) {
    const nomeLocal = (i) => (r.nivel === "uf" ? nomeUf(i.chave)?.estado || i.nome : i.nome);
    $("prev-result").hidden = false;
    $("prev-tbody").innerHTML = r.itens.map((i) => `
      <tr>
        <td class="l"><strong>${nomeLocal(i)}</strong> <small>${i.sigla}</small>
          ${r.nivel === "uf" ? `<span class="sub">média de ${fmtInt(i.municipios)} municípios, ponderada pelas UCs ·
            entre municípios (p10–p90): ${fmtEnergia(i.entre_municipios[0])} a ${fmtEnergia(i.entre_municipios[1])}</span>` : ""}</td>
        <td class="destaque">${fmtEnergia(i.kwh)}<small>/ano</small></td>
        <td>${fmtEnergia(i.kwh / 12)}</td>
        <td>${fmtEnergia(i.faixa[0])} a ${fmtEnergia(i.faixa[1])}</td>
        <td>${i.generica == null ? "—" : fmtEnergia(i.generica)}</td>
        <td>${i.media_existente == null ? "—" : fmtEnergia(i.media_existente)}</td>
      </tr>`).join("");

    // Faixa de 80% (barra flutuante) + valor previsto (ponto), em escala log: as faixas cobrem ~1 ordem de grandeza
    prev.chart?.destroy();
    $("prev-chart").parentElement.style.height = `${Math.max(140, 50 + r.itens.length * 36)}px`;
    prev.chart = new Chart($("prev-chart"), {
      data: {
        labels: r.itens.map((i) => `${nomeLocal(i)} (${i.sigla})`),
        datasets: [
          { type: "bar", label: "Faixa provável (80%)", data: r.itens.map((i) => [Math.max(i.faixa[0], 1), Math.max(i.faixa[1], 1)]),
            backgroundColor: "hsl(258 90% 66% / .28)", borderColor: "hsl(258 90% 66% / .7)", borderWidth: 1,
            borderRadius: 6, borderSkipped: false, barPercentage: 0.55 },
          { type: "line", label: "Consumo previsto", data: r.itens.map((i) => Math.max(i.kwh, 1)), showLine: false,
            pointRadius: 6, pointHoverRadius: 8, pointBackgroundColor: "#22d3ee", pointBorderColor: "#0f1220", pointBorderWidth: 2 },
          { type: "line", label: "Nova UC genérica", data: r.itens.map((i) => i.generica), showLine: false,
            pointStyle: "rectRot", pointRadius: 5, pointBackgroundColor: "transparent", pointBorderColor: "#f59e0b", pointBorderWidth: 2 },
        ],
      },
      options: {
        indexAxis: "y", maintainAspectRatio: false, animation: { duration: 500 },
        plugins: {
          legend: { position: "top", align: "start", labels: { boxWidth: 10, boxHeight: 10, usePointStyle: true, color: "#cbd5e1", padding: 12 } },
          tooltip: {
            ...tooltipCfg,
            callbacks: {
              label: (c) => {
                const i = r.itens[c.dataIndex];
                if (c.datasetIndex === 0) return ` Faixa 80%: ${fmtEnergia(i.faixa[0])} a ${fmtEnergia(i.faixa[1])}`;
                if (c.datasetIndex === 1) return ` Previsto: ${fmtEnergia(i.kwh)}/ano (${fmtEnergia(i.kwh / 12)}/mês)`;
                return ` Nova UC genérica: ${fmtEnergia(i.generica)}/ano`;
              },
            },
          },
        },
        scales: {
          x: { type: "logarithmic", grid: { color: "rgba(148,163,184,0.06)" },
               ticks: { maxRotation: 0, autoSkip: false, callback: (v) => (/^[1]0*$/.test(String(v)) ? fmtEnergia(v).replace(/,0+ /, " ") : "") } },
          y: { grid: { display: false }, ticks: { color: "#cbd5e1", font: { weight: "600" } } },
        },
      },
    });

    const p = r.perfil;
    const desc = Object.entries(p).filter(([k]) => !["LIV", "TEM_GD"].includes(k)).map(([k, v]) => {
      const val = ["CAR_INST", "DEM_CONT"].includes(k) ? fmtKw(v.valor) : v.valor;
      return `<span class="${v.origem === "informado" ? "inf" : ""}">${k} ${val}</span>`;
    }).join(" · ");
    $("prev-perfil").innerHTML = `<strong>Perfil usado (${r.gru_ten}):</strong> ${desc}` +
      `${p.LIV.valor ? " · consumidor livre" : ""}${p.TEM_GD.valor ? " · com GD" : ""}` +
      ` <em>(em destaque: informado; demais: padrão do grupo)</em>` +
      r.avisos.map((a) => `<br><span class="aviso">⚠ ${a}</span>`).join("");
    const r2g = prev.meta.desempenho.r2_grupo[r.gru_ten];
    $("prev-nota").innerHTML =
      `A faixa de 80% vem dos erros do modelo fora da amostra (validação espacial) para o grupo ${r.gru_ten}` +
      `${r2g != null ? ` (R² ${nf2.format(r2g)})` : ""}: a previsão indica a <strong>ordem de grandeza</strong>, não um valor exato. ` +
      `A base de treino não tem a classe residencial (RE), só a residencial rural (RU3).` +
      (r.nivel === "uf" ? " Nos estados, a previsão é feita em cada município e resumida pela média ponderada pelas UCs existentes." : "");
  }

  $("pf-gru_ten").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    if (prev.g === b.dataset.v) return;
    prev.g = b.dataset.v;
    montarFormPrev();
    preverUc();
  }));
  $("prev-form").addEventListener("change", (e) => { if (e.target.type !== "number") preverUc(); });
  $("prev-form").addEventListener("input", (e) => { if (e.target.type === "number") preverUcDepois(); });
  $("prev-form").addEventListener("submit", (e) => { e.preventDefault(); preverUc(); });
  $("pf-reset").addEventListener("click", () => {
    $("prev-form").querySelectorAll("select, input[type=number]").forEach((el) => { el.value = ""; });
    $("pf-livre").checked = $("pf-gd").checked = false;
    preverUc();
  });

  $("btn-comparar").addEventListener("click", abrirComparacao);
  $("btn-fechar-comp").addEventListener("click", fecharComparacao);
  $("modal-comp").addEventListener("click", (e) => { if (e.target.id === "modal-comp") fecharComparacao(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !$("modal-comp").hidden) fecharComparacao(); });
  $("comp-modo").querySelectorAll("button").forEach((b) => b.addEventListener("click", () => {
    comp.modo = b.dataset.modo;
    $("comp-modo").querySelectorAll("button").forEach((x) => x.classList.toggle("active", x === b));
    if (comp.dados) desenharComparacao();
  }));

  // ---------------------------------------------------------------- INÍCIO
  async function iniciar() {
    try {
      const meta = await api("meta", new URLSearchParams());
      state.meta = meta;
      meta.municipios.forEach((m) => state.munPorCodigo.set(m.mun, m));

      const sel = $("sel-uf");
      meta.ufs.forEach(({ uf, sigla, estado }) => sel.insertAdjacentHTML("beforeend",
        `<option value="${uf}">${sigla} — ${estado}</option>`));
      renderSelecao();

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
