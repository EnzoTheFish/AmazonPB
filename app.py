"""Tela inicial — Catálogo e busca de produtos (consulta ao MongoDB).

Executar:  streamlit run app.py
"""
import math

import streamlit as st

from src.repositories.produtos import ORDENACOES
from src.services import catalogo
from src.ui import cabecalho, card_produto, configurar_pagina
from src.utils import dinheiro

POR_PAGINA = 12
COLUNAS = 4

configurar_pagina("Catálogo", "🛍️")
cabecalho("PB Store", "Tudo o que você procura, com entrega rápida.")

facetas = catalogo.obter_facetas()
if not facetas["categorias"]:
    st.info("O catálogo está vazio. Popule o banco com dados de exemplo:")
    st.code("python -m scripts.seed", language="bash")
    st.stop()

# ----------------------------------------------------------------------------- #
# Busca + filtros
# ----------------------------------------------------------------------------- #
texto = st.text_input(
    "Buscar", placeholder="🔎  Busque por produto, marca ou categoria (ex.: notebook, Samsung, livro)",
    label_visibility="collapsed",
)

with st.sidebar:
    st.header("Filtros")
    opcoes_cat = ["Todas"] + [c for c, _ in facetas["categorias"]]
    contagem_cat = dict(facetas["categorias"])
    categoria = st.selectbox(
        "Categoria", opcoes_cat,
        format_func=lambda c: c if c == "Todas" else f"{c} ({contagem_cat[c]})",
    )
    marcas = st.multiselect("Marca", [m for m, _ in facetas["marcas"]])

    p_min = math.floor(dinheiro(facetas["preco_min"]))
    p_max = math.ceil(dinheiro(facetas["preco_max"]))
    if p_max <= p_min:
        p_max = p_min + 1
    faixa = st.slider("Faixa de preço (R$)", min_value=p_min, max_value=p_max,
                      value=(p_min, p_max), step=10 if p_max - p_min > 200 else 1)
    avaliacao_min = st.select_slider(
        "Avaliação mínima", options=[0, 1, 2, 3, 4],
        format_func=lambda v: "Qualquer" if v == 0 else f"{v}★ ou mais",
    )
    ordenacao = st.selectbox("Ordenar por", list(ORDENACOES))

filtros = {
    "texto": texto.strip(),
    "categoria": None if categoria == "Todas" else categoria,
    "marcas": sorted(marcas),
    "preco_min": faixa[0] if faixa[0] > p_min else None,
    "preco_max": faixa[1] if faixa[1] < p_max else None,
    "avaliacao_min": avaliacao_min or None,
    "ordenacao": ordenacao,
}

# volta para a página 1 sempre que os filtros mudam
if st.session_state.get("_filtros") != filtros:
    st.session_state["_filtros"] = filtros
    st.session_state["pagina"] = 1
pagina = st.session_state.get("pagina", 1)

resultado = catalogo.buscar_produtos(**filtros, pagina=pagina, por_pagina=POR_PAGINA)
total = resultado["total"]
itens = resultado["itens"]

# ----------------------------------------------------------------------------- #
# Resultados
# ----------------------------------------------------------------------------- #
legenda = f"**{total}** resultado{'s' if total != 1 else ''}"
if filtros["texto"]:
    legenda += f" para “{filtros['texto']}”"
    if resultado["modo"] == "parcial" and total:
        legenda += " · _busca aproximada_"
st.markdown(legenda)

if not itens:
    st.warning("Nenhum produto encontrado. Tente outros termos ou remova filtros.")
    st.stop()

for inicio in range(0, len(itens), COLUNAS):
    for coluna, produto in zip(st.columns(COLUNAS), itens[inicio:inicio + COLUNAS]):
        with coluna:
            card_produto(produto)

# Paginação
paginas = max(1, math.ceil(total / POR_PAGINA))
if paginas > 1:
    st.divider()
    c1, c2, c3 = st.columns([1, 2, 1])
    if c1.button("← Anterior", disabled=pagina <= 1):
        st.session_state["pagina"] = pagina - 1
        st.rerun()
    c2.markdown(f"<div style='text-align:center'>Página {pagina} de {paginas}</div>",
                unsafe_allow_html=True)
    if c3.button("Próxima →", disabled=pagina >= paginas):
        st.session_state["pagina"] = pagina + 1
        st.rerun()
