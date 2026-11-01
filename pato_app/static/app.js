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
  if (nome === "revisao") carregarSugestoes();
  if (nome === "ajustes") carregarAjustes();
  if (nome === "custos") carregarCustos();
  if (nome === "transporte") carregarTransp();
  if (nome === "orcamento") carregarOrc();
  if (nome === "normas") carregarNormas();
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
  const mudou = pid !== E.pid;
  E.pid = pid;
  if (mudou && typeof limparEstadoProjeto === "function") limparEstadoProjeto();
  try { if (pid) localStorage.setItem("pato.pid", pid); } catch (_) {}
  mostrarSalvo();
  if (pid) sel.value = pid;
  $("#vazio").classList.toggle("oculto", !!pid);
  $("#painelConteudo").classList.toggle("oculto", !pid);
  if (pid) await carregarResumo();
}
// estado de tela de um projeto não pode passar para outro (ex.: lista importada, conferência, caches)
function limparEstadoProjeto() {
  Object.assign(C_, { cfg: null, comp: null, tfOpcoes: null });
  Object.assign(B_, { dados: null });
  Object.assign(T_, { cro: null, q: null });
  Object.assign(O_, { c: null, med: null, lista: null, confQtd: null });
  CF_.r = IP_.d = SZ_.r = DV_.r = null;
  R_.resumo = null;
  ["#fichaListaRes", "#resOrc", "#resBin", "#crqKmzRes"].forEach(q => { const el = $(q); if (el) el.innerHTML = ""; });
  ["#painelCotOcr", "#painelForn", "#editorBin"].forEach(q => { const el = $(q); if (el) el.hidden = true; });
  mostrarSalvo();
}
async function mostrarSalvo() {
  const el = $("#salvoEm"); if (!el || !E.pid) return;
  try { const v = await api(`/api/projetos/${E.pid}/versoes`);
    el.textContent = v.length ? `última versão salva: ${new Date(v[0].salvo_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "short" })}` : "nenhuma versão salva";
  } catch (_) { el.textContent = ""; }
}
async function salvarProjeto(rotulo) {
  if (!E.pid) return;
  try { const r = await jpost(`/api/projetos/${E.pid}/salvar`, { rotulo: rotulo || null });
    toast(`Projeto salvo (${new Date(r.salvo_em).toLocaleTimeString("pt-BR", { timeStyle: "short" })})`); mostrarSalvo(); } catch (e) { erro(e); }
}
$("#btnSalvar").onclick = () => salvarProjeto(null);
document.addEventListener("keydown", e => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "s") { e.preventDefault(); salvarProjeto(null); } });
$("#btnProjArq").onclick = async () => {
  if (!E.pid) return;
  const d = $("#dlg"), f = $("#dlgForm"), p = E.projetos.find(x => x.id === E.pid) || {};
  const v = await api(`/api/projetos/${E.pid}/versoes`);
  f.className = "form";
  f.innerHTML = `<h3>Projeto: ${esc(p.nome || "")}</h3>
    <p class="nota">Cada projeto é independente: trocar de projeto no seletor não altera os outros. Tudo o que você faz já fica gravado;
      <b>Salvar</b> guarda uma versão completa (ponto de restauração) para voltar a ela quando quiser.</p>
    <div class="linha-botoes">
      <button class="btn primario" type="button" id="pvSalvar" data-dica="Salva uma versão com um nome (ex.: 'antes de trocar a data-base')">Salvar versão com nome…</button>
      <button class="btn" type="button" id="pvCopia" data-dica="Cria um projeto novo, independente, com tudo deste">Salvar como cópia…</button>
      <a class="btn" href="/api/projetos/${E.pid}/arquivo" data-dica="Baixa o projeto completo num arquivo .pato (levar para outro computador, backup)">Baixar arquivo do projeto (.pato)</a>
      <button class="btn" type="button" id="pvAbrir" data-dica="Abre um arquivo .pato como um projeto novo (não altera os existentes)">Abrir projeto de arquivo…</button></div>
    <h4>Versões salvas</h4>
    ${v.length ? `<div class="tabela-rolagem" style="max-height:320px"><table class="tab"><tr><th>Salvo em</th><th>Nome</th><th class=n>Tamanho</th><th></th></tr>
      ${v.map(x => `<tr><td>${new Date(x.salvo_em).toLocaleString("pt-BR", { dateStyle: "short", timeStyle: "medium" })}</td><td>${esc(x.rotulo || "")}</td><td class=n>${(x.tamanho / 1024).toLocaleString("pt-BR", { maximumFractionDigits: 0 })} kB</td>
        <td><button class="btn mini" type="button" data-restaura="${esc(x.arquivo)}" data-dica="Volta o projeto para esta versão (o estado atual é salvo antes, como 'antes de restaurar')">Voltar para esta</button>
          <a class="btn mini" href="/api/projetos/${E.pid}/versoes/${encodeURIComponent(x.arquivo)}">baixar</a></td></tr>`).join("")}</table></div>`
      : '<p class="nota">Nenhuma versão salva ainda — use 💾 Salvar.</p>'}
    <div class="linha-botoes"><button class="btn" value="cancelar">Fechar</button></div>`;
  d.showModal();
  $("#pvSalvar").onclick = async () => { const r = prompt("Nome da versão:", ""); if (r === null) return; d.close(); await salvarProjeto(r); };
  $("#pvCopia").onclick = async () => { const n = prompt("Nome do novo projeto:", `${p.nome || "Projeto"} (cópia)`); if (!n) return;
    try { const np = await jpost(`/api/projetos/${E.pid}/duplicar`, { nome: n }); d.close(); limparEstadoProjeto(); await carregarProjetos(np.id); toast("Cópia criada — você está agora na cópia"); irAba($("#abas button.ativa").dataset.aba); } catch (e) { erro(e); } };
  $("#pvAbrir").onclick = async () => { const a = await escolherArquivo(".pato,.zip"); if (!a) return; const fd = new FormData(); fd.append("arquivo", a);
    try { const np = await api("/api/projetos/abrir", { method: "POST", body: fd }); d.close(); limparEstadoProjeto(); await carregarProjetos(np.id); toast(`Projeto aberto: ${np.nome}`); irAba("painel"); } catch (e) { erro(e); } };
  $$("[data-restaura]", f).forEach(b => b.onclick = async () => {
    if (!confirm("Voltar o projeto para esta versão? O estado atual será salvo antes (versão 'antes de restaurar').")) return;
    try { await jpost(`/api/projetos/${E.pid}/versoes/restaurar`, { arquivo: b.dataset.restaura }); d.close(); limparEstadoProjeto(); await carregarProjetos(E.pid);
      toast("Projeto restaurado"); irAba($("#abas button.ativa").dataset.aba); } catch (e) { erro(e); }
  });
};
$("#selProjeto").onchange = async e => {
  E.pid = +e.target.value; E.geo = null; E.pagina = 0;
  limparEstadoProjeto();
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
  $("#nSug").textContent = R.sugestoes_pendentes || "";
  $("#nAj").textContent = R.ajustes_aplicados || "";
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
      <td><button class="btn" data-mapa="${it.id}" data-dica="Mostra o item no mapa">⌖</button></td>`;
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
    <button class="btn" data-dica="Clique depois no mapa para gravar a coordenada" onclick="iniciarPosicionar(${p.id}, 'ini')">Definir coordenada ${p.km_fim != null ? "inicial" : ""} no mapa</button>
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
function renderAlertas() {
  if (!E.resumo) return;
  const A = E.resumo.alertas, n = E.resumo.n_alertas;
  $("#chipsAlerta").innerHTML = [["erro", "Erros"], ["aviso", "Avisos"], ["info", "Informações"]].map(([k, r]) =>
    `<span class="chip ${E.alertaNivel === k ? "ativo" : ""}" data-n="${k}">${r} <span class="q">${n[k] || 0}</span></span>`).join("");
  $$("#chipsAlerta .chip").forEach(c => c.onclick = () => { E.alertaNivel = c.dataset.n; renderAlertas(); });
  const lst = A.filter(a => a.nivel === E.alertaNivel).slice(0, 1000);
  $("#tabAlertas").innerHTML = "<tr><th>Nível</th><th>Categoria</th><th>Mensagem</th><th></th></tr>" + lst.map(a =>
    `<tr><td><span class="tag ${a.nivel}">${a.nivel}</span></td><td>${esc(E.cat.categorias[a.categoria].nome)}</td><td>${esc(a.mensagem)}</td>
     <td><button class="btn" data-mapa="${a.id}" data-dica="Abre o mapa centralizado neste item">Ver no mapa</button></td></tr>`).join("");
  $$("#tabAlertas [data-mapa]").forEach(b => b.onclick = () => verNoMapa(+b.dataset.mapa));
}

// ---------------------------------------------------------------- revisão e ajustes
const SIT_CLS = { "corrigido": "sit-corrigido", "corrigido — conferir": "sit-conferir", "recortado": "sit-recortado",
  "removido": "sit-removido", "verificar em campo": "sit-verificar", "padronizado": "sit-corrigido",
  "padronizado — conferir": "sit-conferir", "fora do padrão — verificar": "sit-verificar" };
const R_ = { rev: { status: "pendente", tipo: null, lista: [] }, aj: { modo: "todos", tipo: null, lista: [] }, resumo: null, abertos: new Set() };
const fmtV = v => v === null || v === undefined || v === "" ? "—" : typeof v === "object" ? (v._excluir ? "retirar do inventário" : JSON.stringify(v)) : String(v);
const TIPOS_SUG = [[null, "Todas"], ["correção", "Coordenadas / trecho / SNV"], ["padronização", "Nomenclatura (álbum DNIT)"], ["SNV", "Cadastro SNV"]];

async function carregarSugestoes() {
  if (!E.pid) return;
  const q = new URLSearchParams({ status: R_.rev.status }); if (R_.rev.tipo) q.set("tipo", R_.rev.tipo);
  const r = await api(`/api/projetos/${E.pid}/sugestoes?${q}`);
  R_.rev.lista = r.sugestoes; R_.resumo = r.resumo;
  atualizarContadores(); renderSnv(r.resumo.snv);
  montarLista("rev");
}
async function carregarAjustes() {
  if (!E.pid) return;
  const q = new URLSearchParams({ status: "aplicada" }); if (R_.aj.tipo) q.set("tipo", R_.aj.tipo);
  const r = await api(`/api/projetos/${E.pid}/sugestoes?${q}`);
  R_.resumo = r.resumo;
  R_.aj.lista = r.sugestoes.filter(s => R_.aj.modo === "todos" || (R_.aj.modo === "auto" ? s.automatica : !s.automatica));
  atualizarContadores(); montarLista("aj");
}
function atualizarContadores() {
  const R = R_.resumo; if (!R) return;
  $("#nSug").textContent = R.pendentes || "";
  $("#nAj").textContent = (R.automaticas + R.manuais) || "";
  const disp = R.contagem.filter(c => c.status === "dispensada").reduce((a, c) => a + c.n, 0);
  $("#chipsStatus").innerHTML = [["pendente", "Pendentes", R.pendentes, "Correções que precisam da sua decisão"], ["dispensada", "Dispensadas", disp, "Sugestões que você decidiu não aplicar"]].map(([k, r, n, d]) =>
    `<span class="chip ${R_.rev.status === k ? "ativo" : ""}" data-st="${k}" data-dica="${d}">${r} <span class="q">${n || 0}</span></span>`).join("");
  $$("#chipsStatus .chip").forEach(c => c.onclick = () => { R_.rev.status = c.dataset.st; carregarSugestoes(); });
  for (const [alvo, est, fn] of [["#chipsTipoSug", R_.rev, carregarSugestoes], ["#chipsTipoAj", R_.aj, carregarAjustes]]) {
    $(alvo).innerHTML = TIPOS_SUG.map(([k, r]) => `<span class="chip ${est.tipo === k ? "ativo" : ""}" data-tp="${k ?? ""}" data-dica="Filtrar por tipo de verificação">${r}</span>`).join("");
    $$(`${alvo} .chip`).forEach(c => c.onclick = () => { est.tipo = c.dataset.tp || null; fn(); });
  }
  $("#chipsModoAj").innerHTML = [["todos", "Todos", R.automaticas + R.manuais, "Todos os ajustes aplicados"], ["auto", "Automáticos", R.automaticas, "Corrigidos pelo sistema por serem certos (regra do km informado, digitação, grafia do álbum)"],
    ["manual", "Por você", R.manuais, "Aplicados por você na aba Revisão"]].map(([k, r, n, d]) =>
    `<span class="chip ${R_.aj.modo === k ? "ativo" : ""}" data-md="${k}" data-dica="${d}">${r} <span class="q">${n || 0}</span></span>`).join("");
  $$("#chipsModoAj .chip").forEach(c => c.onclick = () => { R_.aj.modo = c.dataset.md; carregarAjustes(); });
  $("#btnLoteSug").style.display = R_.rev.status === "pendente" ? "" : "none";
}
function renderSnv(S) {
  if (!S) { $("#infoSnv").innerHTML = ""; return; }
  const tab = t => `<table class="tab"><tr><th>Código</th><th class=n>km inicial</th><th class=n>km final</th></tr>` +
    t.map(x => `<tr><td>${esc(x.codigo)}</td><td class=n>${nf(x.km_ini, 3)}</td><td class=n>${nf(x.km_fim, 3)}</td></tr>`).join("") + "</table>";
  $("#infoSnv").innerHTML = `<details style="margin-top:8px"><summary><b>SNV</b> — versão declarada ${esc(S.versao_inventario || "—")} ·
      referência: ${esc(S.fonte_referencia)} · ${Math.round(S.concordancia * 100)}% dos itens coerentes com o cadastro de segmentos</summary>
    ${S.observacoes.map(o => `<p class="nota">• ${esc(o)}</p>`).join("")}
    <div class="grade2"><div><h4>Cadastro de segmentos do inventário</h4>${tab(S.cadastro_segmentos)}</div><div><h4>Referência</h4>${tab(S.tabela_referencia)}</div></div></details>`;
}
function agrupar(lista) {
  const g = new Map();
  for (const s of lista) {
    const k = [s.tipo, s.situacao, s.categoria, s.tipo === "padronização" ? s.motivo + JSON.stringify(s.atual) : s.motivo.replace(/[\d.,]+/g, "#"),
      JSON.stringify(s.status === "aplicada" ? s.aplicado : s.mudancas), s.automatica ? 1 : 0].join("|");
    if (!g.has(k)) g.set(k, []);
    g.get(k).push(s);
  }
  return [...g.entries()].sort((a, b) => b[1].length - a[1].length);
}
function resumoMud(s) {
  const m = s.status === "aplicada" ? s.aplicado : s.mudancas;
  if (!m || !Object.keys(m).length) return null;
  if (m._excluir) return "retirado do inventário (fora do trecho)";
  if (m._segmentos) return "cadastro de segmentos substituído pelo SNV oficial";
  return Object.entries(m).filter(([c]) => !c.startsWith("_")).map(([c, v]) => `${esc(E.cat.rotulos[c] || c)}: ${esc(fmtV(s.atual?.[c]))} → <b>${esc(fmtV(v))}</b>`).join(" · ");
}
function montarLista(modo) {
  const est = modo === "rev" ? R_.rev : R_.aj, cont = $(modo === "rev" ? "#listaSug" : "#listaAj"), info = $(modo === "rev" ? "#infoSug" : "#infoAj");
  const G = agrupar(est.lista), pend = modo === "rev" && est.status === "pendente";
  info.textContent = modo === "rev"
    ? `${est.lista.length} ${est.status === "pendente" ? "decisões pendentes" : "sugestões dispensadas"} em ${G.length} grupos.`
    : `${est.lista.length} ajustes em ${G.length} grupos.`;
  cont.innerHTML = G.map(([k, lst], gi) => {
    const s0 = lst[0], aberto = R_.abertos.has(modo + k) || lst.length === 1;
    const mud = resumoMud(s0);
    const alt = !mud && s0.opcoes?.length ? `${s0.opcoes.length} alternativa(s)` : (!mud ? "sem correção possível — informe o valor no item ou dispense" : "");
    let acoes = "";
    if (pend) acoes = (mud ? `<button class="btn primario" data-gap="${gi}" data-dica="Aplica a correção sugerida ${lst.length > 1 ? "a todos os itens do grupo" : "a este item"}">Aplicar sugestão${lst.length > 1 ? ` (${lst.length})` : ""}</button>` : "")
      + `<button class="btn" data-gdis="${gi}" data-dica="Não aplica; a sugestão não volta em novas análises (pode ser reaberta em Dispensadas)">Dispensar${lst.length > 1 ? " grupo" : ""}</button>`;
    else if (modo === "rev") acoes = `<button class="btn" data-gdesf="${gi}" data-dica="Volta as sugestões para Pendentes">Reabrir${lst.length > 1 ? " grupo" : ""}</button>`;
    else acoes = `<button class="btn" data-gdesf="${gi}" data-dica="Restaura os valores anteriores e devolve a sugestão para a Revisão">Desfazer${lst.length > 1 ? ` (${lst.length})` : ""}</button>`;
    return `<div class="grupo-sug ${aberto ? "aberto" : ""}">
      <div class="cab"><div><span class="tag ${SIT_CLS[s0.situacao] || ""}">${esc(s0.situacao)}</span><br><small>${esc(s0.tipo)}${s0.confianca && s0.confianca !== "—" ? " · confiança " + esc(s0.confianca) : ""}${modo === "aj" ? (s0.automatica ? " · automático" : " · por você") : ""}</small></div>
        <div><b>${esc(E.cat.categorias[s0.categoria]?.nome || s0.categoria)}</b><br><small>${lst.length} item(ns)</small></div>
        <div style="cursor:pointer" data-abre="${gi}" data-dica="Clique para ver e ajustar item a item">${esc(lst.length > 1 ? s0.motivo.replace(/km ≈[\d.,]+/g, "km ≈…") : s0.motivo)}<div class="mud">${mud || alt}</div></div>
        <div class="linha-botoes" style="margin:0">${acoes}</div></div>
      <div class="itens">${aberto ? lst.slice(0, 300).map(s => itemSug(s, modo)).join("") + (lst.length > 300 ? `<p class="nota">… e mais ${lst.length - 300}</p>` : "") : ""}</div></div>`;
  }).join("") || `<p class="nota">${modo === "rev" ? (est.status === "pendente" ? "Nenhuma decisão pendente. 🎉" : "Nenhuma sugestão dispensada.") : "Nenhum ajuste aplicado."}</p>`;
  $$("[data-abre]", cont).forEach(el => el.onclick = () => { const k = modo + G[+el.dataset.abre][0]; R_.abertos.has(k) ? R_.abertos.delete(k) : R_.abertos.add(k); montarLista(modo); });
  const recarregar = async () => { E.geo = null; await carregarResumo(); modo === "rev" ? carregarSugestoes() : carregarAjustes(); };
  $$("[data-gap]", cont).forEach(b => b.onclick = async () => {
    const lst = G[+b.dataset.gap][1];
    if (lst.length > 1 && !confirm(`Aplicar a correção sugerida a ${lst.length} itens?`)) return;
    const r = await jpost(`/api/projetos/${E.pid}/sugestoes/aplicar-lote`, { ids: lst.map(s => s.id) });
    toast(`${r.aplicadas} aplicada(s) — veja na aba Ajustes`); recarregar();
  });
  $$("[data-gdis]", cont).forEach(b => b.onclick = async () => {
    const lst = G[+b.dataset.gdis][1];
    for (const s of lst) await jpost(`/api/sugestoes/${s.id}/dispensar`, {});
    toast(`${lst.length} dispensada(s)`); recarregar();
  });
  $$("[data-gdesf]", cont).forEach(b => b.onclick = async () => {
    const lst = G[+b.dataset.gdesf][1];
    if (lst.length > 1 && !confirm(`Desfazer ${lst.length} ajustes?`)) return;
    for (const s of lst) { try { await jpost(`/api/sugestoes/${s.id}/desfazer`, {}); } catch (e) { /* segue */ } }
    toast(`${lst.length} desfeito(s) — voltaram para a Revisão`); recarregar();
  });
  $$(".item-sug", cont).forEach(el => ligarItemSug(el, modo, recarregar));
}
function itemSug(s, modo) {
  const campos = Object.keys({ ...(s.atual || {}), ...(s.mudancas || {}), ...(s.aplicado || {}) }).filter(c => !c.startsWith("_"));
  const pend = s.status === "pendente";
  const opc = (s.opcoes || []).map((o, i) => `<option value="${i}">${esc(o.rotulo)}</option>`).join("");
  const exclui = (pend ? s.mudancas : s.aplicado)?._excluir;
  return `<div class="item-sug" data-id="${s.id}">
    <div><b>${esc(s.origem || "—")}</b><br><small>km ${nf(s.km_ini, 3)}${s.km_fim != null ? "–" + nf(s.km_fim, 3) : ""}</small>
      <br><small>${esc(s.motivo)}</small></div>
    <div class="campos-sug">${exclui ? `<span class="tag sit-removido">retirar do inventário (fora do trecho)</span>` : ""}
      ${campos.map(c => {
        const v = pend ? s.mudancas?.[c] : s.aplicado?.[c];
        return `<label>${esc(E.cat.rotulos[c] || c)}<span class="de">${esc(fmtV(s.atual?.[c]))}</span>
          <input data-campo="${c}" value="${esc(v ?? "")}" ${pend ? "" : "disabled"} placeholder="${pend ? "novo valor" : ""}" ${pend ? 'data-dica="Valor sugerido — pode editar antes de aplicar"' : ""}></label>`;
      }).join("")}
      ${pend && opc ? `<label>Alternativas<select data-opc data-dica="Outras opções do álbum / da análise; a primeira é a sugerida"><option value="">— trocar a sugestão —</option>${opc}</select></label>` : ""}</div>
    <div class="linha-botoes" style="margin:0">
      ${pend ? `<button class="btn primario" data-ap data-dica="Grava no inventário o valor mostrado nos campos">Aplicar</button><button class="btn" data-dis data-dica="Não aplica esta sugestão">Dispensar</button>`
             : `<button class="btn" data-desf data-dica="${s.status === "aplicada" ? "Restaura os valores anteriores" : "Volta para Pendentes"}">${s.status === "aplicada" ? "Desfazer" : "Reabrir"}</button>`}
      ${s.item_id ? `<button class="btn" data-mapa="${s.item_id}" data-dica="Mostra o item no mapa">Mapa</button>` : ""}</div></div>`;
}
function ligarItemSug(el, modo, recarregar) {
  const id = +el.dataset.id, lista = modo === "rev" ? R_.rev.lista : R_.aj.lista, s = lista.find(x => x.id === id);
  const sel = $("[data-opc]", el);
  if (sel) sel.onchange = () => {
    if (sel.value === "") return;
    const m = s.opcoes[+sel.value].mudancas;
    $$("input[data-campo]", el).forEach(i => { if (i.dataset.campo in m) i.value = m[i.dataset.campo]; });
  };
  const ap = $("[data-ap]", el);
  if (ap) ap.onclick = async () => {
    let mudancas = {};
    if ((sel && sel.value !== "" && s.opcoes[+sel.value].mudancas._excluir) || s.mudancas?._excluir) mudancas = { _excluir: true };
    else $$("input[data-campo]", el).forEach(i => { if (i.value !== "" && String(i.value) !== String(s.atual?.[i.dataset.campo] ?? "")) mudancas[i.dataset.campo] = i.value; });
    if (!Object.keys(mudancas).length) return toast("Informe o novo valor ou escolha uma alternativa.");
    try { await jpost(`/api/sugestoes/${id}/aplicar`, { mudancas }); toast("Aplicada — registrada em Ajustes"); recarregar(); } catch (e) { erro(e); }
  };
  const dis = $("[data-dis]", el);
  if (dis) dis.onclick = async () => { await jpost(`/api/sugestoes/${id}/dispensar`, {}); recarregar(); };
  const desf = $("[data-desf]", el);
  if (desf) desf.onclick = async () => { try { await jpost(`/api/sugestoes/${id}/desfazer`, {}); toast("Desfeito"); recarregar(); } catch (e) { erro(e); } };
  const mp = $("[data-mapa]", el);
  if (mp) mp.onclick = () => verNoMapa(+mp.dataset.mapa);
}
$("#btnAnalisar").onclick = async () => {
  const fd = new FormData();
  if ($("#arqSnv").files[0]) fd.append("snv", $("#arqSnv").files[0]);
  if ($("#verSnv").value) fd.append("versao", $("#verSnv").value);
  fd.append("tolerancia", $("#tolKm").value || "1");
  $("#infoSug").textContent = "Analisando…";
  try {
    const r = await api(`/api/projetos/${E.pid}/sugestoes/analisar`, { method: "POST", body: fd });
    R_.rev.status = "pendente"; toast(`${r.aplicadas_automaticamente} ajustes automáticos · ${r.pendentes} decisões pendentes`);
    E.geo = null; await carregarResumo(); carregarSugestoes();
  } catch (e) { erro(e); }
};
$("#btnLoteSug").onclick = async () => {
  const n = R_.rev.lista.filter(s => s.mudancas && Object.keys(s.mudancas).length).length;
  if (!n) return toast("Nenhuma sugestão com correção definida.");
  if (!confirm(`Aplicar as ${n} sugestões mostradas que têm correção definida?`)) return;
  const r = await jpost(`/api/projetos/${E.pid}/sugestoes/aplicar-lote`, { ids: R_.rev.lista.map(s => s.id) });
  toast(`${r.aplicadas} aplicada(s) — veja na aba Ajustes`); E.geo = null; await carregarResumo(); carregarSugestoes();
};

// ---------------------------------------------------------------- balões de ajuda
(() => {
  const b = document.createElement("div"); b.className = "balao"; document.body.appendChild(b);
  let alvo = null;
  document.addEventListener("mouseover", e => {
    const el = e.target.closest("[data-dica]");
    if (el === alvo) return;
    alvo = el;
    if (!el) { b.classList.remove("ver"); return; }
    b.textContent = el.dataset.dica;
    const r = el.getBoundingClientRect();
    b.classList.add("ver");
    const w = b.offsetWidth, h = b.offsetHeight;
    let x = Math.min(Math.max(8, r.left + r.width / 2 - w / 2), innerWidth - w - 8);
    let y = r.top - h - 8; if (y < 8) y = r.bottom + 8;
    b.style.left = x + "px"; b.style.top = y + "px";
  });
  document.addEventListener("scroll", () => { b.classList.remove("ver"); alvo = null; }, true);
})();

// ---------------------------------------------------------------- custos
const C_ = { sub: "servicos", cfg: null, comp: null, regimeComp: null, tipoIns: null, tfOpcoes: null };
const REG = { SD: "sem desoneração", CD: "com desoneração" };
const pct = v => v == null ? "—" : (v * 100).toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + "%";
const reais = v => v == null ? "—" : v.toLocaleString("pt-BR", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const base_ = `/api/projetos/`;
async function carregarCustos() {
  if (!E.pid) return;
  $("#cabCustos").innerHTML = `<p class="carregando">Carregando a base SICRO… (na primeira vez a base de exemplo é importada, leva alguns segundos)</p>`;
  try { C_.cfg = await api(`${base_}${E.pid}/custos/config`); } catch (e) { $("#cabCustos").innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; return; }
  const c = C_.cfg;
  C_.regimeComp = C_.regimeComp || c.regime;
  $("#cabCustos").innerHTML = `<div class="it">Base SICRO<br><b>${esc(c.uf || "—")} · ${esc(c.data_base || "—")}</b></div>
    <div class="it">Regime do orçamento<br><b>${esc(REG[c.regime])}</b></div>
    <div class="it">BDI sem desoneração<br><b>${pct(c.bdi.SD)}</b></div><div class="it">BDI com desoneração<br><b>${pct(c.bdi.CD)}</b></div>`;
  const subs = [["servicos", "Serviços e composições", "Escolha os serviços e veja/ajuste as composições"], ["proprias", "Composições próprias", "Crie, copie e edite composições próprias (preços novos)"], ["insumos", "Insumos", "Preços dos insumos usados nos serviços escolhidos"],
    ["binomio", "Binômio", "Cotações × SICRO (pétreos, madeira, capa asfáltica) e betuminosos ANP, com anexos"],
    ["alteracoes", "Alterações", "Registro das alterações de custo, com desfazer"], ["base", "Data-base e BDI", "Base SICRO do projeto (estado, data-base), BDI (conferir e ajustar as parcelas) e importação de novas bases"],
    ["database", "Trocar data-base", "Compare e passe o projeto para outra data-base"]];
  $("#chipsCustos").innerHTML = subs.map(([k, r, d]) => `<span class="chip ${C_.sub === k ? "ativo" : ""}" data-sub="${k}" data-dica="${d}">${r}</span>`).join("");
  $$("#chipsCustos .chip").forEach(ch => ch.onclick = () => { C_.sub = ch.dataset.sub; carregarCustos(); });
  $$(".sub-custos").forEach(el => el.classList.toggle("ativa", el.id === "cst-" + C_.sub));
  ({ servicos: renderServicos, proprias: renderProprias, insumos: renderInsumos, alteracoes: renderAltCusto, binomio: renderBinomio, base: renderBaseCfg, database: renderDataBase })[C_.sub]().catch(erro);
}

// ---- base e BDI
async function renderBaseCfg() {
  const c = C_.cfg, f = $("#formCfgCustos");
  f.base.innerHTML = (c.opcoes || []).map(o => `<option value="${o.uf}|${o.data_base}|${o.fonte}">${esc(o.rotulo)} (${Object.keys(o.bases).map(r => REG[r]).join(", ")})</option>`).join("");
  f.base.value = `${c.uf}|${c.data_base}|${c.fonte}`; f.regime.value = c.regime;
  f.bdi_sd.value = (c.bdi.SD * 100).toFixed(2); f.bdi_cd.value = (c.bdi.CD * 100).toFixed(2);
  $("#parcelasBdi").innerHTML = ["SD", "CD"].map(r => `<div><h4>${REG[r]}</h4>${Object.entries(c.rotulos_parcelas).map(([k, rot]) =>
    `<label style="display:flex;justify-content:space-between;gap:8px;font-size:12px;margin:3px 0">${esc(rot)} <input data-reg="${r}" data-par="${k}" type="number" step="0.0001" value="${c.parcelas[r]?.[k] ?? 0}" style="width:90px"></label>`).join("")}</div>`).join("");
  const ex = c.bdi_extras || {};
  $("#bdiSelic").value = ex.selic ?? ""; $("#bdiAno").value = ex.ano ?? ""; linhasIss(ex.municipios || []);
  const bases = await api("/api/custos/bases");
  $("#tabBases").innerHTML = "<tr><th>UF</th><th>Data-base</th><th>Regime</th><th class=n>Composições</th><th class=n>Lista sintética</th><th>Origem</th><th></th></tr>" +
    bases.map(b => `<tr><td>${esc(b.uf)}</td><td>${esc(b.data_base)}</td><td>${esc(REG[b.regime] || b.regime)}</td><td class=n>${b.n_composicoes}</td><td class=n>${b.n_sintetico || 0}</td>
      <td><small>${esc(b.origem || "")}</small></td><td><button class="btn mini perigo" data-exb="${b.id}" data-dica="Remove esta base do sistema">Excluir</button></td></tr>`).join("");
  $$("[data-exb]").forEach(b => b.onclick = async () => { if (!confirm("Excluir esta base?")) return; await api(`/api/custos/bases/${b.dataset.exb}`, { method: "DELETE" }); carregarCustos(); });
}
function linhasIss(lst) {
  $("#tabIss").innerHTML = "<tr><th>Município</th><th>UF</th><th>Alíquota (%)</th><th>Base de cálculo (% PV)</th><th>Peso</th><th></th></tr>" +
    lst.map((m, i) => `<tr data-mun="${i}"><td><input data-k="nome" value="${esc(m.nome || "")}"></td><td><input data-k="uf" value="${esc(m.uf || "")}" style="width:50px"></td>
      <td><input data-k="aliquota" type="number" step="0.01" value="${m.aliquota ?? ""}" style="width:80px"></td><td><input data-k="base" type="number" step="0.01" value="${m.base ?? 100}" style="width:80px"></td>
      <td><input data-k="peso" type="number" step="0.01" value="${m.peso ?? 1}" style="width:80px"></td><td><button class="btn mini perigo" type="button" data-rmun="${i}" data-dica="Remove o município">×</button></td></tr>`).join("");
  $$("[data-rmun]").forEach(b => b.onclick = () => { const l = lerIss(); l.splice(+b.dataset.rmun, 1); linhasIss(l); });
}
const lerIss = () => $$("#tabIss tr[data-mun]").map(tr => Object.fromEntries($$("input", tr).map(i => [i.dataset.k, i.value])));
$("#btnAddMun").onclick = () => { const l = lerIss(); l.push({ base: 100, peso: 1 }); linhasIss(l); };
$("#btnCalcBdi").onclick = async () => {
  const par = { SD: {}, CD: {} };
  $$("#parcelasBdi input").forEach(i => par[i.dataset.reg][i.dataset.par] = +i.value);
  const municipios = lerIss().filter(m => m.nome || m.aliquota);
  const r = await jpost("/api/custos/bdi/calcular", { parcelas: par, municipios, selic: $("#bdiSelic").value || null, ano: $("#bdiAno").value || null });
  $("#formCfgCustos").bdi_sd.value = (r.bdi.SD * 100).toFixed(2); $("#formCfgCustos").bdi_cd.value = (r.bdi.CD * 100).toFixed(2);
  C_.parcelas = { ...r.parcelas, municipios, selic: r.selic, ano: r.ano };
  for (const reg of ["SD", "CD"]) for (const [k, v] of Object.entries(r.parcelas[reg])) { const i = $(`#parcelasBdi [data-reg="${reg}"][data-par="${k}"]`); if (i) i.value = v; }
  $("#notasBdi").innerHTML = r.notas.map(esc).join(" · ") + ` → BDI ${(r.bdi.SD * 100).toFixed(2)}% / ${(r.bdi.CD * 100).toFixed(2)}%`;
  toast("BDI calculado — clique em Salvar para gravar");
};
$("#formCfgCustos").onsubmit = async e => {
  e.preventDefault();
  const f = e.target, [uf, data_base, fonte] = f.base.value.split("|");
  try {
    await jpost(`${base_}${E.pid}/custos/config`, { uf, data_base, fonte, regime: f.regime.value, ...(C_.parcelas ? { parcelas: C_.parcelas } : {}) }, "PUT");
    // o BDI digitado prevalece sobre as parcelas
    await jpost(`${base_}${E.pid}/custos/config`, { bdi_sd: +f.bdi_sd.value, bdi_cd: +f.bdi_cd.value }, "PUT");
    C_.parcelas = null; C_.regimeComp = f.regime.value; toast("Base e BDI salvos"); carregarCustos();
  } catch (er) { erro(er); }
};
$("#formBase").onsubmit = async e => {
  e.preventDefault();
  const f = e.target, fd = new FormData();
  for (const a of f.arquivos.files) fd.append("arquivos", a);
  if (f.uf.value) fd.append("uf", f.uf.value); if (f.data_base.value) fd.append("data_base", f.data_base.value);
  $("#resBase").innerHTML = `<p class="carregando">Lendo os relatórios do SICRO… (arquivos grandes podem levar alguns minutos)</p>`;
  try {
    const r = await api("/api/custos/bases", { method: "POST", body: fd });
    $("#resBase").innerHTML = `<p class="ok-msg">Importado: ${r.map(b => `${b.uf} ${b.data_base} ${REG[b.regime]} (${b.n_composicoes} composições)`).join(" · ")}</p>`;
    f.reset(); renderBaseCfg();
  } catch (er) { $("#resBase").innerHTML = `<p class="tag erro">${esc(er.message)}</p>`; }
};

