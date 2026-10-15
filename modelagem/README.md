# ⚡ Modelagem de Machine Learning e Análise Espacial (BDGD / ANEEL)

Este módulo implementa o pipeline comparativo e preditivo de Machine Learning desenhado para responder às hipóteses de pesquisa e aos requisitos do arquivo [`Procurando algoritmos ML.txt`](../Procurando%20algoritmos%20ML.txt).

> Visão geral do projeto, dicionário de dados, legendas dos códigos da BDGD e conclusões: veja o [README principal](../README.md).

---

## 📥 Dados de Entrada

O script lê `base/filtrados/{alta,media,baixa}_tensao_municipios.parquet` e usa:

| Coluna | Uso |
| :--- | :--- |
| `ENE_01..12` (MT/BT) ou `ENE_P_xx + ENE_F_xx` (AT) | Consumo anual da UC (kWh) — alvo da Tarefa 1 |
| `GRU_TEN` | Feature da Tarefa 1, alvo da Tarefa 2 e estrato da amostragem |
| `GRU_TAR` | Feature da Tarefa 1 (categórica + *target encoding*) |
| `POINT_X`, `POINT_Y` | Longitude e latitude (fora do retângulo do Brasil = descartada) |
| `SIT_ATIV` | Filtro: só UCs ativas (`AT`), salvo com `--incluir-inativas` |
| `DAT_CON` | Ano de conexão (formato BDGD `DD/MM/AAAA`) → índice de expansão |
| `MUN`, `UF`, `NOME_MUNICIPIO` | Agregação por município e blocos da validação cruzada |

UCs sem coordenada válida, com consumo anual zero ou com `GRU_TEN` ausente ficam fora do treino, mas entram nas estatísticas por município (calculadas sobre a base completa).

---

## 🎯 Objetivos Centrais

1. **Previsão de Consumo para uma Nova Unidade Consumidora (UC):**
   * Estimar qual será o consumo anual em kWh (`ENE_01` até `ENE_12`) ao conectar uma nova UC em determinada região geográfica, a partir de sua localização e parâmetros de ligação (`GRU_TEN` e `GRU_TAR`).
2. **Previsão da Distribuição de Grupos de Tensão (`GRU_TEN`):**
   * Estimar a probabilidade e proporção dos níveis de tensão (Alta Tensão, Média Tensão, Baixa Tensão) que uma nova demanda energética assumirá em dada região.
3. **Mapeamento de Regiões de Maior Consumo e Fronteiras em Expansão:**
   * Cruzar as previsões dos modelos e o histórico territorial para classificar os municípios em quadrantes estratégicos: **Polos Consolidados em Expansão**, **Fronteiras de Expansão**, **Polos Consolidados** e **Baixa Dinâmica**.

---

## 🧠 Algoritmos e Famílias Comparadas

Conforme estruturado nas diretrizes de pesquisa:

| Família | Algoritmos Implementados | Tratamento Espacial Específico |
| :--- | :--- | :--- |
| **Gradient Tree Boosting** | **LightGBM**, **XGBoost**, **CatBoost** | Engenharia de features com coordenadas rotacionadas ($15^\circ, 30^\circ, 45^\circ, 60^\circ$) para mitigar cortes em escada, lags espaciais $k$-NN e target encoding com suavização bayesiana. |
| **Modelos Estatísticos Espaciais** | **GWR** (*Geographically Weighted Regression*) e **MGWR** | Modelagem de coeficientes locais variando geograficamente com seleção adaptativa de largura de banda (*bandwidth*) via critério AICc. Diagnóstico multiescalar no MGWR. |
| **Random Forest** | **Random Forest Padrão** vs. **Random Forest Espacial (RF-sp)** | Comparação direta entre o uso de latitude/longitude brutas contra árvores enriquecidas com densidade e lags espaciais de vizinhança. |
| **Processos Gaussianos** | **Krigagem com Regressão** (*Regression-Kriging*) & **GP Classificador** | Decomposição em tendência determinística (Ridge) + componente estocástico espacial modelado por Processo Gaussiano com kernel RBF e ruído branco (*WhiteKernel*), fornecendo intervalos de confiança e incerteza. |
| **Linha de Base** | **Baseline $k$-NN Espacial** | Média e proporções ponderadas dos $k$ vizinhos mais próximos espaciais via *BallTree* esférica (*Haversine*). |

