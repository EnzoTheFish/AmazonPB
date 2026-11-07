"""Repositório de pedidos: cálculo de valores, criação, histórico e status."""
from __future__ import annotations

import secrets
from decimal import Decimal
from typing import Any

from pymongo.database import Database

from ..db import PEDIDOS, STATUS_PEDIDO, get_db
from ..utils import agora, dinheiro, oid, to_d128
from . import clientes as clientes_repo
from . import produtos as produtos_repo

# Regras comerciais (simples, para a aula)
FRETE_PADRAO = Decimal("19.90")
FRETE_GRATIS_ACIMA = Decimal("199.00")
CUPONS = {"PB10": Decimal("0.10"), "BEMVINDO": Decimal("0.05")}

FLUXO_STATUS = ["pendente", "pago", "enviado", "entregue"]


class PedidoInvalido(ValueError):
    pass


class EstoqueInsuficiente(PedidoInvalido):
    pass


def _col(db: Database | None):
    return (db if db is not None else get_db())[PEDIDOS]


def _gerar_numero() -> str:
    return f"PB-{agora():%Y%m%d}-{secrets.token_hex(3).upper()}"


# --------------------------------------------------------------------------- #
# Valores
# --------------------------------------------------------------------------- #
def calcular_valores(itens: list[dict], cupom: str | None = None) -> dict:
    """itens: [{"preco_unitario": Decimal|Decimal128, "quantidade": int}, ...]"""
    subtotal = sum((dinheiro(i["preco_unitario"]) * i["quantidade"] for i in itens), Decimal("0"))
    subtotal = dinheiro(subtotal)
    frete = Decimal("0.00") if subtotal >= FRETE_GRATIS_ACIMA or subtotal == 0 else FRETE_PADRAO

    codigo = (cupom or "").strip().upper()
    percentual = CUPONS.get(codigo)
    desconto = dinheiro(subtotal * percentual) if percentual else Decimal("0.00")

    return {
        "subtotal": subtotal,
        "frete": dinheiro(frete),
        "desconto": desconto,
        "total": dinheiro(subtotal + frete - desconto),
        "cupom": codigo if percentual else None,
    }


# --------------------------------------------------------------------------- #
# Criação
# --------------------------------------------------------------------------- #
def criar_pedido(cliente_nome: str, cliente_email: str, carrinho: dict[str, int],
                 endereco: dict, metodo_pagamento: str, cupom: str | None = None,
                 db: Database | None = None) -> dict:
    """Cria um pedido a partir do carrinho {produto_id: quantidade}.

    * Preços SEMPRE vêm do banco (nunca da tela).
    * Itens, comprador e valores são gravados como snapshot.
    * Estoque é baixado atomicamente; se algo falhar, é devolvido.
      (Com MongoDB em replica set daria para usar transação multi-documento.)
    """
    carrinho = {pid: int(q) for pid, q in carrinho.items() if int(q) > 0}
    if not carrinho:
        raise PedidoInvalido("O carrinho está vazio.")

    produtos = produtos_repo.obter_varios(carrinho.keys(), db=db)
    itens = []
    for pid, qtd in carrinho.items():
        p = produtos.get(pid)
        if not p or not p.get("ativo", True):
            raise PedidoInvalido("Um dos produtos do carrinho não está mais disponível.")
        preco = dinheiro(p["preco"])
        principal = next((i["url"] for i in p["imagens"] if i.get("principal")), p["imagens"][0]["url"])
        itens.append({
            "produto_id": p["_id"],
            "sku": p["sku"],
            "nome": p["nome"],
            "marca": p["marca"],
            "imagem": principal,
            "quantidade": qtd,
            "preco_unitario": preco,
            "subtotal": dinheiro(preco * qtd),
        })

    valores = calcular_valores(itens, cupom)
    cliente = clientes_repo.obter_ou_criar(cliente_nome, cliente_email, db=db)

    # Reserva de estoque (com compensação em caso de falha)
    reservados: list[tuple[Any, int]] = []
    try:
        for item in itens:
            if not produtos_repo.reservar_estoque(item["produto_id"], item["quantidade"], db=db):
                raise EstoqueInsuficiente(f"Estoque insuficiente para “{item['nome']}”.")
            reservados.append((item["produto_id"], item["quantidade"]))

        momento = agora()
        pago = metodo_pagamento in ("pix", "cartao_credito")  # boleto fica pendente
        historico = [{"status": "pendente", "em": momento, "obs": "Pedido criado"}]
        if pago:
            historico.append({"status": "pago", "em": momento,
                              "obs": f"Pagamento aprovado ({metodo_pagamento})"})

        pedido = {
            "numero": _gerar_numero(),
            "cliente": {"id": cliente["_id"], "nome": cliente["nome"], "email": cliente["email"]},
            "itens": [{**i, "preco_unitario": to_d128(i["preco_unitario"]),
                       "subtotal": to_d128(i["subtotal"])} for i in itens],
            "valores": {k: to_d128(valores[k]) for k in ("subtotal", "frete", "desconto", "total")},
            "cupom": valores["cupom"],
            "status": "pago" if pago else "pendente",
            "historico_status": historico,
            "endereco_entrega": endereco,
            "pagamento": {"metodo": metodo_pagamento},
            "criado_em": momento,
            "atualizado_em": momento,
        }
        pedido["_id"] = _col(db).insert_one(pedido).inserted_id
    except Exception:
        for produto_id, qtd in reservados:
            produtos_repo.devolver_estoque(produto_id, qtd, db=db)
        raise

    clientes_repo.registrar_compra(cliente["_id"], valores["total"], db=db)
    return pedido


