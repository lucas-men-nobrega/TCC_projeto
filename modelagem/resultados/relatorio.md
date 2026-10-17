# Comparação de algoritmos de ML — BDGD/ANEEL

- Amostra estratificada por GRU_TEN: **121.884** UCs (pesos restauram a população)
- Validação: **Spatial Block CV** — 5 folds × 3 repetições, blocos = 50 clusters K-means
- Índice de expansão: DAT_CON (conexões recentes até 2025 e crescimento entre janelas)

## Tarefa 1 — consumo anual de uma nova UC (log1p kWh)
| modelo | familia | RMSE_log_media | RMSE_log_dp | R2_log_media | MdAPE_pct_media |
|---|---|---|---|---|---|
| Random Forest padrão (lat/lon) + todos | Random Forest | 1,2671 | 0,0511 | 0,5756 | 54,0155 |
| CatBoost (feat. espaciais) + todos | Gradient Boosting | 1,2902 | 0,0505 | 0,5599 | 60,0720 |
| LightGBM (feat. espaciais) + todos | Gradient Boosting | 1,2921 | 0,0556 | 0,5582 | 59,5791 |
| Random Forest padrão (lat/lon) + perfil | Random Forest | 1,3730 | 0,0668 | 0,5033 | 55,7404 |
| CatBoost (feat. espaciais) + perfil | Gradient Boosting | 1,4496 | 0,0937 | 0,4468 | 64,1031 |
| LightGBM (feat. espaciais) + perfil | Gradient Boosting | 1,4702 | 0,1150 | 0,4310 | 63,6505 |
| Random Forest padrão (lat/lon) + rede | Random Forest | 1,6012 | 0,0681 | 0,3269 | 75,4631 |
| LightGBM (feat. espaciais) + rede | Gradient Boosting | 1,6168 | 0,0768 | 0,3138 | 75,3714 |
| CatBoost (feat. espaciais) + rede | Gradient Boosting | 1,6410 | 0,0857 | 0,2928 | 75,9514 |
| Random Forest padrão (lat/lon) + geração | Random Forest | 1,7476 | 0,1175 | 0,1993 | 77,6266 |
| Random Forest padrão (lat/lon) + IBGE | Random Forest | 1,7579 | 0,1127 | 0,1892 | 77,4704 |
| Random Forest padrão (lat/lon) | Random Forest | 1,7941 | 0,1542 | 0,1538 | 78,5838 |
| CatBoost (feat. espaciais) + IBGE | Gradient Boosting | 1,8308 | 0,1514 | 0,1177 | 78,3089 |
| LightGBM (feat. espaciais) + IBGE | Gradient Boosting | 1,8392 | 0,1553 | 0,1082 | 78,1221 |
| CatBoost (feat. espaciais) + geração | Gradient Boosting | 1,8574 | 0,1770 | 0,0927 | 78,9930 |
| LightGBM (feat. espaciais) + geração | Gradient Boosting | 1,8676 | 0,1690 | 0,0846 | 78,5570 |
| Random Forest espacial (RF-sp) | Random Forest | 1,8777 | 0,1785 | 0,0728 | 80,3151 |
| CatBoost (feat. espaciais) | Gradient Boosting | 1,8788 | 0,1896 | 0,0732 | 79,4893 |
| LightGBM (feat. espaciais) | Gradient Boosting | 1,9062 | 0,2297 | 0,0447 | 78,9840 |
| Krigagem com regressão (GP) | Processo Gaussiano | 1,9445 | 0,1458 | 0,0058 | 82,1241 |
| XGBoost (feat. espaciais) | Gradient Boosting | 2,0443 | 0,3057 | -0,1027 | 82,9596 |
| Baseline · kNN espacial | Linha de base | 2,1261 | 0,1788 | -0,1813 | 96,9169 |
| GWR (mgwr) | Estatístico espacial | 2,4116 | 0,4103 | -0,4854 | 89,9807 |

**Melhor modelo:** Random Forest padrão (lat/lon) + todos · previsões regionais (nova UC sem perfil nem conjunto/alimentador): **Random Forest padrão (lat/lon) + geração** · alvo anualizado (UCs ligadas no ano da data-base)

