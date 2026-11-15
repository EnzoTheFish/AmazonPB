"""Neo4j (grafo) — modelo, carga e recomendações da PB Store.

Modelo do grafo
---------------
Nós
    (:Cliente   {email, nome})
    (:Produto   {produto_id, nome, marca, preco})
    (:Categoria {nome})

Relacionamentos
    (:Cliente)-[:COMPROU {quantidade, ultima_compra}]->(:Produto)
    (:Cliente)-[:AVALIOU {nota}]->(:Produto)              nota de 1 a 5
    (:Produto)-[:PERTENCE_A]->(:Categoria)

`produto_id` é o _id do produto no MongoDB (como texto). É a "ponte" entre os
bancos: o Neo4j diz QUAIS produtos recomendar e o MongoDB entrega os dados
completos (preço, imagem, estoque) para mostrar na tela.

Recomendação por filtragem colaborativa ("clientes parecidos também compraram")
    1. acha os outros clientes que compraram os mesmos produtos que o cliente;
    2. olha o que ESSES clientes compraram e o cliente ainda não tem;
    3. ordena pelos produtos mais comprados entre os clientes parecidos.

Conexão
-------
Variáveis NEO4J_* do .env (Neo4j local no Docker ou AuraDB na nuvem).
Se o Neo4j estiver fora do ar, as funções levantam `ErroGrafo` e a tela mostra
uma mensagem em vez de quebrar.
"""
from __future__ import annotations

import logging
import threading
import time
from datetime import datetime
from typing import Any

from .config import settings

log = logging.getLogger(__name__)

PAUSA_APOS_FALHA = 10  # segundos sem tentar reconectar depois de uma falha


class ErroGrafo(RuntimeError):
    """Neo4j indisponível, credenciais erradas ou consulta com erro."""


# --------------------------------------------------------------------------- #
# Conexão (um driver único, reaproveitado por todas as sessões do Streamlit)
# --------------------------------------------------------------------------- #
_driver: Any = None
_lock = threading.Lock()
_pausado_ate = 0.0
_ultimo_erro = ""


def get_driver() -> Any:
    global _driver, _pausado_ate, _ultimo_erro
    if _driver is not None:
        return _driver
    with _lock:
        if _driver is not None:
            return _driver
        if time.monotonic() < _pausado_ate:  # evita esperar timeout a cada clique
            raise ErroGrafo(_ultimo_erro)
        try:
            from neo4j import GraphDatabase  # import tardio: só quando o grafo é usado
        except ImportError as exc:
            raise ErroGrafo("A biblioteca 'neo4j' não está instalada. "
                            "Rode:  pip install -r requirements.txt") from exc
        driver = None
        try:
            driver = GraphDatabase.driver(
                settings.neo4j_uri,
                auth=(settings.neo4j_username, settings.neo4j_password),
                connection_timeout=5,
            )
            driver.verify_connectivity()
        except Exception as exc:
            if driver is not None:
                driver.close()
            _ultimo_erro = f"Não foi possível conectar ao Neo4j em {settings.neo4j_uri}: {exc}"
            _pausado_ate = time.monotonic() + PAUSA_APOS_FALHA
            log.warning(_ultimo_erro)
            raise ErroGrafo(_ultimo_erro) from exc
        _driver = driver
        return _driver


def disponivel() -> bool:
    try:
        get_driver()
        return True
    except ErroGrafo:
        return False


def fechar() -> None:
    global _driver
    if _driver is not None:
        _driver.close()
        _driver = None


def executar(consulta: str, **parametros: Any) -> list[dict]:
    """Executa um comando Cypher e devolve as linhas como dicionários.

    Os valores entram por parâmetros ($nome), nunca concatenados no texto da
    consulta — isso evita injeção de Cypher e deixa o Neo4j reaproveitar o plano.
    """
    driver = get_driver()
    try:
        registros, _, _ = driver.execute_query(
            consulta, parameters_=parametros, database_=settings.neo4j_database)
    except Exception as exc:
        raise ErroGrafo(f"Erro ao executar a consulta no Neo4j: {exc}") from exc
    return [r.data() for r in registros]


# --------------------------------------------------------------------------- #
# Schema: restrições de unicidade (também criam índice automaticamente)
# --------------------------------------------------------------------------- #
CONSTRAINTS = [
    "CREATE CONSTRAINT cliente_email IF NOT EXISTS "
    "FOR (c:Cliente) REQUIRE c.email IS UNIQUE",
    "CREATE CONSTRAINT produto_id IF NOT EXISTS "
    "FOR (p:Produto) REQUIRE p.produto_id IS UNIQUE",
    "CREATE CONSTRAINT categoria_nome IF NOT EXISTS "
    "FOR (c:Categoria) REQUIRE c.nome IS UNIQUE",
]


