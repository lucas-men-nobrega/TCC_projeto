# Metodologia — Modelagem Espacial do Consumo e da Expansão do Mercado de Energia Elétrica no Brasil

> Síntese metodológica para composição de proposta. Detalhes de implementação estão em [`README.md`](README.md) e [`modelagem/README.md`](modelagem/README.md). Números de desempenho referem-se à rodada completa de 16/10/2026, salvo indicação contrária.

---

## 1. Contexto e problema

O projeto investiga, com dados públicos regulatórios da ANEEL, **onde a energia elétrica é consumida no Brasil, como a demanda se distribui entre os níveis de tensão e onde o mercado está se expandindo**. A pesquisa parte de duas perguntas:

1. O mercado de energia está se descentralizando para o interior ou permanece concentrado nas grandes metrópoles?
2. Como essa dinâmica reconfigura a demanda sobre as redes de distribuição?

Para respondê-las, a metodologia combina engenharia de dados em larga escala (≈ 11 milhões de unidades consumidoras), aprendizado de máquina espacial e validação estatística rigorosa, com o cuidado central de **medir a capacidade real de generalização para regiões não vistas no treino**.

---

## 2. Objetivos (tarefas de modelagem)

| Tarefa | Pergunta | Unidade | Tipo |
| :--- | :--- | :--- | :--- |
| **1 · Consumo de nova UC** | Qual o consumo anual (kWh) de uma nova unidade consumidora, dada sua localização e o perfil declarado no pedido de ligação? | UC | Regressão |
| **2 · Grupos de tensão** | Que proporção de novas UCs numa região será de baixa (BT), média (MT) ou alta tensão (AT)? | UC e município | Classificação / composição |
| **3 · Expansão da geração** | Quais municípios receberão nova potência de geração centralizada nos 5 anos seguintes? | Município | Classificação + regressão (*hurdle*) |
| **Mapeamento territorial** | Quais municípios são polos consolidados, fronteiras de expansão ou de baixa dinâmica? | Município | Índice descritivo + quadrantes |

---

## 3. Fontes de dados

| Fonte | Conteúdo | Uso |
| :--- | :--- | :--- |
| **BDGD / ANEEL** (PRODIST Módulo 10, data-base 31/12/2025) | Tabelas `UCAT`, `UCMT`, `UCBT`: 10,95 milhões de UCs, consumo mensal, coordenadas, grupo de tensão e tarifário, data de ligação, perfil declarado (classe, CNAE, carga instalada, demanda contratada), distribuidora e conjunto elétrico | Alvo e variáveis das Tarefas 1 e 2; índice de expansão |
| **ANEEL — Liberação para operação comercial** | 59.581 unidades geradoras (134,9 GW, 2.772 usinas) | Variáveis de geração e alvo da Tarefa 3 |
| **ANEEL — SIGA** | Coordenadas e municípios das usinas; usinas em obra | Georreferenciamento das usinas; validação externa da Tarefa 3 |
| **IBGE / SIDRA** | Censo 2010 e 2022, PIB dos Municípios | Contexto socioeconômico municipal |
| **IBGE — sedes municipais** | Latitude/longitude das sedes | Imputação de posição e previsões regionais |

---

## 4. Preparação dos dados

O tratamento segue um pipeline reprodutível em três etapas:

1. **Pré-filtragem:** conversão dos CSVs da BDGD (até 5 GB cada) para Parquet com compressão zstd, com leitura em *streaming* para caber em memória.
2. **Seleção de colunas:** mantêm-se apenas as variáveis de interesse. Variáveis **derivadas do próprio consumo** (tipo de curva de carga, demandas medidas) são descartadas na origem para evitar vazamento de informação.
3. **Junção territorial:** *left join* com a tabela de municípios do IBGE. UCs sem coordenada recebem a posição da sede municipal, com rastreio da origem (`COORD_ORIGEM`). **Coordenadas imputadas não são usadas no treino**, apenas para posicionar o município nas previsões.

Regras adicionais de qualidade:

