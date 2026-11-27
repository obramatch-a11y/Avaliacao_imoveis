import json
from playwright.sync_api import sync_playwright
erros=[]
def gem(route):
    req=json.loads(route.request.post_data)
    assert route.request.headers.get("x-goog-api-key")=="AIzaTESTE"
    txt=req["contents"][0]["parts"][0]["text"]
    if "Responda apenas" in txt: out="ok"
    else: out=json.dumps({"itens":[{"campo":"suites","valor":2,"evidencia":"2 suítes"},{"campo":"piscina","valor":True,"evidencia":"piscina"},{"campo":"idade","valor":10,"evidencia":"10 anos de construído"},{"campo":"vagas","valor":3,"evidencia":"3 vagas cobertas"}]})
    route.fulfill(json={"candidates":[{"content":{"parts":[{"text":out}]}}]})
drive={}
def gd(route):
    r=route.request; u=r.url
    assert r.headers.get("authorization")=="Bearer TOK"
    if "upload/drive" in u: drive["body"]=r.post_data; route.fulfill(json={"id":"F1","name":"IE-x.json","modifiedTime":"2026-11-27T13:00:00Z"})
    elif "alt=media" in u: route.fulfill(body=drive["body"].split("\r\n\r\n",2)[2].rsplit("\r\n--",1)[0], content_type="application/json")
    else: route.fulfill(json={"files":[{"id":"F1","name":"IE-projeto-x.json","modifiedTime":"2026-11-27T13:00:00Z"}]})
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox"]); pg=b.new_context(viewport={"width":1200,"height":800}).new_page()
    pg.on("pageerror",lambda e:erros.append(str(e)))
    pg.route("**/generativelanguage.googleapis.com/**",gem); pg.route("**/www.googleapis.com/**",gd)
    pg.route("**/auth/config",lambda r:r.fulfill(json={"login":True,"client_id":"cid.apps.googleusercontent.com"}))
    pg.route("**/accounts.google.com/gsi/client",lambda r:r.fulfill(content_type="text/javascript",body="window.google={accounts:{oauth2:{initTokenClient:function(o){return{requestAccessToken:function(){setTimeout(function(){o.callback({access_token:'TOK',expires_in:3600})},50)}}}}}};"))
    pg.goto("http://127.0.0.1:8765/coleta/teste1/resultado"); pg.wait_for_selector(".grow")
    # IA
    pg.evaluate("IE.P.amostras[0].titulo='Lindo apto com 2 suítes, piscina e 3 vagas cobertas. Prédio novo.'"); 
    pg.evaluate("location.hash='ia'"); pg.wait_for_timeout(400)
    pg.fill("#iaK","AIzaTESTE"); pg.click("#iaT"); pg.wait_for_selector("#iaS .chip.ok"); print("teste chave ok")
    pg.click("#iaE"); pg.wait_for_selector("#iaR table"); rows=pg.locator("#iaR tbody tr").all_inner_texts(); print("sugestões:",len(rows)); print(pg.locator("#iaR .note").all_inner_texts())
    pg.click('#iaR button[data-i="0"]'); print("suites aplicado:",pg.evaluate("IE.P.amostras[0].suites"), pg.evaluate("IE.P.amostras[0].hist.slice(-1)[0].tipo"))
    print("chave só local:", pg.evaluate("!!localStorage.getItem('ie2-ia')"))
    # Drive
    pg.evaluate("location.hash='nuvem'"); pg.wait_for_timeout(400); pg.click("#dCon"); pg.wait_for_selector("#dSt .chip.ok")
    pg.click("#dProj"); pg.wait_for_selector("#dSt .chip.ok:has-text('Salvo')"); print("salvo no drive; tamanho corpo:",len(drive["body"]))
    pg.click("#dLista"); pg.wait_for_selector("#dRes button[data-id]"); pg.click("#dRes button[data-id]"); pg.wait_for_selector("#dSt:has-text('restaurado')"); pg.wait_for_timeout(900)
    print("projetos após restaurar:", pg.evaluate("IE.indice().length"))
    b.close()
print("ERROS:",erros)
