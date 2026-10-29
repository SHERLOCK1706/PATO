"use strict";
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const nf = (v, d = 2) => (v === null || v === undefined || v === "") ? "" :
  (typeof v === "number" ? v.toLocaleString("pt-BR", { minimumFractionDigits: 0, maximumFractionDigits: d }) : String(v));
const nfEd = v => typeof v === "number" ? v.toLocaleString("pt-BR", { useGrouping: false, maximumFractionDigits: 6 }) : (v ?? "");
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

const E = { cat: null, projetos: [], pid: null, resumo: null, catInv: null, pagina: 0, itens: [], sel: new Set(),
  mapa: null, camadas: {}, geo: null, posicionar: null, alertaNivel: "erro" };
const POR_PAG = 200;
const BASE = ["snv", "km_ini", "km_fim", "lat_ini", "lon_ini", "lat_fim", "lon_fim", "lado", "condicao", "tipo"];

async function api(url, op = {}) {
  const r = await fetch(url, op);
  if (!r.ok) {
    let msg = r.statusText;
    try { msg = (await r.json()).detail || msg; } catch (_) {}
    throw new Error(typeof msg === "string" ? msg : JSON.stringify(msg));
  }
  const t = r.headers.get("content-type") || "";
  return t.includes("json") ? r.json() : r.text();
}
const jpost = (url, body, method = "POST") => api(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
function toast(msg) { const t = $("#toast"); t.textContent = msg; t.classList.add("mostrar"); clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("mostrar"), 3200); }
function erro(e) { console.error(e); toast("Erro: " + e.message); }

// ---------------------------------------------------------------- navegação
function irAba(nome) {
  $$("#abas button").forEach(b => b.classList.toggle("ativa", b.dataset.aba === nome));
  $$(".aba").forEach(s => s.classList.toggle("ativa", s.id === "aba-" + nome));
  if (nome === "mapa") abrirMapa();
  if (nome === "inventario") carregarItens();
  if (nome === "alertas") renderAlertas();
  if (nome === "projeto") renderProjeto();
  try { localStorage.setItem("pato.aba", nome); } catch (_) {}
}
$$("#abas button").forEach(b => b.onclick = () => irAba(b.dataset.aba));
$$("[data-ir]").forEach(b => b.onclick = () => irAba(b.dataset.ir));

// ---------------------------------------------------------------- projetos
async function carregarProjetos(selecionar) {
  E.projetos = await api("/api/projetos");
  const sel = $("#selProjeto");
  sel.innerHTML = E.projetos.map(p => `<option value="${p.id}">${esc(p.nome || p.rodovia || "Projeto " + p.id)} · ${p.n_itens} itens</option>`).join("");
  let pid = selecionar || E.pid;
  if (!pid) { try { pid = +localStorage.getItem("pato.pid"); } catch (_) {} }
  if (!E.projetos.some(p => p.id === pid)) pid = E.projetos[0]?.id || null;
  E.pid = pid;
  if (pid) sel.value = pid;
  $("#vazio").classList.toggle("oculto", !!pid);
  $("#painelConteudo").classList.toggle("oculto", !pid);
  if (pid) await carregarResumo();
}
$("#selProjeto").onchange = async e => {
  E.pid = +e.target.value; E.geo = null; E.pagina = 0;
  try { localStorage.setItem("pato.pid", E.pid); } catch (_) {}
  await carregarResumo();
  const ativa = $("#abas button.ativa").dataset.aba; irAba(ativa);
};
$("#btnNovo").onclick = () => dialogo("Novo projeto", [
  ["nome", "Nome"], ["rodovia", "Rodovia"], ["km_ini", "km inicial", "number"], ["km_fim", "km final", "number"]],
  async v => { const p = await jpost("/api/projetos", v); await carregarProjetos(p.id); irAba("projeto"); });

async function carregarResumo() {
  if (!E.pid) return;
  E.resumo = await api(`/api/projetos/${E.pid}/resumo`);
  renderPainel();
}