// ---- serviços e composição
async function renderServicos() {
  const r = await api(`${base_}${E.pid}/custos/servicos`);
  const cel = (s, reg) => {
    const a = s[`preco_${reg}`], o = s[`preco_original_${reg}`];
    if (a == null) return "—";
    return a !== o ? `<span title="original ${reais(o)}">${reais(a)}</span> <small class="${a > o ? "var-pos" : "var-neg"}">(${((a / o - 1) * 100).toFixed(2)}%)</small>` : reais(a);
  };
  $("#tabServicos").innerHTML = `<tr><th>Código</th><th>Serviço</th><th>Unid.</th><th class=n>Quant. anual</th><th class=n>Preço ${REG.SD}</th><th class=n>Preço ${REG.CD}</th><th></th></tr>` +
    (r.servicos.map(s => `<tr><td>${esc(s.codigo)}</td><td>${esc(s.descricao || "")}${s.analitica ? "" : ' <span class="tag" data-dica="A base não tem o relatório analítico desta composição; o preço vem da lista sintética">sem analítico</span>'}</td>
      <td>${esc(s.unidade || "")}</td><td class=n><input type="number" step="any" data-qserv="${esc(s.codigo)}" value="${s.quantidade ?? ""}" style="width:110px"
        data-dica="${s.origem_quantidade ? "Origem: " + esc(s.origem_quantidade) + ". " : ""}Quantidade de trabalho em 12 meses — usada no quadro de transportes"></td><td class=n>${cel(s, "SD")}</td><td class=n>${cel(s, "CD")}</td>
      <td><div class="linha-botoes" style="margin:0">${s.analitica ? `<button class="btn mini" data-vcomp="${esc(s.codigo)}" data-dica="Abre a composição analítica para ver e ajustar">Composição</button>` : ""}
      <button class="btn mini perigo" data-rserv="${esc(s.codigo)}" data-dica="Tira o serviço da lista do projeto">Remover</button></div></td></tr>`).join("")
      || `<tr><td colspan=7 class="nota">Nenhum serviço escolhido. Busque abaixo e clique em Adicionar.</td></tr>`);
  $$("[data-qserv]").forEach(i => i.onchange = async () => { try { await jpost(`${base_}${E.pid}/custos/quantidade`, { codigo: i.dataset.qserv, quantidade: i.value }, "PUT"); toast("Quantidade gravada"); } catch (e) { erro(e); } });
  $$("[data-vcomp]").forEach(b => b.onclick = () => abrirComposicao(b.dataset.vcomp));
  $$("[data-rserv]").forEach(b => b.onclick = async () => { await api(`${base_}${E.pid}/custos/servicos/${encodeURIComponent(b.dataset.rserv)}`, { method: "DELETE" }); renderServicos(); });
  if (C_.comp) abrirComposicao(C_.comp);
}
let _buscaCompH;
$("#buscaComp").oninput = () => { clearTimeout(_buscaCompH); _buscaCompH = setTimeout(buscarComp, 350); };
async function buscarComp() {
  const q = $("#buscaComp").value.trim();
  if (q.length < 2) { $("#tabBusca").innerHTML = ""; return; }
  const r = await api(`${base_}${E.pid}/custos/buscar?q=${encodeURIComponent(q)}`);
  $("#tabBusca").innerHTML = "<tr><th>Código</th><th>Descrição</th><th>Unid.</th><th class=n>Custo direto</th><th></th></tr>" + r.map(x =>
    `<tr><td>${esc(x.codigo)}</td><td>${esc(x.descricao || "")}${x.analitica ? "" : ' <span class="tag">sem analítico</span>'}</td><td>${esc(x.unidade || "")}</td><td class=n>${reais(x.custo_direto)}</td>
     <td>${x.escolhido ? '<span class="tag">escolhido</span>' : `<button class="btn mini primario" data-addserv="${esc(x.codigo)}" data-dica="Inclui o serviço no projeto">Adicionar</button>`}</td></tr>`).join("");
  $$("[data-addserv]").forEach(b => b.onclick = async () => { await jpost(`${base_}${E.pid}/custos/servicos`, { codigo: b.dataset.addserv }); toast("Serviço adicionado"); renderServicos(); buscarComp(); });
}
async function abrirComposicao(cod) {
  C_.comp = cod;
  const reg = C_.regimeComp || C_.cfg.regime;
  let x;
  try { x = await api(`${base_}${E.pid}/custos/composicao/${encodeURIComponent(cod)}?regime=${reg}`); } catch (e) { $("#detComp").innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; return; }
  if (!C_.tfOpcoes) C_.tfOpcoes = await api(`${base_}${E.pid}/custos/tempo-fixo/opcoes`);
  const n4 = v => v == null ? "" : v.toLocaleString("pt-BR", { maximumFractionDigits: 6 });
  const inp = (attrs, v) => `<input type="number" step="any" ${attrs} value="${v ?? ""}">`;
  const tfSel = t => `<select data-tftrocar="${esc(t.insumo)}" data-tfde="${esc(t.composicao)}" data-dica="Troca a composição de tempo fixo (e o veículo do transporte do mesmo insumo)"><option value="">trocar veículo…</option>${C_.tfOpcoes.map(o => `<option value="${esc(o.codigo)}">${esc(o.codigo)} — ${esc((o.veiculo || o.descricao).slice(0, 70))} (R$ ${reais(o.preco)}/t)</option>`).join("")}</select>`;
  $("#detComp").innerHTML = `<div class="cpu">
    <div class="barra" style="justify-content:space-between"><h3 style="margin:0">${esc(x.codigo)} — ${esc(x.descricao)} <small>(${esc(x.unidade)})</small></h3>
      <div class="chips">${["SD", "CD"].map(r => `<span class="chip ${r === reg ? "ativo" : ""}" data-regc="${r}" data-dica="Mostrar a composição ${REG[r]}">${REG[r]}</span>`).join("")}</div></div>
    <p class="nota">SICRO ${esc(x.uf)} ${esc(x.data_base)} · Produção da equipe ${n4(x.producao)} ${esc(x.unidade)}/h · Edite o preço de um insumo e clique em ✓ — vale para todas as composições que usam o insumo.</p>
    <h4>A — Equipamentos</h4><table class="tab"><tr><th>Código</th><th>Descrição</th><th class=n>Quant.</th><th class=n>Util. op.</th><th class=n>Util. improd.</th><th>Custo produtivo</th><th>Custo improdutivo</th><th class=n>Custo horário</th><th></th></tr>
      ${x.equipamentos.map(e => `<tr><td>${esc(e.codigo)}</td><td>${esc(e.descricao)}</td><td class=n>${n4(e.quant)}</td><td class=n>${n4(e.util_op)}</td><td class=n>${n4(e.util_imp)}</td>
        <td>${inp(`data-eqop="${esc(e.codigo)}"`, e.custo_op)}</td><td>${inp(`data-eqimp="${esc(e.codigo)}"`, e.custo_imp)}</td><td class=n>${n4(e.custo)}</td>
        <td><button class="btn mini" data-saveq="${esc(e.codigo)}" data-dica="Grava o novo custo horário do equipamento">✓</button> <button class="btn mini" data-troca="A|${esc(e.codigo)}" data-dica="Troca este equipamento por outro da base">trocar</button></td></tr>`).join("")}
      <tr class="tot"><td colspan=7>Custo horário de equipamentos</td><td class=n>${n4(x.total_equipamentos)}</td><td></td></tr></table>
    <h4>B — Mão de obra</h4><table class="tab"><tr><th>Código</th><th>Descrição</th><th class=n>Quant.</th><th>Custo horário</th><th class=n>Total</th><th></th></tr>
      ${x.mao_obra.map(m => `<tr><td>${esc(m.codigo)}</td><td>${esc(m.descricao)}</td><td class=n>${n4(m.quant)}</td><td>${inp(`data-mo="${esc(m.codigo)}"`, m.custo)}</td><td class=n>${n4(m.total)}</td>
        <td><button class="btn mini" data-savmo="${esc(m.codigo)}" data-dica="Grava o novo custo horário">✓</button> <button class="btn mini" data-troca="B|${esc(m.codigo)}" data-dica="Troca esta categoria de mão de obra">trocar</button></td></tr>`).join("")}
      <tr class="tot"><td colspan=4>Custo horário de mão de obra</td><td class=n>${n4(x.total_mao_obra)}</td><td></td></tr>
      <tr class="tot"><td colspan=4>Custo unitário de execução (÷ produção) · FIC · FIT</td><td class=n>${n4(x.exec_unitario)} · ${n4(x.fic)} · ${n4(x.fit)}</td><td></td></tr></table>
    <h4>C — Materiais</h4><table class="tab"><tr><th>Código</th><th>Descrição</th><th class=n>Quant.</th><th>Unid.</th><th>Preço</th><th class=n>Custo</th><th></th></tr>
      ${x.materiais.map(m => `<tr><td>${esc(m.codigo)}</td><td>${esc(m.descricao)}</td><td class=n>${n4(m.quant)}</td><td>${esc(m.unidade || "")}</td><td>${inp(`data-mat="${esc(m.codigo)}"`, m.preco)}</td><td class=n>${n4(m.total)}</td>
        <td><button class="btn mini" data-savmat="${esc(m.codigo)}" data-dica="Grava o novo preço do material">✓</button> <button class="btn mini" data-troca="C|${esc(m.codigo)}" data-dica="Troca este material por outro da base (ex.: brita 0 → brita 1)">trocar</button></td></tr>`).join("") || '<tr><td colspan=7 class="nota">—</td></tr>'}</table>
    <h4>D — Atividades auxiliares</h4><table class="tab"><tr><th>Código</th><th>Descrição</th><th class=n>Quant.</th><th>Unid.</th><th class=n>Preço</th><th class=n>Custo</th><th></th></tr>
      ${x.auxiliares.map(a => `<tr><td>${esc(a.codigo)}</td><td>${esc(a.descricao)}</td><td class=n>${n4(a.quant)}</td><td>${esc(a.unidade || "")}</td><td class=n>${reais(a.preco)}</td><td class=n>${n4(a.total)}</td>
        <td><button class="btn mini" data-vcomp2="${esc(a.codigo)}" data-dica="Abre a composição auxiliar">abrir</button> <button class="btn mini" data-troca="D|${esc(a.codigo)}" data-dica="Troca esta atividade auxiliar por outra composição">trocar</button></td></tr>`).join("") || '<tr><td colspan=7 class="nota">—</td></tr>'}</table>
    <h4>E — Tempo fixo</h4><label class="check" style="font-size:12px"><input type="checkbox" id="tfTodas" data-dica="Se marcado, a alteração vale para todas as composições do projeto com o mesmo tempo fixo"> aplicar a alteração em todas as composições com o mesmo tempo fixo</label>
      <table class="tab"><tr><th>Insumo / composição</th><th>Descrição</th><th>Quant. (t)</th><th class=n>Preço</th><th class=n>Custo</th><th>Ações</th></tr>
      ${x.tempo_fixo.map(t => `<tr class="${t.retirado ? "retirado" : ""}"><td>${esc(t.insumo)} · ${esc(t.composicao)}</td><td>${esc(t.descricao)}</td>
        <td>${inp(`data-tfq="${esc(t.insumo)}" data-tfde="${esc(t.composicao)}"`, t.quant)}</td><td class=n>${reais(t.preco)}</td><td class=n>${n4(t.total)}</td>
        <td><div class="linha-botoes" style="margin:0"><button class="btn mini" data-tfqok="${esc(t.insumo)}" data-tfde="${esc(t.composicao)}" data-dica="Grava a nova quantidade do tempo fixo">✓ quant.</button>
          ${t.retirado ? `<button class="btn mini" data-tfinc="${esc(t.insumo)}" data-tfde="${esc(t.composicao)}" data-dica="Volta a considerar o tempo fixo no preço (preço da base)">Incluir</button>`
                       : `<button class="btn mini" data-tfret="${esc(t.insumo)}" data-tfde="${esc(t.composicao)}" data-dica="Retira o tempo fixo do preço da composição">Retirar</button>`}
          ${tfSel(t)}</div></td></tr>`).join("") || '<tr><td colspan=6 class="nota">—</td></tr>'}</table>
    <h4>F — Transportes</h4><table class="tab"><tr><th>Insumo / composição</th><th>Descrição</th><th class=n>Quant.</th><th class=n>Custo LN/RP/P</th><th>DMT LN</th><th>DMT RP</th><th>DMT P</th><th class=n>Custo</th><th></th></tr>
      ${x.transportes.map(t => `<tr><td>${esc(t.insumo)} · ${esc(t.composicao)}</td><td>${esc(t.descricao)}</td><td class=n>${n4(t.quant)}</td><td class=n>${reais(t.custo_ln)} / ${reais(t.custo_rp)} / ${reais(t.custo_p)}</td>
        ${["dmt_ln", "dmt_rp", "dmt_p"].map(k => `<td>${inp(`data-dmt="${k}" data-ins="${esc(t.insumo)}" style="width:70px"`, t[k])}</td>`).join("")}<td class=n>${n4(t.total)}</td>
        <td><button class="btn mini" data-savdmt="${esc(t.insumo)}" data-dica="Grava as distâncias de transporte (km) deste insumo nesta composição">✓</button></td></tr>`).join("") || '<tr><td colspan=9 class="nota">—</td></tr>'}</table>
    <table class="tab" style="margin-top:10px"><tr class="tot"><td>Subtotal</td><td class=n>${reais(x.subtotal)}</td></tr>
      <tr class="tot"><td>Custo unitário direto total</td><td class=n>${reais(x.custo_direto)} ${x.custo_direto !== x.custo_direto_original ? `<small>(original ${reais(x.custo_direto_original)})</small>` : ""}</td></tr>
      <tr class="tot"><td>BDI (${pct(x.bdi_taxa)})</td><td class=n>${reais(x.bdi)}</td></tr>
      <tr class="tot"><td>Preço unitário</td><td class=n>${reais(x.preco)} ${x.preco !== x.preco_original ? `<small class="${x.preco > x.preco_original ? "var-pos" : "var-neg"}">(original ${reais(x.preco_original)})</small>` : ""}</td></tr></table></div>`;
  const D = $("#detComp"), recarregar = async () => { await renderServicos(); };
  $$("[data-regc]", D).forEach(ch => ch.onclick = () => { C_.regimeComp = ch.dataset.regc; abrirComposicao(cod); });
  $$("[data-vcomp2]", D).forEach(b => b.onclick = () => abrirComposicao(b.dataset.vcomp2));
  $$("[data-troca]", D).forEach(b => b.onclick = () => { const [sec, de] = b.dataset.troca.split("|"); dialogoTroca(sec, de, cod, recarregar); });
  const regIns = () => ($("#insAmbos")?.checked ?? true) ? "AMBOS" : reg;
  const altIns = async (tipo, codigo, valores) => { await jpost(`${base_}${E.pid}/custos/insumo`, { tipo, codigo, valores, regime: regIns() }); toast("Preço alterado — registrado em Alterações"); recarregar(); };
  $$("[data-saveq]", D).forEach(b => b.onclick = () => altIns("EQ", b.dataset.saveq, { custo_op: $(`[data-eqop="${b.dataset.saveq}"]`, D).value, custo_imp: $(`[data-eqimp="${b.dataset.saveq}"]`, D).value }));
  $$("[data-savmo]", D).forEach(b => b.onclick = () => altIns("MO", b.dataset.savmo, { preco: $(`[data-mo="${b.dataset.savmo}"]`, D).value }));
  $$("[data-savmat]", D).forEach(b => b.onclick = () => altIns("MAT", b.dataset.savmat, { preco: $(`[data-mat="${b.dataset.savmat}"]`, D).value }));
  const tf = async (corpo) => {
    const todas = $("#tfTodas", D).checked;
    try { await jpost(`${base_}${E.pid}/custos/tempo-fixo`, { composicao: todas ? null : cod, ...corpo }); toast("Tempo fixo alterado — registrado em Alterações"); recarregar(); } catch (e) { erro(e); }
  };
  $$("[data-tfqok]", D).forEach(b => b.onclick = () => tf({ acao: "quantidade", insumo: $("#tfTodas", D).checked ? null : b.dataset.tfqok, de_composicao: b.dataset.tfde, valor: $(`[data-tfq="${b.dataset.tfqok}"][data-tfde="${b.dataset.tfde}"]`, D).value }));
  $$("[data-tfret]", D).forEach(b => b.onclick = () => tf({ acao: "retirar", insumo: $("#tfTodas", D).checked ? null : b.dataset.tfret, de_composicao: b.dataset.tfde }));
  $$("[data-tfinc]", D).forEach(b => b.onclick = () => tf({ acao: "incluir", insumo: $("#tfTodas", D).checked ? null : b.dataset.tfinc, de_composicao: b.dataset.tfde }));
  $$("[data-tftrocar]", D).forEach(sel => sel.onchange = () => { if (sel.value) tf({ acao: "trocar", insumo: $("#tfTodas", D).checked ? null : sel.dataset.tftrocar, de_composicao: sel.dataset.tfde, para_composicao: sel.value }); });
  $$("[data-savdmt]", D).forEach(b => b.onclick = async () => {
    const corpo = { composicao: cod, insumo: b.dataset.savdmt };
    $$(`[data-ins="${b.dataset.savdmt}"]`, D).forEach(i => corpo[i.dataset.dmt] = i.value);
    await jpost(`${base_}${E.pid}/custos/dmt`, corpo); toast("DMT gravada"); recarregar();
  });
}

function dialogoTroca(sec, de, cod, depois) {
  const nomes = { A: "equipamento", B: "mão de obra", C: "material", D: "atividade auxiliar" };
  const d = $("#dlg"), f = $("#dlgForm");
  f.className = "form";
  f.innerHTML = `<h3>Trocar ${nomes[sec]} ${esc(de)}</h3>
    <label>Buscar na base <input id="dtBusca" placeholder="código ou descrição" data-dica="Procura na tabela de insumos da base SICRO"></label>
    <div class="tabela-rolagem" style="max-height:300px;margin-top:8px"><table class="tab" id="dtLista"></table></div>
    <label class="check" style="margin-top:8px"><input type="checkbox" id="dtTodas" data-dica="Troca em todas as composições que usam este insumo"> trocar em todas as composições</label>
    <div class="linha-botoes"><button class="btn" value="cancelar" data-dica="Fecha sem trocar">Fechar</button></div>`;
  d.showModal();
  let h;
  const buscar = async () => {
    const r = await api(`${base_}${E.pid}/custos/insumos-base?tipo=${sec}&q=${encodeURIComponent($("#dtBusca").value)}`);
    $("#dtLista").innerHTML = "<tr><th>Código</th><th>Descrição</th><th>Unid.</th><th class=n>Preço</th><th></th></tr>" + r.map(x =>
      `<tr><td>${esc(x.codigo)}</td><td>${esc(x.descricao || "")}</td><td>${esc(x.unidade || "")}</td><td class=n>${x.preco != null ? reais(x.preco) : x.custo_op != null ? reais(x.custo_op) + " / " + reais(x.custo_imp) : ""}</td>
        <td><button class="btn mini primario" type="button" data-esc="${esc(x.codigo)}" data-dica="Usa este insumo no lugar de ${esc(de)}">usar</button></td></tr>`).join("");
    $$("[data-esc]", f).forEach(b => b.onclick = async () => {
      try { await jpost(`${base_}${E.pid}/custos/trocar-insumo`, { secao: sec, de_codigo: de, para_codigo: b.dataset.esc, composicao: $("#dtTodas").checked ? null : cod });
        d.close(); toast("Insumo trocado — registrado em Alterações"); depois(); } catch (e) { erro(e); }
    });
  };
  $("#dtBusca").oninput = () => { clearTimeout(h); h = setTimeout(buscar, 300); };
  buscar();
}