- Apenas UCs **ativas** entram na modelagem (9,54 milhões).
- Energia anual = soma dos 12 meses; na AT, soma de ponta + fora de ponta.
- Datas de ligação posteriores à data-base (2025) são descartadas.
- UCs ligadas no próprio ano da data-base têm o consumo **anualizado** (`ENE × 12 / meses desde a ligação`).
- Usinas georreferenciadas via cruzamento pelo código CEG com o SIGA, com validação de coerência UF × coordenada: 97,2% do MW com coordenada verificada.

Cada etapa foi validada por testes de conferência (contagem de linhas, nulos e somas contra a base bruta), que identificaram e corrigiram, entre outros, a omissão do consumo fora de ponta na AT (que representava ≈ 91% do consumo real do grupo).

---

## 5. Engenharia de variáveis

As variáveis foram organizadas em **grupos temáticos**, o que permite medir a contribuição de cada um por ablação:

| Grupo | Variáveis | Observação |
| :--- | :--- | :--- |
| **Posição (base)** | Latitude/longitude; coordenadas rotacionadas (15°, 30°, 45°, 60°) | Rotações reduzem os "cortes em escada" das árvores sobre coordenadas puras |
| **Vizinhança** | Lags espaciais *k*-NN (consumo e composição dos vizinhos), densidade local | BallTree com distância *haversine* |
| **Ligação** | Grupo de tensão e grupo tarifário (categórico + *target encoding* com suavização bayesiana) | |
| **Perfil declarado** | Classe/subclasse, divisão CNAE, fases, tensão de fornecimento, área urbana/rural, carga instalada, demanda contratada, consumidor livre, GD | Informação disponível no pedido de ligação |
| **Rede** | Distribuidora (*target encoding*); tamanho e composição do conjunto elétrico | Alimentador excluído após detecção de vazamento estrutural |
| **IBGE** | População, densidade, crescimento 2010–2022, urbanização, PIB per capita, estrutura setorial do valor adicionado | |
| **Geração (`GER_*`)** | Distância à usina mais próxima; MW a 25/50/100 km; MW renováveis e recentes; nº de usinas a 50 km | Fonte externa, sem uso do alvo |

**Prevenção de vazamento** foi tratada como requisito metodológico explícito:

- *Target encodings* recalculados dentro de cada fold;
- variáveis que determinam o próprio alvo excluídas (ex.: demanda contratada e tensão de fornecimento na Tarefa 2);
- o alimentador foi descartado após um teste mostrar que seu "poder preditivo" (acurácia balanceada de 0,33 → 0,72) vinha do formato do registro na BDGD, não de informação física;
- na Tarefa 3, todas as variáveis usam apenas dados até o ano de corte, inclusive o IBGE (retrato de 2010), com verificação por `assert`.

---

## 6. Algoritmos comparados

A seleção cobre as principais famílias de modelagem espacial, do mais simples ao mais sofisticado, com linhas de base explícitas:

| Família | Algoritmos | Justificativa |
| :--- | :--- | :--- |
| **Linha de base** | *k*-NN espacial; média nacional; persistência (Tarefa 3) | Referência mínima de desempenho |
| **Gradient Boosting** | LightGBM, XGBoost, CatBoost | Estado da arte em dados tabulares; captura não linearidades e interações |
| **Random Forest** | RF padrão (lat/lon) e RF espacial (RF-sp) | Robustez a ruído e *outliers*; compara coordenadas brutas × lags espaciais |
| **Estatística espacial** | GWR e MGWR | Coeficientes locais interpretáveis; diagnóstico de escala espacial |
| **Processos Gaussianos** | Krigagem com regressão; GP classificador | Estimativa probabilística com incerteza espacial |
| **Modelos lineares** | Regressão logística (multinomial), Ridge | Interpretabilidade e calibração |

---

## 7. Protocolo de validação

### 7.1 Validação cruzada espacial em blocos (*Spatial Block CV*)

Pela **Primeira Lei da Geografia de Tobler**, pontos próximos são mais parecidos que pontos distantes. Uma validação cruzada aleatória coloca vizinhos no treino e no teste e superestima o desempenho. Por isso:

- o território é dividido em **50 blocos contíguos** (K-means sobre coordenadas projetadas);
- os blocos são distribuídos em folds com *GroupKFold*, de modo que **regiões inteiras ficam fora do treino**;
- o esquema é repetido com sementes diferentes: **5 folds × 3 repetições = 15 folds**;
- a amostragem é estável (chave determinística), garantindo reprodutibilidade entre rodadas.

