"""Popula o MongoDB com produtos, clientes e pedidos de exemplo.

Uso (na raiz do projeto):
    python -m scripts.seed           # insere (ignora SKUs já existentes)
    python -m scripts.seed --reset   # apaga as coleções e recria tudo
"""
import argparse
import random
import sys
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.db import CLIENTES, PEDIDOS, PRODUTOS, get_db, init_db  # noqa: E402
from src.repositories import pedidos as pedidos_repo  # noqa: E402
from src.repositories import produtos as produtos_repo  # noqa: E402
from src.utils import agora  # noqa: E402

CORES = {"Eletrônicos": "232f3e/ffffff", "Informática": "37475a/ffffff", "Livros": "f3e9d2/333333",
         "Moda": "fde2e4/333333", "Casa e Cozinha": "e3f2fd/333333", "Esportes": "e8f5e9/333333",
         "Games": "1b1b2f/ff9900"}


def imagens(nome: str, categoria: str, n: int = 2) -> list[dict]:
    cor = CORES.get(categoria, "eeeeee/333333")
    rotulos = ["", " (detalhe)", " (embalagem)"]
    return [{"url": f"https://placehold.co/600x600/{cor}/png?text={quote_plus(nome + rotulos[i])}",
             "alt": nome + rotulos[i], "principal": i == 0} for i in range(n)]


def p(sku, nome, marca, categorias, preco, especificacoes, estoque=25, preco_original=None,
      descricao="", tags=(), media=4.5, total=100):
    return {
        "sku": sku, "nome": nome, "marca": marca, "categorias": categorias,
        "preco": preco, "preco_original": preco_original, "estoque": estoque,
        "descricao": descricao, "tags": list(tags),
        "imagens": imagens(nome, categorias[0]),
        "especificacoes": especificacoes,
        "avaliacao": {"media": float(media), "total": int(total)},
    }