---

## 🛡️ Metodologia: Validação Cruzada Espacial em Blocos (*Spatial Block CV*)

Em dados georreferenciados, a **Primeira Lei da Geografia de Tobler** (*tudo está relacionado a tudo, mas coisas próximas são mais relacionadas que coisas distantes*) provoca vazamento de dados (*spatial data leakage*) se for utilizada a validação cruzada aleatória tradicional.

* **Abordagem adotada:** Divisão do território brasileiro em blocos espaciais contíguos (via *MiniBatchKMeans* nas coordenadas métricas projetadas ou agrupamento por municípios inteiros).
* **Garantia metodológica:** Conjuntos inteiros de teste são mantidos espacialmente isolados do treino em cada fold (*GroupKFold*), medindo a **real capacidade de generalização do modelo para novas regiões geográficas**.
* **Flag de controle:** O parâmetro `--cv-aleatoria` permite rodar em paralelo a validação aleatória para demonstrar no TCC o ganho de realismo metodológico trazido pela validação em blocos.

---

## 📊 Tratamento Estatístico e Métricas

1. **Transformação Logarítmica e Fator de *Smearing* de Duan:**
   * O consumo energético varia em ordens de magnitude (distribuição assimétrica positiva e cauda longa). Modela-se $\ln(1 + \text{Consumo})$.
   * A retransformação exponencial simples subestima o valor esperado. O script calcula automaticamente o fator de correção não paramétrico de **Duan's Smearing** a partir dos resíduos *Out-Of-Fold* (OOF):
     $$\widehat{\text{Consumo}} = \left(e^{\widehat{y}} \cdot \frac{1}{N}\sum e^{y_i - \widehat{y}_i}\right) - 1$$
2. **Ponderação Populacional Estratificada:**
   * A base é amostrada estrategicamente para não sub-representar Alta e Média Tensão. Cada registro recebe peso $w_i = \frac{N_{\text{populacao}}}{N_{\text{amostra}}}$, reproduzindo a realidade de mercado da distribuidora.
3. **Métricas de Avaliação:**
   * **Regressão (Consumo):** RMSE log, MAE log, $R^2$ log, MdAPE (Erro Percentual Absoluto Mediano) e Viés.
   * **Classificação (Grupos de Tensão):** *Log-Loss* multiclasse ponderada, F1-Score Macro, Acurácia Balanceada e **TVD Regional** (*Total Variation Distance* entre a distribuição observada e a prevista por município).

---

## 🚀 Como Executar

### 1. Instalação das Dependências

Na raiz do projeto ou na pasta `modelagem`:
```powershell
pip install -r modelagem/requirements.txt
```

### 2. Execução Rápida (Teste de Validação Inicial)
Executa a validação cruzada com amostra reduzida e número menor de árvores para validar o ambiente em poucos minutos:
```powershell
python modelagem/comparar_modelos_ml.py --rapido
```

### 3. Execução Completa (Produção e Resultados do TCC)
Roda a validação completa com 5 folds espaciais, ajusta os melhores modelos na base integral e gera as projeções para todos os municípios brasileiros:
```powershell
python modelagem/comparar_modelos_ml.py
```

