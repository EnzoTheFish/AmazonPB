"""Tela 3 — Painel de Recomendação (grafo).

O Neo4j decide QUAIS produtos recomendar (consulta Cypher em src/graph.py);
o MongoDB entrega os dados para exibir (preço, imagem, estoque) e o botão
"Adicionar" coloca o produto no carrinho, que vive no Redis.
"""
import streamlit as st

from src import graph
from src.services import catalogo
from src.ui import card_produto, configurar_pagina

COLUNAS = 4
ESTRATEGIAS = {
    "compras": "Quem comprou o mesmo que você também comprou",
    "avaliacoes": "Quem avaliou parecido com você também gostou",
}

configurar_pagina("Recomendações", "🎯")
st.title("🎯 Recomendações para você")
st.caption("Calculadas no grafo (Neo4j), a partir do que clientes parecidos compraram e avaliaram.")


def mostrar_erro_grafo(exc: Exception) -> None:
    st.error("Não foi possível usar o Neo4j.")
    st.caption(str(exc))
    st.markdown("Se estiver usando o Docker, suba o banco e carregue o grafo:")
    st.code("docker compose up -d neo4j\npython -m scripts.seed_neo4j --reset", language="bash")
    st.markdown("Se estiver usando o AuraDB, confira as variáveis `NEO4J_*` no arquivo `.env`.")


def painel() -> None:
    est = graph.estatisticas()
    if not est["clientes"]:
        st.info("O grafo está vazio. Carregue os dados do MongoDB para o Neo4j:")
        st.code("python -m scripts.seed_neo4j --reset", language="bash")
        st.stop()

    cols = st.columns(5)
    for col, (rotulo, chave) in zip(cols, [("Clientes", "clientes"), ("Produtos", "produtos"),
                                           ("Categorias", "categorias"), ("Compras", "compras"),
                                           ("Avaliações", "avaliacoes")]):
        col.metric(rotulo, est[chave])

    # ----------------------------------------------------------------- filtros
    clientes = graph.listar_clientes()
    emails = [c["email"] for c in clientes]
    nomes = {c["email"]: c["nome"] for c in clientes}
    padrao = st.session_state.get("email_cliente")  # e-mail usado no último checkout
    c1, c2, c3 = st.columns([2.2, 2.4, 1])
    email = c1.selectbox("Cliente", emails, index=emails.index(padrao) if padrao in emails else 0,
                         format_func=lambda e: f"{nomes[e]} ({e})")
    estrategia = c2.selectbox("Tipo de recomendação", list(ESTRATEGIAS), format_func=ESTRATEGIAS.get)
    limite = c3.number_input("Quantidade", min_value=4, max_value=12, value=8, step=4)

    historico = graph.historico_cliente(email)
    with st.expander(f"🧾 O que {nomes[email]} já comprou ({len(historico)} produtos)"):
        if historico:
            st.dataframe([{"Produto": h["nome"], "Qtd": h["quantidade"],
                           "Nota dada": h["nota"] if h["nota"] is not None else "—"}
                          for h in historico], hide_index=True)
        else:
            st.caption("Este cliente ainda não comprou nada.")

    # ----------------------------------------------------------- recomendações
    recs = graph.recomendar(email, estrategia, int(limite))
    produtos = catalogo.obter_produtos([r["produto_id"] for r in recs])  # dados vêm do MongoDB
    exibiveis = [(r, produtos[r["produto_id"]]) for r in recs if r["produto_id"] in produtos]

    st.subheader(ESTRATEGIAS[estrategia])
    if not exibiveis:
        st.warning("Ainda não há recomendações para este cliente: nenhum cliente parecido "
                   "comprou ou gostou de algo que ele não tenha. Compre ou avalie mais produtos.")
    for inicio in range(0, len(exibiveis), COLUNAS):
        for coluna, (rec, produto) in zip(st.columns(COLUNAS), exibiveis[inicio:inicio + COLUNAS]):
            with coluna:
                card_produto(produto)
                st.caption(f"👥 {rec['clientes_similares']} cliente(s) parecido(s)")

    # --------------------------------------------------------------- explicação
    if exibiveis:
        with st.expander("🔍 Por que recomendamos isso?"):
            nome_por_id = {r["produto_id"]: p["nome"] for r, p in exibiveis}
            escolhido = st.selectbox("Produto", list(nome_por_id), format_func=nome_por_id.get)
            linhas = graph.explicar(email, escolhido, estrategia)
            if not linhas:
                st.caption("Sem detalhes para este produto.")
            for linha in linhas:
                st.markdown(f"- **{linha['cliente']}** também levou este produto e tem em comum "
                            f"com {nomes[email]}: {', '.join(linha['em_comum'])}")

    # ---------------------------------------------------------------- avaliação
    with st.expander("⭐ Avaliar um produto comprado"):
        if not historico:
            st.caption("Este cliente ainda não comprou nada.")
        else:
            nome_comprado = {h["produto_id"]: h["nome"] for h in historico}
            alvo = st.selectbox("Produto", list(nome_comprado), format_func=nome_comprado.get,
                                key="alvo_avaliacao")
            nota = st.slider("Nota", 1, 5, 5)
            if st.button("Salvar avaliação", type="primary"):
                graph.registrar_avaliacao(email, alvo, nota)  # cria/atualiza [:AVALIOU] no Neo4j
                st.toast(f"Avaliação salva: {nota}★ para “{nome_comprado[alvo]}”", icon="⭐")
                st.rerun()

    with st.expander("🧠 Ver a consulta Cypher usada"):
        st.code(graph.CYPHER_RECOMENDACAO[estrategia].strip(), language="cypher")


try:
    painel()
except graph.ErroGrafo as exc:
    mostrar_erro_grafo(exc)
