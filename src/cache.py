"""Camada de cache — Redis (cache-aside) com degradação segura.

Como funciona
-------------
* `get_cache()` devolve um `RedisCache` quando `CACHE_BACKEND=redis` e o Redis
  responde; caso contrário devolve um `NullCache` e tudo vai direto ao MongoDB.
  A aplicação nunca cai por causa do cache.
* As consultas de catálogo passam pelo decorator `@cached(...)` e as escritas
  (cadastro de produto, pedido, cancelamento) chamam `invalidar(...)`.
* Se o Redis cair em execução, um "circuit breaker" desativa o cache por alguns
  segundos (evita esperar timeout a cada consulta) e volta a tentar depois.

Ativar
------
1. `pip install -r requirements.txt`
2. No .env: `CACHE_BACKEND=redis` e `REDIS_URL=redis://localhost:6379/0`
3. `docker compose up -d redis`

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
import threading
import time
from abc import ABC, abstractmethod
from functools import wraps
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


_estado = threading.local()


def origem_ultima_consulta() -> str | None:
    """"cache" ou "mongodb" para a última consulta cacheada feita nesta thread
    (cada sessão do Streamlit roda na sua thread). Útil para exibir na tela."""
    return getattr(_estado, "origem", None)


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
    """Backend Redis (redis-py >= 5). Valores serializados com `bson.json_util`."""

    PAUSA_APOS_FALHA = 15  # segundos sem tentar o Redis após um erro (circuit breaker)

    def __init__(self, url: str):
        import redis  # import tardio: só é exigido quando o backend redis é usado

        self._erro = redis.RedisError
        self.r = redis.Redis.from_url(url, socket_timeout=1, socket_connect_timeout=1)
        self.r.ping()  # falha cedo => get_cache() cai para NullCache
        self._pausado_ate = 0.0

    # -- circuit breaker ---------------------------------------------------- #
    def _disponivel(self) -> bool:
        return time.monotonic() >= self._pausado_ate

    def _falhou(self, exc: Exception) -> None:
        self._pausado_ate = time.monotonic() + self.PAUSA_APOS_FALHA
        log.warning("Redis indisponível (%s). Cache pausado por %ss.", exc, self.PAUSA_APOS_FALHA)

    # -- contrato ----------------------------------------------------------- #
    def get(self, chave: str) -> Any | None:
        if not self._disponivel():
            return None
        try:
            bruto = self.r.get(chave)
        except self._erro as exc:
            self._falhou(exc)
            return None
        return desserializar(bruto) if bruto is not None else None

    def set(self, chave: str, valor: Any, ttl: int | None = None) -> None:
        if not self._disponivel():
            return
        try:
            self.r.set(chave, serializar(valor), ex=ttl or settings.cache_ttl_padrao)
        except self._erro as exc:
            self._falhou(exc)

    def delete(self, chave: str) -> None:
        if not self._disponivel():
            return
        try:
            self.r.delete(chave)
        except self._erro as exc:
            self._falhou(exc)

    def invalidar(self, prefixo: str) -> None:
        if not self._disponivel():
            return
        try:
            chaves = list(self.r.scan_iter(match=f"{prefixo}:*", count=500))
            if chaves:
                self.r.delete(*chaves)
        except self._erro as exc:
            self._falhou(exc)


_cache: CacheBackend | None = None
_proxima_tentativa = 0.0
_lock = threading.Lock()
RETENTATIVA_REDIS = 30  # segundos entre tentativas de conexão quando o Redis está fora


def get_cache() -> CacheBackend:
    """Singleton do backend. Se o Redis estava fora na partida, tenta de novo
    a cada `RETENTATIVA_REDIS` segundos (sem precisar reiniciar a aplicação)."""
    global _cache, _proxima_tentativa
    if _cache is not None and not isinstance(_cache, NullCache):
        return _cache
    if settings.cache_backend != "redis":
        _cache = _cache or NullCache()
        return _cache
    with _lock:
        if isinstance(_cache, RedisCache):
            return _cache
        if _cache is None or time.monotonic() >= _proxima_tentativa:
            try:
                _cache = RedisCache(settings.redis_url)
                log.info("Cache Redis conectado em %s", settings.redis_url)
            except Exception as exc:
                log.warning("Cache Redis indisponível (%s). Usando NullCache.", exc)
                _cache = NullCache()
                _proxima_tentativa = time.monotonic() + RETENTATIVA_REDIS
        return _cache


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
                    _estado.origem = "cache"
                    return hit
            except Exception as exc:  # o cache nunca pode derrubar a aplicação
                log.warning("Falha ao ler cache %s: %s", chave, exc)

            resultado = fn(*args, **kwargs)
            _estado.origem = "mongodb"

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
