# Tarefa 3 — onde a geração centralizada se expande

- Unidade: município (5.570). Alvo: receber potência liberada para operação comercial nos 5 anos seguintes ao corte.
- Variáveis só com dados até o ano de corte: conexões BDGD por `DAT_CON`, estoque de geração, posição e, na variante "com IBGE 2010", o retrato socioeconômico de 2010 (Censo e PIB 2010 — o Censo 2022 e o PIB recente seriam informação do futuro).
- Validação temporal: treino com 1 corte (T=2015) ou 3 cortes empilhados (2011, 2013, 2015) → teste T=2020 (alvo 2021–2025). Validação espacial: 5 folds × 3 repetições em T=2020.
- Antes de 2014 a base de UGs não cobre toda a potência anual: cortes antigos têm alvo e estoque subestimados.
- Prevalência do alvo no teste: 5.4% dos municípios (= AUC-PR sem informação).

## Classificação — recebe nova geração?
| esquema | treino | variaveis | modelo | AUC_PR | AUC_ROC | LogLoss | Brier |
|---|---|---|---|---|---|---|---|
| temporal | 1 corte (2015) | com IBGE 2010 | Random Forest | 0,3366 | 0,8319 | 0,1655 | 0,0430 |
| temporal | 3 cortes (2011, 2013, 2015) | com IBGE 2010 | Regressão logística | 0,3273 | 0,8339 | 0,1647 | 0,0432 |
| temporal | 1 corte (2015) | sem IBGE | Random Forest | 0,3192 | 0,8213 | 0,1706 | 0,0439 |
| temporal | 3 cortes (2011, 2013, 2015) | com IBGE 2010 | LightGBM | 0,3179 | 0,8312 | 0,1702 | 0,0450 |
| temporal | 1 corte (2015) | com IBGE 2010 | Regressão logística | 0,3156 | 0,8204 | 0,1704 | 0,0445 |
| temporal | 3 cortes (2011, 2013, 2015) | com IBGE 2010 | Random Forest | 0,3142 | 0,8362 | 0,1662 | 0,0442 |
| temporal | 1 corte (2015) | com IBGE 2010 | LightGBM | 0,3107 | 0,8210 | 0,1883 | 0,0484 |
| temporal | 1 corte (2015) | com IBGE 2010 | CatBoost | 0,3055 | 0,8173 | 0,1827 | 0,0480 |
| temporal | 3 cortes (2011, 2013, 2015) | sem IBGE | Regressão logística | 0,3036 | 0,8165 | 0,1704 | 0,0445 |
| temporal | 3 cortes (2011, 2013, 2015) | com IBGE 2010 | CatBoost | 0,3027 | 0,8243 | 0,1760 | 0,0468 |
| temporal | 3 cortes (2011, 2013, 2015) | sem IBGE | LightGBM | 0,3017 | 0,8185 | 0,1712 | 0,0453 |
| temporal | 1 corte (2015) | sem IBGE | Regressão logística | 0,2952 | 0,8055 | 0,1745 | 0,0453 |
| temporal | 1 corte (2015) | sem IBGE | CatBoost | 0,2931 | 0,7986 | 0,1774 | 0,0459 |
| temporal | 3 cortes (2011, 2013, 2015) | sem IBGE | Random Forest | 0,2899 | 0,8251 | 0,1732 | 0,0452 |
| temporal | 3 cortes (2011, 2013, 2015) | sem IBGE | CatBoost | 0,2871 | 0,8180 | 0,1715 | 0,0454 |
| temporal | 1 corte (2015) | sem IBGE | LightGBM | 0,2848 | 0,8024 | 0,1831 | 0,0472 |
| temporal | 1 corte (2015) | sem IBGE | Baseline · kNN espacial | 0,1787 | 0,7523 | 0,2391 | 0,0480 |
| temporal | 3 cortes (2011, 2013, 2015) | sem IBGE | Baseline · kNN espacial | 0,1751 | 0,7283 | 0,2779 | 0,0486 |
| temporal | 1 corte (2015) | sem IBGE | Baseline · persistência | 0,1511 | 0,6492 | 0,1857 | 0,0462 |
| temporal | 3 cortes (2011, 2013, 2015) | sem IBGE | Baseline · persistência | 0,1511 | 0,6492 | 0,1861 | 0,0463 |

