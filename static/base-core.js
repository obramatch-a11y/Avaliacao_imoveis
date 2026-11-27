/* Base amostral — núcleo: utilidades, projeto (local-first), estados, variáveis, histórico, roteador. */
window.IE = window.IE || {};
(function (IE) {
  "use strict";
  var $ = function (s, r) { return (r || document).querySelector(s); };
  var $$ = function (s, r) { return Array.prototype.slice.call((r || document).querySelectorAll(s)); };
  var esc = function (s) { return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) { return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]; }); };
  var nf0 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 0 });
  var nf2 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 2 });
  var nf4 = new Intl.NumberFormat("pt-BR", { maximumFractionDigits: 4 });
  function num(v) { if (v === null || v === undefined || v === "" || typeof v === "boolean") return v === true ? 1 : v === false ? 0 : null; var n = typeof v === "number" ? v : parseNum(v); return n == null || isNaN(n) ? null : n; }
  function parseNum(s) {
    if (typeof s === "number") return s; s = String(s == null ? "" : s).trim().replace(/[R$\s%m²]/g, ""); if (!s) return null;
    if (s.indexOf(",") >= 0) s = s.replace(/\./g, "").replace(",", "."); else if (/^\d{1,3}(\.\d{3})+$/.test(s)) s = s.replace(/\./g, "");
    var n = Number(s); return isNaN(n) ? null : n;
  }
  var uid = function () { return Date.now().toString(36) + Math.random().toString(36).slice(2, 7); };
  function toast(msg, err) { var t = $("#toast"); t.textContent = msg; t.className = "toast on" + (err ? " err" : ""); clearTimeout(toast._t); toast._t = setTimeout(function () { t.className = "toast"; }, err ? 5000 : 2200); }
  function agora() { return new Date().toISOString(); }
  function hhmm(iso) { var d = iso ? new Date(iso) : new Date(); return d.toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" }); }
  function dataBR(iso) { return new Date(iso).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" }); }
  IE.u = { $: $, $$: $$, esc: esc, nf0: nf0, nf2: nf2, nf4: nf4, num: num, parseNum: parseNum, uid: uid, toast: toast, agora: agora, hhmm: hhmm, dataBR: dataBR };

  /* ------------------------------ colunas padrão da base ------------------------------ */
  // tipo: num | text | cat | bool | link | foto | estado ; grupo para o seletor de colunas
  IE.COLS = [
    { k: "_usar", label: "Usar", tipo: "usar", w: 46, fixa: true, grupo: "Controle" },
    { k: "id", label: "ID", tipo: "num", w: 52, grupo: "Identificação", fixa: true },
    { k: "foto", label: "Foto", tipo: "foto", w: 96, grupo: "Identificação", fixa: true },
    { k: "estado", label: "Situação", tipo: "estado", w: 200, grupo: "Qualificação" },
    { k: "fonte", label: "Fonte", tipo: "cat", w: 110, grupo: "Origem" },
    { k: "url", label: "Link original", tipo: "link", w: 90, grupo: "Origem" },
    { k: "data_coleta", label: "Data da coleta", tipo: "text", w: 100, grupo: "Origem" },
    { k: "tipo", label: "Tipo de imóvel", tipo: "cat", w: 100, grupo: "Imóvel" },
    { k: "natureza", label: "Natureza", tipo: "cat", w: 80, grupo: "Imóvel", editavel: true },
    { k: "uf", label: "UF", tipo: "cat", w: 44, grupo: "Localização" },
    { k: "cidade", label: "Cidade", tipo: "cat", w: 120, grupo: "Localização" },
    { k: "bairro", label: "Bairro", tipo: "cat", w: 130, grupo: "Localização", editavel: true },
    { k: "endereco", label: "Endereço", tipo: "text", w: 180, grupo: "Localização", editavel: true },
    { k: "latitude", label: "Latitude", tipo: "num", w: 90, grupo: "Localização", editavel: true, dec: 6 },
    { k: "longitude", label: "Longitude", tipo: "num", w: 90, grupo: "Localização", editavel: true, dec: 6 },
    { k: "area_privativa", label: "Área privativa (m²)", tipo: "num", w: 100, grupo: "Áreas", editavel: true, dec: 2 },
    { k: "area_construida", label: "Área construída (m²)", tipo: "num", w: 106, grupo: "Áreas", editavel: true, dec: 2 },
    { k: "area_territorial", label: "Área territorial (m²)", tipo: "num", w: 106, grupo: "Áreas", editavel: true, dec: 2 },
    { k: "valor_total", label: "Preço total (R$)", tipo: "num", w: 106, grupo: "Valores", editavel: true, dec: 0, forte: true },
    { k: "valor_unitario", label: "Preço unitário (R$/m²)", tipo: "num", w: 112, grupo: "Valores", calc: true, dec: 0 },
    { k: "quartos", label: "Quartos", tipo: "num", w: 64, grupo: "Características", editavel: true, dec: 0 },
    { k: "suites", label: "Suítes", tipo: "num", w: 58, grupo: "Características", editavel: true, dec: 0 },
    { k: "banheiros", label: "Banheiros", tipo: "num", w: 70, grupo: "Características", editavel: true, dec: 0 },
    { k: "vagas", label: "Vagas", tipo: "num", w: 56, grupo: "Características", editavel: true, dec: 0 },
    { k: "andar", label: "Andar", tipo: "num", w: 56, grupo: "Características", editavel: true, dec: 0 },
    { k: "idade", label: "Idade (anos)", tipo: "num", w: 80, grupo: "Características", editavel: true, dec: 0 },
    { k: "padrao", label: "Padrão construtivo", tipo: "cat", w: 110, grupo: "Características", editavel: true },
    { k: "conservacao", label: "Conservação", tipo: "cat", w: 100, grupo: "Características", editavel: true },
    { k: "elevador", label: "Elevador", tipo: "bool", w: 70, grupo: "Características", editavel: true },
    { k: "piscina", label: "Piscina", tipo: "bool", w: 62, grupo: "Características", editavel: true },
    { k: "varanda", label: "Varanda", tipo: "bool", w: 68, grupo: "Características", editavel: true },
    { k: "vista_mar", label: "Vista p/ o mar", tipo: "bool", w: 90, grupo: "Características", editavel: true },
    { k: "churrasqueira", label: "Churrasqueira", tipo: "bool", w: 90, grupo: "Características", editavel: true },
    { k: "portaria_24h", label: "Portaria 24h", tipo: "bool", w: 84, grupo: "Características", editavel: true },
    { k: "condominio", label: "Condomínio (R$)", tipo: "num", w: 100, grupo: "Valores", editavel: true, dec: 0 },
    { k: "iptu", label: "IPTU (R$)", tipo: "num", w: 80, grupo: "Valores", editavel: true, dec: 0 },
    { k: "distancias", label: "Distâncias relevantes", tipo: "text", w: 150, grupo: "Localização", editavel: true },
    { k: "obs", label: "Observações técnicas", tipo: "text", w: 200, grupo: "Qualificação", editavel: true },
    { k: "titulo", label: "Descrição original", tipo: "text", w: 220, grupo: "Origem" }
  ];
  IE.COLS_PADRAO = ["_usar", "id", "foto", "estado", "fonte", "bairro", "area_privativa", "valor_total", "valor_unitario", "quartos", "banheiros", "vagas", "url"];
  IE.COLS_MAP = {}; IE.COLS.forEach(function (c) { IE.COLS_MAP[c.k] = c; });
  IE.ESTADOS = ["Coletado", "Compatível com os filtros", "Incompleto", "Suspeito", "Possível duplicidade", "Em revisão", "Selecionado", "Validado pelo avaliador", "Excluído da análise"];
  IE.ESTADO_CLASSE = { "Coletado": "", "Compatível com os filtros": "ok", "Incompleto": "warn", "Suspeito": "bad", "Possível duplicidade": "warn", "Em revisão": "info", "Selecionado": "ok", "Validado pelo avaliador": "ok", "Excluído da análise": "bad" };
  IE.MANUAIS = ["Em revisão", "Selecionado", "Validado pelo avaliador", "Excluído da análise"];
  IE.NIVEIS_DENS = ["compacto", "confortavel", "fotografico"];

  /* ------------------------------ projeto (local-first) ------------------------------ */
  var P = IE.P = null; // projeto aberto
  var K_IDX = "ie2-index", K_PROJ = "ie2-proj-", K_PREF = "ie2-prefs", K_BANCO = "ie2-banco";
  function lerJSON(k, d) { try { var v = localStorage.getItem(k); return v ? JSON.parse(v) : d; } catch (e) { return d; } }
  IE.prefs = lerJSON(K_PREF, {});
  IE.savePrefs = function () { try { localStorage.setItem(K_PREF, JSON.stringify(IE.prefs)); } catch (e) {} };
  IE.indice = function () { return lerJSON(K_IDX, []); };
  function gravaIndice(l) { try { localStorage.setItem(K_IDX, JSON.stringify(l)); } catch (e) {} }

  IE.novoProjeto = function (nome, extra) {
    var p = Object.assign({
      v: 2, id: uid(), nome: nome || "Novo projeto", contratante: "", finalidade_trabalho: "", data_ref: new Date().toISOString().slice(0, 10), observacoes: "",
      criado: agora(), atualizado: agora(), arquivado: false, coleta_id: null, params_originais: null, meta: null,
      avaliando: { endereco: "", latitude: "", longitude: "", tipologia: "", area_privativa: "", area_construida: "", area_territorial: "", padrao: "", conservacao: "", idade: "", caracteristicas: "", quartos: "", suites: "", banheiros: "", vagas: "", andar: "", extras: {} },
      amostras: [], variaveis: IE.variaveisPadrao(), colunas: IE.COLS_PADRAO.slice(), larguras: {}, ordem: null, ordenacao: null, filtros: {}, visoes: {}, densidade: "confortavel", fixas: 4,
      matrizes: [], modelo_cfg: { nivel: 0.80 }, colecoes: {}, historico_projeto: [{ t: agora(), tipo: "criacao", nota: "Projeto criado" }]
    }, extra || {});
    return p;
  };
  IE.variaveisPadrao = function () {
    function v(nome, campo, tipo, papel, un, desc) { return { nome: nome, tecnico: campo, campo: campo, descricao: desc || "", unidade: un || "", tipo: tipo, papel: papel, origem: "coleta", regra: "", codificacao: tipo === "nominal" ? "indicadoras" : "nenhuma", transformacao: "nenhuma", ausentes: "excluir", validacao: "", referencia: "", mapa: null, justificativa: "" }; }
    return [
      v("Preço unitário", "valor_unitario", "continua", "dependente", "R$/m²", "Preço total / área privativa (derivado)"),
      v("Preço total", "valor_total", "continua", "ignorar", "R$", "Preço de oferta"),
      v("Área privativa", "area_privativa", "continua", "independente", "m²"), v("Quartos", "quartos", "discreta", "ignorar", "un"),
      v("Banheiros", "banheiros", "discreta", "ignorar", "un"), v("Vagas", "vagas", "discreta", "ignorar", "un"), v("Suítes", "suites", "discreta", "ignorar", "un"),
      v("Andar", "andar", "discreta", "ignorar", "un"), v("Idade", "idade", "continua", "ignorar", "anos"), v("Bairro", "bairro", "nominal", "ignorar", ""),
      v("Padrão construtivo", "padrao", "nominal", "ignorar", ""), v("Elevador", "elevador", "dicotomica", "ignorar", "0/1"), v("Piscina", "piscina", "dicotomica", "ignorar", "0/1"),
      v("Varanda", "varanda", "dicotomica", "ignorar", "0/1"), v("Vista para o mar", "vista_mar", "dicotomica", "ignorar", "0/1"), v("Condomínio", "condominio", "continua", "ignorar", "R$"), v("IPTU", "iptu", "continua", "ignorar", "R$")
    ];
  };
  IE.abrir = function (id) {
    var p = lerJSON(K_PROJ + id, null); if (!p) return false;
    if (!p.variaveis) p.variaveis = IE.variaveisPadrao();
    if (!p.matrizes) p.matrizes = []; if (!p.visoes) p.visoes = {}; if (!p.colecoes) p.colecoes = {};
    IE.P = p; IE.undo = []; IE.redo = []; IE.recalc(); IE.prefs.ultimo = id; IE.savePrefs();
    $("#projNome").value = p.nome; document.title = p.nome + " — Base amostral · Inferência Estatística"; return true;
  };
  var saveT = null;
  IE.salvar = function (imediato) {
    var st = $("#saveSt"); if (!IE.P) return; if (st) st.textContent = "Salvando…";
    clearTimeout(saveT);
    var run = function () {
      try {
        IE.P.atualizado = agora(); localStorage.setItem(K_PROJ + IE.P.id, JSON.stringify(IE.P));
        var idx = IE.indice().filter(function (x) { return x.id !== IE.P.id; });
        idx.unshift({ id: IE.P.id, nome: IE.P.nome, atualizado: IE.P.atualizado, arquivado: IE.P.arquivado, coleta_id: IE.P.coleta_id, n: IE.P.amostras.length, cidade: IE.P.params_originais ? IE.P.params_originais.cidade : "" });
        gravaIndice(idx); IE.banco.atualizar(IE.P);
        if (st) st.textContent = "Salvo " + hhmm(); IE.salvoEm = agora(); IE.barra();
      } catch (e) { if (st) st.textContent = "Erro ao salvar"; toast("Não foi possível salvar neste navegador (armazenamento cheio?). Exporte o projeto (módulo Exportar).", true); }
    };
    if (imediato) run(); else saveT = setTimeout(run, 500);
  };
  IE.duplicar = function (id) {
    var p = lerJSON(K_PROJ + id, null); if (!p) return null; p.id = uid(); p.nome = p.nome + " (cópia)"; p.criado = agora(); p.coleta_id = null;
    p.historico_projeto = (p.historico_projeto || []).concat([{ t: agora(), tipo: "duplicacao", nota: "Duplicado de " + id }]);
    localStorage.setItem(K_PROJ + p.id, JSON.stringify(p)); var idx = IE.indice(); idx.unshift({ id: p.id, nome: p.nome, atualizado: agora(), n: (p.amostras || []).length }); gravaIndice(idx); return p.id;
  };
  IE.removerProjeto = function (id) { try { localStorage.removeItem(K_PROJ + id); } catch (e) {} gravaIndice(IE.indice().filter(function (x) { return x.id !== id; })); };
  IE.arquivar = function (id, v) { var p = lerJSON(K_PROJ + id, null); if (!p) return; p.arquivado = v; localStorage.setItem(K_PROJ + id, JSON.stringify(p)); gravaIndice(IE.indice().map(function (x) { if (x.id === id) x.arquivado = v; return x; })); };
  IE.exportarProjeto = function () { return JSON.stringify({ formato: "inferencia-estatistica-projeto", versao: 2, exportado_em: agora(), projeto: IE.P }, null, 1); };
  IE.importarProjeto = function (txt) {
    var j = JSON.parse(txt); var p = j && j.projeto; if (!p || !Array.isArray(p.amostras)) throw new Error("Arquivo não parece um projeto exportado por esta ferramenta.");
    p.id = uid(); p.nome = (p.nome || "Projeto") + " (importado)"; p.atualizado = agora(); localStorage.setItem(K_PROJ + p.id, JSON.stringify(p));
    var idx = IE.indice(); idx.unshift({ id: p.id, nome: p.nome, atualizado: p.atualizado, n: p.amostras.length }); gravaIndice(idx); return p.id;
  };

  /* ------------------------------ amostras: criação, valores, histórico ------------------------------ */
  IE.amostraDeRegistro = function (r) {
    var usar = !r.fora_filtros && r.alerta === "OK";
    var a = { id: r.id, fonte: r.fonte, data_coleta: r.data_coleta, natureza: r.natureza || "oferta", uf: r.uf, cidade: r.cidade, bairro: r.bairro === "NAO_INFORMADO" ? "" : r.bairro, tipo: r.tipo,
      finalidade: r.finalidade, valor_total: r.valor_total, area_privativa: r.area_privativa, quartos: r.quartos, suites: r.suites, banheiros: r.banheiros, vagas: r.vagas, andar: r.andar,
      condominio: r.condominio, iptu: r.iptu, elevador: r.elevador, piscina: r.piscina, churrasqueira: r.churrasqueira, portaria_24h: r.portaria_24h, titulo: r.titulo, url: r.url,
      fotos: r.fotos || [], _alerta: r.alerta, _fora: !!r.fora_filtros, _motivos: r.motivos || [], _compl: r.completude, usar: usar, estado_manual: null, justificativa: "", obs: "", _orig: {}, hist: [] };
    a.hist.push({ t: agora(), tipo: "coleta", nota: "Coletado de " + (r.fonte || "fonte") + (r.data_coleta ? " em " + r.data_coleta : "") });
    return a;
  };
  IE.valor = function (a, k) {
    if (k === "valor_unitario") { var v = num(a.valor_total), ar = num(a.area_privativa); return v != null && ar ? v / ar : null; }
    var vr = IE.varDerivada(k); if (vr) return IE.calcDerivada(a, vr);
    return a[k] === undefined ? null : a[k];
  };
  IE.varDerivada = function (k) { if (!IE.P) return null; for (var i = 0; i < IE.P.variaveis.length; i++) { var v = IE.P.variaveis[i]; if (v.tipo === "derivada" && v.campo === k) return v; } return null; };
  IE.calcDerivada = function (a, v) {
    var d = v.derivada || {}, x = num(IE.valor(a, d.a)), y = num(IE.valor(a, d.b)); if (x == null || y == null) return null;
    return d.op === "+" ? x + y : d.op === "-" ? x - y : d.op === "*" ? x * y : d.op === "/" ? (y !== 0 ? x / y : null) : null;
  };
  IE.setVal = function (a, k, v, lote) {
    var antigo = a[k] === undefined ? null : a[k], novo = v === "" ? null : v;
    if (antigo === novo || (antigo == null && novo == null)) return false;
    if (!(k in a._orig)) a._orig[k] = antigo;
    a[k] = novo; var orig = a._orig[k];
    if (orig === novo || (orig == null && novo == null)) delete a._orig[k];
    a.hist.push({ t: agora(), tipo: "correcao", campo: k, de: antigo, para: novo });
    if (lote) lote.push({ id: a.id, k: k, de: antigo, para: novo });
    return true;
  };
  IE.commit = function (lote) {
    if (lote && lote.length) { IE.undo.push(lote); IE.redo = []; if (IE.undo.length > 200) IE.undo.shift(); }
    IE.recalc(); IE.salvar(); IE.emit("dados");
  };
  function porId(id) { for (var i = 0; i < IE.P.amostras.length; i++) if (IE.P.amostras[i].id === id) return IE.P.amostras[i]; return null; }
  IE.porId = porId;
  IE.desfazer = function () { var l = IE.undo.pop(); if (!l) return toast("Nada para desfazer"); IE.aplicaLote(l, true); IE.redo.push(l); };
  IE.refazer = function () { var l = IE.redo.pop(); if (!l) return toast("Nada para refazer"); IE.aplicaLote(l, false); IE.undo.push(l); };
  IE.aplicaLote = function (l, inverso) {
    l.forEach(function (c) { var a = porId(c.id); if (!a) return; var alvo = inverso ? c.de : c.para; var antes = a[c.k]; a[c.k] = alvo;
      if (c.k === "usar" || c.k === "estado_manual") { /* sem _orig */ } else { if (!(c.k in a._orig)) a._orig[c.k] = antes; if (a._orig[c.k] === alvo || (a._orig[c.k] == null && alvo == null)) delete a._orig[c.k]; }
      a.hist.push({ t: agora(), tipo: inverso ? "desfazer" : "refazer", campo: c.k, de: antes, para: alvo }); });
    IE.recalc(); IE.salvar(); IE.emit("dados");
  };
  IE.definirUsar = function (ids, usar, nota) {
    var lote = []; ids.forEach(function (id) { var a = porId(id); if (!a || a.usar === usar) return; lote.push({ id: id, k: "usar", de: a.usar, para: usar });
      a.usar = usar; a.hist.push({ t: agora(), tipo: usar ? "reintegracao" : "exclusao", nota: nota || (usar ? "Incluída na análise" : "Retirada da análise") }); });
    IE.commit(lote);
  };
  IE.definirEstado = function (ids, estado, justificativa) {
    var lote = []; ids.forEach(function (id) { var a = porId(id); if (!a) return; lote.push({ id: id, k: "estado_manual", de: a.estado_manual, para: estado });
      a.estado_manual = estado || null; if (justificativa != null) a.justificativa = justificativa;
      if (estado === "Excluído da análise") a.usar = false; else if (estado === "Selecionado" || estado === "Validado pelo avaliador") a.usar = true;
      a.hist.push({ t: agora(), tipo: estado === "Validado pelo avaliador" ? "validacao" : estado === "Excluído da análise" ? "exclusao" : "estado", nota: (estado || "automático") + (justificativa ? " — " + justificativa : "") }); });
    IE.commit(lote);
  };

  /* ------------------------------ qualificação automática ------------------------------ */
  IE.recalc = function () {
    var L = IE.P ? IE.P.amostras : []; L.forEach(function (a) { a._dup = null; });
    var ord = L.slice().sort(function (x, y) { return (x.id || 0) - (y.id || 0); });
    for (var i = 0; i < ord.length; i++) { var A = ord[i], va = num(A.valor_total), ar = num(A.area_privativa); if (va == null || !ar || A._dup) continue;
      for (var j = i + 1; j < ord.length; j++) { var B = ord[j]; if (B._dup) continue; var vb = num(B.valor_total), ab = num(B.area_privativa); if (vb == null || !ab) continue;
        if ((A.bairro || "") === (B.bairro || "") && Math.abs(ar - ab) / ar <= 0.01 && Math.abs(va - vb) / va <= 0.02) B._dup = A.id; } }
  };
  IE.faltas = function (a) {
    var f = []; if (num(a.valor_total) == null) f.push("preço total"); if (num(a.area_privativa) == null) f.push("área privativa"); if (!a.bairro) f.push("bairro"); if (num(a.quartos) == null && a.tipo !== "TERRENO") f.push("quartos"); return f;
  };
  IE.auto = function (a) {
    var r = [], faltas = IE.faltas(a), estado;
    if (faltas.length) { estado = "Incompleto"; r.push("Faltam: " + faltas.join(", ") + "."); }
    if (a._alerta && a._alerta !== "OK") { estado = "Suspeito"; r.push("Saneamento: " + (a._alerta === "POSSIVEL_OUTLIER" ? "R$/m² fora do usual (conferir; não é exclusão automática)." : "valor ou área ausente/inválido.")); }
    (a._motivos || []).forEach(function (m) { if (/entrada|parcela|di[aá]ria|temporada|leil[aã]o/i.test(m)) { estado = "Suspeito"; r.push(m); } else if (/m[íi]nimo|m[áa]ximo|Menos de/i.test(m)) r.push(m); });
    if (a._dup) { if (!estado) estado = "Possível duplicidade"; r.push("Semelhante à amostra #" + a._dup + " (mesmo bairro, área ±1% e preço ±2%)."); }
    if (!estado) estado = a._fora ? "Coletado" : "Compatível com os filtros";
    if (a._fora && estado !== "Coletado") r.push("Fora dos filtros pedidos na coleta.");
    return { estado: estado, razoes: r, cadastral: a._fora ? "fora dos filtros" : "compatível", informacao: faltas.length ? "incompleta" : (a._alerta && a._alerta !== "OK" ? "suspeita" : "completa") };
  };
  IE.estado = function (a) { var au = IE.auto(a); return a.estado_manual ? { estado: a.estado_manual, razoes: [a.justificativa || "Decisão do avaliador."].concat(au.razoes.length ? ["Automático: " + au.estado + " — " + au.razoes.join(" ")] : []), manual: true, cadastral: au.cadastral, informacao: au.informacao } : au; };

  /* ------------------------------ eventos e roteador ------------------------------ */
  var ouvintes = {};
  IE.on = function (ev, fn) { (ouvintes[ev] = ouvintes[ev] || []).push(fn); };
  IE.emit = function (ev, d) { (ouvintes[ev] || []).forEach(function (f) { try { f(d); } catch (e) { console.error(e); } }); };
  IE.modulos = []; IE.mod = {};
  IE.registrar = function (id, titulo, render, opts) { IE.modulos.push({ id: id, titulo: titulo, opts: opts || {} }); IE.mod[id] = render; };
  IE.atual = null;
  IE.ir = function (id) { if (location.hash !== "#" + id) location.hash = id; else IE.render(); };
  IE.render = function () {
    var id = (location.hash || "#base").slice(1).split("/")[0]; if (!IE.mod[id]) id = "base";
    if (IE.atual && IE.sair) { try { IE.sair(); } catch (e) {} } IE.sair = null; IE.atual = id;
    var nav = $("#mods"); nav.innerHTML = IE.modulos.map(function (m) { return '<button data-m="' + m.id + '"' + (m.id === id ? ' aria-current="page"' : "") + ">" + esc(m.titulo) + (m.opts.breve ? '<span class="soon">em preparação</span>' : "") + "</button>"; }).join("");
    nav.classList.remove("on"); var v = $("#view"); v.innerHTML = ""; IE.barra();
    if (!IE.P && id !== "projetos" && id !== "banco") { IE.mod.projetos(v); return; }
    IE.mod[id](v);
  };
  IE.barra = function () {
    var b = $("#bar"); if (!b) return; var P = IE.P;
    if (!P) { b.innerHTML = "<span>Nenhum projeto aberto</span>"; return; }
    var usadas = P.amostras.filter(function (a) { return a.usar; }).length;
    b.innerHTML = '<span><b>' + P.amostras.length + "</b> registros</span><span><b>" + usadas + "</b> na análise</span>" + (IE.barraExtra ? IE.barraExtra() : "") + '<span class="sp"></span><span>' + (IE.salvoEm ? "Salvo às " + hhmm(IE.salvoEm) : "Não salvo") + " · neste navegador</span>";
  };
  IE.on("dados", function () { IE.barra(); });

  /* ------------------------------ banco permanente local ------------------------------ */
  IE.banco = {
    ler: function () { return lerJSON(K_BANCO, {}); },
    atualizar: function (p) {
      if (!p || !p.amostras || !p.amostras.length) return; var b = IE.banco.ler(), mudou = false, ref = (p.data_ref || (p.meta && p.meta.quando) || "").slice(0, 10) || new Date().toISOString().slice(0, 10);
      p.amostras.forEach(function (a) {
        var chave = a.url || (a.fonte + ":" + p.id + ":" + a.id); var e = b[chave];
        var snap = { d: ref, v: a.valor_total, ar: a.area_privativa };
        if (!e) { b[chave] = { url: a.url || "", fonte: a.fonte, cidade: a.cidade, uf: a.uf, bairro: a.bairro, tipo: a.tipo, finalidade: a.finalidade, titulo: a.titulo, foto: (a.fotos || [])[0] || "", quartos: a.quartos, vagas: a.vagas, hist: [snap], projetos: [p.id], colecoes: [] }; mudou = true; }
        else { var ult = e.hist[e.hist.length - 1]; if (!ult || ult.d !== snap.d || ult.v !== snap.v || ult.ar !== snap.ar) { e.hist.push(snap); mudou = true; } if (e.projetos.indexOf(p.id) < 0) { e.projetos.push(p.id); mudou = true; } }
      });
      if (mudou) { try { localStorage.setItem(K_BANCO, JSON.stringify(b)); } catch (e) { /* sem espaço: o projeto continua salvo */ } }
    }
  };

  /* ------------------------------ inicialização ------------------------------ */
  IE.iniciar = function () {
    var tema = IE.prefs.tema; $("#bTema").addEventListener("click", function () { var t = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark"; document.documentElement.setAttribute("data-theme", t); IE.prefs.tema = t; IE.savePrefs(); });
    $("#bMenu").addEventListener("click", function () { $("#mods").classList.toggle("on"); });
    $("#mods").addEventListener("click", function (e) { var b = e.target.closest("button[data-m]"); if (b) IE.ir(b.dataset.m); });
    $("#projNome").addEventListener("change", function () { if (!IE.P) return; var v = this.value.trim() || "Projeto sem nome"; IE.P.nome = v; IE.P.historico_projeto.push({ t: agora(), tipo: "renomear", nota: v }); IE.salvar(); });
    window.addEventListener("hashchange", IE.render);
    var boot = window.IE_BOOT || {}, abrirFinal = function () { if (!location.hash) location.hash = IE.P ? "base" : "projetos"; IE.render(); };
    if (boot.coleta_id) {
      var existente = IE.indice().filter(function (x) { return x.coleta_id === boot.coleta_id; })[0];
      if (existente && IE.abrir(existente.id)) { location.hash = location.hash || "base"; return abrirFinal(); }
      fetch("/coleta/" + boot.coleta_id + "/amostras.json").then(function (r) { return r.json().then(function (j) { return { ok: r.ok, j: j }; }); }).then(function (x) {
        if (!x.ok) { toast(x.j.erro || "Coleta não encontrada.", true); IE.abrirUltimo(); return abrirFinal(); }
        var j = x.j, par = j.parametros || {};
        var nome = "Pesquisa · " + (par.cidade || "") + (par.bairro ? " / " + par.bairro : "") + " · " + (par.tipo_imovel || "").toLowerCase();
        var p = IE.novoProjeto(nome, { coleta_id: boot.coleta_id, params_originais: Object.freeze(JSON.parse(JSON.stringify(par))), meta: j.meta, diagnostico: j.diagnostico || [],
          amostras: j.amostras.map(IE.amostraDeRegistro), finalidade_trabalho: "" });
        p.historico_projeto.push({ t: agora(), tipo: "coleta", nota: "Coleta " + boot.coleta_id + " importada: " + p.amostras.length + " amostras" });
        localStorage.setItem(K_PROJ + p.id, JSON.stringify(p)); var idx = IE.indice(); idx.unshift({ id: p.id, nome: p.nome, atualizado: p.atualizado, coleta_id: p.coleta_id, n: p.amostras.length, cidade: par.cidade }); gravaIndice(idx);
        IE.abrir(p.id); IE.salvar(true); location.hash = "base"; abrirFinal();
      }).catch(function () { toast("Falha de rede ao carregar a coleta.", true); IE.abrirUltimo(); abrirFinal(); });
    } else { IE.abrirUltimo(); abrirFinal(); }
  };
  IE.abrirUltimo = function () { var id = IE.prefs.ultimo; if (id && IE.abrir(id)) return true; var i = IE.indice().filter(function (x) { return !x.arquivado; })[0]; return i ? IE.abrir(i.id) : false; };
  document.addEventListener("DOMContentLoaded", function () { setTimeout(IE.iniciar, 0); });
})(window.IE);
