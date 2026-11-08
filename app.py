"""Ponto de entrada e menu lateral.

Executar:  streamlit run app.py

O nome de cada item do menu é definido aqui (`title=`), independente do nome do arquivo.
A tela do catálogo fica em views/catalogo.py.
"""
import streamlit as st

pagina = st.navigation([
    st.Page("views/catalogo.py", title="Catalogo", default=True),
    st.Page("pages/1_Carrinho.py", title="Carrinho"),
    st.Page("pages/2_Pedidos.py", title="Pedidos"),
    st.Page("pages/3_Cadastrar_Produto.py", title="Cadastrar Produto"),
])
pagina.run()
