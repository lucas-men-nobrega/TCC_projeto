# Interpretabilidade dos modelos

Por que os modelos preveem o que preveem: importância por grupo (permutação fora da amostra), SHAP nativo, dependência parcial, resíduos no espaço e coeficientes.

## A. Tarefas 1 e 2 por UC
Amostra estratificada de 121.884 UCs. 5 folds espaciais (50 blocos K-means). 400 árvores · alvo anualizado · mesma configuração da rodada final (folds = 1ª repetição da comparação).

### Importância por grupo (permutação nos folds de teste)
Aumento médio do erro ao embaralhar juntas as colunas do grupo. Grupos correlacionados (ex.: perfil e grupo de tensão) dividem a informação: a importância de cada um é o que só ele traz.

| tarefa | modelo | grupo | aumento_erro | aumento_erro_dp |
|---|---|---|---|---|
| 1 · consumo | LightGBM (feat. espaciais) + todos | Geração (usinas no entorno) | 0,0051 | 0,0028 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Grupo de tensão e tarifa | 0,3597 | 0,0970 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | IBGE (município) | 0,0058 | 0,0044 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Perfil declarado da UC | 1,3399 | 0,1094 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Posição (lat/lon e rotações) | 0,2276 | 0,1780 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Rede (distribuidora e conjunto) | 0,4662 | 0,1852 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Vizinhança (lags kNN e densidade) | 0,0085 | 0,0044 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Geração (usinas no entorno) | 0,0026 | 0,0020 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Grupo de tensão e tarifa | 0,2408 | 0,0557 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | IBGE (município) | 0,0092 | 0,0080 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Perfil declarado da UC | 1,4097 | 0,1807 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Posição (lat/lon e rotações) | 0,1737 | 0,1214 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Rede (distribuidora e conjunto) | 0,5225 | 0,1992 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | Geração (usinas no entorno) | 0,0012 | 0,0013 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | IBGE (município) | 0,0031 | 0,0026 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | Posição (lat/lon e rotações) | -0,0001 | 0,0028 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | Rede (distribuidora e conjunto) | 0,0153 | 0,0124 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | Vizinhança (lags kNN e densidade) | 0,0076 | 0,0075 |

Gráficos: `importancia_grupos_*.png`.

### SHAP (nativo)
- Tarefa 1 · LightGBM + todos — variáveis com maior |SHAP| médio: TE_GRU_TEN, LOG_DEM_CONT, LOG_CAR_INST, TE_FAS_CON, TE_DIST, LIV (`shap_t1_lightgbm.png`).
- Tarefa 2 · CatBoost + todos, log-odds de MT — LOG_DIST_1_KM, KNN_P_MT, KNN_P_BT, LOG_DIST_K_KM, IBGE_PART_INDUSTRIA, REDE_P_MT (`shap_t2_catboost_mt.png`).
- O RF (melhor da tarefa 1) não tem SHAP nativo; é explicado pela permutação e pela dependência parcial.

### Dependência parcial — Tarefa 1, RF + todos (`dependencia_parcial_t1_rf.png`)
Consumo médio previsto quando uma variável é fixada em cada valor e as demais seguem como observadas (demanda contratada só nas UCs de MT; carga instalada só nas de BT).

### Onde o modelo erra — resíduos fora da amostra (RF + todos)
- I de Moran dos resíduos médios por município (vizinhança 8-NN): **0,261** (p = 0,002). Valor positivo e significativo = sobra estrutura espacial não explicada (falta variável regional); próximo de zero = os erros não se agrupam no espaço. Mapa: `residuos_mapa_t1.png`.

| REGIAO | n_UC | R2_log | vies_log |
|---|---|---|---|
| Centro-Oeste | 9.426,0000 | 0,4475 | 0,0841 |
| N/D | 16,0000 | 0,5009 | -0,4619 |
| Nordeste | 28.760,0000 | 0,4820 | 0,0684 |
| Norte | 8.974,0000 | 0,5895 | 0,0950 |
| Sudeste | 42.847,0000 | 0,6911 | 0,0883 |
| Sul | 31.861,0000 | 0,4087 | 0,0926 |

| GRU_TEN | n_UC | R2_log | vies_log |
|---|---|---|---|
| AT | 1.769,0000 | 0,1844 | 0,7643 |
| BT | 59.933,0000 | 0,4515 | 0,0862 |
| MT | 60.182,0000 | 0,5787 | 0,0554 |

Distribuidoras com mais UCs na amostra (pior → melhor R²):

| DIST | n_UC | R2_log | vies_log |
|---|---|---|---|
| 2866 | 12.920,0000 | 0,3238 | 0,0548 |
| 405 | 5.226,0000 | 0,3271 | 0,0547 |
| 47 | 10.451,0000 | 0,3832 | 0,1401 |
| 396 | 9.055,0000 | 0,3847 | 0,1700 |
| 43 | 6.078,0000 | 0,4720 | -0,0305 |
| 385 | 3.855,0000 | 0,5799 | -0,0783 |
| 63 | 9.227,0000 | 0,6484 | 0,0296 |
| 5697 | 4.967,0000 | 0,7922 | 0,1739 |
| 390 | 3.472,0000 | 0,8689 | -0,1707 |
| 4950 | 8.548,0000 | 0,8706 | 0,0448 |