// ---------------------------------------------------------------- painel
function renderPainel() {
  const R = E.resumo, p = R.projeto;
  $("#cabProj").innerHTML = `<h2>${esc(p.rodovia || p.nome || "")} · ${esc(p.segmento || "")}</h2>
    <p>${esc(p.trecho || "")}${p.subtrecho ? " — " + esc(p.subtrecho) : ""}</p>
    <p>SNV ${esc(p.snv || "—")} · Inventário ${esc(p.data_inventario || "—")} · Data-base ${esc(p.data_base || "—")}</p>`;
  $("#cards").innerHTML = R.painel.map(c => `<div class="card"><div class="r">${esc(c.rotulo)}</div>
    <div class="v">${nf(c.valor, 2)}<span class="u">${esc(c.unidade)}</span></div></div>`).join("");
  let g = "", h = "<tr><th>Descrição</th><th class=n>Quantidade</th></tr>";
  for (const x of R.resumo_invent) {
    if (x.grupo !== g) { g = x.grupo; h += `<tr class="grupo"><td colspan=2>${esc(g)}</td></tr>`; }
    h += `<tr><td>${esc(x.descricao)}</td><td class=n>${nf(x.valor, 3)}</td></tr>`;
  }
  $("#tabResumo").innerHTML = h;
  $("#tabPato").innerHTML = "<tr><th>Item</th><th>Serviço</th><th class=n>Inventário</th><th>Un.</th></tr>" +
    R.pato.map(x => `<tr title="${esc(x.regra)}"><td>${esc(x.item)}</td><td>${esc(x.servico)}<br><small>${esc(x.regra)}</small></td>
      <td class=n>${nf(x.valor, 3)}</td><td>${esc(x.unidade)}</td></tr>`).join("");
  $("#chipsCat").innerHTML = Object.entries(E.cat.categorias).map(([k, c]) => {
    const n = R.categorias[k]?.n || 0;
    return `<span class="chip" data-cat="${k}"><span class="bola" style="background:${c.cor}"></span>${esc(c.nome)} <span class="q">${n}</span></span>`;
  }).join("");
  $$("#chipsCat .chip").forEach(ch => ch.onclick = () => { E.catInv = ch.dataset.cat; E.pagina = 0; irAba("inventario"); });
  const na = R.n_alertas.erro || 0;
  $("#nAlertas").textContent = na ? na : "";
}

// ---------------------------------------------------------------- inventário
function colunasCat(cat) {
  const geom = E.cat.categorias[cat].geom;
  let base = BASE.slice();
  if (geom === "ponto") base = base.filter(c => !["km_fim", "lat_fim", "lon_fim"].includes(c));
  return base.concat(E.cat.colunas[cat] || [], ["obs"]);
}
function renderChipsInv() {
  const R = E.resumo;
  const cats = Object.keys(E.cat.categorias);
  if (!E.catInv) E.catInv = cats.find(c => R.categorias[c]) || "SEG";
  $("#chipsInv").innerHTML = cats.map(k => {
    const c = E.cat.categorias[k], n = R.categorias[k]?.n || 0;
    return `<span class="chip ${k === E.catInv ? "ativo" : ""}" data-cat="${k}"><span class="bola" style="background:${c.cor}"></span>${esc(c.nome)} <span class="q">${n}</span></span>`;
  }).join("");
  $$("#chipsInv .chip").forEach(ch => ch.onclick = () => { E.catInv = ch.dataset.cat; E.pagina = 0; carregarItens(); });
}
let _buscaH;
["#fKmDe", "#fKmAte", "#fTexto"].forEach(s => $(s).oninput = () => { clearTimeout(_buscaH); _buscaH = setTimeout(() => { E.pagina = 0; carregarItens(); }, 300); });

