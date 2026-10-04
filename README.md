# ⚡ Análise da Descentralização da Geração de Energia no Brasil

Este repositório contém scripts e instruções para analisar a evolução espacial e de mercado da geração de energia elétrica no Brasil, utilizando a **BDGD (Base de Dados Geográfica da Distribuidora)** da ANEEL.

## 🎯 A Hipótese

A pesquisa conduzida neste repositório visa responder à seguinte hipótese dupla:
1. **A geração de energia elétrica está se descentralizando para o interior ou permanece concentrada nas grandes metrópoles do Brasil?**
2. **Como essa dinâmica está reconfigurando o mercado de energia e impulsionando as fontes renováveis no país?**

## 🗂️ Origem dos Dados

A análise baseia-se primordialmente no **Módulo 10 do PRODIST (Novo Modelo BDGD)**, que mapeia geoespacialmente todos os ativos de distribuição e geração do país. 

As principais tabelas (shapefiles/geodatabases) utilizadas desta base são:

* `UCBT` 
* `UCMT`
* `UCAT` 

## 🛠️ Metodologia e Instruções de Análise

Para validar a hipótese, o pesquisador deve seguir o roteiro de análise abaixo estruturado nos scripts deste repositório:

### Passo 1: Extração e Tratamento (ETL)
Nas tabelas de geração (`UGBT`, `UGMT`, `UGAT`), foque nas seguintes colunas vitais:
* **`COD_ID`**: Identificador único do gerador.
* **`MUN`**: Código IBGE do município (Crucial para separar Metrópoles vs. Interior).
* **`ARE_LOC`**: Classificação de área (Urbana vs. Não Urbana/Rural).
* **`POT_INST`**: Potência Instalada em kW (Mede o tamanho do mercado).
* **`DAT_CON`**: Data de Conexão (Essencial para a análise temporal de descentralização).
* **`CEG` / `CODGD`**: Códigos de identificação do gerador nos sistemas SIGA e SISGD da ANEEL.

### Passo 2: Análise Espacial (Metrópoles vs. Interior)
1. Utilize o campo `MUN` (Código IBGE) para classificar os municípios em "Regiões Metropolitanas" e "Interior".
2. Calcule a proporção de `POT_INST` (Potência) agregada por essas duas regiões.
3. Utilize as geometrias (pontos geográficos das UGs) para plotar mapas de calor (Heatmaps) no QGIS ou usando bibliotecas como `Folium`/`GeoPandas` em Python, evidenciando a densidade de usinas.

### Passo 3: Análise Temporal (O Ritmo da Descentralização)
1. Extraia o ano da coluna `DAT_CON`.
2. Crie gráficos de linha mostrando o crescimento da Potência Instalada (`POT_INST`) ano a ano nas Metrópoles versus no Interior.


### Passo 4: Cruzamento com Mercado de Renováveis
1. Pegue as colunas **`CODGD`** (Geração Distribuída) e **`CEG`** (Geração Centralizada) das tabelas `UGxx`.
2. Cruze (faça um *Join*) com os Dados Abertos da ANEEL (bases SIGA e SISGD) usando essas chaves.
3. Analise qual fonte domina o avanço para o interior. (Exemplo esperado: Explosão da energia Solar Fotovoltaica no interior e áreas rurais devido à disponibilidade e custo de terras).

## 📊 Como o mercado é afetado? (Perguntas para guiar os scripts)
Ao compilar os dados, seus scripts devem ser capazes de responder:
* A proporção de consumidores livres (`LIV = 1` nas tabelas `UCxx` e `UGxx`) está crescendo fora dos grandes centros?
* Como a energia ativa injetada (`ENE_01` a `ENE_12`) pelas UGs no interior afeta a necessidade de reforço nas redes de Baixa e Média tensão (tabelas `SSDBT` e `SSDMT`)?

## 🚀 Requisitos para Rodar o Projeto

* **Linguagem:** Python 3.8+
* **Bibliotecas:** `pandas`, `geopandas`, `matplotlib`, `seaborn`, `shapely`.
* **Software GIS:** QGIS (Opcional, para visualização rápida dos shapefiles `.shp` ou `.gdb` da BDGD).

---
*Este repositório é um projeto de pesquisa independente utilizando dados públicos regulatórios estruturados pelo Manual de Instruções da BDGD - ANEEL.*