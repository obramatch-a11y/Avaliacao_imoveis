from playwright.sync_api import sync_playwright
erros=[]
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox"]); pg=b.new_context(viewport={"width":420,"height":900}).new_page()
    pg.on("pageerror",lambda e:erros.append(str(e)))
    pg.route("**/auth/config",lambda r:r.fulfill(json={"login":True,"client_id":"cid","cofre":False,"ia_servidor":True,"usuario":{"nome":"Ana","email":"a@x.com"}}))
    pg.route("**/auth/ia",lambda r:r.fulfill(json={"ok":True,"cofre":False}))
    pg.route("**/accounts.google.com/gsi/client",lambda r:r.fulfill(content_type="text/javascript",body="window.google={accounts:{id:{initialize(){},renderButton(){}},oauth2:{}}};"))
    pg.route("**/api/ia/extrair",lambda r:r.fulfill(json={"itens":[{"campo":"suites","valor":2,"evidencia":"2 suítes"},{"campo":"quartos","valor":9,"evidencia":"2 suítes"}],"rejeitados":0,"modelo":"gemini-flash-latest"}))
    pg.goto("http://127.0.0.1:8765/coleta/teste1/resultado"); pg.wait_for_selector(".grow")
    pg.evaluate("IE.ia.cfg.chave=''; var A=IE.P.amostras; A[0].descricao='Apartamento com 2 suítes e piscina'; A[1].descricao='Apto com 2 suítes'; A[0].suites=null; A[1].suites=null; location.hash='ia'"); pg.wait_for_timeout(700)
    print("nota:", pg.locator("#iaTxt").input_value()[:40], "|", "completa" in pg.locator("#iaConta").locator("xpath=../..").inner_text() or pg.content().count("Descrição completa"))
    pg.click("#iaLote"); pg.wait_for_selector("#iaAplica",timeout=15000); print(pg.locator("#iaLoteR").inner_text()[:140].replace("\n"," "))
    pg.click("#iaAplica"); pg.wait_for_timeout(300)
    print("suites:", pg.evaluate("[IE.P.amostras[0].suites, IE.P.amostras[1].suites]"), "quartos0 intacto:", pg.evaluate("IE.P.amostras[0].quartos"))
    b.close()
print("ERROS:",erros)