async function carregarItens() {
  if (!E.pid) return;
  renderChipsInv();
  const q = new URLSearchParams({ categoria: E.catInv });
  if ($("#fKmDe").value) q.set("km_de", $("#fKmDe").value);
  if ($("#fKmAte").value) q.set("km_ate", $("#fKmAte").value);
  if ($("#fTexto").value) q.set("q", $("#fTexto").value);
  E.itens = await api(`/api/projetos/${E.pid}/itens?${q}`);
  E.sel.clear(); $("#btnDelItens").disabled = true;
  renderItens();
}
function renderItens() {
  const cat = E.catInv, cols = colunasCat(cat), R = E.cat.rotulos;
  const meds = E.itens.length ? Object.keys(E.itens[0].medidas) : [];
  const ini = E.pagina * POR_PAG, pag = E.itens.slice(ini, ini + POR_PAG);
  atualizarInfoInv();
  let h = `<thead><tr><th><input type="checkbox" id="selTodos" aria-label="Selecionar todos"></th><th></th>` +
    cols.map(c => `<th>${esc(R[c] || c)}</th>`).join("") + meds.map(m => `<th class="n">${esc(E.cat.medidas[m] || m)} (${esc(E.cat.unidades[m] || "")})</th>`).join("") + `</tr></thead><tbody>`;
  for (const it of pag) {
    h += `<tr data-id="${it.id}"><td><input type="checkbox" class="selItem" ${E.sel.has(it.id) ? "checked" : ""} aria-label="Selecionar"></td>
      <td><button class="btn" data-mapa="${it.id}" title="Ver no mapa">⌖</button></td>`;
    for (const c of cols) {
      const v = BASE.includes(c) || c === "obs" ? it[c] : it.dados[c];
      h += `<td contenteditable="true" data-campo="${c}" class="${typeof v === "number" ? "n" : ""}">${esc(nfEd(v))}</td>`;
    }
    h += meds.map(m => `<td class="n calc">${nf(it.medidas[m], 3)}</td>`).join("") + "</tr>";
  }
  $("#tabItens").innerHTML = h + "</tbody>";
  const np = Math.ceil(E.itens.length / POR_PAG);
  $("#pagInv").innerHTML = np > 1 ? `<button class="btn" id="pgAnt" ${E.pagina ? "" : "disabled"}>‹</button> Página ${E.pagina + 1} de ${np}
    <button class="btn" id="pgProx" ${E.pagina < np - 1 ? "" : "disabled"}>›</button>` : "";
  if (np > 1) { $("#pgAnt").onclick = () => { E.pagina--; renderItens(); }; $("#pgProx").onclick = () => { E.pagina++; renderItens(); }; }
  $("#selTodos").onchange = e => { $$(".selItem").forEach(c => { c.checked = e.target.checked; c.onchange(); }); };
  $$(".selItem").forEach(c => c.onchange = () => {
    const id = +c.closest("tr").dataset.id; c.checked ? E.sel.add(id) : E.sel.delete(id);
    $("#btnDelItens").disabled = !E.sel.size;
  });
  $$("[data-mapa]").forEach(b => b.onclick = () => verNoMapa(+b.dataset.mapa));
  $$("#tabItens td[contenteditable]").forEach(td => {
    td.dataset.orig = td.textContent;
    td.onkeydown = e => { if (e.key === "Enter") { e.preventDefault(); td.blur(); } if (e.key === "Escape") { td.textContent = td.dataset.orig; td.blur(); } };
    td.onblur = () => salvarCelula(td);
  });
}
function atualizarInfoInv() {
  const meds = E.itens.length ? Object.keys(E.itens[0].medidas) : [];
  const tot = {};
  for (const it of E.itens) for (const m of meds) tot[m] = (tot[m] || 0) + (it.medidas[m] || 0);
  $("#infoInv").innerHTML = `${E.itens.length} itens · ` + meds.map(m => `${E.cat.medidas[m] || m}: <b>${nf(tot[m], 2)}</b> ${E.cat.unidades[m] || ""}`).join(" · ") +
    ` · Clique numa célula para editar (Enter salva).`;
}
async function salvarCelula(td) {
  const novo = td.textContent.trim();
  if (novo === td.dataset.orig) return;
  const id = +td.closest("tr").dataset.id, campo = td.dataset.campo;
  try {
    const it = await jpost(`/api/itens/${id}`, { [campo]: novo === "" ? null : novo }, "PUT");
    td.dataset.orig = novo; td.classList.add("salvo"); setTimeout(() => td.classList.remove("salvo"), 900);
    const i = E.itens.findIndex(x => x.id === id);
    if (i >= 0) {
      E.itens[i] = it;
      const calc = $$("td.calc", td.closest("tr"));
      Object.values(it.medidas).forEach((v, k) => { if (calc[k]) calc[k].textContent = nf(v, 3); });
      atualizarInfoInv();
    }
    E.geo = null; carregarResumo();
  } catch (e) { td.textContent = td.dataset.orig; erro(e); }
}
$("#btnDelItens").onclick = async () => {
  if (!confirm(`Excluir ${E.sel.size} item(ns)?`)) return;
  await jpost("/api/itens/excluir", [...E.sel]); E.geo = null; await carregarResumo(); carregarItens();
};
$("#btnAddItem").onclick = () => {
  const cols = colunasCat(E.catInv).map(c => [c, E.cat.rotulos[c] || c,
    ["km_ini", "km_fim", "lat_ini", "lon_ini", "lat_fim", "lon_fim"].includes(c) ? "number" : "text"]);
  dialogo(`Novo item — ${E.cat.categorias[E.catInv].nome}`, cols, async v => {
    Object.keys(v).forEach(k => v[k] === "" && delete v[k]);
    await jpost(`/api/projetos/${E.pid}/itens`, { ...v, categoria: E.catInv });
    E.geo = null; await carregarResumo(); carregarItens(); toast("Item adicionado");
  });
};