PRODUTOS_EXEMPLO = [
    # ---------------- Eletrônicos / Informática ----------------
    p("NOTE-LEN-IP5", "Notebook Lenovo IdeaPad Slim 5", "Lenovo", ["Informática", "Eletrônicos"],
      3899.00, {
          "processador": "AMD Ryzen 7 7730U", "memoria_ram_gb": 16,
          "armazenamento": {"tipo": "SSD NVMe", "capacidade_gb": 512},
          "tela": {"tamanho_pol": 15.6, "resolucao": "1920x1080", "tipo": "IPS"},
          "sistema_operacional": "Windows 11 Home", "peso_kg": 1.7, "garantia_meses": 12,
      }, preco_original=4599.00, estoque=12, tags=["notebook", "laptop", "ryzen"],
      descricao="Notebook fino e leve para trabalho e estudo.", media=4.6, total=2310),
    p("NOTE-DEL-INS", "Notebook Dell Inspiron 15", "Dell", ["Informática", "Eletrônicos"],
      3299.00, {
          "processador": "Intel Core i5-1235U", "memoria_ram_gb": 8,
          "armazenamento": {"tipo": "SSD", "capacidade_gb": 512},
          "tela": {"tamanho_pol": 15.6, "resolucao": "1920x1080"},
          "sistema_operacional": "Windows 11", "garantia_meses": 12,
      }, estoque=4, tags=["notebook", "laptop", "intel"], media=4.3, total=980),
    p("CEL-SAM-A55", "Smartphone Samsung Galaxy A55 5G 256GB", "Samsung", ["Eletrônicos", "Celulares"],
      2199.00, {
          "tela": {"tamanho_pol": 6.6, "tipo": "Super AMOLED", "taxa_hz": 120},
          "armazenamento_gb": 256, "memoria_ram_gb": 8,
          "camera": {"traseira_mp": [50, 12, 5], "frontal_mp": 32},
          "bateria_mah": 5000, "resistencia": "IP67", "cores": ["Azul", "Preto", "Lilás"],
      }, preco_original=2699.00, estoque=40, tags=["celular", "android", "5g"], media=4.7, total=5400),
    p("CEL-APL-15", "iPhone 15 128GB", "Apple", ["Eletrônicos", "Celulares"],
      5299.00, {
          "chip": "A16 Bionic", "armazenamento_gb": 128,
          "tela": {"tamanho_pol": 6.1, "tipo": "Super Retina XDR OLED"},
          "camera": {"principal_mp": 48, "ultra_wide_mp": 12}, "conector": "USB-C",
      }, preco_original=5999.00, estoque=15, tags=["celular", "ios", "iphone"], media=4.8, total=7100),
    p("FONE-JBL-T520", "Fone de Ouvido Bluetooth JBL Tune 520BT", "JBL", ["Eletrônicos", "Áudio"],
      229.00, {
          "tipo": "Over-ear", "conexao": "Bluetooth 5.3", "autonomia_h": 57,
          "microfone": True, "carregamento": "USB-C", "cores": ["Preto", "Azul", "Branco"],
      }, preco_original=299.00, estoque=80, tags=["fone", "headphone", "bluetooth"], media=4.6, total=12000),
    p("KIN-AMZ-11", "Kindle 11ª Geração 16GB", "Amazon", ["Eletrônicos", "Livros"],
      549.00, {
          "tela": {"tamanho_pol": 6, "resolucao_ppi": 300, "luz_embutida": True},
          "armazenamento_gb": 16, "bateria_semanas": 6, "a_prova_dagua": False,
      }, estoque=60, tags=["ereader", "kindle", "leitura"], media=4.8, total=25000),
    p("MON-LG-27", "Monitor LG UltraGear 27\" 144Hz", "LG", ["Informática", "Games"],
      1299.00, {
          "tamanho_pol": 27, "resolucao": "2560x1440", "taxa_hz": 144, "painel": "IPS",
          "tempo_resposta_ms": 1, "entradas": ["HDMI x2", "DisplayPort"], "hdr": "HDR10",
      }, preco_original=1599.00, estoque=9, tags=["monitor", "gamer"], media=4.7, total=3200),
    p("TEC-LOG-MXK", "Teclado sem fio Logitech MX Keys", "Logitech", ["Informática"],
      699.00, {
          "layout": "ABNT2", "conexao": ["Bluetooth", "Logi Bolt"], "retroiluminado": True,
          "bateria": "Recarregável, até 10 dias", "compatibilidade": ["Windows", "macOS", "Linux"],
      }, estoque=30, tags=["teclado", "wireless"], media=4.7, total=1800),
    # ---------------- Games ----------------
    p("GAM-SNY-PS5", "Console PlayStation 5 Slim Digital", "Sony", ["Games", "Eletrônicos"],
      3599.00, {
          "armazenamento": {"tipo": "SSD", "capacidade_tb": 1}, "resolucao_max": "4K 120fps",
          "midia_fisica": False, "controles_inclusos": 1,
      }, preco_original=3999.00, estoque=7, tags=["console", "playstation"], media=4.9, total=8800),
    p("GAM-NIN-SWO", "Nintendo Switch OLED", "Nintendo", ["Games"],
      2299.00, {
          "tela": {"tamanho_pol": 7, "tipo": "OLED"}, "armazenamento_gb": 64,
          "modos": ["TV", "Mesa", "Portátil"], "cor": "Branco",
      }, estoque=3, tags=["console", "portatil"], media=4.8, total=6400),
    # ---------------- Livros ----------------
    p("LIV-ARQ-LIMPA", "Arquitetura Limpa", "Alta Books", ["Livros", "Tecnologia"],
      89.90, {
          "autor": "Robert C. Martin", "editora": "Alta Books", "isbn": "978-8550804606",
          "paginas": 432, "idioma": "Português", "formato": "Capa comum", "edicao": 1,
      }, preco_original=119.90, estoque=50, tags=["software", "programacao"], media=4.8, total=4300),
    p("LIV-DDIA", "Designing Data-Intensive Applications", "O'Reilly", ["Livros", "Tecnologia"],
      329.00, {
          "autor": "Martin Kleppmann", "editora": "O'Reilly Media", "isbn": "978-1449373320",
          "paginas": 616, "idioma": "Inglês", "formato": "Capa comum",
          "assuntos": ["bancos de dados", "sistemas distribuídos"],
      }, estoque=14, tags=["banco de dados", "nosql", "mongodb"], media=4.9, total=9100),
    p("LIV-HABITOS", "Hábitos Atômicos", "Alta Life", ["Livros", "Autoajuda"],
      49.90, {
          "autor": "James Clear", "editora": "Alta Life", "isbn": "978-8550807560",
          "paginas": 320, "idioma": "Português", "formato": "Capa comum",
      }, preco_original=69.90, estoque=120, tags=["produtividade"], media=4.8, total=56000),
    # ---------------- Moda ----------------
    p("MOD-CAM-BAS", "Camiseta Básica Algodão Premium", "Hering", ["Moda", "Masculino"],
      59.90, {
          "tamanhos": ["P", "M", "G", "GG"], "cores": ["Preto", "Branco", "Cinza", "Azul-marinho"],
          "material": "100% algodão", "modelagem": "Regular", "gola": "Careca",
      }, estoque=200, tags=["camiseta", "basica"], media=4.4, total=3100),
    p("MOD-TEN-NIK", "Tênis Nike Revolution 7", "Nike", ["Moda", "Esportes", "Calçados"],
      349.90, {
          "numeracao": list(range(36, 45)), "cores": ["Preto/Branco", "Cinza"],
          "material_cabedal": "Malha", "solado": "Borracha", "indicado_para": "Corrida leve",
      }, preco_original=449.90, estoque=35, tags=["tenis", "corrida"], media=4.5, total=2700),
    # ---------------- Casa e Cozinha ----------------
    p("CAS-AIR-MON", "Fritadeira Air Fryer Mondial 4L", "Mondial", ["Casa e Cozinha", "Eletroportáteis"],
      299.90, {
          "capacidade_l": 4, "potencia_w": 1500, "voltagem": ["127V", "220V"],
          "temperatura_max_c": 200, "timer_min": 60, "cor": "Preto",
      }, preco_original=399.90, estoque=45, tags=["airfryer", "fritadeira"], media=4.6, total=15400),
    p("CAS-CAF-NES", "Cafeteira Nespresso Essenza Mini", "Nespresso", ["Casa e Cozinha"],
      449.00, {
          "pressao_bar": 19, "reservatorio_ml": 600, "voltagem": "127V",
          "compatibilidade_capsulas": "Nespresso Original", "dimensoes_cm": {"a": 20, "l": 8, "p": 33},
      }, estoque=22, tags=["cafe", "capsula"], media=4.7, total=6900),
    p("CAS-ASP-WAP", "Aspirador Robô WAP Robot W90", "WAP", ["Casa e Cozinha"],
      899.00, {
          "autonomia_min": 100, "mapeamento": "Giroscópio", "app": True,
          "funcoes": ["Aspira", "Varre", "Passa pano"], "reservatorio_ml": 300,
      }, preco_original=1199.00, estoque=0, tags=["robo", "limpeza"], media=4.2, total=1500),
    # ---------------- Esportes ----------------
    p("ESP-HAL-10", "Kit Halteres Emborrachados 10kg", "Kikos", ["Esportes"],
      189.90, {
          "peso_total_kg": 10, "itens": ["2 barras", "4 anilhas de 2kg", "2 anilhas de 0,5kg"],
          "material": "Ferro emborrachado",
      }, estoque=18, tags=["musculacao", "academia"], media=4.5, total=870),
    p("ESP-GAR-INOX", "Garrafa Térmica Inox 1L", "Stanley", ["Esportes", "Casa e Cozinha"],
      279.00, {
          "capacidade_ml": 1000, "mantem_gelado_h": 24, "mantem_quente_h": 20,
          "material": "Aço inox 18/8", "cores": ["Verde", "Preto", "Creme"],
      }, estoque=70, tags=["garrafa", "termica"], media=4.9, total=21000),
    # ---------------- Mais eletrônicos ----------------
    p("TV-SAM-55Q", "Smart TV Samsung 55\" QLED 4K Q60D", "Samsung", ["Eletrônicos", "TV e Vídeo"],
      2999.00, {
          "tamanho_pol": 55, "resolucao": "3840x2160", "tecnologia": "QLED",
          "hdr": ["HDR10+", "HLG"], "sistema": "Tizen", "hdmi": 3, "usb": 2,
          "assistentes": ["Bixby", "Alexa integrada"],
      }, preco_original=3699.00, estoque=11, tags=["tv", "smart tv", "4k"], media=4.7, total=4800),
    p("ECHO-DOT-5", "Echo Dot 5ª Geração com Alexa", "Amazon", ["Eletrônicos", "Casa Inteligente"],
      379.00, {
          "assistente": "Alexa", "conexao": ["Wi-Fi", "Bluetooth"], "sensor_temperatura": True,
          "cores": ["Preta", "Branca", "Azul"], "alimentacao": "Fonte 15W",
      }, preco_original=479.00, estoque=150, tags=["alexa", "smart speaker"], media=4.8, total=38000),
    p("TAB-SAM-S9FE", "Tablet Samsung Galaxy Tab S9 FE 128GB", "Samsung", ["Eletrônicos", "Informática"],
      2499.00, {
          "tela": {"tamanho_pol": 10.9, "tipo": "TFT LCD", "taxa_hz": 90},
          "armazenamento_gb": 128, "memoria_ram_gb": 6, "caneta_inclusa": True,
          "bateria_mah": 8000, "resistencia": "IP68",
      }, estoque=16, tags=["tablet", "android"], media=4.6, total=2100),
    p("SMW-APL-S9", "Apple Watch Series 9 GPS 41mm", "Apple", ["Eletrônicos", "Wearables"],
      3299.00, {
          "caixa": {"tamanho_mm": 41, "material": "Alumínio"}, "chip": "S9 SiP",
          "sensores": ["Oxigênio no sangue", "ECG", "Frequência cardíaca", "Temperatura"],
          "resistencia_agua_m": 50, "bateria_h": 18,
      }, preco_original=3999.00, estoque=8, tags=["smartwatch", "relogio"], media=4.8, total=3900),
    p("CAM-GOP-H12", "Câmera GoPro HERO12 Black", "GoPro", ["Eletrônicos", "Câmeras"],
      2599.00, {
          "video_max": "5.3K 60fps", "foto_mp": 27, "estabilizacao": "HyperSmooth 6.0",
          "a_prova_dagua_m": 10, "bateria_mah": 1720, "acessorios": ["Bateria extra", "Suporte curvo"],
      }, estoque=5, tags=["camera", "acao"], media=4.6, total=1200),
    p("MOU-LOG-G203", "Mouse Gamer Logitech G203 Lightsync", "Logitech", ["Informática", "Games"],
      129.90, {
          "dpi_max": 8000, "botoes": 6, "iluminacao": "RGB Lightsync", "conexao": "USB",
          "peso_g": 85,
      }, preco_original=179.90, estoque=95, tags=["mouse", "gamer", "rgb"], media=4.7, total=27000),
    p("SSD-KIN-1TB", "SSD Kingston NV2 1TB NVMe M.2", "Kingston", ["Informática"],
      399.00, {
          "capacidade_gb": 1000, "interface": "PCIe 4.0 x4 NVMe", "formato": "M.2 2280",
          "leitura_mb_s": 3500, "gravacao_mb_s": 2100, "garantia_anos": 3,
      }, preco_original=499.00, estoque=60, tags=["ssd", "armazenamento"], media=4.8, total=14500),
    # ---------------- Games ----------------
    p("GAM-XBX-CTRL", "Controle Xbox Sem Fio Carbon Black", "Microsoft", ["Games"],
      449.00, {
          "compatibilidade": ["Xbox Series X|S", "Xbox One", "Windows", "Android", "iOS"],
          "conexao": ["Xbox Wireless", "Bluetooth", "USB-C"], "pilhas": "2x AA",
      }, estoque=40, tags=["controle", "xbox"], media=4.8, total=11000),
    p("GAM-ZELDA-TOTK", "The Legend of Zelda: Tears of the Kingdom (Switch)", "Nintendo", ["Games"],
      299.00, {
          "plataforma": "Nintendo Switch", "midia": "Física", "genero": ["Aventura", "Ação"],
          "classificacao": "10 anos", "idiomas": ["Português", "Inglês"], "jogadores": 1,
      }, preco_original=349.00, estoque=25, tags=["jogo", "zelda"], media=4.9, total=9500),
    # ---------------- Livros ----------------
    p("LIV-PY-FLU", "Python Fluente — 2ª Edição", "Novatec", ["Livros", "Tecnologia"],
      179.00, {
          "autor": "Luciano Ramalho", "editora": "Novatec", "isbn": "978-8575228425",
          "paginas": 1008, "idioma": "Português", "formato": "Capa comum", "edicao": 2,
      }, estoque=30, tags=["python", "programacao"], media=4.9, total=2600),
    p("LIV-MONGO-DEF", "MongoDB: The Definitive Guide", "O'Reilly", ["Livros", "Tecnologia"],
      289.00, {
          "autor": ["Shannon Bradshaw", "Eoin Brazil", "Kristina Chodorow"],
          "editora": "O'Reilly Media", "isbn": "978-1491954461", "paginas": 514,
          "idioma": "Inglês", "edicao": 3,
      }, estoque=10, tags=["mongodb", "nosql", "banco de dados"], media=4.6, total=800),
    p("LIV-1984", "1984", "Companhia das Letras", ["Livros", "Ficção"],
      39.90, {
          "autor": "George Orwell", "tradutor": "Alexandre Hubner e Heloisa Jahn",
          "editora": "Companhia das Letras", "paginas": 416, "idioma": "Português",
          "formato": "Capa comum",
      }, preco_original=59.90, estoque=90, tags=["classico", "distopia"], media=4.9, total=41000),
    # ---------------- Moda ----------------
    p("MOD-JAQ-JEANS", "Jaqueta Jeans Feminina Oversized", "Levi's", ["Moda", "Feminino"],
      399.90, {
          "tamanhos": ["PP", "P", "M", "G"], "cores": ["Azul claro", "Azul escuro"],
          "material": {"algodao_pct": 99, "elastano_pct": 1}, "modelagem": "Oversized",
      }, preco_original=549.90, estoque=20, tags=["jaqueta", "jeans"], media=4.5, total=650),
    p("MOD-MOC-SAM", "Mochila Samsonite Executiva para Notebook 15.6\"", "Samsonite", ["Moda", "Acessórios"],
      599.00, {
          "capacidade_l": 22, "compartimento_notebook_pol": 15.6, "material": "Poliéster",
          "impermeavel": True, "bolsos": 6, "cor": "Preto",
      }, estoque=14, tags=["mochila", "notebook"], media=4.7, total=1900),
    # ---------------- Casa e Cozinha ----------------
    p("CAS-LIQ-OST", "Liquidificador Oster 1400W 3,2L", "Oster", ["Casa e Cozinha", "Eletroportáteis"],
      229.90, {
          "potencia_w": 1400, "capacidade_l": 3.2, "velocidades": 12, "voltagem": ["127V", "220V"],
          "jarra": "Vidro", "lamina": "Aço inox 6 pontas",
      }, preco_original=299.90, estoque=33, tags=["liquidificador"], media=4.5, total=5200),
    p("CAS-PAN-TRA", "Jogo de Panelas Tramontina Antiaderente 5 peças", "Tramontina", ["Casa e Cozinha"],
      349.90, {
          "pecas": ["Caçarola 20cm", "Caçarola 24cm", "Panela 18cm", "Frigideira 24cm", "Leiteira 16cm"],
          "revestimento": "Starflon Max", "cooktop_inducao": False, "cor": "Vermelho",
      }, preco_original=459.90, estoque=27, tags=["panelas", "cozinha"], media=4.7, total=8700),
]

