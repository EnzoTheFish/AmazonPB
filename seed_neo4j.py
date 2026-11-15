"""Carga inicial do Neo4j (grafo de recomendações).

Uso (com o MongoDB já populado por `python -m scripts.seed`):

    python -m scripts.seed_neo4j --reset          # apaga o grafo e recarrega tudo
    python -m scripts.seed_neo4j --reset --demo 20   # com 20 clientes de exemplo
    python -m scripts.seed_neo4j --demo 0         # só os dados reais do MongoDB

O que o script faz
    1. cria as restrições de unicidade (schema);
    2. copia os produtos do MongoDB       -> nós (:Produto) e (:Categoria);
    3. copia os pedidos do MongoDB        -> nós (:Cliente) e [:COMPROU];
    4. gera avaliações de exemplo         -> [:AVALIOU] (nota 1 a 5);
    5. cria N clientes de exemplo ("demo") só no grafo, com gostos parecidos
       entre si, para que as recomendações tenham de onde sair. Os 3 clientes
       reais do seed têm poucos pedidos, então sem isso quase nada seria
       recomendado.

Os dados são gerados com semente fixa (42): rodar de novo dá os mesmos clientes,
compras e notas (só as datas relativas a "hoje" mudam).
"""
from __future__ import annotations

import argparse
import random
from datetime import datetime, timedelta

from src import graph
from src.db import CLIENTES, PEDIDOS, PRODUTOS, get_db
from src.utils import dinheiro

NOMES_DEMO = [
    "Daniela Rocha", "Eduardo Alves", "Fernanda Costa", "Gabriel Martins", "Helena Dias",
    "Igor Santos", "Juliana Pires", "Kleber Nunes", "Larissa Gomes", "Marcos Teixeira",
    "Natália Ribeiro", "Otávio Freitas", "Patrícia Moura", "Rafael Barros", "Sabrina Lopes",
    "Thiago Cardoso", "Úrsula Melo", "Vinícius Araújo", "Wesley Campos", "Yasmin Correia",
]
PESOS_NOTA = {1: 5, 2: 5, 3: 15, 4: 35, 5: 40}  # a maioria das notas é alta (4 e 5)
CHANCE_AVALIAR = 0.75  # probabilidade de um cliente avaliar o que comprou


# --------------------------------------------------------------------------- #
# Leitura do MongoDB
# --------------------------------------------------------------------------- #
def ler_produtos(db) -> list[dict]:
    return [{
        "produto_id": str(p["_id"]),
        "nome": p["nome"],
        "marca": p.get("marca"),
        "preco": float(dinheiro(p["preco"])),
        "categorias": list(p.get("categorias") or []),
    } for p in db[PRODUTOS].find({"ativo": {"$ne": False}})]


def ler_compras(db) -> list[dict]:
    """Uma linha por (cliente, produto) comprado, somando pedidos repetidos."""
    agrupado: dict[tuple[str, str], dict] = {}
    for pedido in db[PEDIDOS].find({"status": {"$ne": "cancelado"}}):
        cliente = pedido["cliente"]
        data = pedido.get("criado_em") or datetime.now()
        for item in pedido["itens"]:
            chave = (cliente["email"], str(item["produto_id"]))
            linha = agrupado.setdefault(chave, {
                "email": cliente["email"], "nome": cliente["nome"],
                "produto_id": chave[1], "quantidade": 0, "data": data.isoformat()})
            linha["quantidade"] += int(item["quantidade"])
    return list(agrupado.values())


# --------------------------------------------------------------------------- #
# Geração de dados de exemplo (funções puras: não acessam nenhum banco)
# --------------------------------------------------------------------------- #
def gerar_avaliacoes(compras: list[dict], rng: random.Random) -> list[dict]:
    notas, pesos = list(PESOS_NOTA), list(PESOS_NOTA.values())
    return [{"email": c["email"], "produto_id": c["produto_id"],
             "nota": rng.choices(notas, weights=pesos)[0]}
            for c in compras if rng.random() < CHANCE_AVALIAR]


def gerar_clientes_demo(produtos: list[dict], compras_reais: list[dict], quantidade: int,
                        rng: random.Random) -> list[dict]:
    """Cada cliente demo tem uma categoria "favorita" e compra principalmente nela.

    Também compra 1 ou 2 produtos que os clientes reais compraram: é isso que
    cria as ligações entre clientes reais e de exemplo no grafo.
    """
    por_categoria: dict[str, list[str]] = {}
    for p in produtos:
        if p["categorias"]:
            por_categoria.setdefault(p["categorias"][0], []).append(p["produto_id"])
    categorias = sorted(c for c, ids in por_categoria.items() if len(ids) >= 3)
    ancoras = sorted({c["produto_id"] for c in compras_reais}) or [p["produto_id"] for p in produtos]
    if not categorias or not ancoras:
        return []

    agora = datetime.now()
    compras: list[dict] = []
    for i in range(quantidade):
        nome = NOMES_DEMO[i % len(NOMES_DEMO)] + ("" if i < len(NOMES_DEMO) else f" {i // len(NOMES_DEMO) + 1}")
        email = f"demo{i + 1:02d}@exemplo.com"
        favoritas = [categorias[i % len(categorias)]]
        if rng.random() < 0.4:
            favoritas.append(rng.choice(categorias))
        escolhidos: set[str] = set()
        for cat in favoritas:
            escolhidos.update(rng.sample(por_categoria[cat], min(len(por_categoria[cat]), rng.randint(2, 3))))
        escolhidos.update(rng.sample(ancoras, min(len(ancoras), rng.randint(1, 2))))
        for pid in sorted(escolhidos):
            compras.append({"email": email, "nome": nome, "produto_id": pid,
                            "quantidade": rng.randint(1, 2),
                            "data": (agora - timedelta(days=rng.randint(1, 90))).isoformat()})
    return compras


# --------------------------------------------------------------------------- #
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="apaga todo o grafo antes de carregar")
    ap.add_argument("--demo", type=int, default=12, metavar="N",
                    help="quantidade de clientes de exemplo criados só no grafo (padrão 12; 0 = nenhum)")
    args = ap.parse_args()

    db = get_db()
    produtos = ler_produtos(db)
    if not produtos:
        raise SystemExit("O MongoDB não tem produtos. Rode primeiro:  python -m scripts.seed --reset")

    try:
        graph.get_driver()
    except graph.ErroGrafo as exc:
        raise SystemExit(f"{exc}\nSuba o Neo4j (docker compose up -d neo4j) ou confira o NEO4J_* no .env.")

    if args.reset:
        graph.limpar()
        print("Grafo apagado.")
    graph.criar_schema()
    print("Schema criado (restrições de unicidade).")

    graph.carregar_produtos(produtos)
    print(f"Produtos carregados: {len(produtos)}")

    rng = random.Random(42)
    compras = ler_compras(db)
    print(f"Compras reais lidas do MongoDB: {len(compras)} (de {db[CLIENTES].count_documents({})} clientes)")
    demo = gerar_clientes_demo(produtos, compras, args.demo, rng) if args.demo > 0 else []
    todas = compras + demo

    graph.carregar_compras(todas, somar=False)
    graph.carregar_avaliacoes(gerar_avaliacoes(todas, rng))

    est = graph.estatisticas()
    print(f"Grafo pronto: {est['clientes']} clientes, {est['produtos']} produtos, "
          f"{est['categorias']} categorias, {est['compras']} [:COMPROU], {est['avaliacoes']} [:AVALIOU]")
    print("Pronto! Rode:  streamlit run app.py   e abra a página 'Recomendações'.")
    graph.fechar()


if __name__ == "__main__":
    main()