#### Opções e Argumentos Avançados:
* `--cv-aleatoria`: Executa também a validação cruzada aleatória para comparação no texto do TCC.
* `--mgwr`: Executa o diagnóstico multiescalar do MGWR calculando a escala de atuação de cada covariável.
* `--tipo-bloco municipio`: Utiliza limites municipais ao invés de clusters K-means nos folds.
* `--n-blocos 80`: Quantidade de clusters espaciais para particionar o Brasil.
* `--n-arvores 500`: Número de estimadores para os modelos de Gradient Boosting.
* `--grupos ger`: Ablação por grupo de variáveis. Para cada grupo, acrescenta variantes "+ grupo" do RF padrão, do CatBoost e do LightGBM nas duas tarefas e as compara com o modelo base nos mesmos folds. Por enquanto existe o grupo `ger` (variáveis `GER_*` de `features_geracao.py`, que exigem `base/filtrados/unidades_geradoras_geo.parquet`). `--com-geracao` é um atalho para `--grupos ger`.
  * Grava `ablacao.csv` e uma seção no `relatorio.md` com: delta médio, intervalo de 95%, folds em que o grupo ajudou, t pareado com a correção de Nadeau-Bengio (folds de CV compartilham treino, e o t ingênuo é otimista) e o p do Wilcoxon.
* `--grupos perfil`: Perfil declarado da UC, conhecido no pedido de ligação. Só na Tarefa 1.
  * Categorias com *target encoding* ajustado por fold: classe/subclasse (`CLAS_SUB`), divisão CNAE (2 dígitos), fases (`FAS_CON`), tensão de fornecimento (`TEN_FORN`) e área urbana/rural (`ARE_LOC`).
  * Numéricas: log da carga instalada (`CAR_INST`) e da demanda contratada (`DEM_CONT`, só MT/AT), consumidor livre (`LIV`) e GD na UC (`TEM_GD`).
  * Ficam fora por vazamento: `TIP_CC` e `DEM_P_*`/`DEM_F_*`, que são atribuídos ou medidos a partir do consumo. Na Tarefa 2 o grupo inteiro fica fora, porque `DEM_CONT` e `TEN_FORN` determinam o próprio grupo de tensão.
  * As previsões regionais simulam uma nova UC **sem** perfil declarado, então usam o melhor modelo sem esse grupo.
* `--grupos ibge`: Contexto socioeconômico do município da UC, nas duas tarefas ([`features_ibge.py`](features_ibge.py), dados de `base/ibge_municipios.csv`).
  * Variáveis: população e densidade (Censo 2022), crescimento populacional 2010–2022, urbanização (2010), PIB per capita (2023) e participação da agropecuária, indústria, serviços e administração pública no valor adicionado (2021, último ano com setores publicados).
  * Usa o `MUN` da UC; sem ele (previsões regionais), a sede municipal mais próxima.
* `--grupos rede`: Distribuidora e rede elétrica, nas duas tarefas.
  * Distribuidora (`DIST`): *target encoding* ajustado por fold. Na Tarefa 2, é a proporção de cada grupo de tensão por distribuidora no treino.
  * Agregados do conjunto elétrico (`CONJ`, presente em todas as UCs), calculados sobre todas as UCs ativas sem o consumo (`agregados_rede`): tamanho, % MT e AT e % não urbana.
  * Na Tarefa 2 a composição MT/AT do conjunto fica de fora, porque inclui o grupo de tensão da própria UC (vazamento).
  * **O alimentador (`CTMT`/`CTAT`) não é usado.** O registro dele depende da tabela da BDGD: 67% das UCs de BT vêm sem alimentador, a MT quase sempre tem, e cada UC de AT tem o próprio circuito (mediana de 1 UC). Num primeiro teste, o tamanho do alimentador "previa" o grupo de tensão, com acurácia balanceada indo de 0,33 para 0,72. Era vazamento pelo formato do registro, não informação física da rede.
  * Na validação espacial, os conjuntos e alimentadores das regiões de teste não aparecem no treino. Por isso não há *target encoding* deles, só agregados sem o alvo.
  * Como perfil, o grupo não entra nas previsões regionais: a nova UC num município não tem conjunto/alimentador definido.
