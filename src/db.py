"""Conexão com o MongoDB, validadores de esquema ($jsonSchema) e índices.

Modelagem
---------
* produtos  -> catálogo com ESQUEMA FLEXÍVEL: campos comuns obrigatórios
               (sku, nome, marca, categorias, preço, imagens) + o campo
               `especificacoes`, um objeto JSON livre que muda conforme o tipo
               de produto (notebook tem CPU/RAM, livro tem autor/ISBN...).
* clientes  -> compradores (e-mail único) com estatísticas agregadas.
* pedidos   -> cada pedido guarda uma FOTOGRAFIA (snapshot) do comprador, dos
               itens e dos valores no momento da compra. Assim o histórico não
               muda se o produto mudar de preço ou o cliente mudar de nome.
"""
from functools import lru_cache

from pymongo import ASCENDING, DESCENDING, TEXT, MongoClient
from pymongo.database import Database

from .config import settings

PRODUTOS = "produtos"
CLIENTES = "clientes"
PEDIDOS = "pedidos"

STATUS_PEDIDO = ["pendente", "pago", "enviado", "entregue", "cancelado"]
METODOS_PAGAMENTO = ["pix", "cartao_credito", "boleto"]


# --------------------------------------------------------------------------- #
# Conexão
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def get_client() -> MongoClient:
    return MongoClient(
        settings.mongo_uri,
        serverSelectionTimeoutMS=5000,
        tz_aware=True,
        appname="amazon-pb",
    )


def get_db() -> Database:
    return get_client()[settings.mongo_db]


def ping() -> None:
    """Lança exceção se o MongoDB não estiver acessível."""
    get_client().admin.command("ping")


# --------------------------------------------------------------------------- #
# Validadores ($jsonSchema)
# --------------------------------------------------------------------------- #
_DINHEIRO = {"bsonType": "decimal", "minimum": 0}
_INTEIRO = {"bsonType": ["int", "long"], "minimum": 0}
_TEXTO = {"bsonType": "string", "minLength": 1}

VALIDADOR_PRODUTO = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Produto do catálogo",
        "required": ["sku", "nome", "marca", "categorias", "preco", "imagens",
                     "especificacoes", "estoque", "ativo", "criado_em"],
        "properties": {
            "sku": _TEXTO,
            "nome": {"bsonType": "string", "minLength": 3},
            "descricao": {"bsonType": "string"},
            "marca": _TEXTO,
            "categorias": {"bsonType": "array", "minItems": 1, "items": _TEXTO},
            "tags": {"bsonType": "array", "items": {"bsonType": "string"}},
            "preco": _DINHEIRO,
            "preco_original": {"bsonType": ["decimal", "null"]},
            "moeda": {"enum": ["BRL"]},
            "estoque": _INTEIRO,
            "imagens": {
                "bsonType": "array",
                "minItems": 1,
                "items": {
                    "bsonType": "object",
                    "required": ["url"],
                    "properties": {
                        "url": _TEXTO,
                        "alt": {"bsonType": "string"},
                        "principal": {"bsonType": "bool"},
                    },
                },
            },
            # Esquema flexível: qualquer objeto JSON é aceito aqui.
            "especificacoes": {"bsonType": "object"},
            "avaliacao": {
                "bsonType": "object",
                "properties": {
                    "media": {"bsonType": ["double", "int"], "minimum": 0, "maximum": 5},
                    "total": _INTEIRO,
                },
            },
            "ativo": {"bsonType": "bool"},
            "criado_em": {"bsonType": "date"},
            "atualizado_em": {"bsonType": "date"},
        },
        # additionalProperties não é definido => outros campos são permitidos.
    }
}

VALIDADOR_CLIENTE = {
    "$jsonSchema": {
        "bsonType": "object",
        "required": ["nome", "email", "criado_em"],
        "properties": {
            "nome": _TEXTO,
            "email": {"bsonType": "string", "pattern": r"^[^@\s]+@[^@\s]+\.[^@\s]+$"},
            "estatisticas": {
                "bsonType": "object",
                "properties": {
                    "total_pedidos": _INTEIRO,
                    "total_gasto": {"bsonType": "decimal"},
                    "ultimo_pedido_em": {"bsonType": "date"},
                },
            },
            "criado_em": {"bsonType": "date"},
        },
    }
}

