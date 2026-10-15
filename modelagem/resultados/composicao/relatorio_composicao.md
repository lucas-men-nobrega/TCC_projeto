# Tarefa 2 (municipal) — composição dos grupos de tensão

- Unidade: município (5.280; métricas nos 5.280 com ≥ 30 UCs ativas). Alvo: frações BT/MT/AT das UCs ativas.
- 282 municípios com menos de 10 UCs ativas por mil habitantes (cobertura insuficiente: GO e região metropolitana do RJ) ficam fora do treino e da avaliação; recebem previsão. marcada em `COBERTURA_INSUFICIENTE`.
- Validação: Spatial Block CV nas sedes — 5 folds × 3 repetições, 50 blocos K-means.
- Modelo multinomial agregado: 3 linhas por município (uma por classe), peso = fração observada.
- TVD: distância de variação total entre a composição observada e a prevista (0 = idêntica). EA_MT_pp / EA_AT_pp: erro absoluto médio na fração de MT / AT (pontos percentuais).

## Comparação
| modelo | variante | TVD | TVD_pond_UC | EA_MT_pp | EA_AT_pp | Entropia_cruzada | R2_P_MT |
|---|---|---|---|---|---|---|---|
| Logística multinomial | todos (sem knn) | 0,0126 | 0,0131 | 1,2523 | 0,0236 | 0,1094 | 0,4744 |
| CatBoost | todos (sem knn) | 0,0130 | 0,0123 | 1,2847 | 0,0309 | 0,1101 | 0,3939 |
| LightGBM | + ibge | 0,0133 | 0,0121 | 1,3165 | 0,0201 | 0,1104 | 0,2813 |
| LightGBM | todos (sem knn) | 0,0133 | 0,0135 | 1,3159 | 0,0206 | 0,1101 | 0,1791 |
| CatBoost | + ibge | 0,0139 | 0,0132 | 1,3699 | 0,0326 | 0,1109 | 0,3324 |
| Logística multinomial | + ibge | 0,0143 | 0,0144 | 1,4160 | 0,0235 | 0,1108 | 0,2686 |
| CatBoost | + rede | 0,0155 | 0,0136 | 1,5271 | 0,0336 | 0,1123 | 0,2641 |
| Logística multinomial | + rede | 0,0158 | 0,0149 | 1,5593 | 0,0277 | 0,1126 | 0,3045 |
| LightGBM | + rede | 0,0163 | 0,0152 | 1,6177 | 0,0237 | 0,1132 | 0,1533 |
| LightGBM | base | 0,0165 | 0,0152 | 1,6329 | 0,0248 | 0,1138 | 0,0609 |
| CatBoost | base | 0,0166 | 0,0143 | 1,6395 | 0,0354 | 0,1138 | 0,1320 |
| CatBoost | + ger | 0,0167 | 0,0148 | 1,6490 | 0,0362 | 0,1142 | 0,0810 |
| LightGBM | + ger | 0,0168 | 0,0166 | 1,6636 | 0,0233 | 0,1141 | -0,0364 |
| Baseline · kNN espacial | — | 0,0171 | 0,0169 | 1,6901 | 0,0297 | 0,1154 | -0,0779 |
| Logística multinomial | + ger | 0,0186 | 0,0166 | 1,8419 | 0,0277 | 0,1161 | -0,0293 |

**Melhor:** Logística multinomial (todos (sem knn))

## Ablação — TVD (variante − base, mesmos folds; t corrigido de Nadeau-Bengio)
| modelo | variante | base | com_variante | delta_media | folds_melhor | n_folds | p_t_corrigido | p_wilcoxon |
|---|---|---|---|---|---|---|---|---|
| Logística multinomial | + knn | 0,0191 | 0,0211 | 0,0020 | 5 | 15 | 0,3840 | 0,0946 |
| Logística multinomial | + ibge | 0,0191 | 0,0143 | -0,0049 | 15 | 15 | 0,0000 | 0,0001 |
| Logística multinomial | + ger | 0,0191 | 0,0186 | -0,0005 | 14 | 15 | 0,0539 | 0,0026 |
| Logística multinomial | + rede | 0,0191 | 0,0158 | -0,0034 | 15 | 15 | 0,0003 | 0,0001 |
| Logística multinomial | todos (sem knn) | 0,0191 | 0,0126 | -0,0065 | 15 | 15 | 0,0000 | 0,0001 |
| LightGBM | + knn | 0,0165 | 0,0353 | 0,0188 | 0 | 15 | 0,0217 | 0,0001 |
| LightGBM | + ibge | 0,0165 | 0,0133 | -0,0032 | 15 | 15 | 0,0006 | 0,0001 |
| LightGBM | + ger | 0,0165 | 0,0168 | 0,0003 | 7 | 15 | 0,7546 | 0,9780 |
| LightGBM | + rede | 0,0165 | 0,0163 | -0,0002 | 8 | 15 | 0,8443 | 0,8040 |
| LightGBM | todos (sem knn) | 0,0165 | 0,0133 | -0,0032 | 14 | 15 | 0,0030 | 0,0001 |
| CatBoost | + knn | 0,0166 | 0,0236 | 0,0070 | 1 | 15 | 0,0986 | 0,0001 |
| CatBoost | + ibge | 0,0166 | 0,0139 | -0,0027 | 15 | 15 | 0,0000 | 0,0001 |
| CatBoost | + ger | 0,0166 | 0,0167 | 0,0001 | 7 | 15 | 0,7951 | 0,9780 |
| CatBoost | + rede | 0,0166 | 0,0155 | -0,0011 | 13 | 15 | 0,0429 | 0,0009 |
| CatBoost | todos (sem knn) | 0,0166 | 0,0130 | -0,0036 | 15 | 15 | 0,0000 | 0,0001 |

## Municípios com mais MT do que o previsto (top 15)
| NOME_MUNICIPIO | UF | N_UC | P_MT | PREV_P_MT | DIF_MT_pp |
|---|---|---|---|---|---|
| Barra do Quaraí | RS | 349 | 42,1203 | 5,5616 | 36,5588 |
| Colômbia | SP | 587 | 29,9830 | 5,7302 | 24,2528 |
| Lajedão | BA | 301 | 26,9103 | 3,8559 | 23,0544 |
| Itaqui | RS | 1584 | 26,8939 | 6,3748 | 20,5191 |
| Itabela | BA | 869 | 23,4753 | 5,7185 | 17,7567 |
| Uruguaiana | RS | 3988 | 23,2197 | 5,8106 | 17,4090 |
| Itajuípe | BA | 676 | 19,2308 | 3,8999 | 15,3309 |
| Taquaral | SP | 152 | 18,4211 | 3,9188 | 14,5023 |
| Maçambará | RS | 771 | 16,3424 | 2,6238 | 13,7186 |
| Geminiano | PI | 433 | 13,3949 | 0,6017 | 12,7933 |
| Novo Oriente do Piauí | PI | 378 | 13,4921 | 0,7837 | 12,7084 |
| Guaíra | SP | 1668 | 21,2230 | 8,7731 | 12,4499 |
| Itapé | BA | 410 | 15,6098 | 3,2740 | 12,3357 |
| Barro Preto | BA | 277 | 15,8845 | 3,5693 | 12,3151 |
| Floresta Azul | BA | 437 | 15,1030 | 2,8853 | 12,2176 |