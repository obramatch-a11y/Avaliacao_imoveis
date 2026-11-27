from playwright.sync_api import sync_playwright
erros=[]
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox"]); pg=b.new_context(viewport={"width":1366,"height":800}).new_page()
    pg.on("pageerror",lambda e:erros.append(str(e))); pg.on("dialog",lambda d:d.accept("Boa Viagem 2025") if d.type=="prompt" else d.accept())
    pg.goto("http://127.0.0.1:8765/coleta/teste1/resultado"); pg.wait_for_selector(".grow"); pg.wait_for_timeout(500)
    pg.evaluate("location.hash='banco'"); pg.wait_for_timeout(600)
    print("imóveis no banco:", pg.locator("#bT tbody tr").count())
    for i in range(3): pg.locator("#bT input[data-k]").nth(i).check()
    pg.click("#bNovaCol"); pg.wait_for_timeout(300); print("coleções:", pg.locator("#bC option").all_inner_texts())
    pg.select_option("#bC","Boa Viagem 2025"); print("filtrado:", pg.locator("#bT tbody tr").count())
    with pg.expect_download() as d: pg.click("#bExpJ")
    d.value.save_as("/home/claude/e2e/banco.json")
    pg.evaluate("localStorage.removeItem('ie2-banco')"); pg.evaluate("location.reload()"); pg.wait_for_timeout(1500); pg.evaluate("location.hash='banco'"); pg.wait_for_timeout(500)
    print("após limpar:", pg.evaluate("Object.keys(IE.banco.ler()).length"))
    pg.set_input_files("#bImp","/home/claude/e2e/banco.json"); pg.wait_for_timeout(800); pg.evaluate("location.hash='banco'"); pg.wait_for_timeout(500)
    print("após importar:", pg.evaluate("Object.keys(IE.banco.ler()).length"), "coleção preservada:", pg.evaluate("Object.values(IE.banco.ler()).filter(e=>(e.colecoes||[]).length).length"))
    b.close()
print("ERROS:",erros)