// ---------------------------------------------------------------- mapa
async function abrirMapa() {
  if (!E.pid) return;
  if (!E.mapa) {
    E.mapa = L.map("mapa", { preferCanvas: true });
    L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", { maxZoom: 19, attribution: "© OpenStreetMap" }).addTo(E.mapa);
    E.mapa.on("click", ev => { if (E.posicionar) posicionarItem(ev.latlng); });
  }
  setTimeout(() => E.mapa.invalidateSize(), 50);
  if (E.geo) return;
  E.geo = await api(`/api/projetos/${E.pid}/geojson`);
  Object.values(E.camadas).forEach(l => E.mapa.removeLayer(l));
  E.camadas = {};
  const grupos = {};
  for (const f of E.geo.features) (grupos[f.properties.categoria] ||= []).push(f);
  const erros = new Set((E.resumo?.alertas || []).filter(a => a.nivel === "erro").map(a => a.id));
  for (const [cat, feats] of Object.entries(grupos)) {
    const cor = E.cat.categorias[cat].cor;
    E.camadas[cat] = L.geoJSON({ type: "FeatureCollection", features: feats }, {
      style: f => ({ color: cor, weight: cat === "SEG" ? 6 : 4, opacity: cat === "SEG" ? .35 : .85, dashArray: f.properties.estimado ? "6 6" : null }),
      pointToLayer: (f, ll) => L.circleMarker(ll, { radius: erros.has(f.properties.id) ? 7 : 4, color: erros.has(f.properties.id) ? "#b42318" : cor,
        fillColor: cor, fillOpacity: .85, weight: erros.has(f.properties.id) ? 3 : 1 }),
      onEachFeature: (f, l) => l.bindPopup(() => popup(f.properties)),
    }).addTo(E.mapa);
  }
  $("#legenda").innerHTML = "<b>Camadas</b>" + Object.keys(grupos).map(c => `<label><input type="checkbox" checked data-camada="${c}">
    <span class="bola" style="background:${E.cat.categorias[c].cor}"></span>${esc(E.cat.categorias[c].nome)}<span class="q">${grupos[c].length}</span></label>`).join("") +
    `<p class="nota" style="margin-top:6px">Tracejado = posição estimada pelo km. Contorno vermelho = alerta de coordenada.</p>`;
  $$("[data-camada]").forEach(c => c.onchange = () => c.checked ? E.camadas[c.dataset.camada].addTo(E.mapa) : E.mapa.removeLayer(E.camadas[c.dataset.camada]));
  const b = E.camadas.SEG ? E.camadas.SEG.getBounds() : L.featureGroup(Object.values(E.camadas)).getBounds();
  if (b.isValid()) E.mapa.fitBounds(b, { padding: [20, 20] });
}
function popup(p) {
  const nome = E.cat.categorias[p.categoria].nome;
  const linhas = Object.entries(p).filter(([k, v]) => !["cor", "categoria", "id", "projeto_id", "estimado", "ordem"].includes(k) && v !== null && v !== "")
    .map(([k, v]) => `<tr><td>${esc(E.cat.rotulos[k] || k.replace("calc_", "= "))}</td><td><b>${esc(typeof v === "number" ? nf(v, 6) : v)}</b></td></tr>`).join("");
  return `<b>${esc(nome)}</b>${p.estimado ? ' <span class="tag">posição estimada</span>' : ""}<table>${linhas}</table>
    <button class="btn" onclick="iniciarPosicionar(${p.id}, 'ini')">Definir coordenada ${p.km_fim != null ? "inicial" : ""} no mapa</button>
    ${p.km_fim != null ? `<button class="btn" onclick="iniciarPosicionar(${p.id}, 'fim')">final</button>` : ""}`;
}
window.iniciarPosicionar = (id, ponta) => {
  E.posicionar = { id, ponta }; E.mapa.closePopup();
  const a = $("#avisoPosicionar"); a.textContent = `Clique no mapa para posicionar (${ponta === "ini" ? "inicial" : "final"}) · Esc cancela`; a.classList.remove("oculto");
};
document.addEventListener("keydown", e => { if (e.key === "Escape" && E.posicionar) { E.posicionar = null; $("#avisoPosicionar").classList.add("oculto"); } });
async function posicionarItem(ll) {
  const { id, ponta } = E.posicionar; E.posicionar = null; $("#avisoPosicionar").classList.add("oculto");
  try {
    await jpost(`/api/itens/${id}`, { [`lat_${ponta}`]: +ll.lat.toFixed(6), [`lon_${ponta}`]: +ll.lng.toFixed(6) }, "PUT");
    toast("Coordenada gravada"); E.geo = null; await carregarResumo(); abrirMapa();
  } catch (e) { erro(e); }
}
async function verNoMapa(id) {
  irAba("mapa"); await abrirMapa();
  for (const lay of Object.values(E.camadas)) lay.eachLayer(l => {
    if (l.feature?.properties.id === id) {
      if (l.getBounds) E.mapa.fitBounds(l.getBounds(), { maxZoom: 16 }); else E.mapa.setView(l.getLatLng(), 16);
      l.openPopup();
    }
  });
}

