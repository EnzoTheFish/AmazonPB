"""Componentes visuais compartilhados entre as telas Streamlit."""
from __future__ import annotations

import html
import json

import pandas as pd
import streamlit as st
from bson import json_util

from . import carrinho_redis
from .db import init_db, ping
from .utils import achatar, dinheiro, fmt_brl

CSS = """
<style>
.block-container {padding-top: 1.6rem;}
.pb-hero {background: linear-gradient(90deg,#131921 0%,#232f3e 100%); color:#fff;
          padding: 1.1rem 1.4rem; border-radius: 10px; margin-bottom: 1rem;}
.pb-hero h1 {color:#fff; margin:0; font-size:1.8rem;}
.pb-hero h1 span {color:#ff9900;}
.pb-hero p {margin:.2rem 0 0 0; color:#d5d9d9;}
.pb-img {height: 190px; display:flex; align-items:center; justify-content:center;
         background:#fff; border-radius:6px; overflow:hidden; margin-bottom:.4rem;}
.pb-img img {max-height:190px; max-width:100%; object-fit:contain;}
.pb-thumb img {height:64px; width:64px; object-fit:contain; background:#fff; border-radius:4px;}
.pb-nome {font-weight:600; font-size:.95rem; line-height:1.25; height:2.5em; overflow:hidden;}
.pb-marca {color:#888; font-size:.8rem;}
.pb-estrelas {color:#ff9900; font-size:.9rem;}
.pb-estrelas small {color:#007185;}
.pb-preco {font-size:1.35rem; font-weight:700;}
.pb-de {color:#888; text-decoration:line-through; font-size:.85rem; margin-left:.3rem;}
.pb-off {background:#cc0c39; color:#fff; font-size:.75rem; padding:1px 6px; border-radius:4px;
         margin-left:.3rem;}
.pb-estoque-ok {color:#067d62; font-size:.8rem;}
.pb-estoque-baixo {color:#c45500; font-size:.8rem;}
.pb-estoque-zero {color:#cc0c39; font-size:.8rem;}
</style>
"""


# --------------------------------------------------------------------------- #
# Página
# --------------------------------------------------------------------------- #
@st.cache_resource(show_spinner="Conectando ao MongoDB...")
def _inicializar_banco() -> bool:
    ping()
    init_db()
    return True


def configurar_pagina(titulo: str, icone: str) -> None:
    st.set_page_config(page_title=f"{titulo} · PB Store", page_icon=icone, layout="wide")
    st.markdown(CSS, unsafe_allow_html=True)
    try:
        _inicializar_banco()
    except Exception as exc:
        st.error("Não foi possível conectar ao MongoDB.")
        st.caption(f"Detalhe: {exc}")
        st.markdown("Suba o banco com:")
        st.code("docker compose up -d mongo", language="bash")
        st.markdown("ou ajuste `MONGO_URI` no arquivo `.env`.")
        st.stop()
    if not carrinho_redis.disponivel():  # o carrinho ativo vive no Redis
        st.error("Não foi possível conectar ao Redis (carrinho).")
        st.markdown("Suba o Redis com:")
        st.code("docker compose up -d redis", language="bash")
        st.markdown("ou ajuste `REDIS_URL` no arquivo `.env`.")
        st.stop()
    _resumo_carrinho_sidebar()


def cabecalho(titulo: str = "PB Store", subtitulo: str = "") -> None:
    partes = titulo.split(" ", 1)
    titulo_html = (f"{html.escape(partes[0])} <span>{html.escape(partes[1])}</span>"
                   if len(partes) == 2 else html.escape(titulo))
    st.markdown(f'<div class="pb-hero"><h1>{titulo_html}</h1>'
                f'<p>{html.escape(subtitulo)}</p></div>', unsafe_allow_html=True)


# --------------------------------------------------------------------------- #
# Carrinho (Redis — ver src/carrinho_redis.py)
# --------------------------------------------------------------------------- #
def carrinho() -> dict[str, int]:
    """Cópia do carrinho guardado no Redis. Para alterar, use as funções abaixo."""
    return carrinho_redis.obter()


def adicionar_ao_carrinho(produto: dict, quantidade: int = 1) -> None:
    pid = str(produto["_id"])
    estoque = max(int(produto.get("estoque", 0)), 0)
    atual = carrinho_redis.obter().get(pid, 0)
    carrinho_redis.definir(pid, min(atual + quantidade, estoque))


def remover_do_carrinho(produto_id: str) -> None:
    carrinho_redis.remover(produto_id)


def total_itens_carrinho() -> int:
    return sum(carrinho().values())


def _resumo_carrinho_sidebar() -> None:
    with st.sidebar:
        n = total_itens_carrinho()
        st.markdown(f"### 🛒 Carrinho: **{n}** {'item' if n == 1 else 'itens'}")
        if n:
            st.page_link("pages/1_Carrinho.py", label="Ver carrinho e finalizar", icon="➡️")
        st.divider()