### 7.2 Validação temporal e externa (Tarefa 3)

- **Temporal:** treino com corte em T = 2015 (ou cortes empilhados 2011/2013/2015), teste em T = 2020 com alvo 2021–2025.
- **Espacial:** 5 folds × 3 repetições em T = 2020.
- **Externa:** a previsão 2026–2030 é confrontada com as **usinas em obra no SIGA**, dado que não foi usado no treino.

### 7.3 Comparação estatística entre modelos (ablação)

A contribuição de cada grupo de variáveis é medida comparando o modelo com e sem o grupo **nos mesmos folds**, com:

- delta médio e intervalo de 95%;
- número de folds em que o grupo ajudou;
- **teste t pareado com correção de Nadeau-Bengio**, que corrige o otimismo do teste t comum quando os folds compartilham dados de treino;
- teste de Wilcoxon como complemento não paramétrico.

---

## 8. Tratamento estatístico e métricas

**Transformação do alvo (Tarefa 1).** O consumo varia em ordens de grandeza (distribuição assimétrica de cauda longa). Modela-se `ln(1 + kWh)` e, na volta para kWh, aplica-se o **fator de *smearing* de Duan**, estimado com os resíduos fora da amostra, para corrigir o viés de retransformação. As faixas de previsão de 80% vêm dos resíduos fora da amostra, por grupo de tensão.

**Amostragem estratificada com pesos.** A amostra (121.884 UCs) é estratificada por grupo de tensão para não sub-representar MT e AT. Cada registro recebe peso `N_população / N_amostra`, restaurando as proporções reais.

**Métricas:**

| Tarefa | Métricas |
| :--- | :--- |
| 1 · Consumo | RMSE, MAE e R² em log; MdAPE (erro percentual absoluto mediano); viés |
| 2 · Tensão por UC | Log-loss ponderada, F1 macro, acurácia balanceada, AUC-PR por classe, **TVD regional** (distância de variação total entre composição observada e prevista por município) |
| 2 · Composição municipal | TVD, erro absoluto na fração de MT/AT, R² da fração de MT |
| 3 · Expansão da geração | AUC-PR (métrica principal, dado o desbalanceamento de 5,4%), AUC-ROC, log-loss, Brier, precisão no top-*k*; calibração isotônica |

---

## 9. Interpretabilidade

Para explicar *por que* os modelos preveem o que preveem:

- **Importância por permutação por grupo** nos folds de teste (não favorece variáveis contínuas, ao contrário da importância por impureza);
- **SHAP** nativo (LightGBM e CatBoost);
- **Dependência parcial** das variáveis-chave (demanda contratada, carga instalada, distância à usina, densidade);
- **Análise de resíduos**: mapa por município, **I de Moran** e R² por região, grupo de tensão e distribuidora;
- **Coeficientes padronizados** da logística multinomial (composição municipal).

---

## 10. Controle de qualidade do índice de expansão

O índice de expansão do consumo (percentil das conexões recentes e do crescimento entre janelas de 3 anos) revelou um problema de dados: em algumas distribuidoras, as datas de ligação foram aparentemente **recadastradas** (AP 96%, PI 84% de UCs "ligadas" nos últimos 3 anos, contra 12% no Brasil). Em resposta, foi criado um **selo de confiabilidade**:

- **Suspeita de recadastramento:** fração de ligações recentes acima de 3× a mediana nacional, avaliada por município e por distribuidora;
- **Evidências independentes:** geração nova a até 50 km e crescimento populacional do Censo;
- **Selo Alta / Média / Baixa** por município;
- **Índice normalizado por distribuidora**, que elimina o efeito de recadastramentos em bloco e eleva a correlação com o crescimento populacional de 0,06 para 0,21.

Os municípios são então classificados em **quadrantes** (corte no percentil 80 de consumo e de expansão): *Polo consolidado em expansão*, *Polo consolidado*, *Fronteira de expansão* e *Baixa dinâmica*.

---

## 11. Principais resultados

