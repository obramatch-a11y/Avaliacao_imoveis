import json
from playwright.sync_api import sync_playwright
erros=[]; salvou=[]
GIS="window.google={accounts:{id:{initialize:function(o){window.__cb=o.callback},renderButton:function(e){e.innerHTML='<button id=fakeG>Entrar</button>';e.firstChild.onclick=function(){window.__cb({credential:'CRED'})}}},oauth2:{initTokenClient:function(o){return{requestAccessToken:function(a){window.__prompt=a.prompt;setTimeout(function(){o.callback({access_token:'TOK',expires_in:3600})},30)}}}}}};"
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox"]); ctx=b.new_context(viewport={"width":1200,"height":800}); pg=ctx.new_page()
    pg.on("pageerror",lambda e:erros.append(str(e)))
    estado={"logado":False}
    pg.route("**/accounts.google.com/gsi/client",lambda r:r.fulfill(content_type="text/javascript",body=GIS))
    pg.route("**/auth/config",lambda r:r.fulfill(json={"login":True,"client_id":"cid","cofre":True,"usuario":{"nome":"Ana Brasil","email":"ana@x.com"} if estado["logado"] else None}))
    pg.route("**/auth/google",lambda r:(estado.update(logado=True),r.fulfill(json={"ok":True,"usuario":{"nome":"Ana Brasil","email":"ana@x.com"}}))[1])
    pg.route("**/auth/ia",lambda r:r.fulfill(json={"ok":True,"cofre":True,"chave":"AIzaDA_CONTA_DELA_123456","modelo":"gemini-2.5-flash"}) if r.request.method=="GET" else (salvou.append(r.request.post_data),r.fulfill(json={"ok":True}))[1])
    pg.route("**/www.googleapis.com/**",lambda r:r.fulfill(json={"id":"F1","name":"x","modifiedTime":"2026-11-27T13:00:00Z"}))
    pg.goto("http://127.0.0.1:8765/coleta/teste1/resultado"); pg.wait_for_selector(".grow"); pg.wait_for_selector("#fakeG")
    pg.click("#fakeG"); pg.wait_for_selector("#bSair"); print("logado:", pg.locator("#bLogin").inner_text().replace("\n"," "))
    pg.wait_for_timeout(500); print("chave veio da conta:", pg.evaluate("IE.ia.cfg.chave"))
    pg.evaluate("location.hash='nuvem'"); pg.wait_for_timeout(400); print("aviso conta:", "ana@x.com" in pg.locator("#view").inner_text())
    pg.click("#dCon"); pg.wait_for_selector("#dSt .chip.ok"); print("drive_auto:", pg.evaluate("IE.prefs.drive_auto"))
    # recarrega: deve reconectar em silêncio (prompt none) quando logado
    estado["logado"]=True; pg.reload(); pg.wait_for_selector("#bSair"); pg.wait_for_timeout(1200)
    print("reconexão silenciosa token:", pg.evaluate("IE.drive.token"), "prompt:", pg.evaluate("window.__prompt"))
    # sair limpa chave local
    pg.click("#bSair"); pg.wait_for_timeout(400); print("após sair chave local:", repr(pg.evaluate("IE.ia.cfg.chave")), "token:", pg.evaluate("IE.drive.token"))
    b.close()
print("ERROS:",erros)