**Melhor (AUC-PR temporal):** Random Forest · 1 corte (2015) · com IBGE 2010

## Ablação do IBGE 2010 (validação espacial, mesmos folds; t corrigido de Nadeau-Bengio)
| modelo | metrica | sem_IBGE | com_IBGE | delta_media | folds_melhor | n_folds | p_t_corrigido | p_wilcoxon |
|---|---|---|---|---|---|---|---|---|
| Regressão logística | AUC_PR | 0,2816 | 0,3036 | 0,0220 | 11 | 15 | 0,2368 | 0,0181 |
| Regressão logística | LogLoss | 0,1754 | 0,1704 | -0,0050 | 11 | 15 | 0,2107 | 0,0151 |
| Random Forest | AUC_PR | 0,3023 | 0,3010 | -0,0013 | 6 | 15 | 0,9068 | 0,7615 |
| Random Forest | LogLoss | 0,1746 | 0,1706 | -0,0040 | 11 | 15 | 0,1955 | 0,0125 |
| LightGBM | AUC_PR | 0,2917 | 0,2999 | 0,0083 | 10 | 15 | 0,4756 | 0,2078 |
| LightGBM | LogLoss | 0,1908 | 0,1929 | 0,0021 | 7 | 15 | 0,6362 | 0,5614 |
| CatBoost | AUC_PR | 0,3013 | 0,3144 | 0,0131 | 10 | 15 | 0,5674 | 0,1688 |
| CatBoost | LogLoss | 0,1796 | 0,1752 | -0,0044 | 11 | 15 | 0,2900 | 0,0302 |

## Calibração (teste temporal)
| versao | AUC_PR | LogLoss | Brier |
|---|---|---|---|
| sem calibração | 0,3366 | 0,1655 | 0,0430 |
| calibrado (isotônica) | 0,3321 | 0,1680 | 0,0432 |
Curva: `tarefa3_confiabilidade.png`.

## Parte contínua — log1p(MW) nos municípios que receberam (validação temporal)
| modelo | RMSE_log | R2_log | n_treino | n_teste |
|---|---|---|---|---|
| Baseline · média | 1,6739 | -0,1112 | 290 | 299 |
| Ridge | 1,3169 | 0,3123 | 290 | 299 |
| Random Forest | 1,2819 | 0,3483 | 290 | 299 |
| LightGBM | 1,4341 | 0,1843 | 290 | 299 |

## Validação externa — usinas em obra no SIGA (sem UG liberada)
2.234 usinas · 95.877 MW · 324 municípios. A previsão 2026–2030 ordena esses municípios?
| score | AUC_PR | AUC_ROC | LogLoss | Brier | Prevalencia | Precisao_top50 | MW_obra_top50_pct | Precisao_top100 | MW_obra_top100_pct | Precisao_top200 | MW_obra_top200_pct |
|---|---|---|---|---|---|---|---|---|---|---|---|
| Modelo (Tarefa 3) | 0,2645 | 0,7940 | 0,1951 | 0,0527 | 0,0582 | 0,6000 | 14,2230 | 0,5000 | 29,0401 | 0,3450 | 35,7119 |
| Baseline · persistência | 0,1223 | 0,6157 | 1,1087 | 0,0803 | 0,0582 | 0,3400 | 9,5698 | 0,3100 | 16,3093 | 0,3100 | 30,0919 |