* `--grupos ...,todos`: Acrescenta a variante combinada "<modelo> + todos", com a união dos demais grupos listados (na Tarefa 2 sem o perfil). `--grupos todos` sozinho ativa todos os grupos disponíveis e a combinação. Assim, a ablação mostra o efeito de cada grupo isolado e do conjunto. A variante combinada não é usada nas previsões regionais, porque inclui perfil e rede.
* `--alvo-anualizado`: UCs ligadas no ano da data-base (2025) só têm os meses desde a ligação. O consumo delas é extrapolado para 12 meses (`ENE × 12 / (13 − mês de ligação)`).
* `--repeticoes R`: Repete a CV espacial com blocos K-means de sementes diferentes (`5 × R` folds). Com 5 folds, o Wilcoxon não passa de p = 0,0625; use `--repeticoes 3` para que os testes da ablação tenham poder.
* `--saida PASTA`: Grava os resultados em outra pasta. Útil para testes rápidos sem sobrescrever `resultados/`.

A amostra é ordenada por uma chave estável antes de montar os folds. Assim, duas rodadas com os mesmos parâmetros produzem os mesmos blocos e as mesmas métricas, e números de rodadas diferentes passam a ser comparáveis.

O ano de referência do índice de expansão tem como teto `ANO_DATA_BASE = 2025` (data-base da BDGD). Datas de ligação posteriores são descartadas.

---

## 🔍 Consulta Pontual e Inferência: `prever_nova_uc.py`

Após rodar a comparação dos modelos, utilize a ferramenta interativa para simular cenários:

```powershell
# 1. Consulta interativa (perguntas e respostas no terminal)
python modelagem/prever_nova_uc.py --interativo

# 2. Consulta por nome do município e estado
python modelagem/prever_nova_uc.py -m "Campinas" -u "SP"

# 3. Consulta por código IBGE
python modelagem/prever_nova_uc.py --mun 3509502

# 4. Consulta por coordenadas geográficas de um novo empreendimento
python modelagem/prever_nova_uc.py --lat -22.905 --lon -47.060
```

---

## 🏭 Geração × Consumo por UF: `analise_geracao_uf.py`

Cruza a base ANEEL de unidades geradoras liberadas para operação comercial (`base/filtrados/unidades_geradoras_filtrada.parquet`) com o consumo das UCs agregado por UF. O consumo usa `carregar_bases` deste módulo, com as mesmas regras de energia e de UCs ativas. A chave é o código IBGE da UF. O DF aparece com geração zero, porque não tem usina na base.

```powershell
python modelagem/analise_geracao_uf.py                     # janela recente desde 2014
python modelagem/analise_geracao_uf.py --ano-inicio 2020   # outra janela
python modelagem/analise_geracao_uf.py --incluir-inativas  # inclui UCs inativas no consumo
```

A janela começa em 2014 porque a ANEEL avisa que a base é incompleta antes disso. Saídas em `resultados/geracao/`:

* `geracao_uf_fonte_ano.csv`: usinas, UGs e MW por UF × tipo de geração × ano de liberação.
* `geracao_vs_consumo_uf.csv`: potência total e recente, % solar+eólica, % ACR, UCs, GWh, participações nacionais e `RAZAO_POT_CONSUMO` (> 1 = UF com perfil exportador).
* `potencia_uf_tipo.png`, `potencia_ano_regiao.png`, `consumo_x_potencia_uf.png` e `relatorio_geracao.md`.

---

## ⚡ Geração como apoio ao modelo de consumo

Os três scripts usam as usinas georreferenciadas pelo SIGA (`base/filtrados/unidades_geradoras_geo.parquet`, gerado por `tratamento_base/merge_municipios/georreferenciar_usinas.py`).

### `features_geracao.py`: variáveis `GER_*`
Calcula, para qualquer ponto, variáveis do entorno com BallTree haversine:
* `GER_LOG_DIST_KM`: distância (log) até a usina mais próxima;
* `GER_MW_25/50/100`: MW liberados a até 25, 50 e 100 km (log1p);
* `GER_MW_RENOV_50`: MW de solar + eólica a até 50 km;
* `GER_MW_RECENTE_50`: MW liberados desde 2014 a até 50 km;
* `GER_N_USINAS_50`: número de usinas a até 50 km.

O parâmetro `ano_max` corta as usinas pelo ano de liberação, o que impede uso de dados do futuro. Como as variáveis vêm de fonte externa e não usam o alvo, não há ajuste por fold.

