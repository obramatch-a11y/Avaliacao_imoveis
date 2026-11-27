/* Google Drive (backup na conta do próprio usuário, escopo drive.file) e assistente de IA com chave do usuário (Gemini, direto do navegador). */
(function (IE) {
  "use strict";
  var u = IE.u, $ = u.$, $$ = u.$$, esc = u.esc;
  function pagina(v, html) { v.innerHTML = '<div class="page">' + html + "</div>"; }
  function lerLS(k, d) { try { return JSON.parse(localStorage.getItem(k)) || d; } catch (e) { return d; } }

  /* ---- mescla de banco (usada também pelo Drive) ---- */
  IE.banco.mesclar = function (j) {
    if (!j || j.tipo !== "banco_ie" || !j.imoveis) throw new Error("Arquivo não é um backup do banco.");
    var B = IE.banco.ler(), n = 0, h = 0;
    Object.keys(j.imoveis).forEach(function (k) { var e = j.imoveis[k];
      if (!B[k]) { B[k] = e; n++; return; }
      e.hist.forEach(function (x) { if (!B[k].hist.some(function (y) { return y.d === x.d && y.v === x.v && y.ar === x.ar; })) { B[k].hist.push(x); h++; } });
      B[k].hist.sort(function (a, b) { return a.d < b.d ? -1 : 1; });
      (e.colecoes || []).forEach(function (c) { B[k].colecoes = B[k].colecoes || []; if (B[k].colecoes.indexOf(c) < 0) B[k].colecoes.push(c); }); });
    IE.banco.gravar(B); return { novos: n, historico: h };
  };

  /* ================= Google Drive ================= */
  var D = IE.drive = { token: null, exp: 0, cfg: null, SCOPE: "https://www.googleapis.com/auth/drive.file" };
  D.config = function () { if (D.cfg) return Promise.resolve(D.cfg); return fetch("/auth/config").then(function (r) { return r.json(); }).then(function (c) { D.cfg = c; return c; }); };
  D.carregaGIS = function () { return new Promise(function (ok, no) { if (window.google && google.accounts && google.accounts.oauth2) return ok(); var s = document.createElement("script"); s.src = "https://accounts.google.com/gsi/client"; s.async = true; s.onload = function () { ok(); }; s.onerror = function () { no(new Error("Não foi possível carregar o login do Google (rede ou bloqueador).")); }; document.head.appendChild(s); }); };
  D.conectar = function () {
    return D.config().then(function (c) { if (!c.client_id) throw new Error("O login com Google não está configurado neste servidor (falta GOOGLE_CLIENT_ID)."); return D.carregaGIS().then(function () { return c.client_id; }); }).then(function (cid) {
      return new Promise(function (ok, no) { var tc = google.accounts.oauth2.initTokenClient({ client_id: cid, scope: D.SCOPE, callback: function (r) { if (r.error) return no(new Error("Autorização negada ou falhou (" + r.error + ")")); D.token = r.access_token; D.exp = Date.now() + (r.expires_in || 3000) * 1000 - 60000; ok(); }, error_callback: function (e) { no(new Error("Janela de autorização fechada ou bloqueada (" + (e && e.type || "erro") + ").")); } }); tc.requestAccessToken({ prompt: D.token ? "" : "consent" }); }); });
  };
  D.garante = function () { return D.token && Date.now() < D.exp ? Promise.resolve() : D.conectar(); };
  D.api = function (url, opt) { return D.garante().then(function () { opt = opt || {}; opt.headers = Object.assign({ Authorization: "Bearer " + D.token }, opt.headers || {}); return fetch(url, opt); }).then(function (r) { if (r.status === 403) return r.json().catch(function () { return {}; }).then(function (j) { var m = (j.error && j.error.message) || ""; throw new Error(/has not been used|disabled/i.test(m) ? "A API do Google Drive não está ativada no projeto do Google Cloud (ative “Google Drive API”)." : "Acesso negado pelo Google: " + m); }); if (!r.ok) throw new Error("Erro do Google Drive (" + r.status + ")."); return r; }); };
  D.salvar = function (nome, texto, id) {
    var b = "ie" + Math.random().toString(36).slice(2), meta = JSON.stringify(id ? { name: nome } : { name: nome, mimeType: "application/json", description: "Backup Inferência Estatística" });
    var corpo = "--" + b + "\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n" + meta + "\r\n--" + b + "\r\nContent-Type: application/json\r\n\r\n" + texto + "\r\n--" + b + "--";
    return D.api("https://www.googleapis.com/upload/drive/v3/files" + (id ? "/" + id : "") + "?uploadType=multipart&fields=id,name,modifiedTime", { method: id ? "PATCH" : "POST", headers: { "Content-Type": "multipart/related; boundary=" + b }, body: corpo }).then(function (r) { return r.json(); });
  };
  D.listar = function () { return D.api("https://www.googleapis.com/drive/v3/files?q=" + encodeURIComponent("name contains 'IE-' and trashed=false") + "&orderBy=modifiedTime desc&pageSize=50&fields=files(id,name,modifiedTime,size)").then(function (r) { return r.json(); }).then(function (j) { return j.files || []; }); };
  D.baixar = function (id) { return D.api("https://www.googleapis.com/drive/v3/files/" + id + "?alt=media").then(function (r) { return r.text(); }); };

  IE.mod.nuvem = function (v) {
    var P = IE.P;
    pagina(v, '<h2>Google Drive — backup na sua conta</h2><p class="note">Seus dados continuam <b>neste navegador</b> (local-first). Aqui você grava e recupera <b>cópias de segurança</b> no <b>seu</b> Google Drive. O acesso usa o escopo <code>drive.file</code>: o aplicativo só enxerga os arquivos que ele mesmo criou, nunca o resto do seu Drive. O token fica só na memória desta aba; nada passa pelo servidor.</p>' +
      '<div class="card"><p class="note">Cada pessoa usa o <b>próprio</b> Drive: o Google mostra a conta dela para autorizar e os arquivos ficam na pasta dela. ' + (C.usuario ? "Você está logado como <b>" + esc(C.usuario.email) + "</b>." : "Entre com o Google (botão no topo) para associar a sua conta.") + '</p><p id="dSt" class="note">Verificando configuração…</p><p style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn pri" id="dCon">Conectar ao Google Drive</button><button class="btn" id="dProj" disabled>Salvar projeto atual</button><button class="btn" id="dBanco" disabled>Salvar banco local</button><button class="btn" id="dLista" disabled>Ver backups no Drive</button></p><div id="dRes"></div></div>');
    var st = $("#dSt", v), res = $("#dRes", v);
    D.config().then(function (c) { st.innerHTML = c.client_id ? "Pronto para conectar. Ao clicar, o Google pedirá sua autorização." : '<span class="chip bad">Login Google não configurado no servidor</span> (variáveis GOOGLE_CLIENT_ID e SESSION_SECRET).'; if (!c.client_id) $("#dCon", v).disabled = true; });
    function hab() { ["dProj", "dBanco", "dLista"].forEach(function (i) { $("#" + i, v).disabled = !D.token; }); if (!P) $("#dProj", v).disabled = true; }
    function erro(e) { st.innerHTML = '<span class="chip bad">' + esc(e.message || e) + "</span>"; }
    $("#dCon", v).addEventListener("click", function () { st.textContent = "Aguardando autorização…"; D.conectar().then(function () { IE.prefs.drive_auto = true; IE.savePrefs(); st.innerHTML = '<span class="chip ok">Conectado</span> ao Drive de ' + esc(C.usuario ? C.usuario.email : "sua conta Google") + ' (expira em cerca de 1 hora; reconecta sozinho nas próximas visitas e salva o projeto automaticamente cerca de 90 s após cada alteração).'; hab(); }).catch(erro); });
    $("#dProj", v).addEventListener("click", function () { var nome = "IE-projeto-" + IE.slug(P.nome) + "-" + P.id + ".json"; st.textContent = "Salvando…"; D.salvar(nome, IE.exportarProjeto(), P.drive_id).then(function (f) { P.drive_id = f.id; IE.salvar(); st.innerHTML = '<span class="chip ok">Salvo</span> ' + esc(f.name) + " · " + u.dataBR(f.modifiedTime); }).catch(erro); });
    $("#dBanco", v).addEventListener("click", function () { var id = IE.prefs.drive_banco; st.textContent = "Salvando…"; D.salvar("IE-banco-imobiliario.json", JSON.stringify({ tipo: "banco_ie", versao: 1, exportado: u.agora(), imoveis: IE.banco.ler() }), id).then(function (f) { IE.prefs.drive_banco = f.id; IE.savePrefs(); st.innerHTML = '<span class="chip ok">Salvo</span> ' + esc(f.name) + " · " + u.dataBR(f.modifiedTime); }).catch(erro); });
    $("#dLista", v).addEventListener("click", function () { st.textContent = "Consultando…"; D.listar().then(function (L) { st.textContent = L.length + " arquivo(s) criados por este aplicativo."; res.innerHTML = L.length ? '<table class="t"><thead><tr><th>Arquivo</th><th>Modificado</th><th></th></tr></thead><tbody>' + L.map(function (f) { return "<tr><td>" + esc(f.name) + "</td><td>" + u.dataBR(f.modifiedTime) + '</td><td><button class="btn sm" data-id="' + f.id + '" data-n="' + esc(f.name) + '">Restaurar</button></td></tr>'; }).join("") + "</tbody></table>" : '<p class="note">Nenhum backup ainda.</p>'; }).catch(erro); });
    res.addEventListener("click", function (e) { var b = e.target.closest("button[data-id]"); if (!b) return; st.textContent = "Baixando…"; D.baixar(b.dataset.id).then(function (t) { if (/banco/.test(b.dataset.n)) { var r = IE.banco.mesclar(JSON.parse(t)); st.innerHTML = '<span class="chip ok">Banco mesclado</span> ' + r.novos + " imóveis novos, " + r.historico + " registros de histórico (nada sobrescrito)."; } else { var id = IE.importarProjeto(t); IE.abrir(id); st.innerHTML = '<span class="chip ok">Projeto restaurado como cópia</span>'; setTimeout(function () { location.hash = "base"; IE.render(); }, 600); } }).catch(erro); });
    hab();
  };
  IE.registrar("nuvem", "Google Drive", IE.mod.nuvem);

  /* ================= IA: chave do próprio usuário (Gemini) ================= */
  var nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  var A = IE.ia = { cfg: lerLS("ie2-ia", { chave: "", modelo: "gemini-flash-latest" }) };
  if (!A.cfg.modelo || A.cfg.modelo === "gemini-2.5-flash") A.cfg.modelo = "gemini-flash-latest"; /* 2.5 foi descontinuado para contas novas */
  A.salvarCfg = function () { try { localStorage.setItem("ie2-ia", JSON.stringify(A.cfg)); } catch (e) {} };
  A.guardarNuvem = function () { var fd = new FormData(); fd.append("chave", A.cfg.chave); fd.append("modelo", A.cfg.modelo); return fetch("/auth/ia", { method: "POST", body: fd }).then(function (r) { return r.json(); }).then(function (j) { return !!j.ok; }).catch(function () { return false; }); };
  A.chamar1 = function (prompt, json, modelo) {
    if (!A.cfg.chave) return Promise.reject(new Error("Cole sua chave do Google AI Studio primeiro."));
    var body = { contents: [{ parts: [{ text: prompt }] }], generationConfig: { temperature: 0, responseMimeType: json ? "application/json" : "text/plain" } };
    return fetch("https://generativelanguage.googleapis.com/v1beta/models/" + encodeURIComponent(modelo || A.cfg.modelo) + ":generateContent", { method: "POST", headers: { "Content-Type": "application/json", "x-goog-api-key": A.cfg.chave }, body: JSON.stringify(body) }).then(function (r) { return r.json().then(function (j) { if (!r.ok) { var m = (j.error && j.error.message) || ""; throw new Error(r.status === 429 ? "Limite gratuito atingido (aguarde alguns minutos ou até o dia seguinte). " : r.status === 400 || r.status === 403 ? "Chave inválida ou sem permissão. " + m.slice(0, 120) : "Erro do serviço de IA (" + r.status + "). " + m.slice(0, 120)); } var t = j.candidates && j.candidates[0] && j.candidates[0].content && j.candidates[0].content.parts && j.candidates[0].content.parts.map(function (p) { return p.text || ""; }).join(""); if (!t) throw new Error("A IA não devolveu resposta utilizável."); return t; }); });
  };
  /* 503 = alta demanda temporária no Google: tenta de novo e, por fim, um modelo mais leve */
  A.chamar = function (prompt, json) {
    var esp = function (ms) { return new Promise(function (ok) { setTimeout(ok, ms); }); };
    var tenta = function (modelo, n) { return A.chamar1(prompt, json, modelo).catch(function (e) { if (/\(503\)/.test(e.message) && n > 0) return esp(2500).then(function () { return tenta(modelo, n - 1); }); throw e; }); };
    return tenta(A.cfg.modelo, 2).catch(function (e) { if (/\(503\)/.test(e.message)) return tenta("gemini-flash-lite-latest", 1); throw e; });
  };
  var CAMPOS = { quartos: "num", suites: "num", banheiros: "num", vagas: "num", andar: "num", idade: "num", area_construida: "num", area_territorial: "num", condominio: "num", iptu: "num", padrao: "txt", conservacao: "txt", elevador: "bool", piscina: "bool", varanda: "bool", vista_mar: "bool" };
  function norm(s) { return String(s || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/\s+/g, " "); }
  /* A IA só extrai o que está ESCRITO na descrição; cada sugestão precisa de trecho de evidência que exista literalmente no texto. */
  A.extrair = function (texto) {
    if (!A.cfg.chave) { /* sem chave própria: usa a IA da plataforma (exige login) */
      return fetch("/api/ia/extrair", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ texto: texto }) }).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.erro || "Falha na IA da plataforma."); A.modeloUsado = j.modelo; return { itens: j.itens, rejeitados: j.rejeitados }; }); });
    }
    return A.extrairComChave(texto);
  };
  A.extrairComChave = function (texto) {
    var p = "Você extrai dados de anúncios imobiliários brasileiros. Use SOMENTE o texto abaixo; não invente nada, não deduza o que não está escrito. Responda um JSON {\"itens\":[{\"campo\":\"...\",\"valor\":...,\"evidencia\":\"trecho copiado literalmente do texto\"}]}. Campos permitidos: " + Object.keys(CAMPOS).join(", ") + ". Booleanos como true/false (só true se o texto afirma; não use false por ausência). Se não houver dado explícito, devolva {\"itens\":[]}.\n\nTEXTO:\n" + texto;
    return A.chamar(p, true).then(function (t) { var j; try { j = JSON.parse(t.replace(/^```json|```$/g, "").trim()); } catch (e) { throw new Error("A IA devolveu um formato inesperado."); } var nt = norm(texto), out = [], rej = 0;
      (j.itens || []).forEach(function (it) { var tipo = CAMPOS[it.campo]; if (!tipo || it.valor == null || !it.evidencia || nt.indexOf(norm(it.evidencia)) < 0) { rej++; return; } var v = it.valor; if (tipo === "num") { v = u.parseNum(String(v)); if (v == null) { rej++; return; } } else if (tipo === "bool") { if (v !== true) { rej++; return; } v = 1; } else v = String(v); out.push({ campo: it.campo, valor: v, evidencia: it.evidencia }); }); return { itens: out, rejeitados: rej }; });
  };
  IE.mod.ia = function (v) {
    var P = IE.P, G = IE.grid, sel = P && G && G.rows && G.rows[G.act.r] ? G.rows[G.act.r] : (P ? P.amostras[0] : null);
    pagina(v, '<h2>Assistente de IA</h2><div class="warnbox">A plataforma funciona sem IA. Tudo que a IA sugere é <b>inferido</b>: nada é gravado sem o seu “Aceitar”, e só entram sugestões com <b>trecho de evidência que exista literalmente</b> na descrição do anúncio. A IA não calcula estatísticas, não inventa valores/coordenadas e não substitui a responsabilidade técnica do avaliador.</div>' +
      '<div class="card"><h3 style="margin-top:0">1. Extrair dados da descrição de uma amostra</h3><div class="infobox"><b>Como usar:</b> 1) cole a descrição do anúncio no quadro abaixo; 2) toque em <b>Extrair com IA</b>; 3) confira as sugestões e toque em <b>Aceitar</b> nas corretas.</div>' + (sel ? '<p>Amostra <b>#' + sel.id + "</b> — " + esc(sel.bairro || "") + '</p><textarea id="iaTxt" rows="5" style="width:100%;border:1px solid var(--line-2);border-radius:7px;background:var(--surface);padding:6px">' + esc(sel.descricao || sel.titulo || "") + '</textarea>' + (sel.descricao ? '<p class="note">✓ Descrição completa do anúncio carregada automaticamente. Você pode ajustar o texto.</p>' : '<p class="warnbox">Este anúncio veio só com o título (a fonte não informou a descrição). Cole abaixo a descrição completa do anúncio, se tiver, para a IA achar mais dados.</p>') + '<p><button class="btn pri" id="iaE">Extrair com IA</button></p><div id="iaR"></div></div><div class="card"><h3 style="margin-top:0">2. Extrair em várias amostras de uma vez</h3><p class="note">Usa a descrição guardada de cada anúncio (só as que têm descrição) e propõe apenas campos que estão <b>em branco</b>. Nada é gravado sem você tocar em Aplicar. Máximo de 15 amostras por vez, para poupar a cota gratuita.</p><p><button class="btn" id="iaLote">Extrair nas amostras com descrição</button></p><div id="iaLoteR"></div>' : '<p class="note">Abra um projeto com amostras.</p>') + "</div>" +
      "<div class=\"card\"><h3 style=\"margin-top:0\">3. Ler as fotos da amostra</h3><p class=\"note\">A IA olha até 3 fotos do anúncio da amostra ativa e sugere <b>conservação</b>, <b>padrão</b>, piscina e varanda. É uma <b>impressão visual</b> (marcada como inferida): confira antes de aceitar.</p>" + (sel && sel.fotos && sel.fotos.length ? '<p><button class="btn" id="iaFoto">Analisar fotos da amostra #' + sel.id + ' (' + Math.min(3, sel.fotos.length) + ')</button></p>' : '<p class="note">A amostra ativa não tem fotos.</p>') + '<div id="iaFotoR"></div></div>' +
      '<div class="card"><h3 style="margin-top:0">4. Achar amostras suspeitas</h3><p class="note">Procura preços por m² e áreas fora do padrão da própria base, incoerências (área × quartos), dados faltando e anúncios repetidos. <b>Não usa IA</b>: é estatística simples, sem custo e sem enviar nada. Você decide se exclui.</p><p><button class="btn" id="iaSusp">Procurar amostras suspeitas</button></p><div id="iaSuspR"></div></div>' +
      '<div class="card"><h3 style="margin-top:0">5. Explicar o modelo e rascunhar o laudo</h3><p class="note">Depois de ajustar o modelo no módulo <b>Modelo</b>, a IA explica o resultado em português simples e sugere o que verificar, ou redige um <b>rascunho</b> de metodologia e análise. Só números agregados são enviados (nunca dados de cliente). O texto é rascunho: confira cada número.</p><p><button class="btn" id="iaExp">Explicar o modelo</button> <button class="btn" id="iaLaudo">Rascunho do laudo</button></p><div id="iaTxtR"></div></div>' +
      '<details class="card"><summary style="cursor:pointer"><b>Avançado (opcional): usar a minha própria chave do Google</b></summary><p class="note" id="iaConta"></p><p class="note">A criação da chave <b>não pode ser automatizada</b>: o Google exige que você mesmo gere (1 clique, grátis, sem cartão) no Google AI Studio, logado na sua conta. Depois cole aqui. A chave fica <b>só neste navegador</b> e é enviada <b>direto ao Google</b>, nunca ao nosso servidor.</p><p><a class="btn" href="https://aistudio.google.com/apikey" target="_blank" rel="noopener noreferrer">Abrir Google AI Studio e criar chave ↗</a></p><div class="grid2" style="max-width:640px"><label class="f">Chave (começa com “AIza”)<input id="iaK" type="password" autocomplete="off" value="' + esc(A.cfg.chave) + '"></label><label class="f">Modelo<input id="iaM" value="' + esc(A.cfg.modelo) + '"></label></div><p style="display:flex;gap:8px;flex-wrap:wrap"><button class="btn pri" id="iaT">Salvar e testar</button><button class="btn" id="iaX">Apagar chave deste navegador</button><span id="iaS" class="note"></span></p><p class="note">Atenção à privacidade: no nível gratuito do Gemini, o Google pode usar o conteúdo enviado para melhorar seus produtos (nas regiões fora do Espaço Econômico Europeu, Reino Unido e Suíça). Por isso este assistente envia <b>somente a descrição pública do anúncio</b>, sem nome de cliente, contratante ou dados do seu projeto. Limites gratuitos são por projeto do Google e podem mudar.</p></details>');
    var S = $("#iaS", v);
    $("#iaT", v).addEventListener("click", function () { A.cfg.chave = $("#iaK", v).value.trim(); A.cfg.modelo = $("#iaM", v).value.trim() || "gemini-flash-latest"; A.salvarCfg(); S.textContent = "Testando…"; A.chamar("Responda apenas: ok", false).then(function () { S.innerHTML = '<span class="chip ok">Chave funcionando</span>' + (IE.conta.usuario ? " guardando na sua conta…" : ""); return IE.conta.usuario ? A.guardarNuvem().then(function (ok) { S.innerHTML = '<span class="chip ok">Chave funcionando</span> ' + (ok ? "e guardada, cifrada, na sua conta (disponível em qualquer aparelho após o login)." : "mas não foi possível guardar na conta (cofre indisponível); ficou só neste navegador."); }) : null; }).catch(function (e) { S.innerHTML = '<span class="chip bad">' + esc(e.message) + "</span>"; }); });
    $("#iaX", v).addEventListener("click", function () { A.cfg.chave = ""; A.salvarCfg(); if (IE.conta.usuario) fetch("/auth/ia/remover", { method: "POST" }); $("#iaK", v).value = ""; S.textContent = "Chave apagada."; });
    D.config().then(function (c) { var el = $("#iaConta", v); if (!el) return; if (c.ia_servidor) el.innerHTML = C.usuario ? '<span class="chip ok">IA da plataforma disponível para você</span> Nenhuma chave é necessária: use o passo 2 direto. (Limites por pessoa/dia protegem a cota gratuita.) Se preferir, pode usar a sua própria chave abaixo.' : '<span class="chip info">IA da plataforma</span> Entre com o Google (botão no topo) e use o passo 2 sem precisar de chave nenhuma.'; else el.innerHTML = ""; });
    var bE = $("#iaE", v); if (!bE) return;
    bE.addEventListener("click", function () { var R = $("#iaR", v), txt = $("#iaTxt", v).value.trim(); if (!txt) return u.toast("Sem texto para analisar.", true); R.innerHTML = '<p class="note">Consultando a IA…</p>';
      A.extrair(txt).then(function (r) { if (!r.itens.length) { R.innerHTML = '<div class="infobox">Nenhum dado explícito encontrado na descrição' + (r.rejeitados ? " (" + r.rejeitados + " sugestão(ões) da IA descartadas por não terem evidência literal no texto)" : "") + ".</div>"; return; }
        var cart = r.itens.map(function (it, i) { var d = IE.colDef(it.campo), at = sel[it.campo] == null ? "não preenchido" : sel[it.campo], dif = sel[it.campo] != null && String(sel[it.campo]) !== String(it.valor);
          return '<div class="card" style="margin:8px 0;padding:10px"><div><b>' + esc(d.label) + ":</b> " + esc(it.valor) + ' <span class="chip warn">inferido por IA</span></div><div class="note">Hoje na amostra: ' + esc(at) + (dif ? " ⚠ diferente" : "") + "</div><div class=\"note\"><i>Trecho do anúncio: “" + esc(it.evidencia) + '”</i></div><p style="margin:6px 0 0"><button class="btn sm pri" data-i="' + i + '">Aceitar</button></p></div>'; }).join("");
        R.innerHTML = '<p><b>' + r.itens.length + ' sugestão(ões).</b> Toque em <b>Aceitar</b> só nas que estiverem corretas.</p>' + cart + '<p><button class="btn" id="iaTodos">Aceitar todas</button></p>' + (r.rejeitados ? '<p class="note">' + r.rejeitados + " sugestão(ões) descartadas por falta de evidência literal.</p>" : "");
        var aceitar = function (b) { var it = r.itens[+b.dataset.i], l = []; if (IE.setVal(sel, it.campo, it.valor, l)) { sel.hist.push({ t: u.agora(), tipo: "ia", campo: it.campo, nota: "Sugerido por IA (" + (A.cfg.chave ? A.cfg.modelo : (A.modeloUsado || "plataforma")) + "), evidência: “" + it.evidencia + "”; aceito pelo avaliador" }); IE.commit(l); } b.disabled = true; b.textContent = "Aceito ✓"; var cx = b.closest(".card"); if (cx && !cx.querySelector(".gravou")) { var m = document.createElement("div"); m.className = "infobox gravou"; m.innerHTML = "✓ Gravado na <b>amostra #" + sel.id + "</b>. Veja na <a href=\"#base\">Base amostral</a> (o valor aparece na coluna correspondente e fica registrado no histórico como “sugerido por IA”). Para desfazer, use Ctrl+Z ou o botão Desfazer da Base."; cx.appendChild(m); } };
        $("#iaTodos", R).addEventListener("click", function () { [].forEach.call(R.querySelectorAll("button[data-i]:not([disabled])"), aceitar); u.toast("Sugestões aceitas."); });
        R.onclick = function (e) { var b = e.target.closest("button[data-i]"); if (b && !b.disabled) aceitar(b); };
      }).catch(function (e) { R.innerHTML = '<div class="warnbox">' + esc(e.message) + "</div>"; }); });

    var bL = $("#iaLote", v); if (bL) bL.addEventListener("click", function () {
      var R = $("#iaLoteR", v), cand = IE.P.amostras.filter(function (a) { return a.descricao && a.descricao.length > 20; }).slice(0, 15);
      if (!cand.length) { R.innerHTML = '<div class="infobox">Nenhuma amostra tem descrição guardada. Anúncios coletados só com título não podem ser lidos pela IA.</div>'; return; }
      var props = [], i = 0, falha = "";
      var prox = function () { if (i >= cand.length || falha) return fim(); var a = cand[i++]; R.innerHTML = '<p class="note">Lendo ' + i + " de " + cand.length + "…</p>";
        return A.extrair(a.descricao).then(function (r) { r.itens.forEach(function (it) { if (a[it.campo] == null || a[it.campo] === "") props.push({ a: a, it: it }); }); }).catch(function (e) { falha = e.message; }).then(prox); };
      var fim = function () { if (!props.length) { R.innerHTML = '<div class="infobox">' + (falha ? esc(falha) : "Nenhum campo em branco pôde ser preenchido com segurança.") + "</div>"; return; }
        R.innerHTML = "<p><b>" + props.length + " campo(s) em branco</b> podem ser preenchidos em " + new Set(props.map(function (x) { return x.a.id; })).size + " amostra(s)." + (falha ? " (Parou antes do fim: " + esc(falha) + ")" : "") + '</p><div class="note">' + props.slice(0, 12).map(function (x) { return "#" + x.a.id + " " + esc(IE.colDef(x.it.campo).label) + " = " + esc(x.it.valor) + " <i>(“" + esc(x.it.evidencia) + "”)</i>"; }).join("<br>") + (props.length > 12 ? "<br>… e mais " + (props.length - 12) : "") + '</div><p><button class="btn pri" id="iaAplica">Aplicar ' + props.length + ' sugestão(ões)</button></p>';
        $("#iaAplica", R).addEventListener("click", function () { var l = []; props.forEach(function (x) { if (IE.setVal(x.a, x.it.campo, x.it.valor, l)) x.a.hist.push({ t: u.agora(), tipo: "ia", campo: x.it.campo, nota: "Sugerido por IA (" + (A.cfg.chave ? A.cfg.modelo : (A.modeloUsado || "plataforma")) + "), evidência: “" + x.it.evidencia + "”; aplicado em lote pelo avaliador" }); }); IE.commit(l); R.innerHTML = '<div class="infobox">✓ ' + props.length + " sugestão(ões) aplicada(s).</div>"; }); };
      prox();
    });

    /* ---- 3. fotos ---- */
    var bF = $("#iaFoto", v); if (bF) bF.addEventListener("click", function () {
      var R = $("#iaFotoR", v); R.innerHTML = '<p class="note">Baixando e analisando as fotos…</p>';
      fetch("/api/ia/fotos", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ fotos: sel.fotos.slice(0, 3) }) }).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.erro || "Falha na IA."); return j; }); }).then(function (j) {
        if (!j.itens.length) { R.innerHTML = '<div class="infobox">As fotos não permitiram concluir nada com segurança.' + (j.observacoes ? " " + esc(j.observacoes) : "") + "</div>"; return; }
        R.innerHTML = "<p><b>" + j.itens.length + " impressão(ões) visual(is)</b> em " + j.fotos_lidas + " foto(s). Confira antes de aceitar.</p>" + j.itens.map(function (it, i) { var d = IE.colDef(it.campo); return '<div class="card" style="margin:8px 0;padding:10px"><div><b>' + esc(d.label) + ":</b> " + esc(it.valor === 1 ? "sim" : it.valor) + ' <span class="chip warn">inferido pela foto</span> <span class="chip">confiança ' + esc(it.confianca) + '</span></div><div class="note">Hoje na amostra: ' + esc(sel[it.campo] == null || sel[it.campo] === "" ? "não preenchido" : sel[it.campo]) + '</div><div class="note"><i>O que a IA viu: ' + esc(it.evidencia) + '</i></div><p style="margin:6px 0 0"><button class="btn sm pri" data-f="' + i + '">Aceitar</button></p></div>'; }).join("") + (j.observacoes ? '<p class="note">' + esc(j.observacoes) + "</p>" : "");
        R.onclick = function (e) { var b = e.target.closest("button[data-f]"); if (!b || b.disabled) return; var it = j.itens[+b.dataset.f], l = [];
          if (IE.setVal(sel, it.campo, it.valor, l)) { sel.hist.push({ t: u.agora(), tipo: "ia", campo: it.campo, nota: "Impressão visual de IA (" + (j.modelo || "plataforma") + ") a partir das fotos: " + it.evidencia + "; confiança " + it.confianca + "; aceito pelo avaliador" }); IE.commit(l); } b.disabled = true; b.textContent = "Aceito ✓"; };
      }).catch(function (e) { R.innerHTML = '<div class="warnbox">' + esc(e.message) + "</div>"; }); });

    /* ---- 4. amostras suspeitas (sem IA) ---- */
    var bS = $("#iaSusp", v); if (bS) bS.addEventListener("click", function () {
      var A_ = IE.P.amostras, R = $("#iaSuspR", v), med = function (x) { var y = x.slice().sort(function (a, b) { return a - b; }), n = y.length; return n ? (n % 2 ? y[(n - 1) / 2] : (y[n / 2 - 1] + y[n / 2]) / 2) : null; },
        q = function (x, p) { var y = x.slice().sort(function (a, b) { return a - b; }); if (!y.length) return null; var i = (y.length - 1) * p, lo = Math.floor(i), hi = Math.ceil(i); return y[lo] + (y[hi] - y[lo]) * (i - lo); },
        cerca = function (x) { var a = q(x, 0.25), b = q(x, 0.75); if (a == null) return null; var d = b - a; return { lo: a - 1.5 * d, hi: b + 1.5 * d, m: med(x) }; };
      var pu = [], ar = []; A_.forEach(function (a) { var vt = Number(a.valor_total), ap = Number(a.area_privativa); if (vt > 0 && ap > 0) pu.push(vt / ap); if (ap > 0) ar.push(ap); });
      var cp = cerca(pu), ca = cerca(ar), vistos = {}, ach = [];
      A_.forEach(function (a) { var m = [], vt = Number(a.valor_total), ap = Number(a.area_privativa), qt = Number(a.quartos);
        if (!(vt > 0)) m.push("sem valor total"); if (!(ap > 0)) m.push("sem área privativa");
        if (vt > 0 && ap > 0 && cp) { var p = vt / ap; if (p > cp.hi) m.push("R$/m² muito alto (" + nf0.format(p) + " contra mediana " + nf0.format(cp.m) + ")"); else if (p < cp.lo) m.push("R$/m² muito baixo (" + nf0.format(p) + " contra mediana " + nf0.format(cp.m) + ")"); }
        if (ap > 0 && ca && (ap > ca.hi || ap < ca.lo)) m.push("área fora do padrão da base (" + nf0.format(ap) + " m²; mediana " + nf0.format(ca.m) + ")");
        if (ap > 0 && qt > 0 && ap / qt < 12) m.push("área pequena demais para " + qt + " quarto(s)"); if (qt > 6) m.push("muitos quartos (" + qt + ")");
        var ch = [a.bairro || "", vt, ap, a.quartos || ""].join("|"); if (vt > 0 && vistos[ch]) m.push("possível repetido da amostra #" + vistos[ch]); else if (vt > 0) vistos[ch] = a.id;
        if (m.length) ach.push({ a: a, m: m }); });
      if (!ach.length) { R.innerHTML = '<div class="infobox">Nenhuma amostra fora do padrão encontrada (' + A_.length + " analisadas).</div>"; return; }
      R.innerHTML = "<p><b>" + ach.length + " de " + A_.length + " amostra(s) merecem atenção.</b> É um alerta, não uma decisão: um preço alto pode ser um imóvel diferente, não um erro.</p>" + ach.map(function (x, i) { return '<div class="card" style="margin:8px 0;padding:10px"><div><b>Amostra #' + x.a.id + "</b> — " + esc(x.a.bairro || "") + (x.a.usar ? "" : ' <span class="chip">já fora da análise</span>') + '</div><div class="note">' + x.m.map(esc).join("<br>") + "</div>" + (x.a.usar ? '<p style="margin:6px 0 0"><button class="btn sm" data-x="' + i + '">Excluir da análise</button></p>' : "") + "</div>"; }).join("");
      R.onclick = function (e) { var b = e.target.closest("button[data-x]"); if (!b || b.disabled) return; var x = ach[+b.dataset.x]; IE.definirEstado([x.a.id], "Excluído da análise", "Alerta de amostra suspeita: " + x.m.join("; ")); b.disabled = true; b.textContent = "Excluída ✓"; };
    });

    /* ---- 5. explicar modelo / rascunho do laudo ---- */
    function dadosModelo() {
      var M = IE.ultimoModelo; if (!M) return null; var m = M.R.modelo, bp = m.heterocedasticidade_bp || {}, f = function (x) { return typeof x === "number" ? Math.round(x * 10000) / 10000 : x; };
      return { variavel_dependente: M.dep, nivel_confianca: m.nivel_confianca, n: m.n, k: m.k, r2: f(m.r2), r2_ajustado: f(m.r2_ajustado), erro_padrao_regressao: f(m.erro_padrao_regressao), F: f(m.F), F_p_valor: f(m.F_p_valor),
        coeficientes: m.nomes.map(function (nm, i) { return { variavel: nm, coef: f(m.coeficientes[i]), p_valor: f(m.p_valores[i]) }; }),
        normalidade_p_valor: f(m.normalidade && m.normalidade.p_valor), heterocedasticidade_p_valor: f(bp.p_valor != null ? bp.p_valor : bp.p), durbin_watson: f(m.durbin_watson),
        vif_maximo: m.vif ? f(Math.max.apply(null, Object.keys(m.vif).map(function (k2) { return m.vif[k2]; }))) : null, alertas: M.R.alertas_modelo || [], total_amostras_na_base: IE.P.amostras.length };
    }
    function gerar(tipo) { var R = $("#iaTxtR", v), d = dadosModelo(); if (!d) { R.innerHTML = '<div class="infobox">Ajuste um modelo primeiro: abra o módulo <b>Modelo</b>, escolha as variáveis e toque em ajustar. Depois volte aqui.</div>'; return; }
      R.innerHTML = '<p class="note">Escrevendo…</p>';
      fetch("/api/ia/texto", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ tipo: tipo, dados: d }) }).then(function (r) { return r.json().then(function (j) { if (!r.ok) throw new Error(j.erro || "Falha na IA."); return j; }); }).then(function (j) {
        R.innerHTML = '<div class="warnbox"><b>Rascunho gerado por IA.</b> Confira cada número com a tela do Modelo. A responsabilidade técnica é sua.' + (j.numeros_fora.length ? "<br><b>Atenção:</b> estes números aparecem no texto mas não nos dados do modelo: " + esc(j.numeros_fora.join(", ")) + "." : "") + '</div><div class="card" style="white-space:pre-wrap;padding:10px">' + esc(j.texto) + '</div><p><button class="btn" id="iaCopia">Copiar texto</button></p>';
        $("#iaCopia", R).addEventListener("click", function () { (navigator.clipboard ? navigator.clipboard.writeText(j.texto) : Promise.reject()).then(function () { u.toast("Texto copiado."); }, function () { u.toast("Não consegui copiar; selecione o texto.", true); }); });
      }).catch(function (e) { R.innerHTML = '<div class="warnbox">' + esc(e.message) + "</div>"; }); }
    $("#iaExp", v).addEventListener("click", function () { gerar("explicar"); }); $("#iaLaudo", v).addEventListener("click", function () { gerar("laudo"); });
  };
  IE.registrar("ia", "IA", IE.mod.ia);

  /* ---- login Google: cada pessoa usa o PRÓPRIO Drive e a PRÓPRIA chave de IA ---- */
  var C = IE.conta = { usuario: null, cofre: false };
  function pintaLogin() {
    var el = $("#bLogin"); if (!el) return;
    if (C.usuario) { el.innerHTML = '<span class="note" style="color:#cfe">' + esc(C.usuario.nome.split(" ")[0]) + '</span><button class="btn sm" id="bSair">Sair</button>'; $("#bSair").addEventListener("click", function () { fetch("/auth/sair", { method: "POST" }).then(function () { C.usuario = null; D.token = null; IE.prefs.drive_auto = false; IE.savePrefs(); A.cfg.chave = ""; A.salvarCfg(); pintaLogin(); if (IE.atual === "nuvem" || IE.atual === "ia") IE.render(); }); }); return; }
    if (!C.clientId) { el.innerHTML = ""; return; }
    el.innerHTML = '<span id="gBtnBase"></span>';
    D.carregaGIS().then(function () { return new Promise(function (ok) { if (google.accounts.id) return ok(); var s = document.createElement("script"); s.src = "https://accounts.google.com/gsi/client"; s.onload = ok; document.head.appendChild(s); }); }).then(function () {
      google.accounts.id.initialize({ client_id: C.clientId, callback: function (r) { var fd = new FormData(); fd.append("credential", r.credential); fetch("/auth/google", { method: "POST", body: fd }).then(function (x) { return x.json(); }).then(function (j) { if (j.ok) { C.usuario = j.usuario; pintaLogin(); aposLogin(true); u.toast("Conectado como " + j.usuario.email + ". Agora conecte o seu Drive no módulo Google Drive."); } else u.toast(j.erro || "Login não confirmado.", true); }).catch(function () { u.toast("Falha de rede no login.", true); }); }, ux_mode: "popup" });
      google.accounts.id.renderButton($("#gBtnBase"), { theme: "outline", size: "medium", text: "signin", locale: "pt-BR" }); }).catch(function () { el.innerHTML = ""; });
  }
  function aposLogin(novo) {
    if (!C.usuario) return;
    fetch("/auth/ia").then(function (r) { return r.json(); }).then(function (j) { if (j.cofre && j.chave) { A.cfg.chave = j.chave; if (j.modelo) A.cfg.modelo = (j.modelo === "gemini-2.5-flash" ? "gemini-flash-latest" : j.modelo); A.salvarCfg(); if (IE.atual === "ia") IE.render(); } else if (j.cofre && A.cfg.chave) A.guardarNuvem(); }).catch(function () {});
    /* Drive: reconexão silenciosa se esta pessoa já autorizou antes; a primeira vez exige o clique em Conectar (regra do Google) */
    if (IE.prefs.drive_auto) { D.conectarSilencioso().catch(function () {}); }
  }
  D.conectarSilencioso = function () { return D.config().then(function (c) { return D.carregaGIS().then(function () { return new Promise(function (ok, no) { var tc = google.accounts.oauth2.initTokenClient({ client_id: c.client_id, scope: D.SCOPE, hint: C.usuario && C.usuario.email, callback: function (r) { if (r.error) return no(new Error(r.error)); D.token = r.access_token; D.exp = Date.now() + (r.expires_in || 3000) * 1000 - 60000; ok(); }, error_callback: function (e) { no(e); } }); tc.requestAccessToken({ prompt: "none" }); }); }); }); };
  D.autoBackup = function () { if (!D.token || !IE.P || !IE.prefs.drive_auto || D._t) return; D._t = setTimeout(function () { D._t = null; var P = IE.P; if (!P || !D.token) return; D.salvar("IE-projeto-" + IE.slug(P.nome) + "-" + P.id + ".json", IE.exportarProjeto(), P.drive_id).then(function (f) { P.drive_id = f.id; try { localStorage.setItem("ie2-proj-" + P.id, JSON.stringify(P)); } catch (e) {} }).catch(function () {}); }, 90000); };
  IE.on("dados", function () { D.autoBackup(); });
  fetch("/auth/config").then(function (r) { return r.json(); }).then(function (c) { C.clientId = c.login ? c.client_id : ""; C.cofre = !!c.cofre; C.usuario = c.usuario || null; pintaLogin(); if (C.usuario) aposLogin(false); }).catch(function () {});

  var ordem = ["projetos", "avaliando", "pesquisa", "base", "variaveis", "exploratoria", "matriz", "modelo", "geografia", "exportar", "banco", "nuvem", "ia"];
  IE.modulos.sort(function (a, b) { return ordem.indexOf(a.id) - ordem.indexOf(b.id); });
})(window.IE);