// ---------------------------------------------------------------- alertas
async function renderLog() {
  if (!E.pid) return;
  const ent = await api(`/api/projetos/${E.pid}/log?tipo=${encodeURIComponent("padronização")}`);
  if (!ent.length) { $("#resLog").textContent = "Nenhum ajuste de nomenclatura registrado para este projeto."; return; }
  const g = {};
  for (const e of ent) {
    const k = [e.situacao, e.categoria, e.campo, e.de, e.para, e.regra].join("|");
    (g[k] ||= { ...e, n: 0, ex: [] }).n++;
    if (g[k].ex.length < 3 && e.origem) g[k].ex.push(e.origem);
  }
  const lst = Object.values(g).sort((a, b) => (a.situacao > b.situacao ? 1 : -1) || b.n - a.n);
  $("#resLog").innerHTML = `<div class="tabela-rolagem" style="max-height:320px"><table class="tab"><tr><th>Situação</th><th>Cat.</th><th>Campo</th><th>Original</th><th>Padrão</th><th class=n>Qtde</th><th>Regra</th><th>Exemplos</th></tr>` +
    lst.map(x => `<tr class="${x.situacao.startsWith("fora") ? "sit-verificar" : x.situacao.includes("conferir") ? "sit-conferir" : "sit-corrigido"}">
      <td>${esc(x.situacao)}</td><td>${esc(x.categoria)}</td><td>${esc(x.campo)}</td><td>${esc(x.de ?? "")}</td><td><b>${esc(x.para ?? "—")}</b></td>
      <td class=n>${x.n}</td><td>${esc(x.regra)}</td><td><small>${esc(x.ex.join(", "))}</small></td></tr>`).join("") + "</table></div>";
}
function renderAlertas() {
  if (!E.resumo) return;
  renderLog().catch(erro);
  const A = E.resumo.alertas, n = E.resumo.n_alertas;
  $("#chipsAlerta").innerHTML = [["erro", "Erros"], ["aviso", "Avisos"], ["info", "Informações"]].map(([k, r]) =>
    `<span class="chip ${E.alertaNivel === k ? "ativo" : ""}" data-n="${k}">${r} <span class="q">${n[k] || 0}</span></span>`).join("");
  $$("#chipsAlerta .chip").forEach(c => c.onclick = () => { E.alertaNivel = c.dataset.n; renderAlertas(); });
  const lst = A.filter(a => a.nivel === E.alertaNivel).slice(0, 1000);
  $("#tabAlertas").innerHTML = "<tr><th>Nível</th><th>Categoria</th><th>Mensagem</th><th></th></tr>" + lst.map(a =>
    `<tr><td><span class="tag ${a.nivel}">${a.nivel}</span></td><td>${esc(E.cat.categorias[a.categoria].nome)}</td><td>${esc(a.mensagem)}</td>
     <td><button class="btn" data-mapa="${a.id}">Ver no mapa</button></td></tr>`).join("");
  $$("#tabAlertas [data-mapa]").forEach(b => b.onclick = () => verNoMapa(+b.dataset.mapa));
}

// ---------------------------------------------------------------- correções
const SIT_CLS = { "corrigido": "sit-corrigido", "corrigido — conferir": "sit-conferir", "recortado": "sit-recortado",
  "removido": "sit-removido", "verificar em campo": "sit-verificar" };
$("#btnAnalisar").onclick = async () => {
  const box = $("#resCorrecao"); box.innerHTML = `<p class="carregando">Analisando…</p>`;
  const fd = new FormData();
  if ($("#arqSnv").files[0]) fd.append("snv", $("#arqSnv").files[0]);
  if ($("#verSnv").value) fd.append("versao", $("#verSnv").value);
  try {
    const an = await api(`/api/projetos/${E.pid}/corrigir/analisar`, { method: "POST", body: fd });
    const R = an.resumo, S = an.snv;
    let filtro = null;
    const tabSnv = (t) => `<table class="tab"><tr><th>Código</th><th class=n>km inicial</th><th class=n>km final</th></tr>` +
      t.map(x => `<tr><td>${esc(x.codigo)}</td><td class=n>${nf(x.km_ini, 3)}</td><td class=n>${nf(x.km_fim, 3)}</td></tr>`).join("") + "</table>";
    const desenhar = () => {
      const lst = an.acoes.filter(a => !filtro || a.situacao === filtro);
      $("#tabAcoes").innerHTML = "<tr><th>Situação</th><th>Origem</th><th>km</th><th>Campo</th><th>Original</th><th>Corrigido</th><th>Motivo</th><th></th></tr>" +
        lst.slice(0, 2000).map(a => `<tr class="${SIT_CLS[a.situacao]}"><td>${esc(a.situacao)}</td><td>${esc(a.origem || "")}</td>
          <td class=n>${nf(a.km_ini, 3)}${a.km_fim != null ? "–" + nf(a.km_fim, 3) : ""}</td><td>${esc(a.campo)}</td>
          <td>${esc(a.de ?? "")}</td><td><b>${esc(a.para ?? "")}</b></td><td>${esc(a.motivo)}<br><small>${esc(a.metodo)} · confiança ${esc(a.confianca)}</small></td>
          <td>${a.id != null ? `<button class="btn" data-mapa="${a.id}">Mapa</button>` : ""}</td></tr>`).join("");
      $$("#tabAcoes [data-mapa]").forEach(b => b.onclick = () => verNoMapa(+b.dataset.mapa));
    };
    box.innerHTML = `<div class="cards" style="margin-top:12px">${Object.entries(R).map(([k, v]) =>
        `<div class="card ${SIT_CLS[k]}" data-sit="${esc(k)}" style="cursor:pointer"><div class="r">${esc(k)}</div><div class="v">${v.itens}<span class="u">itens</span></div></div>`).join("")}</div>
      <div class="grade2"><div><h4>SNV</h4><p class="nota">Versão declarada: <b>${esc(S.versao_inventario || "—")}</b> · Referência: <b>${esc(S.fonte_referencia)}</b> ·
        ${Math.round(S.concordancia * 100)}% dos itens coerentes com o cadastro de segmentos.</p>
        ${S.observacoes.map(o => `<p class="nota">• ${esc(o)}</p>`).join("")}</div>
        <div class="grade2"><div><h4>Cadastro de segmentos</h4>${tabSnv(S.cadastro_segmentos)}</div><div><h4>Referência</h4>${tabSnv(S.tabela_referencia)}</div></div></div>
      <div class="legenda-sit">${Object.entries(SIT_CLS).map(([k, c]) => `<span class="${c}">${esc(k)}</span>`).join("")}</div>
      <div class="linha-botoes"><button class="btn primario" id="btnAplicarCorr">Aplicar correções</button>
        <span class="nota">“Verificar em campo” não altera nada; os valores originais ficam guardados em cada item.</span></div>
      <div id="resAplicar"></div>
      <div class="tabela-rolagem" style="margin-top:10px"><table class="tab" id="tabAcoes"></table></div>`;
    $$(".cards [data-sit]", box).forEach(c => c.onclick = () => { filtro = filtro === c.dataset.sit ? null : c.dataset.sit; desenhar(); });
    desenhar();
    $("#btnAplicarCorr").onclick = async () => {
      if (!confirm("Aplicar as correções no inventário deste projeto?")) return;
      try {
        const r = await jpost("/api/corrigir/aplicar", { token: an.token });
        $("#resAplicar").innerHTML = `<p class="ok-msg">${r.resultado.alterados} itens corrigidos, ${r.resultado.removidos} removidos (fora do trecho).</p>
          <div class="linha-botoes">${linkBaixar({ nome: r.relatorio })}${r.original_corrigido ? linkBaixar({ nome: r.original_corrigido }) : ""}</div>`;
        $("#btnAplicarCorr").disabled = true; E.geo = null; await carregarResumo(); renderAlertas();
      } catch (e) { erro(e); }
    };
  } catch (e) { box.innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; }
};