### `modelo_expansao_geracao.py`: Tarefa 3
```powershell
python modelagem/modelo_expansao_geracao.py   # ~2 min
```
* **Pergunta:** quais municípios recebem nova potência liberada nos 5 anos seguintes a um ano de corte T?
* **Variáveis (só até T):** conexões por ano via `DAT_CON`, crescimento e mix de tensão; estoque de geração no município e no entorno; posição da sede. O consumo de 2025 não entra.
* **Retrato IBGE de 2010** (Censo e PIB 2010) como variável. O Censo 2022 e o PIB recente seriam informação do futuro para os cortes; um `assert` impede cortes anteriores a 2010.
* **Validação temporal:** treino com 1 corte (T=2015) ou com cortes empilhados (2011, 2013, 2015); teste em T=2020.
* **Validação espacial:** 5 folds × 3 repetições em blocos, em T=2020, com ablação pareada do IBGE 2010.
* **Validação externa:** a previsão 2026–2030 é comparada às usinas em obra no SIGA sem UG liberada (`base/filtrados/siga_obras.parquet`, gerado por `georreferenciar_usinas.py`). Métricas: AUC-PR, AUC-ROC, precisão e % do MW em obra nos 50/100/200 primeiros, contra a persistência.
* **Calibração:** isotônica, com curva de confiabilidade em `tarefa3_confiabilidade.png`.
* **Modelos:** kNN espacial e persistência como linhas de base, regressão logística, RF, LightGBM e CatBoost. Há também uma parte contínua (*hurdle*) para os MW recebidos.
* **Saídas em `resultados/geracao/`:** `tarefa3_comparacao.csv`, `tarefa3_por_fold.csv`, `tarefa3_ablacao_ibge.csv`, `tarefa3_calibracao.csv`, `tarefa3_validacao_obras_siga.csv`, `tarefa3_mw_comparacao.csv`, `tarefa3_importancia.csv`, `previsao_expansao_geracao_municipios.csv` (probabilidade para 2026–2030 e MW em obra no SIGA) e `relatorio_tarefa3.md`.

### `modelo_composicao_tensao.py`: Tarefa 2 por município
```powershell
python modelagem/modelo_composicao_tensao.py   # ~11 min (5 folds × 3 repetições)
```
* **Pergunta:** que fração das UCs de um município é BT, MT ou AT? Por UC, nenhum modelo honesto separa as classes, porque quase toda UC é BT. No agregado, a composição é previsível.
* **Modelo multinomial agregado:** cada município vira 3 linhas (BT, MT, AT), com peso igual à fração observada; o classificador estima a composição esperada.
* **Grupos de variáveis:**
  * base: sede, rotações e log do número de UCs;
  * `knn`: composição dos vizinhos do treino;
  * `ibge`;
  * `ger`;
  * `rede`: composição média por distribuidora no treino, sem incluir o próprio município.
  * A combinação **"todos (sem knn)"** exclui o lag espacial. Na validação por blocos ele piora todos os modelos, porque os vizinhos do treino ficam em outra região.
* **Cobertura:** municípios com menos de 10 UCs ativas por mil habitantes (282, quase todos de GO e da região metropolitana do RJ, onde o recorte quase não tem BT) ficam fora do treino e da avaliação. Eles recebem previsão, marcada como `COBERTURA_INSUFICIENTE`.
* **Validação:** espacial em blocos sobre as sedes, com ablação pareada (t corrigido e Wilcoxon).
* **Métricas:** TVD da composição, erro absoluto e R² da fração de MT.
* **Saídas em `resultados/composicao/`:** comparação, por fold, ablação, composição prevista por município (com o desvio entre a fração de MT observada e a prevista) e `relatorio_composicao.md`.

