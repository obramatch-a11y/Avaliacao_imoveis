from playwright.sync_api import sync_playwright
erros=[]
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox"]); pg=b.new_context(viewport={"width":420,"height":900}).new_page()
    pg.on("pageerror",lambda e:erros.append(str(e)))
    pg.route("**/auth/config",lambda r:r.fulfill(json={"login":True,"client_id":"cid","cofre":False,"ia_servidor":True,"usuario":{"nome":"Ana","email":"a@x.com"}}))
    pg.route("**/auth/ia",lambda r:r.fulfill(json={"ok":True,"cofre":False}))
    pg.route("**/accounts.google.com/gsi/client",lambda r:r.fulfill(content_type="text/javascript",body="window.google={accounts:{id:{initialize(){},renderButton(){}},oauth2:{}}};"))
    pg.route("**/api/ia/fotos",lambda r:r.fulfill(json={"itens":[{"campo":"conservacao","valor":"regular","evidencia":"mancha de umidade no teto","confianca":"media"},{"campo":"piscina","valor":1,"evidencia":"piscina ao fundo","confianca":"alta"}],"observacoes":"fotos escuras","fotos_lidas":2,"modelo":"gemini-flash-latest"}))
    pg.route("**/api/ia/texto",lambda r:r.fulfill(json={"texto":"O R² é 0,31. Há 53 amostras. Erro de 999,5.","numeros_fora":["999,5"],"modelo":"x"}))
    pg.goto("http://127.0.0.1:8765/coleta/teste1/resultado"); pg.wait_for_selector(".grow")
    pg.evaluate("IE.ia.cfg.chave=''; IE.P.amostras[0].fotos=['https://x.com/a.jpg','https://x.com/b.jpg']; IE.P.amostras[3].valor_total=99000000; IE.P.amostras[3].area_privativa=50; location.hash='ia'"); pg.wait_for_timeout(700)
    # fotos
    pg.click("#iaFoto"); pg.wait_for_selector("button[data-f]"); print("cartoes foto:", pg.locator("button[data-f]").count())
    pg.click('button[data-f="0"]'); print("conservacao:", pg.evaluate("IE.P.amostras[0].conservacao"), "|", pg.evaluate("IE.P.amostras[0].hist.slice(-1)[0].nota")[:60])
    # suspeitas
    pg.click("#iaSusp"); pg.wait_for_selector("#iaSuspR .card"); print("suspeitas:", pg.locator("#iaSuspR .card").count(), "|", pg.locator("#iaSuspR").inner_text()[:150].replace("\n"," "))
    pg.click("button[data-x]"); pg.wait_for_timeout(200); print("excluida usar=", pg.evaluate("IE.P.amostras.filter(a=>!a.usar).length>0"))
    # explicar sem modelo
    pg.click("#iaExp"); print("sem modelo:", pg.locator("#iaTxtR").inner_text()[:60].replace("\n"," "))
    pg.evaluate("IE.ultimoModelo={dep:'Valor',nc:0.8,R:{alertas_modelo:[],modelo:{n:53,k:3,r2:0.3123,r2_ajustado:0.28,erro_padrao_regressao:100.2,F:5,F_p_valor:0.001,nivel_confianca:0.8,nomes:['(Intercepto)','area'],coeficientes:[1,2],p_valores:[0.1,0.01],normalidade:{p_valor:0.2},heterocedasticidade_bp:{p_valor:0.03},durbin_watson:2,vif:{area:1.2}}}}")
    pg.click("#iaExp"); pg.wait_for_selector("#iaCopia"); print("texto:", pg.locator("#iaTxtR").inner_text()[:140].replace("\n"," "))
    b.close()
print("ERROS:",erros)