## Tarefa 2 — distribuição de GRU_TEN por região
| modelo | familia | LogLoss_media | F1_macro_media | TVD_regional_media | AUC_PR_AT_media | Prevalencia_AT_media | AUC_PR_MT_media | Prevalencia_MT_media |
|---|---|---|---|---|---|---|---|---|
| CatBoost (feat. espaciais) + todos | Gradient Boosting | 0,1936 | 0,2270 | 0,0703 | 0,0033 | 0,0003 | 0,1296 | 0,0505 |
| CatBoost (feat. espaciais) + rede | Gradient Boosting | 0,1987 | 0,2245 | 0,0751 | 0,0010 | 0,0003 | 0,1159 | 0,0505 |
| GP classificador (RBF) | Processo Gaussiano | 0,2026 | 0,2189 | 0,0854 | 0,0006 | 0,0003 | 0,0676 | 0,0505 |
| CatBoost (feat. espaciais) + IBGE | Gradient Boosting | 0,2047 | 0,2299 | 0,0815 | 0,0010 | 0,0003 | 0,1084 | 0,0505 |
| CatBoost (feat. espaciais) + geração | Gradient Boosting | 0,2049 | 0,2262 | 0,0813 | 0,0035 | 0,0003 | 0,1010 | 0,0505 |
| CatBoost (feat. espaciais) | Gradient Boosting | 0,2083 | 0,2215 | 0,0834 | 0,0007 | 0,0003 | 0,0949 | 0,0505 |
| LightGBM (feat. espaciais) + rede | Gradient Boosting | 0,2115 | 0,2407 | 0,0802 | 0,0010 | 0,0003 | 0,1080 | 0,0505 |
| LightGBM (feat. espaciais) | Gradient Boosting | 0,2172 | 0,2384 | 0,0897 | 0,0009 | 0,0003 | 0,0922 | 0,0505 |
| LightGBM (feat. espaciais) + todos | Gradient Boosting | 0,2244 | 0,2894 | 0,0871 | 0,0055 | 0,0003 | 0,1202 | 0,0505 |
| LightGBM (feat. espaciais) + geração | Gradient Boosting | 0,2288 | 0,2748 | 0,0954 | 0,0102 | 0,0003 | 0,0959 | 0,0505 |
| Random Forest padrão (lat/lon) + rede | Random Forest | 0,2625 | 0,3137 | 0,1414 | 0,0022 | 0,0003 | 0,1283 | 0,0505 |
| LightGBM (feat. espaciais) + IBGE | Gradient Boosting | 0,2684 | 0,2717 | 0,1032 | 0,0008 | 0,0003 | 0,1114 | 0,0505 |
| Random Forest padrão (lat/lon) | Random Forest | 0,2843 | 0,2888 | 0,1575 | 0,0019 | 0,0003 | 0,0902 | 0,0505 |
| Random Forest padrão (lat/lon) + todos | Random Forest | 0,3160 | 0,3441 | 0,1969 | 0,0128 | 0,0003 | 0,1510 | 0,0505 |
| Random Forest padrão (lat/lon) + geração | Random Forest | 0,3181 | 0,2967 | 0,1772 | 0,0087 | 0,0003 | 0,1070 | 0,0505 |
| Random Forest padrão (lat/lon) + IBGE | Random Forest | 0,3670 | 0,3439 | 0,2017 | 0,0011 | 0,0003 | 0,1314 | 0,0505 |
| Random Forest espacial (RF-sp) | Random Forest | 0,3891 | 0,3190 | 0,2030 | 0,0015 | 0,0003 | 0,0805 | 0,0505 |
| Baseline · kNN espacial | Linha de base | 0,4774 | 0,2425 | 0,0993 | 0,0006 | 0,0003 | 0,0907 | 0,0505 |
| XGBoost (feat. espaciais) | Gradient Boosting | 0,9783 | 0,3613 | 0,3329 | 0,0010 | 0,0003 | 0,0791 | 0,0505 |

**Melhor modelo:** CatBoost (feat. espaciais) + todos · previsões regionais: **GP classificador (RBF)**

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

## Ablação por grupo de variáveis
Mesmos folds para o modelo com e sem o grupo (`ger` = variáveis `GER_*` das usinas, ANEEL/SIGA). Delta = com − sem; `folds_melhor` conta os folds em que o grupo ajudou. `p_t_corrigido`: t pareado com a correção de Nadeau-Bengio para folds de CV (que compartilham treino); `p_wilcoxon`: postos sinalizados (com 5 folds, o menor p bilateral possível é 0,0625 — use `--repeticoes`).

