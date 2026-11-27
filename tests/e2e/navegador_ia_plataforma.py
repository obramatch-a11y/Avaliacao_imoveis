from playwright.sync_api import sync_playwright
erros=[]
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox"]); pg=b.new_context(viewport={"width":1200,"height":800}).new_page()
    pg.on("pageerror",lambda e:erros.append(str(e)))
    pg.route("**/auth/config",lambda r:r.fulfill(json={"login":True,"client_id":"cid","cofre":False,"ia_servidor":True,"usuario":{"nome":"Ana","email":"a@x.com"}}))
    pg.route("**/auth/ia",lambda r:r.fulfill(json={"ok":True,"cofre":False}))
    pg.route("**/accounts.google.com/gsi/client",lambda r:r.fulfill(content_type="text/javascript",body="window.google={accounts:{id:{initialize(){},renderButton(){}},oauth2:{}}};"))
    pg.route("**/api/ia/extrair",lambda r:r.fulfill(json={"itens":[{"campo":"suites","valor":2,"evidencia":"2 suítes"}],"rejeitados":1,"modelo":"gemini-2.5-flash"}))
    pg.goto("http://127.0.0.1:8765/coleta/teste1/resultado"); pg.wait_for_selector(".grow")
    pg.evaluate("IE.ia.cfg.chave=''; IE.P.amostras[0].titulo='Apartamento com 2 suítes e piscina grande'; location.hash='ia'"); pg.wait_for_timeout(600)
    print("aviso:", pg.locator("#iaConta").inner_text()[:90])
    pg.click("#iaE"); pg.wait_for_selector("#iaTodos"); print("cartoes:", pg.locator("#iaR button[data-i]").count()); pg.click("#iaR button[data-i=\"0\"]")
    print("suites:", pg.evaluate("IE.P.amostras[0].suites"), pg.evaluate("IE.P.amostras[0].hist.slice(-1)[0].nota")[:70])
    b.close()
print("ERROS:",erros)
