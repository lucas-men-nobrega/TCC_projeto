"""Gera a apresentação do TCC com a identidade visual dos dashboards (Inter + Dancing Script, tema creme/siena)."""
import sys
from pptx import Presentation
from pptx.util import Inches, Pt, Emu
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE, MSO_CONNECTOR
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.chart.data import CategoryChartData
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION, XL_MARKER_STYLE, XL_TICK_LABEL_POSITION
from pptx.oxml.ns import qn
import os

OUT = sys.argv[1]

# ---- tokens do dashboard (dashboard/static/style.css + app.js) ----
BG = "F7F2E8"; BG2 = "FBF8F1"; SURFACE = "FFFDF8"; BORDER = "EBE3D3"; BORDER_STRONG = "DDD2BD"
TEXT = "2F2A23"; TEXT2 = "5F574B"; TEXT3 = "938A7B"
ACCENT = "A0522D"; ACCENT_SOFT = "F3E6D8"; ACCENT2 = "C9A27E"; SAGE = "7D9A78"; WARM = "C98A2B"
GOLD = "D9A05B"; BLUE = "5B7C99"; MUTED = "C9B79C"; MUTED2 = "9A8C7E"; DEEP = "7A2A1E"
TITLE_FONT = "Dancing Script"; BODY = os.environ.get("QA_BODY_FONT", "Inter")  # QA: Arial tem métrica próxima da Inter

W, H = 13.333, 7.5
prs = Presentation()
prs.slide_width = Inches(W); prs.slide_height = Inches(H)
BLANK = prs.slide_layouts[6]
FOOTER = "Consumo e expansão do mercado de energia elétrica · BDGD/ANEEL"


def rgb(h):
    return RGBColor.from_string(h)


def set_bg(slide, color):
    f = slide.background.fill
    f.solid(); f.fore_color.rgb = rgb(color)


def text(slide, x, y, w, h, paras, size=16, color=TEXT, font=BODY, bold=False, align=PP_ALIGN.LEFT,
         anchor=MSO_ANCHOR.TOP, spacing=None, after=0, name=None):
    """paras: str | list[str | list[(texto, {opts})]]"""
    tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
    if name:
        tb.name = name
    tf = tb.text_frame
    tf.word_wrap = True
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = anchor
    if isinstance(paras, str):
        paras = [paras]
    for i, p in enumerate(paras):
        par = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        par.alignment = align
        if spacing:
            par.line_spacing = spacing
        par.space_after = Pt(after)
        runs = [(p, {})] if isinstance(p, str) else p
        for t, o in runs:
            r = par.add_run(); r.text = t
            f = r.font
            f.name = o.get("font", font); f.size = Pt(o.get("size", size)); f.bold = o.get("bold", bold)
            f.italic = o.get("italic", False)
            f.color.rgb = rgb(o.get("color", color))
            if o.get("spc"):
                r._r.get_or_add_rPr().set("spc", str(o["spc"]))
    return tb


def card(slide, x, y, w, h, fill=SURFACE, line=BORDER, radius=0.14, name=None):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(h))
    s.adjustments[0] = min(0.5, radius / min(w, h))
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line); s.line.width = Pt(0.75)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    if name:
        s.name = name
    return s


def badge(slide, x, y, d, label, fill=ACCENT_SOFT, color=ACCENT, size=16, line=BORDER_STRONG):
    s = slide.shapes.add_shape(MSO_SHAPE.OVAL, Inches(x), Inches(y), Inches(d), Inches(d))
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill)
    if line:
        s.line.color.rgb = rgb(line); s.line.width = Pt(0.75)
    else:
        s.line.fill.background()
    s.shadow.inherit = False
    tf = s.text_frame
    tf.margin_left = tf.margin_right = tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = label
    r.font.name = BODY; r.font.size = Pt(size); r.font.bold = True; r.font.color.rgb = rgb(color)
    return s


def chip(slide, x, y, w, label, fill=ACCENT_SOFT, color=ACCENT, size=11):
    s = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(x), Inches(y), Inches(w), Inches(0.32))
    s.adjustments[0] = 0.5
    s.fill.solid(); s.fill.fore_color.rgb = rgb(fill); s.line.fill.background(); s.shadow.inherit = False
    tf = s.text_frame
    tf.margin_left = tf.margin_right = Inches(0.08); tf.margin_top = tf.margin_bottom = 0
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p = tf.paragraphs[0]; p.alignment = PP_ALIGN.CENTER
    r = p.add_run(); r.text = label
    r.font.name = BODY; r.font.size = Pt(size); r.font.bold = True; r.font.color.rgb = rgb(color)
    return s


slide_no = [0]


def content_slide(kicker, title, notes=None):
    s = prs.slides.add_slide(BLANK)
    slide_no[0] += 1
    set_bg(s, BG)
    text(s, 0.6, 0.42, 10, 0.3, [[(kicker.upper(), {"spc": 150, "bold": True})]], size=11, color=TEXT3, name="Kicker")
    text(s, 0.6, 0.68, 12.1, 0.9, title, size=38, font=TITLE_FONT, bold=True, color=TEXT,
         anchor=MSO_ANCHOR.MIDDLE, name="Título")
    text(s, 0.6, 7.02, 9, 0.25, FOOTER, size=9, color=TEXT3, name="Rodapé")
    text(s, 11.73, 7.02, 1.0, 0.25, str(slide_no[0]), size=9, color=TEXT3, align=PP_ALIGN.RIGHT, name="Número")
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def divider_slide(kicker, title, subtitle, notes=None):
    s = prs.slides.add_slide(BLANK)
    slide_no[0] += 1
    set_bg(s, ACCENT)
    text(s, 0.9, 2.45, 11, 0.35, [[(kicker.upper(), {"spc": 200, "bold": True})]], size=13, color=ACCENT_SOFT)
    text(s, 0.9, 2.85, 11.5, 1.4, title, size=66, font=TITLE_FONT, bold=True, color=SURFACE, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 0.9, 4.35, 11, 0.9, subtitle, size=18, color=ACCENT_SOFT)
    if notes:
        s.notes_slide.notes_text_frame.text = notes
    return s


def stat(slide, x, y, w, h, value, label, sub=None, value_color=ACCENT, vsize=40, label_lines=1):
    card(slide, x, y, w, h)
    text(slide, x + 0.3, y + 0.25, w - 0.6, 0.8, value, size=vsize, bold=True, color=value_color, anchor=MSO_ANCHOR.BOTTOM)
    text(slide, x + 0.3, y + 1.12, w - 0.6, 0.35 * label_lines, label, size=14, bold=True, color=TEXT, spacing=1.0)
    if sub:
        sy = y + 1.5 + 0.27 * (label_lines - 1)
        text(slide, x + 0.3, sy, w - 0.6, h - (sy - y) - 0.15, sub, size=11, color=TEXT2, spacing=1.1)


def br(v, d=0, signed=False, suffix=""):
    """Número no formato brasileiro."""
    s = f"{v:+,.{d}f}" if signed else f"{v:,.{d}f}"
    return s.replace(",", "X").replace(".", ",").replace("X", ".").replace("-", "−") + suffix