| tarefa | grupo | modelo_base | metrica | base_media | com_grupo_media | delta_media | ic95_inf | ic95_sup | folds_melhor | n_folds | p_t_corrigido | p_wilcoxon |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 · consumo | ger | LightGBM (feat. espaciais) | RMSE_log | 1,9062 | 1,8676 | -0,0386 | -0,1679 | 0,0906 | 10 | 15 | 0,5318 | 0,2078 |
| 1 · consumo | ger | LightGBM (feat. espaciais) | R2_log | 0,0447 | 0,0846 | 0,0398 | -0,0992 | 0,1788 | 10 | 15 | 0,5487 | 0,1688 |
| 1 · consumo | ger | LightGBM (feat. espaciais) | MdAPE_pct | 78,9840 | 78,5570 | -0,4270 | -1,6876 | 0,8336 | 9 | 15 | 0,4795 | 0,2078 |
| 1 · consumo | ger | LightGBM (feat. espaciais) | R2_log_AT | -0,2114 | -0,1510 | 0,0604 | -0,0354 | 0,1562 | 12 | 15 | 0,1978 | 0,0067 |
| 1 · consumo | ger | LightGBM (feat. espaciais) | R2_log_BT | -0,2202 | -0,1649 | 0,0553 | -0,1290 | 0,2395 | 10 | 15 | 0,5303 | 0,1514 |
| 1 · consumo | ger | LightGBM (feat. espaciais) | R2_log_MT | 0,0550 | 0,0640 | 0,0090 | -0,0337 | 0,0516 | 7 | 15 | 0,6598 | 1,0000 |
| 1 · consumo | ger | CatBoost (feat. espaciais) | RMSE_log | 1,8788 | 1,8574 | -0,0214 | -0,0778 | 0,0350 | 10 | 15 | 0,4296 | 0,0730 |
| 1 · consumo | ger | CatBoost (feat. espaciais) | R2_log | 0,0732 | 0,0927 | 0,0195 | -0,0375 | 0,0765 | 10 | 15 | 0,4755 | 0,1070 |
| 1 · consumo | ger | CatBoost (feat. espaciais) | MdAPE_pct | 79,4893 | 78,9930 | -0,4963 | -1,6865 | 0,6939 | 9 | 15 | 0,3863 | 0,0946 |
| 1 · consumo | ger | CatBoost (feat. espaciais) | R2_log_AT | -0,3784 | -0,4651 | -0,0867 | -0,3954 | 0,2220 | 7 | 15 | 0,5565 | 0,2769 |
| 1 · consumo | ger | CatBoost (feat. espaciais) | R2_log_BT | -0,1755 | -0,1482 | 0,0273 | -0,0479 | 0,1025 | 11 | 15 | 0,4497 | 0,0730 |
| 1 · consumo | ger | CatBoost (feat. espaciais) | R2_log_MT | -0,0075 | 0,0063 | 0,0138 | -0,0763 | 0,1039 | 8 | 15 | 0,7475 | 0,5614 |
| 1 · consumo | ger | Random Forest padrão (lat/lon) | RMSE_log | 1,7941 | 1,7476 | -0,0465 | -0,1373 | 0,0443 | 11 | 15 | 0,2905 | 0,0181 |
| 1 · consumo | ger | Random Forest padrão (lat/lon) | R2_log | 0,1538 | 0,1993 | 0,0455 | -0,0435 | 0,1345 | 11 | 15 | 0,2912 | 0,0256 |
| 1 · consumo | ger | Random Forest padrão (lat/lon) | MdAPE_pct | 78,5838 | 77,6266 | -0,9572 | -2,5043 | 0,5900 | 12 | 15 | 0,2058 | 0,0103 |
| 1 · consumo | ger | Random Forest padrão (lat/lon) | R2_log_AT | -0,0158 | -0,0584 | -0,0426 | -0,2305 | 0,1453 | 7 | 15 | 0,6342 | 0,3591 |
| 1 · consumo | ger | Random Forest padrão (lat/lon) | R2_log_BT | -0,0717 | -0,0126 | 0,0592 | -0,0648 | 0,1832 | 11 | 15 | 0,3233 | 0,0302 |
| 1 · consumo | ger | Random Forest padrão (lat/lon) | R2_log_MT | 0,0813 | 0,1021 | 0,0208 | -0,0404 | 0,0821 | 8 | 15 | 0,4775 | 0,2293 |
| 1 · consumo | ibge | LightGBM (feat. espaciais) | RMSE_log | 1,9062 | 1,8392 | -0,0670 | -0,2363 | 0,1023 | 11 | 15 | 0,4104 | 0,0946 |
| 1 · consumo | ibge | LightGBM (feat. espaciais) | R2_log | 0,0447 | 0,1082 | 0,0635 | -0,1083 | 0,2353 | 11 | 15 | 0,4413 | 0,1354 |
| 1 · consumo | ibge | LightGBM (feat. espaciais) | MdAPE_pct | 78,9840 | 78,1221 | -0,8619 | -2,4984 | 0,7747 | 10 | 15 | 0,2776 | 0,0479 |
| 1 · consumo | ibge | LightGBM (feat. espaciais) | R2_log_AT | -0,2114 | -0,1121 | 0,0993 | -0,0088 | 0,2075 | 14 | 15 | 0,0690 | 0,0004 |
| 1 · consumo | ibge | LightGBM (feat. espaciais) | R2_log_BT | -0,2202 | -0,1350 | 0,0852 | -0,1490 | 0,3194 | 10 | 15 | 0,4482 | 0,1514 |
| 1 · consumo | ibge | LightGBM (feat. espaciais) | R2_log_MT | 0,0550 | 0,1310 | 0,0760 | 0,0019 | 0,1501 | 14 | 15 | 0,0450 | 0,0001 |
| 1 · consumo | ibge | CatBoost (feat. espaciais) | RMSE_log | 1,8788 | 1,8308 | -0,0480 | -0,1307 | 0,0347 | 12 | 15 | 0,2334 | 0,0256 |
| 1 · consumo | ibge | CatBoost (feat. espaciais) | R2_log | 0,0732 | 0,1177 | 0,0445 | -0,0384 | 0,1275 | 12 | 15 | 0,2689 | 0,0554 |
| 1 · consumo | ibge | CatBoost (feat. espaciais) | MdAPE_pct | 79,4893 | 78,3089 | -1,1804 | -2,6556 | 0,2948 | 13 | 15 | 0,1082 | 0,0026 |
| 1 · consumo | ibge | CatBoost (feat. espaciais) | R2_log_AT | -0,3784 | -0,3167 | 0,0617 | -0,1717 | 0,2951 | 10 | 15 | 0,5795 | 0,2524 |
| 1 · consumo | ibge | CatBoost (feat. espaciais) | R2_log_BT | -0,1755 | -0,1185 | 0,0570 | -0,0563 | 0,1703 | 12 | 15 | 0,2987 | 0,0637 |
| 1 · consumo | ibge | CatBoost (feat. espaciais) | R2_log_MT | -0,0075 | 0,0761 | 0,0837 | 0,0133 | 0,1541 | 15 | 15 | 0,0232 | 0,0001 |
| 1 · consumo | ibge | Random Forest padrão (lat/lon) | RMSE_log | 1,7941 | 1,7579 | -0,0362 | -0,1197 | 0,0473 | 9 | 15 | 0,3680 | 0,0730 |
| 1 · consumo | ibge | Random Forest padrão (lat/lon) | R2_log | 0,1538 | 0,1892 | 0,0353 | -0,0458 | 0,1165 | 9 | 15 | 0,3663 | 0,0730 |
| 1 · consumo | ibge | Random Forest padrão (lat/lon) | MdAPE_pct | 78,5838 | 77,4704 | -1,1134 | -1,9497 | -0,2771 | 14 | 15 | 0,0127 | 0,0001 |
| 1 · consumo | ibge | Random Forest padrão (lat/lon) | R2_log_AT | -0,0158 | -0,0481 | -0,0322 | -0,3337 | 0,2692 | 7 | 15 | 0,8219 | 0,9341 |
| 1 · consumo | ibge | Random Forest padrão (lat/lon) | R2_log_BT | -0,0717 | -0,0304 | 0,0413 | -0,0708 | 0,1534 | 9 | 15 | 0,4427 | 0,1514 |
| 1 · consumo | ibge | Random Forest padrão (lat/lon) | R2_log_MT | 0,0813 | 0,1606 | 0,0794 | 0,0047 | 0,1540 | 14 | 15 | 0,0387 | 0,0001 |
| 1 · consumo | perfil | LightGBM (feat. espaciais) | RMSE_log | 1,9062 | 1,4702 | -0,4361 | -0,6010 | -0,2711 | 15 | 15 | 0,0001 | 0,0001 |
| 1 · consumo | perfil | LightGBM (feat. espaciais) | R2_log | 0,0447 | 0,4310 | 0,3862 | 0,2217 | 0,5508 | 15 | 15 | 0,0002 | 0,0001 |
| 1 · consumo | perfil | LightGBM (feat. espaciais) | MdAPE_pct | 78,9840 | 63,6505 | -15,3335 | -18,4549 | -12,2120 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | perfil | LightGBM (feat. espaciais) | R2_log_AT | -0,2114 | 0,0801 | 0,2915 | -0,0065 | 0,5896 | 13 | 15 | 0,0545 | 0,0009 |
| 1 · consumo | perfil | LightGBM (feat. espaciais) | R2_log_BT | -0,2202 | 0,2691 | 0,4892 | 0,2647 | 0,7137 | 15 | 15 | 0,0004 | 0,0001 |
| 1 · consumo | perfil | LightGBM (feat. espaciais) | R2_log_MT | 0,0550 | 0,5035 | 0,4485 | 0,3558 | 0,5411 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | perfil | CatBoost (feat. espaciais) | RMSE_log | 1,8788 | 1,4496 | -0,4292 | -0,5694 | -0,2891 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | perfil | CatBoost (feat. espaciais) | R2_log | 0,0732 | 0,4468 | 0,3737 | 0,2430 | 0,5044 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | perfil | CatBoost (feat. espaciais) | MdAPE_pct | 79,4893 | 64,1031 | -15,3862 | -18,3276 | -12,4447 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | perfil | CatBoost (feat. espaciais) | R2_log_AT | -0,3784 | 0,1983 | 0,5768 | 0,3418 | 0,8117 | 15 | 15 | 0,0001 | 0,0001 |
| 1 · consumo | perfil | CatBoost (feat. espaciais) | R2_log_BT | -0,1755 | 0,2927 | 0,4682 | 0,2892 | 0,6471 | 15 | 15 | 0,0001 | 0,0001 |
| 1 · consumo | perfil | CatBoost (feat. espaciais) | R2_log_MT | -0,0075 | 0,4912 | 0,4987 | 0,3638 | 0,6336 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | perfil | Random Forest padrão (lat/lon) | RMSE_log | 1,7941 | 1,3730 | -0,4210 | -0,5591 | -0,2830 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | perfil | Random Forest padrão (lat/lon) | R2_log | 0,1538 | 0,5033 | 0,3495 | 0,2229 | 0,4760 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | perfil | Random Forest padrão (lat/lon) | MdAPE_pct | 78,5838 | 55,7404 | -22,8434 | -27,1661 | -18,5207 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | perfil | Random Forest padrão (lat/lon) | R2_log_AT | -0,0158 | 0,3434 | 0,3592 | -0,0512 | 0,7697 | 13 | 15 | 0,0815 | 0,0043 |
| 1 · consumo | perfil | Random Forest padrão (lat/lon) | R2_log_BT | -0,0717 | 0,3611 | 0,4328 | 0,2618 | 0,6037 | 15 | 15 | 0,0001 | 0,0001 |
| 1 · consumo | perfil | Random Forest padrão (lat/lon) | R2_log_MT | 0,0813 | 0,5987 | 0,5174 | 0,4381 | 0,5968 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | rede | LightGBM (feat. espaciais) | RMSE_log | 1,9062 | 1,6168 | -0,2894 | -0,5007 | -0,0782 | 15 | 15 | 0,0108 | 0,0001 |
| 1 · consumo | rede | LightGBM (feat. espaciais) | R2_log | 0,0447 | 0,3138 | 0,2691 | 0,0634 | 0,4747 | 15 | 15 | 0,0140 | 0,0001 |
| 1 · consumo | rede | LightGBM (feat. espaciais) | MdAPE_pct | 78,9840 | 75,3714 | -3,6126 | -5,5002 | -1,7249 | 15 | 15 | 0,0011 | 0,0001 |
| 1 · consumo | rede | LightGBM (feat. espaciais) | R2_log_AT | -0,2114 | -0,1372 | 0,0743 | -0,0541 | 0,2027 | 10 | 15 | 0,2350 | 0,0256 |
| 1 · consumo | rede | LightGBM (feat. espaciais) | R2_log_BT | -0,2202 | 0,1404 | 0,3606 | 0,0729 | 0,6483 | 15 | 15 | 0,0177 | 0,0001 |
| 1 · consumo | rede | LightGBM (feat. espaciais) | R2_log_MT | 0,0550 | 0,1314 | 0,0764 | 0,0177 | 0,1350 | 15 | 15 | 0,0144 | 0,0001 |
| 1 · consumo | rede | CatBoost (feat. espaciais) | RMSE_log | 1,8788 | 1,6410 | -0,2379 | -0,3764 | -0,0993 | 15 | 15 | 0,0025 | 0,0001 |
| 1 · consumo | rede | CatBoost (feat. espaciais) | R2_log | 0,0732 | 0,2928 | 0,2196 | 0,0860 | 0,3533 | 15 | 15 | 0,0034 | 0,0001 |
| 1 · consumo | rede | CatBoost (feat. espaciais) | MdAPE_pct | 79,4893 | 75,9514 | -3,5379 | -5,4497 | -1,6260 | 15 | 15 | 0,0014 | 0,0001 |
| 1 · consumo | rede | CatBoost (feat. espaciais) | R2_log_AT | -0,3784 | -0,3172 | 0,0613 | -0,1888 | 0,3113 | 8 | 15 | 0,6073 | 0,2293 |
| 1 · consumo | rede | CatBoost (feat. espaciais) | R2_log_BT | -0,1755 | 0,1164 | 0,2919 | 0,1026 | 0,4813 | 15 | 15 | 0,0052 | 0,0001 |
| 1 · consumo | rede | CatBoost (feat. espaciais) | R2_log_MT | -0,0075 | 0,0783 | 0,0858 | -0,0159 | 0,1875 | 14 | 15 | 0,0918 | 0,0020 |
| 1 · consumo | rede | Random Forest padrão (lat/lon) | RMSE_log | 1,7941 | 1,6012 | -0,1928 | -0,3270 | -0,0587 | 15 | 15 | 0,0081 | 0,0001 |
| 1 · consumo | rede | Random Forest padrão (lat/lon) | R2_log | 0,1538 | 0,3269 | 0,1730 | 0,0456 | 0,3004 | 15 | 15 | 0,0113 | 0,0001 |
| 1 · consumo | rede | Random Forest padrão (lat/lon) | MdAPE_pct | 78,5838 | 75,4631 | -3,1207 | -4,6176 | -1,6238 | 15 | 15 | 0,0005 | 0,0001 |
| 1 · consumo | rede | Random Forest padrão (lat/lon) | R2_log_AT | -0,0158 | -0,0086 | 0,0072 | -0,0711 | 0,0855 | 9 | 15 | 0,8465 | 0,7197 |
| 1 · consumo | rede | Random Forest padrão (lat/lon) | R2_log_BT | -0,0717 | 0,1558 | 0,2275 | 0,0528 | 0,4022 | 15 | 15 | 0,0144 | 0,0001 |
| 1 · consumo | rede | Random Forest padrão (lat/lon) | R2_log_MT | 0,0813 | 0,1650 | 0,0838 | 0,0235 | 0,1440 | 15 | 15 | 0,0099 | 0,0001 |
| 1 · consumo | todos | LightGBM (feat. espaciais) | RMSE_log | 1,9062 | 1,2921 | -0,6141 | -0,8538 | -0,3744 | 15 | 15 | 0,0001 | 0,0001 |
| 1 · consumo | todos | LightGBM (feat. espaciais) | R2_log | 0,0447 | 0,5582 | 0,5135 | 0,2976 | 0,7293 | 15 | 15 | 0,0002 | 0,0001 |
| 1 · consumo | todos | LightGBM (feat. espaciais) | MdAPE_pct | 78,9840 | 59,5791 | -19,4048 | -23,6345 | -15,1752 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | LightGBM (feat. espaciais) | R2_log_AT | -0,2114 | 0,0883 | 0,2997 | -0,0106 | 0,6100 | 13 | 15 | 0,0573 | 0,0006 |
| 1 · consumo | todos | LightGBM (feat. espaciais) | R2_log_BT | -0,2202 | 0,4420 | 0,6621 | 0,3621 | 0,9622 | 15 | 15 | 0,0003 | 0,0001 |
| 1 · consumo | todos | LightGBM (feat. espaciais) | R2_log_MT | 0,0550 | 0,5156 | 0,4606 | 0,3457 | 0,5755 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | CatBoost (feat. espaciais) | RMSE_log | 1,8788 | 1,2902 | -0,5886 | -0,7841 | -0,3931 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | CatBoost (feat. espaciais) | R2_log | 0,0732 | 0,5599 | 0,4867 | 0,3193 | 0,6541 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | CatBoost (feat. espaciais) | MdAPE_pct | 79,4893 | 60,0720 | -19,4173 | -22,8461 | -15,9884 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | CatBoost (feat. espaciais) | R2_log_AT | -0,3784 | 0,1863 | 0,5647 | 0,3083 | 0,8211 | 15 | 15 | 0,0003 | 0,0001 |
| 1 · consumo | todos | CatBoost (feat. espaciais) | R2_log_BT | -0,1755 | 0,4439 | 0,6194 | 0,3908 | 0,8479 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | CatBoost (feat. espaciais) | R2_log_MT | -0,0075 | 0,5153 | 0,5229 | 0,3786 | 0,6671 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | Random Forest padrão (lat/lon) | RMSE_log | 1,7941 | 1,2671 | -0,5269 | -0,6902 | -0,3637 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | Random Forest padrão (lat/lon) | R2_log | 0,1538 | 0,5756 | 0,4217 | 0,2807 | 0,5627 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | Random Forest padrão (lat/lon) | MdAPE_pct | 78,5838 | 54,0155 | -24,5683 | -29,3543 | -19,7822 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | Random Forest padrão (lat/lon) | R2_log_AT | -0,0158 | 0,3077 | 0,3235 | -0,1180 | 0,7650 | 12 | 15 | 0,1384 | 0,0067 |
| 1 · consumo | todos | Random Forest padrão (lat/lon) | R2_log_BT | -0,0717 | 0,4602 | 0,5320 | 0,3424 | 0,7215 | 15 | 15 | 0,0000 | 0,0001 |
| 1 · consumo | todos | Random Forest padrão (lat/lon) | R2_log_MT | 0,0813 | 0,5817 | 0,5004 | 0,4070 | 0,5938 | 15 | 15 | 0,0000 | 0,0001 |
| 2 · GRU_TEN | ger | LightGBM (feat. espaciais) | LogLoss | 0,2172 | 0,2288 | 0,0117 | -0,0066 | 0,0299 | 3 | 15 | 0,1914 | 0,0012 |
| 2 · GRU_TEN | ger | LightGBM (feat. espaciais) | TVD_regional | 0,0897 | 0,0954 | 0,0057 | -0,0011 | 0,0125 | 3 | 15 | 0,0918 | 0,0012 |
| 2 · GRU_TEN | ger | LightGBM (feat. espaciais) | F1_macro | 0,2384 | 0,2748 | 0,0364 | 0,0092 | 0,0636 | 15 | 15 | 0,0124 | 0,0001 |
| 2 · GRU_TEN | ger | LightGBM (feat. espaciais) | AUC_PR_MT | 0,0922 | 0,0959 | 0,0037 | -0,0152 | 0,0227 | 8 | 15 | 0,6785 | 0,6788 |
| 2 · GRU_TEN | ger | LightGBM (feat. espaciais) | AUC_PR_AT | 0,0009 | 0,0102 | 0,0093 | -0,0018 | 0,0204 | 15 | 15 | 0,0942 | 0,0001 |
| 2 · GRU_TEN | ger | CatBoost (feat. espaciais) | LogLoss | 0,2083 | 0,2049 | -0,0034 | -0,0096 | 0,0028 | 13 | 15 | 0,2571 | 0,0125 |
| 2 · GRU_TEN | ger | CatBoost (feat. espaciais) | TVD_regional | 0,0834 | 0,0813 | -0,0020 | -0,0070 | 0,0029 | 11 | 15 | 0,3932 | 0,0125 |
| 2 · GRU_TEN | ger | CatBoost (feat. espaciais) | F1_macro | 0,2215 | 0,2262 | 0,0047 | -0,0113 | 0,0207 | 8 | 15 | 0,5376 | 0,0464 |
| 2 · GRU_TEN | ger | CatBoost (feat. espaciais) | AUC_PR_MT | 0,0949 | 0,1010 | 0,0061 | -0,0070 | 0,0191 | 13 | 15 | 0,3355 | 0,0103 |
| 2 · GRU_TEN | ger | CatBoost (feat. espaciais) | AUC_PR_AT | 0,0007 | 0,0035 | 0,0028 | -0,0006 | 0,0062 | 15 | 15 | 0,1011 | 0,0001 |
| 2 · GRU_TEN | ger | Random Forest padrão (lat/lon) | LogLoss | 0,2843 | 0,3181 | 0,0338 | -0,0135 | 0,0811 | 3 | 15 | 0,1472 | 0,0067 |
| 2 · GRU_TEN | ger | Random Forest padrão (lat/lon) | TVD_regional | 0,1575 | 0,1772 | 0,0196 | -0,0168 | 0,0560 | 3 | 15 | 0,2669 | 0,0353 |
| 2 · GRU_TEN | ger | Random Forest padrão (lat/lon) | F1_macro | 0,2888 | 0,2967 | 0,0079 | -0,0262 | 0,0420 | 9 | 15 | 0,6258 | 0,2769 |
| 2 · GRU_TEN | ger | Random Forest padrão (lat/lon) | AUC_PR_MT | 0,0902 | 0,1070 | 0,0168 | -0,0037 | 0,0373 | 12 | 15 | 0,1009 | 0,0015 |
| 2 · GRU_TEN | ger | Random Forest padrão (lat/lon) | AUC_PR_AT | 0,0019 | 0,0087 | 0,0069 | 0,0016 | 0,0122 | 15 | 15 | 0,0150 | 0,0001 |
| 2 · GRU_TEN | ibge | LightGBM (feat. espaciais) | LogLoss | 0,2172 | 0,2684 | 0,0513 | -0,0359 | 0,1385 | 3 | 15 | 0,2279 | 0,0103 |
| 2 · GRU_TEN | ibge | LightGBM (feat. espaciais) | TVD_regional | 0,0897 | 0,1032 | 0,0135 | -0,0017 | 0,0288 | 2 | 15 | 0,0783 | 0,0003 |
| 2 · GRU_TEN | ibge | LightGBM (feat. espaciais) | F1_macro | 0,2384 | 0,2717 | 0,0333 | -0,0150 | 0,0815 | 14 | 15 | 0,1611 | 0,0020 |
| 2 · GRU_TEN | ibge | LightGBM (feat. espaciais) | AUC_PR_MT | 0,0922 | 0,1114 | 0,0193 | -0,0209 | 0,0595 | 11 | 15 | 0,3211 | 0,0730 |
| 2 · GRU_TEN | ibge | LightGBM (feat. espaciais) | AUC_PR_AT | 0,0009 | 0,0008 | -0,0001 | -0,0009 | 0,0008 | 9 | 15 | 0,8552 | 0,8904 |
| 2 · GRU_TEN | ibge | CatBoost (feat. espaciais) | LogLoss | 0,2083 | 0,2047 | -0,0036 | -0,0161 | 0,0089 | 12 | 15 | 0,5483 | 0,0946 |
| 2 · GRU_TEN | ibge | CatBoost (feat. espaciais) | TVD_regional | 0,0834 | 0,0815 | -0,0018 | -0,0055 | 0,0019 | 11 | 15 | 0,3107 | 0,0353 |
| 2 · GRU_TEN | ibge | CatBoost (feat. espaciais) | F1_macro | 0,2215 | 0,2299 | 0,0085 | -0,0124 | 0,0294 | 12 | 15 | 0,3985 | 0,0076 |
| 2 · GRU_TEN | ibge | CatBoost (feat. espaciais) | AUC_PR_MT | 0,0949 | 0,1084 | 0,0135 | -0,0012 | 0,0281 | 13 | 15 | 0,0682 | 0,0015 |
| 2 · GRU_TEN | ibge | CatBoost (feat. espaciais) | AUC_PR_AT | 0,0007 | 0,0010 | 0,0004 | -0,0002 | 0,0009 | 13 | 15 | 0,2037 | 0,0020 |
| 2 · GRU_TEN | ibge | Random Forest padrão (lat/lon) | LogLoss | 0,2843 | 0,3670 | 0,0827 | -0,0219 | 0,1873 | 3 | 15 | 0,1119 | 0,0015 |
| 2 · GRU_TEN | ibge | Random Forest padrão (lat/lon) | TVD_regional | 0,1575 | 0,2017 | 0,0441 | -0,0087 | 0,0969 | 4 | 15 | 0,0946 | 0,0054 |
| 2 · GRU_TEN | ibge | Random Forest padrão (lat/lon) | F1_macro | 0,2888 | 0,3439 | 0,0551 | 0,0035 | 0,1067 | 13 | 15 | 0,0381 | 0,0003 |
| 2 · GRU_TEN | ibge | Random Forest padrão (lat/lon) | AUC_PR_MT | 0,0902 | 0,1314 | 0,0411 | -0,0339 | 0,1162 | 12 | 15 | 0,2591 | 0,0215 |
| 2 · GRU_TEN | ibge | Random Forest padrão (lat/lon) | AUC_PR_AT | 0,0019 | 0,0011 | -0,0008 | -0,0049 | 0,0033 | 9 | 15 | 0,6978 | 0,4543 |
| 2 · GRU_TEN | rede | LightGBM (feat. espaciais) | LogLoss | 0,2172 | 0,2115 | -0,0057 | -0,0264 | 0,0150 | 12 | 15 | 0,5633 | 0,0833 |
| 2 · GRU_TEN | rede | LightGBM (feat. espaciais) | TVD_regional | 0,0897 | 0,0802 | -0,0095 | -0,0182 | -0,0009 | 15 | 15 | 0,0332 | 0,0001 |
| 2 · GRU_TEN | rede | LightGBM (feat. espaciais) | F1_macro | 0,2384 | 0,2407 | 0,0022 | -0,0181 | 0,0226 | 10 | 15 | 0,8172 | 0,3894 |
| 2 · GRU_TEN | rede | LightGBM (feat. espaciais) | AUC_PR_MT | 0,0922 | 0,1080 | 0,0158 | -0,0039 | 0,0355 | 14 | 15 | 0,1071 | 0,0004 |
| 2 · GRU_TEN | rede | LightGBM (feat. espaciais) | AUC_PR_AT | 0,0009 | 0,0010 | 0,0002 | -0,0016 | 0,0019 | 7 | 15 | 0,8576 | 0,9780 |
| 2 · GRU_TEN | rede | CatBoost (feat. espaciais) | LogLoss | 0,2083 | 0,1987 | -0,0096 | -0,0174 | -0,0018 | 15 | 15 | 0,0197 | 0,0001 |
| 2 · GRU_TEN | rede | CatBoost (feat. espaciais) | TVD_regional | 0,0834 | 0,0751 | -0,0083 | -0,0148 | -0,0018 | 15 | 15 | 0,0163 | 0,0001 |
| 2 · GRU_TEN | rede | CatBoost (feat. espaciais) | F1_macro | 0,2215 | 0,2245 | 0,0031 | -0,0074 | 0,0136 | 8 | 15 | 0,5431 | 0,1361 |
| 2 · GRU_TEN | rede | CatBoost (feat. espaciais) | AUC_PR_MT | 0,0949 | 0,1159 | 0,0210 | 0,0052 | 0,0367 | 15 | 15 | 0,0127 | 0,0001 |
| 2 · GRU_TEN | rede | CatBoost (feat. espaciais) | AUC_PR_AT | 0,0007 | 0,0010 | 0,0003 | -0,0003 | 0,0009 | 10 | 15 | 0,3200 | 0,0479 |
| 2 · GRU_TEN | rede | Random Forest padrão (lat/lon) | LogLoss | 0,2843 | 0,2625 | -0,0218 | -0,0629 | 0,0193 | 12 | 15 | 0,2744 | 0,0215 |
| 2 · GRU_TEN | rede | Random Forest padrão (lat/lon) | TVD_regional | 0,1575 | 0,1414 | -0,0161 | -0,0574 | 0,0252 | 10 | 15 | 0,4169 | 0,1688 |
| 2 · GRU_TEN | rede | Random Forest padrão (lat/lon) | F1_macro | 0,2888 | 0,3137 | 0,0249 | -0,0265 | 0,0762 | 12 | 15 | 0,3173 | 0,0413 |
| 2 · GRU_TEN | rede | Random Forest padrão (lat/lon) | AUC_PR_MT | 0,0902 | 0,1283 | 0,0380 | -0,0019 | 0,0780 | 15 | 15 | 0,0603 | 0,0001 |
| 2 · GRU_TEN | rede | Random Forest padrão (lat/lon) | AUC_PR_AT | 0,0019 | 0,0022 | 0,0003 | -0,0010 | 0,0017 | 10 | 15 | 0,6151 | 0,0833 |
| 2 · GRU_TEN | todos | LightGBM (feat. espaciais) | LogLoss | 0,2172 | 0,2244 | 0,0073 | -0,0116 | 0,0261 | 4 | 15 | 0,4211 | 0,0833 |
| 2 · GRU_TEN | todos | LightGBM (feat. espaciais) | TVD_regional | 0,0897 | 0,0871 | -0,0026 | -0,0236 | 0,0184 | 6 | 15 | 0,7940 | 0,7615 |
| 2 · GRU_TEN | todos | LightGBM (feat. espaciais) | F1_macro | 0,2384 | 0,2894 | 0,0509 | 0,0240 | 0,0779 | 15 | 15 | 0,0012 | 0,0001 |
| 2 · GRU_TEN | todos | LightGBM (feat. espaciais) | AUC_PR_MT | 0,0922 | 0,1202 | 0,0280 | -0,0042 | 0,0602 | 12 | 15 | 0,0835 | 0,0009 |
| 2 · GRU_TEN | todos | LightGBM (feat. espaciais) | AUC_PR_AT | 0,0009 | 0,0055 | 0,0046 | -0,0012 | 0,0105 | 15 | 15 | 0,1135 | 0,0001 |
| 2 · GRU_TEN | todos | CatBoost (feat. espaciais) | LogLoss | 0,2083 | 0,1936 | -0,0147 | -0,0248 | -0,0047 | 15 | 15 | 0,0070 | 0,0001 |
| 2 · GRU_TEN | todos | CatBoost (feat. espaciais) | TVD_regional | 0,0834 | 0,0703 | -0,0131 | -0,0228 | -0,0034 | 15 | 15 | 0,0117 | 0,0001 |
| 2 · GRU_TEN | todos | CatBoost (feat. espaciais) | F1_macro | 0,2215 | 0,2270 | 0,0055 | -0,0113 | 0,0223 | 12 | 15 | 0,4928 | 0,0258 |
| 2 · GRU_TEN | todos | CatBoost (feat. espaciais) | AUC_PR_MT | 0,0949 | 0,1296 | 0,0347 | 0,0128 | 0,0567 | 15 | 15 | 0,0044 | 0,0001 |
| 2 · GRU_TEN | todos | CatBoost (feat. espaciais) | AUC_PR_AT | 0,0007 | 0,0033 | 0,0026 | -0,0003 | 0,0055 | 15 | 15 | 0,0772 | 0,0001 |
| 2 · GRU_TEN | todos | Random Forest padrão (lat/lon) | LogLoss | 0,2843 | 0,3160 | 0,0317 | -0,0341 | 0,0975 | 7 | 15 | 0,3193 | 0,1070 |
| 2 · GRU_TEN | todos | Random Forest padrão (lat/lon) | TVD_regional | 0,1575 | 0,1969 | 0,0393 | -0,0118 | 0,0904 | 4 | 15 | 0,1210 | 0,0043 |
| 2 · GRU_TEN | todos | Random Forest padrão (lat/lon) | F1_macro | 0,2888 | 0,3441 | 0,0553 | -0,0037 | 0,1142 | 13 | 15 | 0,0640 | 0,0004 |
| 2 · GRU_TEN | todos | Random Forest padrão (lat/lon) | AUC_PR_MT | 0,0902 | 0,1510 | 0,0608 | -0,0002 | 0,1217 | 15 | 15 | 0,0506 | 0,0001 |
| 2 · GRU_TEN | todos | Random Forest padrão (lat/lon) | AUC_PR_AT | 0,0019 | 0,0128 | 0,0109 | -0,0003 | 0,0221 | 14 | 15 | 0,0553 | 0,0001 |