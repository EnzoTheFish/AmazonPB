"""Repositório de clientes (compradores)."""
from __future__ import annotations

from typing import Any

from bson import Decimal128
from pymongo import ReturnDocument
from pymongo.database import Database

from ..db import CLIENTES, get_db
from ..utils import agora, oid, to_d128


def _col(db: Database | None):
    return (db if db is not None else get_db())[CLIENTES]


def normalizar_email(email: str) -> str:
    return (email or "").strip().lower()


def obter_por_email(email: str, db: Database | None = None) -> dict | None:
    return _col(db).find_one({"email": normalizar_email(email)})


def obter_ou_criar(nome: str, email: str, db: Database | None = None) -> dict:
    """Upsert pelo e-mail: cria o cliente na primeira compra."""
    momento = agora()
    return _col(db).find_one_and_update(
        {"email": normalizar_email(email)},
        {
            "$set": {"nome": nome.strip(), "atualizado_em": momento},
            "$setOnInsert": {
                "email": normalizar_email(email),
                "criado_em": momento,
                "estatisticas": {"total_pedidos": 0, "total_gasto": Decimal128("0.00")},
            },
        },
        upsert=True,
        return_document=ReturnDocument.AFTER,
    )


def registrar_compra(cliente_id: Any, total: Any, db: Database | None = None) -> None:
    """Atualiza as estatísticas acumuladas do comprador."""
    _col(db).update_one(
        {"_id": oid(cliente_id)},
        {
            "$inc": {"estatisticas.total_pedidos": 1, "estatisticas.total_gasto": to_d128(total)},
            "$set": {"estatisticas.ultimo_pedido_em": agora()},
        },
    )


def estornar_compra(cliente_id: Any, total: Any, db: Database | None = None) -> None:
    _col(db).update_one(
        {"_id": oid(cliente_id)},
        {"$inc": {"estatisticas.total_pedidos": -1,
                  "estatisticas.total_gasto": Decimal128(-to_d128(total).to_decimal())}},
    )


def listar(limite: int = 50, db: Database | None = None) -> list[dict]:
    return list(_col(db).find({}, {"nome": 1, "email": 1}).sort("nome", 1).limit(limite))