// ---------------------------------------------------------------- projeto
async function renderProjeto() {
  if (!E.pid) return;
  const p = E.resumo.projeto, f = $("#formProjeto");
  for (const el of f.elements) if (el.name) el.value = p[el.name] ?? "";
  $("#formTrecho").km_ini.value = p.km_ini ?? ""; $("#formTrecho").km_fim.value = p.km_fim ?? "";
  const h = await api(`/api/projetos/${E.pid}/historico`);
  $("#historico").innerHTML = h.map(x => `<li><b>${esc(x.quando)}</b> · ${esc(x.acao)} ${esc(x.detalhe || "")}</li>`).join("") || "<li>—</li>";
}
const formObj = f => Object.fromEntries([...f.elements].filter(e => e.name).map(e => [e.name, e.type === "checkbox" ? e.checked : e.value]));
$("#formProjeto").onsubmit = async e => {
  e.preventDefault();
  try { const v = formObj(e.target); for (const k in v) if (v[k] === "") v[k] = null;
    await jpost(`/api/projetos/${E.pid}`, v, "PUT"); await carregarProjetos(E.pid); toast("Projeto salvo"); renderProjeto(); } catch (er) { erro(er); }
};
$("#formTrecho").onsubmit = async e => {
  e.preventDefault();
  const v = formObj(e.target);
  if (v.recortar && !confirm("Recortar remove os itens fora do novo trecho e corta as feições na divisa. Continuar?")) return;
  try { const r = await jpost(`/api/projetos/${E.pid}/trecho`, v);
    toast(`Trecho alterado. Removidos: ${r.removidos}, cortados: ${r.cortados}`); E.geo = null; await carregarProjetos(E.pid); renderProjeto(); } catch (er) { erro(er); }
};
$("#formAceiro").onsubmit = async e => {
  e.preventDefault();
  try { const r = await jpost(`/api/projetos/${E.pid}/gerar-aceiro`, formObj(e.target));
    toast(`${r.gerados} trechos de aceiro gerados a partir das cercas`); E.geo = null; await carregarResumo(); } catch (er) { erro(er); }
};
$("#btnDuplicar").onclick = async () => { const p = await jpost(`/api/projetos/${E.pid}/duplicar`, {}); await carregarProjetos(p.id); toast("Projeto duplicado"); };
$("#btnExcluirProj").onclick = async () => {
  if (!confirm("Excluir este projeto e todo o seu inventário? Esta ação não pode ser desfeita.")) return;
  await api(`/api/projetos/${E.pid}`, { method: "DELETE" }); E.pid = null; E.geo = null; await carregarProjetos(); irAba("painel");
};

