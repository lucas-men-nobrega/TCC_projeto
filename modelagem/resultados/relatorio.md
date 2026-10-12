# Comparação de algoritmos de ML — BDGD/ANEEL

- Amostra estratificada por GRU_TEN: **31.926** UCs (pesos restauram a população)
- Validação: **Spatial Block CV** — 3 folds, blocos = 30 clusters K-means
- Índice de expansão: PROXY — tendência linear do consumo mensal ENE_01→ENE_12 (DAT_CON ausente; sujeito à sazonalidade)

## Tarefa 1 — consumo anual de uma nova UC (log1p kWh)
| modelo | familia | RMSE_log_media | RMSE_log_dp | R2_log_media | MdAPE_pct_media |
|---|---|---|---|---|---|
| CatBoost (feat. espaciais) | Gradient Boosting | 1,8379 | 0,1232 | 0,1169 | 82,6101 |
| Random Forest padrão (lat/lon) | Random Forest | 1,8505 | 0,2315 | 0,1004 | 82,1550 |
| XGBoost (feat. espaciais) | Gradient Boosting | 1,8637 | 0,1463 | 0,0913 | 83,5423 |
| Random Forest espacial (RF-sp) | Random Forest | 1,8651 | 0,1722 | 0,0889 | 83,9237 |
| LightGBM (feat. espaciais) | Gradient Boosting | 1,8940 | 0,1634 | 0,0614 | 82,5243 |
| Krigagem com regressão (GP) | Processo Gaussiano | 1,9253 | 0,1341 | 0,0298 | 83,7439 |
| Baseline · kNN espacial | Linha de base | 2,1396 | 0,2810 | -0,2023 | 97,1639 |

**Melhor modelo:** CatBoost (feat. espaciais)

## Tarefa 2 — distribuição de GRU_TEN por região
| modelo | familia | LogLoss_media | F1_macro_media | TVD_regional_media |
|---|---|---|---|---|
| CatBoost (feat. espaciais) | Gradient Boosting | 0,1990 | 0,2244 | 0,0790 |
| GP classificador (RBF) | Processo Gaussiano | 0,1998 | 0,2148 | 0,0862 |
| LightGBM (feat. espaciais) | Gradient Boosting | 0,2129 | 0,2600 | 0,0933 |
| Random Forest padrão (lat/lon) | Random Forest | 0,3089 | 0,2760 | 0,1638 |
| Baseline · kNN espacial | Linha de base | 0,3131 | 0,2495 | 0,0919 |
| Random Forest espacial (RF-sp) | Random Forest | 0,4093 | 0,3252 | 0,2507 |
| XGBoost (feat. espaciais) | Gradient Boosting | 0,8022 | 0,3489 | 0,3313 |

**Melhor modelo:** CatBoost (feat. espaciais)

## Top 15 municípios — maior consumo anual
| NOME_MUNICIPIO | UF | N_UC | ENE_TOTAL_kWh | QUADRANTE |
|---|---|---|---|---|
| São Paulo | 35 | 336986 | 7.601.180.129,9400 | Polo consolidado |
| Rio de Janeiro | 33 | 4198 | 4.293.473.841,5409 | Polo consolidado |
| Curitiba | 41 | 115766 | 2.679.484.311,0000 | Polo consolidado em expansão |
| Manaus | 13 | 52504 | 2.353.570.920,8500 | Polo consolidado |
| Brasília | 53 | 133915 | 2.150.525.927,2460 | Polo consolidado |
| Guarulhos | 35 | 38223 | 1.845.740.947,6611 | Polo consolidado |
| Salvador | 29 | 82774 | 1.655.507.606,3800 | Polo consolidado |
| Fortaleza | 23 | 64058 | 1.448.625.955,9300 | Polo consolidado |
| Campinas | 35 | 41650 | 1.379.449.597,6950 | Polo consolidado |
| Recife | 26 | 54805 | 1.286.796.772,7095 | Polo consolidado |
| Belo Horizonte | 31 | 140308 | 1.236.987.982,1665 | Polo consolidado |
| Jundiaí | 35 | 14271 | 1.137.166.144,3610 | Polo consolidado |
| Sorocaba | 35 | 19015 | 1.113.817.267,5880 | Polo consolidado |
| Ribeirão Preto | 35 | 27255 | 1.077.658.638,6760 | Polo consolidado |
| Goiânia | 52 | 2403 | 1.053.021.463,6600 | Polo consolidado |

## Top 15 municípios — maior índice de expansão
| NOME_MUNICIPIO | UF | N_UC | INDICE_EXPANSAO | QUADRANTE |
|---|---|---|---|---|
| Ipaumirim | 23 | 1114 | 1,0000 | Fronteira de expansão |
| Nova Guataporanga | 35 | 183 | 0,9998 | Fronteira de expansão |
| Estrela do Norte | 35 | 228 | 0,9996 | Fronteira de expansão |
| Mulungu | 23 | 835 | 0,9994 | Fronteira de expansão |
| Dom Inocêncio | 22 | 336 | 0,9993 | Fronteira de expansão |
| Anhumas | 35 | 445 | 0,9991 | Fronteira de expansão |
| Júlio Borges | 22 | 215 | 0,9989 | Fronteira de expansão |
| Marmelópolis | 31 | 327 | 0,9987 | Fronteira de expansão |
| Planalto | 35 | 284 | 0,9985 | Fronteira de expansão |
| Riacho Frio | 22 | 94 | 0,9983 | Fronteira de expansão |
| Guarani d'Oeste | 35 | 199 | 0,9981 | Fronteira de expansão |
| Gastão Vidigal | 35 | 330 | 0,9980 | Fronteira de expansão |
| Irapuru | 35 | 597 | 0,9978 | Fronteira de expansão |
| Cachoeira Grande | 21 | 118 | 0,9976 | Fronteira de expansão |
| Funilândia | 31 | 495 | 0,9974 | Fronteira de expansão |