"""Carrinho e checkout — grava o pedido no MongoDB."""
import html
import re

import streamlit as st

from src.repositories.pedidos import (CUPONS, FRETE_GRATIS_ACIMA, EstoqueInsuficiente,
                                      PedidoInvalido, calcular_valores)
from src.services import catalogo, checkout
from src.ui import carrinho, configurar_pagina, imagem_principal, remover_do_carrinho
from src.utils import dinheiro, fmt_brl

UFS = ["AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA",
       "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]
PAGAMENTOS = {"pix": "Pix", "cartao_credito": "Cartão de crédito", "boleto": "Boleto bancário"}

configurar_pagina("Carrinho", "🛒")
st.title("🛒 Seu carrinho")

if numero := st.session_state.pop("ultimo_pedido", None):
    st.success(f"Pedido **{numero}** realizado com sucesso! 🎉")
    st.page_link("pages/2_Pedidos.py", label="Ver meus pedidos", icon="📦")

itens_carrinho = carrinho()
if not itens_carrinho:
    st.info("Seu carrinho está vazio.")
    st.page_link("app.py", label="Continuar comprando", icon="🛍️")
    st.stop()

produtos = catalogo.obter_produtos(list(itens_carrinho))

col_itens, col_resumo = st.columns([3, 1.3], gap="large")

linhas = []
with col_itens:
    for pid, qtd in list(itens_carrinho.items()):
        p = produtos.get(pid)
        if not p or int(p.get("estoque", 0)) <= 0:
            remover_do_carrinho(pid)
            st.warning("Um item ficou indisponível e foi removido do carrinho.")
            continue
        estoque = int(p["estoque"])
        with st.container(border=True):
            c_img, c_info, c_qtd, c_sub, c_rm = st.columns([1, 4, 1.4, 1.4, 0.6],
                                                           vertical_alignment="center")
            c_img.markdown(f'<img src="{html.escape(imagem_principal(p))}" '
                           f'style="width:80px;height:80px;object-fit:contain;background:#fff;'
                           f'border-radius:6px">', unsafe_allow_html=True)
            c_info.markdown(f"**{p['nome']}**  \n{p['marca']} · {fmt_brl(p['preco'])} cada")
            nova_qtd = c_qtd.number_input("Qtd", min_value=1, max_value=estoque,
                                          value=min(qtd, estoque), key=f"qtd_{pid}")
            itens_carrinho[pid] = int(nova_qtd)
            c_sub.markdown(f"**{fmt_brl(dinheiro(p['preco']) * int(nova_qtd))}**")
            if c_rm.button("🗑️", key=f"rm_{pid}", help="Remover"):
                remover_do_carrinho(pid)
                st.rerun()
        linhas.append({"preco_unitario": p["preco"], "quantidade": int(nova_qtd)})

with col_resumo:
    st.subheader("Resumo")
    cupom = st.text_input("Cupom de desconto", placeholder="ex.: PB10",
                          help=f"Cupons de teste: {', '.join(CUPONS)}")
    valores = calcular_valores(linhas, cupom)
    if cupom and not valores["cupom"]:
        st.caption("❌ Cupom inválido")
    st.markdown(
        f"Subtotal: **{fmt_brl(valores['subtotal'])}**  \n"
        f"Frete: **{'Grátis' if valores['frete'] == 0 else fmt_brl(valores['frete'])}**  \n"
        + (f"Desconto ({valores['cupom']}): **- {fmt_brl(valores['desconto'])}**  \n"
           if valores["desconto"] else "")
    )
    st.markdown(f"### Total: {fmt_brl(valores['total'])}")
    if valores["frete"]:
        falta = FRETE_GRATIS_ACIMA - valores["subtotal"]
        st.caption(f"Faltam {fmt_brl(falta)} para frete grátis.")

# ----------------------------------------------------------------------------- #
# Checkout
# ----------------------------------------------------------------------------- #
st.divider()
st.subheader("Finalizar compra")
with st.form("checkout"):
    c1, c2 = st.columns(2)
    nome = c1.text_input("Nome completo")
    email = c2.text_input("E-mail", value=st.session_state.get("email_cliente", ""))
    c3, c4, c5 = st.columns([1, 3, 1])
    cep = c3.text_input("CEP", placeholder="00000-000")
    logradouro = c4.text_input("Endereço (rua, número, complemento)")
    uf = c5.selectbox("UF", UFS, index=UFS.index("SP"))
    cidade = st.text_input("Cidade")
    metodo = st.radio("Pagamento", list(PAGAMENTOS), format_func=PAGAMENTOS.get, horizontal=True)
    enviar = st.form_submit_button(f"Confirmar pedido · {fmt_brl(valores['total'])}", type="primary")

if enviar:
    erros = []
    if len(nome.strip()) < 3:
        erros.append("Informe o nome completo.")
    if not re.match(r"^[^@\s]+@[^@\s]+\.[^@\s]+$", email.strip()):
        erros.append("Informe um e-mail válido.")
    if not re.match(r"^\d{5}-?\d{3}$", cep.strip()):
        erros.append("CEP inválido.")
    if not logradouro.strip() or not cidade.strip():
        erros.append("Preencha endereço e cidade.")
    if erros:
        for e in erros:
            st.error(e)
    else:
        try:
            pedido = checkout.finalizar_compra(
                cliente_nome=nome,
                cliente_email=email,
                carrinho=dict(itens_carrinho),
                endereco={"cep": cep.strip(), "logradouro": logradouro.strip(),
                          "cidade": cidade.strip(), "uf": uf},
                metodo_pagamento=metodo,
                cupom=cupom,
            )
        except (EstoqueInsuficiente, PedidoInvalido) as exc:
            st.error(str(exc))
        else:
            st.session_state["carrinho"] = {}
            st.session_state["email_cliente"] = email.strip().lower()
            st.session_state["ultimo_pedido"] = pedido["numero"]
            st.rerun()