// ---- composições próprias
const CAT_PROP = { servico: "Serviço", tempo_fixo: "Tempo fixo", transporte: "Transporte" };
const SEC_PROP = [
  ["equipamentos", "A — Equipamentos", [["codigo", "Código (ex.: E9018)"], ["quant", "Quant."], ["util_op", "Util. operativa"], ["util_imp", "Util. improdutiva"]]],
  ["mao_obra", "B — Mão de obra", [["codigo", "Código (ex.: P9824)"], ["quant", "Quant."]]],
  ["materiais", "C — Materiais", [["codigo", "Código (ex.: M0082)"], ["quant", "Quant."]]],
  ["auxiliares", "D — Atividades auxiliares", [["codigo", "Composição"], ["quant", "Quant."]]],
  ["tempo_fixo", "E — Tempo fixo", [["insumo", "Insumo"], ["composicao", "Composição de tempo fixo"], ["quant", "Quant. (t)"]]],
  ["transportes", "F — Transportes", [["insumo", "Insumo"], ["composicao", "Composição de transporte"], ["quant", "Quant. (t)"], ["custo_ln", "Custo LN"], ["custo_rp", "Custo RP"], ["custo_p", "Custo P"], ["dmt_ln", "DMT LN"], ["dmt_rp", "DMT RP"], ["dmt_p", "DMT P"]]],
];
async function renderProprias() {
  const lst = await api(`${base_}${E.pid}/custos/proprias`);
  C_.proprias = lst;
  $("#tabProprias").innerHTML = "<tr><th>Código</th><th>Descrição</th><th>Tipo</th><th>Unid.</th><th class=n>Custo direto SD</th><th class=n>Custo direto CD</th><th>Origem</th><th></th></tr>" + (lst.map(p =>
    `<tr><td>${esc(p.codigo)}</td><td>${esc(p.descricao || "")}${(p.avisos || []).length ? ` <span class="tag aviso" data-dica="${esc(p.avisos.join("; "))}">insumo fora da base</span>` : ""}</td><td>${esc(CAT_PROP[p.categoria] || p.categoria)}</td><td>${esc(p.unidade || "")}</td>
     <td class=n>${reais(p.cd_SD)}</td><td class=n>${reais(p.cd_CD)}</td><td><small>${esc(p.origem || "")}</small></td>
     <td><div class="linha-botoes" style="margin:0"><button class="btn mini" data-edprop="${esc(p.codigo)}" data-dica="Abre no editor">Editar</button>
       <button class="btn mini" data-verprop="${esc(p.codigo)}" data-dica="Mostra a composição calculada (analítico)">Ver</button>
       <button class="btn mini primario" data-addprop="${esc(p.codigo)}" data-dica="Inclui como serviço do projeto">+ Projeto</button>
       <button class="btn mini perigo" data-exprop="${esc(p.codigo)}" data-dica="Apaga a composição própria (de todos os projetos)">Excluir</button></div></td></tr>`).join("")
    || '<tr><td colspan=8 class="nota">Nenhuma composição própria.</td></tr>');
  $$("[data-edprop]").forEach(b => b.onclick = () => editorPropria(lst.find(p => p.codigo === b.dataset.edprop)));
  $$("[data-verprop]").forEach(b => b.onclick = () => { C_.sub = "servicos"; carregarCustos().then(() => abrirComposicao(b.dataset.verprop)); });
  $$("[data-addprop]").forEach(b => b.onclick = async () => { await jpost(`${base_}${E.pid}/custos/servicos`, { codigo: b.dataset.addprop }); toast("Adicionada aos serviços do projeto"); });
  $$("[data-exprop]").forEach(b => b.onclick = async () => { if (!confirm("Excluir a composição própria " + b.dataset.exprop + "?")) return; await api(`/api/custos/proprias/${encodeURIComponent(b.dataset.exprop)}`, { method: "DELETE" }); renderProprias(); });
  if (!$("#editorPropria").innerHTML) $("#editorPropria").innerHTML = '<p class="nota">Use “Nova composição”, “Copiar de uma composição” ou “Editar”.</p>';
}
function editorPropria(p) {
  p = p || { codigo: "", descricao: "", unidade: "", categoria: "servico", dados: { producao: 1, fic: 0, fit: 0, fic_base: "execucao" } };
  const d = p.dados || {};
  const sec = ([k, titulo, cols]) => `<h4>${titulo}</h4><table class="tab" data-sec="${k}"><tr>${cols.map(c => `<th>${esc(c[1])}</th>`).join("")}<th></th></tr>
    ${(d[k] || []).map(r => linhaProp(cols, r)).join("")}</table>
    <button class="btn mini" type="button" data-addlin="${k}" data-dica="Acrescenta uma linha nesta seção">+ linha</button>`;
  $("#editorPropria").innerHTML = `<form class="form" id="formPropria"><h3>${p.codigo ? "Editar " + esc(p.codigo) : "Nova composição própria"}</h3>
    <div class="campos">
      <label>Código <input name="codigo" value="${esc(p.codigo)}" placeholder="PN01" required data-dica="Código próprio (não pode coincidir com código do SICRO)"></label>
      <label>Unidade <input name="unidade" value="${esc(p.unidade || "")}" placeholder="t, tkm, m³…"></label>
      <label class="largo">Descrição <input name="descricao" value="${esc(p.descricao || "")}" required data-dica="Para transportes e tempos fixos, use o padrão SICRO (ex.: “Transporte com … - rodovia pavimentada”) para o sistema reconhecer o veículo"></label>
      <label>Tipo <select name="categoria" data-dica="Tempo fixo e transporte aparecem como opções na troca de veículo">${Object.entries(CAT_PROP).map(([k, v]) => `<option value="${k}" ${p.categoria === k ? "selected" : ""}>${v}</option>`).join("")}</select></label>
      <label>Produção da equipe <input name="producao" type="number" step="any" value="${d.producao ?? 1}" data-dica="Unidades por hora"></label>
      <label>FIC (fator) <input name="fic" type="number" step="any" value="${d.fic ?? 0}" data-dica="Fator de influência de chuvas"></label>
      <label>Base do FIC <select name="fic_base" data-dica="Execução: FIC × custo unitário de execução (como nas composições aprovadas pela CGCIT). Improdutivo: sobre mão de obra + custo improdutivo"><option value="execucao" ${d.fic_base !== "improdutivo" ? "selected" : ""}>custo de execução</option><option value="improdutivo" ${d.fic_base === "improdutivo" ? "selected" : ""}>mão de obra + improdutivo</option></select></label>
      <label>FIT (fator) <input name="fit" type="number" step="any" value="${d.fit ?? 0}" data-dica="Fator de interferência de tráfego"></label>
      <label class="largo">Origem / referência <input name="origem" value="${esc(p.origem || "")}" placeholder="ex.: ATF nº 32 – FGV/2024"></label>
      <label class="largo">Observações <textarea name="observacoes" rows="2">${esc(p.observacoes || "")}</textarea></label>
    </div>
    ${SEC_PROP.map(sec).join("")}
    <div class="linha-botoes"><button class="btn primario" type="submit" data-dica="Grava a composição; o preço é calculado com os insumos da base do projeto">Salvar composição</button></div></form>`;
  $$("[data-addlin]").forEach(b => b.onclick = () => { const k = b.dataset.addlin, cols = SEC_PROP.find(x => x[0] === k)[2]; $(`table[data-sec="${k}"]`).insertAdjacentHTML("beforeend", linhaProp(cols, {})); ligarRemover(); });
  ligarRemover();
  $("#formPropria").onsubmit = async e => {
    e.preventDefault();
    const f = e.target, dados = { producao: f.producao.value, fic: f.fic.value, fit: f.fit.value, fic_base: f.fic_base.value };
    for (const [k, , cols] of SEC_PROP) dados[k] = $$(`table[data-sec="${k}"] tr[data-lin]`).map(tr => Object.fromEntries(cols.map(([c]) => [c, $(`[data-c="${c}"]`, tr).value]))).filter(r => r.codigo || r.composicao);
    try {
      const r = await jpost("/api/custos/proprias", { codigo: f.codigo.value, descricao: f.descricao.value, unidade: f.unidade.value, categoria: f.categoria.value, origem: f.origem.value, observacoes: f.observacoes.value, dados });
      toast("Composição " + r.codigo + " salva"); C_.tfOpcoes = null; renderProprias();
    } catch (er) { erro(er); }
  };
}
const linhaProp = (cols, r) => `<tr data-lin>${cols.map(([c]) => `<td><input data-c="${c}" value="${esc(r[c] ?? "")}" ${c === "codigo" || c === "insumo" || c === "composicao" ? "" : 'type="number" step="any"'} style="width:${c === "codigo" || c === "composicao" ? 120 : 80}px"></td>`).join("")}<td><button class="btn mini perigo" type="button" data-rmlin data-dica="Remove a linha">×</button></td></tr>`;
const ligarRemover = () => $$("[data-rmlin]").forEach(b => b.onclick = () => b.closest("tr").remove());
$("#btnNovaPropria").onclick = () => editorPropria(null);
$("#btnExemplo28").onclick = async () => { await jpost("/api/custos/proprias/exemplo-28m3", {}); toast("PN01–PN04 criadas (caminhão 28 m³)"); C_.tfOpcoes = null; renderProprias(); };
$("#btnCopiarPropria").onclick = () => dialogo("Copiar composição", [["codigo", "Código da composição de origem (SICRO ou própria)"], ["novo_codigo", "Código da nova composição (ex.: PN10)"], ["descricao", "Descrição (opcional)"]],
  async v => { const r = await jpost(`${base_}${E.pid}/custos/proprias/copiar`, v); toast("Criada " + r.codigo); await renderProprias(); editorPropria(C_.proprias.find(p => p.codigo === r.codigo)); });

// ---- insumos
let _buscaInsH;
$("#buscaIns").oninput = () => { clearTimeout(_buscaInsH); _buscaInsH = setTimeout(renderInsumos, 350); };
async function renderInsumos() {
  const tipos = [[null, "Todos"], ["EQ", "Equipamentos"], ["MO", "Mão de obra"], ["MAT", "Materiais"], ["TF", "Tempo fixo"]];
  $("#chipsTipoIns").innerHTML = tipos.map(([k, r]) => `<span class="chip ${C_.tipoIns === k ? "ativo" : ""}" data-ti="${k ?? ""}" data-dica="Filtrar por tipo de insumo">${r}</span>`).join("");
  $$("#chipsTipoIns .chip").forEach(c => c.onclick = () => { C_.tipoIns = c.dataset.ti || null; renderInsumos(); });
  const q = new URLSearchParams({ regime: C_.cfg.regime, q: $("#buscaIns").value }); if (C_.tipoIns) q.set("tipo", C_.tipoIns);
  const lst = await api(`${base_}${E.pid}/custos/insumos?${q}`);
  $("#tabInsumos").innerHTML = `<tr><th>Tipo</th><th>Código</th><th>Descrição</th><th>Unid.</th><th>Preço atual (${REG[C_.cfg.regime]})</th><th class=n>Original</th><th class=n>Usos</th><th></th></tr>` + lst.map(i => {
    const atual = i.tipo === "EQ" ? `<input type="number" step="any" data-iop="${esc(i.codigo)}" value="${i.custo_op}" style="width:95px" data-dica="Custo horário produtivo"> / <input type="number" step="any" data-iimp="${esc(i.codigo)}" value="${i.custo_imp}" style="width:95px" data-dica="Custo horário improdutivo">`
      : `<input type="number" step="any" data-ip="${esc(i.tipo)}:${esc(i.codigo)}" value="${i.preco}" style="width:110px">`;
    const orig = i.tipo === "EQ" ? `${n6(i.original_op)} / ${n6(i.original_imp)}` : n6(i.original);
    return `<tr class="${i.alterado ? "alterado sit-corrigido" : ""}"><td>${esc(i.tipo)}</td><td>${esc(i.codigo)}</td><td>${esc(i.descricao)}</td><td>${esc(i.unidade || "")}</td><td>${atual}</td><td class=n>${orig}</td><td class=n>${i.usos}</td>
      <td><button class="btn mini" data-salvai="${esc(i.tipo)}:${esc(i.codigo)}" data-dica="Grava o preço; vale para todas as composições que usam este insumo">✓</button></td></tr>`;
  }).join("");
  $$("[data-salvai]").forEach(b => b.onclick = async () => {
    const [tipo, codigo] = b.dataset.salvai.split(":");
    const valores = tipo === "EQ" ? { custo_op: $(`[data-iop="${codigo}"]`).value, custo_imp: $(`[data-iimp="${codigo}"]`).value } : { preco: $(`[data-ip="${tipo}:${codigo}"]`).value };
    try { await jpost(`${base_}${E.pid}/custos/insumo`, { tipo, codigo, valores, regime: $("#insAmbos").checked ? "AMBOS" : C_.cfg.regime }); toast("Preço alterado"); renderInsumos(); } catch (e) { erro(e); }
  });
}
const n6 = v => v == null ? "—" : v.toLocaleString("pt-BR", { maximumFractionDigits: 6 });

// ---- alterações
async function renderAltCusto() {
  const lst = await api(`${base_}${E.pid}/custos/alteracoes`);
  $("#tabAltCusto").innerHTML = "<tr><th>Quando</th><th>Tipo</th><th>Alteração</th><th>Situação</th><th></th></tr>" + (lst.slice().reverse().map(a =>
    `<tr class="${a.ativa ? "" : "retirado"}"><td>${esc(a.quando)}</td><td>${esc(a.tipo)}</td><td>${esc(a.descricao)}</td><td>${a.ativa ? "ativa" : "desfeita"}</td>
     <td><button class="btn mini" data-atv="${a.id}" data-v="${a.ativa ? 0 : 1}" data-dica="${a.ativa ? "Desfaz esta alteração (os preços voltam)" : "Reativa esta alteração"}">${a.ativa ? "Desfazer" : "Reativar"}</button></td></tr>`).join("")
    || '<tr><td colspan=5 class="nota">Nenhuma alteração.</td></tr>');
  $$("[data-atv]").forEach(b => b.onclick = async () => { await jpost(`${base_}${E.pid}/custos/alteracoes/${b.dataset.atv}`, { ativa: b.dataset.v === "1" }); renderAltCusto(); });
}

// ---- binômio
const B_ = { dados: null, serie: null };
const pctN = v => v == null ? "" : (v * 100).toLocaleString("pt-BR", { maximumFractionDigits: 4 }) + "%";
function escolherArquivo(accept = "") {
  return new Promise(ok => { const i = document.createElement("input"); i.type = "file"; i.accept = accept; i.onchange = () => ok(i.files[0] || null); i.click(); });
}
async function enviarAnexo(binomio_id, tipo, rotulo) {
  const arq = await escolherArquivo(".pdf,.xlsx,.xls,.docx,.doc,.png,.jpg,.jpeg,.msg,.eml,.txt,.zip"); if (!arq) return;
  const fd = new FormData(); fd.append("arquivo", arq); fd.append("tipo", tipo);
  if (binomio_id) fd.append("binomio_id", binomio_id); if (rotulo) fd.append("rotulo", rotulo);
  try { await api(`${base_}${E.pid}/anexos`, { method: "POST", body: fd }); toast("Anexo gravado"); renderBinomio(); } catch (e) { erro(e); }
}
const listaAnexos = (lst, tipos) => !lst.length ? "" : `<div class="anexos">📎 ${lst.map(a => `<span class="anexo"><a href="/api/anexos/${a.id}" data-dica="Baixar o arquivo anexado">${esc(a.nome)}</a>
  <small>${esc(tipos[a.tipo] || a.tipo)}${a.rotulo ? " · " + esc(a.rotulo) : ""}</small> <button class="btn mini perigo" data-exax="${a.id}" data-dica="Remove o anexo">×</button></span>`).join(" ")}</div>`;
async function renderBinomio() {
  const d = B_.dados = await api(`${base_}${E.pid}/binomio`);
  $("#binRef").innerHTML = `Data-base: <b>${esc(d.data_base)}</b> · BDI aplicado aos betuminosos: <b>${pctN(d.bdi)}</b> (Custos → Data-base e BDI).`;
  $("#anexosGerais").innerHTML = listaAnexos(d.anexos_gerais, d.tipos_anexo);
  const vazio = !d.materiais.length && !d.produtos.length;
  $("#listaMateriais").innerHTML = vazio ? `<div class="caixa"><p class="nota">Nenhum binômio neste projeto. Crie um material ou importe de uma planilha PATO (abas BINOMIO_COTACOES e BINOMIO_ANP).</p></div>` :
    d.materiais.map(m => cartaoMaterial(m, d)).join("");
  $("#listaBetuminosos").innerHTML = d.produtos.map(p => cartaoBetuminoso(p, d)).join("");
  $$("[data-exax]").forEach(b => b.onclick = async () => { if (!confirm("Remover este anexo?")) return; await api(`/api/anexos/${b.dataset.exax}`, { method: "DELETE" }); renderBinomio(); });
  $$("[data-edbin]").forEach(b => b.onclick = () => { const id = +b.dataset.edbin; const m = d.materiais.find(x => x.id === id); m ? editorMaterial(m) : editorBetuminoso(d.produtos.find(x => x.id === id)); });
  $$("[data-exbin]").forEach(b => b.onclick = async () => { if (!confirm("Excluir este binômio e seus anexos?")) return; await api(`${base_}${E.pid}/binomio/${b.dataset.exbin}`, { method: "DELETE" }); renderBinomio(); });
  $$("[data-axbin]").forEach(b => b.onclick = () => { const [id, tipo] = b.dataset.axbin.split(":"); enviarAnexo(id, tipo, prompt("Fornecedor/origem a que se refere o anexo (opcional):") || ""); });
  $$("[data-apbin]").forEach(b => b.onclick = () => aplicarVencedor(+b.dataset.apbin));
  $$("[data-cotbin]").forEach(b => b.onclick = () => cotacaoPdf(+b.dataset.cotbin));
  renderResumoBin(d);
}
function renderResumoBin(d) {
  const r = d.resumo || [];
  if (!r.length) { $("#resumoBin").innerHTML = ""; return; }
  const pend = r.filter(x => x.conferido && !x.adotado).length;
  $("#resumoBin").innerHTML = `<div class="bin-cab"><h3>③ Resumo do mais vantajoso · ④ Conferência · ⑤ Preço adotado</h3>
    <div class="linha-botoes" style="margin:0"><button class="btn primario" id="btnAdotarConf" ${pend ? "" : "disabled"} data-dica="Grava nas composições (insumo SICRO, sem e com desoneração) o preço do vencedor de cada material conferido, e as DMT do transporte">Adotar nas composições os conferidos (${pend})</button></div></div>
    <p class="nota">Confira cada linha (vencedor, preço reajustado e DMT) e marque “conferido”. Só os conferidos são adotados. Se uma cotação mudar depois, a conferência deixa de valer.</p>
    <div class="tabela-rolagem"><table class="tab"><tr><th>Material</th><th>Código</th><th class=n>Cotações</th><th>Mais vantajoso</th><th class=n>Total R$/t</th><th class=n>SICRO R$/t</th>
      <th class=n>Preço a adotar</th><th class=n>DMT pav./não pav.</th><th>Avisos</th><th>Conferido</th><th>Composição</th></tr>
    ${r.map(x => `<tr class="${x.adotado ? "adotado" : ""}"><td>${esc(x.material)}</td><td>${esc(x.codigo || "—")}</td><td class=n>${x.tipo === "material" ? x.cotacoes : "ANP"}</td>
      <td>${x.vencedor ? (x.sicro_vence ? "SICRO (centro sede)" : esc(x.vencedor)) : '<span class="tag aviso">sem cotação</span>'}</td>
      <td class=n><b>${reais(x.total)}</b></td><td class=n>${reais(x.total_sicro)}</td><td class=n>${x.preco_adotar != null ? `R$ ${reais(x.preco_adotar)}/${esc(x.unidade)}` : ""}</td>
      <td class=n>${x.tipo === "material" ? `${nf(x.dmt_pav)} / ${nf(x.dmt_npav)}` : ""}</td>
      <td>${x.avisos.map(a => `<small class="tag aviso">${esc(a)}</small>`).join(" ")}${x.conferencia_vencida ? '<small class="tag erro">cotação mudou depois da conferência</small>' : ""}</td>
      <td><label class="check"><input type="checkbox" data-confbin="${x.id}" ${x.conferido ? "checked" : ""} ${x.vencedor ? "" : "disabled"}> ${x.conferido && x.conferido_por ? esc(x.conferido_por) : ""}</label></td>
      <td>${x.adotado ? '<span class="tag ok">adotado</span>' : x.sicro_vence ? '<span class="tag">SICRO mantido</span>' : '<span class="tag">pendente</span>'}</td></tr>`).join("")}</table></div>`;
  $$("[data-confbin]").forEach(c => c.onchange = async () => {
    try { await jpost(`${base_}${E.pid}/binomio/${c.dataset.confbin}/conferir`, { conferido: c.checked }); renderBinomio(); } catch (e) { erro(e); }
  });
  const bt = $("#btnAdotarConf");
  if (bt) bt.onclick = async () => {
    if (!confirm("Adotar nas composições o preço dos materiais conferidos? As alterações entram em “Alterações” e podem ser desfeitas.")) return;
    try { const a = await jpost(`${base_}${E.pid}/binomio/aplicar-conferidos`, {}); toast(a.mensagens.join(" ")); renderBinomio(); } catch (e) { erro(e); }
  };
}

// cotação em PDF: leitura automática (OCR) → conferência e ajuste → grava no binômio
async function cotacaoPdf(binomio_id) {
  const arq = await escolherArquivo(".pdf,.png,.jpg,.jpeg,.tif,.tiff"); if (!arq) return;
  const pn = $("#painelCotOcr"); pn.hidden = false;
  pn.innerHTML = `<p class="carregando">Lendo a cotação ${esc(arq.name)}… (PDF digitalizado ou foto: OCR, pode levar alguns segundos)</p>`;
  pn.scrollIntoView({ behavior: "smooth" });
  const fd = new FormData(); fd.append("arquivo", arq);
  let r;
  try { r = await api(`${base_}${E.pid}/binomio/cotacao/ler`, { method: "POST", body: fd }); } catch (e) { pn.innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; return; }
  if (!r.itens.length) r.itens = [{ material: "", preco: null, unidade: "m³", binomio_id: binomio_id || null, dmt_pav: r.distancia_km, dmt_npav: 0 }];
  if (binomio_id) r.itens.forEach(i => { if (!i.binomio_id) i.binomio_id = binomio_id; });
  const optsMat = sel => `<option value="">➕ novo material</option>` + r.materiais.map(m => `<option value="${m.id}" ${+sel === m.id ? "selected" : ""}>${esc(m.nome)}${m.codigo ? " · " + esc(m.codigo) : ""}</option>`).join("");
  const linha = i => `<tr data-cit><td><input type="checkbox" data-k="incluir" checked></td><td><select data-k="binomio_id">${optsMat(i.binomio_id)}</select>
      <input data-k="material" value="${esc(i.material || "")}" placeholder="nome do material novo" style="width:150px"></td>
    <td><input data-k="codigo" value="${esc(i.codigo || "")}" style="width:80px" placeholder="SICRO" data-dica="Código do insumo SICRO (material novo)"></td>
    <td><input data-k="preco" type="number" step="any" value="${i.preco ?? ""}" style="width:90px"></td>
    <td><select data-k="unidade"><option value="m3" ${String(i.unidade).startsWith("m") ? "selected" : ""}>R$/m³</option><option value="t" ${i.unidade === "t" ? "selected" : ""}>R$/t</option></select></td>
    <td><input data-k="densidade" type="number" step="any" value="${i.densidade ?? ""}" style="width:70px" placeholder="do material"></td>
    <td><input data-k="dmt_pav" type="number" step="any" value="${i.dmt_pav ?? ""}" style="width:75px"></td>
    <td><input data-k="dmt_npav" type="number" step="any" value="${i.dmt_npav ?? ""}" style="width:75px"></td>
    <td><small>${esc(i.descricao || "")}</small></td></tr>`;
  const pos = r.posicao;
  pn.innerHTML = `<div class="bin-cab"><h3>① Cotação lida — confira e ajuste antes de gravar</h3><small>${esc(arq.name)} · ${r.ocr ? "lido por OCR (documento digitalizado)" : "texto do PDF"}</small></div>
    ${r.avisos.map(a => `<p class="tag aviso">${esc(a)}</p>`).join("")}
    <div class="form"><div class="campos cot-campos">
      <label>Fornecedor <input id="coForn" value="${esc(r.fornecedor || "")}"></label>
      <label>CNPJ <input id="coCnpj" value="${esc(r.cnpj || "")}"></label>
      <label>Mês da cotação <input id="coData" type="month" value="${esc(r.data || "")}" data-dica="Mês da proposta: o preço é reajustado pelo índice até a data-base"></label>
      <label>Frete <select id="coFrete"><option value="">não informado</option><option ${r.frete === "FOB" ? "selected" : ""}>FOB</option><option ${r.frete === "CIF" ? "selected" : ""}>CIF</option></select></label>
      <label>Local <input id="coLocal" value="${esc(r.local || "")}"></label>
      <label>Endereço na rodovia <input value="${r.rodovia ? `BR-${r.rodovia.br} km ${r.rodovia.km}` : ""}" disabled></label></div>
    ${pos ? `<p class="nota">📍 Posição do fornecedor: ${esc(pos.fonte_posicao || "")}${pos.rodovia_proxima ? " · " + esc(pos.rodovia_proxima) : ""}${pos.distancia_canteiro_km != null ? ` · ${nf(pos.distancia_canteiro_km)} km em linha reta até o canteiro` : ""}</p>` : ""}
    <h4>Itens (DMT em km até o canteiro — ajuste pavimentada / não pavimentada)</h4>
    <div class="tabela-rolagem"><table class="tab" id="tabCotOcr"><tr><th>Gravar</th><th>Material do binômio</th><th>Código</th><th>Preço</th><th>Unid.</th><th>Dens. t/m³</th><th>DMT pav.</th><th>DMT não pav.</th><th>Linha lida</th></tr>${r.itens.map(linha).join("")}</table></div>
    <div class="linha-botoes"><button class="btn mini" id="coAdd">+ Item</button></div>
    <details><summary>Texto lido do documento</summary><pre style="white-space:pre-wrap;max-height:260px;overflow:auto">${esc(r.texto || "")}</pre></details>
    <div class="linha-botoes"><button class="btn primario" id="coGravar" data-dica="Acrescenta a cotação aos materiais (substitui a do mesmo fornecedor) e anexa o PDF">Gravar cotação no binômio</button><button class="btn" id="coFechar">Cancelar</button></div></div>`;
  $("#coAdd").onclick = () => $("#tabCotOcr").insertAdjacentHTML("beforeend", linha({ unidade: "m3", dmt_pav: r.distancia_km, dmt_npav: 0, binomio_id }));
  $("#coFechar").onclick = () => pn.hidden = true;
  $("#coGravar").onclick = async () => {
    const itens = $$("#tabCotOcr tr[data-cit]").map(tr => Object.fromEntries($$("[data-k]", tr).map(i => [i.dataset.k, i.type === "checkbox" ? i.checked : i.value === "" ? null : i.value])));
    const dados = { fornecedor: $("#coForn").value, cnpj: $("#coCnpj").value, data: $("#coData").value, frete: $("#coFrete").value || null, local: $("#coLocal").value, itens };
    const f2 = new FormData(); f2.append("arquivo", arq); f2.append("dados", JSON.stringify(dados));
    try { const g = await api(`${base_}${E.pid}/binomio/cotacao/adicionar`, { method: "POST", body: f2 });
      toast(`Cotação gravada: ${g.gravados.map(x => x.material).join(", ")}`); pn.hidden = true; renderBinomio(); } catch (e) { erro(e); }
  };
}