### `explicar_modelos.py`: interpretabilidade
```powershell
python modelagem/explicar_modelos.py                 # partes A, B e C (~25 min)
python modelagem/explicar_modelos.py --partes C      # só os coeficientes por município (segundos)
```
Responde por que os modelos preveem o que preveem, sem dependência nova. Saídas em `resultados/explicacao/`, com `relatorio_explicacao.md`.
* **A · Tarefas 1 e 2 por UC** (configuração do modo rápido, 3 folds espaciais):
  * **Importância por grupo por permutação** nos folds de teste: embaralha juntas as colunas de cada grupo (posição, vizinhança, grupo de tensão/tarifa, perfil, rede, IBGE, geração) e mede o aumento do erro. Ao contrário da importância por impureza, não favorece variáveis contínuas.
  * **SHAP nativo:** LightGBM (`pred_contrib`) na Tarefa 1 e CatBoost (`ShapValues`, log-odds de MT) na Tarefa 2. O RF, que não tem SHAP nativo, é explicado pela permutação e pela dependência parcial.
  * **Dependência parcial** do RF + todos: demanda contratada (MT), carga instalada (BT), distância à usina, densidade, peso da indústria e encoding da distribuidora.
  * **Resíduos fora da amostra:** mapa por município, I de Moran (vizinhança 8-NN, `libpysal`) e R² por região, grupo de tensão e distribuidora.
* **B · Tarefa 3:** queda da AUC-PR ao permutar cada grupo (posição, conexões, geração, IBGE 2010), dependência parcial e o perfil em percentis dos municípios de maior probabilidade.
* **C · Tarefa 2 por município:** coeficientes padronizados da logística multinomial (log-razão de chances de MT e AT em relação à BT por +1 desvio-padrão).

### `validacao_expansao.py`: selo de confiabilidade
```powershell
python modelagem/validacao_expansao.py   # depois de comparar_modelos_ml.py
```
* **Suspeita de recadastramento,** com o mesmo limiar absoluto (3× a mediana municipal da fração de UCs ativas ligadas nos últimos 3 anos, ≈ 37%):
  * **por município;**
  * **por distribuidora,** que é a unidade real do recadastramento. Os municípios de uma distribuidora suspeita herdam a suspeita. Hoje são 4: as do PI, PA, AL e AP, com 58% a 99% de ligações "recentes".
* **Cobertura:** municípios com menos de 10 UCs ativas por mil habitantes (GO e RJ metropolitano) recebem selo Baixa.
* **Evidências independentes:** MW liberados em 2021–2025 a até 50 km da sede e crescimento populacional 2010–2022 acima do percentil 75 (Censo).
* **Selo:**
  * **Baixa:** amostra ou cobertura insuficiente, ou suspeita sem evidência independente;
  * **Média:** suspeita, mas com geração nova ou crescimento populacional alto;
  * **Alta:** sem suspeita.
* **Índice normalizado por distribuidora (`INDICE_EXPANSAO_DIST`):** percentil de cada município entre os municípios da **mesma** distribuidora (só distribuidoras com 5 ou mais municípios elegíveis). Um recadastramento que atingiu a distribuidora inteira desloca todos os seus municípios por igual e deixa de dominar o ranking. A correlação com o crescimento populacional do Censo sobe de 0,06 (índice original) para 0,21.
* **Saídas:** `previsoes_regionais_municipios_validado.csv` e `relatorio_validacao.md`, com as distribuidoras suspeitas, as correlações de Spearman do índice (original e normalizado) com o crescimento populacional e com a geração, e o top do índice normalizado. O `prever_nova_uc.py` mostra o selo quando o arquivo validado é mais recente que as previsões.

---

## 📁 Estrutura de Arquivos Gerados (`modelagem/resultados/`)

Ao final do processamento, os seguintes arquivos são gravados:

