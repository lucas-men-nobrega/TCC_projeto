# Comparação de algoritmos de ML — BDGD/ANEEL

- Amostra estratificada por GRU_TEN: **121.884** UCs (pesos restauram a população)
- Validação: **Spatial Block CV** — 5 folds, blocos = 50 clusters K-means
- Índice de expansão: DAT_CON (conexões recentes até 2025 e crescimento entre janelas)

## Tarefa 1 — consumo anual de uma nova UC (log1p kWh)
| modelo | familia | RMSE_log_media | RMSE_log_dp | R2_log_media | MdAPE_pct_media |
|---|---|---|---|---|---|
| Random Forest padrão (lat/lon) + geração | Random Forest | 1,7127 | 0,0639 | 0,2425 | 77,4663 |
| Random Forest padrão (lat/lon) | Random Forest | 1,7369 | 0,0627 | 0,2202 | 78,4296 |
| Random Forest espacial (RF-sp) | Random Forest | 1,8047 | 0,0770 | 0,1567 | 79,6886 |
| CatBoost (feat. espaciais) + geração | Gradient Boosting | 1,8086 | 0,1107 | 0,1543 | 79,0536 |
| CatBoost (feat. espaciais) | Gradient Boosting | 1,8241 | 0,0891 | 0,1371 | 78,9980 |
| LightGBM (feat. espaciais) + geração | Gradient Boosting | 1,8505 | 0,1335 | 0,1112 | 78,8582 |
| Krigagem com regressão (GP) | Processo Gaussiano | 1,8641 | 0,0969 | 0,1026 | 80,7850 |
| LightGBM (feat. espaciais) | Gradient Boosting | 1,8706 | 0,1203 | 0,0911 | 79,2405 |
| XGBoost (feat. espaciais) | Gradient Boosting | 1,9956 | 0,1535 | -0,0287 | 82,4053 |
| Baseline · kNN espacial | Linha de base | 2,1431 | 0,2188 | -0,2067 | 96,9228 |
| GWR (mgwr) | Estatístico espacial | 2,6564 | 0,8900 | -1,0910 | 87,5233 |

**Melhor modelo:** Random Forest padrão (lat/lon) + geração

## Tarefa 2 — distribuição de GRU_TEN por região
| modelo | familia | LogLoss_media | F1_macro_media | TVD_regional_media |
|---|---|---|---|---|
| GP classificador (RBF) | Processo Gaussiano | 0,2022 | 0,2190 | 0,0860 |
| CatBoost (feat. espaciais) + geração | Gradient Boosting | 0,2111 | 0,2210 | 0,0845 |
| CatBoost (feat. espaciais) | Gradient Boosting | 0,2159 | 0,2193 | 0,0884 |
| LightGBM (feat. espaciais) | Gradient Boosting | 0,2246 | 0,2446 | 0,0928 |
| LightGBM (feat. espaciais) + geração | Gradient Boosting | 0,2620 | 0,2748 | 0,1015 |
| Random Forest padrão (lat/lon) | Random Forest | 0,2793 | 0,2739 | 0,1430 |
| Random Forest padrão (lat/lon) + geração | Random Forest | 0,3030 | 0,2873 | 0,1701 |
| Random Forest espacial (RF-sp) | Random Forest | 0,3440 | 0,3051 | 0,1736 |
| Baseline · kNN espacial | Linha de base | 0,7768 | 0,2423 | 0,1083 |
| XGBoost (feat. espaciais) | Gradient Boosting | 0,7830 | 0,3533 | 0,2763 |

**Melhor modelo:** GP classificador (RBF)

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
| Duque de Caxias | 33 | 5586 | 1.830.006.631,2539 | Polo consolidado |
| Jundiaí | 35 | 14271 | 1.799.937.786,1910 | Polo consolidado em expansão |
| Fortaleza | 23 | 64058 | 1.796.355.297,1600 | Polo consolidado em expansão |
| Campinas | 35 | 41650 | 1.795.013.786,5280 | Polo consolidado em expansão |
| São Bernardo do Campo | 35 | 18161 | 1.671.649.171,7400 | Polo consolidado |

## Top 15 municípios — maior índice de expansão
| NOME_MUNICIPIO | UF | N_UC | INDICE_EXPANSAO | QUADRANTE |
|---|---|---|---|---|
| Miguel Alves | 22 | 959 | 0,9966 | Fronteira de expansão |
| Oiapoque | 16 | 933 | 0,9965 | Fronteira de expansão |
| Colônia do Piauí | 22 | 596 | 0,9964 | Fronteira de expansão |
| Alto Longá | 22 | 503 | 0,9962 | Fronteira de expansão |
| Ipiranga do Piauí | 22 | 489 | 0,9962 | Fronteira de expansão |
| Capitão de Campos | 22 | 476 | 0,9961 | Fronteira de expansão |
| Cumaru do Norte | 15 | 447 | 0,9955 | Fronteira de expansão |
| Nazária | 22 | 438 | 0,9952 | Fronteira de expansão |
| Isaías Coelho | 22 | 389 | 0,9950 | Fronteira de expansão |
| Brasileira | 22 | 384 | 0,9949 | Fronteira de expansão |
| Novo Oriente do Piauí | 22 | 378 | 0,9949 | Fronteira de expansão |
| Barro Duro | 22 | 369 | 0,9948 | Fronteira de expansão |
| Acauã | 22 | 339 | 0,9946 | Fronteira de expansão |
| Dom Inocêncio | 22 | 336 | 0,9945 | Fronteira de expansão |
| Afuá | 15 | 307 | 0,9942 | Fronteira de expansão |

