import json, sys
from playwright.sync_api import sync_playwright
erros = []
def main(w, h, tag):
    with sync_playwright() as p:
        b = p.chromium.launch(executable_path="/usr/bin/google-chrome", args=["--no-sandbox"])
        pg = b.new_page(viewport={"width": w, "height": h})
        pg.on("pageerror", lambda e: erros.append(f"{tag} pageerror: {e}"))
        pg.on("console", lambda m: m.type == "error" and erros.append(f"{tag} console: {m.text}"))
        pg.goto("http://127.0.0.1:8765/coleta/teste1/resultado"); pg.wait_for_selector(".grow", timeout=8000)
        rows = pg.locator(".grow").count(); print(tag, "linhas renderizadas:", rows)
        print(tag, "kpis:", pg.locator(".sumario .kpis").inner_text().replace("\n", " "))
        pg.screenshot(path=f"/home/claude/e2e/{tag}_base.png")
        if tag == "desk":
            # edição inline: clicar célula de área, digitar, Enter
            col = pg.evaluate("IE.grid.cols.indexOf('area_privativa')")
            pg.click(f'.grow[data-r="0"] .gc[data-c="{col}"]'); pg.keyboard.type("77,5"); pg.keyboard.press("Enter")
            print("area linha0:", pg.evaluate("IE.grid.rows[0].area_privativa"), "orig:", pg.evaluate("JSON.stringify(IE.grid.rows[0]._orig)"))
            pg.keyboard.press("Control+z"); print("após desfazer:", pg.evaluate("IE.grid.rows[0].area_privativa"))
            pg.keyboard.press("Control+y"); print("após refazer:", pg.evaluate("IE.grid.rows[0].area_privativa"))
            # ordenar
            pg.click('.gh[data-k="valor_unitario"] span >> nth=0'); v = pg.evaluate("IE.grid.rows.slice(0,3).map(a=>IE.valor(a,'valor_unitario'))"); print("ordenado asc:", v)
            # busca
            pg.fill("#gBusca", "Pina"); print("busca Pina:", pg.evaluate("IE.grid.rows.length")); pg.fill("#gBusca", "")
            # densidades
            for d in ("compacto", "fotografico", "confortavel"):
                pg.select_option("#gDens", d); print("dens", d, pg.locator(".grow").count())
            pg.select_option("#gDens", "confortavel")
            # painel
            pg.click('.grow[data-r="1"] .gc[data-c="2"]', position={"x": 5, "y": 5}); pg.click("#gInsp"); pg.wait_for_selector(".insp.on"); print("painel:", pg.locator(".insp .hd b").inner_text())
            pg.screenshot(path="/home/claude/e2e/desk_insp.png"); pg.click(".insp [data-x]")
            # novo campo/variável
            pg.click("#gNova"); pg.fill("#nvN", "Padrão acabamento"); pg.select_option("#nvT", "discreta"); pg.click("#nvOk"); print("colunas:", pg.evaluate("IE.P.colunas.length"))
            # módulos
            for m in ["projetos", "avaliando", "pesquisa", "variaveis", "exploratoria", "matriz", "modelo", "geografia", "exportar", "banco", "ia", "base"]:
                pg.evaluate(f"location.hash='{m}'"); pg.wait_for_timeout(700)
                txt = pg.locator("#view").inner_text()[:90].replace("\n", " "); print("módulo", m, "→", txt)
                if m in ("exploratoria", "matriz"): pg.wait_for_timeout(1500); pg.screenshot(path=f"/home/claude/e2e/mod_{m}.png", full_page=False)
            # modelo: configurar variáveis e ajustar
            pg.evaluate("""(()=>{const V=IE.P.variaveis;V.forEach(v=>{v.papel='ignorar'});const s=(n,p)=>{const v=V.find(x=>x.campo===n);if(v)v.papel=p};s('valor_total','dependente');s('area_privativa','independente');s('quartos','independente');s('vagas','independente');IE.salvar();})()""")
            pg.evaluate("location.hash='avaliando'"); pg.wait_for_timeout(300)
            pg.fill('input[data-k="area_privativa"]', "85"); pg.fill('input[data-k="quartos"]', "3"); pg.fill('input[data-k="vagas"]', "2")
            pg.evaluate("location.hash='modelo'"); pg.wait_for_timeout(500); pg.click("#moGo"); pg.wait_for_selector("#moRes table", timeout=8000); pg.wait_for_timeout(500)
            print("modelo:", pg.locator("#moRes .chip").all_inner_texts()[:6]); print("estimativa:", pg.locator("#moRes").inner_text().split("Estimativa para o imóvel avaliando")[-1][:160].replace("\n", " "))
            pg.screenshot(path="/home/claude/e2e/mod_modelo.png", full_page=True)
            # persistência: recarregar sem coleta
            pg.goto("http://127.0.0.1:8765/base"); pg.wait_for_selector(".grow", timeout=8000); print("persistiu após recarregar:", pg.evaluate("IE.P.amostras.length"), "edição mantida:", pg.evaluate("IE.P.amostras.some(a=>a._orig&&a._orig.area_privativa!==undefined)"))
        else:
            ov = pg.evaluate("document.documentElement.scrollWidth > innerWidth + 2"); print(tag, "overflow horizontal da página:", ov)
        b.close()
main(1366, 800, "desk"); main(412, 860, "mobile")
print("ERROS:", erros or "nenhum")
