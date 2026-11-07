"""Serviço de catálogo — leituras passam pelo cache (hoje NullCache, amanhã Redis)."""
from __future__ import annotations

from typing import Any

from ..cache import cached, invalidar
from ..repositories import produtos as produtos_repo

PREFIXO = "catalogo"


@cached(f"{PREFIXO}:busca", ttl=120)
def buscar_produtos(**filtros: Any) -> dict:
    """Ver `produtos_repo.buscar` para os filtros aceitos."""
    return produtos_repo.buscar(**filtros)


@cached(f"{PREFIXO}:facetas", ttl=600)
def obter_facetas() -> dict:
    return produtos_repo.facetas()


@cached(f"{PREFIXO}:produto", ttl=300)
def obter_produto(produto_id: str) -> dict | None:
    return produtos_repo.obter(produto_id)


def obter_produtos(ids: list[str]) -> dict[str, dict]:
    # Usado no carrinho: precisa de preço/estoque atualizados, então não usa cache.
    return produtos_repo.obter_varios(ids)


def cadastrar_produto(dados: dict) -> str:
    novo_id = produtos_repo.inserir(dados)
    invalidar(PREFIXO)  # catálogo mudou => limpa buscas/facetas em cache
    return str(novo_id)