VALIDADOR_PEDIDO = {
    "$jsonSchema": {
        "bsonType": "object",
        "title": "Pedido",
        "required": ["numero", "cliente", "itens", "valores", "status",
                     "historico_status", "criado_em"],
        "properties": {
            "numero": _TEXTO,
            "cliente": {  # snapshot do comprador
                "bsonType": "object",
                "required": ["id", "nome", "email"],
                "properties": {
                    "id": {"bsonType": "objectId"},
                    "nome": _TEXTO,
                    "email": _TEXTO,
                },
            },
            "itens": {
                "bsonType": "array",
                "minItems": 1,
                "items": {
                    "bsonType": "object",
                    "required": ["produto_id", "sku", "nome", "quantidade",
                                 "preco_unitario", "subtotal"],
                    "properties": {
                        "produto_id": {"bsonType": "objectId"},
                        "sku": _TEXTO,
                        "nome": _TEXTO,
                        "marca": {"bsonType": "string"},
                        "imagem": {"bsonType": "string"},
                        "quantidade": {"bsonType": ["int", "long"], "minimum": 1},
                        "preco_unitario": _DINHEIRO,
                        "subtotal": _DINHEIRO,
                    },
                },
            },
            "valores": {
                "bsonType": "object",
                "required": ["subtotal", "frete", "desconto", "total"],
                "properties": {
                    "subtotal": _DINHEIRO,
                    "frete": _DINHEIRO,
                    "desconto": _DINHEIRO,
                    "total": _DINHEIRO,
                },
            },
            "cupom": {"bsonType": ["string", "null"]},
            "status": {"enum": STATUS_PEDIDO},
            "historico_status": {
                "bsonType": "array",
                "items": {
                    "bsonType": "object",
                    "required": ["status", "em"],
                    "properties": {
                        "status": {"enum": STATUS_PEDIDO},
                        "em": {"bsonType": "date"},
                        "obs": {"bsonType": "string"},
                    },
                },
            },
            "endereco_entrega": {"bsonType": "object"},
            "pagamento": {
                "bsonType": "object",
                "required": ["metodo"],
                "properties": {"metodo": {"enum": METODOS_PAGAMENTO}},
            },
            "criado_em": {"bsonType": "date"},
        },
    }
}


# --------------------------------------------------------------------------- #
# Inicialização (idempotente)
# --------------------------------------------------------------------------- #
def _aplicar_validador(db: Database, nome: str, validador: dict) -> None:
    if nome in db.list_collection_names():
        db.command("collMod", nome, validator=validador,
                   validationLevel="moderate", validationAction="error")
    else:
        db.create_collection(nome, validator=validador,
                             validationLevel="moderate", validationAction="error")


def init_db(db: Database | None = None) -> None:
    """Cria coleções, validadores e índices. Pode ser chamada várias vezes."""
    if db is None:
        db = get_db()

    _aplicar_validador(db, PRODUTOS, VALIDADOR_PRODUTO)
    _aplicar_validador(db, CLIENTES, VALIDADOR_CLIENTE)
    _aplicar_validador(db, PEDIDOS, VALIDADOR_PEDIDO)

    produtos = db[PRODUTOS]
    produtos.create_index([("sku", ASCENDING)], unique=True, name="uk_sku")
    produtos.create_index(
        [("nome", TEXT), ("marca", TEXT), ("categorias", TEXT),
         ("tags", TEXT), ("descricao", TEXT)],
        weights={"nome": 10, "marca": 6, "categorias": 4, "tags": 3, "descricao": 1},
        default_language="portuguese",
        name="txt_busca",
    )
    produtos.create_index([("ativo", ASCENDING), ("categorias", ASCENDING),
                           ("preco", ASCENDING)], name="ix_categoria_preco")
    produtos.create_index([("ativo", ASCENDING), ("marca", ASCENDING)], name="ix_marca")
    produtos.create_index([("ativo", ASCENDING), ("avaliacao.media", DESCENDING)],
                          name="ix_avaliacao")

    db[CLIENTES].create_index([("email", ASCENDING)], unique=True, name="uk_email")

    pedidos = db[PEDIDOS]
    pedidos.create_index([("numero", ASCENDING)], unique=True, name="uk_numero")
    pedidos.create_index([("cliente.id", ASCENDING), ("criado_em", DESCENDING)],
                         name="ix_cliente_data")
    pedidos.create_index([("status", ASCENDING), ("criado_em", DESCENDING)],
                         name="ix_status_data")