### Tarefa 1 — Consumo de nova UC
- **Modelo final: Random Forest + todos os grupos.** RMSE log = 1,267 ± 0,051; **R² = 0,58**; MdAPE = 54%.
- Supera CatBoost e LightGBM com significância (13–14 de 15 folds; p corrigido < 0,05).
- O ganho vem sobretudo do **perfil declarado** (+0,35 de R²) e da **rede** (+0,17); a localização pura explica pouco (R² ≈ 0,15).
- Modelos geoestatísticos (krigagem, GWR) ficaram abaixo do ML: o consumo individual é dominado por atributos da própria UC.
- Uso adequado: **estimativa de ordem de grandeza** para pedidos de ligação (erro típico de ≈ 2,5×).

### Tarefa 2 — Grupos de tensão
- Por UC, nenhum modelo discrimina as classes (acurácia balanceada ≈ 0,33): quase toda UC é BT.
- No agregado, a composição é previsível. Por UC agregada, o melhor é o **CatBoost + todos** (TVD = 0,070).
- No **modelo municipal**, a melhor é uma **regressão logística multinomial** (TVD = 0,0126; R² da fração de MT = 0,47), 34% melhor que a média nacional. IBGE e distribuidora são decisivos (15/15 folds, p < 0,001).
- A vizinhança espacial (*k*-NN) **piora** todos os modelos na validação por blocos, exemplo concreto de variável que só parece útil sob validação aleatória.

### Tarefa 3 — Expansão da geração
- **Random Forest + IBGE 2010:** AUC-PR = 0,34 (prevalência 0,054; ≈ 6× o acaso e 2× as linhas de base).
- **Validação externa:** 30 dos 50 municípios de maior probabilidade já têm usina em obra no SIGA (precisão de 60%, contra 34% da persistência).
- A expansão é **dependente da trajetória**: a geração já instalada é o principal preditor, e a dinâmica de consumo quase não pesa. A geração centralizada **não segue a demanda**.

### Leitura territorial
- AT (0,02% das UCs) consome 33% da energia; MT, 54%; BT (97% das UCs), 13%.
- Desde 2014, Nordeste e Norte receberam 71% da nova potência, mas concentram 19% do consumo; Sudeste e Sul somam 74% do consumo.

---

## 12. Produtos entregues

- **Bases tratadas** em Parquet, com dicionário de dados e rastreio de imputações.
- **Pipeline de comparação de modelos** parametrizável (amostra, folds, grupos de variáveis, ablação).
- **Ferramenta de consulta** (`prever_nova_uc.py`): consumo esperado de uma nova UC por município, coordenada ou perfil de ligação, com faixa de 80% e selo de confiabilidade.
- **Painel web interativo** de consumo e geração (mapa, filtros, comparação entre localidades e previsões integradas).
- **Relatórios** de comparação, ablação, interpretabilidade e validação.

---

## 13. Limitações

- O recorte `_PJ` da BDGD parece não cobrir todo o mercado (baixa participação residencial); a extrapolação exige confirmação.
- Goiás (UCs sem coordenada e 97% desativadas) e a região metropolitana do RJ (quase sem BT no recorte) têm cobertura insuficiente.
- A data de ligação é pouco confiável em algumas distribuidoras (mitigado pelo selo).
- A base de geração cobre apenas usinas centralizadas fiscalizadas, sem geração distribuída, e é incompleta antes de 2014.
- O modelo regional (nova UC sem perfil declarado) tem capacidade preditiva limitada (R² ≈ 0,20).
- Resíduos da Tarefa 1 ainda têm autocorrelação espacial (I de Moran = 0,34), indicando estrutura regional não capturada.

## 14. Próximos passos

1. Incorporar a **geração distribuída** (tabelas `UGBT`, `UGMT`, `UGAT`) e comparar metrópoles × interior ano a ano.
2. Testar a combinação **geração + IBGE** no modelo regional e um modelo de composição mais calibrado para o mapa de tensão.
3. Atualizar a análise de interpretabilidade para a configuração da rodada completa.
4. Investigar a evolução de consumidores livres fora dos grandes centros.
5. Validar com versões mais recentes da BDGD das distribuidoras com problemas de cadastro.