def criar_schema() -> None:
    for comando in CONSTRAINTS:
        executar(comando)


def limpar() -> None:
    """Apaga TODOS os nós e relacionamentos (usado pelo seed com --reset)."""
    executar("MATCH (n) DETACH DELETE n")


# --------------------------------------------------------------------------- #
# Escrita (MERGE = "cria se não existir": rodar duas vezes não duplica nada)
# --------------------------------------------------------------------------- #
def carregar_produtos(produtos: list[dict]) -> None:
    """produtos: [{"produto_id", "nome", "marca", "preco", "categorias": [..]}]"""
    if not produtos:
        return
    executar(
        """
        UNWIND $produtos AS item
        MERGE (p:Produto {produto_id: item.produto_id})
        SET p.nome = item.nome, p.marca = item.marca, p.preco = item.preco
        WITH p, item
        UNWIND item.categorias AS nome_categoria
        MERGE (c:Categoria {nome: nome_categoria})
        MERGE (p)-[:PERTENCE_A]->(c)
        """,
        produtos=produtos,
    )


def carregar_compras(compras: list[dict], somar: bool = True) -> None:
    """compras: [{"email", "nome", "produto_id", "quantidade", "data"}]

    somar=True  -> compra repetida do mesmo produto soma a quantidade (uso normal);
    somar=False -> sobrescreve (uso do seed, para poder rodar de novo sem inflar).
    """
    if not compras:
        return
    executar(
        """
        UNWIND $compras AS c
        MERGE (cl:Cliente {email: c.email})
          ON CREATE SET cl.nome = c.nome
        MERGE (p:Produto {produto_id: c.produto_id})
        MERGE (cl)-[r:COMPROU]->(p)
          ON CREATE SET r.quantidade = c.quantidade, r.ultima_compra = c.data
          ON MATCH SET r.ultima_compra = c.data,
                       r.quantidade = CASE WHEN $somar
                                           THEN r.quantidade + c.quantidade
                                           ELSE c.quantidade END
        """,
        compras=compras, somar=somar,
    )


def carregar_avaliacoes(avaliacoes: list[dict]) -> None:
    """avaliacoes: [{"email", "produto_id", "nota"}]  (nota de 1 a 5)"""
    if not avaliacoes:
        return
    executar(
        """
        UNWIND $avaliacoes AS a
        MERGE (cl:Cliente {email: a.email})
        MERGE (p:Produto {produto_id: a.produto_id})
        MERGE (cl)-[r:AVALIOU]->(p)
        SET r.nota = a.nota
        """,
        avaliacoes=avaliacoes,
    )


def registrar_pedido(pedido: dict) -> None:
    """Grava no grafo as compras de um pedido recém-criado no MongoDB.

    Chamar no checkout, logo depois de gravar o pedido:
        graph.registrar_pedido(pedido)
    """
    cliente = pedido["cliente"]
    data = (pedido.get("criado_em") or datetime.now()).isoformat()
    carregar_compras([
        {"email": cliente["email"], "nome": cliente["nome"],
         "produto_id": str(item["produto_id"]), "quantidade": int(item["quantidade"]),
         "data": data}
        for item in pedido["itens"]
    ], somar=True)


def registrar_avaliacao(email: str, produto_id: str, nota: int) -> None:
    if not 1 <= int(nota) <= 5:
        raise ValueError("A nota deve estar entre 1 e 5.")
    carregar_avaliacoes([{"email": email, "produto_id": str(produto_id), "nota": int(nota)}])


# --------------------------------------------------------------------------- #
# Leitura
# --------------------------------------------------------------------------- #
def estatisticas() -> dict:
    linhas = executar(
        """
        MATCH (c:Cliente) WITH count(c) AS clientes
        MATCH (p:Produto) WITH clientes, count(p) AS produtos
        MATCH (k:Categoria) WITH clientes, produtos, count(k) AS categorias
        OPTIONAL MATCH ()-[r:COMPROU]->() WITH clientes, produtos, categorias, count(r) AS compras
        OPTIONAL MATCH ()-[a:AVALIOU]->()
        RETURN clientes, produtos, categorias, compras, count(a) AS avaliacoes
        """
    )
    return linhas[0] if linhas else {"clientes": 0, "produtos": 0, "categorias": 0,
                                     "compras": 0, "avaliacoes": 0}


def listar_clientes() -> list[dict]:
    return executar("MATCH (c:Cliente) RETURN c.email AS email, c.nome AS nome ORDER BY nome")


