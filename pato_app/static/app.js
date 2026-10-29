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
  const subs = [["servicos", "Serviços e composições", "Escolha os serviços e veja/ajuste as composições"], ["insumos", "Insumos", "Preços dos insumos usados nos serviços escolhidos"],
    ["alteracoes", "Alterações", "Registro das alterações de custo, com desfazer"], ["base", "Base e BDI", "Base SICRO do projeto, BDI e importação de novas bases"],
    ["database", "Trocar data-base", "Compare e passe o projeto para outra data-base"]];
  $("#chipsCustos").innerHTML = subs.map(([k, r, d]) => `<span class="chip ${C_.sub === k ? "ativo" : ""}" data-sub="${k}" data-dica="${d}">${r}</span>`).join("");
  $$("#chipsCustos .chip").forEach(ch => ch.onclick = () => { C_.sub = ch.dataset.sub; carregarCustos(); });
  $$(".sub-custos").forEach(el => el.classList.toggle("ativa", el.id === "cst-" + C_.sub));
  ({ servicos: renderServicos, insumos: renderInsumos, alteracoes: renderAltCusto, base: renderBaseCfg, database: renderDataBase })[C_.sub]().catch(erro);
}

// ---- base e BDI
async function renderBaseCfg() {
  const c = C_.cfg, f = $("#formCfgCustos");
  f.base.innerHTML = c.disponiveis.map(d => `<option value="${d.uf}|${d.data_base}">${d.uf} — ${d.data_base} (${d.regimes.map(r => REG[r]).join(", ")})</option>`).join("");
  f.base.value = `${c.uf}|${c.data_base}`; f.regime.value = c.regime;
  f.bdi_sd.value = (c.bdi.SD * 100).toFixed(2); f.bdi_cd.value = (c.bdi.CD * 100).toFixed(2);
  $("#parcelasBdi").innerHTML = ["SD", "CD"].map(r => `<div><h4>${REG[r]}</h4>${Object.entries(c.rotulos_parcelas).map(([k, rot]) =>
    `<label style="display:flex;justify-content:space-between;gap:8px;font-size:12px;margin:3px 0">${esc(rot)} <input data-reg="${r}" data-par="${k}" type="number" step="0.0001" value="${c.parcelas[r]?.[k] ?? 0}" style="width:90px"></label>`).join("")}</div>`).join("");
  const bases = await api("/api/custos/bases");
  $("#tabBases").innerHTML = "<tr><th>UF</th><th>Data-base</th><th>Regime</th><th class=n>Composições</th><th class=n>Lista sintética</th><th>Origem</th><th></th></tr>" +
    bases.map(b => `<tr><td>${esc(b.uf)}</td><td>${esc(b.data_base)}</td><td>${esc(REG[b.regime] || b.regime)}</td><td class=n>${b.n_composicoes}</td><td class=n>${b.n_sintetico || 0}</td>
      <td><small>${esc(b.origem || "")}</small></td><td><button class="btn mini perigo" data-exb="${b.id}" data-dica="Remove esta base do sistema">Excluir</button></td></tr>`).join("");
  $$("[data-exb]").forEach(b => b.onclick = async () => { if (!confirm("Excluir esta base?")) return; await api(`/api/custos/bases/${b.dataset.exb}`, { method: "DELETE" }); carregarCustos(); });
}
$("#btnCalcBdi").onclick = () => {
  const par = { SD: {}, CD: {} };
  $$("#parcelasBdi input").forEach(i => par[i.dataset.reg][i.dataset.par] = +i.value);
  const calc = p => ((1 + (p.ac + p.lucro) / 100) / (1 - (p.df + p.seguros + p.riscos + p.pis + p.cofins + p.iss + p.cprb) / 100) - 1) * 100;
  $("#formCfgCustos").bdi_sd.value = calc(par.SD).toFixed(2); $("#formCfgCustos").bdi_cd.value = calc(par.CD).toFixed(2);
  C_.parcelas = par; toast("BDI calculado — clique em Salvar para gravar");
};
$("#formCfgCustos").onsubmit = async e => {
  e.preventDefault();
  const f = e.target, [uf, data_base] = f.base.value.split("|");
  try {
    await jpost(`${base_}${E.pid}/custos/config`, { uf, data_base, regime: f.regime.value, bdi_sd: +f.bdi_sd.value, bdi_cd: +f.bdi_cd.value, ...(C_.parcelas ? { parcelas: C_.parcelas } : {}) }, "PUT");
    // BDI digitado prevalece sobre as parcelas
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
  $("#tabServicos").innerHTML = `<tr><th>Código</th><th>Serviço</th><th>Unid.</th><th class=n>Preço ${REG.SD}</th><th class=n>Preço ${REG.CD}</th><th></th></tr>` +
    (r.servicos.map(s => `<tr><td>${esc(s.codigo)}</td><td>${esc(s.descricao || "")}${s.analitica ? "" : ' <span class="tag" data-dica="A base não tem o relatório analítico desta composição; o preço vem da lista sintética">sem analítico</span>'}</td>
      <td>${esc(s.unidade || "")}</td><td class=n>${cel(s, "SD")}</td><td class=n>${cel(s, "CD")}</td>
      <td><div class="linha-botoes" style="margin:0">${s.analitica ? `<button class="btn mini" data-vcomp="${esc(s.codigo)}" data-dica="Abre a composição analítica para ver e ajustar">Composição</button>` : ""}
      <button class="btn mini perigo" data-rserv="${esc(s.codigo)}" data-dica="Tira o serviço da lista do projeto">Remover</button></div></td></tr>`).join("")
      || `<tr><td colspan=6 class="nota">Nenhum serviço escolhido. Busque abaixo e clique em Adicionar.</td></tr>`);
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
        <td><button class="btn mini" data-saveq="${esc(e.codigo)}" data-dica="Grava o novo custo horário do equipamento">✓</button></td></tr>`).join("")}
      <tr class="tot"><td colspan=7>Custo horário de equipamentos</td><td class=n>${n4(x.total_equipamentos)}</td><td></td></tr></table>
    <h4>B — Mão de obra</h4><table class="tab"><tr><th>Código</th><th>Descrição</th><th class=n>Quant.</th><th>Custo horário</th><th class=n>Total</th><th></th></tr>
      ${x.mao_obra.map(m => `<tr><td>${esc(m.codigo)}</td><td>${esc(m.descricao)}</td><td class=n>${n4(m.quant)}</td><td>${inp(`data-mo="${esc(m.codigo)}"`, m.custo)}</td><td class=n>${n4(m.total)}</td>
        <td><button class="btn mini" data-savmo="${esc(m.codigo)}" data-dica="Grava o novo custo horário">✓</button></td></tr>`).join("")}
      <tr class="tot"><td colspan=4>Custo horário de mão de obra</td><td class=n>${n4(x.total_mao_obra)}</td><td></td></tr>
      <tr class="tot"><td colspan=4>Custo unitário de execução (÷ produção) · FIC · FIT</td><td class=n>${n4(x.exec_unitario)} · ${n4(x.fic)} · ${n4(x.fit)}</td><td></td></tr></table>
    <h4>C — Materiais</h4><table class="tab"><tr><th>Código</th><th>Descrição</th><th class=n>Quant.</th><th>Unid.</th><th>Preço</th><th class=n>Custo</th><th></th></tr>
      ${x.materiais.map(m => `<tr><td>${esc(m.codigo)}</td><td>${esc(m.descricao)}</td><td class=n>${n4(m.quant)}</td><td>${esc(m.unidade || "")}</td><td>${inp(`data-mat="${esc(m.codigo)}"`, m.preco)}</td><td class=n>${n4(m.total)}</td>
        <td><button class="btn mini" data-savmat="${esc(m.codigo)}" data-dica="Grava o novo preço do material">✓</button></td></tr>`).join("") || '<tr><td colspan=7 class="nota">—</td></tr>'}</table>
    <h4>D — Atividades auxiliares</h4><table class="tab"><tr><th>Código</th><th>Descrição</th><th class=n>Quant.</th><th>Unid.</th><th class=n>Preço</th><th class=n>Custo</th><th></th></tr>
      ${x.auxiliares.map(a => `<tr><td>${esc(a.codigo)}</td><td>${esc(a.descricao)}</td><td class=n>${n4(a.quant)}</td><td>${esc(a.unidade || "")}</td><td class=n>${reais(a.preco)}</td><td class=n>${n4(a.total)}</td>
        <td><button class="btn mini" data-vcomp2="${esc(a.codigo)}" data-dica="Abre a composição auxiliar">abrir</button></td></tr>`).join("") || '<tr><td colspan=7 class="nota">—</td></tr>'}</table>
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
