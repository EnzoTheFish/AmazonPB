"""Verifica se o servidor MongoDB configurado está acessível (usado pelo popular_banco.bat)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from pymongo import MongoClient  # noqa: E402
from pymongo.errors import PyMongoError  # noqa: E402

from src.config import settings  # noqa: E402

try:
    MongoClient(settings.mongo_uri, serverSelectionTimeoutMS=4000).admin.command("ping")
except PyMongoError:
    print(f"      ERRO: nenhum servidor MongoDB respondendo em {settings.mongo_uri}")
    sys.exit(1)
print(f"      OK: MongoDB acessível em {settings.mongo_uri}")
