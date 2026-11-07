"""Cadastro de produto com especificações em JSON (esquema flexível)."""
import json

import streamlit as st
from pymongo.errors import DuplicateKeyError, WriteError

from src.repositories.produtos import ProdutoInvalido
from src.services import catalogo
from src.ui import configurar_pagina

# Modelos de especificações: mostram que cada tipo de produto tem campos diferentes
MODELOS = {
    "Eletrônicos": {
        "processador": "Intel Core i5-1335U",
        "memoria_ram_gb": 16,
        "armazenamento": {"tipo": "SSD NVMe", "capacidade_gb": 512},
        "tela": {"tamanho_pol": 15.6, "resolucao": "1920x1080", "tipo": "IPS"},
        "conectividade": ["Wi-Fi 6", "Bluetooth 5.2", "USB-C"],
        "garantia_meses": 12,
    },
    "Livros": {
        "autor": "Nome do Autor",
        "editora": "Editora",
        "isbn": "978-85-0000-000-0",
        "paginas": 320,
        "idioma": "Português",
        "formato": "Capa comum",
    },
    "Moda": {
        "tamanhos": ["P", "M", "G", "GG"],
        "cores": ["Preto", "Branco"],
        "material": "100% algodão",
        "genero": "Unissex",
        "instrucoes_lavagem": "Lavar à mão",
    },
    "Casa e Cozinha": {
        "voltagem": "127V",
        "potencia_w": 1200,
        "capacidade_l": 1.5,
        "dimensoes_cm": {"altura": 30, "largura": 20, "profundidade": 25},
        "cor": "Inox",
    },
    "Em branco": {},
}

configurar_pagina("Cadastrar produto", "➕")
st.title("➕ Cadastrar produto")
st.caption("Os campos comuns são validados pelo $jsonSchema da coleção; "
           "as especificações aceitam qualquer JSON (esquema flexível).")

modelo = st.selectbox("Modelo de especificações", list(MODELOS))

with st.form("cadastro", clear_on_submit=False):
    c1, c2, c3 = st.columns([1, 2, 1])
    sku = c1.text_input("SKU *", placeholder="NOTE-ABC-001")
    nome = c2.text_input("Nome *")
    marca = c3.text_input("Marca *")
    descricao = st.text_area("Descrição", height=80)

    c4, c5, c6 = st.columns(3)
    preco = c4.number_input("Preço (R$) *", min_value=0.0, step=10.0, format="%.2f")
    preco_original = c5.number_input("Preço original / “de” (R$)", min_value=0.0,
                                     step=10.0, format="%.2f")
    estoque = c6.number_input("Estoque", min_value=0, step=1, value=10)

    c7, c8 = st.columns(2)
    categorias = c7.text_input("Categorias * (separadas por vírgula)",
                               value="" if modelo == "Em branco" else modelo)
    tags = c8.text_input("Tags (separadas por vírgula)")

    imagens = st.text_area("URLs das imagens * (uma por linha — a primeira é a principal)",
                           placeholder="https://placehold.co/600x600?text=Produto", height=80)
    especificacoes_txt = st.text_area(
        "Especificações (JSON)", value=json.dumps(MODELOS[modelo], indent=2, ensure_ascii=False),
        height=300, key=f"specs_{modelo}",
    )
    salvar = st.form_submit_button("Salvar produto", type="primary")

if salvar:
    try:
        especificacoes = json.loads(especificacoes_txt or "{}")
        if not isinstance(especificacoes, dict):
            raise ValueError("o JSON precisa ser um objeto { ... }")
    except ValueError as exc:
        st.error(f"Especificações inválidas: {exc}")
        st.stop()

    dados = {
        "sku": sku,
        "nome": nome,
        "marca": marca,
        "descricao": descricao,
        "preco": preco,
        "preco_original": preco_original or None,
        "estoque": int(estoque),
        "categorias": [c for c in (x.strip() for x in categorias.split(",")) if c],
        "tags": [t for t in (x.strip() for x in tags.split(",")) if t],
        "imagens": [u.strip() for u in imagens.splitlines() if u.strip()],
        "especificacoes": especificacoes,
    }
    try:
        novo_id = catalogo.cadastrar_produto(dados)
    except ProdutoInvalido as exc:
        st.error(str(exc))
    except DuplicateKeyError:
        st.error(f"Já existe um produto com o SKU “{sku.strip().upper()}”.")
    except WriteError as exc:
        st.error("O MongoDB rejeitou o documento (validação do esquema).")
        st.json(exc.details or {}, expanded=False)
    else:
        st.success(f"Produto cadastrado! _id: `{novo_id}`")
        st.page_link("app.py", label="Ver no catálogo", icon="🛍️")
