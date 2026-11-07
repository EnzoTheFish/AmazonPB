"""Repositório de produtos: busca textual, filtros, facetas e estoque."""
from __future__ import annotations

import re
from typing import Any, Iterable

from bson import ObjectId
from pymongo.database import Database

from ..db import PRODUTOS, get_db
from ..utils import agora, dinheiro, oid, to_d128

# Ordenações disponíveis na tela de catálogo
ORDENACOES: dict[str, list[tuple[str, int]] | None] = {
    "Relevância": None,
    "Menor preço": [("preco", 1)],
    "Maior preço": [("preco", -1)],
    "Mais bem avaliados": [("avaliacao.media", -1), ("avaliacao.total", -1)],
    "Novidades": [("criado_em", -1)],
}


class ProdutoInvalido(ValueError):
    pass


def _col(db: Database | None):
    return (db if db is not None else get_db())[PRODUTOS]


# --------------------------------------------------------------------------- #
# Busca
# --------------------------------------------------------------------------- #
def _filtro_base(categoria: str | None, marcas: Iterable[str] | None,
                 preco_min: float | None, preco_max: float | None,
                 avaliacao_min: float | None) -> dict:
    filtro: dict[str, Any] = {"ativo": True}
    if categoria:
        filtro["categorias"] = categoria  # casa com qualquer item do array
    if marcas:
        filtro["marca"] = {"$in": list(marcas)}
    faixa: dict[str, Any] = {}
    if preco_min is not None:
        faixa["$gte"] = to_d128(preco_min)
    if preco_max is not None:
        faixa["$lte"] = to_d128(preco_max)
    if faixa:
        filtro["preco"] = faixa
    if avaliacao_min:
        filtro["avaliacao.media"] = {"$gte": float(avaliacao_min)}
    return filtro


def _executar(filtro: dict, ordenacao: str, pagina: int, por_pagina: int,
              com_score: bool, db: Database | None) -> dict:
    pipeline: list[dict] = [{"$match": filtro}]
    ordem = ORDENACOES.get(ordenacao)
    if com_score:
        pipeline.append({"$addFields": {"_score": {"$meta": "textScore"}}})
        if ordem is None:
            ordem = [("_score", -1)]
    if ordem is None:  # "Relevância" sem texto = mais populares
        ordem = [("avaliacao.total", -1)]
    sort = dict(ordem)
    sort.setdefault("_id", 1)  # desempate estável para a paginação
    pipeline.append({"$sort": sort})
    pipeline.append({
        "$facet": {
            "itens": [{"$skip": max(pagina - 1, 0) * por_pagina}, {"$limit": por_pagina}],
            "total": [{"$count": "n"}],
        }
    })
    resultado = next(_col(db).aggregate(pipeline), {"itens": [], "total": []})
    total = resultado["total"][0]["n"] if resultado["total"] else 0
    return {"itens": resultado["itens"], "total": total}


def buscar(texto: str = "", categoria: str | None = None,
           marcas: Iterable[str] | None = None, preco_min: float | None = None,
           preco_max: float | None = None, avaliacao_min: float | None = None,
           ordenacao: str = "Relevância", pagina: int = 1, por_pagina: int = 12,
           db: Database | None = None) -> dict:
    """Busca produtos no catálogo.

    1. Com texto: usa o índice de texto ($text) do MongoDB (stemming em
       português, pesos por campo e ordenação por relevância).
    2. Se o $text não achar nada (ex.: palavra parcial "note"), cai para uma
       busca por regex em nome/marca/categorias/tags.
    3. Sem texto: só filtros.

    Retorna {"itens": [...], "total": int, "modo": "texto"|"parcial"|"filtro"}
    """
    base = _filtro_base(categoria, marcas, preco_min, preco_max, avaliacao_min)
    texto = (texto or "").strip()

    if texto:
        res = _executar({"$text": {"$search": texto}, **base}, ordenacao,
                        pagina, por_pagina, com_score=True, db=db)
        if res["total"]:
            return {**res, "modo": "texto"}

        regex = {"$regex": re.escape(texto), "$options": "i"}
        filtro = {**base, "$or": [{"nome": regex}, {"marca": regex},
                                  {"categorias": regex}, {"tags": regex}]}
        res = _executar(filtro, ordenacao, pagina, por_pagina, com_score=False, db=db)
        return {**res, "modo": "parcial"}

    res = _executar(base, ordenacao, pagina, por_pagina, com_score=False, db=db)
    return {**res, "modo": "filtro"}