CLIENTES_EXEMPLO = [
    ("Ana Souza", "ana@exemplo.com"),
    ("Bruno Lima", "bruno@exemplo.com"),
    ("Carla Mendes", "carla@exemplo.com"),
]

ENDERECOS = [
    {"cep": "01310-100", "logradouro": "Av. Paulista, 1000, ap 12", "cidade": "São Paulo", "uf": "SP"},
    {"cep": "20040-020", "logradouro": "Rua da Assembleia, 50", "cidade": "Rio de Janeiro", "uf": "RJ"},
    {"cep": "30130-000", "logradouro": "Av. Afonso Pena, 300", "cidade": "Belo Horizonte", "uf": "MG"},
]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--reset", action="store_true", help="apaga as coleções antes de popular")
    args = ap.parse_args()

    db = get_db()
    if args.reset:
        for nome in (PRODUTOS, CLIENTES, PEDIDOS):
            db.drop_collection(nome)
        print("Coleções apagadas.")
    init_db(db)

    inseridos = 0
    for i, dados in enumerate(PRODUTOS_EXEMPLO):
        if db[PRODUTOS].find_one({"sku": dados["sku"]}):
            continue
        dados["criado_em"] = agora() - timedelta(days=len(PRODUTOS_EXEMPLO) - i)
        produtos_repo.inserir(dados, db=db)
        inseridos += 1
    print(f"Produtos inseridos: {inseridos} (total no catálogo: {db[PRODUTOS].count_documents({})})")

    if db[PEDIDOS].count_documents({}) == 0:
        random.seed(42)
        disponiveis = [str(x["_id"]) for x in db[PRODUTOS].find({"estoque": {"$gte": 5}}, {"_id": 1})]
        total = 0
        for (nome, email), endereco in zip(CLIENTES_EXEMPLO, ENDERECOS):
            for _ in range(random.randint(2, 4)):
                carrinho = {pid: random.randint(1, 2) for pid in random.sample(disponiveis, random.randint(1, 3))}
                pedido = pedidos_repo.criar_pedido(
                    nome, email, carrinho, endereco,
                    metodo_pagamento=random.choice(["pix", "cartao_credito", "boleto"]),
                    cupom=random.choice([None, None, "PB10"]), db=db,
                )
                # simula evolução do pedido para enriquecer o histórico
                for _ in range(random.randint(0, 2)):
                    atual = db[PEDIDOS].find_one({"_id": pedido["_id"]}, {"status": 1})["status"]
                    prox = pedidos_repo.proximo_status(atual)
                    if prox:
                        pedidos_repo.alterar_status(pedido["_id"], prox, "Atualização automática (seed)", db=db)
                total += 1
        print(f"Pedidos de exemplo criados: {total} para {len(CLIENTES_EXEMPLO)} clientes")
    else:
        print("Já existem pedidos; nenhum pedido de exemplo foi criado.")

    print("Pronto! Rode:  streamlit run app.py")


if __name__ == "__main__":
    main()
