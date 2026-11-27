import random, time, sys
sys.path.insert(0, "/home/claude/zipapp")
import uvicorn
from app import main
from app.main import app, JOBS, normalizar_lista
from app.models import BuscaImovelInput  # type: ignore
random.seed(7)
p = BuscaImovelInput(uf="PE", cidade="Recife", bairro="", finalidade="VENDA", tipo_imovel="APARTAMENTO", limite_paginas=1)  # type: ignore
brutos = []
bairros = ["Boa Viagem", "Pina", "Espinheiro", "Graças", "Casa Forte"]
for i in range(60):
    a = random.choice([45, 60, 75, 90, 120, 150]) + random.randint(-4, 4)
    b = random.choice(bairros); f = {"Boa Viagem": 9500, "Pina": 8500, "Espinheiro": 7000, "Graças": 7500, "Casa Forte": 8200}[b]
    brutos.append({"titulo": f"Apto {i} {b}" + (" com piscina" if i % 3 == 0 else ""), "preco": f"R$ {int(a*f*(0.9+random.random()*0.2)):,}".replace(",", "."), "area": f"{a} m²", "quartos": str(2 + a // 70), "banheiros": "2", "vagas": str(1 + i % 2), "bairro": b, "fonte": "Chaves na Mão" if i % 2 else "OLX", "url": f"https://x.test/{i}", "fotos": ["https://www.chavesnamao.com.br/x.jpg"] if i % 4 else []})
brutos.append(dict(brutos[3]))  # duplicata
JOBS["teste1"] = {"params": p, "fontes": ["chaves"], "estado": "concluida", "pagina": 1, "encontrados": 60, "chave": None, "previa": [], "parcial": [], "cancelar": False, "resultado": normalizar_lista(brutos, p), "diagnostico": [], "erro": "", "inicio": time.time()}
uvicorn.run(app, host="127.0.0.1", port=8765, log_level="warning")