// ---------------------------------------------------------------- importar
const soltar = $("#soltar");
["dragover", "dragenter"].forEach(ev => soltar.addEventListener(ev, e => { e.preventDefault(); soltar.classList.add("sobre"); }));
["dragleave", "drop"].forEach(ev => soltar.addEventListener(ev, e => { e.preventDefault(); soltar.classList.remove("sobre"); }));
soltar.addEventListener("drop", e => { if (e.dataTransfer.files[0]) enviarPrevia(e.dataTransfer.files[0]); });
$("#arqImport").onchange = e => e.target.files[0] && enviarPrevia(e.target.files[0]);

async function enviarPrevia(arq) {
  const box = $("#previa");
  box.innerHTML = `<p class="carregando">Lendo ${esc(arq.name)}… (planilhas grandes podem levar alguns segundos)</p>`;
  const fd = new FormData(); fd.append("arquivo", arq);
  try {
    const r = await api("/api/importar/previa", { method: "POST", body: fd });
    const p = r.projeto, R = E.cat.rotulos;
    const proj = [["rodovia", "Rodovia"], ["trecho", "Trecho"], ["subtrecho", "Subtrecho"], ["segmento", "Segmento"], ["km_ini", "km inicial"],
      ["km_fim", "km final"], ["snv", "SNV"], ["snv_versao", "Versão SNV"], ["data_inventario", "Data do inventário"], ["unidade_local", "Unidade local"], ["data_base", "Data-base"]]
      .filter(([k]) => p[k] != null).map(([k, l]) => `<tr><td>${l}</td><td><b>${esc(nf(p[k], 3))}</b></td></tr>`).join("");
    const rel = r.relatorio.map(x => `<details ${x.avisos.length ? "open" : ""}><summary><b>${esc(x.aba)}</b> → ${esc(x.nome_categoria)} ·
        ${x.linhas} itens ${x.avisos.map(a => `<span class="tag aviso">${esc(a)}</span>`).join(" ")}</summary>
        <div class="mapcols">${Object.entries(x.colunas).map(([k, v]) => `<span><b>${esc(R[k] || k)}</b> ← ${esc(v.join(", "))}</span>`).join("")}</div>
        ${x.nao_mapeadas.length ? `<p class="nota">Colunas não reconhecidas (guardadas como atributos extras): ${esc(x.nao_mapeadas.join(" · "))}</p>` : ""}</details>`).join("");
    const cats = Object.entries(r.por_categoria).map(([k, n]) => `<label class="check"><input type="checkbox" name="cat" value="${k}" checked> ${esc(E.cat.categorias[k].nome)} (${n})</label>`).join("");
    box.innerHTML = `<h3 style="margin-top:16px">Prévia — ${esc(r.arquivo)}: ${r.total} itens</h3>
      <div class="grade2"><div><h4>Dados do trecho encontrados</h4><table class="tab">${proj}</table></div>
      <form id="formConfirmar"><h4>Gravar como</h4>
        <label class="check"><input type="radio" name="modo" value="novo" checked> Novo projeto</label>
        <label class="check"><input type="radio" name="modo" value="substituir" ${E.pid ? "" : "disabled"}> Substituir estas categorias no projeto atual</label>
        <label class="check"><input type="radio" name="modo" value="acrescentar" ${E.pid ? "" : "disabled"}> Acrescentar ao projeto atual</label>
        <label style="display:flex;flex-direction:column;gap:3px;margin:8px 0;font-size:12px">Nome do projeto
          <input name="nome" value="${esc([p.rodovia, p.segmento].filter(Boolean).join(" "))}"></label>
        <h4>Categorias</h4><div class="chips" style="flex-direction:column;gap:2px">${cats}</div>
        <div class="linha-botoes"><button class="btn primario">Confirmar importação</button></div></form></div>
      <h4>Nomenclatura × Álbum DNIT (IPR-736) — log de padronização</h4>
      ${r.padronizacao.length ? `<div class="tabela-rolagem" style="max-height:300px"><table class="tab"><tr><th>Situação</th><th>Cat.</th><th>Original</th><th>Padrão</th><th class=n>Qtde</th><th>Regra</th></tr>` +
        r.padronizacao.map(x => `<tr class="${x.situacao.startsWith("fora") ? "sit-verificar" : x.situacao.includes("conferir") ? "sit-conferir" : "sit-corrigido"}"><td>${esc(x.situacao)}</td><td>${esc(x.categoria)}</td>
          <td>${esc(x.de ?? "")}</td><td><b>${esc(x.para ?? "—")}</b></td><td class=n>${x.quantidade}</td><td>${esc(x.regra)}<br><small>${esc(x.origens.join(", "))}</small></td></tr>`).join("") + "</table></div>"
        : `<p class="nota">Nomenclatura dos dispositivos de drenagem já está no padrão do álbum.</p>`}
      ${r.vocabulario.length ? `<p class="nota">Vocabulário normalizado: ${r.vocabulario.slice(0, 12).map(v => `${esc(v.campo)} “${esc(v.de)}” → “${esc(v.para)}” (${v.quantidade})`).join(" · ")}</p>` : ""}
      <h4>Como cada aba foi lida</h4><div class="relatorio">${rel}</div>
      ${r.ignoradas.length ? `<p class="nota">Abas ignoradas: ${esc(r.ignoradas.slice(0, 40).join(", "))}${r.ignoradas.length > 40 ? "…" : ""}</p>` : ""}`;
    $("#formConfirmar").onsubmit = async e => {
      e.preventDefault();
      const f = e.target, modo = f.modo.value;
      const categorias = $$("input[name=cat]:checked", f).map(c => c.value);
      const res = await jpost("/api/importar/confirmar", { token: r.token, modo, nome: f.nome.value, projeto_id: modo === "novo" ? null : E.pid, categorias });
      box.innerHTML = `<p class="ok-msg">${res.importados} itens importados em “${esc(res.projeto.nome)}”.</p>`;
      E.geo = null; await carregarProjetos(res.projeto.id); irAba("painel");
    };
  } catch (e) { box.innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; }
}