// cadastro de fornecedores e pontos do KMZ
async function renderForn() {
  const pn = $("#painelForn"); pn.hidden = false;
  const f = await api(`${base_}${E.pid}/fornecedores`);
  pn.innerHTML = `<div class="bin-cab"><h3>Fornecedores e localização</h3><div class="linha-botoes" style="margin:0">
      <button class="btn mini" id="fnImp" data-dica="Planilha com as colunas FORNECEDOR, ENDEREÇO e INSUMO (opcionais CNPJ e CONTATO). O endereço “BR-xxx, km yyy” é localizado no SNV">Importar planilha de fornecedores</button>
      <button class="btn mini" id="fnKmz" data-dica="Pontos do Google Earth (pedreiras, areais…): localizados no SNV e incluídos no croqui">Importar KMZ/KML</button>
      <button class="btn mini" id="fnFechar">Fechar</button></div></div>
    <p class="nota">${esc(f.nota)} ${f.km_canteiro == null ? "<b>Informe o km do canteiro no croqui (aba Transporte) para calcular a distância.</b>" : `Canteiro no km ${nf(f.km_canteiro)}.`}</p>
    ${f.lista.length ? `<div class="tabela-rolagem"><table class="tab"><tr><th>Fornecedor</th><th>Insumo</th><th>Endereço</th><th>Posição</th><th>Rodovia mais próxima</th><th class=n>km na rodovia do projeto</th><th class=n>Dist. ao eixo (km)</th><th class=n>Dist. ao canteiro (linha reta, km)</th></tr>
      ${f.lista.map(x => `<tr><td>${esc(x.nome)}</td><td>${esc(x.insumo || "")}</td><td><small>${esc(x.endereco || "")}</small></td><td><small>${esc(x.fonte_posicao || "sem posição — importe o KMZ")}</small></td>
        <td><small>${esc(x.rodovia_proxima || "")}</small></td><td class=n>${nf(x.km_projeto)}</td><td class=n>${nf(x.distancia_eixo_km)}</td><td class=n>${nf(x.distancia_canteiro_km)}</td></tr>`).join("")}</table></div>`
      : '<p class="nota">Nenhum fornecedor cadastrado.</p>'}`;
  $("#fnFechar").onclick = () => pn.hidden = true;
  $("#fnImp").onclick = async () => { const a = await escolherArquivo(".xlsx,.xlsm"); if (!a) return; const fd = new FormData(); fd.append("arquivo", a);
    try { await api(`${base_}${E.pid}/fornecedores/importar`, { method: "POST", body: fd }); toast("Fornecedores importados"); renderForn(); } catch (e) { erro(e); } };
  $("#fnKmz").onclick = async () => { await importarKmz(); renderForn(); };
}
async function importarKmz() {
  const a = await escolherArquivo(".kmz,.kml"); if (!a) return null;
  const fd = new FormData(); fd.append("arquivo", a);
  try { const r = await api(`${base_}${E.pid}/croqui/pontos`, { method: "POST", body: fd });
    toast(`${r.pontos.length} ponto(s) localizados no SNV ${r.versao_snv || ""}`); return r; } catch (e) { erro(e); return null; }
}
function cartaoMaterial(m, d) {
  const un = m.sicro ? (m.sicro.unidade || "") : "";
  const lin = m.linhas.map(l => `<tr class="${l.vencedor ? "vencedor" : ""}"><td>${l.vencedor ? "🏆 " : ""}${esc(l.fornecedor)}${l.sicro ? ' <small class="tag">SICRO</small>' : ""}${l.local ? `<br><small>${esc(l.local)}</small>` : ""}</td>
    <td class=n>${reais(l.unidade === "t" ? l.preco_t : l.preco_m3)} /${l.unidade === "t" ? "t" : "m³"}</td><td class=n>${nf(l.densidade, 3)}</td><td>${esc(l.data || "")}</td>
    <td class=n title="índice data-base ${nf(l.indice_base, 3)} ÷ índice da cotação ${nf(l.indice_cotacao, 3)} − 1">${pctN(l.fator)}</td>
    <td class=n>${reais(l.preco_t_reaj)}</td><td class=n>${reais(l.preco_m3_reaj)}</td><td class=n>${nf(l.dmt_pav)}</td><td class=n>${nf(l.dmt_npav)}</td>
    <td class=n>${reais(l.transporte)}</td><td class=n><b>${reais(l.total)}</b></td></tr>`).join("");
  const ap = m.aplicado ? `<span class="tag ok">aplicado: ${esc(m.aplicado.fornecedor)} — R$ ${reais(m.aplicado.preco)}</span>` : "";
  return `<div class="caixa bin-card"><div class="bin-cab"><h3>${esc(m.nome)} <small>${esc(m.codigo || "sem código SICRO")} · ${esc(d.grupos[m.grupo] || m.grupo)}</small></h3>
    <div>${m.vencedor ? `Mais vantajoso: <b>${esc(m.vencedor.fornecedor)}</b> — R$ ${reais(m.vencedor.total)}/t` : '<span class="tag aviso">sem cotação válida</span>'} ${ap}</div></div>
    ${m.sem_indice ? `<p class="tag aviso">Sem índice “${esc(m.indice_nome)}” para ${esc(m.data_base)} — preços sem reajuste. Cadastre o índice em “Índices de reajuste”.</p>` : ""}
    <p class="nota">Índice: ${esc(m.indice_nome)} · custo do transporte: pavimentada R$ ${nf(m.custo_pav, 4)}/t·km, não pavimentada R$ ${nf(m.custo_npav, 4)}/t·km${m.sicro ? ` · SICRO ${esc(m.codigo)}: R$ ${reais(m.sicro.preco)}/${esc(un)}` : ""}</p>
    <div class="tabela-rolagem"><table class="tab"><tr><th>Fornecedor</th><th class=n>Preço cotado</th><th class=n>Dens. (t/m³)</th><th>Data</th><th class=n>Reajuste</th>
      <th class=n>Preço reaj. R$/t</th><th class=n>Preço reaj. R$/m³</th><th class=n>DMT pav. (km)</th><th class=n>DMT não pav. (km)</th><th class=n>Transporte R$/t</th><th class=n>TOTAL R$/t</th></tr>${lin}</table></div>
    ${listaAnexos(m.anexos, d.tipos_anexo)}
    <div class="linha-botoes"><button class="btn mini primario" data-apbin="${m.id}" data-dica="Grava o preço reajustado do vencedor no insumo SICRO (todas as composições) e as DMTs do transporte">Aplicar vencedor ao insumo</button>
      <button class="btn mini" data-edbin="${m.id}" data-dica="Edita o material e as cotações">Editar</button>
      <button class="btn mini" data-cotbin="${m.id}" data-dica="Lê o PDF da cotação (OCR se digitalizado), pré-preenche preço, data, unidade e DMT para conferir e grava neste material, com o PDF anexado">📄 Cotação em PDF (leitura automática)</button>
      <button class="btn mini" data-axbin="${m.id}:cotacao" data-dica="Só anexa o arquivo (proposta, e-mail, planilha), sem ler">Anexar arquivo</button>
      <button class="btn mini perigo" data-exbin="${m.id}" data-dica="Exclui este material do binômio">Excluir</button></div></div>`;
}
function cartaoBetuminoso(p, d) {
  const lin = p.linhas.map(l => `<tr class="${l.vencedor ? "vencedor" : ""}"><td>${l.vencedor ? "🏆 " : ""}${esc(l.nome)}</td><td>${esc(l.uf || "")}</td><td>${esc(l.local || "")}</td>
    <td class=n>${nf(l.d_fluvial)}</td><td class=n>${nf(l.d_pav)}</td><td class=n>${nf(l.d_rp)}</td><td class=n>${nf(l.d_ln)}</td><td class=n>${pctN(l.icms)}</td>
    <td class=n>${reais(l.aq_sem_icms)}</td><td class=n>${reais(l.tr_sem_icms)}</td><td class=n>${reais(l.aq_icms)}</td><td class=n>${reais(l.tr_icms)}</td>
    <td class=n>${reais(l.pedagio_t)}</td><td class=n>${reais(l.aq_bdi)}</td><td class=n>${reais(l.tr_bdi)}</td><td class=n><b>${reais(l.total)}</b></td></tr>`).join("");
  const ap = p.aplicado ? `<span class="tag ok">aplicado: ${esc(p.aplicado.fornecedor)} — R$ ${reais(p.aplicado.preco)}/t em ${esc(p.aplicado.codigo)}</span>` : "";
  return `<div class="caixa bin-card"><div class="bin-cab"><h3>${esc(p.produto)} <small>${esc(p.codigo || "sem código SICRO")} · betuminoso ANP</small></h3>
    <div>${p.vencedor ? `Mais vantajoso: <b>${esc(p.vencedor.local)}/${esc(p.vencedor.uf)}</b> — R$ ${reais(p.vencedor.total)}/t` : '<span class="tag aviso">sem preço ANP</span>'} ${ap}</div></div>
    <p class="nota">Índice ${esc(p.indice || "Pavimentação")} na data-base: ${nf(p.indice_atual, 3)} → Kr = ${nf(p.kr, 3)} (base jul/2014 = 270,237) · Kf = ${nf(p.kf, 3)} (base nov/2016 = 303,752) ·
      PIS ${pctN(p.pis)} · COFINS ${pctN(p.cofins)} · BDI aquisição ${pctN(p.bdi)}${p.bdi_projeto ? " (do projeto)" : ""} · BDI transporte ${pctN(p.bdi_transporte)} · pedágio ÷ ${nf(p.ton_viagem)} t
      ${p.fluvial_sempre ? " · parcela fixa do fluvial sempre somada (como na planilha de referência)" : ""}</p>
    <div class="tabela-rolagem"><table class="tab"><tr><th>Origem</th><th>UF</th><th>Local</th><th class=n>Fluvial D</th><th class=n>Pav. D1</th><th class=n>RP D2</th><th class=n>LN D3</th><th class=n>ICMS</th>
      <th class=n>Aquisição ANP R$/t</th><th class=n>Transp. s/ ICMS</th><th class=n>Aquisição c/ ICMS</th><th class=n>Transp. c/ ICMS</th><th class=n>Pedágio R$/t</th>
      <th class=n>Aquisição c/ BDI</th><th class=n>Transp. c/ BDI</th><th class=n>TOTAL R$/t</th></tr>${lin}</table></div>
    ${listaAnexos(p.anexos, d.tipos_anexo)}
    <div class="linha-botoes"><button class="btn mini primario" data-apbin="${p.id}" data-dica="Grava a aquisição com ICMS da origem vencedora no insumo SICRO (o BDI é aplicado na composição)">Aplicar vencedor ao insumo</button>
      <button class="btn mini" data-edbin="${p.id}" data-dica="Edita o produto, as origens, ICMS e distâncias">Editar</button>
      <button class="btn mini" data-axbin="${p.id}:icms" data-dica="Anexa o documento do ICMS (legislação/alíquota do estado de origem)">Anexar ICMS</button>
      <button class="btn mini" data-axbin="${p.id}:anp" data-dica="Anexa a tabela de preços ANP usada">Anexar tabela ANP</button>
      <button class="btn mini perigo" data-exbin="${p.id}" data-dica="Exclui este betuminoso do binômio">Excluir</button></div></div>`;
}
async function aplicarVencedor(id) {
  const it = [...B_.dados.materiais, ...B_.dados.produtos].find(x => x.id === id);
  let codigo = it.codigo;
  if (!codigo) { codigo = prompt("Código do insumo no SICRO que receberá o preço (ex.: M0191):"); if (!codigo) return; }
  const v = it.vencedor; if (!v) return toast("Não há cotação válida.");
  const forn = v.fornecedor || `${v.local}/${v.uf}`;
  if (!confirm(`Aplicar o vencedor (${forn}) ao insumo ${codigo}? A alteração entra em “Alterações” e pode ser desfeita.`)) return;
  try { const r = await jpost(`${base_}${E.pid}/binomio/${id}/aplicar`, { codigo, aplicar_dmt: true }); toast(r.mensagens.join(" ")); renderBinomio(); } catch (e) { erro(e); }
}
const inp = (k, v, t = "text", w = 90, extra = "") => `<input data-c="${k}" type="${t}" ${t === "number" ? 'step="any"' : ""} value="${esc(v ?? "")}" style="width:${w}px" ${extra}>`;
function editorMaterial(m) {
  m = m || { nome: "", grupo: "petreo", indice: B_.dados.indices.includes("Conservação Rodoviária") ? "Conservação Rodoviária" : "", custo_pav: null, custo_npav: null, cotacoes: [{}, {}, {}] };
  const ed = $("#editorBin"); ed.hidden = false;
  const linha = c => `<tr data-cot><td>${inp("fornecedor", c.fornecedor, "text", 150)}</td><td><input data-c="sicro" type="checkbox" ${c.sicro ? "checked" : ""} data-dica="Linha de referência: usa o preço do insumo na base SICRO do projeto"></td>
    <td>${inp("preco", c.preco, "number", 90, c.sicro ? 'placeholder="base SICRO" data-dica="Linha SICRO: o preço vem da base do projeto"' : "")}</td><td><select data-c="unidade"><option value="t" ${c.unidade !== "m3" ? "selected" : ""}>R$/t</option><option value="m3" ${c.unidade === "m3" ? "selected" : ""}>R$/m³</option></select></td>
    <td>${inp("densidade", c.densidade, "number", 70)}</td><td>${inp("data", c.data, "month", 130, 'data-dica="Mês da cotação (para o reajuste até a data-base)"')}</td>
    <td>${inp("dmt_pav", c.dmt_pav, "number", 70)}</td><td>${inp("dmt_npav", c.dmt_npav, "number", 70)}</td><td>${inp("local", c.local, "text", 130)}</td>
    <td><button class="btn mini perigo" type="button" data-rmlin data-dica="Remove a cotação">×</button></td></tr>`;
  ed.innerHTML = `<h3>${m.id ? "Editar" : "Novo"} material cotado</h3><div class="form"><div class="campos">
    <label>Material <input id="bmNome" value="${esc(m.nome)}" data-dica="Ex.: Brita 1, Pedra de mão, Madeira serrada, CBUQ comercial"></label>
    <label>Código SICRO <input id="bmCod" value="${esc(m.codigo || "")}" data-dica="Insumo da base (ex.: M0191) — dá o preço de referência e recebe o preço vencedor"></label>
    <label>Grupo <select id="bmGrupo">${Object.entries(B_.dados.grupos).map(([k, r]) => `<option value="${k}" ${m.grupo === k ? "selected" : ""}>${esc(r)}</option>`).join("")}</select></label>
    <label>Índice de reajuste <select id="bmInd" data-dica="Pétreos: Conservação Rodoviária (como na planilha de referência)">${B_.dados.indices.map(n => `<option ${m.indice === n ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>
    <label>Custo t·km pavimentada (R$) <input id="bmCp" type="number" step="any" value="${m.custo_pav ?? ""}" data-dica="Custo do transporte por t·km em rodovia pavimentada (composição de transporte SICRO)"></label>
    <label>Custo t·km não pavimentada (R$) <input id="bmCn" type="number" step="any" value="${m.custo_npav ?? ""}" data-dica="Custo do transporte por t·km em rodovia não pavimentada"></label>
    <label>Densidade padrão (t/m³) <input id="bmDens" type="number" step="any" value="${m.densidade ?? ""}" data-dica="Usada quando a cotação não informa a densidade"></label></div>
    <h4>Cotações</h4><div class="tabela-rolagem"><table class="tab" id="tabCot"><tr><th>Fornecedor</th><th>SICRO</th><th>Preço</th><th>Unid.</th><th>Dens.</th><th>Mês</th><th>DMT pav.</th><th>DMT não pav.</th><th>Local/jazida</th><th></th></tr>
    ${(m.cotacoes || []).map(linha).join("")}</table></div>
    <div class="linha-botoes"><button class="btn mini" type="button" id="bmAdd" data-dica="Acrescenta uma cotação">+ Cotação</button></div>
    <div class="linha-botoes"><button class="btn primario" id="bmSalvar" data-dica="Grava e recalcula o binômio">Salvar</button><button class="btn" id="bmFechar">Fechar</button></div></div>`;
  ligarRemover();
  $("#bmAdd").onclick = () => { $("#tabCot").insertAdjacentHTML("beforeend", linha({})); ligarRemover(); };
  $("#bmFechar").onclick = () => ed.hidden = true;
  $("#bmSalvar").onclick = async () => {
    const cotacoes = $$("#tabCot tr[data-cot]").map(tr => Object.fromEntries($$("[data-c]", tr).map(i => [i.dataset.c, i.type === "checkbox" ? i.checked : i.value])));
    const dados = { id: m.id, nome: $("#bmNome").value, codigo: $("#bmCod").value, grupo: $("#bmGrupo").value, indice: $("#bmInd").value,
      custo_pav: $("#bmCp").value, custo_npav: $("#bmCn").value, densidade: $("#bmDens").value, cotacoes };
    try { await jpost(`${base_}${E.pid}/binomio/material`, dados); toast("Binômio gravado"); ed.hidden = true; renderBinomio(); } catch (e) { erro(e); }
  };
  ed.scrollIntoView({ behavior: "smooth" });
}
function editorBetuminoso(p) {
  p = p || { produto: "", indice: "Pavimentação", pis: 0.0065, cofins: 0.03, bdi_transporte: 0.15, ton_viagem: 60, fluvial_sempre: true, origens: [{ nome: "R-1" }, { nome: "R-2" }, { nome: "R-3" }] };
  const ed = $("#editorBin"); ed.hidden = false;
  const linha = o => `<tr data-ori><td>${inp("nome", o.nome, "text", 50)}</td><td>${inp("uf", o.uf, "text", 40)}</td><td>${inp("local", o.local, "text", 130)}</td>
    <td>${inp("preco_t", o.preco_t, "number", 90, 'data-dica="Preço ANP sem ICMS (R$/t)"')}</td><td>${inp("icms", o.icms != null ? +(o.icms * 100).toFixed(4) : "", "number", 60, 'data-dica="Alíquota de ICMS da operação (%)"')}</td>
    <td>${inp("d_fluvial", o.d_fluvial, "number", 60)}</td><td>${inp("d_pav", o.d_pav, "number", 60)}</td><td>${inp("d_rp", o.d_rp, "number", 60)}</td><td>${inp("d_ln", o.d_ln, "number", 60)}</td>
    <td>${inp("pedagio", o.pedagio, "number", 70, 'data-dica="Pedágio por viagem (R$) — dividido pela carga do caminhão"')}</td><td>${inp("balsa", o.balsa, "number", 70)}</td>
    <td><button class="btn mini perigo" type="button" data-rmlin data-dica="Remove a origem">×</button></td></tr>`;
  const pc = v => v == null ? "" : +(v * 100).toFixed(4);
  ed.innerHTML = `<h3>${p.id ? "Editar" : "Novo"} material betuminoso</h3><div class="form"><div class="campos">
    <label>Produto <input id="bpProd" value="${esc(p.produto)}" data-dica="Ex.: CAP 50/70, Emulsão RR-1C"></label>
    <label>Código SICRO <input id="bpCod" value="${esc(p.codigo || "")}" data-dica="Insumo da base que recebe o preço vencedor (aquisição com ICMS)"></label>
    <label>Índice <select id="bpInd">${B_.dados.indices.map(n => `<option ${p.indice === n ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>
    <label>PIS (%) <input id="bpPis" type="number" step="any" value="${pc(p.pis)}"></label><label>COFINS (%) <input id="bpCof" type="number" step="any" value="${pc(p.cofins)}"></label>
    <label>BDI aquisição (%) <input id="bpBdi" type="number" step="any" value="${p.bdi_projeto || p.bdi == null ? "" : pc(p.bdi)}" placeholder="do projeto" data-dica="Em branco: usa o BDI do projeto (aba Base e BDI)"></label>
    <label>BDI transporte (%) <input id="bpBdiT" type="number" step="any" value="${pc(p.bdi_transporte)}" data-dica="Portaria DNIT: 15% sobre o transporte de betuminosos"></label>
    <label>Carga por viagem (t) <input id="bpTon" type="number" step="any" value="${p.ton_viagem ?? 60}" data-dica="Divide o pedágio e a balsa por viagem"></label>
    <label class="check"><input id="bpFlu" type="checkbox" ${p.fluvial_sempre ? "checked" : ""} data-dica="A planilha de referência soma a parcela fixa do fluvial (20,7256) mesmo sem trecho fluvial"> somar a parcela fixa do fluvial sempre</label></div>
    <h4>Origens (distribuidoras / refinarias)</h4><div class="tabela-rolagem"><table class="tab" id="tabOri"><tr><th>Origem</th><th>UF</th><th>Local</th><th>ANP R$/t</th><th>ICMS %</th><th>Fluvial</th><th>Pav.</th><th>RP</th><th>LN</th><th>Pedágio</th><th>Balsa</th><th></th></tr>
    ${(p.origens || []).map(linha).join("")}</table></div>
    <div class="linha-botoes"><button class="btn mini" type="button" id="bpAdd" data-dica="Acrescenta uma origem">+ Origem</button></div>
    <div class="linha-botoes"><button class="btn primario" id="bpSalvar" data-dica="Grava e recalcula o binômio">Salvar</button><button class="btn" id="bpFechar">Fechar</button></div></div>`;
  ligarRemover();
  $("#bpAdd").onclick = () => { $("#tabOri").insertAdjacentHTML("beforeend", linha({ nome: `R-${$$("#tabOri tr[data-ori]").length + 1}` })); ligarRemover(); };
  $("#bpFechar").onclick = () => ed.hidden = true;
  $("#bpSalvar").onclick = async () => {
    const origens = $$("#tabOri tr[data-ori]").map(tr => Object.fromEntries($$("[data-c]", tr).map(i => [i.dataset.c, i.value])));
    const dados = { id: p.id, produto: $("#bpProd").value, codigo: $("#bpCod").value, indice: $("#bpInd").value, pis: $("#bpPis").value, cofins: $("#bpCof").value,
      bdi: $("#bpBdi").value, bdi_transporte: $("#bpBdiT").value, ton_viagem: $("#bpTon").value, fluvial_sempre: $("#bpFlu").checked, origens };
    try { await jpost(`${base_}${E.pid}/binomio/betuminoso`, dados); toast("Binômio gravado"); ed.hidden = true; renderBinomio(); } catch (e) { erro(e); }
  };
  ed.scrollIntoView({ behavior: "smooth" });
}
$("#btnNovoMat").onclick = () => editorMaterial(null);
$("#btnCotPdf").onclick = () => cotacaoPdf(null);
$("#btnForn").onclick = () => { const p = $("#painelForn"); if (!p.hidden) { p.hidden = true; return; } renderForn().catch(erro); };
$("#btnNovoBet").onclick = () => editorBetuminoso(null);
$("#btnAnexoGeral").onclick = () => { const t = prompt("Tipo do documento: icms, anp, cotacao ou outro", "icms"); if (t) enviarAnexo(null, t.trim().toLowerCase(), ""); };
$("#btnImpBin").onclick = async () => {
  const arq = await escolherArquivo(".xlsx,.xlsm"); if (!arq) return;
  const subst = confirm("Substituir os binômios já cadastrados neste projeto?\n(OK = substituir · Cancelar = acrescentar)");
  const fd = new FormData(); fd.append("arquivo", arq); fd.append("substituir", subst);
  $("#resBin").innerHTML = `<p class="carregando">Lendo o binômio da planilha…</p>`;
  try { const r = await api(`${base_}${E.pid}/binomio/importar`, { method: "POST", body: fd });
    $("#resBin").innerHTML = `<p class="ok-msg">Importado: ${r.importados.materiais} materiais cotados e ${r.importados.produtos} betuminosos (e os índices de reajuste da planilha).</p>`; renderBinomio();
  } catch (e) { $("#resBin").innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; }
};
$("#btnExpBin").onclick = async () => {
  try { const r = await jpost(`${base_}${E.pid}/exportar/binomio`, {}); $("#resBin").innerHTML = `<div class="linha-botoes">${linkBaixar(r)}</div>`; } catch (e) { erro(e); }
};
$("#btnIndices").onclick = () => { const p = $("#painelIndices"); p.hidden = !p.hidden; if (!p.hidden) renderIndices(); };
async function renderIndices() {
  const r = await api("/api/indices"), p = $("#painelIndices");
  B_.serie = B_.serie && r.series[B_.serie] ? B_.serie : r.padrao.petreos;
  const s = r.series[B_.serie] || {};
  p.innerHTML = `<h3>Índices de reajustamento (DNIT)</h3><p class="nota">Usados para reajustar as cotações até a data-base (Conservação Rodoviária para pétreos) e para Kr/Kf dos betuminosos (Pavimentação).
    Digite o índice do mês quando o DNIT publicar, ou importe a aba de índices de uma planilha.</p>
    <div class="barra filtros"><label>Índice <select id="selSerie">${r.nomes.map(n => `<option ${n === B_.serie ? "selected" : ""}>${esc(n)}</option>`).join("")}</select></label>
    <label>Mês <input type="month" id="indMes"></label><label>Valor <input type="number" step="any" id="indVal" style="width:100px"></label>
    <button class="btn" id="btnGravaInd" data-dica="Grava (ou corrige) o índice do mês">Gravar</button>
    <button class="btn" id="btnImpInd" data-dica="Lê a publicação mensal do DNIT 'Índices de Reajustamento de Obras Rodoviárias' (PDF) ou a aba INDICES_REAJ de uma planilha; meses novos são acrescentados">Importar publicação (PDF) ou planilha</button></div>
    <div class="tabela-rolagem" style="max-height:260px"><table class="tab"><tr><th>Mês</th><th class=n>Valor</th></tr>
    ${Object.keys(s).sort().reverse().map(m => `<tr><td>${esc(m)}</td><td class=n>${nf(s[m], 3)}</td></tr>`).join("")}</table></div>`;
  $("#selSerie").onchange = e => { B_.serie = e.target.value; renderIndices(); };
  $("#btnGravaInd").onclick = async () => { try { await jpost("/api/indices", { nome: B_.serie, mes: $("#indMes").value, valor: $("#indVal").value }, "PUT"); toast("Índice gravado"); renderIndices(); renderBinomio(); } catch (e) { erro(e); } };
  $("#btnImpInd").onclick = async () => { const a = await escolherArquivo(".pdf,.xlsx,.xlsm"); if (!a) return; const fd = new FormData(); fd.append("arquivo", a);
    try { const x = await api("/api/indices/importar", { method: "POST", body: fd }); toast(`${x.gravados} índices gravados`); renderIndices(); renderBinomio(); } catch (e) { erro(e); } };
}

// ---- data-base
async function renderDataBase() {
  const c = C_.cfg;
  $("#selNovaBase").innerHTML = c.disponiveis.filter(d => !(d.uf === c.uf && d.data_base === c.data_base))
    .map(d => `<option value="${d.uf}|${d.data_base}">${d.uf} — ${d.data_base}</option>`).join("") || '<option value="">(importe outra base em “Base e BDI”)</option>';
  $("#tabComparar").innerHTML = "";
}
$("#btnComparar").onclick = async () => {
  const v = $("#selNovaBase").value; if (!v) return toast("Importe outra base primeiro (Base e BDI).");
  const [uf, data_base] = v.split("|");
  const r = await api(`${base_}${E.pid}/custos/comparar?uf=${uf}&data_base=${data_base}`);
  const vv = x => x == null ? "—" : `<span class="${x > 0 ? "var-pos" : "var-neg"}">${x > 0 ? "+" : ""}${x.toFixed(2)}%</span>`;
  $("#tabComparar").innerHTML = `<tr><th>Código</th><th>Serviço</th><th class=n>Atual SD</th><th class=n>Nova SD</th><th class=n>Var.</th><th class=n>Atual CD</th><th class=n>Nova CD</th><th class=n>Var.</th></tr>` +
    r.servicos.map(s => `<tr><td>${esc(s.codigo)}</td><td>${esc(s.descricao || "")}</td><td class=n>${reais(s.atual_SD)}</td><td class=n>${reais(s.novo_SD)}</td><td class=n>${vv(s.var_SD)}</td>
      <td class=n>${reais(s.atual_CD)}</td><td class=n>${reais(s.novo_CD)}</td><td class=n>${vv(s.var_CD)}</td></tr>`).join("");
};
$("#btnAdotarBase").onclick = async () => {
  const v = $("#selNovaBase").value; if (!v) return;
  const [uf, data_base] = v.split("|");
  if (!confirm(`Passar o projeto para a base ${uf} ${data_base}?`)) return;
  await jpost(`${base_}${E.pid}/custos/config`, { uf, data_base }, "PUT"); toast("Data-base alterada"); C_.sub = "servicos"; carregarCustos();
};

// ---------------------------------------------------------------- transporte
const T_ = { sub: "croqui", cro: null, q: null };
const km3 = v => v == null || v === "" ? "—" : Number(v).toLocaleString("pt-BR", { minimumFractionDigits: 3, maximumFractionDigits: 3 });
async function carregarTransp() {
  if (!E.pid) return;
  const subs = [["croqui", "Croqui", "Desenho do segmento com as ocorrências e travessias urbanas"], ["vmd", "VMD", "Volume médio diário por segmento (modelagem DNIT)"],
    ["dmt", "DMT e FIT", "Distâncias médias de transporte e fator de interferência de tráfego por rota"], ["quadro", "Quadro de transportes", "Momentos de transporte por serviço e material"]];
  $("#chipsTransp").innerHTML = subs.map(([k, r, d]) => `<span class="chip ${T_.sub === k ? "ativo" : ""}" data-sub="${k}" data-dica="${d}">${r}</span>`).join("");
  $$("#chipsTransp .chip").forEach(ch => ch.onclick = () => { T_.sub = ch.dataset.sub; carregarTransp(); });
  $$(".sub-transp").forEach(el => el.classList.toggle("ativa", el.id === "trp-" + T_.sub));
  try {
    T_.cro = await api(`${base_}${E.pid}/croqui`);
    const d = T_.cro.dados, nOc = d.ocorrencias.filter(o => o.km !== null && o.km !== "" && o.km !== undefined).length;
    const fits = T_.cro.rotas.filter(r => r.fit !== 1);
    $("#cabTransp").innerHTML = `<div class="it">Segmento<br><b>km ${nf(T_.cro.km_ini, 3)} ao ${nf(T_.cro.km_fim, 3)}</b></div>
      <div class="it">Ocorrências no croqui<br><b>${nOc} com km · ${d.ocorrencias.length - nOc} com distância fixa</b></div>
      <div class="it">Travessias urbanas<br><b>${d.travessias.length}</b></div><div class="it">Segmentos com VMD<br><b>${d.vmd.filter(s => s.vmda != null || s.vmdf_c != null).length} de ${d.vmd.length}</b></div>
      <div class="it">Rotas com FIT<br><b>${fits.length}</b></div>`;
    await ({ croqui: renderCroqui, vmd: renderVmd, dmt: renderRotas, quadro: renderQuadro })[T_.sub]();
  } catch (e) { erro(e); }
}

// ---- croqui
const COR_TIPO = { canteiro: "#1f4e79", pedreira: "#7f6000", areal: "#c55a11", usina: "#7030a0", deposito: "#3b6ea8", bota_fora: "#595959",
  emprestimo: "#548235", aterro: "#843c0c", cidade: "#000", outro: "#2e75b6" };
function svgCroqui(c) {
  const d = c.dados, a = +c.km_ini, b = +c.km_fim, W = 1200, x0 = 80, x1 = W - 80;
  const X = k => x0 + (Math.min(Math.max(+k, a), b) - a) / ((b - a) || 1) * (x1 - x0);
  const e = s => esc(s);
  // ocorrências: acima (E) / abaixo (D), em níveis para não sobrepor
  const ocs = (d.ocorrencias || []).filter(o => o.km !== "" && o.km != null).sort((p, q) => p.km - q.km);
  const ult = { E: [], D: [] }, pos = [];
  ocs.forEach(o => {
    const lado = (o.lado || "E").toUpperCase().startsWith("D") ? "D" : "E", x = X(o.km);
    let n = 0; while (ult[lado][n] != null && x - ult[lado][n] < 160) n++;
    ult[lado][n] = x; pos.push({ o, lado, n, x });
  });
  const nE = Math.max(1, ult.E.length), nD = ult.D.length, Y = 110 + nE * 54, YD = Y + 128;
  const H = YD + nD * 54 + 50;
  let linhas = "", caixas = "";
  let g = `<rect x="0" y="0" width="${W}" height="${H}" fill="#fff"/>`;
  g += `<text x="${W / 2}" y="28" text-anchor="middle" font-size="17" font-weight="700" fill="#1b2430">CROQUI DE OCORRÊNCIA DE MATERIAIS E DMT's</text>`;
  g += `<text x="${W / 2}" y="48" text-anchor="middle" font-size="12" fill="#5b6675">${e((E.resumo?.projeto?.rodovia || "") + " — segmento km " + nf(a, 3) + " ao km " + nf(b, 3))}</text>`;
  (d.vmd || []).forEach((s, i) => {
    const xa = X(s.km_ini), xb = X(s.km_fim), y = Y + 84;
    g += `<line x1="${xa}" y1="${Y + 10}" x2="${xa}" y2="${y + 20}" stroke="#bbb" stroke-dasharray="3 3"/>`;
    const f = s.faixas_sentido || 1;
    const vc = s.vmdf_c ?? (s.vmda_c != null ? s.vmda_c / f : s.vmda != null ? s.vmda / 2 / f : null);
    const vd = s.vmdf_d ?? (s.vmda_d != null ? s.vmda_d / f : s.vmda != null ? s.vmda / 2 / f : null);
    g += `<text x="${(xa + xb) / 2}" y="${y}" text-anchor="middle" font-size="11" fill="#3b6ea8">${e(s.snv || "Seg. " + (s.segmento || i + 1))}</text>`;
    if (vc != null || vd != null) g += `<text x="${(xa + xb) / 2}" y="${y + 15}" text-anchor="middle" font-size="11" fill="#3b6ea8">VMDf ${vc != null ? Math.round(vc) : "—"} → / ← ${vd != null ? Math.round(vd) : "—"}</text>`;
  });
  g += `<line x1="${x0}" y1="${Y}" x2="${x1}" y2="${Y}" stroke="#595959" stroke-width="10" stroke-linecap="round"/>`;
  (d.travessias || []).forEach(t => {
    const xa = X(t.km_ini), xb = X(t.km_fim);
    g += `<rect x="${xa}" y="${Y - 9}" width="${Math.max(3, xb - xa)}" height="18" fill="#f4b183"/>`;
    g += `<text x="${(xa + xb) / 2}" y="${Y + 44}" text-anchor="middle" font-size="10" fill="#843c0c">TRAVESSIA URBANA</text>`;
    g += `<text x="${(xa + xb) / 2}" y="${Y + 57}" text-anchor="middle" font-size="10.5" font-weight="700" fill="#843c0c">${e(t.nome || "")}</text>`;
  });
  g += `<line x1="${x0}" y1="${Y}" x2="${x1}" y2="${Y}" stroke="#fff" stroke-width="1.5" stroke-dasharray="14 10"/>`;
  const passo = [1, 2, 5, 10, 20, 25, 50, 100].find(p => (b - a) / p <= 12) || 100;
  for (let k = Math.ceil(a / passo) * passo; k <= b; k += passo) g += `<line x1="${X(k)}" y1="${Y + 7}" x2="${X(k)}" y2="${Y + 14}" stroke="#333"/><text x="${X(k)}" y="${Y + 26}" text-anchor="middle" font-size="9.5" fill="#555">${k}</text>`;
  g += `<text x="${x0}" y="${Y - 30}" text-anchor="middle" font-size="11" font-weight="700">INÍCIO</text><text x="${x0}" y="${Y - 16}" text-anchor="middle" font-size="10.5">km ${nf(a, 3)}</text>`;
  g += `<text x="${x1}" y="${Y - 30}" text-anchor="middle" font-size="11" font-weight="700">FIM</text><text x="${x1}" y="${Y - 16}" text-anchor="middle" font-size="10.5">km ${nf(b, 3)}</text>`;
  (d.localidades || []).filter(l => l.km !== "" && l.km != null).forEach(l => {
    g += `<text x="${X(l.km)}" y="${Y + 70}" text-anchor="middle" font-size="11" font-weight="700">${e(l.nome)}</text>`;
  });
  pos.forEach(({ o, lado, n, x }) => {
    const y = lado === "E" ? Y - 64 - n * 54 : YD + n * 54, cor = COR_TIPO[o.tipo] || "#2e75b6";
    const ac = ["ln", "rp", "p"].map(k => +o["acesso_" + k] ? `${k.toUpperCase()} ${nf(+o["acesso_" + k], 2)} km` : "").filter(Boolean).join(" · ");
    linhas += `<line x1="${x}" y1="${Y}" x2="${x}" y2="${y}" stroke="${cor}" stroke-width="1.5" ${ac ? 'stroke-dasharray="5 3"' : ""}/>`;
    const h = ac ? 44 : 34;
    caixas += `<rect x="${x - 74}" y="${y - h / 2}" width="148" height="${h}" rx="6" fill="#fff" stroke="${cor}" stroke-width="1.5"/>`;
    caixas += `<text x="${x}" y="${y - h / 2 + 15}" text-anchor="middle" font-size="11.5" font-weight="700" fill="${cor}">${e(o.nome)}</text>`;
    caixas += `<text x="${x}" y="${y - h / 2 + 28}" text-anchor="middle" font-size="10" fill="#333">km ${nf(+o.km, 3)}</text>`;
    if (ac) caixas += `<text x="${x}" y="${y - h / 2 + 39}" text-anchor="middle" font-size="9.5" fill="#555">acesso ${e(ac)}</text>`;
    caixas += `<circle cx="${x}" cy="${Y}" r="6" fill="${cor}" stroke="#fff" stroke-width="2"/>`;
  });
  g += linhas + caixas;
  const fixas = (d.ocorrencias || []).filter(o => o.km === "" || o.km == null);
  if (fixas.length) {
    g += `<text x="${x0}" y="${H - 18}" font-size="11" fill="#333"><tspan font-weight="700">Distância fixa até a pista: </tspan>${e(fixas.map(o => {
      const p = o.meia_extensao ? (b - a) / 2 : +o.dist_p || 0;
      return `${o.nome} (${["LN " + nf(+o.dist_ln || 0, 2), "RP " + nf(+o.dist_rp || 0, 2), "P " + nf(p, 2)].filter(x => !x.endsWith(" 0")).join(", ") || "0"} km)`;
    }).join(" · "))}</text>`;
  }
  return `<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 ${W} ${H}" font-family="Segoe UI, Arial, sans-serif">${g}</svg>`;
}
const SEL_TIPO = v => `<select data-c="tipo">${Object.entries(T_.cro.tipos).map(([k, r]) => `<option value="${k}" ${v === k ? "selected" : ""}>${esc(r)}</option>`).join("")}</select>`;
const ci = (k, v, t = "text", extra = "") => `<input data-c="${k}" type="${t}" ${t === "number" ? 'step="any"' : ""} value="${esc(v ?? "")}" ${extra}>`;
function linhaOcorr(o) {
  return `<tr data-oc><td>${ci("nome", o.nome)}</td><td>${SEL_TIPO(o.tipo)}</td><td>${ci("km", o.km, "number", 'data-dica="km na rodovia; em branco = ocorrência fora do segmento com distância fixa"')}</td>
    <td><select data-c="lado"><option value="E" ${(o.lado || "E") === "E" ? "selected" : ""}>E</option><option value="D" ${o.lado === "D" ? "selected" : ""}>D</option></select></td>
    <td>${ci("acesso_ln", o.acesso_ln, "number")}</td><td>${ci("acesso_rp", o.acesso_rp, "number")}</td><td>${ci("acesso_p", o.acesso_p, "number")}</td>
    <td>${ci("dist_ln", o.dist_ln, "number")}</td><td>${ci("dist_rp", o.dist_rp, "number")}</td><td>${ci("dist_p", o.dist_p, "number")}</td>
    <td style="text-align:center"><input data-c="meia_extensao" type="checkbox" ${o.meia_extensao ? "checked" : ""} data-dica="P = metade da extensão do segmento (ex.: aterro sanitário, recolhimento ao longo do trecho)"></td>
    <td>${ci("obs", o.obs)}</td><td><button class="btn mini perigo" type="button" data-rmlin data-dica="Remove a ocorrência">×</button></td></tr>`;
}
const lerTab = sel => $$(sel).map(tr => Object.fromEntries($$("[data-c]", tr).map(i => [i.dataset.c, i.type === "checkbox" ? i.checked : (i.type === "number" ? (i.value === "" ? null : +i.value) : i.value)])));
async function renderCroqui() {
  const c = T_.cro, d = c.dados;
  $("#croquiSvg").innerHTML = svgCroqui(c);
  if (d.automatico) { $("#crqKmCant").value = d.automatico.km_canteiro ?? ""; $("#crqKmUsina").value = d.automatico.km_usina ?? ""; }
  const om = d.origem_material || {};
  $("#crqNotas").innerHTML = (Object.keys(om).length ? `<p class="nota"><b>Origem dos materiais (binômio):</b> ${Object.entries(om).map(([m, o]) => `${esc(m.toLowerCase())} → ${esc(o)}`).join(" · ")}</p>`
      : d.automatico ? '<p class="tag aviso">Sem materiais no binômio: os materiais saem do centro sede (preço SICRO). Cadastre as cotações para comparar.</p>' : "") +
    ((d.automatico?.notas || []).length ? `<ul class="nota">${d.automatico.notas.map(n => `<li>${esc(n)}</li>`).join("")}</ul>` : "");
  $("#tabOcorr").innerHTML = `<tr><th>Nome</th><th>Tipo</th><th>km</th><th>Lado</th><th colspan=3 data-dica="Distância do acesso entre a rodovia e a ocorrência">Acesso LN / RP / P (km)</th>
    <th colspan=3 data-dica="Para ocorrências sem km: distância fixa até a pista (ex.: bota-fora a 5 km)">Distância fixa LN / RP / P (km)</th><th>½ ext.</th><th>Obs.</th><th></th></tr>` + d.ocorrencias.map(linhaOcorr).join("");
  $("#tabTrav").innerHTML = `<tr><th>Nome</th><th>km inicial</th><th>km final</th><th></th></tr>` + d.travessias.map(t => `<tr data-tv><td>${ci("nome", t.nome)}</td><td>${ci("km_ini", t.km_ini, "number")}</td><td>${ci("km_fim", t.km_fim, "number")}</td><td><button class="btn mini perigo" type="button" data-rmlin>×</button></td></tr>`).join("");
  $("#tabLocal").innerHTML = `<tr><th>Nome</th><th>km</th><th></th></tr>` + (d.localidades || []).map(l => `<tr data-lc><td>${ci("nome", l.nome)}</td><td>${ci("km", l.km, "number")}</td><td><button class="btn mini perigo" type="button" data-rmlin>×</button></td></tr>`).join("");
  $("#crMetodo").value = d.metodo || "referencia"; $("#crFitMax").value = d.fit_dmt_max ?? 100;
  $("#crPareSiga").value = d.pare_siga || "auto"; $("#crVelUrb").value = d.vel_urbana ?? 30;
  $("#crKmIni").value = d.km_ini ?? ""; $("#crKmFim").value = d.km_fim ?? "";
  ligarRemover();
}
$("#btnAddOcorr").onclick = () => { $("#tabOcorr").insertAdjacentHTML("beforeend", linhaOcorr({ tipo: "pedreira", lado: "E" })); ligarRemover(); };
$("#btnAddTrav").onclick = () => { $("#tabTrav").insertAdjacentHTML("beforeend", `<tr data-tv><td>${ci("nome", "")}</td><td>${ci("km_ini", "", "number")}</td><td>${ci("km_fim", "", "number")}</td><td><button class="btn mini perigo" type="button" data-rmlin>×</button></td></tr>`); ligarRemover(); };
$("#btnAddLocal").onclick = () => { $("#tabLocal").insertAdjacentHTML("beforeend", `<tr data-lc><td>${ci("nome", "")}</td><td>${ci("km", "", "number")}</td><td><button class="btn mini perigo" type="button" data-rmlin>×</button></td></tr>`); ligarRemover(); };
$("#btnSalvarCroqui").onclick = async () => {
  const dados = { ocorrencias: lerTab("#tabOcorr tr[data-oc]").filter(o => o.nome), travessias: lerTab("#tabTrav tr[data-tv]").filter(t => t.km_ini != null && t.km_fim != null),
    localidades: lerTab("#tabLocal tr[data-lc]").filter(l => l.nome), metodo: $("#crMetodo").value, fit_dmt_max: +$("#crFitMax").value || 100,
    pare_siga: $("#crPareSiga").value, vel_urbana: +$("#crVelUrb").value || 30,
    km_ini: $("#crKmIni").value === "" ? null : +$("#crKmIni").value, km_fim: $("#crKmFim").value === "" ? null : +$("#crKmFim").value };
  try { await jpost(`${base_}${E.pid}/croqui`, dados, "PUT"); toast("Croqui salvo — DMT e FIT recalculados"); carregarTransp(); } catch (e) { erro(e); }
};
$("#btnSvgCroqui").onclick = () => {
  const blob = new Blob([svgCroqui(T_.cro)], { type: "image/svg+xml" }), a = document.createElement("a");
  a.href = URL.createObjectURL(blob); a.download = "croqui.svg"; a.click(); setTimeout(() => URL.revokeObjectURL(a.href), 2000);
};

// ---- VMD
function linhaSeg(s) {
  return `<tr data-sg><td>${ci("segmento", s.segmento)}</td><td>${ci("snv", s.snv)}</td><td>${ci("km_ini", s.km_ini, "number")}</td><td>${ci("km_fim", s.km_fim, "number")}</td>
    <td>${ci("vmda", s.vmda, "number", 'data-dica="VMDa total (dois sentidos)"')}</td><td>${ci("vmda_c", s.vmda_c, "number")}</td><td>${ci("vmda_d", s.vmda_d, "number")}</td>
    <td>${ci("faixas_sentido", s.faixas_sentido ?? 1, "number", 'data-dica="Faixas por sentido (pista simples = 1)"')}</td>
    <td>${ci("vmdf_c", s.vmdf_c, "number", 'data-dica="VMD por faixa no sentido crescente (se informado, prevalece)"')}</td><td>${ci("vmdf_d", s.vmdf_d, "number")}</td>
    <td>${ci("ano", s.ano)}</td><td><small>${esc(s.fonte || "")}</small><input data-c="fonte" type="hidden" value="${esc(s.fonte || "")}"></td><td><button class="btn mini perigo" type="button" data-rmlin>×</button></td></tr>`;
}
async function renderVmd() {
  $("#lnkVmd").href = T_.cro.fonte_vmd;
  $("#tabVmd").innerHTML = `<tr><th>Seg.</th><th>SNV</th><th>km inicial</th><th>km final</th><th>VMDa</th><th>VMDa cresc.</th><th>VMDa decresc.</th><th>Faixas/sentido</th><th>VMDf cresc.</th><th>VMDf decresc.</th><th>Ano</th><th>Fonte</th><th></th></tr>` +
    T_.cro.dados.vmd.map(linhaSeg).join("");
  ligarRemover();
}
$("#btnAddSeg").onclick = () => { $("#tabVmd").insertAdjacentHTML("beforeend", linhaSeg({ faixas_sentido: 1, fonte: "manual" })); ligarRemover(); };
$("#btnSalvarVmd").onclick = async () => {
  try { await jpost(`${base_}${E.pid}/croqui`, { vmd: lerTab("#tabVmd tr[data-sg]").filter(s => s.km_ini != null) }, "PUT"); toast("VMD salvo"); carregarTransp(); } catch (e) { erro(e); }
};
$("#btnImpVmd").onclick = async () => {
  const a = await escolherArquivo(".xlsx,.xls,.csv,.txt,.geojson,.json"); if (!a) return;
  const fd = new FormData(); fd.append("arquivo", a);
  try { const r = await api(`${base_}${E.pid}/croqui/vmd`, { method: "POST", body: fd });
    $("#resTransp").innerHTML = `<p class="ok-msg">VMD importado: ${r.segmentos} segmentos (${r.casados} subtrechos de ${r.lidos} registros do arquivo).</p>` +
      (r.lacunas.length ? `<p class="tag aviso">Sem VMD no arquivo: ${r.lacunas.map(l => `km ${nf(l.km_ini, 3)} a ${nf(l.km_fim, 3)}`).join(" · ")} — o FIT usa o segmento vizinho; confira ou digite o VMD.</p>` : "");
    carregarTransp(); } catch (e) { erro(e); }
};

// ---- DMT e FIT
async function renderRotas() {
  $("#notaPareSiga").innerHTML = T_.cro.pare_siga ? "<b>A1 considerado</b> (operação PARE e SIGA " + (T_.cro.pare_siga_previsto ? "prevista no orçamento" : "marcada no croqui") + ")."
    : "<b>A1 = 0</b>: o orçamento não prevê a operação PARE e SIGA (5213850).";
  const man = new Set((T_.cro.dados.rotas_manuais || []).map(r => `${r.origem}|${r.destino}`));
  $("#tabRotas").innerHTML = `<tr><th>Origem</th><th>Destino</th><th class=n>LN</th><th class=n>RP</th><th class=n>P</th><th class=n>Pr</th><th class=n>Pu</th><th class=n>DMT</th><th>Sentido</th><th class=n>VMDf</th><th class=n>A1 (s)</th><th class=n>A2 (s)</th><th class=n>FIT</th><th>Cálculo</th><th></th></tr>` +
    (T_.cro.rotas.map(r => { const m = man.has(`${r.origem}|${r.destino}`);
      return `<tr><td>${esc(r.origem)}</td><td>${esc(r.destino)}</td><td class="n">${km3(r.ln)}</td><td class="n">${km3(r.rp)}</td><td class="n ${m ? "manual" : ""}">${km3(r.p)}</td><td class=n>${km3(r.pr)}</td><td class=n>${km3(r.pu)}</td>
      <td class=n><b>${km3(r.dmt)}</b></td><td>${esc(r.sentido || "")}</td><td class=n>${r.vmdf ?? "—"}</td><td class=n>${r.a1 != null ? nf(r.a1, 3) : ""}</td><td class=n>${r.a2 != null ? nf(r.a2, 3) : ""}</td>
      <td class=n><b>${nf(r.fit, 4)}</b></td><td><small>${esc(r.metodo)}</small>${r.erro ? `<br><span class="tag erro">${esc(r.erro)}</span>` : ""}${r.aviso ? `<br><span class="tag aviso">${esc(r.aviso)}</span>` : ""}</td>
      <td><button class="btn mini" data-rman="${esc(r.origem)}|${esc(r.destino)}" data-dica="Informa as distâncias medidas desta rota (prevalecem sobre o cálculo)">Informar</button>
      ${m ? `<button class="btn mini perigo" data-rdes="${esc(r.origem)}|${esc(r.destino)}" data-dica="Volta ao cálculo pelo croqui">Calcular</button>` : ""}</td></tr>`; }).join("")
    || '<tr><td colspan=15 class="nota">Cadastre as ocorrências no croqui.</td></tr>');
  $$("[data-rman]").forEach(b => b.onclick = () => {
    const [origem, destino] = b.dataset.rman.split("|");
    dialogo(`Distâncias ${origem} → ${destino}`, [["ln", "LN (km)", "number"], ["rp", "RP (km)", "number"], ["p", "P total (km)", "number"], ["pu", "Pu — parte urbana (km)", "number"], ["vmdf", "VMDf (para o FIT)", "number"]],
      async v => { const lst = (T_.cro.dados.rotas_manuais || []).filter(r => !(r.origem === origem && r.destino === destino));
        lst.push({ origem, destino, ...Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x === "" ? null : +x])), aplicar_fit: v.vmdf !== "" });
        await jpost(`${base_}${E.pid}/croqui`, { rotas_manuais: lst }, "PUT"); toast("Rota informada"); carregarTransp(); });
  });
  $$("[data-rdes]").forEach(b => b.onclick = async () => { const [o, d] = b.dataset.rdes.split("|");
    await jpost(`${base_}${E.pid}/croqui`, { rotas_manuais: (T_.cro.dados.rotas_manuais || []).filter(r => !(r.origem === o && r.destino === d)) }, "PUT"); carregarTransp(); });
}

