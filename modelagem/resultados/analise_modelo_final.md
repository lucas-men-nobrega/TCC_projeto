# Análise do modelo final — rodada completa (16/10/2026)

Base: `relatorio.md`, `comparacao_tarefa1_consumo*.csv`, `comparacao_tarefa2_grupos_tensao*.csv` e `ablacao.csv`.
Validação: Spatial Block CV, 5 folds × 3 repetições (15 folds), amostra de 121.884 UCs, alvo anualizado.
Comparações pareadas fold a fold usam o t de Nadeau-Bengio (folds de CV compartilham treino).

## Tarefa 1 — consumo anual de uma nova UC

**Modelo final: Random Forest padrão (lat/lon) + todos.** RMSE_log = 1,267 ± 0,051, R² = 0,576, MdAPE = 54,0%.

### 1. Supera os boostings de forma estatisticamente sustentada

| RF + todos vs. | ΔRMSE_log | folds em que o RF venceu | p corrigido | ΔMdAPE |
|---|---|---|---|---|
| CatBoost + todos | −0,023 | 13/15 | 0,027 | −6,1 p.p. (15/15) |
| LightGBM + todos | −0,025 | 14/15 | 0,048 | −5,6 p.p. (15/15) |

No RMSE a diferença é pequena. Na mediana do erro (MdAPE) ela é grande e consistente. Há um custo: o RF levou cerca de 2.000 s, contra 114 s do LightGBM. Se o tempo pesar, o LightGBM + todos é uma alternativa só um pouco pior.

### 2. O ganho vem quase todo do perfil declarado e da rede

Ablação sobre o RF lat/lon (R² base de 0,154):

| grupo | ΔR² | significativo? |
|---|---|---|
| perfil | +0,350 | sim, 15/15 folds, p ≈ 0 |
| rede | +0,173 | sim, p = 0,011 |
| geração (`ger`) | +0,046 | não (p = 0,29; IC cruza zero) |
| IBGE | +0,035 | não no geral, mas melhora o MdAPE (p = 0,013) e o R² de MT (+0,08, 14/15 folds) |
| todos | +0,422 | sim |

O modelo "todos" ainda supera o "perfil" sozinho em 15/15 folds (+0,07 de R²). Ou seja, rede, IBGE e geração somam informação de forma complementar, mesmo que isoladamente sejam fracos. A interpretabilidade anterior aponta na mesma direção: na permutação, perfil = 1,28, rede = 0,43, posição = 0,08 e geração/IBGE ≈ 0.

### 3. Desempenho por grupo de tensão

- **MT:** R² = 0,58, bom e estável (dp 0,07).
- **BT:** R² = 0,46 (dp 0,07). É o grupo mais numeroso e o que mais ganhou com "todos" (+0,53).
- **AT:** R² = 0,31, mas com dp 0,35. É instável, porque há poucas UCs AT por fold, e não deve ser apresentado como resultado confiável.
- Em MT e AT, o modelo só com perfil (0,599 e 0,343) supera o "todos" (0,582 e 0,308). Os grupos extras ajudam a BT e adicionam um pouco de ruído nas tensões mais altas.

### 4. Como ler o erro na prática

Um MAE_log de 0,91 equivale a errar, tipicamente, por um fator de cerca de 2,5× (e^0,91), e o MdAPE de 54% diz que metade das previsões erra por mais da metade do consumo real. O modelo serve como **estimativa de ordem de grandeza** para o pedido de ligação, não como previsão pontual. O viés ficou pequeno (0,07 em log, contra 0,4–0,7 nos modelos sem perfil), o que é bom para agregados.

### 5. Os modelos geoestatísticos ficaram abaixo dos de ML

Krigagem (R² ≈ 0), GWR (R² negativo, só 7 de 15 folds concluídos) e kNN (baseline) ficaram atrás. O consumo de uma UC é dominado por atributos próprios, e a autocorrelação espacial explica pouco. O XGBoost foi o mais instável (dp 0,31), provavelmente por falta de tuning.

### Ressalva: o modelo regional

As previsões por município usam **RF + geração**, com R² = 0,20 e MdAPE de 78%, bem mais fraco que o modelo final.

- O ganho de `ger` sobre o RF puro **não é significativo** (p corrigido = 0,29). O Wilcoxon (0,018) ignora que os folds compartilham dados de treino, então não basta para justificar a escolha.
- O RF + IBGE fica praticamente empatado (RMSE 1,758 contra 1,748) e é o único grupo com ganho significativo no MdAPE. Vale testar uma variante **ger + ibge** para o cenário regional, já que hoje o "todos" fica de fora porque inclui perfil e rede.

## Tarefa 2 — distribuição de GRU_TEN

**Melhor modelo: CatBoost (feat. espaciais) + todos.** LogLoss = 0,194, TVD regional = 0,070.

- Supera o GP na TVD (−0,015, 14/15 folds, p = 0,046). Na LogLoss o ganho **não é significativo** (p = 0,10).
- O ganho sobre o CatBoost + rede é pequeno, mas consistente (15/15 folds na LogLoss, p = 0,016).

### Nenhum modelo discrimina as classes individualmente

- A acurácia balanceada fica entre 0,333 e 0,34 em todos os bons modelos, o mesmo que um chute. No GP ela é exatamente 1/3 com dp 0: ele prevê sempre BT.
- A AUC-PR de MT é 0,13, contra uma prevalência de 0,05 (ganho de cerca de 2,5×). A de AT é 0,003, contra 0,0003: o ganho relativo é de 10×, mas o valor absoluto é desprezível.
- Por isso a tarefa só se sustenta como **estimativa da proporção regional** (TVD), não como classificação de UCs.
- RF e XGBoost têm F1 maior, mas LogLoss e TVD muito piores: estão mal calibrados.

### O modelo regional também pode melhorar

Hoje é o GP, mas o CatBoost + IBGE e o CatBoost + geração, que também podem ser usados no cenário regional, têm:

- TVD melhor (0,081–0,082 contra 0,085);
- AUC-PR de MT bem maior (0,10–0,11 contra 0,068);
- LogLoss apenas 0,002 pior.

Eles são candidatos melhores para o mapa regional do que um modelo que só reproduz a classe majoritária.

## Rankings e cuidados de comparação

- Os rankings de consumo e de expansão são descritivos e não mudaram em relação à rodada anterior.
- **Não compare diretamente com a rodada anterior.** O RF base caiu de R² 0,22 para 0,15 porque mudaram o protocolo (5 folds × 3 repetições) e o alvo (agora anualizado). O ganho real vem da ablação dentro da mesma rodada.
- **Interpretabilidade desatualizada:** a pasta `explicacao/` é de 15/10, rodada no modo rápido (3 folds, 32 mil UCs). Rodar de novo o `explicar_modelos.py` no modo completo, para que SHAP, resíduos e importâncias correspondam ao modelo final.
- **Importâncias do modelo errado:** o `importancia_features_tarefa1.csv` se refere ao modelo **regional** (RF + geração), não ao final. Por isso aparecem LAT/LON no topo e nenhuma variável de perfil.

## Resumo

O RF com todos os grupos explica cerca de 58% da variância do log-consumo sob validação espacial rigorosa e supera os boostings com significância. O ganho vem principalmente do perfil declarado e da rede, enquanto geração e IBGE contribuem pouco. Para o cenário regional, sem perfil, a capacidade preditiva cai para R² ≈ 0,2, e a classificação de tensão só é útil em nível agregado.
