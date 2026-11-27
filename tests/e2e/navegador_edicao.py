from playwright.sync_api import sync_playwright
erros=[]
with sync_playwright() as p:
    b=p.chromium.launch(executable_path="/usr/bin/google-chrome",args=["--no-sandbox"]); ctx=b.new_context(viewport={"width":1366,"height":800}, permissions=["clipboard-read","clipboard-write"]); pg=ctx.new_page()
    pg.on("pageerror",lambda e:erros.append(str(e)))
    pg.goto("http://127.0.0.1:8765/coleta/teste1/resultado"); pg.wait_for_selector(".grow")
    c=pg.evaluate("IE.grid.cols.indexOf('area_privativa')")
    # preencher para baixo: digita em linha0, seleciona 0..3, Ctrl+D
    pg.click(f'.grow[data-r="0"] .gc[data-c="{c}"]'); pg.keyboard.type("100"); pg.keyboard.press("Enter")
    pg.click(f'.grow[data-r="0"] .gc[data-c="{c}"]'); pg.keyboard.down("Shift"); pg.keyboard.press("ArrowDown"); pg.keyboard.press("ArrowDown"); pg.keyboard.up("Shift"); pg.keyboard.press("Control+d")
    print("fill-down:", pg.evaluate("IE.grid.rows.slice(0,4).map(a=>a.area_privativa)"))
    # copiar/colar interno: copia linha0 area -> cola em linha 5
    pg.click(f'.grow[data-r="0"] .gc[data-c="{c}"]'); pg.keyboard.press("Control+c"); pg.wait_for_timeout(200)
    pg.click(f'.grow[data-r="5"] .gc[data-c="{c}"]'); pg.keyboard.press("Control+v"); pg.wait_for_timeout(300)
    print("colar:", pg.evaluate("IE.grid.rows[5].area_privativa"))
    # colar bloco vindo do Excel (2x2) via evento paste
    pg.evaluate("""(()=>{const sc=document.querySelector('.gscroll');const dt=new DataTransfer();dt.setData('text','150\\t3\\n160\\t4');sc.focus();sc.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));})()""")
    pg.wait_for_timeout(200); pg.click(f'.grow[data-r="7"] .gc[data-c="{c}"]')
    pg.evaluate("""(()=>{const sc=document.querySelector('.gscroll');const dt=new DataTransfer();dt.setData('text','150\\t3\\n160\\t4');sc.dispatchEvent(new ClipboardEvent('paste',{clipboardData:dt,bubbles:true,cancelable:true}));})()""")
    pg.wait_for_timeout(300); print("bloco:", pg.evaluate("IE.grid.rows.slice(7,9).map(a=>[a.area_privativa,a.quartos])"))
    # filtro por coluna numérica
    pg.evaluate("IE.P.filtros={valor_total:{min:600000,max:900000}}; IE.grid.render()"); n=pg.evaluate("IE.grid.rows.length"); print("filtro 600-900k:", n, pg.evaluate("IE.grid.rows.every(a=>a.valor_total>=600000&&a.valor_total<=900000)"))
    pg.evaluate("IE.P.filtros={}; IE.grid.render()")
    # estado manual com justificativa e excluir da análise
    pg.evaluate("IE.definirEstado([3],'Excluído da análise','fora do padrão do avaliando'); IE.grid.render()")
    print("excluída usar=", pg.evaluate("IE.porId(3).usar"), "estado:", pg.evaluate("IE.estado(IE.porId(3)).estado"))
    # exportar xlsx
    pg.evaluate("location.hash='exportar'"); pg.wait_for_timeout(500)
    with pg.expect_download() as d: pg.click("#xXlsx")
    d.value.save_as("/home/claude/e2e/saida.xlsx"); print("xlsx baixado")
    with pg.expect_download() as d: pg.click("#xCsv")
    d.value.save_as("/home/claude/e2e/saida.csv")
    b.close()
print("ERROS JS:",[e for e in erros])
