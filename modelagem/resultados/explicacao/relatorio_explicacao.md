# Interpretabilidade dos modelos

Por que os modelos preveem o que preveem: importância por grupo (permutação fora da amostra), SHAP nativo, dependência parcial, resíduos no espaço e coeficientes.

## A. Tarefas 1 e 2 por UC
Amostra estratificada de 32.042 UCs. 3 folds espaciais (configuração do modo rápido).

### Importância por grupo (permutação nos folds de teste)
Aumento médio do erro ao embaralhar juntas as colunas do grupo. Grupos correlacionados (ex.: perfil e grupo de tensão) dividem a informação: a importância de cada um é o que só ele traz.

| tarefa | modelo | grupo | aumento_erro | aumento_erro_dp |
|---|---|---|---|---|
| 1 · consumo | LightGBM (feat. espaciais) + todos | Geração (usinas no entorno) | 0,0027 | 0,0010 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Grupo de tensão e tarifa | 0,3576 | 0,1200 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | IBGE (município) | 0,0038 | 0,0121 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Perfil declarado da UC | 1,2721 | 0,0961 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Posição (lat/lon e rotações) | 0,0828 | 0,0284 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Rede (distribuidora e conjunto) | 0,3714 | 0,0166 |
| 1 · consumo | LightGBM (feat. espaciais) + todos | Vizinhança (lags kNN e densidade) | 0,0131 | 0,0078 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Geração (usinas no entorno) | 0,0031 | 0,0036 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Grupo de tensão e tarifa | 0,2984 | 0,0697 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | IBGE (município) | 0,0128 | 0,0091 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Perfil declarado da UC | 1,2755 | 0,0767 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Posição (lat/lon e rotações) | 0,0792 | 0,0657 |
| 1 · consumo | Random Forest padrão (lat/lon) + todos | Rede (distribuidora e conjunto) | 0,4331 | 0,0379 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | Geração (usinas no entorno) | 0,0018 | 0,0016 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | IBGE (município) | 0,0072 | 0,0020 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | Posição (lat/lon e rotações) | 0,0030 | 0,0017 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | Rede (distribuidora e conjunto) | 0,0107 | 0,0043 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) + todos | Vizinhança (lags kNN e densidade) | 0,0043 | 0,0010 |

Gráficos: `importancia_grupos_*.png`.

### SHAP (nativo)
- Tarefa 1 · LightGBM + todos — variáveis com maior |SHAP| médio: TE_GRU_TEN, LOG_DEM_CONT, LOG_CAR_INST, TE_FAS_CON, TE_TEN_FORN, TE_DIST (`shap_t1_lightgbm.png`).
- Tarefa 2 · CatBoost + todos, log-odds de MT — LOG_DIST_1_KM, KNN_P_BT, KNN_P_MT, REDE_P_BT, REDE_P_MT, IBGE_URBANIZACAO (`shap_t2_catboost_mt.png`).
- O RF (melhor da tarefa 1) não tem SHAP nativo; é explicado pela permutação e pela dependência parcial.

### Dependência parcial — Tarefa 1, RF + todos (`dependencia_parcial_t1_rf.png`)
Consumo médio previsto quando uma variável é fixada em cada valor e as demais seguem como observadas (demanda contratada só nas UCs de MT; carga instalada só nas de BT).

### Onde o modelo erra — resíduos fora da amostra (RF + todos)
- I de Moran dos resíduos médios por município (vizinhança 8-NN): **0.341** (p = 0.002). Valor positivo e significativo = sobra estrutura espacial não explicada (falta variável regional); próximo de zero = os erros não se agrupam no espaço. Mapa: `residuos_mapa_t1.png`.

| REGIAO | n_UC | R2_log | vies_log |
|---|---|---|---|
| Centro-Oeste | 2.475,0000 | 0,3913 | 0,0733 |
| N/D | 6,0000 | 0,2283 | -1,5232 |
| Nordeste | 7.594,0000 | 0,3424 | 0,2371 |
| Norte | 2.261,0000 | 0,4923 | 0,1438 |
| Sudeste | 11.574,0000 | 0,6472 | 0,0553 |
| Sul | 8.132,0000 | 0,3673 | -0,0083 |

| GRU_TEN | n_UC | R2_log | vies_log |
|---|---|---|---|
| AT | 1.769,0000 | 0,1937 | 0,5395 |
| BT | 15.109,0000 | 0,3852 | 0,0926 |
| MT | 15.164,0000 | 0,4701 | -0,0368 |

Distribuidoras com mais UCs na amostra (pior → melhor R²):

| DIST | n_UC | R2_log | vies_log |
|---|---|---|---|
| 2866 | 3.217,0000 | 0,2423 | -0,0603 |
| 405 | 1.359,0000 | 0,2999 | 0,0632 |
| 47 | 2.714,0000 | 0,3333 | 0,0688 |
| 43 | 1.672,0000 | 0,3780 | 0,2978 |
| 396 | 2.405,0000 | 0,3948 | 0,0253 |
| 63 | 2.487,0000 | 0,4948 | 0,0432 |
| 385 | 1.069,0000 | 0,5134 | -0,3942 |
| 5697 | 1.279,0000 | 0,7244 | 0,4623 |
| 4950 | 2.306,0000 | 0,8398 | 0,0164 |
| 390 | 1.042,0000 | 0,8487 | -0,3519 |

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