// ---- quadro
async function renderQuadro() {
  const q = T_.q = await api(`${base_}${E.pid}/transportes`);
  const selLocal = (v, k) => `<select data-k="${k}"><option value="">${k === "origem" ? "(CIF — sem transporte)" : "—"}</option>${q.locais.map(l => `<option ${l === v ? "selected" : ""}>${esc(l)}</option>`).join("")}${v && !q.locais.includes(v) ? `<option selected>${esc(v)}</option>` : ""}</select>`;
  $("#avisoQuadro").innerHTML = (q.sem_quantidade.length ? `<p class="tag aviso">Serviços sem quantidade anual (momento zero): ${q.sem_quantidade.slice(0, 12).map(esc).join(", ")}${q.sem_quantidade.length > 12 ? "…" : ""} — informe em Custos → Serviços.</p>` : "")
    + (q.linhas.some(l => l.erro) ? `<p class="tag erro">Há linhas com local que não está no croqui: cadastre a ocorrência ou ajuste a origem.</p>` : "");
  $("#tabTotTransp").innerHTML = `<tr><th>Código</th><th>Serviço de transporte</th><th class=n>Momento (t·km)</th><th class=n>Linhas</th><th>No orçamento</th></tr>` +
    (q.totais.map(t => `<tr><td>${esc(t.codigo)}</td><td>${esc(t.descricao || "")}</td><td class=n><b>${nf(t.momento, 3)}</b></td><td class=n>${t.linhas}</td>
      <td>${t.no_orcamento ? (Math.abs((t.quantidade_orcamento || 0) - t.momento) < 0.001 ? '<span class="tag ok">aplicado</span>' : `<span class="tag aviso">orçamento: ${nf(t.quantidade_orcamento, 3)}</span>`) : '<span class="tag">não</span>'}</td></tr>`).join("")
     || '<tr><td colspan=5 class="nota">Sem momentos: gere o quadro das composições ou importe de uma planilha PATO.</td></tr>');
  $("#tabOrigens").innerHTML = `<tr><th>Material</th><th>Insumo</th><th>Usado em</th><th>Origem</th><th>Destino</th><th></th></tr>` + (q.materiais.map(m =>
    `<tr data-mat="${esc(m.chave)}"><td>${esc(m.material)}</td><td>${esc(m.insumo || "")}</td><td><small>${m.chave.endsWith("|usina") ? "usinagem" : "serviço"}</small></td>
     <td>${selLocal(m.origem, "origem")}</td><td>${selLocal(m.destino, "destino")}</td><td><button class="btn mini" data-salvaori data-dica="Grava a origem/destino deste material em todas as linhas">✓</button></td></tr>`).join("")
    || '<tr><td colspan=6 class="nota">Gere o quadro das composições para listar os materiais.</td></tr>');
  $$("[data-salvaori]").forEach(b => b.onclick = async () => { const tr = b.closest("tr");
    try { await jpost(`${base_}${E.pid}/transportes/origem`, { chave: tr.dataset.mat, origem: $('[data-k="origem"]', tr).value, destino: $('[data-k="destino"]', tr).value || "Pista" }, "PUT"); toast("Origem gravada"); renderQuadro(); } catch (e) { erro(e); } });
  const linhas = q.linhas.map((l, i) => [l, i]).filter(([l]) => l.ativo !== false && l.origem);
  $("#tabQuadro").innerHTML = `<tr><th>Serviço</th><th>Material</th><th class=n>Quant. anual</th><th class=n>Fator (t/un)</th><th class=n>Peso (t)</th><th>Origem → destino</th><th class=n>DMT</th><th class=n>FIT</th><th>Transporte</th><th class=n>Momento (t·km)</th><th></th></tr>` +
    linhas.map(([l, i]) => `<tr><td>${esc(l.servico)}<br><small>${esc((l.servico_desc || "").slice(0, 60))}</small></td><td>${esc(l.material)}${l.origem_linha !== "composição" ? ` <span class="tag">${esc(l.origem_linha)}</span>` : ""}</td>
      <td class=n>${nf(l.quantidade_anual, 3)}</td><td class=n>${nf(l.fator, 6)}</td><td class=n>${nf(l.peso, 3)}</td><td>${esc(l.origem)} → ${esc(l.destino)}${l.erro ? `<br><span class="tag erro">${esc(l.erro)}</span>` : ""}</td>
      <td class=n>${km3(l.dmt)}</td><td class=n>${nf(l.fit, 4)}</td><td><small>${Object.keys(l.momentos || {}).map(esc).join(", ") || esc(l.transporte || "")}</small></td>
      <td class=n>${nf(Object.values(l.momentos || {}).reduce((x, y) => x + y, 0), 3)}</td>
      <td><button class="btn mini perigo" data-rmq="${i}" data-dica="Tira a linha do quadro">×</button></td></tr>`).join("");
  $$("[data-rmq]").forEach(b => b.onclick = async () => { const lst = T_.q.linhas.filter((_, i) => i !== +b.dataset.rmq);
    await jpost(`${base_}${E.pid}/transportes/linhas`, { linhas: lst }, "PUT"); renderQuadro(); });
}
$("#btnGerarQuadro").onclick = async () => {
  if (!confirm("Gerar as linhas a partir das composições dos serviços escolhidos?\n(As linhas manuais e importadas são mantidas; as geradas antes são substituídas.)")) return;
  $("#avisoQuadro").innerHTML = '<p class="carregando">Lendo os transportes das composições…</p>';
  try { await jpost(`${base_}${E.pid}/transportes/gerar`, { manter_manuais: true }); toast("Quadro gerado"); renderQuadro(); } catch (e) { erro(e); }
};
$("#btnLinhaManual").onclick = () => dialogo("Linha manual do quadro", [["servico", "Código do serviço"], ["material", "Material"], ["fator", "Fator de utilização (t por unidade do serviço)", "number"],
  ["origem", "Origem (Pista ou nome da ocorrência)"], ["destino", "Destino"], ["transporte", "Composição de transporte (ex.: 5915321)"], ["quantidade", "Quantidade anual (vazio = a do serviço)", "number"]],
  async v => { const lst = (T_.q?.linhas || []).concat([{ ...v, origem_linha: "manual", ativo: true }]); await jpost(`${base_}${E.pid}/transportes/linhas`, { linhas: lst }, "PUT"); toast("Linha incluída"); renderQuadro(); });
$("#btnAplicarMom").onclick = async () => {
  if (!confirm("Gravar os momentos como quantidade dos serviços de transporte do orçamento?")) return;
  try { const r = await jpost(`${base_}${E.pid}/transportes/aplicar`, {}); toast(`${r.aplicados.length} serviços de transporte atualizados`); renderQuadro(); } catch (e) { erro(e); }
};
$("#btnImpTransp").onclick = async () => {
  const a = await escolherArquivo(".xlsx,.xlsm"); if (!a) return;
  const fd = new FormData(); fd.append("arquivo", a);
  $("#resTransp").innerHTML = '<p class="carregando">Lendo a planilha…</p>';
  try { const r = await api(`${base_}${E.pid}/transportes/importar`, { method: "POST", body: fd });
    $("#resTransp").innerHTML = `<p class="ok-msg">Importado: quantidades de ${r.quantidades} serviços, ${r.linhas} linhas do quadro, VMD de ${r.vmd} segmentos. Confira o croqui (ocorrências e travessias).</p>`; carregarTransp();
  } catch (e) { $("#resTransp").innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; }
};
$("#btnExpTransp").onclick = async () => {
  try { const r = await jpost(`${base_}${E.pid}/exportar/transportes`, {}); $("#resTransp").innerHTML = `<div class="linha-botoes">${linkBaixar(r)}</div>`; } catch (e) { erro(e); }
};

