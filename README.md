# PB Store — E-commerce inspirado na Amazon

Python + **Streamlit** (telas) + **MongoDB** (catálogo flexível e pedidos).
Cache **Redis** nas consultas do catálogo (com fallback automático para o MongoDB).

## Como rodar (Windows / PowerShell)

Pré-requisitos: Python 3.10+ e um MongoDB. **Docker é opcional**, escolha uma opção:

* **MongoDB Community Server (Windows)** — baixe o instalador `.msi` em mongodb.com/try/download/community, marque *Install MongoDB as a Service*. Ele fica rodando em `localhost:27017`, que já é o padrão do projeto: pule o passo 3.
* **MongoDB Atlas (nuvem, grátis)** — crie um cluster M0 em mongodb.com/atlas, um usuário de banco e libere seu IP em *Network Access*. Copie a connection string para o `.env`:
  `MONGO_URI=mongodb+srv://usuario:senha@cluster0.xxxxx.mongodb.net/`  — pule o passo 3.
* **Docker** — `docker compose up -d mongo` (passo 3).

```powershell
# 1. Ambiente virtual e dependências
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 2. Configuração (opcional — os padrões já apontam para localhost)
copy .env.example .env

# 3. MongoDB (apenas se usar Docker)
docker compose up -d mongo

# 4. Dados de exemplo (36 produtos, 3 clientes e pedidos com histórico)
python -m scripts.seed --reset

# 5. Aplicação
streamlit run app.py
```

Abra http://localhost:8501.

**Atalho:** dê dois cliques em `popular_banco.bat`. Ele cria o ambiente, sobe o MongoDB, popula o banco e abre o Streamlit.

**Sem Python/seed (MongoDB Compass):** crie o banco `amazon_pb`, coleção `produtos`, e use *Add Data → Import JSON or CSV file* com `dados/produtos_exemplo.json`. Depois rode o app normalmente (os índices são criados na primeira abertura).
Via linha de comando: `mongoimport --db amazon_pb --collection produtos --jsonArray --file dados/produtos_exemplo.json`
Para inspecionar o banco pelo navegador: `docker compose --profile admin up -d mongo-express` → http://localhost:8081

## Telas

| Tela | Arquivo | O que faz |
|---|---|---|
| Catálogo e busca | `views/catalogo.py` | Busca textual (índice `$text` em português com pesos) + filtros por categoria, marca, preço e avaliação; ordenação e paginação via `$facet`; detalhes do produto com especificações JSON |
| Carrinho | `pages/1_Carrinho.py` | Quantidades, cupom (`PB10`, `BEMVINDO`), frete grátis acima de R$ 199, checkout que grava o pedido |
| Meus pedidos | `pages/2_Pedidos.py` | Histórico do comprador, resumo agregado (total gasto, ticket médio), itens, valores e linha do tempo de status |
| Cadastrar produto | `pages/3_Cadastrar_Produto.py` | Formulário com especificações em JSON livre (modelos por tipo de produto) |

## Estrutura

```
app.py                     ponto de entrada e menu lateral (st.navigation)
views/catalogo.py          tela do catálogo + busca
pages/                     demais telas do Streamlit
src/
  config.py                variáveis de ambiente (.env)
  db.py                    conexão, validadores $jsonSchema e índices
  cache.py                 camada de cache (RedisCache + NullCache de fallback)
  utils.py                 dinheiro em Decimal128, datas, formatação
  ui.py                    componentes visuais compartilhados
  repositories/            acesso às coleções (produtos, clientes, pedidos)
  services/                regras usadas pelas telas + pontos de cache/invalidação
scripts/seed.py            dados de exemplo
docker-compose.yml         mongo + redis (mongo-express em profile opcional)
```

## Modelagem no MongoDB

### `produtos` — esquema flexível

Campos comuns são validados pelo `$jsonSchema`; `especificacoes` aceita **qualquer objeto JSON**, então cada tipo de produto tem atributos próprios:

