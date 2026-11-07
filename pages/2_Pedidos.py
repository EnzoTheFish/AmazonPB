"""Histórico de pedidos do comprador."""
import pandas as pd
import streamlit as st

from src.repositories import clientes as clientes_repo
from src.repositories import pedidos as pedidos_repo
from src.repositories.pedidos import PedidoInvalido
from src.services import checkout
from src.ui import configurar_pagina
from src.utils import fmt_brl, fmt_data

ICONES = {"pendente": "🕒", "pago": "💳", "enviado": "🚚", "entregue": "✅", "cancelado": "❌"}
PAGAMENTOS = {"pix": "Pix", "cartao_credito": "Cartão de crédito", "boleto": "Boleto bancário"}

configurar_pagina("Meus pedidos", "📦")
st.title("📦 Meus pedidos")

conhecidos = clientes_repo.listar()
c1, c2 = st.columns([2, 1])
email = c1.text_input("E-mail do comprador", value=st.session_state.get("email_cliente", ""))
if conhecidos:
    escolha = c2.selectbox("…ou escolha um cliente", ["—"] + [c["email"] for c in conhecidos])
    if escolha != "—" and not email:
        email = escolha

if not email:
    st.info("Informe o e-mail usado na compra para ver o histórico.")
    st.stop()

cliente = clientes_repo.obter_por_email(email)
if not cliente:
    st.warning("Nenhum cliente encontrado com esse e-mail.")
    st.stop()
st.session_state["email_cliente"] = cliente["email"]

# ----------------------------------------------------------------------------- #
# Resumo do comprador (agregação no MongoDB)
# ----------------------------------------------------------------------------- #
resumo = pedidos_repo.resumo_cliente(cliente["_id"])
st.markdown(f"### Olá, {cliente['nome'].split()[0]}!")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Pedidos", resumo["pedidos"])
m2.metric("Total gasto", fmt_brl(resumo["total_gasto"]))
m3.metric("Ticket médio", fmt_brl(resumo["ticket_medio"]))
m4.metric("Cliente desde", fmt_data(cliente.get("criado_em"), com_hora=False))

# ----------------------------------------------------------------------------- #
# Lista de pedidos
# ----------------------------------------------------------------------------- #
filtro_status = st.segmented_control(
    "Status", ["Todos", "pendente", "pago", "enviado", "entregue", "cancelado"],
    default="Todos", format_func=lambda s: s if s == "Todos" else f"{ICONES[s]} {s.title()}",
)
pedidos = pedidos_repo.listar_por_cliente(
    cliente["_id"], status=None if filtro_status in (None, "Todos") else filtro_status)

if not pedidos:
    st.caption("Nenhum pedido para este filtro.")

for ped in pedidos:
    v = ped["valores"]
    titulo = (f"{ICONES.get(ped['status'], '')} **{ped['numero']}** · "
              f"{fmt_data(ped['criado_em'])} · {ped['status'].title()} · {fmt_brl(v['total'])}")
    with st.expander(titulo):
        st.dataframe(
            pd.DataFrame([{
                "Produto": i["nome"], "Marca": i.get("marca", ""), "SKU": i["sku"],
                "Qtd": i["quantidade"], "Preço unit.": fmt_brl(i["preco_unitario"]),
                "Subtotal": fmt_brl(i["subtotal"]),
            } for i in ped["itens"]]),
            hide_index=True,
        )

        a, b, c = st.columns(3)
        with a:
            st.markdown("**Valores**")
            rotulo_cupom = f" ({ped['cupom']})" if ped.get("cupom") else ""
            st.markdown(
                f"Subtotal: {fmt_brl(v['subtotal'])}  \n"
                f"Frete: {fmt_brl(v['frete'])}  \n"
                f"Desconto{rotulo_cupom}: - {fmt_brl(v['desconto'])}  \n"
                f"**Total: {fmt_brl(v['total'])}**"
            )
        with b:
            st.markdown("**Entrega**")
            e = ped.get("endereco_entrega", {})
            st.markdown(f"{ped['cliente']['nome']}  \n{e.get('logradouro', '')}  \n"
                        f"{e.get('cidade', '')} - {e.get('uf', '')} · CEP {e.get('cep', '')}")
            st.caption(f"Pagamento: {PAGAMENTOS.get(ped['pagamento']['metodo'], '')}")
        with c:
            st.markdown("**Histórico de status**")
            for h in ped["historico_status"]:
                obs = f" — {h['obs']}" if h.get("obs") else ""
                st.markdown(f"{ICONES.get(h['status'], '')} {fmt_data(h['em'])} · "
                            f"**{h['status']}**{obs}")

        # Ações de demonstração (simulam a operação da loja)
        prox = pedidos_repo.proximo_status(ped["status"])
        b1, b2, _ = st.columns([1.3, 1, 3])
        if prox and b1.button(f"Avançar para “{prox}”", key=f"av_{ped['_id']}"):
            checkout.avancar_status(ped)
            st.rerun()
        if ped["status"] in ("pendente", "pago") and b2.button("Cancelar", key=f"cx_{ped['_id']}"):
            try:
                checkout.cancelar_pedido(ped["_id"])
                st.rerun()
            except PedidoInvalido as exc:
                st.error(str(exc))