// ---------------------------------------------------------------- PATO (orçamento)
const O_ = { sub: "planilha", c: null, med: null };
const q3 = v => v == null ? "—" : Number(v).toLocaleString("pt-BR", { maximumFractionDigits: 3 });
async function carregarOrc() {
  if (!E.pid) return;
  const subs = [["ficha", "Ficha de serviços", "Escolha dos serviços e níveis de esforço para montar o PATO do segmento"], ["planilha", "Planilha PATO", "Itens, quantidades (base × nível de esforço) e preços nos dois regimes"], ["ip", "Levantamento IP", "Condição do pavimento km a km e quantidades de tapa-buraco, remendo, fresagem e microrrevestimento"],
    ["sinal", "Sinalização de obras", "Duração dos serviços, projetos-tipo e dispositivos (un.dia) — Anexo XIII"], ["div", "ADM local e mobilização", "Administração local, canteiro, usina e mobilização/desmobilização calculados com a base SICRO"], ["conf", "Conferência", "Checklists de elaboração e auditoria e regras dos normativos — verificação automática e itens a marcar"], ["resumo", "Resumo e % dos grupos", "Totais por grupo de tarefas (Anexo XX) e limite de DSM"],
    ["abc", "Curva ABC", "Anexo XXI"], ["crono", "Cronograma", "Distribuição mensal do orçamento"], ["desemp", "Desempenho", "Composição da parcela mensal dos grupos por desempenho"]];
  $("#chipsOrc").innerHTML = subs.map(([k, r, d]) => `<span class="chip ${O_.sub === k ? "ativo" : ""}" data-sub="${k}" data-dica="${d}">${r}</span>`).join("");
  $$("#chipsOrc .chip").forEach(ch => ch.onclick = () => { O_.sub = ch.dataset.sub; carregarOrc(); });
  $$(".sub-orc").forEach(el => el.classList.toggle("ativa", el.id === "orc-" + O_.sub));
  $("#cabOrc").innerHTML = '<p class="carregando">Calculando a planilha…</p>';
  try {
    const c = O_.c = await api(`${base_}${E.pid}/pato`);
    const n = c.itens.filter(i => i.tipo === "servico").length, t = c.totais;
    $("#cabOrc").innerHTML = n ? `<div class="it">Sem desoneração<br><b>R$ ${reais(t.SD)}</b></div><div class="it">Com desoneração<br><b>R$ ${reais(t.CD)}</b></div>
      <div class="it">Mais vantajosa<br><b>${REG[c.vantajosa]}</b></div><div class="it">Serviços<br><b>${n}</b></div>
      <div class="it">Base<br><b>${esc(c.config.uf)} · ${esc(c.config.data_base)}</b></div>
      <div class="it">BDI SD / CD<br><b>${pct(c.config.bdi.SD)} / ${pct(c.config.bdi.CD)}</b> <button class="btn mini" id="btnVerBdi" data-dica="Abre Custos → Data-base e BDI para conferir as parcelas e ajustar">conferir/ajustar</button></div>${c.totais_ref?.SD ? `<div class="it">Planilha de origem<br><b>R$ ${reais(c.totais_ref.SD)} / ${reais(c.totais_ref.CD)}</b></div>` : ""}`
      : `<div class="it">BDI SD / CD<br><b>${pct(c.config.bdi.SD)} / ${pct(c.config.bdi.CD)}</b> <button class="btn mini" id="btnVerBdi" data-dica="Abre Custos → Data-base e BDI para conferir as parcelas e ajustar">conferir/ajustar</button></div>
        <p class="nota">Nenhuma planilha PATO neste projeto. Monte pela ficha de serviços, importe a aba PATO de uma planilha de referência ou inclua os itens.</p>`;
    if ($("#btnVerBdi")) $("#btnVerBdi").onclick = () => { C_.sub = "base"; irAba("custos"); };
    await ({ ficha: renderFicha, planilha: renderOrcPlanilha, ip: renderIp, sinal: renderSinal, div: renderDiv, conf: renderConf, resumo: renderOrcResumo, abc: renderOrcAbc, crono: renderOrcCrono, desemp: renderOrcDesemp })[O_.sub]();
  } catch (e) { $("#cabOrc").innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; }
}
function renderOrcPlanilha() {
  const c = O_.c;
  const acoes = i => `<span class="acoes-orc">
      <button class="btn mini" data-novo="${esc(i.id)}" data-dica="Inclui um serviço ou um título (tópico) logo abaixo desta linha">＋</button>
      <button class="btn mini" data-sobe="${esc(i.id)}" data-dica="${i.tipo === "titulo" ? "Sobe o tópico inteiro (título e seus serviços)" : "Sobe a linha"}">↑</button>
      <button class="btn mini" data-desce="${esc(i.id)}" data-dica="${i.tipo === "titulo" ? "Desce o tópico inteiro" : "Desce a linha"}">↓</button>
      <button class="btn mini perigo" data-exorc="${esc(i.id)}" data-dica="${i.tipo === "titulo" ? "Exclui o título (pergunta se exclui também os serviços do tópico)" : "Exclui o serviço"}">×</button></span>`;
  $("#tabOrc").innerHTML = `<tr><th>Item</th><th>Código</th><th>Discriminação</th><th class=n>Base</th><th class=n>NE</th><th class=n>Quantidade</th><th>Und</th>
    <th class=n>Preço SD</th><th class=n>Parcial SD</th><th class=n>Preço CD</th><th class=n>Parcial CD</th><th></th></tr>` + c.itens.map(i => i.tipo === "titulo"
    ? `<tr class="titulo-orc"><td>${esc(i.item)}</td><td colspan=10>${esc(i.descricao)}</td>
      <td style="white-space:nowrap"><button class="btn mini" data-edtit="${esc(i.id)}" data-dica="Edita a numeração e o nome do tópico">Editar</button>${acoes(i)}</td></tr>`
    : `<tr><td>${esc(i.item)}</td><td>${esc(i.codigo)}</td><td>${esc(i.descricao)}</td>
      <td class=n title="${esc(i.base_fonte || "")}">${q3(i.base_valor)}<br><small>${esc((i.base_fonte || "").slice(0, 38))}</small></td><td class=n>${(i.base || {}).tipo === "direta" ? "—" : q3(i.ne)}</td>
      <td class=n><b>${q3(i.quantidade)}</b></td><td>${esc(i.unidade || "")}</td>
      <td class=n title="${esc(i.preco_fonte_SD || "")}">${reais(i.preco_SD)}</td><td class=n>${reais(i.parcial_SD)}</td>
      <td class=n title="${esc(i.preco_fonte_CD || "")}">${reais(i.preco_CD)}</td><td class=n>${reais(i.parcial_CD)}</td>
      <td style="white-space:nowrap"><button class="btn mini" data-edorc="${esc(i.id)}" data-dica="Altera numeração, código, descrição, a base da quantidade (inventário, IP, outro item, transporte, valor), o nível de esforço ou o preço">Editar</button>${acoes(i)}</td></tr>`).join("")
    + `<tr class="titulo-orc"><td colspan=8>TOTAL GERAL DO ORÇAMENTO</td><td class=n>${reais(c.totais.SD)}</td><td></td><td class=n>${reais(c.totais.CD)}</td><td></td></tr>`;
  $$("[data-edorc]").forEach(b => b.onclick = () => editarItemOrc(b.dataset.edorc));
  $$("[data-edtit]").forEach(b => b.onclick = () => dialogoLinha(O_.c.itens.find(x => x.id === b.dataset.edtit), null));
  $$("[data-novo]").forEach(b => b.onclick = () => dialogoLinha(null, b.dataset.novo));
  const mover = (id, dir) => jpost(`${base_}${E.pid}/pato/itens/${id}/mover`, { direcao: dir }).then(carregarOrc).catch(erro);
  $$("[data-sobe]").forEach(b => b.onclick = () => mover(b.dataset.sobe, -1));
  $$("[data-desce]").forEach(b => b.onclick = () => mover(b.dataset.desce, 1));
  $$("[data-exorc]").forEach(b => b.onclick = async () => {
    const x = O_.c.itens.find(y => y.id === b.dataset.exorc);
    let com = false;
    if (x.tipo === "titulo") {
      if (!confirm(`Excluir o título ${x.item} — ${x.descricao}?`)) return;
      com = confirm("Excluir também os serviços e subtítulos deste tópico?\n(OK = excluir o tópico inteiro · Cancelar = excluir só o título)");
    } else if (!confirm(`Excluir o serviço ${x.item} ${x.codigo || ""}?`)) return;
    try { await api(`${base_}${E.pid}/pato/itens/${x.id}?com_itens=${com}`, { method: "DELETE" }); toast("Excluído"); carregarOrc(); } catch (e) { erro(e); }
  });
}
// novo título/serviço (apos = id da linha acima) ou edição de um título
function dialogoLinha(x, apos) {
  const d = $("#dlg"), f = $("#dlgForm"), novo = !x;
  const acima = apos ? O_.c.itens.find(y => y.id === apos) : null;
  const sug = acima ? (acima.tipo === "titulo" ? acima.item + ".01" : (acima.item || "").replace(/(\d+)$/, m => String(+m + 1).padStart(m.length, "0"))) : "";
  f.className = "form";
  f.innerHTML = `<h3>${novo ? "Incluir linha" + (acima ? ` abaixo de ${esc(acima.item)}` : "") : `Editar título ${esc(x.item)}`}</h3><div class="campos">
    ${novo ? `<label>Tipo <select name="tipo"><option value="servico">Serviço</option><option value="titulo">Título (tópico)</option></select></label>` : ""}
    <label>Item (numeração) <input name="item" value="${esc(x ? x.item : sug)}" data-dica="Ex.: 01.03 (tópico) ou 01.03.05 (serviço). Os serviços de um tópico começam com a numeração dele"></label>
    <label class="largo">Nome / discriminação <input name="descricao" value="${esc(x ? x.descricao : "")}" placeholder="ex.: CONSERVAÇÃO PREVENTIVA PERIÓDICA (vazio no serviço = descrição da base)"></label>
    ${novo ? `<label>Código SICRO/próprio <input name="codigo" data-dica="Serviço: a descrição, a unidade e o preço vêm da base"></label>
      <label>Quantidade (base) <input name="quantidade" type="number" step="any" data-dica="Depois, em Editar, ligue a quantidade ao inventário, ao IP ou a outro item"></label>
      <label>Nível de esforço <input name="ne" type="number" step="any" value="1"></label>` : ""}</div>
    <div class="linha-botoes"><button class="btn primario" value="ok">Salvar</button><button class="btn" value="cancelar" formnovalidate>Cancelar</button></div>`;
  d.showModal();
  d.onclose = async () => {
    if (d.returnValue !== "ok") return;
    const v = formObj(f);
    try {
      if (novo) {
        if (v.tipo === "servico" && !v.codigo) return toast("Informe o código do serviço");
        await jpost(`${base_}${E.pid}/pato/itens`, { ...v, apos, ne: v.ne || 1 });
      } else await jpost(`${base_}${E.pid}/pato/itens/${x.id}`, { item: v.item, descricao: v.descricao }, "PUT");
      toast("Planilha atualizada"); carregarOrc();
    } catch (e) { erro(e); }
  };
}
async function editarItemOrc(id) {
  const i = O_.c.itens.find(x => x.id === id), b = i.base || {};
  O_.med = O_.med || await api(`${base_}${E.pid}/pato/medidas`);
  const itens = O_.c.itens.filter(x => x.tipo === "servico" && x.id !== id);
  const d = $("#dlg"), f = $("#dlgForm");
  f.className = "form";
  f.innerHTML = `<h3>Item ${esc(i.item)} — ${esc(i.codigo)}</h3><div class="campos">
    <label>Item (numeração) <input name="item_num" value="${esc(i.item || "")}"></label>
    <label>Código <input name="codigo" value="${esc(i.codigo || "")}" data-dica="Trocar o código troca a composição (preço) do serviço"></label>
    <label class="largo">Discriminação <input name="descricao" value="${esc(i.descricao || "")}"></label>
    <label>Unidade <input name="unidade" value="${esc(i.unidade || "")}"></label>
    <label>Base da quantidade <select name="tipo">${[["valor", "Valor informado"], ["inventario", "Medida do inventário"], ["item", "Outro item da planilha"], ["producao", "Produção da equipe × horas × dias"],
      ["extensao", "Extensão do segmento × fator"], ["contrato", "Rateio por ano de contrato (fator ÷ anos)"], ["ip", "Levantamento IP"], ["transporte", "Momento do quadro de transportes"], ["direta", "Quantidade direta"]]
      .map(([k, r]) => `<option value="${k}" ${b.tipo === k ? "selected" : ""}>${r}</option>`).join("")}</select></label>
    <label>Valor <input name="valor" type="number" step="any" value="${b.valor ?? i.base_valor ?? ""}" data-dica="Base (valor informado) ou quantidade (direta)"></label>
    <label class="largo">Medida do inventário <select name="medida"><option value=""></option>${Object.entries(O_.med).map(([k, v]) => `<option value="${esc(k)}" ${b.medida === k ? "selected" : ""}>${esc(k)} = ${q3(v)}</option>`).join("")}</select></label>
    <label>Fator sobre a medida <input name="fator" type="number" step="any" value="${b.fator ?? 1}"></label>
    <label class="largo">Item de referência <select name="ref"><option value=""></option>${itens.map(x => `<option value="${esc(x.id)}" ${b.ref === x.id ? "selected" : ""}>${esc(x.item)} ${esc(x.codigo)} — ${esc((x.descricao || "").slice(0, 50))}</option>`).join("")}</select></label>
    <label>Usar do item <select name="campo"><option value="quantidade">quantidade</option><option value="base" ${b.campo === "base" ? "selected" : ""}>base</option></select></label>
    <label>Dias de equipe <input name="dias" type="number" step="any" value="${b.dias ?? ""}" data-dica="Produção: dias de trabalho no ano (a produção horária vem da composição da base)"></label>
    <label>Horas por dia <input name="horas" type="number" step="any" value="${b.horas ?? 8}"></label>
    <label>Fator (extensão / contrato) <input name="fext" type="number" step="any" value="${b.tipo === "extensao" || b.tipo === "contrato" ? b.fator ?? 1 : ""}" data-dica="Extensão: quantidade por km do segmento · Contrato: unidades rateadas pelos anos de vigência"></label>
    <label>Nível de esforço <input name="ne" type="number" step="any" value="${i.ne ?? 1}"></label>
    <label>Arredondamento <select name="arred"><option value="trunc">TRUNCAR (3 casas)</option><option value="arred" ${i.arred === "arred" ? "selected" : ""}>ARRED (3 casas)</option></select></label>
    <label>Preço SD informado <input name="psd" type="number" step="any" value="${i.preco_manual?.SD ?? ""}" placeholder="${reais(i.preco_SD)}"></label>
    <label>Preço CD informado <input name="pcd" type="number" step="any" value="${i.preco_manual?.CD ?? ""}" placeholder="${reais(i.preco_CD)}"></label>
    </div>${b.expr ? `<p class="nota">Memória de origem: <code>${esc(b.expr)}</code></p>` : ""}
    <div class="linha-botoes"><button class="btn primario" value="ok">Salvar</button><button class="btn perigo" value="remover" formnovalidate>Remover item</button><button class="btn" value="cancelar" formnovalidate>Cancelar</button></div>`;
  d.showModal();
  d.onclose = async () => {
    try {
      if (d.returnValue === "remover") { if (confirm("Remover o item?")) { await api(`${base_}${E.pid}/pato/itens/${id}`, { method: "DELETE" }); carregarOrc(); } return; }
      if (d.returnValue !== "ok") return;
      const v = formObj(f), base = { tipo: v.tipo, expr: b.expr, fonte: v.tipo === b.tipo ? b.fonte : "informado" };
      if (v.tipo === "valor" || v.tipo === "direta") base.valor = +v.valor;
      if (v.tipo === "inventario") Object.assign(base, { medida: v.medida, fator: +v.fator || 1, valor: +v.valor || null });
      if (v.tipo === "item") Object.assign(base, { ref: v.ref, campo: v.campo });
      if (v.tipo === "transporte") Object.assign(base, { codigo: i.codigo, valor: b.valor });
      if (v.tipo === "producao") Object.assign(base, { dias: +v.dias || 1, horas: +v.horas || 8, producao_ref: b.producao_ref, fonte: "produção SICRO × 8 h × dias" });
      if (v.tipo === "extensao" || v.tipo === "contrato") Object.assign(base, { fator: +v.fext || 1 });
      if (v.tipo === "ip") Object.assign(base, { chaves: b.chaves, campo: b.campo, fator: b.fator });
      await jpost(`${base_}${E.pid}/pato/itens/${id}`, { item: v.item_num, codigo: v.codigo, descricao: v.descricao, unidade: v.unidade, base, ne: v.ne, arred: v.arred, preco_manual: { SD: v.psd === "" ? null : +v.psd, CD: v.pcd === "" ? null : +v.pcd } }, "PUT");
      toast("Item atualizado"); carregarOrc();
    } catch (e) { erro(e); }
  };
}
async function renderOrcResumo() {
  const c = O_.c;
  $("#avisosOrc").innerHTML = c.avisos.map(a => `<p class="tag aviso">${esc(a)}</p>`).join("") + (c.sem_preco.length ? `<p class="tag erro">Sem preço: ${c.sem_preco.map(esc).join(", ")}</p>` : "");
  $("#tabOrcResumo").innerHTML = `<tr><th>Seção</th><th>Grupo de tarefas</th><th class=n>Itens</th><th class=n>Sem desoneração</th><th class=n>%</th><th class=n>Com desoneração</th><th class=n>%</th></tr>` +
    c.secoes.map(s => `<tr><td>${esc(s.secao)}</td><td>${esc(s.nome)}</td><td class=n>${s.n}</td><td class=n>${reais(s.SD)}</td><td class=n>${pct(s.pct_SD)}</td><td class=n>${reais(s.CD)}</td><td class=n>${pct(s.pct_CD)}</td></tr>`).join("") +
    `<tr class="titulo-orc"><td colspan=3>TOTAL</td><td class=n>${reais(c.totais.SD)}</td><td class=n>100%</td><td class=n>${reais(c.totais.CD)}</td><td class=n>100%</td></tr>`;
}
async function renderOrcAbc() {
  const r = O_.res = await api(`${base_}${E.pid}/pato/resumo`);
  $("#tabAbc").innerHTML = `<tr><th>Faixa</th><th>Código</th><th>Descrição</th><th>Und</th><th class=n>Quantidade</th><th class=n>Preço</th><th class=n>Custo total</th><th class=n>%</th><th class=n>% acumulado</th></tr>` +
    r.abc.map(a => `<tr><td><span class="tag ${a.faixa === "A" ? "erro" : a.faixa === "B" ? "aviso" : ""}">${a.faixa}</span></td><td>${esc(a.codigo)}</td><td>${esc(a.descricao || "")}</td><td>${esc(a.unidade || "")}</td>
      <td class=n>${q3(a.quantidade)}</td><td class=n>${reais(a.preco)}</td><td class=n>${reais(a.total)}</td><td class=n>${pct(a.pct)}</td><td class=n>${pct(a.acumulado)}</td></tr>`).join("");
}
async function renderOrcCrono() {
  const r = await api(`${base_}${E.pid}/pato/resumo`), cr = r.cronograma;
  $("#tabCrono").innerHTML = `<tr><th>Grupo</th><th class=n>Total</th>${cr.por_mes.map((_, i) => `<th class=n>Mês ${i + 1}</th>`).join("")}</tr>` +
    cr.linhas.map(l => `<tr><td>${esc(l.nome)}</td><td class=n>${reais(l.total)}</td>${l.meses.map(v => `<td class=n>${reais(v)}</td>`).join("")}</tr>`).join("") +
    `<tr class="titulo-orc"><td>Total do mês</td><td class=n>${reais(cr.por_mes.reduce((a, b) => a + b, 0))}</td>${cr.por_mes.map(v => `<td class=n>${reais(v)}</td>`).join("")}</tr>
     <tr><td>% acumulado</td><td></td>${cr.acumulado.map(v => `<td class=n>${pct(v)}</td>`).join("")}</tr>`;
}
function renderOrcDesemp() {
  const g = Object.values(O_.c.desempenho || {}), ner = O_.c.ne_rocada;
  const blocoNer = `<h4>Nível de esforço da roçada — norma DNIT 182/2018 (Res. 8/2023, art. 24, § 4º)</h4>
    <p class="nota">NERp = Σ(NERe ÷ distância) ÷ Σ(1 ÷ distância) das estações pluviométricas mais próximas; NE = NERp arredondado + acréscimo.
      O NE adotado é a frequência anual da capina e das roçadas do grupo por desempenho; pode prevalecer a observação de campo, com justificativa.</p>
    <table class="tab" id="tabNer"><tr><th>Estação</th><th>UF</th><th>Nome / município</th><th class=n>Distância (km)</th><th class=n>NERe</th><th></th></tr>
    ${(ner?.estacoes || []).map(e => `<tr data-est><td><input data-c="codigo" value="${esc(e.codigo || "")}" style="width:90px"></td><td><input data-c="uf" value="${esc(e.uf || "")}" style="width:40px"></td>
      <td><input data-c="nome" value="${esc(e.nome || "")}" style="width:160px"> <input data-c="municipio" value="${esc(e.municipio || "")}" style="width:160px"></td>
      <td class=n><input data-c="distancia" type="number" step="any" value="${e.distancia ?? ""}" style="width:80px"></td><td class=n><input data-c="nere" type="number" step="any" value="${e.nere ?? ""}" style="width:70px"></td>
      <td><button class="btn mini perigo" type="button" data-rmlin>×</button></td></tr>`).join("")}</table>
    <div class="linha-botoes"><button class="btn mini" type="button" id="btnNerAdd">+ Estação</button>
      <button class="btn mini" type="button" id="btnNerAuto" data-dica="Busca, entre as 82 estações da norma (Anexo A / Est-Pluv_NERP), as mais próximas do ponto médio do segmento (pelo eixo do inventário) e calcula as distâncias geodésicas — como a régua do Google Earth">Buscar estações mais próximas</button>
      <label>nº de estações <select id="nerN">${[5, 4, 3, 2].map(n => `<option>${n}</option>`).join("")}</select></label>
      ${ner?.ponto_medio ? `<small>ponto médio do trecho: ${nf(ner.ponto_medio.lat, 5)}, ${nf(ner.ponto_medio.lon, 5)}</small>` : ""}</div>
    <p>NERp = <b>${ner?.nerp != null ? nf(ner.nerp, 4) : "—"}</b> · acréscimo <input id="nerAcr" type="number" step="any" value="${ner?.acrescimo ?? 1}" style="width:60px">
      · sugerido <b>${ner?.sugerido ?? "—"}</b> · <b>NE adotado</b> <input id="nerAdot" type="number" step="any" value="${ner && ner.adotado !== ner.sugerido ? ner.adotado : ""}" placeholder="${ner?.sugerido ?? ""}" style="width:70px">
      <input id="nerJust" placeholder="justificativa (observação de campo)" value="${esc(ner?.justificativa || "")}" style="width:280px">
      <button class="btn mini primario" type="button" id="btnNerSalvar" data-dica="Grava o NE da roçada; o grupo por desempenho é recalculado">Salvar NE</button></p>`;
  $("#listaDesemp").innerHTML = g.map(x => `<h4>${esc(x.codigo)} — ${esc(x.descricao)}: R$ ${reais(x.mensal_SD)}/mês (SD) · R$ ${reais(x.mensal_CD)}/mês (CD)</h4>
    <div class="tabela-rolagem"><table class="tab"><tr><th>Serviço</th><th>Descrição</th><th class=n>Qtde total</th><th class=n>NE</th><th class=n>Freq.</th><th class=n>Qtde/km</th><th>Und</th><th class=n>Preço SD</th><th class=n>R$/km/ano SD</th><th class=n>Preço CD</th><th class=n>R$/km/ano CD</th></tr>
    ${x.linhas.map(l => `<tr><td>${esc(l.codigo)}</td><td>${esc(l.descricao)}<br><small>${esc(l.desc_qtd || "")}</small></td><td class=n>${q3(l.qtd_total_calc)}</td><td class=n>${q3(l.ne)}</td><td class=n>${q3(l.freq)}</td>
      <td class=n>${q3(l.qtd_km_calc)}</td><td>${esc(l.unidade || "")}</td><td class=n>${reais(l.preco)}</td><td class=n>${reais(l.valor_km_ano)}</td><td class=n>${reais(l.preco_CD)}</td><td class=n>${reais(l.valor_km_ano_CD)}</td></tr>`).join("")}</table></div>`).join("")
    || '<p class="nota">Sem grupos por desempenho (importe de uma planilha PATO com a aba DESEMPENHO).</p>';
  $("#listaDesemp").insertAdjacentHTML("beforeend", blocoNer);
  ligarRemover();
  $("#btnNerAdd").onclick = () => { $("#tabNer").insertAdjacentHTML("beforeend", `<tr data-est><td><input data-c="codigo" style="width:90px"></td><td><input data-c="uf" style="width:40px"></td><td><input data-c="nome" style="width:160px"> <input data-c="municipio" style="width:160px"></td><td class=n><input data-c="distancia" type="number" step="any" style="width:80px"></td><td class=n><input data-c="nere" type="number" step="any" style="width:70px"></td><td><button class="btn mini perigo" type="button" data-rmlin>×</button></td></tr>`); ligarRemover(); };
  $("#btnNerAuto").onclick = async () => {
    try { const r = await jpost(`${base_}${E.pid}/ne-rocada/estacoes`, { n: +$("#nerN").value });
      toast(`NERp ${nf(r.nerp, 2)} → NE ${r.sugerido} (${r.estacoes.length} estações)`); carregarOrc(); } catch (e) { erro(e); }
  };
  $("#btnNerSalvar").onclick = async () => {
    const estacoes = lerTab("#tabNer tr[data-est]").filter(e => e.distancia != null);
    try { await jpost(`${base_}${E.pid}/ne-rocada`, { estacoes, acrescimo: +$("#nerAcr").value, adotado: $("#nerAdot").value === "" ? null : +$("#nerAdot").value, justificativa: $("#nerJust").value }, "PUT");
      toast("NE da roçada salvo — desempenho recalculado"); carregarOrc(); } catch (e) { erro(e); }
  };
}
$("#btnCrqAuto").onclick = async () => {
  const km = $("#crqKmCant").value;
  if (km === "") return toast("Informe o km do canteiro");
  if (!confirm("Montar o croqui pelo modelo? As ocorrências atuais são substituídas (travessias e VMD são mantidos).")) return;
  try { const r = await jpost(`${base_}${E.pid}/croqui/montar`, { km_canteiro: +km, km_usina: $("#crqKmUsina").value === "" ? null : +$("#crqKmUsina").value });
    toast(`Croqui montado — ${r.linhas_reorientadas} linhas do quadro reorientadas`); carregarTransp(); } catch (e) { erro(e); }
};

$("#btnCrqKmz").onclick = async () => {
  const r = await importarKmz(); if (!r) return;
  $("#crqKmzRes").innerHTML = `<div class="tabela-rolagem"><table class="tab"><tr><th>Ponto</th><th>Tipo</th><th class=n>km (SNV)</th><th class=n>Distância ao eixo (km)</th><th>Segmento</th><th>Observação</th></tr>
    ${r.pontos.map(p => `<tr><td>${esc(p.nome)}</td><td>${esc(p.tipo)}</td><td class=n>${nf(p.km)}</td><td class=n>${nf(p.distancia_km)}</td><td>${esc(p.segmento)}</td><td><small>${esc(p.obs)}</small></td></tr>`).join("")}</table></div>
    ${r.fora?.length ? `<p class="tag aviso">Sem localização no SNV: ${esc(r.fora.join(", "))}</p>` : ""}<p class="nota">Confira o acesso (estrada até a rodovia) e ajuste na tabela de ocorrências.</p>`;
  carregarTransp();
};