```json
{
  "sku": "NOTE-LEN-IP5",
  "nome": "Notebook Lenovo IdeaPad Slim 5",
  "marca": "Lenovo",
  "categorias": ["Informática", "Eletrônicos"],
  "tags": ["notebook", "laptop", "ryzen"],
  "preco": NumberDecimal("3899.00"),
  "preco_original": NumberDecimal("4599.00"),
  "estoque": 12,
  "imagens": [{ "url": "https://...", "alt": "...", "principal": true }],
  "especificacoes": {
    "processador": "AMD Ryzen 7 7730U",
    "memoria_ram_gb": 16,
    "armazenamento": { "tipo": "SSD NVMe", "capacidade_gb": 512 },
    "tela": { "tamanho_pol": 15.6, "resolucao": "1920x1080" }
  },
  "avaliacao": { "media": 4.6, "total": 2310 },
  "ativo": true
}
```

Um livro, no mesmo catálogo, tem `especificacoes: { autor, editora, isbn, paginas }`.

Índices: `sku` único, texto (`nome` peso 10, `marca` 6, `categorias` 4, `tags` 3, `descricao` 1), `categorias+preco`, `marca`, `avaliacao.media`.

### `pedidos` — histórico do comprador e valores

Cada pedido guarda um **snapshot** do comprador, dos itens (preço no momento da compra) e dos valores, além do histórico de status:

```json
{
  "numero": "PB-20261107-A1B2C3",
  "cliente": { "id": ObjectId("..."), "nome": "Ana Souza", "email": "ana@exemplo.com" },
  "itens": [{ "produto_id": ObjectId("..."), "sku": "...", "nome": "...", "quantidade": 2,
              "preco_unitario": NumberDecimal("229.00"), "subtotal": NumberDecimal("458.00") }],
  "valores": { "subtotal": NumberDecimal("458.00"), "frete": NumberDecimal("0.00"),
               "desconto": NumberDecimal("45.80"), "total": NumberDecimal("412.20") },
  "cupom": "PB10",
  "status": "enviado",
  "historico_status": [
    { "status": "pendente", "em": ISODate("..."), "obs": "Pedido criado" },
    { "status": "pago",     "em": ISODate("..."), "obs": "Pagamento aprovado (pix)" },
    { "status": "enviado",  "em": ISODate("..."), "obs": "Atualizado pela loja" }
  ],
  "endereco_entrega": { "cep": "...", "logradouro": "...", "cidade": "...", "uf": "SP" },
  "pagamento": { "metodo": "pix" }
}
```

### `clientes`

E-mail único, criado automaticamente na primeira compra (upsert), com `estatisticas` acumuladas (`total_pedidos`, `total_gasto`, `ultimo_pedido_em`).

### Decisões

* **Dinheiro em `Decimal128`** — sem erros de arredondamento de `float`.
* **Preço vem sempre do banco** no checkout, nunca da tela.
* **Estoque baixado de forma atômica** (`update_one` com `estoque >= qtd`); se algo falhar, o estoque reservado é devolvido. Com MongoDB em replica set, dá para trocar por uma transação multi-documento.

## Cache Redis

Cache-aside nas consultas do catálogo (busca, facetas e produto):

* `src/cache.py`: `CacheBackend`, `RedisCache` (TTL, serialização BSON, circuit breaker), `NullCache` (fallback), decorator `@cached` e `invalidar()`.
* `src/services/catalogo.py`: busca (TTL 120s), facetas (600s) e produto (300s) passam por `@cached`; o texto da busca é normalizado para aumentar o hit rate. Cadastrar produto invalida `catalogo:*`.
* `src/services/checkout.py`: criar/cancelar pedido invalida o catálogo (estoque mudou).
* Se o Redis estiver fora, a aplicação continua consultando o MongoDB e tenta reconectar sozinha a cada 30s.
* A tela de catálogo mostra se o resultado veio do cache (⚡) ou do MongoDB (🍃).

Para usar:

1. `pip install -r requirements.txt`
2. `docker compose up -d redis` (ou `brew install redis && redis-server`)
3. `.env`: `CACHE_BACKEND=redis` (já é o padrão) e `REDIS_URL=redis://localhost:6379/0`

Para desligar: `CACHE_BACKEND=none`.