| Arquivo | Descrição |
| :--- | :--- |
| `comparacao_tarefa1_consumo.csv` | Tabela consolidada com médias e desvios de todas as métricas de regressão por modelo. |
| `comparacao_tarefa1_consumo_por_fold.csv` | Desempenho detalhado de cada fold da validação cruzada espacial. |
| `comparacao_tarefa2_grupos_tensao.csv` | Tabela consolidada das métricas de classificação (`GRU_TEN`). |
| `comparacao_tarefa2_grupos_tensao_por_fold.csv` | Desempenho detalhado por fold na tarefa de classificação. |
| `previsoes_regionais_municipios.csv` | Base consolidada por município contendo: consumo previsto para nova UC (geral e por classe), distribuição prevista de `GRU_TEN`, consumo histórico total, índice de expansão e quadrante. |
| `ranking_maior_consumo.csv` | Top 100 municípios com maiores consumos energéticos anuais. |
| `ranking_expansao.csv` | Top 100 municípios em maior ritmo de expansão energética. |
| `resumo_uf.csv` | Indicadores agregados por Unidade Federativa. |
| `importancia_features_*.csv` | Ranking de importância das features geográficas e espaciais nos modelos de árvores. |
| `comparacao_modelos.png` | Gráfico comparativo de barras com intervalos de erro por modelo. |
| `consumo_x_expansao.png` | Gráfico de dispersão dos quadrantes energéticos dos municípios brasileiros. |
| `relatorio.md` | Relatório executivo sintetizando os principais achados. |

---

## 📈 Índice de Expansão e Quadrantes

Para cada município com ao menos `--min-uc` UCs (padrão 30):

* **Taxa de conexões recentes** = UCs com `DAT_CON` nos últimos `--janela-expansao` anos (padrão 3) ÷ UCs com data válida.
* **Crescimento entre janelas** = (conexões na janela recente + 1) ÷ (conexões na janela anterior + 1).
* **`INDICE_EXPANSAO`** = média dos percentis dessas duas medidas. Se `DAT_CON` não existir, o script usa como *proxy* a tendência linear do consumo mensal (`ENE_01 → ENE_12`), que é sensível à sazonalidade.
* **`QUADRANTE`** = corte no percentil 80 do consumo total e do índice de expansão (legenda no [README principal](../README.md#legenda--quadrante-classificação-dos-municípios)).

> ⚠️ Em algumas distribuidoras, `DAT_CON` parece ter sido recadastrada (AP: 96% e PI: 84% das UCs aparecem conectadas nos últimos 3 anos, contra 12% no Brasil). Isso infla o índice desses estados.

---

## 🏁 Resultados da Execução Rápida (`--rapido`)

Amostra de 32.042 UCs, 3 folds espaciais em 30 blocos K-means, 150 árvores, 9,3 min. As tabelas completas estão em [`resultados/relatorio.md`](resultados/relatorio.md) e a discussão no [README principal](../README.md#-resultados).

| Tarefa | Melhor modelo | Métrica | Baseline kNN |
| :--- | :--- | :--- | :--- |
| 1 — Consumo de nova UC | CatBoost (feat. espaciais) | RMSE log 1,816 · R² log 0,138 | RMSE log 2,101 |
| 2 — Distribuição de `GRU_TEN` | GP classificador (RBF) | Log-loss 0,200 · TVD 0,094 | Log-loss 0,258 · TVD 0,097 |

---

## 🔩 Notas de Implementação

Correções feitas após a primeira execução de teste. Todas foram verificadas na segunda execução, que terminou sem falhas:

* **Parâmetros por modelo:** cada `lambda` da fábrica de modelos captura o próprio dicionário de parâmetros (`lambda par=par: ...`). Antes, LightGBM e XGBoost recebiam os parâmetros do CatBoost.
* **Categorias não vistas no treino:** valores de `GRU_TAR` ausentes no fold de treino viram `NaN` no `Categorical` e, para o CatBoost, são convertidos para `"N/D"`.
* **Previsão do GWR:** o `GWR.predict` do `mgwr` 2.2.1 indexa a matriz de treino pelo índice do ponto previsto e falha quando há mais pontos previstos que de treino. A previsão é feita por mínimos quadrados ponderados locais (kernel bisquare adaptativo do próprio `mgwr`). Nos pontos de treino, ela coincide com o `mgwr` até 2,7 × 10⁻¹⁵.
* **Ano de conexão:** o ano é extraído como o primeiro grupo de 4 dígitos de `DAT_CON`, o que aceita `DD/MM/AAAA` (BDGD) e `AAAA-MM-DD`.