// ---- conferência
const CF_ = { r: null };
const CF_TAG = { ok: ["ok", "OK"], atencao: ["aviso", "Atenção"], falha: ["erro", "Falha"], manual: ["", "A conferir"], feito: ["ok", "Conferido"] };
async function renderConf() {
  const r = CF_.r = await api(`${base_}${E.pid}/conferencia`);
  const rs = r.resumo;
  $("#confResumo").innerHTML = `<p>${Object.entries(CF_TAG).map(([k, [cl, t]]) => `<span class="tag ${cl}">${t}: ${rs[k] || 0}</span>`).join(" ")}</p>`;
  desenharConf();
}
function desenharConf() {
  const so = $("#confPend").checked; let sec = "";
  $("#tabConf").innerHTML = `<tr><th>Situação</th><th>Verificação</th><th>Detalhe</th><th>Fonte</th><th>Observação</th></tr>` +
    CF_.r.itens.filter(x => !so || ["falha", "atencao", "manual"].includes(x.status)).map(x => {
      const [cl, t] = CF_TAG[x.status] || ["", x.status];
      const cab = x.secao !== sec ? `<tr class="tit"><td colspan=5><b>${esc(sec = x.secao)}</b></td></tr>` : "";
      return cab + `<tr><td>${x.tipo === "manual" ? `<label class="check"><input type="checkbox" data-cfok="${x.id}" ${x.status === "feito" ? "checked" : ""}> ` : ""}<span class="tag ${cl}">${t}</span>${x.tipo === "manual" ? "</label>" : ""}<br><small>${x.tipo === "auto" ? "automático" : "manual"}</small></td>
        <td>${esc(x.texto)}</td><td><small>${esc(x.detalhe || "")}</small></td><td><small>${esc(x.fonte)}</small></td>
        <td><input data-cfobs="${x.id}" value="${esc(x.obs || "")}" placeholder="observação / documento de suporte" style="width:220px"></td></tr>`;
    }).join("");
  $$("[data-cfok]").forEach(c => c.onchange = async () => { await jpost(`${base_}${E.pid}/conferencia/${c.dataset.cfok}`, { feito: c.checked }, "PUT"); renderConf(); });
  $$("[data-cfobs]").forEach(i => i.onchange = async () => { await jpost(`${base_}${E.pid}/conferencia/${i.dataset.cfobs}`, { obs: i.value }, "PUT"); toast("Observação gravada"); });
}
$("#confPend").onchange = () => CF_.r && desenharConf();

// ---- ficha de serviços
async function renderFicha() {
  const f = await api(`${base_}${E.pid}/pato/ficha`), atuais = new Set((O_.c?.itens || []).filter(i => i.tipo === "servico").map(i => i.id));
  $("#fichaOrigem").textContent = f.origem || "modelo";
  const vazio = !atuais.size;
  $("#tabFicha").innerHTML = `<tr><th></th><th>Item</th><th>Código</th><th>Serviço</th><th>Un.</th><th>Regra da quantidade</th><th class=n>Nível de esforço</th><th class=n>Valor a informar</th></tr>` +
    f.servicos.map(x => x.tipo === "titulo" ? `<tr class="tit"><td></td><td colspan=7><b>${esc(x.item || "")} ${esc(x.descricao || "")}</b></td></tr>`
      : `<tr><td><input type="checkbox" data-fsel="${x.id}" ${vazio || atuais.has(x.id) ? "checked" : ""}></td><td>${esc(x.item)}</td><td>${esc(x.codigo)}</td>
        <td>${esc((x.descricao || "").slice(0, 70))}</td><td>${esc(x.unidade || "")}</td><td><small>${esc(x.regra)}</small></td>
        <td class=n>${x.depende_de ? "—" : `<input data-fne="${x.id}" type="number" step="any" value="${x.ne ?? ""}" style="width:90px" data-dica="${esc(x.ne_rotulo || "Nível de esforço do item")}">`}</td>
        <td class=n>${x.a_informar ? `<input data-fval="${x.id}" type="number" step="any" value="${x.valor_ref ?? ""}" style="width:100px" data-dica="Quantidade sem regra automática (sugestão: valor do modelo)">` : ""}</td></tr>`).join("");
  $("#fichaTodos").onchange = e => $$("[data-fsel]").forEach(c => c.checked = e.target.checked);
}
$("#btnFichaMontar").onclick = async () => {
  if (O_.c?.itens?.length && !confirm("Substituir a planilha PATO deste projeto pelos serviços marcados na ficha?")) return;
  const selecionados = $$("[data-fsel]").filter(c => c.checked).map(c => c.dataset.fsel);
  const ne = Object.fromEntries($$("[data-fne]").filter(i => i.value !== "").map(i => [i.dataset.fne, +i.value]));
  const valores = Object.fromEntries($$("[data-fval]").filter(i => i.value !== "").map(i => [i.dataset.fval, +i.value]));
  $("#resOrc").innerHTML = '<p class="carregando">Montando a planilha PATO pela ficha…</p>';
  try { const r = await jpost(`${base_}${E.pid}/pato/montar`, { selecionados, ne, valores, extras: O_.lista?.extras || [], conferir: O_.lista?.quantidades || null });
    if (r.conferencia_qtd?.length) { O_.confQtd = r.conferencia_qtd; O_.sub = "planilha"; await carregarOrc(); mostrarConfQtd(); return; }
    $("#resOrc").innerHTML = `<p class="ok-msg">${r.servicos} serviços; ${r.transporte_linhas} linhas de transporte local do modelo.</p>` +
      (r.ocorrencias_faltando?.length ? `<p class="tag aviso">Ocorrências do quadro sem correspondente no croqui: ${esc(r.ocorrencias_faltando.join(", "))} — monte o croqui na aba Transporte.</p>` : "");
    O_.sub = "planilha"; carregarOrc(); } catch (e) { $("#resOrc").innerHTML = ""; erro(e); }
};
function mostrarConfQtd() {
  const l = O_.confQtd || [], dif = l.filter(x => !x.confere);
  $("#resOrc").innerHTML = `<div class="caixa"><h3>Quantidades: ficha enviada × calculadas pelo sistema</h3>
    <p class="nota">A quantidade continua ligada ao inventário / ICM-IP / extensão / prazo deste projeto. ${l.length - dif.length} de ${l.length} conferem (até 1%).
      Onde diverge, confira a fonte; “usar a da ficha” troca a base do item por quantidade direta (perde a ligação).</p>
    ${dif.length ? `<div class="tabela-rolagem"><table class="tab"><tr><th>Item</th><th>Código</th><th>Discriminação</th><th class=n>Ficha</th><th class=n>Sistema</th><th class=n>Diferença</th><th>Fonte do sistema</th><th></th></tr>
      ${dif.map(x => `<tr><td>${esc(x.item)}</td><td>${esc(x.codigo)}</td><td>${esc((x.descricao || "").slice(0, 50))}</td><td class=n>${q3(x.quantidade_ficha)}</td><td class=n>${q3(x.quantidade_sistema)}</td>
        <td class=n>${x.diferenca == null ? "—" : pctN(x.diferenca)}</td><td><small>${esc(x.fonte || "")}</small></td>
        <td><button class="btn mini" data-usaficha="${esc(x.id)}" data-q="${x.quantidade_ficha}" data-dica="Quantidade direta = valor da ficha">usar a da ficha</button></td></tr>`).join("")}</table></div>` : '<p class="ok-msg">Todas as quantidades conferem.</p>'}</div>`;
  $$("[data-usaficha]").forEach(b => b.onclick = async () => {
    try { await jpost(`${base_}${E.pid}/pato/itens/${b.dataset.usaficha}`, { base: { tipo: "direta", valor: +b.dataset.q, fonte: "ficha enviada" } }, "PUT");
      O_.confQtd = O_.confQtd.filter(x => x.id !== b.dataset.usaficha); await carregarOrc(); mostrarConfQtd(); } catch (e) { erro(e); }
  });
}
$("#btnFichaLista").onclick = async () => {
  const a = await escolherArquivo(".xlsx,.xlsm,.csv,.txt"); if (!a) return;
  const fd = new FormData(); fd.append("arquivo", a);
  try { const r = O_.lista = await api(`${base_}${E.pid}/pato/lista-servicos`, { method: "POST", body: fd });
    const sel = new Set(r.selecionados);
    $$("[data-fsel]").forEach(c => c.checked = sel.has(c.dataset.fsel));
    Object.entries(r.ne || {}).forEach(([id, v]) => { const i = $(`[data-fne="${id}"]`); if (i) i.value = v; });
    $("#fichaListaRes").innerHTML = `<p class="ok-msg">${r.lidos} linhas lidas: ${r.selecionados.length} serviços da ficha marcados${Object.keys(r.quantidades || {}).length ? ` · ${Object.keys(r.quantidades).length} quantidades serão conferidas com o inventário/IP ao montar` : ""}.</p>` +
      (r.avisos || []).map(a => `<p class="tag aviso">${esc(a)}</p>`).join("") +
      (r.extras.length ? `<p class="nota">Fora da ficha (entram em “01.08 Serviços incluídos pela lista” ao montar):</p><ul class="nota">${r.extras.map(e => `<li>${esc(e.codigo)} — ${esc(e.descricao || "")} ${e.na_base ? "" : '<span class="tag aviso">não está na base SICRO do projeto</span>'}</li>`).join("")}</ul>` : "");
  } catch (e) { erro(e); }
};
$("#btnFichaGravar").onclick = async () => {
  if (!confirm("Gravar a planilha PATO deste projeto como a ficha de serviços (substitui a ficha atual)?")) return;
  try { await jpost(`${base_}${E.pid}/pato/ficha`, {}); toast("Ficha de serviços gravada"); carregarOrc(); } catch (e) { erro(e); }
};

$("#btnImpOrc").onclick = async () => {
  const a = await escolherArquivo(".xlsx,.xlsm"); if (!a) return;
  if (O_.c?.itens?.length && !confirm("Substituir a planilha PATO deste projeto pela importada?")) return;
  const fd = new FormData(); fd.append("arquivo", a);
  $("#resOrc").innerHTML = '<p class="carregando">Lendo a planilha PATO…</p>';
  try { const r = await api(`${base_}${E.pid}/pato/importar`, { method: "POST", body: fd });
    $("#resOrc").innerHTML = `<p class="ok-msg">Importado: ${r.itens} linhas; ${r.vinculados} quantidades ligadas ao inventário do projeto.</p>`; O_.med = null; carregarOrc();
  } catch (e) { $("#resOrc").innerHTML = `<p class="tag erro">${esc(e.message)}</p>`; }
};
$("#btnAddOrc").onclick = () => dialogoLinha(null, O_.c?.itens?.length ? O_.c.itens[O_.c.itens.length - 1].id : null);
$("#btnExpOrc").onclick = async () => {
  try { const r = await jpost(`${base_}${E.pid}/exportar/orcamento`, {}); $("#resOrc").innerHTML = `<div class="linha-botoes">${linkBaixar(r)}</div>`; } catch (e) { erro(e); }
};

$("#btnExpLic").onclick = async () => {
  $("#resOrc").innerHTML = '<p class="carregando">Gerando a planilha de licitação e recalculando para conferir…</p>';
  try { const r = await jpost(`${base_}${E.pid}/exportar/licitacao`, {}), cf = r.conferencia || {};
    const ok = cf.diferenca && Math.abs(cf.diferenca.SD) < 0.01 && Math.abs(cf.diferenca.CD) < 0.01;
    const conf = cf.totais_planilha ? `<p class="tag ${ok ? "ok" : "aviso"}">Planilha recalculada: SD R$ ${reais(cf.totais_planilha.SD)} · CD R$ ${reais(cf.totais_planilha.CD)}
      ${ok ? "— igual ao sistema" : `— diferença SD ${reais(cf.diferenca.SD)} · CD ${reais(cf.diferenca.CD)}`}</p>` : (cf.erro ? `<p class="tag aviso">Sem conferência automática (${esc(cf.erro)}); o Excel recalcula ao abrir.</p>` : "");
    $("#resOrc").innerHTML = `<div class="linha-botoes">${linkBaixar(r)}</div>${conf}<ul class="nota">${r.log.map(l => `<li>${esc(l)}</li>`).join("")}${(r.pendencias || []).map(l => `<li class="sit-conferir">${esc(l)}</li>`).join("")}</ul>`;
  } catch (e) { $("#resOrc").innerHTML = ""; erro(e); }
};

// ---- levantamento IP
const IP_ = { d: null };
const NIV = ["Bom", "Regular", "Ruim", "Péssimo"];
async function renderIp() {
  const d = IP_.d = await api(`${base_}${E.pid}/ip`);
  const rc = Object.entries(d.resumo_condicao || {}).map(([k, v]) => `${k}: ${nf(v, 1)} kmf`).join(" · ");
  $("#ipResumo").innerHTML = d.linhas.length ? `<p class="nota"><b>${nf(d.kmf_total, 1)} kmf</b> levantados · ${esc(rc)} · ${d.divergencias} km com intervenção diferente da sugerida ·
    largura da faixa <input id="ipLarg" type="number" step="any" value="${d.largura}" style="width:70px" data-dica="Largura da faixa (m) — CAD_PISTA ÷ 2"> m</p>`
    : `<p class="tag aviso">Sem levantamento. Importe da planilha PATO ou gere a grade km a km e lance a condição.</p>`;
  const P = d.parametros.intervencoes;
  $("#tabIpCalc").innerHTML = `<tr><th>Serviço</th><th class=n>kmf</th><th class=n>Inventário (kmf)</th><th>Nível de esforço</th><th class=n>NE</th><th class=n>Quantidade</th><th class=n>Histórico</th><th class=n>PATO</th><th>Critério</th></tr>` +
    d.calculo.map(c => `<tr data-ipk="${esc(c.chave)}"><td>${esc(c.rotulo)}</td><td class=n>${nf(c.kmf, 1)}</td><td class=n>${c.inventario}</td>
      <td>${c.modo === "ne" ? `<input data-p="ne" type="number" step="any" value="${P[c.chave].ne ?? ""}" style="width:70px"> ${esc(c.unidade)}/kmf`
        : `${c.espessura ? `esp. <input data-p="espessura" type="number" step="any" value="${P[c.chave].espessura ?? ""}" style="width:75px"> m · ` : ""}% <input data-p="pct" type="number" step="any" value="${P[c.chave].pct ?? ""}" style="width:75px">`}</td>
      <td class=n>${nf(c.ne_calc, 3)}</td><td class=n>${q3(c.quantidade)}</td>
      <td class=n><input data-p="historico" type="number" step="any" value="${P[c.chave].historico ?? ""}" style="width:100px" data-dica="Consumo nos últimos 12 meses (SIAC); o PATO usa o maior valor"></td>
      <td class=n><b>${q3(c.pato)}</b> <small>${esc(c.fonte)}</small></td><td><small>${esc(c.nota || "")}</small></td></tr>`).join("");
  desenharLinhasIp();
}
function desenharLinhasIp() {
  const d = IP_.d, soI = $("#ipSoInterv").checked, soD = $("#ipSoDiv").checked;
  const sel = (v, k) => `<select data-k="${k}">${NIV.map((n, i) => `<option value="${i}" ${v === i ? "selected" : ""}>${n}</option>`).join("")}</select>`;
  const opc = (v, lst, k) => `<select data-k="${k}">${[...new Set([...lst, v || ""])].map(o => `<option ${o === (v || "") ? "selected" : ""}>${esc(o)}</option>`).join("")}</select>`;
  $("#tabIp").innerHTML = `<tr><th>km inicial</th><th>km final</th><th class=n>kmf</th><th>Panela</th><th>Remendo</th><th>Trincamento</th><th class=n>ICP</th><th>Condição</th><th>Intervenção primária</th><th>Secundária</th><th>Sugestão</th></tr>` +
    d.linhas.map((l, i) => [l, i]).filter(([l]) => (!soI || l.panela || l.remendo || l.trinca || l.primaria || l.secundaria) && (!soD || l.diverge)).map(([l, i]) =>
      `<tr data-ipl="${i}" class="${l.diverge ? "sit-conferir" : ""}"><td>${nf(l.km_ini, 3)}</td><td>${nf(l.km_fim, 3)}</td><td class=n>${nf(l.ext, 3)}</td>
       <td>${sel(l.panela, "panela")}</td><td>${sel(l.remendo, "remendo")}</td><td>${sel(l.trinca, "trinca")}</td><td class=n>${nf(l.icp, 1)}</td><td>${esc(l.condicao)}</td>
       <td>${opc(l.primaria, d.opcoes.primaria, "primaria")}</td><td>${opc(l.secundaria, d.opcoes.secundaria, "secundaria")}</td>
       <td><small>${esc(l.sugestao.filter(Boolean).join(" + ") || "—")}</small></td></tr>`).join("");
}
$("#ipSoInterv").onchange = desenharLinhasIp; $("#ipSoDiv").onchange = desenharLinhasIp;
function lerIp() {
  const linhas = IP_.d.linhas.map(l => ({ ...l }));
  $$("#tabIp tr[data-ipl]").forEach(tr => { const l = linhas[+tr.dataset.ipl];
    $$("select", tr).forEach(s => { l[s.dataset.k] = ["panela", "remendo", "trinca"].includes(s.dataset.k) ? +s.value : s.value; }); });
  const intervencoes = {};
  $$("#tabIpCalc tr[data-ipk]").forEach(tr => { intervencoes[tr.dataset.ipk] = Object.fromEntries($$("[data-p]", tr).map(i => [i.dataset.p, i.value === "" ? null : +i.value])); });
  return { linhas, parametros: { largura: $("#ipLarg") ? +$("#ipLarg").value : null, intervencoes } };
}
$("#btnIpSalvar").onclick = async () => { try { await jpost(`${base_}${E.pid}/ip`, lerIp(), "PUT"); toast("Levantamento salvo — PATO recalculado"); carregarOrc(); } catch (e) { erro(e); } };
$("#btnIpSug").onclick = async () => { try { await jpost(`${base_}${E.pid}/ip`, lerIp(), "PUT"); const r = await jpost(`${base_}${E.pid}/ip/sugestoes`, { so_vazias: true }); toast(`${r.aplicadas} km com intervenção sugerida`); carregarOrc(); } catch (e) { erro(e); } };
$("#btnIpGrade").onclick = async () => { if (IP_.d?.linhas?.length && !confirm("Substituir o levantamento atual por uma grade em branco (km a km, ida e volta)?")) return;
  try { await jpost(`${base_}${E.pid}/ip/grade`, { passo: 1, faixas: 2 }); toast("Grade criada"); carregarOrc(); } catch (e) { erro(e); } };
$("#btnIpImp").onclick = async () => { const a = await escolherArquivo(".xlsx,.xlsm"); if (!a) return; const fd = new FormData(); fd.append("arquivo", a);
  try { const r = await api(`${base_}${E.pid}/ip/importar`, { method: "POST", body: fd }); toast(`${r.linhas.length} linhas importadas`); carregarOrc(); } catch (e) { erro(e); } };

// ---- sinalização de obras
const SZ_ = { r: null };
async function renderSinal() {
  const r = SZ_.r = await api(`${base_}${E.pid}/sinalizacao`), d = r.dados, res = r.resultado;
  $("#szHd").value = d.horas_dia;
  if (!res) { $("#szTotais").innerHTML = '<p class="tag aviso">Sem cadastro de sinalização: importe a planilha PATO (abas DURACAO_SERVICOS, TEMPO_PROJETO_TIPO e UN_DIA).</p>'; }
  const cods = res ? [...new Set(Object.values(res.grupos).flatMap(g => Object.keys(g.codigos)))] : [];
  if (res) $("#szTotais").innerHTML = `<table class="tab"><tr><th>Código</th>${Object.entries(r.grupos).map(([k, v]) => `<th class=n>${esc(v)}</th>`).join("")}</tr>` +
    cods.map(c => `<tr><td>${esc(c)}</td>${Object.keys(r.grupos).map(g => `<td class=n>${nf(res.grupos[g].codigos[c] ?? 0, 3)}</td>`).join("")}</tr>`).join("") + "</table>";
  const tipoSel = (v, i) => `<select data-szt="${i}">${Object.entries(r.tipos_rotulo).map(([k, rot]) => `<option value="${k}" ${+k === +v ? "selected" : ""}>${k} — ${esc(rot)}</option>`).join("")}</select>`;
  $("#tabSzServ").innerHTML = `<tr><th>Grupo</th><th>Código</th><th>Descrição</th><th class=n>Quantidade</th><th class=n>Produção/h</th><th class=n>Horas</th><th>Projeto-tipo</th></tr>` +
    (res ? res.servicos : d.servicos).map((x, i) => `<tr><td>${esc(r.grupos[x.grupo] || x.grupo)}</td><td>${esc(x.codigo)}</td><td>${esc((x.descricao || "").slice(0, 60))}</td>
      <td class=n>${q3(x.quantidade)}</td><td class=n>${x.h_por_km ? `${nf(x.h_por_km)} h/km` : q3(x.producao)}</td><td class=n>${q3(x.horas)}</td><td>${tipoSel(x.tipo, i)}</td></tr>`).join("");
  const tps = Object.keys(d.tipos);
  $("#tabSzTipos").innerHTML = `<tr><th>Projeto-tipo</th><th class=n>Operadores</th>${res ? Object.values(r.grupos).map(g => `<th class=n>Horas / dias — ${esc(g)}</th>`).join("") : ""}</tr>` +
    tps.map(t => `<tr><td>${t} — ${esc(d.tipos[t].rotulo)}</td><td class=n><input data-szop="${t}" type="number" step="any" value="${d.tipos[t].operadores}" style="width:60px"></td>
      ${res ? Object.keys(r.grupos).map(g => { const x = res.grupos[g].tipos.find(y => +y.tipo === +t) || {}; return `<td class=n>${q3(x.horas)} h / ${nf(x.dias, 2)} d</td>`; }).join("") : ""}</tr>`).join("");
  $("#tabSzDisp").innerHTML = `<tr><th>Dispositivo</th><th>Código</th>${tps.map(t => `<th class=n>Tipo ${t}</th>`).join("")}</tr>` +
    d.dispositivos.map((x, i) => `<tr><td>${esc(x.chave)}<br><small>${esc(x.descricao || "")}</small></td><td>${esc(x.codigo || "—")}</td>
      ${tps.map(t => `<td class=n><input data-szd="${i}" data-t="${t}" type="number" step="any" value="${x.qtd[t] ?? 0}" style="width:60px"></td>`).join("")}</tr>`).join("");
}
$("#btnSzSalvar").onclick = async () => {
  const d = JSON.parse(JSON.stringify(SZ_.r.dados));
  d.horas_dia = +$("#szHd").value || 7.333;
  $$("[data-szt]").forEach(s => { d.servicos[+s.dataset.szt].tipo = +s.value; });
  $$("[data-szop]").forEach(i => { d.tipos[i.dataset.szop].operadores = +i.value; });
  $$("[data-szd]").forEach(i => { d.dispositivos[+i.dataset.szd].qtd[i.dataset.t] = +i.value; });
  try { await jpost(`${base_}${E.pid}/sinalizacao`, d, "PUT"); toast("Sinalização salva — PATO recalculado"); carregarOrc(); } catch (e) { erro(e); }
};