# --------------------------------------------------------------------------- #
# Produto
# --------------------------------------------------------------------------- #
def imagem_principal(p: dict) -> str:
    imagens = p.get("imagens") or [{"url": "https://placehold.co/400x400?text=Sem+imagem"}]
    return next((i["url"] for i in imagens if i.get("principal")), imagens[0]["url"])


def estrelas(media: float, total: int) -> str:
    cheias = int(round(media or 0))
    return (f'<div class="pb-estrelas">{"★" * cheias}{"☆" * (5 - cheias)} '
            f'<small>{(media or 0):.1f} ({total or 0:,})</small></div>').replace(",", ".")


def bloco_preco(p: dict) -> str:
    preco = dinheiro(p["preco"])
    de = p.get("preco_original")
    extra = ""
    if de and dinheiro(de) > preco:
        off = int(round((1 - preco / dinheiro(de)) * 100))
        extra = f'<span class="pb-de">{fmt_brl(de)}</span><span class="pb-off">-{off}%</span>'
    return f'<div class="pb-preco">{fmt_brl(preco)}{extra}</div>'


def bloco_estoque(estoque: int) -> str:
    if estoque <= 0:
        return '<div class="pb-estoque-zero">Indisponível</div>'
    if estoque <= 5:
        return f'<div class="pb-estoque-baixo">Só restam {estoque} em estoque</div>'
    return '<div class="pb-estoque-ok">Em estoque</div>'


def card_produto(p: dict) -> None:
    pid = str(p["_id"])
    av = p.get("avaliacao") or {}
    with st.container(border=True):
        st.markdown(
            f'<div class="pb-img"><img src="{html.escape(imagem_principal(p))}" alt=""></div>'
            f'<div class="pb-nome">{html.escape(p["nome"])}</div>'
            f'<div class="pb-marca">{html.escape(p["marca"])}</div>'
            f'{estrelas(av.get("media", 0), av.get("total", 0))}'
            f'{bloco_preco(p)}{bloco_estoque(int(p.get("estoque", 0)))}',
            unsafe_allow_html=True,
        )
        c1, c2 = st.columns(2)
        if c1.button("Detalhes", key=f"det_{pid}"):
            dialogo_produto(p)
        if c2.button("🛒 Adicionar", key=f"add_{pid}", type="primary",
                     disabled=int(p.get("estoque", 0)) <= 0):
            adicionar_ao_carrinho(p)
            st.toast(f"“{p['nome']}” adicionado ao carrinho", icon="🛒")
            st.rerun()


def documento_para_json(doc: dict) -> dict:
    """Converte o documento BSON em JSON puro para exibição (st.json)."""
    return json.loads(json_util.dumps(doc, json_options=json_util.RELAXED_JSON_OPTIONS))


@st.dialog("Detalhes do produto", width="large")
def dialogo_produto(p: dict) -> None:
    av = p.get("avaliacao") or {}
    col_img, col_info = st.columns([2, 3])
    with col_img:
        st.markdown(f'<div class="pb-img" style="height:280px"><img style="max-height:280px" '
                    f'src="{html.escape(imagem_principal(p))}" alt=""></div>', unsafe_allow_html=True)
        miniaturas = "".join(f'<img src="{html.escape(i["url"])}" title="{html.escape(i.get("alt", ""))}"> '
                             for i in p.get("imagens", []))
        st.markdown(f'<div class="pb-thumb">{miniaturas}</div>', unsafe_allow_html=True)
    with col_info:
        st.subheader(p["nome"])
        st.markdown(f"Marca: **{p['marca']}** · SKU `{p['sku']}`")
        st.markdown(estrelas(av.get("media", 0), av.get("total", 0)) + bloco_preco(p)
                    + bloco_estoque(int(p.get("estoque", 0))), unsafe_allow_html=True)
        st.caption(" › ".join(p.get("categorias", [])))
        if p.get("descricao"):
            st.write(p["descricao"])
        estoque = int(p.get("estoque", 0))
        if estoque > 0:
            qtd = st.number_input("Quantidade", min_value=1, max_value=estoque, value=1,
                                  key=f"dlg_qtd_{p['_id']}")
            if st.button("🛒 Adicionar ao carrinho", type="primary", key=f"dlg_add_{p['_id']}"):
                adicionar_ao_carrinho(p, int(qtd))
                st.rerun()

    st.markdown("#### Especificações técnicas")
    specs = achatar(p.get("especificacoes", {}))
    if specs:
        st.dataframe(pd.DataFrame(specs.items(), columns=["Especificação", "Valor"]),
                     hide_index=True)
    else:
        st.caption("Sem especificações cadastradas.")

    with st.expander("Documento no MongoDB (JSON)"):
        st.json(documento_para_json(p), expanded=False)
