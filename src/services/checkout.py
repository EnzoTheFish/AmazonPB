"""Serviço de checkout/pedidos — orquestra repositório e invalidação de cache."""
from __future__ import annotations

from typing import Any

from ..cache import invalidar
from ..repositories import pedidos as pedidos_repo
from .catalogo import PREFIXO as PREFIXO_CATALOGO


def finalizar_compra(**dados: Any) -> dict:
    pedido = pedidos_repo.criar_pedido(**dados)
    invalidar(PREFIXO_CATALOGO)  # estoque mudou
    return pedido


def avancar_status(pedido: dict) -> str | None:
    novo = pedidos_repo.proximo_status(pedido["status"])
    if novo:
        pedidos_repo.alterar_status(pedido["_id"], novo, "Atualizado pela loja")
    return novo


def cancelar_pedido(pedido_id: Any) -> None:
    pedidos_repo.cancelar(pedido_id)
    invalidar(PREFIXO_CATALOGO)  # estoque devolvido
