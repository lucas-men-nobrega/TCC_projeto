# ⚡ Modelagem de Machine Learning e Análise Espacial (BDGD / ANEEL)

Este módulo implementa o pipeline comparativo e preditivo de Machine Learning desenhado para responder às hipóteses de pesquisa e aos requisitos do arquivo [`Procurando algoritmos ML.txt`](file:///c:/Users/LUCAS/OneDrive/%C3%81rea%20de%20Trabalho/TCC_projeto/Procurando%20algoritmos%20ML.txt).

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