## Ablação — variáveis de geração (usinas liberadas, ANEEL/SIGA)
Mesmos folds para o modelo com e sem as variáveis `GER_*`. Delta = com geração − sem geração; `folds_melhor` conta os folds em que a geração ajudou.

| tarefa | modelo_base | metrica | base_media | com_geracao_media | delta_media | folds_melhor | n_folds |
|---|---|---|---|---|---|---|---|
| 1 · consumo | LightGBM (feat. espaciais) | RMSE_log | 1,8706 | 1,8505 | -0,0201 | 3 | 5 |
| 1 · consumo | LightGBM (feat. espaciais) | R2_log | 0,0911 | 0,1112 | 0,0200 | 3 | 5 |
| 1 · consumo | LightGBM (feat. espaciais) | MdAPE_pct | 79,2405 | 78,8582 | -0,3823 | 4 | 5 |
| 1 · consumo | LightGBM (feat. espaciais) | R2_log_AT | -0,2472 | -0,2066 | 0,0406 | 4 | 5 |
| 1 · consumo | LightGBM (feat. espaciais) | R2_log_BT | -0,1535 | -0,1277 | 0,0258 | 3 | 5 |
| 1 · consumo | LightGBM (feat. espaciais) | R2_log_MT | 0,0419 | 0,0508 | 0,0089 | 2 | 5 |
| 1 · consumo | CatBoost (feat. espaciais) | RMSE_log | 1,8241 | 1,8086 | -0,0155 | 3 | 5 |
| 1 · consumo | CatBoost (feat. espaciais) | R2_log | 0,1371 | 0,1543 | 0,0173 | 3 | 5 |
| 1 · consumo | CatBoost (feat. espaciais) | MdAPE_pct | 78,9980 | 79,0536 | 0,0556 | 2 | 5 |
| 1 · consumo | CatBoost (feat. espaciais) | R2_log_AT | -0,4081 | -0,4791 | -0,0710 | 1 | 5 |
| 1 · consumo | CatBoost (feat. espaciais) | R2_log_BT | -0,0875 | -0,0647 | 0,0228 | 3 | 5 |
| 1 · consumo | CatBoost (feat. espaciais) | R2_log_MT | 0,0064 | 0,0068 | 0,0004 | 2 | 5 |
| 1 · consumo | Random Forest padrão (lat/lon) | RMSE_log | 1,7369 | 1,7127 | -0,0241 | 3 | 5 |
| 1 · consumo | Random Forest padrão (lat/lon) | R2_log | 0,2202 | 0,2425 | 0,0222 | 3 | 5 |
| 1 · consumo | Random Forest padrão (lat/lon) | MdAPE_pct | 78,4296 | 77,4663 | -0,9633 | 5 | 5 |
| 1 · consumo | Random Forest padrão (lat/lon) | R2_log_AT | -0,0605 | -0,1010 | -0,0405 | 4 | 5 |
| 1 · consumo | Random Forest padrão (lat/lon) | R2_log_BT | 0,0138 | 0,0448 | 0,0310 | 3 | 5 |
| 1 · consumo | Random Forest padrão (lat/lon) | R2_log_MT | 0,1130 | 0,1131 | 0,0001 | 2 | 5 |
| 2 · GRU_TEN | LightGBM (feat. espaciais) | LogLoss | 0,2246 | 0,2620 | 0,0374 | 2 | 5 |
| 2 · GRU_TEN | LightGBM (feat. espaciais) | TVD_regional | 0,0928 | 0,1015 | 0,0088 | 0 | 5 |
| 2 · GRU_TEN | LightGBM (feat. espaciais) | F1_macro | 0,2446 | 0,2748 | 0,0302 | 5 | 5 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) | LogLoss | 0,2159 | 0,2111 | -0,0048 | 4 | 5 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) | TVD_regional | 0,0884 | 0,0845 | -0,0039 | 5 | 5 |
| 2 · GRU_TEN | CatBoost (feat. espaciais) | F1_macro | 0,2193 | 0,2210 | 0,0017 | 4 | 5 |
| 2 · GRU_TEN | Random Forest padrão (lat/lon) | LogLoss | 0,2793 | 0,3030 | 0,0237 | 1 | 5 |
| 2 · GRU_TEN | Random Forest padrão (lat/lon) | TVD_regional | 0,1430 | 0,1701 | 0,0270 | 1 | 5 |
| 2 · GRU_TEN | Random Forest padrão (lat/lon) | F1_macro | 0,2739 | 0,2873 | 0,0133 | 4 | 5 |