## B. Tarefa 3 — expansão da geração
RF + IBGE 2010 treinado em T=2015; AUC-PR no teste temporal (T=2020) = 0.337.

### Importância por grupo (queda da AUC-PR ao permutar o grupo)
| grupo | n_colunas | queda_AUC_PR | queda_AUC_PR_dp |
|---|---|---|---|
| Posição (lat/lon) | 2 | 0,0581 | 0,0041 |
| Conexões de consumo (DAT_CON) | 5 | 0,0047 | 0,0026 |
| Geração já instalada | 9 | 0,2258 | 0,0054 |
| IBGE 2010 | 8 | 0,0316 | 0,0078 |

### Dependência parcial (`dependencia_parcial_t3.png`)
Probabilidade média de receber geração quando a variável é fixada em cada valor.

### Por que os municípios do topo? Percentil nacional de cada variável (T=2025)
| MUNICIPIO | UF | PROB | MW já no município (log) | Distância à usina (log km) | PIB per capita 2010 (log) | Part. agro no VA 2010 | Crescimento de conexões (log) |
|---|---|---|---|---|---|---|---|
| Areia de Baraúnas | PB | 0,9230 | 96,0000 | 9,0000 | 26,0000 | 21,0000 | 86,0000 |
| São José do Sabugi | PB | 0,8880 | 97,0000 | 10,0000 | 26,0000 | 43,0000 | 9,0000 |
| Campo Redondo | RN | 0,8840 | 98,0000 | 9,0000 | 13,0000 | 14,0000 | 80,0000 |
| Lagoa do Barro do Piauí | PI | 0,8810 | 99,0000 | 6,0000 | 6,0000 | 33,0000 | 97,0000 |
| Ruy Barbosa | RN | 0,8730 | 96,0000 | 4,0000 | 22,0000 | 14,0000 | 61,0000 |
| Paranatama | PE | 0,8640 | 98,0000 | 10,0000 | 16,0000 | 45,0000 | 85,0000 |
| Mulungu do Morro | BA | 0,8530 | 98,0000 | 16,0000 | 4,0000 | 38,0000 | 19,0000 |
| Simões | PI | 0,8500 | 99,0000 | 11,0000 | 6,0000 | 31,0000 | 97,0000 |
| Igaporã | BA | 0,8470 | 99,0000 | 7,0000 | 8,0000 | 41,0000 | 68,0000 |
| Queimada Nova | PI | 0,8410 | 98,0000 | 9,0000 | 5,0000 | 35,0000 | 95,0000 |
| Betânia do Piauí | PI | 0,8410 | 98,0000 | 17,0000 | 6,0000 | 48,0000 | 96,0000 |
| Curral Novo do Piauí | PI | 0,8400 | 99,0000 | 27,0000 | 1,0000 | 33,0000 | 99,0000 |

## C. Tarefa 2 por município — o que explica a fração de MT
Logística multinomial (melhor modelo), variáveis padronizadas: cada coeficiente é a variação na log-razão de chances de uma UC ser MT (ou AT) em vez de BT quando a variável sobe 1 desvio-padrão, com as demais fixas. Variáveis correlacionadas (ex.: densidade e urbanização) dividem o efeito.

| variavel | MT_vs_BT_log_odds | MT_vs_BT_razao_chances | AT_vs_BT_log_odds |
|---|---|---|---|
| IBGE_LOG_POP | 0,6583 | 1,9314 | 0,3626 |
| LOG_N_UC | -0,5784 | 0,5608 | -0,2921 |
| DIST_P_MT | 0,2425 | 1,2744 | 0,1338 |
| DIST_P_BT | -0,2387 | 0,7877 | -0,1331 |
| DIST_P_AT | -0,2053 | 0,8144 | 0,0190 |
| IBGE_URBANIZACAO | 0,2018 | 1,2236 | 0,0822 |
| IBGE_LOG_PIB_PC | 0,1918 | 1,2114 | 0,2065 |
| IBGE_PART_ADM | -0,1819 | 0,8337 | -0,1320 |
| IBGE_PART_AGRO | 0,1217 | 1,1294 | -0,0867 |
| IBGE_LOG_DENS | -0,0950 | 0,9094 | -0,0148 |
| IBGE_PART_SERVICOS | 0,0586 | 1,0603 | 0,0085 |
| GER_MW_RENOV_50 | 0,0569 | 1,0586 | 0,0453 |
| GER_MW_25 | 0,0555 | 1,0571 | 0,1362 |
| GER_MW_RECENTE_50 | -0,0479 | 0,9532 | 0,0487 |
| GER_MW_50 | 0,0461 | 1,0472 | 0,0855 |

Gráfico: `coeficientes_composicao.png`.
