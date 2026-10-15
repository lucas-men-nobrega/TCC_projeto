# Validação do índice de expansão — selo de confiabilidade

- Fração de UCs ativas com `DAT_CON` em 2023–2025: mediana nacional **12,2%** (municípios com ≥ 30 UCs). Suspeita de recadastramento acima de **36,6%** (3× a mediana).
- Evidência independente: potência liberada para operação comercial em 2021–2025 a até 50 km da sede (ANEEL/SIGA).
- Selos: **4.914 Alta · 90 Média · 559 Baixa**
- Municípios com suspeita de recadastramento: **479**
- Top 30 do índice de expansão: **30** com suspeita; selos Baixa: 24, Média: 6

## O índice acompanha a geração?
- Spearman (municípios): índice × log MW recentes a 50 km = **-0,043**; sem os municípios suspeitos = **0,010**
- Spearman (UFs): índice médio × log MW recentes = **0,012**
- Correlação próxima de zero indica que a expansão da geração centralizada (guiada pelo recurso: vento, sol, rios) não acompanha a das conexões de consumo. Por isso a geração no entorno só eleva um município suspeito a **Média**, nunca a Alta: ela mostra atividade nova na região, não prova que as datas de ligação estão corretas. O selo se apoia sobretudo no sinal de qualidade do dado.

## Por UF
| SIGLA_UF | MUNICIPIOS | INDICE_MEDIO | PCT_DAT_RECENTE | MW_GER_RECENTE | PCT_SUSPEITOS | PCT_SELO_BAIXA |
|---|---|---|---|---|---|---|
| AL | 102,0000 | 0,9450 | 0,9757 | 40,0000 | 100,0000 | 77,4510 |
| AP | 16,0000 | 0,9529 | 0,9808 | 0,0000 | 100,0000 | 100,0000 |
| PI | 224,0000 | 0,9638 | 0,9856 | 3.671,9844 | 100,0000 | 80,8036 |
| PA | 144,0000 | 0,7722 | 0,5817 | 14,4500 | 58,3333 | 54,8611 |
| MA | 217,0000 | 0,7338 | 0,2899 | 499,1470 | 12,4424 | 11,0599 |
| RN | 167,0000 | 0,6972 | 0,3168 | 7.265,0585 | 4,7904 | 2,9940 |
| RJ | 84,0000 | 0,4514 | 0,2573 | 4.287,7150 | 4,7619 | 1,1905 |
| MT | 141,0000 | 0,7197 | 0,2589 | 309,8200 | 2,8369 | 0,0000 |
| CE | 184,0000 | 0,6755 | 0,1769 | 2.059,1084 | 2,1739 | 0,5435 |
| SP | 645,0000 | 0,5133 | 0,1289 | 1.904,1950 | 0,4651 | 0,0000 |
| RS | 497,0000 | 0,5620 | 0,1607 | 454,3010 | 0,4024 | 0,4024 |
| BA | 417,0000 | 0,6920 | 0,2255 | 9.214,3271 | 0,2398 | 0,2398 |
| MS | 79,0000 | 0,5756 | 0,1801 | 885,0120 | 0,0000 | 0,0000 |
| MG | 853,0000 | 0,5378 | 0,1483 | 8.036,4077 | 0,0000 | 0,0000 |
| GO | 77,0000 | 0,4324 | 0,0776 | 162,2946 | 0,0000 | 0,0000 |
| ES | 78,0000 | 0,4072 | 0,0674 | 160,4520 | 0,0000 | 0,0000 |
| DF | 1,0000 | 0,3140 | 0,0475 | 0,0000 | 0,0000 | 0,0000 |
| AM | 62,0000 | 0,0116 | 0,0086 | 216,4605 | 0,0000 | 0,0000 |
| AC | 22,0000 | 0,6291 | 0,1775 | 69,4664 | 0,0000 | 0,0000 |
| PB | 223,0000 | 0,6095 | 0,1763 | 1.522,6565 | 0,0000 | 0,0000 |
| PR | 399,0000 | 0,3887 | 0,0638 | 588,4630 | 0,0000 | 0,0000 |
| PE | 185,0000 | 0,7202 | 0,2222 | 2.082,7240 | 0,0000 | 0,0000 |
| N/D | 1,0000 | 0,8126 | 0,2500 | 0,0000 | 0,0000 | 0,0000 |
| RO | 52,0000 | 0,6694 | 0,1952 | 10,5000 | 0,0000 | 0,0000 |
| RR | 15,0000 | 0,0385 | 0,0205 | 261,2850 | 0,0000 | 0,0000 |
| SC | 294,0000 | 0,1395 | 0,0478 | 353,7580 | 0,0000 | 0,0000 |
| SE | 75,0000 | 0,5978 | 0,1600 | 0,0000 | 0,0000 | 0,0000 |
| TO | 139,0000 | 0,4999 | 0,1556 | 8,0000 | 0,0000 | 0,0000 |