// ---- ADM local, canteiro, usina e mobilização
const DV_ = { r: null };
const dvIn = (path, v, w = 80, dica = "") => `<input data-dv="${path}" type="number" step="any" value="${v ?? ""}" style="width:${w}px" ${dica ? `data-dica="${esc(dica)}"` : ""}>`;
const dvTx = (path, v, w = 160) => `<input data-dvt="${path}" value="${esc(v ?? "")}" style="width:${w}px">`;
function seletorMetodologia(r) {
  return `<p><b>Metodologia:</b> <select id="dvModelo" data-dica="SICRO 2ª edição: Manual de Custos de 17/11/2025 (Vol. 06 a 08). Planilha de origem: reproduz a planilha BR-158/MT">
    ${Object.entries(r.modelos || {}).map(([k, v]) => `<option value="${k}" ${r.modelo === k ? "selected" : ""}>${esc(v)}</option>`).join("")}</select></p>`;
}
function ligarSeletorMetodologia() {
  const s = $("#dvModelo"); if (!s) return;
  s.onchange = () => { const d = lerDiv(); d.modelo = s.value; salvarDiv(d); };
}
async function renderDiv() {
  const r = DV_.r = await api(`${base_}${E.pid}/diversos`), d = r.dados, res = r.resultado;
  if (r.modelo === "sicro2025" && res) return renderDiv2025(r);
  if (!res) { $("#divResumo").innerHTML = '<p class="tag aviso">Sem base SICRO no projeto: importe a base na aba Custos.</p>'; ["#divAdm", "#divCan", "#divUsi", "#divMob"].forEach(s => $(s).innerHTML = ""); return; }
  const aviso = r.gravado ? "" : '<p class="tag aviso">Parâmetros do modelo BR-158/MT — ajuste e salve para este projeto.</p>';
  $("#divResumo").innerHTML = seletorMetodologia(r) + aviso + `<table class="tab"><tr><th>Código</th><th>Item</th><th class=n>Calculado SD</th><th class=n>Calculado CD</th><th class=n>Planilha de origem SD</th><th class=n>Planilha de origem CD</th><th>Fixar</th></tr>` +
    Object.entries(r.codigos).map(([c, nome]) => { const p = res.precos[c], f = r.referencia[c] || {};
      const dif = reg => f[reg] != null && Math.abs(f[reg] - p[reg]) > 0.005 ? ' class="n sit-conferir"' : " class=n";
      return `<tr><td>${c}</td><td>${esc(nome)}${c === "ADM" ? " (por mês)" : ""}</td><td class=n>${reais(p.SD)}</td><td class=n>${reais(p.CD)}</td>
        <td${dif("SD")}>${f.SD == null ? "—" : reais(f.SD)}</td><td${dif("CD")}>${f.CD == null ? "—" : reais(f.CD)}</td>
        <td><input type="checkbox" data-dvfix="${c}" ${r.fixos.includes(c) ? "checked" : ""} ${f.SD == null ? "disabled" : ""} data-dica="Usa o preço da planilha de origem em vez do calculado"></td></tr>`; }).join("") + "</table>";
  // ADM
  const a = res.adm, REGRA = { contrato: "meses do contrato", "contrato-1": "meses do contrato − 1", ela: "equipes de laboratório (ELA)" };
  $("#divAdm").innerHTML = a.parcelas.map((p, i) => `<h5>${esc(p.titulo || p.chave)} — ${q3(p.meses)} meses <small>(${esc(REGRA[p.regra] || "informado")})</small></h5>
    <table class="tab"><tr><th>Código</th><th>Descrição</th><th class=n>Quant.</th><th class=n>h prod/mês</th><th class=n>h improd/mês</th><th class=n>Unit. SD</th><th class=n>Total/mês SD</th><th class=n>Unit. CD</th><th class=n>Total/mês CD</th></tr>` +
    p.mao_obra.map((x, j) => `<tr><td>${esc(x.codigo)}</td><td>${esc(x.descricao || "")}</td><td class=n>${dvIn(`adm.parcelas.${i}.mao_obra.${j}.quant`, x.quant, 70)}</td><td></td><td></td>
      <td class=n>${reais(x.preco_SD)}</td><td class=n>${reais(x.total_SD)}</td><td class=n>${reais(x.preco_CD)}</td><td class=n>${reais(x.total_CD)}</td></tr>`).join("") +
    p.veiculos.map((x, j) => `<tr><td>${esc(x.codigo)}</td><td>${esc(x.descricao || "")}</td><td class=n>${dvIn(`adm.parcelas.${i}.veiculos.${j}.quant`, x.quant, 70)}</td>
      <td class=n>${dvIn(`adm.parcelas.${i}.veiculos.${j}.h_prod`, x.h_prod, 70)}</td><td class=n>${dvIn(`adm.parcelas.${i}.veiculos.${j}.h_improd`, x.h_improd, 84)}</td>
      <td class=n>${nf(x.chp_SD, 4)} / ${nf(x.chi_SD, 4)}</td><td class=n>${reais(x.total_SD)}</td><td class=n>${nf(x.chp_CD, 4)} / ${nf(x.chi_CD, 4)}</td><td class=n>${reais(x.total_CD)}</td></tr>`).join("") +
    `<tr class="tot"><td colspan=6>Total da parcela (× meses)</td><td class=n>${reais(p.total_SD)}</td><td></td><td class=n>${reais(p.total_CD)}</td></tr></table>`).join("") +
    `<h5>Equipes de laboratório (parcela variável): ELA = Σ ARRED(quantidade no contrato ÷ QE; 5) = ${nf(a.ela, 5)}</h5>
    <table class="tab"><tr><th>Código</th><th>Serviço</th><th class=n>Quantidade no contrato</th><th class=n>QE</th><th class=n>ELA</th></tr>` +
    a.ela_linhas.map((x, j) => `<tr><td>${esc(x.codigo)}</td><td>${esc((x.descricao || "").slice(0, 70))}</td><td class=n>${q3(x.quantidade)}</td>
      <td class=n>${dvIn(`adm.ela.${j}.qe`, x.qe, 100)}</td><td class=n>${nf(x.ela, 5)}</td></tr>`).join("") + "</table>" +
    `<p>Despesas diversas ${dvIn("adm.despesas_pct", a.despesas_pct, 60)} % · Custo SD R$ ${reais(a.SD.custo)} · CD R$ ${reais(a.CD.custo)} ·
      Preço SD R$ ${reais(a.SD.preco)} (R$ ${reais(a.SD.mensal)}/mês) · CD R$ ${reais(a.CD.preco)} (R$ ${reais(a.CD.mensal)}/mês) · ${q3(a.meses)} meses</p>`;
  // canteiro
  const c = res.canteiro, dc = d.canteiro || {}, f = c.funcionarios;
  $("#divCan").innerHTML = `<p>Funcionários: fixa ${q3(f.fixa)} · vinculada ${q3(f.vinculada)} · variável ${q3(f.variavel)} · mão de obra ordinária (NMO) ${dvIn("canteiro.nmo", dc.nmo, 70)} · NMAX ${q3(f.nmax)}</p>
    <table class="tab"><tr><th>Área</th><th>Regra</th><th class=n>Área (m²)</th><th class=n>FEAC</th><th class=n>Equivalente</th></tr>` +
    c.areas.map((x, i) => `<tr><td>${esc(x.nome)}</td><td><small>${esc(x.formula)}</small></td><td class=n>${i >= 4 ? dvIn(`canteiro.areas_fixas.${i - 4}.area`, x.area, 80) : nf(x.area, 4)}</td>
      <td class=n>${dvIn(i >= 4 ? `canteiro.areas_fixas.${i - 4}.feac` : `canteiro.feac_${["escritorio", "refeitorio", "alojamento", "banheiros"][i]}`, x.feac, 55)}</td><td class=n>${nf(x.equivalente, 2)}</td></tr>`).join("") +
    `<tr class="tot"><td colspan=4>AC (área coberta equivalente)</td><td class=n>${nf(c.ac, 2)}</td></tr></table>
    <p>k1 ${dvIn("canteiro.k1", dc.k1, 60)} · k2 ${dvIn("canteiro.k2", dc.k2, 60)} · distância aos centros fornecedores ${dvIn("canteiro.distancia_km", dc.distancia_km, 60)} km (k3 = ${nf(c.k3, 4)}) · FEAD ${dvIn("canteiro.fead", dc.fead, 70)}</p>
    <p>CMCC (custo médio da construção civil, R$/m²): SD ${dvIn("canteiro.cmcc.SD", (dc.cmcc || {}).SD, 90)} · CD ${dvIn("canteiro.cmcc.CD", (dc.cmcc || {}).CD, 90)}</p>
    <p>CCO = (k1·k2·k3·AC + AD·FEAD)·CMCC → SD R$ ${reais(c.SD.custo)} · CD R$ ${reais(c.CD.custo)}<br><b>PCO SD R$ ${reais(c.SD.preco)} · CD R$ ${reais(c.CD.preco)}</b></p>`;
  const u = res.usina;
  $("#divUsi").innerHTML = `<table class="tab"><tr><th>Área coberta</th><th class=n>Área (m²)</th><th class=n>FEAC</th><th class=n>Equivalente</th></tr>` +
    u.areas.map((x, i) => `<tr><td>${esc(x.nome)}</td><td class=n>${dvIn(`usina.areas.${i}.area`, x.area, 70)}</td><td class=n>${dvIn(`usina.areas.${i}.feac`, x.feac, 55)}</td><td class=n>${nf(x.equivalente, 2)}</td></tr>`).join("") +
    `</table><p>Instalação da usina: composição ${dvTx("usina.codigo_instalacao", u.codigo_instalacao, 90)} — custo direto SD R$ ${reais(u.SD.instalacao)} · CD R$ ${reais(u.CD.instalacao)}</p>
    <p>CCO = k1·k2·k3·AC·CMCC + instalação → SD R$ ${reais(u.SD.custo)} · CD R$ ${reais(u.CD.custo)}<br><b>PCO SD R$ ${reais(u.SD.preco)} · CD R$ ${reais(u.CD.preco)}</b></p>
    <p class="nota">A planilha BR-158/MT soma, na condição com desoneração, o custo da instalação sem desoneração (USINA!H38 usa F22): o sistema usa o custo com desoneração.</p>`;
  const m = res.mob, dm = d.mob || {}, ps = m.pessoal;
  $("#divMob").innerHTML = `<p>Pessoal: ${ps.quantidade} motoristas/operadores (50% dos equipamentos) × passagem R$ ${reais(ps.passagem)} — itinerário ${dvTx("mob.itinerario", dm.itinerario, 200)} ·
      passagem pesquisada R$ ${dvIn("mob.passagem", dm.passagem, 80)} · mês do índice da pesquisa ${dvTx("mob.mes_indice_pesquisa", dm.mes_indice_pesquisa, 80)}
      (${esc(ps.indice)}: ${ps.a ? `${nf(ps.a, 2)} → ${nf(ps.b, 2)}` : "sem índice — fator da planilha"}, reajuste ${nf(ps.fator * 100, 4)}%)</p>
    <div class="tabela-rolagem" style="max-height:420px"><table class="tab"><tr><th>Código</th><th>Equipamento</th><th>Veículo transp.</th><th class=n>Quant.</th><th class=n>DMT pav</th><th class=n>DMT npav</th><th class=n>v pav</th><th class=n>v npav</th>
      <th class=n>Viagem (h)</th><th class=n>Descanso (h)</th><th class=n>FU</th><th class=n>Custo SD</th><th class=n>Custo CD</th><th></th></tr>` +
    m.equipamentos.map((x, i) => `<tr><td>${esc(x.codigo)}</td><td><small>${esc(x.descricao || "")}</small></td><td>${dvTx(`mob.equipamentos.${i}.transporte`, x.transporte, 70)}</td>
      <td class=n>${dvIn(`mob.equipamentos.${i}.quant`, x.quant, 50)}</td><td class=n>${dvIn(`mob.equipamentos.${i}.dmt_pav`, x.dmt_pav, 60)}</td><td class=n>${dvIn(`mob.equipamentos.${i}.dmt_npav`, x.dmt_npav, 60)}</td>
      <td class=n>${dvIn(`mob.equipamentos.${i}.vel_pav`, x.vel_pav, 58)}</td><td class=n>${dvIn(`mob.equipamentos.${i}.vel_npav`, x.vel_npav, 58)}</td>
      <td class=n>${nf(x.tempo_viagem, 4)}</td><td class=n>${nf(x.tempo_descanso, 1)}</td><td class=n>${dvIn(`mob.equipamentos.${i}.fu`, x.fu, 64)}</td>
      <td class=n>${reais(x.custo_SD)}</td><td class=n>${reais(x.custo_CD)}</td><td><button class="btn mini" data-dvrem="${i}" data-dica="Retira o equipamento da mobilização">×</button></td></tr>`).join("") +
    `</table></div><p>Custo SD R$ ${reais(m.SD.custo)} · CD R$ ${reais(m.CD.custo)} → <b>MOB = DESMOB: SD R$ ${reais(m.SD.preco)} · CD R$ ${reais(m.CD.preco)}</b></p>`;
  $$("[data-dvrem]").forEach(b => b.onclick = () => { const dd = lerDiv(); dd.mob.equipamentos.splice(+b.dataset.dvrem, 1); salvarDiv(dd); });
  ligarSeletorMetodologia();
}
function tabelaPrecosDiv(r, res) {
  return `<table class="tab"><tr><th>Código</th><th>Item</th><th class=n>Calculado SD</th><th class=n>Calculado CD</th><th class=n>Planilha de origem SD</th><th class=n>Planilha de origem CD</th><th>Fixar</th></tr>` +
    Object.entries(r.codigos).map(([c, nome]) => { const p = res.precos[c], f = r.referencia[c] || {};
      return `<tr><td>${c}</td><td>${esc(nome)}${c === "ADM" ? " (por mês)" : ""}</td><td class=n>${reais(p.SD)}</td><td class=n>${reais(p.CD)}</td>
        <td class=n>${f.SD == null ? "—" : reais(f.SD)}</td><td class=n>${f.CD == null ? "—" : reais(f.CD)}</td>
        <td><input type="checkbox" data-dvfix="${c}" ${r.fixos.includes(c) ? "checked" : ""} ${f.SD == null ? "disabled" : ""}></td></tr>`; }).join("") + "</table>";
}
function renderDiv2025(r) {
  const s = r.dados.sicro2025, res = r.resultado, P = "sicro2025.";
  const REG = { contrato: "meses do contrato", "contrato-1": "meses do contrato − 1", ela: "ELA (laboratório)", manejo: "Tf (manejo florestal)" };
  $("#divResumo").innerHTML = seletorMetodologia(r) + `<p class="nota">Planilha de origem com os ajustes da 2ª edição do Manual de Custos (17/11/2025): administração local
    + manejo florestal; canteiro pelo método construtivo (instalação provisória, Vol. 06) com a distância ao centro fornecedor; usina corrigida;
    mobilização com descanso a cada 4 h e distância a partir da capital mais próxima.</p>` + tabelaPrecosDiv(r, res);
  const a = res.adm;
  $("#divAdm").innerHTML = a.parcelas.map((p, i) => `<h5>${esc(p.titulo || p.chave)} — ${q3(p.meses)} meses <small>(${esc(REG[p.regra] || "informado")})</small></h5>
    <table class="tab"><tr><th>Código</th><th>Descrição</th><th class=n>Quant.</th><th class=n>h prod / h improd (mês)</th><th class=n>Unit. SD</th><th class=n>Total/mês SD</th><th class=n>Total/mês CD</th></tr>` +
    p.mao_obra.map((x, j) => `<tr><td>${esc(x.codigo)}</td><td>${esc(x.descricao || "")}</td><td class=n>${dvIn(`${P}adm.parcelas.${i}.mao_obra.${j}.quant`, x.quant, 70)}</td><td></td>
      <td class=n>${reais(x.preco_SD)}</td><td class=n>${reais(x.total_SD)}</td><td class=n>${reais(x.total_CD)}</td></tr>`).join("") +
    (p.veiculos || []).map((x, j) => `<tr><td>${esc(x.codigo)}</td><td>${esc(x.descricao || "")}</td><td class=n>${dvIn(`${P}adm.parcelas.${i}.veiculos.${j}.quant`, x.quant, 70)}</td>
      <td class=n>${nf(x.h_prod, 2)} / ${nf(x.h_improd, 2)}</td><td class=n>${nf(x.chp_SD, 4)} / ${nf(x.chi_SD, 4)}</td><td class=n>${reais(x.total_SD)}</td><td class=n>${reais(x.total_CD)}</td></tr>`).join("") +
    `<tr class="tot"><td colspan=5>Total da parcela (× meses)</td><td class=n>${reais(p.total_SD)}</td><td class=n>${reais(p.total_CD)}</td></tr></table>`).join("") +
    `<h5>Laboratório: ELA = Σ ARRED(quantidade no contrato ÷ QE) = ${nf(a.ela, 5)}</h5><table class="tab"><tr><th>Código</th><th>Serviço</th><th class=n>Quantidade no contrato</th><th class=n>QE</th><th class=n>ELA</th></tr>` +
    a.ela_linhas.map((x, j) => `<tr><td>${esc(x.codigo)}</td><td>${esc((x.descricao || "").slice(0, 70))}</td><td class=n>${q3(x.quantidade)}</td><td class=n>${dvIn(`${P}adm.ela.${j}.qe`, x.qe, 100)}</td><td class=n>${nf(x.ela, 5)}</td></tr>`).join("") + "</table>" +
    `<h5>Manejo florestal (técnico florestal): Tf = Σ ARRED(quantidade ÷ (produção horária × ${nf(s.adm.horas_mes, 2)} h); 2) = ${nf(a.tf, 2)} meses</h5>
    <table class="tab"><tr><th>Código</th><th class=n>Quantidade no contrato</th><th class=n>Produção/h (composição)</th><th class=n>Tf (meses)</th></tr>` +
    (a.tf_linhas || []).map(x => `<tr><td>${esc(x.codigo)}</td><td class=n>${q3(x.quantidade)}</td><td class=n>${q3(x.producao)}</td><td class=n>${nf(x.tf, 2)}</td></tr>`).join("") + "</table>" +
    `<p>Despesas diversas ${dvIn(P + "adm.despesas_pct", a.despesas_pct, 60)} % · Preço SD R$ ${reais(a.SD.preco)} (R$ ${reais(a.SD.mensal)}/mês) · CD R$ ${reais(a.CD.preco)} (R$ ${reais(a.CD.mensal)}/mês)</p>`;
  const c = res.canteiro, sc = s.canteiro, f = c.funcionarios, cf = sc.centro_fornecedor || {}, loc = r.locais || {};
  $("#divCan").innerHTML = `<p><b>Centro fornecedor</b> (capital, centro sede ou cidade com suporte mais próxima):
      <select data-dvt="${P}canteiro.centro_fornecedor.modo"><option value="croqui" ${cf.modo !== "manual" ? "selected" : ""}>medir no croqui</option><option value="manual" ${cf.modo === "manual" ? "selected" : ""}>informar a distância</option></select>
      <select data-dvt="${P}canteiro.centro_fornecedor.nome">${(loc.locais || []).map(l => `<option ${l.nome === cf.nome ? "selected" : ""}>${esc(l.nome)}</option>`).join("")}</select>
      <small>canteiro no km ${loc.km_canteiro ?? "—"}</small></p>
    <p>Funcionários: fixa ${q3(f.fixa)} · vinculada ${q3(f.vinculada)} · variável ${q3(f.variavel)} · mão de obra ordinária no pico ${dvIn(P + "canteiro.mo_pico", sc.mo_pico, 70)} → NMO ${nf(f.nmo, 2)} · NMAX ${q3(f.nmax)}</p>
    <table class="tab"><tr><th>Área</th><th>Regra</th><th class=n>Área (m²)</th><th class=n>FEAC</th><th class=n>Equivalente</th></tr>` +
    c.areas.map((x, i) => `<tr><td>${esc(x.nome)}</td><td><small>${esc(x.formula)}</small></td><td class=n>${i >= 4 ? dvIn(`${P}canteiro.areas_fixas.${i - 4}.area`, x.area, 80) : nf(x.area, 4)}</td><td class=n>${nf(x.feac, 2)}</td><td class=n>${nf(x.equivalente, 2)}</td></tr>`).join("") +
    `<tr class="tot"><td colspan=4>AC (= AD)</td><td class=n>${nf(c.ac, 2)}</td></tr></table>
    <p>k1 ${dvIn(P + "canteiro.k1", sc.k1, 60)} · k2 ${dvIn(P + "canteiro.k2", sc.k2, 60)} · DT (km): pavimentada ${dvIn(P + "canteiro.dt.pav", c.dt?.pav, 60)} · revestimento primário ${dvIn(P + "canteiro.dt.rp", c.dt?.rp, 60)}
      · leito natural ${dvIn(P + "canteiro.dt.leito", c.dt?.leito, 60)} → k3 = ${nf(c.k3, 4)} · FEAD ${dvIn(P + "canteiro.fead", sc.fead, 60)}</p>
    <p>CMCC SD ${dvIn(P + "canteiro.cmcc.SD", sc.cmcc?.SD, 90)} · CD ${dvIn(P + "canteiro.cmcc.CD", sc.cmcc?.CD, 90)} → <b>PCO SD R$ ${reais(c.SD.preco)} · CD R$ ${reais(c.CD.preco)}</b></p>`;
  const u = res.usina;
  $("#divUsi").innerHTML = `<table class="tab"><tr><th>Área coberta</th><th class=n>Área (m²)</th><th class=n>FEAC</th><th class=n>Equivalente</th></tr>` +
    u.areas.map((x, i) => `<tr><td>${esc(x.nome)}</td><td class=n>${dvIn(`${P}usina.areas.${i}.area`, x.area, 70)}</td><td class=n>${nf(x.feac, 2)}</td><td class=n>${nf(x.equivalente, 2)}</td></tr>`).join("") +
    `</table><p>k1 ${nf(u.k1, 2)} · k2 ${dvIn(P + "usina.k2", s.usina.k2, 60)} · k3 ${nf(u.k3, 4)} (centro fornecedor do canteiro) · instalação ${dvTx(P + "usina.codigo_instalacao", u.codigo_instalacao, 90)}:
      SD R$ ${reais(u.SD.instalacao)} · CD R$ ${reais(u.CD.instalacao)}</p>
    <p>CCO = (k1·k2·k3·AC + AD·FEAD)·CMCC + instalação → <b>PCO SD R$ ${reais(u.SD.preco)} · CD R$ ${reais(u.CD.preco)}</b></p>`;
  const m = res.mob, sm = s.mob, ps = m.pessoal, o = sm.origem || {};
  $("#divMob").innerHTML = `<p><b>Origem: capital mais próxima</b> ${dvTx(P + "mob.origem.capital", o.capital, 140)} → ${dvTx(P + "mob.origem.destino", o.destino, 140)} ·
      distância rodoviária pavimentada ${dvIn(P + "mob.origem.dmt_pav", o.dmt_pav, 70)} km · não pavimentada ${dvIn(P + "mob.origem.dmt_npav", o.dmt_npav, 70)} km
      <br><small>Sugestão pelo canteiro (linha reta): ${(r.capitais || []).map(x => `${esc(x.capital)} ${nf(x.linha_reta_km, 0)} km`).join(" · ") || "—"} — confirme a distância pela rodovia.</small></p>
    <p>Pessoal: ${ps.quantidade} motoristas/operadores × passagem R$ ${reais(ps.passagem)} (pesquisada ${dvIn(P + "mob.passagem", sm.passagem, 80)}) ·
      descanso de ${nf(sm.tempo_descanso, 1)} h a cada ${dvIn(P + "mob.horas_entre_descansos", sm.horas_entre_descansos, 45)} h de viagem</p>
    <div class="tabela-rolagem" style="max-height:420px"><table class="tab"><tr><th>Código</th><th>Equipamento</th><th>Transportador</th><th class=n>Quant.</th><th class=n>FU</th>
      <th class=n>Viagem (h)</th><th class=n>Descansos</th><th class=n>Descanso (h)</th><th class=n>Custo SD</th><th class=n>Custo CD</th></tr>` +
    m.equipamentos.map((x, i) => `<tr><td>${esc(x.codigo)}</td><td><small>${esc(x.descricao || "")}</small></td><td>${dvTx(`${P}mob.equipamentos.${i}.transporte`, x.transporte, 64)}</td>
      <td class=n>${dvIn(`${P}mob.equipamentos.${i}.quant`, x.quant, 45)}</td><td class=n>${dvIn(`${P}mob.equipamentos.${i}.fu`, x.fu, 55)}</td>
      <td class=n>${nf(x.tempo_viagem, 4)}</td><td class=n>${x.descansos}</td><td class=n>${nf(x.tempo_descanso, 1)}</td><td class=n>${reais(x.custo_SD)}</td><td class=n>${reais(x.custo_CD)}</td></tr>`).join("") +
    `</table></div><p>Custo SD R$ ${reais(m.SD.custo)} · CD R$ ${reais(m.CD.custo)} → <b>MOB = DESMOB: SD R$ ${reais(m.SD.preco)} · CD R$ ${reais(m.CD.preco)}</b></p>`;
  ligarSeletorMetodologia();
}
function lerDiv() {
  const d = JSON.parse(JSON.stringify(DV_.r.dados));
  const por = (path, v) => { const ks = path.split("."); let o = d; ks.slice(0, -1).forEach(k => { o[k] ??= {}; o = o[k]; }); o[ks.at(-1)] = v; };
  $$("[data-dv]").forEach(i => por(i.dataset.dv, i.value === "" ? null : +i.value));
  $$("[data-dvt]").forEach(i => por(i.dataset.dvt, i.value.trim() || null));
  return d;
}
async function salvarDiv(d) {
  const fixos = $$("[data-dvfix]").filter(c => c.checked).map(c => c.dataset.dvfix);
  try { await jpost(`${base_}${E.pid}/diversos`, { dados: d, fixos }, "PUT"); toast("Parâmetros salvos — PATO recalculado"); carregarOrc(); } catch (e) { erro(e); }
}
$("#btnDivSalvar").onclick = () => salvarDiv(lerDiv());
$("#btnDivSug").onclick = async () => {
  try { const l = await api(`${base_}${E.pid}/diversos/sugerir-mob`); if (!l.length) return toast("Nenhum equipamento com transporte rodoviário nas composições");
    if (!confirm(`Substituir a lista da mobilização por ${l.length} equipamentos das composições do PATO?`)) return;
    const d = lerDiv();
    if (d.modelo === "sicro2025" && d.sicro2025) {
      const ant = d.sicro2025.mob.equipamentos[0] || {};
      d.sicro2025.mob.equipamentos = l.map(x => ({ ...x, dmt_pav: ant.dmt_pav ?? 0, dmt_npav: ant.dmt_npav ?? 0, vel_pav: ant.vel_pav ?? 60, vel_npav: ant.vel_npav ?? 50, k: 1 }));
    } else {
      const ant = d.mob.equipamentos[0] || {};
      d.mob.equipamentos = l.map(x => ({ ...x, dmt_pav: ant.dmt_pav ?? 0, dmt_npav: ant.dmt_npav ?? 0, vel_pav: ant.vel_pav ?? 60, vel_npav: ant.vel_npav ?? 50, k: 1 }));
    }
    salvarDiv(d); } catch (e) { erro(e); }
};

// ---------------------------------------------------------------- base de conhecimento
const NM_ = { r: null };
const SIT_CLASSE = { revogado: "erro", substituido: "erro", modelo_antigo: "aviso", parcial: "aviso", vigente_confirmar: "", vigente: "ok", referencia: "" };
async function carregarNormas() {
  const r = NM_.r = await api("/api/base/documentos"), docs = r.documentos;
  const cats = [...new Set(docs.map(d => d.categoria))].sort();
  if ($("#nmCat").options.length <= 1) $("#nmCat").insertAdjacentHTML("beforeend", cats.map(c => `<option>${esc(c)}</option>`).join(""));
  const cont = {}; docs.forEach(d => cont[d.situacao_txt] = (cont[d.situacao_txt] || 0) + 1);
  $("#nmResumo").innerHTML = `<p>${docs.length} documentos · ${Object.entries(cont).map(([k, v]) => `${esc(k)}: <b>${v}</b>`).join(" · ")} · retirados da busca: <b>${docs.filter(d => d.retirar).length}</b></p>`;
  $("#tabNm").innerHTML = `<tr><th>Situação</th><th>Documento</th><th>Categoria</th><th>Identificação</th><th>Nota / substituto</th><th></th></tr>` +
    docs.map(d => `<tr><td><span class="tag ${SIT_CLASSE[d.situacao] || ""}">${esc(d.situacao_txt)}</span>${d.retirar ? "<br><small>fora da busca</small>" : ""}</td>
      <td>${esc(d.titulo)}${d.pacote ? `<br><small>pacote: ${esc(d.pacote)}</small>` : ""}</td><td>${esc(d.categoria)}</td><td>${esc(d.identificacao || "—")}</td>
      <td><small>${esc(d.nota || "")}${d.substituto ? `<br><b>Substituto:</b> ${esc(d.substituto)}` : ""}${d.evidencia ? `<br><i>Evidência:</i> ${esc(d.evidencia)}` : ""}
        ${(d.cita_desatualizado || []).map(c => `<br>⚠ cita ${esc(c.citada)} (p. ${c.pagina}) — atual: ${esc(c.mais_nova)}`).join("")}</small></td>
      <td><button class="btn mini" data-nmdoc="${d.id}">Ler</button></td></tr>`).join("");
  $("#tabNmExt").innerHTML = `<tr><th>Ato</th><th>Situação</th><th>Substituto</th><th>Evidência</th></tr>` +
    (r.externos || []).map(x => `<tr><td>${esc(x.identificacao)}</td><td><span class="tag erro">${esc(r.situacoes[x.situacao] || x.situacao)}</span></td><td>${esc(x.substituto || "")}</td><td><small>${esc(x.evidencia || "")}</small></td></tr>`).join("");
  ligarLerNorma();
}
function ligarLerNorma() {
  $$("[data-nmdoc]").forEach(b => b.onclick = async () => {
    const d = await api(`/api/base/documento/${encodeURIComponent(b.dataset.nmdoc)}${b.dataset.pg ? `?pagina=${b.dataset.pg}` : ""}`);
    $("#dlgNmTxt").textContent = `${d.titulo}${d.pagina ? ` — página ${d.pagina}` : ""}\n\n${(d.texto || "").replace(/\f/g, "\n\n———— página ————\n\n")}`;
    $("#dlgNm").showModal();
  });
}
async function buscarNormas() {
  const q = $("#nmQ").value.trim(); if (!q) return;
  const r = await api(`/api/base/buscar?q=${encodeURIComponent(q)}&categoria=${encodeURIComponent($("#nmCat").value)}&retirados=${$("#nmRet").checked}`);
  $("#nmRes").innerHTML = r.length ? r.map(x => `<div class="caixa" style="margin:6px 0;padding:8px"><b>${esc(x.titulo)}</b> · p. ${x.pagina} · <small>${esc(x.categoria)}</small>
      ${x.situacao && x.situacao !== "vigente" ? ` <span class="tag ${SIT_CLASSE[x.situacao] || ""}">${esc(NM_.r?.situacoes?.[x.situacao] || x.situacao)}</span>` : ""}
      <p style="margin:4px 0">${esc(x.trecho)}</p><button class="btn mini" data-nmdoc="${x.id}" data-pg="${x.pagina}">Ler a página</button>
      ${x.original ? ` <a class="btn mini" href="/api/base/original/${encodeURIComponent(x.id)}" target="_blank">Original</a>` : ""}</div>`).join("")
    : '<p class="nota">Nada encontrado.</p>';
  ligarLerNorma();
}
$("#btnNmBuscar").onclick = buscarNormas;
$("#nmQ").onkeydown = e => { if (e.key === "Enter") buscarNormas(); };

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
$("#btnDuplicar").onclick = async () => { const atual = E.projetos.find(x => x.id === E.pid) || {}; const n = prompt("Nome do novo projeto:", `${atual.nome || "Projeto"} (cópia)`); if (!n) return;
  try { const p = await jpost(`/api/projetos/${E.pid}/duplicar`, { nome: n }); limparEstadoProjeto(); await carregarProjetos(p.id); toast("Cópia completa criada — você está agora na cópia"); renderProjeto(); } catch (e) { erro(e); } };
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
        <div class="linha-botoes"><button class="btn primario" data-dica="Grava os itens; o sistema já aplica as correções certas e lista as decisões na aba Revisão">Confirmar importação</button></div></form></div>
      <h4>Nomenclatura × Álbum DNIT (IPR-736) — sugestões que irão para a aba Revisão</h4>
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
      box.innerHTML = `<p class="ok-msg">${res.importados} itens importados em “${esc(res.projeto.nome)}”. ${res.ajustes_automaticos} ajustes automáticos (aba Ajustes) e ${res.sugestoes} decisões pendentes (aba Revisão).</p>`;
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
    box.innerHTML = `<div class="linha-botoes">${linkBaixar(r)}<button class="btn" id="btnConferir" data-dica="Recalcula a planilha gerada (LibreOffice) e mostra os totais do PATO">Conferir totais (LibreOffice)</button></div>
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

$("#formRelPontos").onsubmit = async e => {
  e.preventDefault();
  const v = formObj(e.target), box = $("#resRelPontos");
  box.innerHTML = `<p class="carregando">Gerando relatório…</p>`;
  try {
    const r = await jpost(`/api/projetos/${E.pid}/relatorio-pontos`, v);
    box.innerHTML = `<p class="nota">${r.pontos} pontos: ${Object.entries(r.por_acao).map(([k, n]) => `${esc(k)} (${n})`).join(" · ") || "nenhum"}</p>
      <div class="linha-botoes">${linkBaixar(r)}</div>`;
  } catch (er) { box.innerHTML = `<p class="tag erro">${esc(er.message)}</p>`; }
};

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
