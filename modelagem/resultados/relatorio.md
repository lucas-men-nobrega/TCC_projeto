# Comparação de algoritmos de ML — BDGD/ANEEL

- Amostra estratificada por GRU_TEN: **121.884** UCs (pesos restauram a população)
- Validação: **Spatial Block CV** — 5 folds, blocos = 50 clusters K-means
- Índice de expansão: DAT_CON (conexões recentes até 2026 e crescimento entre janelas)

## Tarefa 1 — consumo anual de uma nova UC (log1p kWh)
| modelo | familia | RMSE_log_media | RMSE_log_dp | R2_log_media | MdAPE_pct_media |
|---|---|---|---|---|---|
| Random Forest padrão (lat/lon) | Random Forest | 1,7533 | 0,0603 | 0,2030 | 77,8329 |
| CatBoost (feat. espaciais) | Gradient Boosting | 1,8227 | 0,1468 | 0,1424 | 79,3113 |
| Random Forest espacial (RF-sp) | Random Forest | 1,8235 | 0,1253 | 0,1415 | 80,2375 |
| LightGBM (feat. espaciais) | Gradient Boosting | 1,8295 | 0,1553 | 0,1379 | 78,1760 |
| Krigagem com regressão (GP) | Processo Gaussiano | 1,8936 | 0,0972 | 0,0603 | 81,2732 |
| XGBoost (feat. espaciais) | Gradient Boosting | 1,9218 | 0,1834 | 0,0469 | 81,8989 |
| Baseline · kNN espacial | Linha de base | 2,0412 | 0,1675 | -0,0719 | 96,6207 |
| GWR (mgwr) | Estatístico espacial | 2,1750 | 0,2264 | -0,2948 | 85,6758 |

**Melhor modelo:** Random Forest padrão (lat/lon)

## Tarefa 2 — distribuição de GRU_TEN por região
| modelo | familia | LogLoss_media | F1_macro_media | TVD_regional_media |
|---|---|---|---|---|
| CatBoost (feat. espaciais) | Gradient Boosting | 0,2063 | 0,2192 | 0,0856 |
| GP classificador (RBF) | Processo Gaussiano | 0,2065 | 0,2190 | 0,0915 |
| LightGBM (feat. espaciais) | Gradient Boosting | 0,2145 | 0,2447 | 0,0879 |
| Random Forest padrão (lat/lon) | Random Forest | 0,2690 | 0,2725 | 0,1355 |
| Baseline · kNN espacial | Linha de base | 0,3108 | 0,2288 | 0,0968 |
| Random Forest espacial (RF-sp) | Random Forest | 0,3682 | 0,3098 | 0,1806 |
| XGBoost (feat. espaciais) | Gradient Boosting | 0,6740 | 0,3588 | 0,2972 |

**Melhor modelo:** CatBoost (feat. espaciais)

## Top 15 municípios — maior consumo anual
| NOME_MUNICIPIO | UF | N_UC | ENE_TOTAL_kWh | QUADRANTE |
|---|---|---|---|---|
| São Paulo | 35 | 336986 | 9.265.110.860,6600 | Polo consolidado |
| Rio de Janeiro | 33 | 4198 | 6.217.443.113,6409 | Polo consolidado |
| Manaus | 13 | 52504 | 3.609.471.625,8500 | Polo consolidado |
| Curitiba | 41 | 115766 | 3.029.192.915,0000 | Polo consolidado |
| Brasília | 53 | 133915 | 2.574.541.940,4073 | Polo consolidado |
| Guarulhos | 35 | 38223 | 2.387.962.252,5336 | Polo consolidado |
| Volta Redonda | 33 | 194 | 2.200.255.938,4557 | Polo consolidado |
| Joinville | 42 | 32890 | 1.978.656.773,5256 | Polo consolidado |
| Salvador | 29 | 82774 | 1.959.143.990,2200 | Polo consolidado em expansão |
| Piracicaba | 35 | 14633 | 1.916.090.084,1550 | Polo consolidado em expansão |
| Duque de Caxias | 33 | 5586 | 1.830.006.631,2539 | Polo consolidado em expansão |
| Jundiaí | 35 | 14271 | 1.799.937.786,1910 | Polo consolidado em expansão |
| Fortaleza | 23 | 64058 | 1.796.355.297,1600 | Polo consolidado em expansão |
| Campinas | 35 | 41650 | 1.795.013.786,5280 | Polo consolidado em expansão |
| São Bernardo do Campo | 35 | 18161 | 1.671.649.171,7400 | Polo consolidado |

## Top 15 municípios — maior índice de expansão
| NOME_MUNICIPIO | UF | N_UC | INDICE_EXPANSAO | QUADRANTE |
|---|---|---|---|---|
| Alto Longá | 22 | 503 | 0,9976 | Fronteira de expansão |
| Capitão de Campos | 22 | 476 | 0,9975 | Fronteira de expansão |
| Isaías Coelho | 22 | 389 | 0,9970 | Fronteira de expansão |
| Brasileira | 22 | 384 | 0,9969 | Fronteira de expansão |
| Novo Oriente do Piauí | 22 | 378 | 0,9968 | Fronteira de expansão |
| Barro Duro | 22 | 369 | 0,9968 | Fronteira de expansão |
| Acauã | 22 | 339 | 0,9965 | Fronteira de expansão |
| Afuá | 15 | 307 | 0,9964 | Fronteira de expansão |
| São José do Piauí | 22 | 304 | 0,9963 | Fronteira de expansão |
| São João do Arraial | 22 | 289 | 0,9961 | Fronteira de expansão |
| São Francisco de Assis do Piauí | 22 | 287 | 0,9960 | Fronteira de expansão |
| Murici dos Portelas | 22 | 285 | 0,9959 | Fronteira de expansão |
| Massapê do Piauí | 22 | 277 | 0,9957 | Fronteira de expansão |
| Lagoa do Sítio | 22 | 269 | 0,9956 | Fronteira de expansão |
| São Julião | 22 | 269 | 0,9956 | Fronteira de expansão |