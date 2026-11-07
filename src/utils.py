"""Funções utilitárias: dinheiro (Decimal128), datas e formatação."""
from datetime import datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Any

from bson import Decimal128, ObjectId

CENTAVOS = Decimal("0.01")
FUSO_BR = timezone(timedelta(hours=-3), "BRT")  # Brasília (sem horário de verão)


# --------------------------------------------------------------------------- #
# Dinheiro
# Valores monetários são gravados no MongoDB como Decimal128 (bsonType
# "decimal") para evitar erros de arredondamento de float.
# --------------------------------------------------------------------------- #
def dinheiro(valor: Any) -> Decimal:
    """Converte qualquer valor numérico (int, float, str, Decimal128) em Decimal com 2 casas."""
    if valor is None:
        return Decimal("0.00")
    if isinstance(valor, Decimal128):
        valor = valor.to_decimal()
    return Decimal(str(valor)).quantize(CENTAVOS, rounding=ROUND_HALF_UP)


def to_d128(valor: Any) -> Decimal128:
    """Converte um valor para Decimal128 (formato de gravação no MongoDB)."""
    return Decimal128(dinheiro(valor))


def fmt_brl(valor: Any) -> str:
    """Formata no padrão brasileiro: R$ 1.234,56"""
    texto = f"{dinheiro(valor):,.2f}"
    return "R$ " + texto.replace(",", "X").replace(".", ",").replace("X", ".")


# --------------------------------------------------------------------------- #
# Datas / ids
# --------------------------------------------------------------------------- #
def agora() -> datetime:
    return datetime.now(timezone.utc)


def fmt_data(dt: datetime | None, com_hora: bool = True) -> str:
    if not dt:
        return "-"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(FUSO_BR)
    return dt.strftime("%d/%m/%Y %H:%M" if com_hora else "%d/%m/%Y")


def oid(valor: Any) -> ObjectId:
    return valor if isinstance(valor, ObjectId) else ObjectId(str(valor))


# --------------------------------------------------------------------------- #
# Especificações (JSON flexível)
# --------------------------------------------------------------------------- #
def achatar(dados: dict, prefixo: str = "") -> dict[str, str]:
    """Achata um dicionário aninhado para exibição em tabela.

    {"tela": {"tamanho": "15.6\"", "tipo": "IPS"}} -> {"tela › tamanho": "15.6\"", "tela › tipo": "IPS"}
    """
    saida: dict[str, str] = {}
    for chave, valor in (dados or {}).items():
        nome = f"{prefixo} › {chave}" if prefixo else str(chave)
        if isinstance(valor, dict):
            saida.update(achatar(valor, nome))
        elif isinstance(valor, (list, tuple)):
            saida[nome] = ", ".join(str(v) for v in valor)
        elif isinstance(valor, bool):
            saida[nome] = "Sim" if valor else "Não"
        else:
            saida[nome] = str(valor)
    return saida