# ---------------------------------------------------------------- charts
def style_chart(chart, legend=False):
    chart.has_title = False
    chart.font.name = BODY; chart.font.size = Pt(11); chart.font.color.rgb = rgb(TEXT2)
    chart.has_legend = legend
    if legend:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(11); chart.legend.font.color.rgb = rgb(TEXT2); chart.legend.font.name = BODY


def quiet_axes(chart, show_val=False, val_fmt=None, gridlines=False):
    ca = chart.category_axis
    ca.format.line.color.rgb = rgb(BORDER_STRONG)
    ca.tick_labels.font.size = Pt(11); ca.tick_labels.font.color.rgb = rgb(TEXT2); ca.tick_labels.font.name = BODY
    ca.has_major_gridlines = False
    ca.major_tick_mark = 2  # none
    va = chart.value_axis
    va.visible = show_val
    va.has_major_gridlines = gridlines
    if gridlines:
        va.major_gridlines.format.line.color.rgb = rgb(BORDER); va.major_gridlines.format.line.width = Pt(0.75)
    va.format.line.fill.background()
    va.tick_labels.font.size = Pt(10); va.tick_labels.font.color.rgb = rgb(TEXT3); va.tick_labels.font.name = BODY
    if val_fmt:
        va.tick_labels.number_format = val_fmt; va.tick_labels.number_format_is_linked = False


def labels(series, fmt, values, pos=XL_LABEL_POSITION.OUTSIDE_END, color=TEXT, size=11, bold=True):
    """Rótulos com texto próprio por ponto, para manter a vírgula decimal em qualquer idioma do Office."""
    for i, v in enumerate(values):
        dl = series.points[i].data_label
        neg = v < 0
        dl.position = XL_LABEL_POSITION.INSIDE_BASE if neg else pos
        tf = dl.text_frame
        tf.text = fmt(v)
        f = tf.paragraphs[0].runs[0].font
        f.size = Pt(size); f.bold = bold; f.color.rgb = rgb(SURFACE if neg else color); f.name = BODY


def bar_chart(slide, x, y, w, h, cats, series, colors, fmt, horizontal=True, point_colors=None,
              legend=False, gap=60, overlap=None, name=None):
    cd = CategoryChartData(); cd.categories = cats
    for nm, vals in series:
        cd.add_series(nm, vals)
    kind = XL_CHART_TYPE.BAR_CLUSTERED if horizontal else XL_CHART_TYPE.COLUMN_CLUSTERED
    gf = slide.shapes.add_chart(kind, Inches(x), Inches(y), Inches(w), Inches(h), cd)
    if name:
        gf.name = name
    ch = gf.chart
    style_chart(ch, legend)
    quiet_axes(ch)
    if horizontal:
        ch.category_axis.reverse_order = True
    ch.category_axis.tick_label_position = XL_TICK_LABEL_POSITION.LOW
    allv = [v for _, vals in series for v in vals]
    ch.value_axis.maximum_scale = max(allv) * 1.2
    ch.value_axis.minimum_scale = min(allv) * 1.05 if min(allv) < 0 else 0
    plot = ch.plots[0]
    plot.gap_width = gap
    if overlap is not None:
        plot.overlap = overlap
    for i, s in enumerate(plot.series):
        s.invert_if_negative = False
        s.format.fill.solid(); s.format.fill.fore_color.rgb = rgb(colors[i])
        s.format.line.fill.background()
        labels(s, fmt[i] if isinstance(fmt, list) else fmt, series[i][1])
    if point_colors:
        s = plot.series[0]
        for i, c in enumerate(point_colors):
            pt = s.points[i]
            pt.format.fill.solid(); pt.format.fill.fore_color.rgb = rgb(c)
    # barras negativas sem inversão de cor também no nível do ponto
    for dPt in ch._chartSpace.xpath(".//c:dPt"):
        if not dPt.xpath("c:invertIfNegative"):
            inv = dPt.makeelement(qn("c:invertIfNegative"), {"val": "0"})
            dPt.find(qn("c:idx")).addnext(inv)
    return ch


def table(slide, x, y, w, rows, col_w, row_h=0.42, header_fill=ACCENT_SOFT, size=12, bold_first_col=True,
          highlight_rows=()):
    nr, nc = len(rows), len(rows[0])
    gf = slide.shapes.add_table(nr, nc, Inches(x), Inches(y), Inches(w), Inches(row_h * nr))
    tbl = gf.table
    # remove o estilo padrão de faixas
    tblPr = gf._element.graphic.graphicData.tbl.tblPr
    tblPr.set("bandRow", "0"); tblPr.set("firstRow", "0")
    for j, cw in enumerate(col_w):
        tbl.columns[j].width = Inches(cw)
    for i in range(nr):
        tbl.rows[i].height = Inches(row_h)
        for j in range(nc):
            c = tbl.cell(i, j)
            c.fill.solid()
            c.fill.fore_color.rgb = rgb(header_fill if i == 0 else (BG2 if i in highlight_rows else SURFACE))
            c.margin_left = c.margin_right = Inches(0.12); c.margin_top = c.margin_bottom = Inches(0.03)
            c.vertical_anchor = MSO_ANCHOR.MIDDLE
            tf = c.text_frame; tf.word_wrap = True
            p = tf.paragraphs[0]
            p.alignment = PP_ALIGN.LEFT if j == 0 else PP_ALIGN.RIGHT
            r = p.add_run(); r.text = rows[i][j]
            r.font.name = BODY; r.font.size = Pt(size if i else size - 1)
            r.font.bold = (i == 0) or (j == 0 and bold_first_col)
            r.font.color.rgb = rgb(ACCENT if i == 0 else (TEXT if j == 0 else TEXT2))
            # bordas finas em tom creme
            tcPr = c._tc.get_or_add_tcPr()
            for tag in ("a:lnL", "a:lnR", "a:lnT", "a:lnB"):
                ln = tcPr.makeelement(qn(tag), {"w": "9525"})
                sf = ln.makeelement(qn("a:solidFill"), {})
                clr = sf.makeelement(qn("a:srgbClr"), {"val": BORDER})
                sf.append(clr); ln.append(sf); tcPr.append(ln)
    return tbl


def arrow(slide, x1, y1, x2, y2, color=ACCENT2):
    c = slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, Inches(x1), Inches(y1), Inches(x2), Inches(y2))
    c.line.color.rgb = rgb(color); c.line.width = Pt(2)
    ln = c.line._get_or_add_ln()
    tail = ln.makeelement(qn("a:tailEnd"), {"type": "triangle", "w": "med", "len": "med"})
    ln.append(tail)
    return c