def facetas(db: Database | None = None) -> dict:
    """Categorias e marcas (com contagem) e faixa de preço do catálogo ativo."""
    pipeline = [
        {"$match": {"ativo": True}},
        {"$facet": {
            "categorias": [
                {"$unwind": "$categorias"},
                {"$group": {"_id": "$categorias", "n": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ],
            "marcas": [
                {"$group": {"_id": "$marca", "n": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
            ],
            "precos": [
                {"$group": {"_id": None, "min": {"$min": "$preco"}, "max": {"$max": "$preco"}}},
            ],
        }},
    ]
    r = next(_col(db).aggregate(pipeline), None) or {"categorias": [], "marcas": [], "precos": []}
    precos = r["precos"][0] if r["precos"] else {"min": 0, "max": 0}
    return {
        "categorias": [(c["_id"], c["n"]) for c in r["categorias"]],
        "marcas": [(m["_id"], m["n"]) for m in r["marcas"]],
        "preco_min": precos["min"],
        "preco_max": precos["max"],
    }


# --------------------------------------------------------------------------- #
# Leitura por id
# --------------------------------------------------------------------------- #
def obter(produto_id: Any, db: Database | None = None) -> dict | None:
    return _col(db).find_one({"_id": oid(produto_id)})


def obter_varios(ids: Iterable[Any], db: Database | None = None) -> dict[str, dict]:
    """Retorna {id_str: documento} para os ids informados."""
    ids_oid = [oid(i) for i in ids]
    if not ids_oid:
        return {}
    return {str(p["_id"]): p for p in _col(db).find({"_id": {"$in": ids_oid}})}


# --------------------------------------------------------------------------- #
# Escrita
# --------------------------------------------------------------------------- #
def preparar(dados: dict) -> dict:
    """Valida os campos comuns e monta o documento no formato do banco.

    `especificacoes` é livre: qualquer dicionário JSON é aceito.
    Campos extras desconhecidos também são preservados (esquema flexível).
    """
    obrigatorios = ["sku", "nome", "marca", "categorias", "preco", "imagens"]
    faltando = [c for c in obrigatorios if not dados.get(c)]
    if faltando:
        raise ProdutoInvalido(f"Campos obrigatórios ausentes: {', '.join(faltando)}")

    especificacoes = dados.get("especificacoes") or {}
    if not isinstance(especificacoes, dict):
        raise ProdutoInvalido("`especificacoes` deve ser um objeto JSON (chave: valor).")

    imagens = []
    for i, img in enumerate(dados["imagens"]):
        if isinstance(img, str):
            img = {"url": img}
        imagens.append({"url": img["url"], "alt": img.get("alt", dados["nome"]),
                        "principal": bool(img.get("principal", i == 0))})

    preco = dinheiro(dados["preco"])
    if preco <= 0:
        raise ProdutoInvalido("O preço deve ser maior que zero.")
    preco_original = dados.get("preco_original")
    preco_original = to_d128(preco_original) if preco_original and dinheiro(preco_original) > preco else None

    momento = agora()
    doc = {k: v for k, v in dados.items() if k not in {"_id"}}  # preserva extras
    doc.update({
        "sku": str(dados["sku"]).strip().upper(),
        "nome": str(dados["nome"]).strip(),
        "descricao": str(dados.get("descricao", "")).strip(),
        "marca": str(dados["marca"]).strip(),
        "categorias": [c.strip() for c in dados["categorias"] if str(c).strip()],
        "tags": [t.strip().lower() for t in dados.get("tags", []) if str(t).strip()],
        "preco": to_d128(preco),
        "preco_original": preco_original,
        "moeda": "BRL",
        "estoque": int(dados.get("estoque", 0)),
        "imagens": imagens,
        "especificacoes": especificacoes,
        "avaliacao": dados.get("avaliacao") or {"media": 0.0, "total": 0},
        "ativo": bool(dados.get("ativo", True)),
        "criado_em": dados.get("criado_em", momento),
        "atualizado_em": momento,
    })
    return doc


def inserir(dados: dict, db: Database | None = None) -> ObjectId:
    return _col(db).insert_one(preparar(dados)).inserted_id


def reservar_estoque(produto_id: Any, quantidade: int, db: Database | None = None) -> bool:
    """Baixa o estoque de forma atômica, apenas se houver quantidade suficiente."""
    r = _col(db).update_one(
        {"_id": oid(produto_id), "ativo": True, "estoque": {"$gte": quantidade}},
        {"$inc": {"estoque": -quantidade}, "$set": {"atualizado_em": agora()}},
    )
    return r.modified_count == 1


def devolver_estoque(produto_id: Any, quantidade: int, db: Database | None = None) -> None:
    _col(db).update_one(
        {"_id": oid(produto_id)},
        {"$inc": {"estoque": quantidade}, "$set": {"atualizado_em": agora()}},
    )