## Previsão 2026–2030 — top 20 municípios
| NOME_MUNICIPIO | UF | PROB_NOVA_GERACAO_2026_2030 | MW_ESPERADO | RECEBEU_2021_2025 | MW_EM_OBRA_SIGA |
|---|---|---|---|---|---|
| Igaporã | BA | 0,9390 | 133,7513 | True | 0,0000 |
| Areia de Baraúnas | PB | 0,9293 | 99,8176 | True | 0,0000 |
| Pedra Grande | RN | 0,9288 | 120,9318 | True | 50,4000 |
| Simões | PI | 0,9125 | 196,3335 | True | 0,0000 |
| Bodó | RN | 0,9063 | 117,9992 | True | 106,2000 |
| Caetité | BA | 0,9019 | 128,4714 | True | 458,6600 |
| São Miguel do Gostoso | RN | 0,8998 | 117,1522 | True | 30,0000 |
| São José do Sabugi | PB | 0,8906 | 95,6683 | True | 0,0000 |
| Cerro Corá | RN | 0,8839 | 115,0864 | True | 0,0000 |
| Urandi | BA | 0,8796 | 125,3012 | True | 223,2000 |
| Campo Formoso | BA | 0,8761 | 124,7925 | True | 142,8000 |
| Licínio de Almeida | BA | 0,8753 | 124,6894 | True | 105,4000 |
| Mulungu do Morro | BA | 0,8748 | 124,6178 | True | 0,0000 |
| Queimada Nova | PI | 0,8724 | 187,6988 | True | 33,6000 |
| Lagoa do Barro do Piauí | PI | 0,8719 | 187,5974 | True | 357,4480 |
| Morro do Chapéu | BA | 0,8636 | 123,0169 | True | 553,3800 |
| Gentio do Ouro | BA | 0,8628 | 122,9083 | True | 761,6400 |
| Itaguaçu da Bahia | BA | 0,8599 | 122,4852 | True | 99,9980 |
| São José do Belmonte | PE | 0,8599 | 51,5921 | True | 723,0000 |
| Brotas de Macaúbas | BA | 0,8563 | 121,9740 | True | 0,0000 |

## Previsão 2026–2030 por UF
| UF | PROB_MEDIA | MW_ESPERADO | MW_EM_OBRA_SIGA |
|---|---|---|---|
| RN | 0,3509 | 7.629,1289 | 5.931,5990 |
| BA | 0,1244 | 7.387,2559 | 20.821,8790 |
| PI | 0,1084 | 5.223,7059 | 13.216,5420 |
| RJ | 0,0990 | 5.035,1706 | 1.667,1950 |
| CE | 0,1145 | 3.833,0435 | 13.637,5570 |
| MA | 0,0430 | 2.328,4997 | 367,1180 |
| PB | 0,0928 | 2.222,3456 | 5.013,4310 |
| MG | 0,0422 | 2.218,4550 | 16.950,0930 |
| PE | 0,1106 | 1.227,8361 | 2.514,8721 |
| SP | 0,0522 | 1.117,6155 | 535,1300 |
| MS | 0,1130 | 428,5400 | 2.334,2180 |
| MT | 0,1091 | 418,7867 | 1.568,0066 |
| PR | 0,0433 | 345,1719 | 239,0900 |
| RS | 0,0466 | 338,1805 | 2.298,0030 |
| GO | 0,0450 | 258,5494 | 4.251,4550 |
| SC | 0,0637 | 174,3372 | 445,1017 |
| AL | 0,0424 | 173,1212 | 102,7000 |
| AM | 0,3154 | 141,3189 | 662,5716 |
| ES | 0,0513 | 95,9012 | 5,0000 |
| AP | 0,1283 | 82,8582 | 7,5000 |
| SE | 0,0262 | 79,3713 | 782,4880 |
| RR | 0,2148 | 37,2144 | 0,0000 |
| AC | 0,1754 | 36,3560 | 0,0000 |
| TO | 0,0280 | 31,1794 | 710,2010 |
| RO | 0,0717 | 19,5817 | 81,0000 |
| PA | 0,1156 | 12,5725 | 1.601,9880 |
| DF | 0,0604 | 2,4381 | 0,0000 |

`MW_ESPERADO` = probabilidade calibrada × mediana dos MW recebidos pelos municípios da UF que receberam geração em 2021–2025 (ordem de grandeza, não projeção de leilão).