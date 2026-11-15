"""Configurações da aplicação, lidas de variáveis de ambiente (ou do arquivo .env)."""
import os
from dataclasses import dataclass

try:  # python-dotenv é opcional: se estiver instalado, carrega o .env da raiz
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # pragma: no cover
    pass


@dataclass(frozen=True)
class Settings:
    # MongoDB
    mongo_uri: str = os.getenv("MONGO_URI", "mongodb://localhost:27017")
    mongo_db: str = os.getenv("MONGO_DB", "amazon_pb")

    # Cache (Redis) — "redis" (padrão; se o Redis estiver fora, segue sem cache) ou "none"
    cache_backend: str = os.getenv("CACHE_BACKEND", "redis").lower()
    redis_url: str = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    cache_ttl_padrao: int = int(os.getenv("CACHE_TTL", "300"))  # segundos

    # Carrinho ativo (Redis) — tempo até um carrinho sem alterações expirar
    carrinho_ttl: int = int(os.getenv("CARRINHO_TTL", "7200"))  # segundos (2 horas)

    # Neo4j (grafo de recomendações) — Docker local (bolt://) ou AuraDB (neo4j+s://)
    neo4j_uri: str = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    neo4j_username: str = os.getenv("NEO4J_USERNAME", "neo4j")
    neo4j_password: str = os.getenv("NEO4J_PASSWORD", "pbstore123")
    neo4j_database: str = os.getenv("NEO4J_DATABASE", "neo4j")


settings = Settings()
