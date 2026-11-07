"""Camada de cache — PREPARADA para Redis, ainda NÃO implementada.

Como está hoje
--------------
* `get_cache()` devolve um `NullCache` (não guarda nada), então toda leitura
  vai direto ao MongoDB. A aplicação funciona normalmente sem Redis.
* As consultas de catálogo já passam pelo decorator `@cached(...)` e as
  escritas já chamam `invalidar(...)`. Ou seja: os pontos de leitura,
  gravação e invalidação já estão no lugar certo.

Para ativar o Redis no futuro
-----------------------------
1. `pip install redis`  (e descomentar no requirements.txt)
2. Implementar os métodos de `RedisCache` (há um exemplo comentado abaixo).
3. No .env: `CACHE_BACKEND=redis` e `REDIS_URL=redis://localhost:6379/0`
4. `docker compose --profile cache up -d redis`

Convenção de chaves
-------------------
    catalogo:busca:<hash>     resultados de busca (texto + filtros + página)
    catalogo:facetas:<hash>   categorias, marcas e faixa de preço
    catalogo:produto:<hash>   documento de um produto
Invalidar o prefixo "catalogo" limpa tudo isso de uma vez (ex.: após cadastrar
produto ou baixar estoque em um pedido).
"""
from __future__ import annotations

import hashlib
import json
import logging
from abc import ABC, abstractmethod
from functools import lru_cache, wraps
from typing import Any, Callable

from bson import json_util

from .config import settings

log = logging.getLogger(__name__)


# --------------------------------------------------------------------------- #
# Serialização — documentos do Mongo têm ObjectId, Decimal128 e datetime,
# que o json padrão não entende. O json_util do BSON resolve isso.
# --------------------------------------------------------------------------- #
def serializar(valor: Any) -> str:
    return json_util.dumps(valor)


def desserializar(texto: str | bytes) -> Any:
    return json_util.loads(texto)


def gerar_chave(prefixo: str, *args: Any, **kwargs: Any) -> str:
    """Chave determinística: mesmos parâmetros => mesma chave."""
    payload = json.dumps([args, kwargs], sort_keys=True, default=str, ensure_ascii=False)
    return f"{prefixo}:{hashlib.sha1(payload.encode()).hexdigest()[:16]}"


# --------------------------------------------------------------------------- #
# Contrato
# --------------------------------------------------------------------------- #
class CacheBackend(ABC):
    @abstractmethod
    def get(self, chave: str) -> Any | None: ...

    @abstractmethod
    def set(self, chave: str, valor: Any, ttl: int | None = None) -> None: ...

    @abstractmethod
    def delete(self, chave: str) -> None: ...

    @abstractmethod
    def invalidar(self, prefixo: str) -> None:
        """Remove todas as chaves que começam com `prefixo`."""


class NullCache(CacheBackend):
    """Cache que não guarda nada (padrão enquanto o Redis não é implementado)."""

    def get(self, chave: str) -> Any | None:
        return None

    def set(self, chave: str, valor: Any, ttl: int | None = None) -> None:
        pass

    def delete(self, chave: str) -> None:
        pass

    def invalidar(self, prefixo: str) -> None:
        pass


class RedisCache(CacheBackend):
    """Backend Redis — TODO: implementar quando o cache entrar no escopo.

    Exemplo de implementação (redis-py >= 5):

        import redis

        def __init__(self, url: str):
            self.r = redis.Redis.from_url(url, socket_timeout=1)
            self.r.ping()

        def get(self, chave):
            bruto = self.r.get(chave)
            return desserializar(bruto) if bruto is not None else None

        def set(self, chave, valor, ttl=None):
            self.r.set(chave, serializar(valor), ex=ttl or settings.cache_ttl_padrao)

        def delete(self, chave):
            self.r.delete(chave)

        def invalidar(self, prefixo):
            for k in self.r.scan_iter(match=f"{prefixo}:*", count=500):
                self.r.delete(k)
    """

    def __init__(self, url: str):
        raise NotImplementedError("RedisCache ainda não foi implementado (fora do escopo atual).")

    def get(self, chave: str) -> Any | None:  # pragma: no cover
        raise NotImplementedError

    def set(self, chave: str, valor: Any, ttl: int | None = None) -> None:  # pragma: no cover
        raise NotImplementedError

    def delete(self, chave: str) -> None:  # pragma: no cover
        raise NotImplementedError

    def invalidar(self, prefixo: str) -> None:  # pragma: no cover
        raise NotImplementedError


@lru_cache(maxsize=1)
def get_cache() -> CacheBackend:
    if settings.cache_backend == "redis":
        try:
            return RedisCache(settings.redis_url)
        except Exception as exc:  # NotImplementedError hoje; falha de conexão amanhã
            log.warning("Cache Redis indisponível (%s). Usando NullCache.", exc)
    return NullCache()


# --------------------------------------------------------------------------- #
# Decorator
# --------------------------------------------------------------------------- #
def cached(prefixo: str, ttl: int | None = None) -> Callable:
    """Cache-aside: tenta o cache; se não achar, executa a função e grava.

    @cached("catalogo:busca", ttl=120)
    def buscar_produtos(...): ...
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            cache = get_cache()
            chave = gerar_chave(prefixo, *args, **kwargs)
            try:
                hit = cache.get(chave)
                if hit is not None:
                    return hit
            except Exception as exc:  # o cache nunca pode derrubar a aplicação
                log.warning("Falha ao ler cache %s: %s", chave, exc)

            resultado = fn(*args, **kwargs)

            try:
                cache.set(chave, resultado, ttl or settings.cache_ttl_padrao)
            except Exception as exc:
                log.warning("Falha ao gravar cache %s: %s", chave, exc)
            return resultado

        wrapper.prefixo_cache = prefixo  # type: ignore[attr-defined]
        return wrapper

    return decorator


def invalidar(prefixo: str) -> None:
    try:
        get_cache().invalidar(prefixo)
    except Exception as exc:
        log.warning("Falha ao invalidar cache %s: %s", prefixo, exc)