# --------------------------------------------------------------------------- #
# Consulta / histórico
# --------------------------------------------------------------------------- #
def obter(pedido_id: Any, db: Database | None = None) -> dict | None:
    return _col(db).find_one({"_id": oid(pedido_id)})


def listar_por_cliente(cliente_id: Any, status: str | None = None,
                       db: Database | None = None) -> list[dict]:
    filtro: dict[str, Any] = {"cliente.id": oid(cliente_id)}
    if status:
        filtro["status"] = status
    return list(_col(db).find(filtro).sort("criado_em", -1))


def resumo_cliente(cliente_id: Any, db: Database | None = None) -> dict:
    """Agregação: total de pedidos, total gasto e ticket médio (sem cancelados)."""
    pipeline = [
        {"$match": {"cliente.id": oid(cliente_id), "status": {"$ne": "cancelado"}}},
        {"$group": {
            "_id": None,
            "pedidos": {"$sum": 1},
            "total_gasto": {"$sum": "$valores.total"},
            "ticket_medio": {"$avg": "$valores.total"},
            "itens": {"$sum": {"$sum": "$itens.quantidade"}},
            "primeiro": {"$min": "$criado_em"},
            "ultimo": {"$max": "$criado_em"},
        }},
    ]
    r = next(_col(db).aggregate(pipeline), None)
    if not r:
        return {"pedidos": 0, "total_gasto": Decimal("0"), "ticket_medio": Decimal("0"),
                "itens": 0, "primeiro": None, "ultimo": None}
    return {**r, "total_gasto": dinheiro(r["total_gasto"]),
            "ticket_medio": dinheiro(r["ticket_medio"])}


# --------------------------------------------------------------------------- #
# Status
# --------------------------------------------------------------------------- #
def proximo_status(status: str) -> str | None:
    if status not in FLUXO_STATUS:
        return None
    i = FLUXO_STATUS.index(status)
    return FLUXO_STATUS[i + 1] if i + 1 < len(FLUXO_STATUS) else None


def alterar_status(pedido_id: Any, novo_status: str, obs: str = "",
                   db: Database | None = None) -> None:
    if novo_status not in STATUS_PEDIDO:
        raise PedidoInvalido(f"Status inválido: {novo_status}")
    momento = agora()
    _col(db).update_one(
        {"_id": oid(pedido_id)},
        {"$set": {"status": novo_status, "atualizado_em": momento},
         "$push": {"historico_status": {"status": novo_status, "em": momento, "obs": obs}}},
    )


def cancelar(pedido_id: Any, motivo: str = "Cancelado pelo cliente",
             db: Database | None = None) -> None:
    """Cancela, devolve o estoque e estorna as estatísticas do cliente."""
    pedido = obter(pedido_id, db=db)
    if not pedido:
        raise PedidoInvalido("Pedido não encontrado.")
    if pedido["status"] not in ("pendente", "pago"):
        raise PedidoInvalido("Só é possível cancelar pedidos pendentes ou pagos.")
    alterar_status(pedido_id, "cancelado", motivo, db=db)
    for item in pedido["itens"]:
        produtos_repo.devolver_estoque(item["produto_id"], item["quantidade"], db=db)
    clientes_repo.estornar_compra(pedido["cliente"]["id"], pedido["valores"]["total"], db=db)
