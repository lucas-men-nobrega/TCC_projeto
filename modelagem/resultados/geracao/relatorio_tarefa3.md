# Tarefa 3 — onde a geração centralizada se expande

- Unidade: município (5.570). Alvo: receber potência liberada para operação comercial nos 5 anos seguintes ao corte.
- Variáveis só com dados até o ano de corte (conexões BDGD por `DAT_CON`, estoque de geração, posição).
- Validação temporal: treino T=2015 (alvo 2016–2020) → teste T=2020 (alvo 2021–2025). Validação espacial: 5 folds, 50 blocos K-means em T=2020.
- Prevalência do alvo no teste: 5.4% dos municípios. A AUC-PR de um modelo sem informação é igual à prevalência.

## Classificação — recebe nova geração?
| esquema | modelo | AUC_PR | AUC_ROC | LogLoss | Brier |
|---|---|---|---|---|---|
| temporal | Random Forest | 0,3192 | 0,8213 | 0,1706 | 0,0439 |
| temporal | Regressão logística | 0,2952 | 0,8055 | 0,1745 | 0,0453 |
| temporal | CatBoost | 0,2931 | 0,7986 | 0,1774 | 0,0459 |
| temporal | LightGBM | 0,2848 | 0,8024 | 0,1831 | 0,0472 |
| temporal | Baseline · kNN espacial | 0,1787 | 0,7523 | 0,2391 | 0,0480 |
| temporal | Baseline · persistência | 0,1511 | 0,6492 | 0,1857 | 0,0462 |
| espacial | Random Forest | 0,3085 | 0,8104 | 0,1761 | 0,0445 |
| espacial | CatBoost | 0,3020 | 0,7906 | 0,1799 | 0,0450 |
| espacial | Regressão logística | 0,2869 | 0,8129 | 0,1766 | 0,0458 |
| espacial | LightGBM | 0,2756 | 0,7737 | 0,1970 | 0,0462 |
| espacial | Baseline · persistência | 0,1519 | 0,6457 | 0,1863 | 0,0464 |
| espacial | Baseline · kNN espacial | 0,1392 | 0,6109 | 0,3216 | 0,0525 |

**Melhor modelo (AUC-PR temporal):** Random Forest

## Parte contínua — log1p(MW) nos municípios que receberam (validação temporal)
| modelo | RMSE_log | R2_log | n_treino | n_teste |
|---|---|---|---|---|
| Baseline · média | 1,6739 | -0,1112 | 290 | 299 |
| Ridge | 1,3169 | 0,3123 | 290 | 299 |
| Random Forest | 1,2819 | 0,3483 | 290 | 299 |
| LightGBM | 1,4341 | 0,1843 | 290 | 299 |

## Previsão 2026–2030 — top 20 municípios
| NOME_MUNICIPIO | UF | PROB_NOVA_GERACAO_2026_2030 | MW_ESPERADO | RECEBEU_2021_2025 |
|---|---|---|---|---|
| Igaporã | BA | 0,8183 | 116,5709 | True |
| São José do Belmonte | PE | 0,8112 | 48,6718 | True |
| Morro do Chapéu | BA | 0,8042 | 114,5553 | True |
| Juazeiro | BA | 0,7980 | 113,6677 | True |
| Licínio de Almeida | BA | 0,7854 | 111,8772 | True |
| Campo Formoso | BA | 0,7803 | 111,1459 | True |
| Urandi | BA | 0,7770 | 110,6751 | True |
| Xique-Xique | BA | 0,7754 | 110,4529 | True |
| Pindaí | BA | 0,7510 | 106,9769 | True |
| Sítio Novo | RN | 0,7480 | 97,3942 | False |
| Várzea da Palma | MG | 0,7473 | 46,1104 | True |
| Brotas de Macaúbas | BA | 0,7457 | 106,2276 | True |
| Itaguaçu da Bahia | BA | 0,7444 | 106,0405 | True |
| Junco do Seridó | PB | 0,7435 | 79,8608 | True |
| Lagoa do Barro do Piauí | PI | 0,7416 | 159,5589 | True |
| Gentio do Ouro | BA | 0,7388 | 105,2447 | True |
| São Pedro | RN | 0,7359 | 95,8120 | False |
| Queimada Nova | PI | 0,7348 | 158,1044 | True |
| Icapuí | CE | 0,7329 | 133,3888 | True |
| São Bento do Trairí | RN | 0,7327 | 95,4030 | False |

## Previsão 2026–2030 por UF
| UF | PROB_MEDIA | MW_ESPERADO |
|---|---|---|
| RN | 0,3280 | 7.132,0370 |
| BA | 0,1158 | 6.880,9472 |
| RJ | 0,0981 | 4.990,9135 |
| CE | 0,1275 | 4.269,2733 |
| PI | 0,0872 | 4.201,5546 |
| PB | 0,0954 | 2.285,8045 |
| MG | 0,0421 | 2.216,4539 |
| MA | 0,0295 | 1.598,4106 |
| PE | 0,1162 | 1.289,3932 |
| SP | 0,0587 | 1.256,5866 |
| MS | 0,1247 | 472,7286 |
| MT | 0,1213 | 465,6169 |
| PR | 0,0505 | 403,0073 |
| RS | 0,0487 | 354,0314 |
| AL | 0,0628 | 256,1777 |
| GO | 0,0371 | 213,3805 |
| SC | 0,0753 | 205,9711 |
| ES | 0,0604 | 112,9524 |
| AM | 0,2443 | 109,4619 |
| AP | 0,1131 | 73,0744 |
| SE | 0,0240 | 72,6012 |
| RR | 0,2597 | 44,9914 |
| RO | 0,1171 | 31,9755 |
| AC | 0,1523 | 31,5695 |
| TO | 0,0215 | 23,9488 |
| PA | 0,1090 | 11,8481 |
| DF | 0,1001 | 4,0413 |

`MW_ESPERADO` = probabilidade × mediana dos MW recebidos pelos municípios da UF que receberam geração em 2021–2025 (ordem de grandeza, não projeção de leilão).