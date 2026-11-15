"""Serviço de checkout/pedidos — orquestra repositório e invalidação de cache."""
from __future__ import annotations

import logging
from typing import Any

from .. import graph
from ..cache import invalidar
from ..repositories import pedidos as pedidos_repo
from .catalogo import PREFIXO as PREFIXO_CATALOGO

log = logging.getLogger(__name__)


def finalizar_compra(**dados: Any) -> dict:
    pedido = pedidos_repo.criar_pedido(**dados)
    invalidar(PREFIXO_CATALOGO)  # estoque mudou
    try:  # o pedido já está no MongoDB: se o Neo4j estiver fora, a compra NÃO falha
        graph.registrar_pedido(pedido)
    except graph.ErroGrafo as exc:
        log.warning("Pedido %s não foi enviado ao grafo: %s", pedido.get("numero"), exc)
    return pedido


def avancar_status(pedido: dict) -> str | None:
    novo = pedidos_repo.proximo_status(pedido["status"])
    if novo:
        pedidos_repo.alterar_status(pedido["_id"], novo, "Atualizado pela loja")
    return novo


def cancelar_pedido(pedido_id: Any) -> None:
    pedido = pedidos_repo.obter(pedido_id)
    pedidos_repo.cancelar(pedido_id)
    invalidar(PREFIXO_CATALOGO)  # estoque devolvido
    if pedido:
        try:
            graph.desfazer_pedido(pedido)
        except graph.ErroGrafo as exc:
            log.warning("Cancelamento do pedido %s não foi enviado ao grafo: %s",
                        pedido.get("numero"), exc)
