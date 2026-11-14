"""Carrinho ativo no Redis — um hash por sessão: cart:<sessao_id> (produto_id -> quantidade).

Comandos do Redis usados (todos O(1) por item):
    HINCRBY / HSET   adicionar ou alterar a quantidade
    HDEL             remover um item
    HGETALL          listar os itens
    DEL              limpar o carrinho (após o checkout)
    EXPIRE / TTL     o carrinho expira sozinho: o prazo é renovado a cada alteração

Só ids e quantidades ficam no Redis; preço e estoque vêm sempre do MongoDB
(o checkout nunca confia em valores vindos da tela).

Convenção de chaves (o catálogo usa o prefixo "catalogo:", então não há colisão):
    cart:<sessao_id>
"""
from __future__ import annotations

import uuid

import redis
import streamlit as st

from .config import settings

PREFIXO = "cart"

_cliente: redis.Redis | None = None


def _redis() -> redis.Redis:
    global _cliente
    if _cliente is None:
        _cliente = redis.Redis.from_url(settings.redis_url, decode_responses=True,
                                        socket_timeout=2, socket_connect_timeout=2)
    return _cliente


def disponivel() -> bool:
    """True se o Redis responde (usado para avisar na tela em vez de quebrar)."""
    try:
        return bool(_redis().ping())
    except redis.RedisError:
        return False


def sessao_id() -> str:
    """Identifica o carrinho desta sessão do Streamlit."""
    if "sessao_id" not in st.session_state:
        st.session_state["sessao_id"] = uuid.uuid4().hex
    return st.session_state["sessao_id"]


def _chave() -> str:
    return f"{PREFIXO}:{sessao_id()}"


def obter() -> dict[str, int]:
    """Itens do carrinho: {produto_id: quantidade}."""
    return {pid: int(qtd) for pid, qtd in _redis().hgetall(_chave()).items()}


def definir(produto_id: str, quantidade: int) -> None:
    """Grava a quantidade de um item (0 ou menos remove) e renova o TTL."""
    if quantidade <= 0:
        remover(produto_id)
        return
    pipe = _redis().pipeline()
    pipe.hset(_chave(), str(produto_id), int(quantidade))
    pipe.expire(_chave(), settings.carrinho_ttl)
    pipe.execute()


def remover(produto_id: str) -> None:
    _redis().hdel(_chave(), str(produto_id))


def limpar() -> None:
    """Esvazia o carrinho (chamado após o pedido ser gravado no MongoDB)."""
    _redis().delete(_chave())


def ttl_restante() -> int:
    """Segundos até o carrinho expirar (-2 se não existir)."""
    return int(_redis().ttl(_chave()))