## Quadrante × selo
| QUADRANTE | Alta | Baixa | Média |
|---|---|---|---|
| Amostra insuficiente (<30 UCs) | 0 | 170 | 0 |
| Baixa dinâmica | 3727 | 7 | 1 |
| Fronteira de expansão | 156 | 353 | 70 |
| Polo consolidado | 866 | 4 | 4 |
| Polo consolidado em expansão | 165 | 25 | 15 |

## Top 30 do índice de expansão com o selo
| NOME_MUNICIPIO | SIGLA_UF | INDICE_EXPANSAO | PCT_DAT_RECENTE | MW_GER_RECENTE_50KM | SELO_CONFIABILIDADE |
|---|---|---|---|---|---|
| Miguel Alves | PI | 0,9966 | 100,0000 | 0,0000 | Baixa |
| Oiapoque | AP | 0,9965 | 100,0000 | 0,0000 | Baixa |
| Colônia do Piauí | PI | 0,9964 | 100,0000 | 0,0000 | Baixa |
| Alto Longá | PI | 0,9962 | 100,0000 | 0,0000 | Baixa |
| Ipiranga do Piauí | PI | 0,9962 | 100,0000 | 0,0000 | Baixa |
| Capitão de Campos | PI | 0,9961 | 100,0000 | 0,0000 | Baixa |
| Cumaru do Norte | PA | 0,9955 | 100,0000 | 0,0000 | Baixa |
| Nazária | PI | 0,9952 | 100,0000 | 0,0000 | Baixa |
| Isaías Coelho | PI | 0,9950 | 100,0000 | 0,0000 | Baixa |
| Brasileira | PI | 0,9949 | 100,0000 | 360,0000 | Média |
| Novo Oriente do Piauí | PI | 0,9949 | 100,0000 | 0,0000 | Baixa |
| Barro Duro | PI | 0,9948 | 100,0000 | 0,0000 | Baixa |
| Acauã | PI | 0,9946 | 100,0000 | 206,8000 | Média |
| Dom Inocêncio | PI | 0,9945 | 100,0000 | 1.300,2000 | Média |
| Afuá | PA | 0,9942 | 100,0000 | 0,0000 | Baixa |
| São José do Piauí | PI | 0,9941 | 100,0000 | 0,0000 | Baixa |
| Amapá | AP | 0,9940 | 100,0000 | 0,0000 | Baixa |
| São João do Arraial | PI | 0,9939 | 100,0000 | 0,0000 | Baixa |
| São Francisco de Assis do Piauí | PI | 0,9938 | 100,0000 | 68,6000 | Média |
| Marcos Parente | PI | 0,9937 | 100,0000 | 0,0000 | Baixa |
| Murici dos Portelas | PI | 0,9936 | 100,0000 | 0,0000 | Baixa |
| Massapê do Piauí | PI | 0,9935 | 100,0000 | 45,6000 | Média |
| Palmeira do Piauí | PI | 0,9934 | 100,0000 | 0,0000 | Baixa |
| Lagoa do Sítio | PI | 0,9932 | 100,0000 | 0,0000 | Baixa |
| São Julião | PI | 0,9932 | 100,0000 | 258,6940 | Média |
| Bocaina | PI | 0,9931 | 100,0000 | 0,0000 | Baixa |
| Castelo do Piauí | PI | 0,9930 | 99,9056 | 0,0000 | Baixa |
| Paragominas | PA | 0,9930 | 99,8120 | 0,0000 | Baixa |
| Quatipuru | PA | 0,9930 | 100,0000 | 0,0000 | Baixa |
| Boa Hora | PI | 0,9929 | 100,0000 | 0,0000 | Baixa |