# ====================================================================== 1. Capa
s = prs.slides.add_slide(BLANK); slide_no[0] += 1
set_bg(s, ACCENT)
badge(s, 0.9, 1.0, 0.75, "⚡", fill=SURFACE, color=ACCENT, size=22, line=None)
text(s, 0.9, 2.0, 11, 0.35, [[("TRABALHO DE CONCLUSÃO DE CURSO", {"spc": 200, "bold": True})]], size=13, color=ACCENT_SOFT)
text(s, 0.9, 2.4, 11.6, 2.2, "Consumo e expansão do mercado de energia elétrica no Brasil",
     size=58, font=TITLE_FONT, bold=True, color=SURFACE, spacing=0.95, anchor=MSO_ANCHOR.MIDDLE)
text(s, 0.9, 4.75, 11, 0.5, "Modelagem espacial com aprendizado de máquina sobre a BDGD/ANEEL", size=20, color=ACCENT_SOFT)
text(s, 0.9, 6.3, 8, 0.35, [[("Lucas Mendonça Nóbrega", {"bold": True}), ("   ·   2026", {})]], size=14, color=SURFACE)
s.notes_slide.notes_text_frame.text = (
    "Apresentação do TCC: análise espacial do consumo de energia elétrica no Brasil com dados públicos da ANEEL "
    "(BDGD), comparação de modelos de machine learning espacial e um olhar dedicado à região do ABC.")

# ====================================================================== 2. Perguntas
s = content_slide("Contexto", "Duas perguntas de pesquisa",
                  "A pesquisa parte de uma hipótese dupla sobre descentralização do mercado e sobre o efeito disso na rede de distribuição.")
qs = [("1", "O mercado de energia está se descentralizando para o interior ou permanece concentrado nas grandes metrópoles?"),
      ("2", "Como essa dinâmica reconfigura a demanda sobre as redes de distribuição?")]
for i, (n, q) in enumerate(qs):
    x = 0.6 + i * 6.2
    card(s, x, 1.95, 5.9, 2.85)
    badge(s, x + 0.4, 2.3, 0.7, n, size=20)
    text(s, x + 0.4, 3.2, 5.1, 1.5, q, size=20, color=TEXT, spacing=1.1)
card(s, 0.6, 5.15, 12.1, 1.45, fill=ACCENT_SOFT, line=None)
text(s, 1.0, 5.15, 11.3, 1.45,
     [[("Abordagem: ", {"bold": True, "color": ACCENT}),
       ("dados públicos regulatórios da ANEEL em larga escala, aprendizado de máquina espacial e validação estatística "
        "rigorosa, medindo a capacidade real de generalizar para regiões não vistas no treino.", {})]],
     size=16, color=TEXT, anchor=MSO_ANCHOR.MIDDLE, spacing=1.1)

# ====================================================================== 3. Tarefas
s = content_slide("Objetivos", "Quatro tarefas de modelagem",
                  "Cada tarefa responde a uma pergunta prática de planejamento, em escala de UC ou de município.")
tarefas = [("1", "Consumo de nova UC", "Quanto consome por ano uma nova unidade consumidora, dada a localização e o perfil do pedido de ligação?", "Regressão · UC"),
           ("2", "Grupos de tensão", "Que proporção das novas UCs de uma região será de baixa, média ou alta tensão?", "Composição · município"),
           ("3", "Expansão da geração", "Quais municípios receberão nova potência de geração centralizada nos próximos 5 anos?", "Classificação · município"),
           ("4", "Mapa territorial", "Quais municípios são polos consolidados, fronteiras de expansão ou de baixa dinâmica?", "Índice · quadrantes")]
for i, (n, t, q, tag) in enumerate(tarefas):
    x = 0.6 + i * 3.1
    card(s, x, 1.95, 2.85, 4.65)
    badge(s, x + 0.3, 2.25, 0.6, n, size=18)
    text(s, x + 0.3, 3.05, 2.3, 0.75, t, size=18, bold=True, color=TEXT, spacing=1.0)
    text(s, x + 0.3, 3.85, 2.3, 1.95, q, size=14, color=TEXT2, spacing=1.12)
    chip(s, x + 0.3, 5.95, 2.25, tag, size=10)

# ====================================================================== 4. Dados
s = content_slide("Dados", "Onze milhões de unidades consumidoras",
                  "Base central: BDGD da ANEEL, data-base 31/12/2025, tabelas UCAT, UCMT e UCBT. Do lado da geração, a base de "
                  "liberação para operação comercial, georreferenciada pelo SIGA.")
stats = [("10,95 mi", "UCs na BDGD", "Alta, média e baixa tensão, com consumo mensal, coordenadas e perfil declarado"),
         ("9,54 mi", "UCs ativas", "Universo usado na modelagem, após regras de qualidade"),
         ("134,9 GW", "de geração liberada", "59.581 unidades geradoras em 2.772 usinas centralizadas"),
         ("5.570", "municípios", "Cruzados com Censo 2010/2022 e PIB municipal do IBGE")]
for i, (v, l, sub) in enumerate(stats):
    stat(s, 0.6 + i * 3.1, 1.95, 2.85, 2.5, v, l, sub, vsize=36)