// ---------------------------------------------------------------- exportar
function linkBaixar(r) { return `<a class="btn primario" href="/api/downloads/${encodeURIComponent(r.nome)}">Baixar ${esc(r.nome)}</a>`; }
$("#btnExpPato").onclick = async () => {
  const box = $("#resExpPato"); box.innerHTML = `<p class="carregando">Gerando planilha…</p>`;
  const fd = new FormData();
  if ($("#arqModelo").files[0]) fd.append("modelo", $("#arqModelo").files[0]);
  fd.append("limpar_ausentes", $("#chkLimpar").checked);
  try {
    const r = await api(`/api/projetos/${E.pid}/exportar/pato`, { method: "POST", body: fd });
    box.innerHTML = `<div class="linha-botoes">${linkBaixar(r)}<button class="btn" id="btnConferir">Conferir totais (LibreOffice)</button></div>
      <div class="log">${r.log.map(l => `<div>${esc(l)}</div>`).join("")}</div><div id="totais"></div>`;
    $("#btnConferir").onclick = async () => {
      $("#totais").innerHTML = `<p class="carregando">Recalculando a planilha (pode levar ~1 min)…</p>`;
      try {
        const t = await jpost("/api/conferir", { nome: r.nome });
        $("#totais").innerHTML = `<table class="tab" style="margin-top:10px"><tr><th>Item</th><th>Família</th><th class=n>Sem desoneração (R$)</th><th class=n>Com desoneração (R$)</th></tr>` +
          t.linhas.map(x => `<tr><td>${esc(x.item ?? "")}</td><td>${esc(x.familia ?? "")}</td><td class=n>${nf(x.sem_deson)}</td><td class=n>${nf(x.com_deson)}</td></tr>`).join("") + "</table>";
      } catch (e) { $("#totais").innerHTML = `<p class="tag aviso">${esc(e.message)}</p>`; }
    };
  } catch (e) { box.innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; }
};
$("#btnDefModelo").onclick = async () => {
  const a = $("#arqModelo").files[0];
  if (!a) return toast("Escolha primeiro o arquivo do modelo");
  const fd = new FormData(); fd.append("arquivo", a);
  try { await api("/api/modelo", { method: "POST", body: fd }); toast("Modelo padrão atualizado"); $("#nomeModelo").textContent = a.name; } catch (e) { erro(e); }
};
$$("[data-exp]").forEach(b => b.onclick = async () => {
  const box = $("#resExpInv"); box.innerHTML = `<p class="carregando">Gerando…</p>`;
  try { const r = await api(`/api/projetos/${E.pid}/exportar/${b.dataset.exp}`, { method: "POST" }); box.innerHTML = `<div class="linha-botoes">${linkBaixar(r)}</div>`; }
  catch (e) { box.innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; }
});

// ---------------------------------------------------------------- diálogo
function dialogo(titulo, campos, aoConfirmar) {
  const d = $("#dlg"), f = $("#dlgForm");
  f.innerHTML = `<h3>${esc(titulo)}</h3><div class="form"><div class="campos">${campos.map(([n, r, t]) =>
    `<label>${esc(r)}<input name="${n}" type="${t || "text"}" ${t === "number" ? 'step="any"' : ""}></label>`).join("")}</div></div>
    <div class="linha-botoes"><button class="btn primario" value="ok">Salvar</button><button class="btn" value="cancelar" formnovalidate>Cancelar</button></div>`;
  f.className = "form";
  d.showModal();
  d.onclose = async () => { if (d.returnValue === "ok") { try { await aoConfirmar(formObj(f)); } catch (e) { erro(e); } } };
}

// ---------------------------------------------------------------- início
(async () => {
  try {
    E.cat = await api("/api/catalogo");
    $("#nomeModelo").textContent = E.cat.modelo;
    await carregarProjetos();
    let aba = "painel"; try { aba = localStorage.getItem("pato.aba") || "painel"; } catch (_) {}
    irAba(E.pid ? aba : "painel");
  } catch (e) { erro(e); }
})();