def historico_cliente(email: str) -> list[dict]:
    """Produtos que o cliente comprou, com a nota que ele deu (se avaliou)."""
    return executar(
        """
        MATCH (:Cliente {email: $email})-[r:COMPROU]->(p:Produto)
        OPTIONAL MATCH (:Cliente {email: $email})-[a:AVALIOU]->(p)
        RETURN p.produto_id AS produto_id, p.nome AS nome,
               r.quantidade AS quantidade, a.nota AS nota
        ORDER BY nome
        """,
        email=email,
    )


# --------------------------------------------------------------------------- #
# Recomendações (Cypher)
# --------------------------------------------------------------------------- #
CYPHER_COMPROU = """
// Quem comprou o mesmo que eu também comprou...
MATCH (eu:Cliente {email: $email})-[:COMPROU]->(p:Produto)<-[:COMPROU]-(outro:Cliente)
WHERE outro <> eu
WITH eu, outro, count(DISTINCT p) AS em_comum          // quantos produtos temos em comum
MATCH (outro)-[:COMPROU]->(rec:Produto)
WHERE NOT (eu)-[:COMPROU]->(rec)                        // só o que eu ainda não comprei
WITH rec, count(DISTINCT outro) AS clientes_similares, sum(em_comum) AS afinidade
RETURN rec.produto_id AS produto_id, rec.nome AS nome, clientes_similares, afinidade
ORDER BY clientes_similares DESC, afinidade DESC, nome
LIMIT $limite
"""

CYPHER_AVALIOU = """
// Quem avaliou parecido comigo também gostou...
MATCH (eu:Cliente {email: $email})-[r1:AVALIOU]->(p:Produto)<-[r2:AVALIOU]-(outro:Cliente)
WHERE outro <> eu AND abs(r1.nota - r2.nota) <= 1      // notas parecidas = gosto parecido
WITH eu, outro, count(DISTINCT p) AS em_comum
MATCH (outro)-[r3:AVALIOU]->(rec:Produto)
WHERE r3.nota >= 4                                      // só o que eles realmente gostaram
  AND NOT (eu)-[:AVALIOU]->(rec) AND NOT (eu)-[:COMPROU]->(rec)
WITH rec, count(DISTINCT outro) AS clientes_similares, sum(em_comum) AS afinidade,
     avg(r3.nota) AS nota_media
RETURN rec.produto_id AS produto_id, rec.nome AS nome, clientes_similares, afinidade,
       round(nota_media, 1) AS nota_media
ORDER BY clientes_similares DESC, afinidade DESC, nome
LIMIT $limite
"""

CYPHER_RECOMENDACAO = {"compras": CYPHER_COMPROU, "avaliacoes": CYPHER_AVALIOU}

_CYPHER_EXPLICAR_COMPROU = """
MATCH (eu:Cliente {email: $email})-[:COMPROU]->(p:Produto)<-[:COMPROU]-(outro:Cliente)
      -[:COMPROU]->(:Produto {produto_id: $produto_id})
WHERE outro <> eu
RETURN outro.nome AS cliente, collect(DISTINCT p.nome) AS em_comum
ORDER BY size(em_comum) DESC
LIMIT 5
"""

_CYPHER_EXPLICAR_AVALIOU = """
MATCH (eu:Cliente {email: $email})-[r1:AVALIOU]->(p:Produto)<-[r2:AVALIOU]-(outro:Cliente)
      -[r3:AVALIOU]->(:Produto {produto_id: $produto_id})
WHERE outro <> eu AND abs(r1.nota - r2.nota) <= 1 AND r3.nota >= 4
RETURN outro.nome AS cliente, collect(DISTINCT p.nome) AS em_comum
ORDER BY size(em_comum) DESC
LIMIT 5
"""

_CYPHER_EXPLICAR = {"compras": _CYPHER_EXPLICAR_COMPROU, "avaliacoes": _CYPHER_EXPLICAR_AVALIOU}


def recomendar(email: str, estrategia: str = "compras", limite: int = 8) -> list[dict]:
    """Produtos recomendados para o cliente.

    estrategia: "compras" (COMPROU) ou "avaliacoes" (AVALIOU).
    Cada item: {"produto_id", "nome", "clientes_similares", "afinidade", ...}
    """
    if estrategia not in CYPHER_RECOMENDACAO:
        raise ValueError(f"Estratégia desconhecida: {estrategia!r}")
    return executar(CYPHER_RECOMENDACAO[estrategia], email=email, limite=int(limite))


def explicar(email: str, produto_id: str, estrategia: str = "compras") -> list[dict]:
    """Quais clientes parecidos levaram este produto e o que têm em comum com o cliente."""
    return executar(_CYPHER_EXPLICAR[estrategia], email=email, produto_id=str(produto_id))