card(s, 0.6, 4.75, 12.1, 1.95)
text(s, 0.95, 4.95, 4, 0.3, [[("FONTES", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
fontes = [("BDGD / ANEEL", "PRODIST Módulo 10 · consumo, tensão, tarifa, perfil e rede"),
          ("ANEEL · Liberação comercial", "Unidades geradoras e potência por usina"),
          ("ANEEL · SIGA", "Coordenadas das usinas e obras em andamento"),
          ("IBGE / SIDRA", "População, urbanização, PIB e sedes municipais")]
for i, (a, b) in enumerate(fontes):
    x = 0.95 + (i % 2) * 5.9; y = 5.35 + (i // 2) * 0.6
    text(s, x, y, 5.6, 0.5, [[(a, {"bold": True, "color": ACCENT}), ("  " + b, {})]], size=13, color=TEXT2)

# ====================================================================== 5. Pipeline
s = content_slide("Preparação dos dados", "Um pipeline reprodutível em três etapas",
                  "As etapas foram validadas com testes de conferência contra a base bruta. Um desses testes encontrou a omissão do "
                  "consumo fora de ponta na AT, que representava cerca de 91% do consumo do grupo. A modelagem usa uma amostra de "
                  "121.884 UCs estratificada por grupo de tensão, com pesos que restauram as proporções reais. O alimentador "
                  "foi descartado: elevava a acurácia balanceada de 0,33 para 0,72 por causa do formato do registro na BDGD, "
                  "não de informação física (vazamento).")
steps = [("1", "Pré-filtragem", "CSVs de até 5 GB convertidos para Parquet (zstd), com leitura em streaming para caber em memória."),
         ("2", "Seleção de colunas", "Só as variáveis de interesse. Variáveis derivadas do próprio consumo saem na origem para evitar vazamento."),
         ("3", "Junção territorial", "Join com os municípios do IBGE. UCs sem coordenada vão para a sede, com a origem rastreada e fora do treino.")]
for i, (n, t, d) in enumerate(steps):
    x = 0.6 + i * 4.15
    card(s, x, 1.95, 3.7, 2.7)
    badge(s, x + 0.3, 2.25, 0.6, n, size=18)
    text(s, x + 0.3, 3.0, 3.1, 0.4, t, size=18, bold=True)
    text(s, x + 0.3, 3.5, 3.1, 1.05, d, size=13, color=TEXT2, spacing=1.1)
    if i < 2:
        arrow(s, x + 3.75, 3.3, x + 4.1, 3.3)
quals = [("UCs ativas na modelagem", "9,54 mi"), ("UCs na amostra, estratificada por tensão e com pesos", "121.884"), ("de acurácia falsa do alimentador: vazamento removido", "0,72"), ("do MW das usinas com coordenada verificada", "97,2%")]
for i, (a, b) in enumerate(quals):
    x = 0.6 + i * 3.1
    card(s, x, 5.0, 2.85, 1.6, fill=ACCENT_SOFT, line=None)
    text(s, x + 0.3, 5.15, 2.3, 0.6, b, size=26, bold=True, color=ACCENT, anchor=MSO_ANCHOR.BOTTOM)
    text(s, x + 0.3, 5.8, 2.3, 0.7, a, size=12, color=TEXT, spacing=1.05)

# ====================================================================== 6. Validação
s = content_slide("Metodologia", "Validar em regiões que o modelo nunca viu",
                  "Pela Primeira Lei de Tobler, vizinhos se parecem. Uma validação aleatória coloca vizinhos no treino e no teste e "
                  "superestima o desempenho. Por isso usamos validação cruzada espacial em blocos.")
card(s, 0.6, 1.95, 5.6, 4.7)
text(s, 0.95, 2.15, 5, 0.3, [[("SPATIAL BLOCK CV · UM FOLD", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
test_blocks = {3, 4, 13, 22, 27, 28, 36, 41, 45, 46}
cols, rows_, sz, gap = 10, 5, 0.42, 0.06
gx0 = 0.6 + (5.6 - (cols * sz + (cols - 1) * gap)) / 2
for k in range(cols * rows_):
    r_, c_ = divmod(k, cols)
    b = s.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(gx0 + c_ * (sz + gap)), Inches(2.65 + r_ * (sz + gap)), Inches(sz), Inches(sz))
    b.adjustments[0] = 0.18
    b.fill.solid(); b.fill.fore_color.rgb = rgb(ACCENT if k in test_blocks else "E9DFCC"); b.line.fill.background(); b.shadow.inherit = False
text(s, 0.95, 5.25, 4.9, 1.2,
     [[("■ ", {"color": ACCENT}), ("blocos de teste: regiões inteiras fora do treino", {})],
      [("■ ", {"color": "D8CBB4"}), ("blocos de treino", {})]], size=13, color=TEXT2, after=4)
facts = [("50", "blocos contíguos", "K-means sobre coordenadas projetadas"),
         ("15", "folds", "5 folds × 3 repetições com GroupKFold"),
         ("t", "Nadeau-Bengio", "teste pareado corrigido para folds que compartilham treino")]
for i, (n, a, b) in enumerate(facts):
    y = 1.95 + i * 1.2
    badge(s, 6.6, y + 0.12, 0.75, n, size=18 if n != "t" else 20)
    text(s, 7.55, y + 0.1, 5.1, 0.4, a, size=17, bold=True)
    text(s, 7.55, y + 0.5, 5.1, 0.5, b, size=13, color=TEXT2)
text(s, 6.6, 5.6, 6, 0.3, [[("ALGORITMOS COMPARADOS", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
fams = ["kNN espacial", "Random Forest", "LightGBM", "XGBoost", "CatBoost", "Krigagem / GP", "GWR · MGWR", "Logística"]
cx = 6.6
for i, f in enumerate(fams):
    wd = 0.35 + 0.095 * len(f)
    if cx + wd > 12.75:
        cx = 6.6
    yy = 5.95 if i < 4 else 6.35
    if i == 4:
        cx = 6.6
    chip(s, cx, yy, wd, f, size=10)
    cx += wd + 0.1

# ====================================================================== 7. Divisor resultados
divider_slide("Parte 2", "Principais resultados", "Concentração do consumo, desempenho dos modelos e leitura territorial")

# ====================================================================== 8. Concentração por tensão
s = content_slide("Retrato do consumo", "Poucas UCs de AT e MT concentram 87% do consumo",
                  "AT: cerca de 2,1 mil UCs (0,02%) consomem 33% da energia. MT: 314 mil UCs (2,9%) consomem 54%. "
                  "BT: 10,6 milhões de UCs (97%) consomem só 13%.")
card(s, 0.6, 1.95, 7.6, 4.7)
ch = bar_chart(s, 0.85, 2.1, 7.1, 4.4, ["Baixa tensão", "Média tensão", "Alta tensão"],
               [("% das UCs", (97.1, 2.9, 0.02)), ("% do consumo", (13, 54, 33))],
               [MUTED, ACCENT], [lambda v: br(v, 2 if v < 1 else 1, suffix="%"), lambda v: br(v, 0, suffix="%")], horizontal=False, legend=True, gap=80, overlap=-10)
stat(s, 8.5, 1.95, 4.2, 2.2, "33%", "do consumo vem da AT", "com apenas cerca de 2,1 mil UCs no país inteiro")
stat(s, 8.5, 4.45, 4.2, 2.2, "13%", "do consumo vem da BT", "apesar de reunir 97% das unidades consumidoras", value_color=MUTED2)

# ====================================================================== 9. Tarefa 1
s = content_slide("Tarefa 1 · Consumo de nova UC", "Random Forest com todos os grupos lidera",
                  "Rodada completa: 121.884 UCs, 15 folds espaciais. O RF + todos supera CatBoost e LightGBM em 13 e 14 de 15 folds "
                  "(p corrigido < 0,05). Modelos geoestatísticos ficaram abaixo do ML.")
card(s, 0.6, 1.95, 7.6, 4.7)
text(s, 0.95, 2.15, 7, 0.3, [[("R² DO LOG-CONSUMO · VALIDAÇÃO ESPACIAL", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
models = ["Random Forest + todos", "CatBoost + todos", "LightGBM + todos", "Random Forest (só posição)", "Krigagem (GP)", "kNN espacial", "GWR"]
vals = (0.576, 0.560, 0.558, 0.154, 0.006, -0.181, -0.485)
bar_chart(s, 0.85, 2.5, 7.1, 4.0, models, [("R²", vals)], [MUTED], lambda v: br(v, 2), point_colors=[ACCENT, MUTED, MUTED, MUTED, MUTED, MUTED2, MUTED2], gap=45)
stat(s, 8.5, 1.95, 2.0, 2.2, "0,58", "R²", "variância explicada", vsize=32)
stat(s, 10.7, 1.95, 2.0, 2.2, "54%", "MdAPE", "erro percentual mediano", vsize=32)
card(s, 8.5, 4.45, 4.2, 2.2, fill=ACCENT_SOFT, line=None)
text(s, 8.8, 4.65, 3.6, 1.9,
     [[("Como usar: ", {"bold": True, "color": ACCENT}),
       ("estimativa de ordem de grandeza para o pedido de ligação. O erro típico é de um fator de cerca de 2,5×, com viés baixo nos agregados.", {})]],
     size=14, color=TEXT, spacing=1.12, anchor=MSO_ANCHOR.MIDDLE)

# ====================================================================== 10. Ablação
s = content_slide("Tarefa 1 · Ablação", "O ganho vem do perfil declarado e da rede",
                  "Ablação sobre o RF com posição (R² base de 0,154). Perfil e rede são significativos; geração e IBGE não, mas "
                  "somam informação de forma complementar: o modelo com todos supera o só-perfil em 15 de 15 folds.")
card(s, 0.6, 1.95, 7.6, 4.7)
text(s, 0.95, 2.15, 7, 0.3, [[("GANHO DE R² SOBRE O MODELO SÓ COM POSIÇÃO", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
bar_chart(s, 0.85, 2.5, 7.1, 3.6, ["Todos os grupos", "Perfil declarado", "Rede (distribuidora)", "Geração no entorno", "IBGE"],
          [("ΔR²", (0.422, 0.350, 0.173, 0.046, 0.035))], [ACCENT], lambda v: br(v, 3, signed=True), point_colors=[DEEP, ACCENT, ACCENT, MUTED, MUTED], gap=45)
text(s, 0.95, 6.15, 7, 0.35, [[("■ ", {"color": ACCENT}), ("significativo    ", {}), ("■ ", {"color": MUTED}), ("não significativo (Nadeau-Bengio)", {})]], size=11, color=TEXT2)
text(s, 8.5, 1.95, 4.2, 0.3, [[("R² POR GRUPO DE TENSÃO", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
for i, (g, v, d) in enumerate([("MT", "0,58", "bom e estável"), ("BT", "0,46", "maior ganho com todos (+0,53)"), ("AT", "0,31", "instável (dp 0,35): poucas UCs")]):
    y = 2.35 + i * 1.45
    card(s, 8.5, y, 4.2, 1.25)
    badge(s, 8.75, y + 0.27, 0.7, g, size=14)
    text(s, 9.65, y + 0.18, 1.4, 0.55, v, size=26, bold=True, color=ACCENT if g != "AT" else MUTED2)
    text(s, 9.65, y + 0.72, 2.9, 0.4, d, size=12, color=TEXT2)

# ====================================================================== 11. Tarefa 2
s = content_slide("Tarefa 2 · Grupos de tensão", "A composição é previsível no agregado, não por UC",
                  "Por UC, a acurácia balanceada fica em 0,33, igual ao acaso: quase toda UC é BT. No município, a regressão logística "
                  "multinomial é a melhor (TVD 0,0126) e erra 34% menos que a média nacional.")
stat(s, 0.6, 1.95, 3.9, 2.2, "0,33", "acurácia balanceada por UC", "igual ao acaso para 3 classes", value_color=MUTED2)
stat(s, 0.6, 4.45, 3.9, 2.2, "−34%", "de erro no município", "logística vs. média nacional · R² da fração de MT = 0,47")
card(s, 4.8, 1.95, 7.9, 4.7)
text(s, 5.15, 2.15, 7, 0.3, [[("TVD MUNICIPAL (MENOR É MELHOR)", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
bar_chart(s, 5.05, 2.5, 7.4, 2.9, ["Logística multinomial", "CatBoost", "kNN espacial", "Média nacional"],
          [("TVD", (0.0126, 0.0130, 0.0171, 0.0190))], [MUTED], lambda v: br(v, 4), point_colors=[ACCENT, MUTED, MUTED2, MUTED2], gap=45)
text(s, 5.15, 5.5, 7.2, 1.0,
     [[("IBGE (indústria, agro, urbanização) é decisivo: ", {"bold": True, "color": TEXT}),
       ("melhora 15 de 15 folds (p < 0,001). A vizinhança kNN piora todos os modelos na validação por blocos.", {})]],
     size=13, color=TEXT2, spacing=1.1)

# ====================================================================== 12. Tarefa 3
s = content_slide("Tarefa 3 · Expansão da geração", "Onde a geração vai chegar nos próximos 5 anos",
                  "Validação temporal (treino até 2015, teste em 2020). Validação externa: a previsão 2026–2030 foi confrontada com as "
                  "usinas em obra no SIGA, que não entraram no treino.")
card(s, 0.6, 1.95, 6.6, 4.7)
text(s, 0.95, 2.15, 6, 0.3, [[("AUC-PR · VALIDAÇÃO TEMPORAL", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
bar_chart(s, 0.85, 2.5, 6.1, 4.0, ["RF + IBGE 2010", "kNN espacial", "Persistência", "Acaso"],
          [("AUC-PR", (0.337, 0.179, 0.151, 0.054))], [MUTED], lambda v: br(v, 3), horizontal=False, point_colors=[ACCENT, MUTED, MUTED, MUTED2], gap=70)
stat(s, 7.5, 1.95, 5.2, 2.2, "30 de 50", "municípios do topo já têm usina em obra",
     "Precisão de 60%, contra 34% da persistência e 6% do acaso")
card(s, 7.5, 4.45, 5.2, 2.2, fill=ACCENT_SOFT, line=None)
text(s, 7.8, 4.6, 4.6, 1.95,
     [[("Dependente da trajetória: ", {"bold": True, "color": ACCENT}),
       ("a geração já instalada é o principal preditor. Lideram Igaporã e Caetité (BA), Pedra Grande e Bodó (RN) e Simões (PI), com cerca de 41 GW esperados.", {})]],
     size=14, color=TEXT, spacing=1.1, anchor=MSO_ANCHOR.MIDDLE)

# ====================================================================== 13. Geração x consumo
s = content_slide("Geração × consumo", "A geração cresce longe de onde a energia é consumida",
                  "Desde 2014, Nordeste e Norte receberam 71% da nova potência, mas concentram 19% do consumo. Sudeste e Sul somam 74% "
                  "do consumo. Isso reforça o papel da transmissão.")
card(s, 0.6, 1.95, 8.1, 4.7)
bar_chart(s, 0.85, 2.15, 7.6, 4.35, ["Nordeste", "Norte", "Sudeste", "Sul", "Centro-Oeste"],
          [("Nova potência desde 2014", (47.0, 24.3, 18.4, 5.1, 5.2)), ("Consumo das UCs", (14.0, 4.8, 50.5, 23.7, 7.0))],
          [SAGE, ACCENT], lambda v: br(v, 0, suffix="%"), horizontal=False, legend=True, gap=70, overlap=-10)
stat(s, 9.0, 1.95, 3.7, 2.2, "71%", "da nova potência no NE e N", "eólica e solar no Nordeste, hidrelétricas no Norte", value_color=SAGE)
stat(s, 9.0, 4.45, 3.7, 2.2, "74%", "do consumo no SE e S", "a demanda segue nos centros do Sul-Sudeste")

# ====================================================================== 14. Mapa territorial
s = content_slide("Leitura territorial", "Quadrantes de consumo e expansão",
                  "Corte no percentil 80 de consumo e de expansão. O índice de expansão usa a data de ligação, que foi recadastrada em "
                  "algumas distribuidoras (AP 96%, PI 84% de ligações 'recentes', contra 12% no Brasil). O selo de confiabilidade trata isso.")
quad = [("Fronteira de expansão", "579", 0, 0, ACCENT_SOFT, ACCENT), ("Polo consolidado em expansão", "205", 1, 0, ACCENT, SURFACE),
        ("Baixa dinâmica", "3.735", 0, 1, SURFACE, TEXT2), ("Polo consolidado", "874", 1, 1, "EAD9C4", DEEP)]
qx0, qy0, qw, qh = 1.15, 2.05, 3.1, 2.05
for nm, n, cx_, cy_, fill, col in quad:
    x = qx0 + cx_ * (qw + 0.12); y = qy0 + cy_ * (qh + 0.12)
    card(s, x, y, qw, qh, fill=fill, line=BORDER)
    text(s, x + 0.25, y + 0.25, qw - 0.5, 0.8, n, size=32, bold=True, color=col)
    text(s, x + 0.25, y + 1.15, qw - 0.5, 0.75, nm, size=13, bold=True, color=col if col != SURFACE else SURFACE, spacing=1.05)
text(s, 0.8 - 2.11, 4.16 - 0.15, 4.22, 0.3, [[("EXPANSÃO →", {"spc": 100, "bold": True})]], size=10, color=TEXT3, align=PP_ALIGN.CENTER)
s.shapes[-1].rotation = 270
text(s, qx0, 6.38, 2 * qw + 0.12, 0.3, [[("CONSUMO →", {"spc": 100, "bold": True})]], size=10, color=TEXT3, align=PP_ALIGN.CENTER)
text(s, 8.2, 1.95, 4.5, 0.3, [[("SELO DE CONFIABILIDADE", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
for i, (sel, n, c) in enumerate([("Alta", "4.914", SAGE), ("Média", "90", GOLD), ("Baixa", "559", "B23A2E")]):
    y = 2.35 + i * 0.95
    card(s, 8.2, y, 4.5, 0.8)
    badge(s, 8.42, y + 0.2, 0.4, "", fill=c, line=None)
    text(s, 9.05, y, 1.8, 0.8, sel, size=15, bold=True, anchor=MSO_ANCHOR.MIDDLE)
    text(s, 10.6, y, 1.85, 0.8, n, size=20, bold=True, color=TEXT, align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)
card(s, 8.2, 5.25, 4.5, 1.4, fill=ACCENT_SOFT, line=None)
text(s, 8.45, 5.3, 4.0, 1.3,
     [[("Índice normalizado por distribuidora: ", {"bold": True, "color": ACCENT}),
       ("correlação com o crescimento populacional sobe de 0,06 para 0,21.", {})]],
     size=13, color=TEXT, spacing=1.1, anchor=MSO_ANCHOR.MIDDLE)

# ====================================================================== 15. Divisor ABC
divider_slide("Parte 3 · Seção especial", "Região do ABC", "Santo André  ·  São Bernardo do Campo  ·  São Caetano do Sul",
              "Recorte dos resultados do projeto para os três municípios do ABC paulista.")

# ====================================================================== 16. ABC em números
s = content_slide("Região do ABC", "Um polo industrial consolidado",
                  "Os três municípios estão no quadrante 'Polo consolidado' e têm selo de confiabilidade Alta: datas de ligação sem "
                  "anomalia e geração nova a até 50 km. São Bernardo é o 6º maior consumo do estado de São Paulo.")
stat(s, 0.6, 1.95, 3.9, 2.2, "2,96 TWh", "de consumo anual", "4,0% do estado de SP e 1,1% do Brasil no recorte da BDGD", vsize=36)
stat(s, 4.7, 1.95, 3.9, 2.2, "43,9 mil", "UCs ativas", "1.737 delas em média e alta tensão", vsize=36)
stat(s, 8.8, 1.95, 3.9, 2.2, "3 de 3", "polos consolidados", "todos com selo de confiabilidade Alta", vsize=36)
table(s, 0.6, 4.45, 12.1,
      [["Município", "Consumo (GWh/ano)", "UCs ativas", "Média por UC (MWh)", "Ranking SP", "Ranking Brasil"],
       ["São Bernardo do Campo", "1.672", "18.161", "92,0", "6º", "15º"],
       ["Santo André", "927", "17.622", "52,6", "15º", "42º"],
       ["São Caetano do Sul", "360", "8.069", "44,6", "51º", "149º"]],
      [3.1, 2.3, 1.6, 2.1, 1.4, 1.6], row_h=0.44, size=13)
text(s, 0.6, 6.32, 12.1, 0.3, "Referência: mediana do consumo médio por UC de 18,9 MWh nos municípios de SP e 7,1 MWh no Brasil. "
     "Rankings entre 645 municípios de SP e 5.563 do Brasil.", size=10, color=TEXT3)

# ====================================================================== 17. Perfil ABC
s = content_slide("Região do ABC · Perfil", "Consumo industrial, em alta e média tensão",
                  "AT: 46 UCs, 59% do consumo. MT: 1.691 UCs, 41%. A BT da distribuidora da região (DIST 390) tem consumo zerado em "
                  "98,5% das UCs neste recorte da BDGD, por isso aparece próxima de zero.")
card(s, 0.6, 1.95, 4.3, 4.7)
text(s, 0.95, 2.15, 3.8, 0.3, [[("CONSUMO POR TENSÃO", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
bar_chart(s, 0.75, 2.5, 4.0, 3.5, ["AT · 46 UCs", "MT · 1.691 UCs", "BT · 42.115 UCs*"],
          [("%", (59.4, 40.6, 0.02))], [ACCENT], lambda v: "≈ 0%" if v < 1 else br(v, 0, suffix="%"), horizontal=False, point_colors=[DEEP, ACCENT, MUTED], gap=60)
text(s, 0.95, 6.1, 3.8, 0.45, "* consumo de BT ausente no recorte", size=10, color=TEXT3)
card(s, 5.1, 1.95, 4.3, 4.7)
text(s, 5.45, 2.15, 3.8, 0.3, [[("CONSUMO POR CLASSE", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
bar_chart(s, 5.25, 2.5, 4.0, 3.9, ["Industrial", "Comercial", "Serviço público", "Poder público"],
          [("%", (65.0, 26.9, 5.7, 2.4))], [ACCENT], lambda v: br(v, 0, suffix="%"), point_colors=[ACCENT, GOLD, SAGE, BLUE], gap=45)
stat(s, 9.6, 1.95, 3.1, 4.7, "48%", "das UCs de AT/MT no mercado livre",
     "827 consumidores livres: 44 em AT e 783 em MT.", vsize=44, label_lines=2)
for i, (nm, v, c) in enumerate([("ABC", 47.6, ACCENT), ("Brasil", 24.7, MUTED2)]):
    yb = 4.65 + i * 0.75
    text(s, 9.9, yb, 2.5, 0.3, [[(nm, {"bold": True}), ("   " + br(v, 0, suffix="%"), {"color": c, "bold": True})]], size=12, color=TEXT)
    trk = card(s, 9.9, yb + 0.33, 2.5, 0.2, fill="EFE6D6", line=None, radius=0.1)
    card(s, 9.9, yb + 0.33, 2.5 * v / 100 * 1.9, 0.2, fill=c, line=None, radius=0.1)

# ====================================================================== 18. Dinâmica ABC
s = content_slide("Região do ABC · Dinâmica", "Maturidade: poucas ligações novas",
                  "Em 2023–2025 foram ligadas 4% a 5% das UCs ativas do ABC, contra 12,2% na mediana nacional. A demanda da região cresce "
                  "mais por intensidade de uso das cargas existentes do que por novas ligações.")
card(s, 0.6, 1.95, 7.4, 4.7)
text(s, 0.95, 2.15, 6.8, 0.3, [[("CONSUMO MENSAL EM 2025 (GWh)", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
cd = CategoryChartData()
cd.categories = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez"]
cd.add_series("São Bernardo do Campo", (122.9, 130.9, 138.5, 134.1, 129.6, 134.0, 125.7, 143.4, 126.8, 130.6, 166.8, 188.4))
cd.add_series("Santo André", (68.6, 99.3, 86.4, 89.6, 74.3, 75.3, 66.8, 61.5, 69.7, 80.7, 88.7, 66.3))
cd.add_series("São Caetano do Sul", (29.7, 31.0, 31.1, 30.9, 29.2, 29.4, 27.5, 23.8, 33.2, 29.5, 36.0, 28.4))
gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.8), Inches(2.45), Inches(7.0), Inches(4.05), cd)
ch = gf.chart
style_chart(ch, legend=True)
quiet_axes(ch, show_val=True, val_fmt='0', gridlines=True)
for ser, c in zip(ch.plots[0].series, [ACCENT, GOLD, SAGE]):
    ser.smooth = False
    ser.format.line.color.rgb = rgb(c); ser.format.line.width = Pt(2.5)
    ser.marker.style = XL_MARKER_STYLE.CIRCLE; ser.marker.size = 6
    ser.marker.format.fill.solid(); ser.marker.format.fill.fore_color.rgb = rgb(c); ser.marker.format.line.color.rgb = rgb(SURFACE)
card(s, 8.3, 1.95, 4.4, 4.7)
text(s, 8.6, 2.15, 4.0, 0.3, [[("UCS LIGADAS EM 2023–2025", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
bar_chart(s, 8.45, 2.5, 4.1, 3.0, ["São Bernardo", "Santo André", "São Caetano", "Brasil (mediana)"],
          [("%", (4.4, 5.3, 3.8, 12.2))], [ACCENT], lambda v: br(v, 1, suffix="%"), point_colors=[ACCENT, GOLD, SAGE, MUTED2], gap=45)
text(s, 8.6, 5.6, 3.9, 0.9, [[("São Bernardo: ", {"bold": True, "color": TEXT}), ("tendência de +2,5% ao mês, puxada por novembro e dezembro.", {})]],
     size=12, color=TEXT2, spacing=1.1)

# ====================================================================== 19. Previsões ABC
s = content_slide("Região do ABC · Modelos", "O que os modelos projetam para o ABC",
                  "Consumo esperado de uma nova UC pelo modelo regional (sem perfil declarado), composição de tensão pela logística "
                  "multinomial e probabilidade de nova geração centralizada em 2026–2030 pela Tarefa 3.")
table(s, 0.6, 1.95, 8.1,
      [["Indicador", "São Bernardo", "Santo André", "São Caetano"],
       ["Nova UC de MT (MWh/ano)", "1.310", "756", "1.831"],
       ["Nova UC de AT (GWh/ano)", "44,7", "137,6", "125,7"],
       ["Nova UC · valor esperado (MWh/ano)", "170", "160", "273"],
       ["Fração de MT observada", "5,0%", "2,9%", "3,3%"],
       ["Fração de MT prevista", "9,3%", "7,3%", "6,0%"],
       ["Prob. de nova geração 2026–30", "13%", "40%", "5%"],
       ["Ranking em SP (geração)", "63º", "11º", "127º"]],
      [3.6, 1.5, 1.5, 1.5], row_h=0.56, size=13, highlight_rows=(3, 6))
stat(s, 9.0, 1.95, 3.7, 2.15, "3 a 5×", "o valor esperado nacional", "Nova UC no ABC: 160 a 273 MWh/ano, contra 58 MWh na mediana do país", vsize=40)
stat(s, 9.0, 4.35, 3.7, 2.15, "40%", "chance em Santo André", "11º do estado. A UTE Vesta (40 MW, gás) entrou em operação em 2023", vsize=40)
text(s, 0.6, 6.5, 8.1, 0.3, "Mediana nacional da probabilidade de nova geração: 2,9%.", size=10, color=TEXT3)

# ====================================================================== 20. Leitura ABC
s = content_slide("Região do ABC · Leitura", "Três mensagens sobre o ABC",
                  "Síntese da seção ABC para o planejamento da distribuição e da expansão.")
msgs = [("1", "Polo maduro e intenso", "Consumo médio por UC de 6 a 13× a mediana nacional e um terço do ritmo nacional de novas ligações. A pressão sobre a rede vem da carga existente."),
        ("2", "Indústria e mercado livre", "65% do consumo é industrial e quase metade das UCs de AT/MT já está no mercado livre. A região é sensível ao ciclo industrial e à migração para o ACL."),
        ("3", "Importadora de energia", "Só 50 MW de geração centralizada nova a até 50 km, 40 MW deles da UTE Vesta. O modelo prevê mais MT do que o observado (+3 a +4 p.p.): espaço para novas cargas.")]
for i, (n, t, d) in enumerate(msgs):
    x = 0.6 + i * 4.1
    card(s, x, 1.95, 3.85, 4.7)
    badge(s, x + 0.35, 2.3, 0.75, n, size=20)
    text(s, x + 0.35, 3.3, 3.2, 0.5, t, size=19, bold=True)
    text(s, x + 0.35, 3.9, 3.2, 2.5, d, size=14, color=TEXT2, spacing=1.15)

# ====================================================================== 21. Conclusões
s = content_slide("Conclusões", "O que o projeto mostra",
                  "Principais conclusões do TCC e produtos entregues.")
concl = [("O consumo é muito concentrado em AT e MT", "Para a rede, poucas UCs de AT/MT pesam mais que milhões de UCs de BT."),
         ("O pedido de ligação prevê o consumo", "RF + todos: R² 0,58. Perfil declarado e rede explicam quase todo o ganho."),
         ("A tensão só é previsível no agregado", "Composição municipal com TVD 0,013; por UC, nenhum modelo supera o acaso."),
         ("A geração não segue a demanda", "Expansão previsível (AUC-PR 6× o acaso) e concentrada no NE e N."),
         ("Validação espacial muda conclusões", "Vizinhança kNN e geoestatística falham em regiões não vistas no treino.")]
for i, (t, d) in enumerate(concl):
    y = 1.9 + i * 0.94
    badge(s, 0.6, y + 0.1, 0.6, str(i + 1), size=16)
    text(s, 1.45, y + 0.05, 6.8, 0.4, t, size=16, bold=True)
    text(s, 1.45, y + 0.45, 6.8, 0.45, d, size=12, color=TEXT2)
card(s, 8.7, 1.95, 4.0, 4.7, fill=ACCENT_SOFT, line=None)
text(s, 9.0, 2.15, 3.5, 0.3, [[("PRODUTOS ENTREGUES", {"spc": 150, "bold": True})]], size=11, color=ACCENT)
prods = ["Bases tratadas em Parquet com dicionário de dados", "Pipeline de comparação de modelos e ablação",
         "Ferramenta de consulta de consumo de nova UC", "Painel web interativo de consumo e geração", "Relatórios de validação e interpretabilidade"]
text(s, 9.0, 2.6, 3.45, 3.9, [[("— ", {"color": ACCENT, "bold": True}), (p, {})] for p in prods], size=15, color=TEXT, after=14, spacing=1.05)

# ====================================================================== 22. Limitações
s = content_slide("Limitações e próximos passos", "Onde o trabalho pode avançar",
                  "Limitações conhecidas dos dados e dos modelos, e a agenda de continuação.")
card(s, 0.6, 1.95, 5.9, 4.7)
text(s, 0.95, 2.15, 5.3, 0.3, [[("LIMITAÇÕES", {"spc": 150, "bold": True})]], size=11, color=TEXT3)
lims = ["Recorte da BDGD com cobertura incompleta da BT em algumas áreas (RJ metropolitano, Enel SP)",
        "Goiás sem coordenadas e com 97% das UCs desativadas",
        "Data de ligação recadastrada em algumas distribuidoras",
        "Geração só centralizada, sem geração distribuída",
        "Modelo regional sem perfil: R² ≈ 0,20; resíduos com I de Moran 0,34"]
text(s, 0.95, 2.6, 5.3, 3.9, [[("— ", {"color": MUTED2, "bold": True}), (p, {})] for p in lims], size=15, color=TEXT2, after=14, spacing=1.05)
card(s, 6.8, 1.95, 5.9, 4.7)
text(s, 7.15, 2.15, 5.3, 0.3, [[("PRÓXIMOS PASSOS", {"spc": 150, "bold": True})]], size=11, color=ACCENT)
nexts = ["Incorporar a geração distribuída (UGBT, UGMT, UGAT) e comparar metrópole × interior",
         "Testar geração + IBGE no modelo regional",
         "Atualizar a interpretabilidade para a rodada completa",
         "Acompanhar consumidores livres fora dos grandes centros",
         "Validar com BDGDs mais recentes nas distribuidoras com problemas de cadastro"]
text(s, 7.15, 2.6, 5.3, 3.9, [[("→ ", {"color": ACCENT, "bold": True}), (p, {})] for p in nexts], size=15, color=TEXT, after=14, spacing=1.05)

# ====================================================================== 23. Encerramento
s = prs.slides.add_slide(BLANK); slide_no[0] += 1
set_bg(s, ACCENT)
text(s, 0.9, 2.5, 11.5, 1.6, "Obrigado!", size=80, font=TITLE_FONT, bold=True, color=SURFACE, anchor=MSO_ANCHOR.MIDDLE)
text(s, 0.9, 4.2, 11, 0.5, "Perguntas e discussão", size=20, color=ACCENT_SOFT)
text(s, 0.9, 6.3, 8, 0.35, [[("Lucas Mendonça Nóbrega", {"bold": True}), ("   ·   dados públicos BDGD/ANEEL, SIGA e IBGE", {})]], size=14, color=SURFACE)

# ====================================================================== 24. Referências
s = content_slide("Referências", "Fontes de dados utilizadas",
                  "Todas as bases são públicas. As datas indicam quando cada extração foi gerada para o projeto.")
refs = [
    ("ANEEL", [
        ("BDGD", "AGÊNCIA NACIONAL DE ENERGIA ELÉTRICA (ANEEL). Base de Dados Geográfica da Distribuidora – BDGD: "
                 "tabelas UCAT, UCMT e UCBT. Data-base 31/12/2025. Disponível em: dadosabertos.aneel.gov.br."),
        ("PRODIST", "ANEEL. Procedimentos de Distribuição (PRODIST), Módulo 10, e Manual de Instruções da BDGD."),
        ("Geração", "ANEEL. Liberação para operação comercial – detalhado. Extração de 06/10/2026. "
                    "Disponível em: dadosabertos.aneel.gov.br."),
        ("SIGA", "ANEEL. SIGA – Sistema de Informações de Geração da ANEEL. Extração de 01/10/2026. "
                 "Disponível em: dadosabertos.aneel.gov.br/dataset/siga-sistema-de-informacoes-de-geracao-da-aneel."),
    ]),
    ("IBGE e apoio", [
        ("Censo", "INSTITUTO BRASILEIRO DE GEOGRAFIA E ESTATÍSTICA (IBGE). Censo Demográfico 2022 (tabela 4714) e "
                  "Censo Demográfico 2010 (tabela 202). SIDRA. Disponível em: sidra.ibge.gov.br."),
        ("PIB", "IBGE. Produto Interno Bruto dos Municípios (tabela 5938): PIB 2023 e valor adicionado por setor 2021. "
                "SIDRA. Disponível em: sidra.ibge.gov.br."),
        ("Sedes", "KELVINS. Municípios brasileiros: coordenadas das sedes municipais, derivadas do IBGE. "
                  "Disponível em: github.com/kelvins/municipios-brasileiros."),
    ]),
]
for i, (grupo, itens) in enumerate(refs):
    x = 0.6 + i * 6.2
    card(s, x, 1.95, 5.9, 4.7)
    text(s, x + 0.35, 2.15, 5.2, 0.3, [[(grupo.upper(), {"spc": 150, "bold": True})]], size=11, color=ACCENT)
    text(s, x + 0.35, 2.6, 5.2, 3.9,
         [[(tag + "  ", {"bold": True, "color": ACCENT}), (ref, {})] for tag, ref in itens],
         size=11, color=TEXT2, after=10, spacing=1.08)

# fontes do tema: títulos em Dancing Script, corpo em Inter
theme_part = [p for p in prs.part.package.iter_parts() if p.partname.endswith("theme1.xml")][0]
xml = theme_part.blob.decode("utf-8")
import re
xml = re.sub(r'(<a:majorFont>\s*<a:latin typeface=")[^"]*"', r'\1Dancing Script"', xml, count=1)
xml = re.sub(r'(<a:minorFont>\s*<a:latin typeface=")[^"]*"', r'\1Inter"', xml, count=1)
theme_part._blob = xml.encode("utf-8")

prs.core_properties.title = "Consumo e expansão do mercado de energia elétrica no Brasil"
prs.core_properties.author = "Lucas Mendonça Nóbrega"
prs.save(OUT)
print("ok", OUT, slide_no[0], "slides")
