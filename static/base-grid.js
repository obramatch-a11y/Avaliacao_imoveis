/* Base amostral — planilha inteligente (virtualizada), painel de inspeção, importação e colunas/visões. */
(function (IE) {
  "use strict";
  var u = IE.u, $ = u.$, $$ = u.$$, esc = u.esc, num = u.num;
  var ALT = { compacto: 26, confortavel: 40, fotografico: 78 };
  var G = IE.grid = { rows: [], sel: null, act: { r: 0, c: 0 }, edit: null, busca: "", filtroEstado: "", inspOn: false, inspId: null, raiz: null };

  /* ---------------- definição de colunas (padrão + variáveis personalizadas) ---------------- */
  IE.colDef = function (k) {
    if (IE.COLS_MAP[k]) return IE.COLS_MAP[k];
    var v = IE.P.variaveis.filter(function (x) { return x.campo === k; })[0]; if (!v) return { k: k, label: k, tipo: "text", w: 100, editavel: true };
    var t = v.tipo === "nominal" || v.tipo === "ordinal" ? "cat" : v.tipo === "dicotomica" ? "bool" : "num";
    return { k: k, label: v.nome + (v.unidade ? " (" + v.unidade + ")" : ""), tipo: t, w: 110, grupo: "Variáveis", editavel: v.tipo !== "derivada", calc: v.tipo === "derivada", dec: 2, custom: true };
  };
  function ordenadas() { var P = IE.P, base = P.colunas.filter(function (k) { return k && (IE.COLS_MAP[k] || P.variaveis.some(function (v) { return v.campo === k; })); }); return base; }
  function largura(k) { return (IE.P.larguras && IE.P.larguras[k]) || IE.colDef(k).w || 100; }
  function altura() { return ALT[IE.P.densidade] || 40; }

  /* ---------------- visão (busca, filtros, ordenação) ---------------- */
  function texto(a, k) {
    var d = IE.colDef(k);
    if (k === "estado") return IE.estado(a).estado; if (k === "foto") return (a.fotos || []).length ? "sim" : "não";
    var v = IE.valor(a, k); if (v == null) return ""; if (d.tipo === "bool") return num(v) ? "sim" : "não"; return String(v);
  }
  IE.calcVisao = function () {
    var P = IE.P, b = G.busca.trim().toLowerCase(), cols = ordenadas();
    var out = P.amostras.filter(function (a) {
      if (G.filtroEstado) { var e = IE.estado(a).estado; if (G.filtroEstado === "__usar") { if (!a.usar) return false; } else if (G.filtroEstado === "__fora") { if (a.usar) return false; } else if (e !== G.filtroEstado) return false; }
      if (b) { var hay = [a.id, a.bairro, a.fonte, a.titulo, a.endereco, a.cidade, IE.estado(a).estado, a.obs].join(" ").toLowerCase(); if (hay.indexOf(b) < 0) return false; }
      for (var k in P.filtros) { var f = P.filtros[k]; if (!f) continue; var d = IE.colDef(k), v = IE.valor(a, k);
        if (f.min != null || f.max != null) { var n = num(v); if (n == null || (f.min != null && n < f.min) || (f.max != null && n > f.max)) return false; }
        if (f.txt) { if (texto(a, k).toLowerCase().indexOf(f.txt.toLowerCase()) < 0) return false; }
        if (f.set && f.set.length) { if (f.set.indexOf(texto(a, k)) < 0) return false; } }
      return true;
    });
    var o = P.ordenacao; if (o && o.k) { var d2 = IE.colDef(o.k), dir = o.dir === "desc" ? -1 : 1;
      out.sort(function (x, y) { var vx = d2.tipo === "num" || d2.tipo === "bool" ? num(IE.valor(x, o.k)) : texto(x, o.k).toLowerCase(), vy = d2.tipo === "num" || d2.tipo === "bool" ? num(IE.valor(y, o.k)) : texto(y, o.k).toLowerCase();
        if (vx == null && vy == null) return 0; if (vx == null) return 1; if (vy == null) return -1; return (vx < vy ? -1 : vx > vy ? 1 : 0) * dir; }); }
    G.rows = out; G.cols = cols;
  };

  /* ---------------- renderização ---------------- */
  function fmtCel(a, k, d) {
    var v = IE.valor(a, k);
    if (d.tipo === "usar") return '<input type="checkbox" data-act="usar" aria-label="Usar amostra ' + a.id + ' na análise"' + (a.usar ? " checked" : "") + ">";
    if (d.tipo === "foto") { var f = a.fotos || []; return f.length ? '<button class="th" data-act="foto" aria-label="Ver fotos"><img loading="lazy" decoding="async" referrerpolicy="no-referrer" alt="" src="' + esc(f[0]) + '">' + (f.length > 1 ? '<span class="cn">' + f.length + "</span>" : "") + "</button>" : '<span class="note" title="Sem foto disponível na fonte">—</span>'; }
    if (d.tipo === "estado") { var e = IE.estado(a); return '<span class="chip ' + (IE.ESTADO_CLASSE[e.estado] || "") + '" title="' + esc(e.razoes.join(" ")) + '">' + esc(e.estado) + (e.manual ? " ✎" : "") + "</span>"; }
    if (d.tipo === "link") return a.url ? '<a href="' + esc(a.url) + '" target="_blank" rel="noopener noreferrer" data-act="link">abrir ↗</a>' : "";
    if (v == null || v === "") return "";
    if (d.tipo === "bool") return num(v) ? "✓" : "–";
    if (d.tipo === "num") { var n = num(v); if (n == null) return esc(v); return d.dec === 0 ? u.nf0.format(n) : (d.dec >= 4 ? u.nf4.format(n) : u.nf2.format(n)); }
    return esc(v);
  }
  var cabecalho = function () {
    var P = IE.P, off = 0, h = "";
    G.cols.forEach(function (k, i) { var d = IE.colDef(k), w = largura(k), fixa = i < P.fixas, o = P.ordenacao, f = P.filtros[k] && (P.filtros[k].min != null || P.filtros[k].max != null || P.filtros[k].txt || (P.filtros[k].set && P.filtros[k].set.length));
      var st = "width:" + w + "px" + (fixa ? ";position:sticky;left:" + off + "px;z-index:6" : ""); if (fixa) off += w;
      h += '<div class="gh' + (f ? " filt" : "") + (d.calc ? " calc" : "") + '" data-k="' + esc(k) + '" style="' + st + '" draggable="' + (fixa ? "false" : "true") + '" title="' + esc(d.label) + '">' +
        '<span>' + esc(d.label) + "</span>" + (o && o.k === k ? '<span class="srt">' + (o.dir === "desc" ? "▼" : "▲") + "</span>" : "") +
        (d.tipo !== "usar" && d.tipo !== "foto" ? '<span class="fl" data-act="filtro" title="Filtrar coluna">⏷</span>' : "") + '<span class="rs" data-act="rs"></span></div>'; });
    return h;
  };
  G.render = function () {
    var root = G.raiz; if (!root) return; var sc = $(".gscroll", root), P = IE.P; IE.calcVisao();
    var rh = altura(), total = G.rows.length, W = G.cols.reduce(function (s, k) { return s + largura(k); }, 0);
    var inner = $(".gin", sc); inner.style.height = 30 + total * rh + "px"; inner.style.width = W + "px"; $(".ghead", sc).innerHTML = cabecalho(); $(".ghead", sc).style.width = W + "px";
    G.W = W; G.pinta();
    var vazio = $(".vazio", root); vazio.style.display = total ? "none" : "block";
    vazio.innerHTML = P.amostras.length ? "Nenhuma amostra corresponde à busca ou aos filtros. <button class='btn sm' data-act='limpar'>Limpar filtros</button>" : "Base vazia. Use o módulo <b>Pesquisa de mercado</b> (coleta, importação ou cadastro manual).";
    IE.barraExtra = function () { return "<span><b>" + G.rows.length + "</b> exibidos</span>" + (selecao().length ? "<span><b>" + selecao().length + "</b> linha(s) marcada(s)</span>" : ""); }; IE.barra(); resumo();
  };
  G.pinta = function () {
    var root = G.raiz; if (!root) return; var sc = $(".gscroll", root), P = IE.P, rh = altura(), top = sc.scrollTop, vh = sc.clientHeight, left = sc.scrollLeft, vw = sc.clientWidth;
    var i0 = Math.max(0, Math.floor((top - 30) / rh) - 3), i1 = Math.min(G.rows.length, Math.ceil((top + vh) / rh) + 3);
    var inner = $(".gin", sc), html = "", S = G.sel, ar = G.act;
    var offs = [], off = 0; G.cols.forEach(function (k, i) { offs.push(off); off += largura(k); });
    for (var r = i0; r < i1; r++) {
      var a = G.rows[r], cls = "grow" + (a.usar ? "" : " ex") + (G.inspId === a.id ? " rowsel" : "");
      html += '<div class="' + cls + '" data-r="' + r + '" data-id="' + a.id + '" style="top:' + (30 + r * rh) + "px;height:" + rh + "px;width:" + G.W + 'px">';
      for (var c = 0; c < G.cols.length; c++) { var k = G.cols[c], d = IE.colDef(k), w = largura(k), fixa = c < P.fixas;
        var inSel = S && r >= Math.min(S.r1, S.r2) && r <= Math.max(S.r1, S.r2) && c >= Math.min(S.c1, S.c2) && c <= Math.max(S.c1, S.c2);
        var corr = d.tipo !== "usar" && a._orig && (k in a._orig);
        var cl = "gc" + (d.tipo === "num" ? " n" : "") + (inSel ? " sel" : "") + (ar.r === r && ar.c === c ? " act" : "") + (corr ? " ed" : "") + (d.calc ? " calc" : "") + (fixa ? " fix" : "");
        var st = "width:" + w + "px" + (fixa ? ";left:" + offs[c] + "px" : "");
        var tit = corr ? ' title="Valor corrigido pelo avaliador. Original: ' + esc(a._orig[k] == null ? "(vazio)" : a._orig[k]) + '"' : (d.calc ? ' title="Valor calculado (derivado), não observado"' : "");
        html += '<div class="' + cl + '" data-c="' + c + '" style="' + st + '"' + tit + ">" + fmtCel(a, k, d) + "</div>"; }
      html += "</div>";
    }
    var antigo = $(".grows", inner); if (!antigo) { antigo = document.createElement("div"); antigo.className = "grows"; inner.appendChild(antigo); }
    antigo.innerHTML = html; if (G.edit) abreEdicao(G.edit.r, G.edit.c, G.edit.valor, true);
  };
  function resumo() {
    var P = IE.P, el = $(".sumario .kpis", G.raiz); if (!el) return; var cont = {}, comp = 0, nn = 0;
    P.amostras.forEach(function (a) { var e = IE.estado(a).estado; cont[e] = (cont[e] || 0) + 1; comp += (IE.faltas(a).length ? 0 : 1); nn++; });
    function k(l, v, cl) { return '<span class="kpi ' + (cl || "") + '">' + l + " <b>" + v + "</b></span>"; }
    el.innerHTML = k("Coletadas", nn) + k("Compatíveis", cont["Compatível com os filtros"] || 0) + k("Incompletas", cont["Incompleto"] || 0) + k("Suspeitas", cont["Suspeito"] || 0) + k("Duplicidades", cont["Possível duplicidade"] || 0) +
      k("Em revisão", cont["Em revisão"] || 0) + k("Validadas", cont["Validado pelo avaliador"] || 0) + k("Na análise", P.amostras.filter(function (a) { return a.usar; }).length) + k("Completude", nn ? Math.round(100 * comp / nn) + "%" : "–");
  }

  /* ---------------- seleção, edição, teclado ---------------- */
  function selecao() { var S = G.sel; if (!S) return []; var ids = [], a = Math.min(S.r1, S.r2), b = Math.max(S.r1, S.r2); for (var r = a; r <= b; r++) if (G.rows[r]) ids.push(G.rows[r].id); return ids; }
  G.selIds = selecao;
  function ativa(r, c, estende) {
    r = Math.max(0, Math.min(G.rows.length - 1, r)); c = Math.max(0, Math.min(G.cols.length - 1, c)); if (!G.rows.length) return;
    if (estende && G.sel) { G.sel.r2 = r; G.sel.c2 = c; } else G.sel = { r1: r, c1: c, r2: r, c2: c }; G.act = { r: r, c: c }; garanteVisivel(r, c); G.pinta(); IE.barra();
    if (G.inspOn && G.rows[r]) { G.inspId = G.rows[r].id; painelInspecao(); }
  }
  function garanteVisivel(r, c) {
    var sc = $(".gscroll", G.raiz), rh = altura(); var y0 = 30 + r * rh, y1 = y0 + rh;
    if (y0 - 30 < sc.scrollTop) sc.scrollTop = y0 - 30; else if (y1 > sc.scrollTop + sc.clientHeight) sc.scrollTop = y1 - sc.clientHeight;
    var off = 0; for (var i = 0; i < c; i++) off += largura(G.cols[i]); var w = largura(G.cols[c]), fx = 0; for (var j = 0; j < IE.P.fixas; j++) fx += largura(G.cols[j]);
    if (c >= IE.P.fixas) { if (off - fx < sc.scrollLeft) sc.scrollLeft = off - fx; else if (off + w > sc.scrollLeft + sc.clientWidth) sc.scrollLeft = off + w - sc.clientWidth; }
  }
  function celEl(r, c) { return $('.grow[data-r="' + r + '"] .gc[data-c="' + c + '"]', G.raiz); }
  function coage(d, txt) {
    if (txt == null) return null; txt = String(txt).trim(); if (txt === "") return null;
    if (d.tipo === "num") { var n = u.parseNum(txt); return n; }
    if (d.tipo === "bool") return /^(1|sim|s|true|x|✓|yes)$/i.test(txt) ? 1 : 0; return txt;
  }
  function abreEdicao(r, c, inicial, mantem) {
    var a = G.rows[r], k = G.cols[c], d = IE.colDef(k);
    if (d.tipo === "estado") { popEstado([a.id], celEl(r, c)); return; }
    if (d.tipo === "usar") { IE.definirUsar([a.id], !a.usar); return; }
    if (d.tipo === "bool" && inicial == null) { var l = []; IE.setVal(a, k, num(a[k]) ? 0 : 1, l); IE.commit(l); return; }
    if (!d.editavel) { if (!mantem) u.toast(d.calc ? "Coluna calculada: edite as colunas de origem." : "Coluna de origem da coleta: não editável (o original é sempre preservado).", false); return; }
    var el = celEl(r, c); if (!el) return; var v = IE.valor(a, k);
    var val = inicial != null ? inicial : (v == null ? "" : (d.tipo === "num" ? String(v).replace(".", ",") : v));
    el.innerHTML = '<input class="cell" aria-label="Editar ' + esc(d.label) + '" value="' + esc(val) + '">'; var inp = $("input", el); inp.focus(); if (inicial == null) inp.select(); else inp.setSelectionRange(val.length, val.length);
    G.edit = { r: r, c: c, valor: val }; inp.addEventListener("input", function () { G.edit.valor = inp.value; });
    inp.addEventListener("keydown", function (e) {
      if (e.key === "Enter" || e.key === "Tab") { e.preventDefault(); e.stopPropagation(); fechaEdicao(true); ativa(G.act.r + (e.key === "Enter" ? (e.shiftKey ? -1 : 1) : 0), G.act.c + (e.key === "Tab" ? (e.shiftKey ? -1 : 1) : 0)); G.focoGrade(); }
      else if (e.key === "Escape") { e.preventDefault(); e.stopPropagation(); fechaEdicao(false); G.focoGrade(); } else e.stopPropagation();
    });
    inp.addEventListener("blur", function () { if (G.edit) fechaEdicao(true); });
  }
  function fechaEdicao(grava) {
    var e = G.edit; if (!e) return; G.edit = null; var a = G.rows[e.r], k = G.cols[e.c];
    if (grava && a) { var d = IE.colDef(k), v = coage(d, e.valor); if (d.tipo === "num" && e.valor.trim() !== "" && v == null) u.toast("Valor numérico inválido: " + e.valor, true); else { var l = []; if (IE.setVal(a, k, v, l)) IE.commit(l); } }
    G.render();
  }
  G.focoGrade = function () { var s = $(".gscroll", G.raiz); if (s) s.focus({ preventScroll: true }); };
  function copiar(cortar) {
    var S = G.sel; if (!S) return; var linhas = [], r0 = Math.min(S.r1, S.r2), r1 = Math.max(S.r1, S.r2), c0 = Math.min(S.c1, S.c2), c1 = Math.max(S.c1, S.c2);
    for (var r = r0; r <= r1; r++) { var cs = []; for (var c = c0; c <= c1; c++) { var k = G.cols[c], d = IE.colDef(k), a = G.rows[r]; var v = d.tipo === "estado" ? IE.estado(a).estado : d.tipo === "foto" ? (a.fotos || [])[0] || "" : d.tipo === "usar" ? (a.usar ? 1 : 0) : IE.valor(a, k); cs.push(v == null ? "" : (d.tipo === "num" ? String(v).replace(".", ",") : String(v))); } linhas.push(cs.join("\t")); }
    var t = linhas.join("\n"); (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(function () { u.toast("Copiado: " + (r1 - r0 + 1) + "×" + (c1 - c0 + 1) + " células"); }, function () { u.toast("Seu navegador bloqueou a área de transferência; use Ctrl+C com a planilha em foco.", true); });
    if (cortar) apagar();
  }
  function colar(txt) {
    if (!txt || !G.rows.length) return; var lin = txt.replace(/\r/g, "").replace(/\n$/, "").split("\n").map(function (l) { return l.split("\t"); }), S = G.sel || { r1: G.act.r, c1: G.act.c, r2: G.act.r, c2: G.act.c };
    var r0 = Math.min(S.r1, S.r2), c0 = Math.min(S.c1, S.c2), r1 = Math.max(S.r1, S.r2), c1 = Math.max(S.c1, S.c2), lote = [], n = 0, ign = 0;
    var unico = lin.length === 1 && lin[0].length === 1, nr = unico ? r1 - r0 + 1 : lin.length, nc = unico ? c1 - c0 + 1 : lin[0].length;
    for (var i = 0; i < nr; i++) for (var j = 0; j < nc; j++) { var r = r0 + i, c = c0 + j; if (r >= G.rows.length || c >= G.cols.length) continue; var d = IE.colDef(G.cols[c]); if (!d.editavel) { ign++; continue; }
      var raw = unico ? lin[0][0] : (lin[i] || [])[j]; var v = coage(d, raw); if (d.tipo === "num" && raw && raw.trim() !== "" && v == null) { ign++; continue; } if (IE.setVal(G.rows[r], G.cols[c], v, lote)) n++; }
    IE.commit(lote); u.toast(n + " célula(s) coladas" + (ign ? " · " + ign + " ignorada(s) (colunas não editáveis ou valores inválidos)" : "")); G.render();
  }
  function apagar() { var S = G.sel; if (!S) return; var lote = []; var r0 = Math.min(S.r1, S.r2), r1 = Math.max(S.r1, S.r2), c0 = Math.min(S.c1, S.c2), c1 = Math.max(S.c1, S.c2);
    for (var r = r0; r <= r1; r++) for (var c = c0; c <= c1; c++) { var d = IE.colDef(G.cols[c]); if (d.editavel) IE.setVal(G.rows[r], G.cols[c], null, lote); } IE.commit(lote); G.render(); }
  function preencherAbaixo() { var S = G.sel; if (!S) return; var r0 = Math.min(S.r1, S.r2), r1 = Math.max(S.r1, S.r2), c0 = Math.min(S.c1, S.c2), c1 = Math.max(S.c1, S.c2); if (r0 === r1) return u.toast("Selecione mais de uma linha para preencher.");
    var lote = []; for (var c = c0; c <= c1; c++) { var d = IE.colDef(G.cols[c]); if (!d.editavel) continue; var v = G.rows[r0][G.cols[c]]; for (var r = r0 + 1; r <= r1; r++) IE.setVal(G.rows[r], G.cols[c], v === undefined ? null : v, lote); } IE.commit(lote); G.render(); u.toast("Preenchido para baixo"); }

  function teclado(e) {
    if (G.edit) return; var ctrl = e.ctrlKey || e.metaKey, k = e.key, S = e.shiftKey;
    if (ctrl && k.toLowerCase() === "z") { e.preventDefault(); return S ? IE.refazer() : IE.desfazer(); } if (ctrl && k.toLowerCase() === "y") { e.preventDefault(); return IE.refazer(); }
    if (ctrl && k.toLowerCase() === "c") { e.preventDefault(); return copiar(false); } if (ctrl && k.toLowerCase() === "x") { e.preventDefault(); return copiar(true); }
    if (ctrl && k.toLowerCase() === "d") { e.preventDefault(); return preencherAbaixo(); }
    if (ctrl && k.toLowerCase() === "a") { e.preventDefault(); G.sel = { r1: 0, c1: 0, r2: G.rows.length - 1, c2: G.cols.length - 1 }; G.pinta(); return; }
    if (ctrl && k.toLowerCase() === "v") return; /* tratado pelo evento paste */
    var a = G.act;
    if (k === "ArrowDown") { e.preventDefault(); ativa(a.r + 1, a.c, S); } else if (k === "ArrowUp") { e.preventDefault(); ativa(a.r - 1, a.c, S); }
    else if (k === "ArrowRight") { e.preventDefault(); ativa(a.r, a.c + 1, S); } else if (k === "ArrowLeft") { e.preventDefault(); ativa(a.r, a.c - 1, S); }
    else if (k === "Tab") { e.preventDefault(); ativa(a.r, a.c + (S ? -1 : 1)); } else if (k === "PageDown") { e.preventDefault(); ativa(a.r + 10, a.c, S); } else if (k === "PageUp") { e.preventDefault(); ativa(a.r - 10, a.c, S); }
    else if (k === "Home") { e.preventDefault(); ativa(ctrl ? 0 : a.r, 0, S); } else if (k === "End") { e.preventDefault(); ativa(ctrl ? G.rows.length - 1 : a.r, G.cols.length - 1, S); }
    else if (k === "Enter" || k === "F2") { e.preventDefault(); abreEdicao(a.r, a.c, null); }
    else if (k === "Delete" || k === "Backspace") { e.preventDefault(); apagar(); }
    else if (k === " " && G.rows[a.r]) { e.preventDefault(); var ids = selecao(); IE.definirUsar(ids, !G.rows[a.r].usar); G.render(); }
    else if (k === "Escape") { G.sel = { r1: a.r, c1: a.c, r2: a.r, c2: a.c }; G.pinta(); }
    else if (k.length === 1 && !ctrl && !e.altKey) { var d = IE.colDef(G.cols[a.c]); if (d.editavel && d.tipo !== "bool") { e.preventDefault(); abreEdicao(a.r, a.c, k); } }
  }

  /* ---------------- popovers ---------------- */
  var popAtual = null;
  function fechaPop() { if (popAtual) { popAtual.remove(); popAtual = null; } }
  function pop(ancora, html, larg) {
    fechaPop(); var p = document.createElement("div"); p.className = "pop"; p.innerHTML = html; document.body.appendChild(p); popAtual = p;
    var r = ancora ? ancora.getBoundingClientRect() : { left: 20, bottom: 60, top: 60 }; var w = larg || 300; p.style.width = Math.min(w, innerWidth - 16) + "px";
    p.style.left = Math.max(8, Math.min(innerWidth - Math.min(w, innerWidth - 16) - 8, r.left)) + "px"; p.style.top = Math.min(innerHeight - 100, r.bottom + 4) + "px"; return p;
  }
  document.addEventListener("mousedown", function (e) { if (popAtual && !popAtual.contains(e.target) && !(e.target.closest && e.target.closest("[data-pop]"))) fechaPop(); });
  document.addEventListener("keydown", function (e) { if (e.key === "Escape" && popAtual) { fechaPop(); } });
  IE.pop = pop; IE.fechaPop = fechaPop;

  function popEstado(ids, ancora) {
    var a = IE.porId(ids[0]); var atual = ids.length === 1 ? a.estado_manual : null;
    var p = pop(ancora, '<h5>Situação da amostra' + (ids.length > 1 ? " (" + ids.length + " linhas)" : " #" + ids[0]) + '</h5>' +
      '<label class="r"><input type="radio" name="es" value="" ' + (!atual ? "checked" : "") + '> Automática (' + esc(ids.length === 1 ? IE.auto(a).estado : "pelas regras") + ')</label>' +
      IE.MANUAIS.map(function (s) { return '<label class="r"><input type="radio" name="es" value="' + s + '" ' + (atual === s ? "checked" : "") + "> " + s + "</label>"; }).join("") +
      '<label class="f" style="margin-top:6px">Justificativa (fica no histórico)<textarea rows="2" id="esj">' + esc(ids.length === 1 ? a.justificativa : "") + '</textarea></label>' +
      '<p class="note">O sistema sugere; a decisão é do avaliador. Nada é apagado: a exclusão apenas retira a amostra da análise.</p><button class="btn pri" id="esOk">Aplicar</button>', 310);
    $("#esOk", p).addEventListener("click", function () { var v = ($('input[name=es]:checked', p) || {}).value || ""; IE.definirEstado(ids, v, $("#esj", p).value.trim()); fechaPop(); G.render(); });
  }
  function popFiltro(k, ancora) {
    var P = IE.P, d = IE.colDef(k), f = P.filtros[k] || {}, h = '<h5>Filtro — ' + esc(d.label) + "</h5>";
    if (d.tipo === "num") h += '<div class="grid2"><label class="f">Mínimo<input id="fmin" inputmode="decimal" value="' + (f.min != null ? f.min : "") + '"></label><label class="f">Máximo<input id="fmax" inputmode="decimal" value="' + (f.max != null ? f.max : "") + '"></label></div>';
    else { var cont = {}; P.amostras.forEach(function (a) { var t = texto(a, k); cont[t] = (cont[t] || 0) + 1; }); var ks = Object.keys(cont).sort();
      h += '<label class="f">Contém<input id="ftxt" value="' + esc(f.txt || "") + '"></label>';
      if (ks.length <= 40) h += '<div style="margin-top:6px;max-height:220px;overflow:auto">' + ks.map(function (t) { return '<label class="r"><input type="checkbox" class="fset" value="' + esc(t) + '"' + ((f.set || []).indexOf(t) >= 0 ? " checked" : "") + "> " + esc(t || "(vazio)") + ' <span class="note">' + cont[t] + "</span></label>"; }).join("") + "</div>"; }
    h += '<div style="display:flex;gap:6px;margin-top:8px"><button class="btn pri" id="fOk">Aplicar</button><button class="btn" id="fLimpa">Limpar</button></div>';
    var p = pop(ancora, h, 280);
    $("#fOk", p).addEventListener("click", function () { var nf = {}; if (d.tipo === "num") { var a = u.parseNum($("#fmin", p).value), b = u.parseNum($("#fmax", p).value); if (a != null) nf.min = a; if (b != null) nf.max = b; }
      else { var t = $("#ftxt", p).value.trim(); if (t) nf.txt = t; var s = $$(".fset:checked", p).map(function (x) { return x.value; }); if (s.length) nf.set = s; }
      if (Object.keys(nf).length) P.filtros[k] = nf; else delete P.filtros[k]; fechaPop(); IE.salvar(); G.render(); });
    $("#fLimpa", p).addEventListener("click", function () { delete P.filtros[k]; fechaPop(); IE.salvar(); G.render(); });
  }
  function popColunas(ancora) {
    var P = IE.P, ativas = ordenadas(), todas = IE.COLS.map(function (c) { return c.k; }).concat(P.variaveis.filter(function (v) { return !IE.COLS_MAP[v.campo] && v.origem !== "coleta"; }).map(function (v) { return v.campo; }));
    var h = '<h5>Colunas visíveis (ordem de exibição)</h5><div style="max-height:46vh;overflow:auto">' + ativas.map(function (k, i) { return '<div class="r" style="display:flex;gap:4px;align-items:center"><span style="flex:1">' + esc(IE.colDef(k).label) + '</span><button class="btn sm" data-mv="' + i + '|-1" aria-label="Mover para cima">↑</button><button class="btn sm" data-mv="' + i + '|1" aria-label="Mover para baixo">↓</button><button class="btn sm" data-hide="' + esc(k) + '">ocultar</button></div>'; }).join("") + "</div>";
    var ocultas = todas.filter(function (k) { return ativas.indexOf(k) < 0; });
    h += '<h5 style="margin-top:10px">Disponíveis</h5><div style="max-height:30vh;overflow:auto">' + (ocultas.length ? ocultas.map(function (k) { return '<label class="r"><input type="checkbox" data-show="' + esc(k) + '"> ' + esc(IE.colDef(k).label) + ' <span class="note">' + esc(IE.colDef(k).grupo || "") + "</span></label>"; }).join("") : '<span class="note">Todas visíveis.</span>') + "</div>";
    h += '<label class="f" style="margin-top:8px">Colunas fixas à esquerda<input type="number" id="nfix" min="0" max="6" value="' + P.fixas + '"></label>';
    var p = pop(ancora, h, 340);
    p.addEventListener("click", function (e) { var b = e.target.closest("button"); if (!b) return; if (b.dataset.mv) { var s = b.dataset.mv.split("|"), i = +s[0], j = i + +s[1]; if (j < 0 || j >= ativas.length) return; var t = ativas[i]; ativas[i] = ativas[j]; ativas[j] = t; P.colunas = ativas; } else if (b.dataset.hide) { P.colunas = ativas.filter(function (k) { return k !== b.dataset.hide; }); } else return; IE.salvar(); G.render(); popColunas(ancora); });
    p.addEventListener("change", function (e) { if (e.target.dataset && e.target.dataset.show) { ativas.push(e.target.dataset.show); P.colunas = ativas; IE.salvar(); G.render(); popColunas(ancora); } else if (e.target.id === "nfix") { P.fixas = Math.max(0, Math.min(6, +e.target.value || 0)); IE.salvar(); G.render(); } });
  }
  function popVisoes(ancora) {
    var P = IE.P, nomes = Object.keys(P.visoes);
    var h = '<h5>Visões salvas da base</h5>' + (nomes.length ? nomes.map(function (n) { return '<div class="r" style="display:flex;gap:4px;align-items:center"><button class="btn sm" data-ap="' + esc(n) + '" style="flex:1;text-align:left">' + esc(n) + '</button><button class="btn sm" data-del="' + esc(n) + '" aria-label="Excluir visão">✕</button></div>'; }).join("") : '<p class="note">Nenhuma visão salva ainda.</p>') +
      '<label class="f" style="margin-top:8px">Salvar visão atual como<input id="vNome" placeholder="ex.: Matriz compacta"></label><button class="btn pri" id="vSalva" style="margin-top:6px">Salvar visão</button><p class="note">Guarda colunas, ordem, larguras, filtros, ordenação e densidade.</p>';
    var p = pop(ancora, h, 300);
    p.addEventListener("click", function (e) { var b = e.target.closest("button"); if (!b) return;
      if (b.id === "vSalva") { var n = $("#vNome", p).value.trim(); if (!n) return; P.visoes[n] = JSON.parse(JSON.stringify({ colunas: P.colunas, larguras: P.larguras, ordenacao: P.ordenacao, filtros: P.filtros, densidade: P.densidade, fixas: P.fixas })); IE.salvar(); u.toast("Visão salva"); popVisoes(ancora); }
      else if (b.dataset.ap) { var v = P.visoes[b.dataset.ap]; Object.assign(P, JSON.parse(JSON.stringify(v))); IE.salvar(); fechaPop(); aplicaDens(); G.render(); } else if (b.dataset.del) { delete P.visoes[b.dataset.del]; IE.salvar(); popVisoes(ancora); } });
  }
  function popNovaVar(ancora) {
    var cols = IE.COLS.filter(function (c) { return c.tipo === "num"; }).map(function (c) { return c.k; });
    var p = pop(ancora, '<h5>Nova variável (coluna)</h5><label class="f">Nome<input id="nvN"></label><label class="f" style="margin-top:6px">Tipo<select id="nvT"><option value="continua">Quantitativa contínua</option><option value="discreta">Quantitativa discreta</option><option value="dicotomica">Dicotômica (0/1)</option><option value="nominal">Qualitativa nominal</option><option value="ordinal">Qualitativa ordinal</option><option value="proxy">Proxy</option><option value="geografica">Geográfica</option><option value="derivada">Derivada (a ○ b)</option></select></label>' +
      '<label class="f" style="margin-top:6px">Unidade<input id="nvU"></label><div id="nvD" style="display:none"><div class="grid2"><label class="f">Campo a<select id="nvA">' + cols.map(function (k) { return '<option value="' + k + '">' + esc(IE.colDef(k).label) + "</option>"; }).join("") + '</select></label><label class="f">Operação<select id="nvO"><option>+</option><option>-</option><option>*</option><option>/</option></select></label></div><label class="f" style="margin-top:6px">Campo b<select id="nvB">' + cols.map(function (k) { return '<option value="' + k + '">' + esc(IE.colDef(k).label) + "</option>"; }).join("") + '</select></label></div><button class="btn pri" id="nvOk" style="margin-top:8px">Criar variável</button><p class="note">Definição completa (papel, codificação, transformação…) no módulo Variáveis.</p>', 320);
    $("#nvT", p).addEventListener("change", function () { $("#nvD", p).style.display = this.value === "derivada" ? "block" : "none"; });
    $("#nvOk", p).addEventListener("click", function () { var n = $("#nvN", p).value.trim(); if (!n) return u.toast("Informe o nome.", true); var t = $("#nvT", p).value, cam = "v_" + IE.slug(n);
      if (IE.P.variaveis.some(function (v) { return v.campo === cam || v.nome === n; })) return u.toast("Já existe variável com esse nome.", true);
      var v = IE.novaVariavel(n, t, $("#nvU", p).value.trim()); if (t === "derivada") v.derivada = { a: $("#nvA", p).value, op: $("#nvO", p).value, b: $("#nvB", p).value };
      IE.P.variaveis.push(v); IE.P.colunas.push(v.campo); IE.salvar(); fechaPop(); G.render(); u.toast("Variável criada e adicionada às colunas"); });
  }
  IE.slug = function (s) { return String(s).normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, "_").replace(/^_|_$/g, ""); };
  IE.novaVariavel = function (nome, tipo, un) { return { nome: nome, tecnico: IE.slug(nome), campo: "v_" + IE.slug(nome), descricao: "", unidade: un || "", tipo: tipo, papel: "ignorar", origem: tipo === "derivada" ? "derivada" : "manual", regra: "", codificacao: tipo === "nominal" ? "indicadoras" : "nenhuma", transformacao: "nenhuma", ausentes: "excluir", validacao: "", referencia: "", mapa: null, justificativa: "" }; };

  /* ---------------- painel de inspeção ---------------- */
  var lbF = [], lbI = 0, lbT = "";
  function abreLb(fotos, i, tit) { lbF = fotos; lbI = i; lbT = tit; var lb = $("#lb"); if (!lb) { lb = document.createElement("div"); lb.id = "lb"; lb.className = "lb"; lb.innerHTML = '<div class="t"></div><img alt=""><div class="nav"><button class="btn" data-l="-1">‹ Anterior</button><button class="btn" data-l="0">Fechar</button><button class="btn" data-l="1">Próxima ›</button></div>'; document.body.appendChild(lb);
    lb.addEventListener("click", function (e) { var b = e.target.closest("button"); if (b) { var d = +b.dataset.l; if (!d) lb.classList.remove("on"); else { lbI = (lbI + d + lbF.length) % lbF.length; pintaLb(); } } else if (e.target === lb) lb.classList.remove("on"); }); document.addEventListener("keydown", function (e) { if (!lb.classList.contains("on")) return; if (e.key === "Escape") lb.classList.remove("on"); else if (e.key === "ArrowRight") { lbI = (lbI + 1) % lbF.length; pintaLb(); } else if (e.key === "ArrowLeft") { lbI = (lbI - 1 + lbF.length) % lbF.length; pintaLb(); } }); }
    lb.classList.add("on"); pintaLb(); }
  function pintaLb() { var lb = $("#lb"); $("img", lb).src = lbF[lbI]; $("img", lb).referrerPolicy = "no-referrer"; $(".t", lb).textContent = lbT + " — foto " + (lbI + 1) + " de " + lbF.length + " (imagem da fonte; evidência auxiliar, não comprova padrão nem conservação)"; }
  IE.abreLb = abreLb;
  function painelInspecao() {
    var el = $(".insp", G.raiz), a = IE.porId(G.inspId); if (!a) { el.classList.remove("on"); G.inspOn = false; return; } el.classList.add("on");
    var e = IE.estado(a), f = a.fotos || [], idx = G.rows.findIndex(function (r) { return r.id === a.id; });
    function campo(k) { var d = IE.colDef(k), v = a[k]; return '<label class="f">' + esc(d.label) + (k in a._orig ? ' <span class="chip warn" title="Original: ' + esc(a._orig[k] == null ? "(vazio)" : a._orig[k]) + '">corrigido</span>' : "") + '<input data-k="' + k + '" value="' + esc(v == null ? "" : (d.tipo === "num" ? String(v).replace(".", ",") : v)) + '"></label>'; }
    var pend = []; IE.faltas(a).forEach(function (x) { pend.push("Informar " + x); }); if (!f.length) pend.push("Sem fotografia disponível na fonte"); if (a.latitude == null || a.longitude == null) pend.push("Sem coordenadas (necessárias para variáveis geográficas)");
    el.innerHTML = '<div class="hd"><b style="flex:1">Amostra #' + a.id + '</b><button class="btn sm" data-n="-1" aria-label="Anterior" title="Anterior (K)">↑</button><button class="btn sm" data-n="1" aria-label="Próxima" title="Próxima (J)">↓</button><button class="btn sm" data-x aria-label="Fechar painel">✕</button></div><div class="bd">' +
      (f.length ? '<img class="bigph" referrerpolicy="no-referrer" alt="Foto principal do anúncio" src="' + esc(f[0]) + '" data-big>' + (f.length > 1 ? '<div class="gal">' + f.map(function (u2, i) { return '<img referrerpolicy="no-referrer" loading="lazy" alt="" src="' + esc(u2) + '" data-i="' + i + '">'; }).join("") + "</div>" : "") : '<div class="bigph" style="display:grid;place-items:center" class="note">Sem fotografia disponível</div>') +
      '<p style="margin:8px 0 2px"><span class="chip ' + (IE.ESTADO_CLASSE[e.estado] || "") + '">' + esc(e.estado) + (e.manual ? " ✎" : "") + '</span> <button class="btn sm" data-st>Alterar situação</button></p>' +
      '<p class="note">Cadastral: <b>' + e.cadastral + "</b> · Informação: <b>" + e.informacao + '</b> · Representatividade estatística: <b>avaliar na análise exploratória</b></p>' +
      (e.razoes.length ? '<ul class="hist" style="max-height:none">' + e.razoes.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : "") +
      '<h4>Origem</h4><dl><dt>Fonte</dt><dd>' + esc(a.fonte) + "</dd><dt>Data da coleta</dt><dd>" + esc(a.data_coleta || "–") + "</dd><dt>Natureza</dt><dd>" + esc(a.natureza) + " (oferta; não é transação)</dd><dt>Link</dt><dd>" + (a.url ? '<a href="' + esc(a.url) + '" target="_blank" rel="noopener noreferrer">anúncio original ↗</a>' : "–") + "</dd></dl>" +
      '<h4>Descrição original</h4><p style="margin:0;font-size:12.5px">' + esc(a.titulo || "–") + "</p>" +
      '<h4>Dados (editáveis — o valor original é preservado)</h4><div class="ed">' + ["valor_total", "area_privativa", "area_construida", "area_territorial", "quartos", "suites", "banheiros", "vagas", "andar", "idade", "condominio", "iptu", "bairro", "endereco", "latitude", "longitude", "padrao", "conservacao"].map(campo).join("") + "</div>" +
      '<p class="note" style="margin:6px 0 0">Preço unitário (calculado, não observado): <b>' + (IE.valor(a, "valor_unitario") != null ? "R$ " + u.nf0.format(IE.valor(a, "valor_unitario")) + "/m²" : "–") + "</b></p>" +
      '<h4>Pendências identificadas</h4>' + (pend.length ? '<ul class="hist" style="max-height:none">' + pend.map(function (x) { return "<li>" + esc(x) + "</li>"; }).join("") + "</ul>" : '<p class="note">Nenhuma.</p>') +
      '<h4>Observações técnicas</h4><textarea data-k="obs" rows="3" style="width:100%;border:1px solid var(--line-2);border-radius:7px;background:var(--surface);padding:6px">' + esc(a.obs || "") + "</textarea>" +
      '<h4>Histórico</h4><ul class="hist">' + a.hist.slice().reverse().map(function (h) { return "<li>" + u.dataBR(h.t) + " · " + esc(h.tipo) + (h.campo ? " " + esc(h.campo) + ": " + esc(h.de == null ? "∅" : h.de) + " → " + esc(h.para == null ? "∅" : h.para) : "") + (h.nota ? " — " + esc(h.nota) : "") + "</li>"; }).join("") + "</ul></div>";
    el.onclick = function (ev) { var t = ev.target; if (t.matches("[data-x]")) { G.inspOn = false; G.inspId = null; el.classList.remove("on"); G.pinta(); return; }
      if (t.dataset.n) { var j = idx + +t.dataset.n; if (G.rows[j]) { ativa(j, G.act.c); G.inspId = G.rows[j].id; painelInspecao(); } return; } if (t.matches("[data-st]")) return popEstado([a.id], t);
      if (t.matches("[data-big]")) return abreLb(f, 0, "Amostra #" + a.id); if (t.dataset.i != null) return abreLb(f, +t.dataset.i, "Amostra #" + a.id); };
    $$("input[data-k],textarea[data-k]", el).forEach(function (inp) { inp.addEventListener("change", function () { var k = inp.dataset.k, d = IE.colDef(k), v = d.tipo === "num" ? u.parseNum(inp.value) : (inp.value.trim() || null); if (d.tipo === "num" && inp.value.trim() !== "" && v == null) return u.toast("Valor numérico inválido.", true);
      var l = []; if (k === "obs") { var antes = a.obs; a.obs = inp.value; a.hist.push({ t: u.agora(), tipo: "observacao", nota: "Observação técnica atualizada" }); if (antes !== a.obs) { IE.salvar(); } return; } if (IE.setVal(a, k, v, l)) { IE.commit(l); G.render(); painelInspecao(); } }); });
  }
  G.abrirInsp = function (id) { G.inspOn = true; G.inspId = id; painelInspecao(); G.pinta(); };

  /* ---------------- módulo Base amostral ---------------- */
  function aplicaDens() { document.body.setAttribute("data-dens", IE.P.densidade); }
  IE.mod.base = function (v) {
    var P = IE.P; aplicaDens(); G.inspOn = false; G.inspId = null; G.sel = { r1: 0, c1: 0, r2: 0, c2: 0 }; G.act = { r: 0, c: 0 };
    var par = P.params_originais, pills = "";
    if (par) { pills += '<span class="chip info" title="Parâmetros usados na coleta. Ficam registrados e não mudam.">' + esc((par.tipo_imovel || "").toLowerCase()) + " · " + (par.finalidade === "VENDA" ? "venda" : "locação") + " · " + esc(par.cidade) + (par.bairro ? " / " + esc(par.bairro) : "") + " · " + esc(par.uf) + "</span>";
      if (par.area_min || par.area_max) pills += '<span class="chip">' + (par.area_min || 0) + "–" + (par.area_max || "∞") + " m²</span>"; if (par.preco_min || par.preco_max) pills += '<span class="chip">R$ ' + u.nf0.format(par.preco_min || 0) + " – " + (par.preco_max ? u.nf0.format(par.preco_max) : "∞") + "</span>"; if (par.quartos_min) pills += '<span class="chip">≥ ' + par.quartos_min + " quartos</span>";
      if (P.meta) pills += '<span class="chip" title="Coleta registrada">' + esc(P.meta.quando) + " · " + esc(P.meta.fontes) + "</span>"; } else pills = '<span class="chip">Sem coleta vinculada (base manual/importada)</span>';
    v.innerHTML = '<div class="ws"><div class="wsmain"><div class="sumario"><b>Base amostral — Pesquisa de mercado</b> ' + pills + '<span class="kpis" style="margin-left:auto"></span></div>' +
      '<div class="tool"><input type="search" id="gBusca" placeholder="Buscar ( / )" aria-label="Buscar na base"><select id="gEst" aria-label="Filtrar por situação"><option value="">Todas as situações</option><option value="__usar">Na análise</option><option value="__fora">Fora da análise</option>' + IE.ESTADOS.map(function (s) { return "<option>" + s + "</option>"; }).join("") + '</select>' +
      '<button class="btn" id="gCols" data-pop>Colunas</button><button class="btn" id="gVis" data-pop>Visões</button><select id="gDens" aria-label="Densidade"><option value="compacto">Compacto</option><option value="confortavel">Confortável</option><option value="fotografico">Fotográfico</option></select>' +
      '<button class="btn" id="gUndo" title="Desfazer (Ctrl+Z)">↶</button><button class="btn" id="gRedo" title="Refazer (Ctrl+Y)">↷</button><button class="btn" id="gNova" data-pop>+ Variável</button><button class="btn" id="gAdd">+ Amostra</button>' +
      '<button class="btn" id="gUsar">Incluir marcadas</button><button class="btn" id="gTirar">Retirar marcadas</button><button class="btn" id="gEstM" data-pop>Situação…</button><button class="btn" id="gInsp">Painel</button><button class="btn" id="gAj" title="Atalhos">?</button></div>' +
      '<div class="gridwrap"><div class="gscroll" tabindex="0" role="grid" aria-label="Planilha de amostras (setas navegam, Enter edita, Ctrl+C/V copia e cola)"><div class="ghead"></div><div class="gin"></div></div><div class="vazio note" style="display:none;padding:20px"></div></div></div><aside class="insp" aria-label="Painel de inspeção do imóvel"></aside></div>';
    G.raiz = v; $("#gDens", v).value = P.densidade;
    var sc = $(".gscroll", v); sc.addEventListener("scroll", function () { if (!G._raf) G._raf = requestAnimationFrame(function () { G._raf = 0; G.pinta(); }); }); new ResizeObserver(function () { G.pinta(); }).observe(sc);
    sc.addEventListener("keydown", teclado); sc.addEventListener("paste", function (e) { if (G.edit) return; e.preventDefault(); colar((e.clipboardData || window.clipboardData).getData("text")); });
    var down = false;
    sc.addEventListener("mousedown", function (e) { var c = e.target.closest(".gc"); if (!c || e.target.matches("input,a,button")) return; var row = c.closest(".grow"), r = +row.dataset.r, ci = +c.dataset.c; if (G.edit) fechaEdicao(true); down = true;
      if (e.shiftKey && G.sel) { ativa(r, ci, true); } else if (G.cols[ci] === "id") { G.sel = { r1: r, c1: 0, r2: r, c2: G.cols.length - 1 }; G.act = { r: r, c: ci }; G.pinta(); } else ativa(r, ci); });
    sc.addEventListener("mouseover", function (e) { if (!down) return; var c = e.target.closest(".gc"); if (!c) return; var r = +c.closest(".grow").dataset.r; G.sel.r2 = r; G.sel.c2 = +c.dataset.c; G.pinta(); });
    document.addEventListener("mouseup", function () { down = false; });
    sc.addEventListener("dblclick", function (e) { var c = e.target.closest(".gc"); if (!c || e.target.matches("input,a")) return; abreEdicao(+c.closest(".grow").dataset.r, +c.dataset.c, null); });
    sc.addEventListener("click", function (e) { var t = e.target;
      if (t.matches('input[data-act="usar"]')) { var id = +t.closest(".grow").dataset.id, ids = selecao(); var alvo = ids.indexOf(id) >= 0 && ids.length > 1 ? ids : [id]; IE.definirUsar(alvo, t.checked); G.render(); return; }
      if (t.closest('[data-act="foto"]')) { var a = IE.porId(+t.closest(".grow").dataset.id); abreLb(a.fotos, 0, "Amostra #" + a.id); return; }
      var g = t.closest(".gh"); if (g && !t.matches(".rs")) { var k = g.dataset.k; if (t.dataset.act === "filtro") { popFiltro(k, t); return; } var o = IE.P.ordenacao; IE.P.ordenacao = !o || o.k !== k ? { k: k, dir: "asc" } : (o.dir === "asc" ? { k: k, dir: "desc" } : null); IE.salvar(); G.render(); } });
    // redimensionar e reordenar colunas
    sc.addEventListener("mousedown", function (e) { if (!e.target.matches(".rs")) return; e.preventDefault(); e.stopPropagation(); var g = e.target.closest(".gh"), k = g.dataset.k, x0 = e.clientX, w0 = largura(k);
      var mv = function (ev) { IE.P.larguras[k] = Math.max(40, w0 + ev.clientX - x0); G.render(); }, up = function () { document.removeEventListener("mousemove", mv); document.removeEventListener("mouseup", up); IE.salvar(); }; document.addEventListener("mousemove", mv); document.addEventListener("mouseup", up); }, true);
    var arrasta = null;
    sc.addEventListener("dragstart", function (e) { var g = e.target.closest(".gh"); if (!g) return; arrasta = g.dataset.k; e.dataTransfer.setData("text/plain", arrasta); e.dataTransfer.effectAllowed = "move"; });
    sc.addEventListener("dragover", function (e) { if (arrasta && e.target.closest(".gh")) e.preventDefault(); });
    sc.addEventListener("drop", function (e) { var g = e.target.closest(".gh"); if (!g || !arrasta || g.dataset.k === arrasta) return; e.preventDefault(); var cols = ordenadas(), i = cols.indexOf(arrasta), j = cols.indexOf(g.dataset.k); if (j < IE.P.fixas) return u.toast("Não é possível soltar sobre colunas fixas."); cols.splice(i, 1); cols.splice(j, 0, arrasta); IE.P.colunas = cols; arrasta = null; IE.salvar(); G.render(); });
    v.addEventListener("click", function (e) { var b = e.target.closest("[data-act='limpar']"); if (b) { IE.P.filtros = {}; G.busca = ""; G.filtroEstado = ""; $("#gBusca", v).value = ""; $("#gEst", v).value = ""; IE.salvar(); G.render(); } });
    $("#gBusca", v).addEventListener("input", function () { G.busca = this.value; G.render(); }); $("#gEst", v).addEventListener("change", function () { G.filtroEstado = this.value; G.render(); });
    $("#gDens", v).addEventListener("change", function () { P.densidade = this.value; aplicaDens(); IE.salvar(); G.render(); });
    $("#gCols", v).addEventListener("click", function () { popColunas(this); }); $("#gVis", v).addEventListener("click", function () { popVisoes(this); }); $("#gNova", v).addEventListener("click", function () { popNovaVar(this); });
    $("#gUndo", v).addEventListener("click", IE.desfazer); $("#gRedo", v).addEventListener("click", IE.refazer);
    $("#gAdd", v).addEventListener("click", function () { var id = P.amostras.reduce(function (m, a) { return Math.max(m, a.id || 0); }, 0) + 1; var a = IE.amostraDeRegistro({ id: id, fonte: "Manual", data_coleta: new Date().toISOString().slice(0, 10), natureza: "oferta", uf: par ? par.uf : "", cidade: par ? par.cidade : "", tipo: par ? par.tipo_imovel : "", finalidade: par ? par.finalidade : "VENDA", alerta: "OK", fora_filtros: false, motivos: [], fotos: [] });
      a.hist = [{ t: u.agora(), tipo: "cadastro", nota: "Cadastro manual" }]; a.usar = false; P.amostras.push(a); IE.commit([]); G.render(); ativa(G.rows.indexOf(a), G.cols.indexOf("area_privativa") >= 0 ? G.cols.indexOf("area_privativa") : 0); G.focoGrade(); u.toast("Amostra #" + id + " criada (preencha os dados e marque para usar)"); });
    $("#gUsar", v).addEventListener("click", function () { var ids = selecao(); if (!ids.length) return u.toast("Selecione linhas na planilha."); IE.definirUsar(ids, true); G.render(); });
    $("#gTirar", v).addEventListener("click", function () { var ids = selecao(); if (!ids.length) return u.toast("Selecione linhas na planilha."); IE.definirUsar(ids, false); G.render(); });
    $("#gEstM", v).addEventListener("click", function () { var ids = selecao(); if (!ids.length) return u.toast("Selecione linhas na planilha."); popEstado(ids, this); });
    $("#gInsp", v).addEventListener("click", function () { if (G.inspOn) { G.inspOn = false; G.inspId = null; $(".insp", v).classList.remove("on"); G.pinta(); } else { var r = G.rows[G.act.r]; if (r) G.abrirInsp(r.id); } });
    $("#gAj", v).addEventListener("click", function () { var p = pop(this, '<h5>Atalhos da planilha</h5><p class="note" style="line-height:1.9"><span class="kbd">↑↓←→</span> navegar · <span class="kbd">Shift</span>+setas selecionar intervalo<br><span class="kbd">Enter</span>/<span class="kbd">F2</span> ou digitar: editar · <span class="kbd">Esc</span> cancelar<br><span class="kbd">Ctrl+C</span>/<span class="kbd">V</span>/<span class="kbd">X</span>: copiar, colar (do Excel), recortar<br><span class="kbd">Ctrl+D</span> preencher para baixo · <span class="kbd">Del</span> limpar<br><span class="kbd">Ctrl+Z</span>/<span class="kbd">Y</span> desfazer/refazer · <span class="kbd">Espaço</span> incluir/retirar da análise<br><span class="kbd">J</span>/<span class="kbd">K</span> próxima/anterior com painel aberto · <span class="kbd">/</span> buscar · <span class="kbd">I</span> painel<br>Clique no cabeçalho: ordenar · ⏷ filtrar · arraste para reordenar · borda para redimensionar</p>', 380); });
    v.addEventListener("keydown", function (e) { if (G.edit || /INPUT|TEXTAREA|SELECT/.test(e.target.tagName)) return; if (e.key === "/") { e.preventDefault(); $("#gBusca", v).focus(); } else if (e.key.toLowerCase() === "i" && !e.ctrlKey) { $("#gInsp", v).click(); } else if (G.inspOn && (e.key.toLowerCase() === "j" || e.key.toLowerCase() === "k")) { var j = G.act.r + (e.key.toLowerCase() === "j" ? 1 : -1); ativa(j, G.act.c); } });
    IE.on("dados", dadosHandler); G.dados = true; IE.sair = function () { G.raiz = null; document.body.removeAttribute("data-dens"); fechaPop(); };
    G.render(); setTimeout(G.focoGrade, 0);
  };
  function dadosHandler() { if (G.raiz && IE.atual === "base") { G.render(); if (G.inspOn) painelInspecao(); } }
  IE.registrar("base", "Base amostral", IE.mod.base);

  /* ---------------- importação de planilha (CSV/TSV) ---------------- */
  function sep(txt) { var l = txt.split("\n")[0]; var c = { ";": (l.match(/;/g) || []).length, "\t": (l.match(/\t/g) || []).length, ",": (l.match(/,/g) || []).length }; return Object.keys(c).sort(function (a, b) { return c[b] - c[a]; })[0]; }
  function parseCSV(txt, s) { var rows = [], row = [], cur = "", q = false; for (var i = 0; i < txt.length; i++) { var ch = txt[i];
    if (q) { if (ch === '"') { if (txt[i + 1] === '"') { cur += '"'; i++; } else q = false; } else cur += ch; } else if (ch === '"') q = true; else if (ch === s) { row.push(cur); cur = ""; } else if (ch === "\n") { row.push(cur.replace(/\r$/, "")); rows.push(row); row = []; cur = ""; } else cur += ch; }
    if (cur !== "" || row.length) { row.push(cur.replace(/\r$/, "")); rows.push(row); } return rows.filter(function (r) { return r.some(function (x) { return x.trim() !== ""; }); }); }
  var ALIAS = { preco: "valor_total", preco_total: "valor_total", valor: "valor_total", valor_total: "valor_total", valor_oferta: "valor_total", area: "area_privativa", area_privativa: "area_privativa", area_m2: "area_privativa", area_util: "area_privativa", preco_unitario: "valor_unitario", dormitorios: "quartos", garagens: "vagas", vagas_na_garagem: "vagas", link: "url", link_original: "url", fonte: "fonte", bairro: "bairro", endereco: "endereco", latitude: "latitude", lat: "latitude", longitude: "longitude", lon: "longitude", lng: "longitude", idade: "idade", quartos: "quartos", suites: "suites", banheiros: "banheiros", andar: "andar", condominio: "condominio", iptu: "iptu", cidade: "cidade", uf: "uf", padrao: "padrao", padrao_construtivo: "padrao", conservacao: "conservacao", estado_de_conservacao: "conservacao", area_construida: "area_construida", area_territorial: "area_territorial", observacoes: "obs", descricao: "titulo", titulo: "titulo", id: "_ignorar", data_da_coleta: "data_coleta", data_coleta: "data_coleta", natureza: "natureza" };
  IE.importarCSV = function (txt, nomeFonte) {
    var P = IE.P, s = sep(txt), tab = parseCSV(txt, s); if (tab.length < 2) throw new Error("O arquivo precisa de uma linha de cabeçalho e ao menos uma linha de dados.");
    var cab = tab[0].map(function (h) { return h.trim(); }), mapa = cab.map(function (h) { var sl = IE.slug(h); if (ALIAS[sl]) return ALIAS[sl]; var d = IE.COLS.filter(function (c) { return IE.slug(c.label) === sl; })[0]; return d ? d.k : null; });
    var novasVars = [], id0 = P.amostras.reduce(function (m, a) { return Math.max(m, a.id || 0); }, 0);
    cab.forEach(function (h, i) { if (mapa[i] == null && h) { var existente = P.variaveis.filter(function (v) { return v.nome === h; })[0]; if (!existente) { var v = IE.novaVariavel(h, "continua", ""); v.origem = "importacao"; P.variaveis.push(v); P.colunas.push(v.campo); novasVars.push(h); mapa[i] = v.campo; } else mapa[i] = existente.campo; } });
    var n = 0, lote = [];
    tab.slice(1).forEach(function (lin) { id0++; var a = IE.amostraDeRegistro({ id: id0, fonte: nomeFonte || "Importado", data_coleta: new Date().toISOString().slice(0, 10), natureza: "oferta", uf: P.params_originais ? P.params_originais.uf : "", cidade: P.params_originais ? P.params_originais.cidade : "", tipo: P.params_originais ? P.params_originais.tipo_imovel : "", finalidade: "VENDA", alerta: "OK", fora_filtros: false, motivos: [], fotos: [] });
      a.hist = [{ t: u.agora(), tipo: "importacao", nota: "Importado de planilha (" + (nomeFonte || "arquivo") + ")" }];
      lin.forEach(function (cel, i) { var k = mapa[i]; if (!k || k === "_ignorar") return; var d = IE.colDef(k), v = cel.trim(); if (v === "") return; a[k] = d.tipo === "num" ? u.parseNum(v) : (d.tipo === "bool" ? (/^(1|sim|s|true|x)$/i.test(v) ? 1 : 0) : v); });
      if (a.valor_total == null && a.area_privativa == null) { id0--; return; } a._alerta = "OK"; a.usar = !IE.faltas(a).length; P.amostras.push(a); n++; });
    P.historico_projeto.push({ t: u.agora(), tipo: "importacao", nota: n + " amostras importadas" + (novasVars.length ? "; novas variáveis: " + novasVars.join(", ") : "") }); IE.commit([]); return { n: n, novasVars: novasVars };
  };
})(window.IE);
