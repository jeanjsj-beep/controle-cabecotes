// --- LOGICA DE FRONTEND SPA PARA SCRC ---
const API_BASE = window.location.origin + "/api";
let currentCabecoteId = null;
let currentLoteId = null;

// Variáveis Globais de Sessão e Autenticação (Sessão 100% por Cookie HttpOnly + CSRF)
let currentUser = null;
let mandatoryPasswordChange = false;

// Caches em memória para eliminação de interpolação insegura em atributos inline
const cacheCabecotes = {};
const cacheLotes = {};
const cacheUsuarios = {};

// Utilitário Anti-XSS para escapar texto dinâmico inserido via innerHTML (Item 12)
function escapeHtml(str) {
    if (str === null || str === undefined) return "";
    return String(str)
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
}

function urlFotoSegura(url) {
    if (!url || typeof url !== "string") return "";
    const clean = url.trim();
    if (clean.startsWith("/uploads/") && /^(\/uploads\/[A-Za-z0-9_.-]{1,120})$/.test(clean)) {
        return escapeHtml(clean);
    }
    if (clean.startsWith("data:image/") && clean.length < 5_000_000) {
        return escapeHtml(clean);
    }
    return "";
}

function getCookieValue(name) {
    const match = document.cookie.match(new RegExp("(^| )" + name + "=([^;]+)"));
    return match ? decodeURIComponent(match[2]) : null;
}

// Interceptador Global de Fetch com Cookie Seguro HttpOnly e Anti-CSRF
const _originalFetch = window.fetch.bind(window);
window.fetch = async function(url, options = {}) {
    options.headers = options.headers || {};
    options.credentials = "same-origin";
    options.headers["X-Requested-With"] = "XMLHttpRequest";
    const csrfCookie = getCookieValue("scrc_csrf");
    if (csrfCookie) {
        options.headers["X-CSRF-Token"] = csrfCookie;
    }
    const response = await _originalFetch(url, options);
    if (response.status === 401 && typeof url === "string" && !url.includes("/api/auth/login")) {
        forcarLogoutSessao("Sua sessão expirou ou foi encerrada. Faça login novamente.");
    }
    if (response.status === 403) {
        try {
            const clone = response.clone();
            const data = await clone.json();
            if (data && data.detail && data.detail.includes("SENHA_TROCA_OBRIGATORIA")) {
                exigirTrocaDeSenhaObrigatoria();
            } else if (data && data.detail) {
                showToast(data.detail, "error");
            }
        } catch (_) {}
    }
    return response;
};

// Variáveis Globais
let refreshTimer = null;
let currentSalaModalEtapa = null;
let searchDebounceTimeout = null;
let uploadedQualidadePhotos = [];
let cachedRelatoriosList = [];

// Catálogo de Módulos e Permissões
const PERMISSOES_CATALOGO = [
    { key: "dashboard",     label: "📊 Dashboard Geral",       group: "GERAL" },
    { key: "entrada",       label: "📥 1. Entrada de Lote",    group: "GERAL" },
    { key: "recebimento",   label: "📋 Fila & Triagem",        group: "GERAL" },
    { key: "lavagem",       label: "🧼 Lavagem",               group: "OFICINA" },
    { key: "jateamento",    label: "💨 Jateamento",            group: "OFICINA" },
    { key: "estanqueidade", label: "💧 Estanqueidade",         group: "OFICINA" },
    { key: "faceamento",    label: "📐 Faceamento",            group: "OFICINA" },
    { key: "lapidacao",     label: "💎 Lapidação & Vácuo",     group: "OFICINA" },
    { key: "montagem",      label: "🔧 Montagem",              group: "OFICINA" },
    { key: "qualidade",     label: "🛡️ Qualidade",             group: "OFICINA" },
    { key: "pintura",       label: "🎨 Pintura",               group: "OFICINA" },
    { key: "expedicao",     label: "🚚 Expedição & Saída",     group: "SAÍDA" },
    { key: "relatorios",    label: "📄 Relatórios (PDF)",      group: "SAÍDA" },
    { key: "configuracoes", label: "⚙️ Configurações",         group: "AJUSTES" }
];

// Configuração Visual dos Postos / Salas da Oficina
const ROOM_CONFIGS = {
    TRIAGEM:       { title: "Fila & Triagem",        icon: "📋", nav: "recebimento",   desc: "Recepção, conferência e definição de rota" },
    LAVAGEM:       { title: "Lavagem",               icon: "🧼", nav: "lavagem",       desc: "Lavagem química, foto e confirmação" },
    JATEAMENTO:    { title: "Jateamento",            icon: "💨", nav: "jateamento",    desc: "Jateamento abrasivo, foto e confirmação" },
    ESTANQUEIDADE: { title: "Estanqueidade",         icon: "💧", nav: "estanqueidade", desc: "Teste de pressão aplicada, foto e checkbox" },
    FACEAMENTO:    { title: "Faceamento (Retífica)", icon: "📐", nav: "faceamento",    desc: "Medida inicial e medida final da face" },
    LAPIDACAO:     { title: "Lapidação & Vácuo",     icon: "💎", nav: "lapidacao",     desc: "Confirmação do vácuo (APR/REP) e retrabalho" },
    MONTAGEM:      { title: "Montagem",              icon: "🔧", nav: "montagem",      desc: "Válvula, Sede e Guia (Exaustão / Admissão)" },
    QUALIDADE:     { title: "Qualidade & Relatório", icon: "🛡️", nav: "qualidade",     desc: "Fotos de inspeção e emissão do relatório PDF" },
    PINTURA:       { title: "Pintura",               icon: "🎨", nav: "pintura",       desc: "Acabamento final e registro fotográfico" },
    PRONTO:        { title: "Expedição Final",       icon: "🚚", nav: "expedicao",     desc: "Lotes prontos (Foto, Nota, Veículo, Motorista)" },
    CONDENADO:     { title: "Peças Condenadas",      icon: "⚠️", nav: "recebimento",   desc: "Peças reprovadas aguardando reposição" }
};

// Utilitários de Modal
function openModal(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add("active");
}

function closeModal(id) {
    if (id === "modal-alterar-senha" && mandatoryPasswordChange) {
        showToast("A troca de senha é obrigatória antes de continuar utilizando o sistema.", "warning");
        return;
    }
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove("active");
}

// Impressão dedicada (Ficha Física ou Relatório Individual PDF)
function imprimirElemento(modalId) {
    document.querySelectorAll(".modal").forEach(m => m.classList.remove("print-active"));
    const target = document.getElementById(modalId);
    if (target) target.classList.add("print-active");
    window.print();
}

// Toast Notifications (com proteção Anti-XSS)
function showToast(msg, type = "success") {
    const wrap = document.getElementById("toast-wrap");
    if (!wrap) return;
    const toast = document.createElement("div");
    toast.className = `toast ${type}`;

    let emoji = "✅";
    if (type === "error") emoji = "❌";
    if (type === "warning") emoji = "⚠️";
    if (type === "info") emoji = "ℹ️";

    toast.innerHTML = `
        <span>${emoji}</span>
        <span class="toast-msg">${escapeHtml(msg)}</span>
    `;

    wrap.appendChild(toast);
    setTimeout(() => {
        toast.style.animation = "slideIn 0.3s ease reverse";
        setTimeout(() => toast.remove(), 300);
    }, 4500);
}

// --- UPLOAD REAL DE FOTOS (COM COMPRESSÃO AUTOMÁTICA PARA VERCEL / SUPABASE) ---
function readFileAsBase64(file) {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = (e) => {
            const img = new Image();
            img.onload = () => {
                try {
                    const MAX_DIM = 1280;
                    let width = img.width;
                    let height = img.height;
                    if (width > MAX_DIM || height > MAX_DIM) {
                        if (width > height) {
                            height = Math.round((height * MAX_DIM) / width);
                            width = MAX_DIM;
                        } else {
                            width = Math.round((width * MAX_DIM) / height);
                            height = MAX_DIM;
                        }
                    }
                    const canvas = document.createElement("canvas");
                    canvas.width = width;
                    canvas.height = height;
                    const ctx = canvas.getContext("2d");
                    ctx.drawImage(img, 0, 0, width, height);
                    const compressedBase64 = canvas.toDataURL("image/jpeg", 0.78);
                    resolve(compressedBase64);
                } catch (err) {
                    resolve(e.target.result);
                }
            };
            img.onerror = () => resolve(e.target.result);
            img.src = e.target.result;
        };
        reader.onerror = err => reject(err);
        reader.readAsDataURL(file);
    });
}

async function uploadFileToServer(file) {
    const base64 = await readFileAsBase64(file);
    const res = await fetch(`${API_BASE}/upload`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
            filename: file.name || "foto.jpg",
            content_base64: base64
        })
    });
    if (!res.ok) {
        throw new Error("Falha ao enviar foto");
    }
    const data = await res.json();
    return data.url;
}

async function handleSinglePhotoUpload(fileInput, hiddenInputId, previewContainerId) {
    const file = fileInput.files && fileInput.files[0];
    if (!file) return;

    const preview = document.getElementById(previewContainerId);
    if (preview) preview.innerHTML = `<span class="text-muted" style="font-size:0.8rem;">⏳ Enviando foto...</span>`;

    try {
        const url = await uploadFileToServer(file);
        document.getElementById(hiddenInputId).value = url;
        if (preview) {
            const safeUrl = urlFotoSegura(url);
            preview.innerHTML = `
                <div class="uploaded-thumb-wrap">
                    <img src="${safeUrl}" alt="Foto anexada" class="uploaded-thumb">
                    <span class="badge badge-success">📷 Foto Anexada</span>
                </div>
            `;
        }
        showToast("Foto carregada com sucesso!", "info");
    } catch (err) {
        if (preview) preview.innerHTML = `<span class="text-danger" style="font-size:0.8rem;">❌ Erro ao enviar imagem</span>`;
        showToast("Erro ao fazer upload da foto.", "error");
    }
}

async function handleMultiplePhotosUpload(fileInput, previewContainerId) {
    const files = fileInput.files ? Array.from(fileInput.files) : [];
    if (files.length === 0) return;

    const preview = document.getElementById(previewContainerId);
    if (preview) preview.innerHTML = `<span class="text-muted" style="font-size:0.8rem;">⏳ Enviando ${files.length} foto(s)...</span>`;

    try {
        for (const f of files) {
            const url = await uploadFileToServer(f);
            uploadedQualidadePhotos.push(url);
        }
        renderQualidadePhotosPreview(previewContainerId);
        showToast(`${files.length} foto(s) adicionada(s)!`, "info");
    } catch (err) {
        showToast("Erro ao enviar fotos da qualidade.", "error");
    }
}

function renderQualidadePhotosPreview(previewContainerId) {
    const preview = document.getElementById(previewContainerId);
    if (!preview) return;
    if (uploadedQualidadePhotos.length === 0) {
        preview.innerHTML = `<span class="text-muted" style="font-size:0.8rem;">Nenhuma foto selecionada.</span>`;
        return;
    }
    preview.innerHTML = uploadedQualidadePhotos.map((url, idx) => `
        <div class="uploaded-thumb-item">
            <img src="${urlFotoSegura(url)}" alt="Foto ${Number(idx) + 1}" class="uploaded-thumb">
            <button type="button" class="btn-remove-photo" onclick="removerFotoQualidade(${Number(idx)})">&times;</button>
        </div>
    `).join("");
}

function removerFotoQualidade(idx) {
    uploadedQualidadePhotos.splice(idx, 1);
    renderQualidadePhotosPreview('qual-fotos-preview');
}

// Verificar se o usuário logado possui permissão para determinado módulo
function usuarioTemPermissao(screenName) {
    if (!currentUser) return false;
    if (currentUser.is_admin) return true;
    if (screenName === "usuarios") return false;
    return Array.isArray(currentUser.permissoes) && currentUser.permissoes.includes(screenName);
}

// Controle do Menu Lateral Responsivo (Mobile Drawer)
function toggleMobileSidebar() {
    const sidebar = document.getElementById("app-sidebar");
    const backdrop = document.getElementById("mobile-sidebar-backdrop");
    if (!sidebar) return;
    const isOpen = sidebar.classList.toggle("mobile-open");
    if (backdrop) {
        backdrop.classList.toggle("active", isOpen);
    }
}

function closeMobileSidebar() {
    const sidebar = document.getElementById("app-sidebar");
    const backdrop = document.getElementById("mobile-sidebar-backdrop");
    if (sidebar) sidebar.classList.remove("mobile-open");
    if (backdrop) backdrop.classList.remove("active");
}

// Navegação entre telas com validação de permissão
function navigate(screenName) {
    if (!currentUser) return;

    if (!usuarioTemPermissao(screenName)) {
        showToast(`Acesso restrito: seu perfil não possui permissão para o módulo '${screenName.toUpperCase()}'.`, "warning");
        return;
    }

    closeMobileSidebar();

    document.querySelectorAll(".screen").forEach(s => s.classList.remove("active"));
    document.querySelectorAll(".nav-item").forEach(i => i.classList.remove("active"));
    document.querySelectorAll(".mobile-nav-btn[data-screen]").forEach(btn => {
        btn.classList.toggle("active", btn.getAttribute("data-screen") === screenName);
    });

    const targetScreen = document.getElementById(`screen-${screenName}`);
    if (targetScreen) {
        targetScreen.classList.add("active");
    }

    const navItems = Array.from(document.querySelectorAll(".nav-item"));
    const activeItem = navItems.find(item => item.getAttribute("onclick")?.includes(`'${screenName}'`));
    if (activeItem) {
        activeItem.classList.add("active");
    }

    const pageTitles = {
        dashboard:     { title: "📊 Dashboard Geral", subtitle: "Acompanhamento em tempo real da eficiência do fluxo fabril" },
        entrada:       { title: "📥 1. Entrada de Lote", subtitle: "Seleção ou cadastro de cliente e identificação das peças" },
        recebimento:   { title: "📋 Fila & Triagem", subtitle: "Controle FIFO de lotes recebidos, abertura e checklist" },
        lavagem:       { title: "🧼 Posto de Lavagem", subtitle: "Registro de foto e checkbox de confirmação da lavagem" },
        jateamento:    { title: "💨 Posto de Jateamento", subtitle: "Registro de foto e checkbox de confirmação do jateamento" },
        estanqueidade: { title: "💧 Posto de Estanqueidade", subtitle: "Registro de foto, checkbox e pressão aplicada no cabeçote" },
        faceamento:    { title: "📐 Posto de Faceamento", subtitle: "Registro de Medida Inicial e Medida Final" },
        lapidacao:     { title: "💎 Posto de Lapidação & Vácuo", subtitle: "Confirmação do vácuo (APR / REP) e retrabalho de Válvula / Sede" },
        montagem:      { title: "🔧 Posto de Montagem", subtitle: "Checklist de Válvula, Sede e Guia (Exaustão e Admissão)" },
        qualidade:     { title: "🛡️ Controle de Qualidade", subtitle: "Fotos da inspeção e salvamento do Relatório Técnico Individual" },
        pintura:       { title: "🎨 Posto de Pintura", subtitle: "Registro fotográfico da pintura e envio para expedição" },
        expedicao:     { title: "🚚 Expedição & Saída", subtitle: "Despacho com Foto, Número da Nota, Veículo e Motorista" },
        relatorios:    { title: "📄 Relatórios Técnicos (PDF)", subtitle: "Consulta, download e impressão PDF dos relatórios individuais salvos no banco" },
        usuarios:      { title: "👥 Usuários & Permissões", subtitle: "Gerenciamento de contas, senhas e permissões granulares por módulo" },
        configuracoes: { title: "⚙️ Configurações", subtitle: "Gerenciamento modular de funcionalidades do sistema" }
    };

    if (pageTitles[screenName]) {
        const titleEl = document.getElementById("current-page-title");
        const subtitleEl = document.getElementById("current-page-subtitle");
        if (titleEl) titleEl.innerText = pageTitles[screenName].title;
        if (subtitleEl) subtitleEl.innerText = pageTitles[screenName].subtitle;
    }

    if (screenName === 'dashboard') fetchStats();
    else if (screenName === 'entrada') initEntradaScreen();
    else if (screenName === 'recebimento') loadRecebimento();
    else if (screenName === 'lavagem') loadEtapaList('LAVAGEM', 'lavagem-list');
    else if (screenName === 'jateamento') loadEtapaList('JATEAMENTO', 'jateamento-list');
    else if (screenName === 'estanqueidade') loadEtapaList('ESTANQUEIDADE', 'estanqueidade-list');
    else if (screenName === 'faceamento') loadEtapaList('FACEAMENTO', 'faceamento-list');
    else if (screenName === 'lapidacao') loadEtapaList('LAPIDACAO', 'lapidacao-list');
    else if (screenName === 'montagem') loadEtapaList('MONTAGEM', 'montagem-list');
    else if (screenName === 'qualidade') loadEtapaList('QUALIDADE', 'qualidade-list');
    else if (screenName === 'pintura') loadEtapaList('PINTURA', 'pintura-list');
    else if (screenName === 'expedicao') loadAlmoxarifado();
    else if (screenName === 'relatorios') loadRelatoriosScreen();
    else if (screenName === 'usuarios') loadUsuariosScreen();
}

// Inicialização com verificação de sessão segura
document.addEventListener("DOMContentLoaded", () => {
    startLiveClock();
    setupGlobalSearchClickListener();
    renderPermissoesCheckboxes();
    verificarSessaoInicial();
});

function startLiveClock() {
    setInterval(() => {
        const now = new Date();
        const clockEl = document.getElementById("live-clock");
        if (clockEl) clockEl.innerText = now.toLocaleTimeString("pt-BR");
    }, 1000);
}

function changeAutoRefresh(msStr) {
    const ms = parseInt(msStr, 10);
    if (refreshTimer) clearInterval(refreshTimer);
    if (ms > 0) {
        refreshTimer = setInterval(fetchStats, ms);
        showToast(`Auto-refresh configurado para ${ms / 1000}s`, "info");
    } else {
        showToast("Auto-refresh pausado", "warning");
    }
}

function setupGlobalSearchClickListener() {
    document.addEventListener("click", (e) => {
        const dropdown = document.getElementById("search-results-dropdown");
        const input = document.getElementById("global-search-input");
        if (dropdown && input && !dropdown.contains(e.target) && e.target !== input) {
            dropdown.classList.add("hidden");
        }
    });
}

function handleGlobalSearch(query) {
    clearTimeout(searchDebounceTimeout);
    const dropdown = document.getElementById("search-results-dropdown");
    if (!query || query.trim().length < 1) {
        if (dropdown) dropdown.classList.add("hidden");
        return;
    }

    searchDebounceTimeout = setTimeout(async () => {
        try {
            const res = await fetch(`${API_BASE}/dashboard/buscar?q=${encodeURIComponent(query.trim())}`);
            const data = await res.json();

            if (!dropdown) return;
            dropdown.innerHTML = "";

            let hasResults = false;

            if (data.lotes && data.lotes.length > 0) {
                hasResults = true;
                const section = document.createElement("div");
                section.className = "search-section-title";
                section.innerText = "📦 Lotes Encontrados:";
                dropdown.appendChild(section);

                data.lotes.forEach(l => {
                    const item = document.createElement("div");
                    item.className = "search-item";
                    item.innerHTML = `
                        <div>
                            <strong>${escapeHtml(l.codigo_lote)}</strong> — ${escapeHtml(l.cliente_nome)}
                            <div class="text-muted" style="font-size:0.75rem;">NF: ${escapeHtml(l.nf_remessa || 'N/A')} | ${Number(l.total_pecas)} peça(s)</div>
                        </div>
                        <span class="badge badge-info">${escapeHtml(l.status)}</span>
                    `;
                    item.onclick = () => {
                        dropdown.classList.add("hidden");
                        navigate('recebimento');
                    };
                    dropdown.appendChild(item);
                });
            }

            if (data.cabecotes && data.cabecotes.length > 0) {
                hasResults = true;
                const section = document.createElement("div");
                section.className = "search-section-title";
                section.innerText = "⚙️ Cabeçotes Encontrados:";
                dropdown.appendChild(section);

                data.cabecotes.forEach(c => {
                    const item = document.createElement("div");
                    item.className = "search-item";
                    item.innerHTML = `
                        <div>
                            <strong>${escapeHtml(c.numero_serie)}</strong>
                            <div class="text-muted" style="font-size:0.75rem;">Lote: ${escapeHtml(c.codigo_lote)} (${escapeHtml(c.cliente_nome)})</div>
                        </div>
                        <div style="display:flex; gap:6px; align-items:center;">
                            <span class="badge badge-warning">${escapeHtml(c.status_etapa)}</span>
                            <button class="btn btn-secondary btn-sm" onclick="event.stopPropagation(); abrirRelatorioIndividualModal(${Number(c.id)})">📄 PDF</button>
                        </div>
                    `;
                    item.onclick = () => {
                        dropdown.classList.add("hidden");
                        openSalaModal(c.status_etapa);
                    };
                    dropdown.appendChild(item);
                });
            }

            if (!hasResults) {
                dropdown.innerHTML = `<div style="padding:12px; color: var(--text-muted); text-align:center;">Nenhum lote ou cabeçote encontrado para "${escapeHtml(query)}"</div>`;
            }

            dropdown.classList.remove("hidden");
        } catch (err) {
            console.error("Erro na busca global:", err);
        }
    }, 300);
}

// Buscar estatísticas do Dashboard
async function fetchStats() {
    try {
        const res = await fetch(`${API_BASE}/dashboard/stats`);
        const data = await res.json();

        const oeeVal = data.taxa_aprovacao || 100.0;
        const oeeProgressEl = document.getElementById("oee-circle-progress");
        const oeeTextEl = document.getElementById("oee-percentage-val");
        if (oeeTextEl) oeeTextEl.innerText = `${oeeVal}%`;
        if (oeeProgressEl) {
            const offset = 251.2 - (251.2 * (oeeVal / 100));
            oeeProgressEl.style.strokeDashoffset = offset;
        }
        document.getElementById("oee-badge-aprovados").innerText = `${data.total_prontos || 0} Aprovados`;
        document.getElementById("oee-badge-condenados").innerText = `${data.total_condenados || 0} Condenados`;

        const slaVal = data.porcentagem_sla_global || 100.0;
        const slaProgressEl = document.getElementById("sla-circle-progress");
        const slaTextEl = document.getElementById("sla-percentage-val");
        if (slaTextEl) slaTextEl.innerText = `${slaVal}%`;
        if (slaProgressEl) {
            const offset = 251.2 - (251.2 * (slaVal / 100));
            slaProgressEl.style.strokeDashoffset = offset;
        }
        document.getElementById("sla-badge-no-prazo").innerText = `Prazo Geral de SLA Ok`;

        const mainGargalo = data.posto_gargalo || "Sem gargalos";
        const filaGargalo = (data.gargalos_fila && data.gargalos_fila[mainGargalo]) || 0;
        const horGargalo = (data.gargalos_tempo_medio_horas && data.gargalos_tempo_medio_horas[mainGargalo]) || 0;
        const mainTitle = document.getElementById("bottleneck-main-title");
        const mainDesc = document.getElementById("bottleneck-main-desc");
        if (mainTitle) {
            if (mainGargalo === "Sem gargalos" || (filaGargalo === 0 && horGargalo === 0)) {
                mainTitle.innerText = "Monitor de Gargalos: Fluxo Estável";
            } else {
                mainTitle.innerText = `Gargalo Atual: ${ROOM_CONFIGS[mainGargalo]?.title || mainGargalo}`;
            }
        }
        if (mainDesc) {
            if (mainGargalo === "Sem gargalos" || (filaGargalo === 0 && horGargalo === 0)) {
                mainDesc.innerText = "Sem gargalos no momento. Todas as etapas estão operando com fluxo regular.";
            } else {
                mainDesc.innerText = `${filaGargalo} peça(s) na fila · retenção média histórica ${horGargalo.toFixed(1)}h.`;
            }
        }

        const lotesProcesso = (data.status_lotes.RECEBIDO || 0) + (data.status_lotes.EM_PROCESSO || 0);
        document.getElementById("kpi-lotes-ativos").innerText = lotesProcesso;
        document.getElementById("kpi-lotes-detalhes").innerText = `${data.status_lotes.RECEBIDO || 0} em triagem | ${data.status_lotes.EM_PROCESSO || 0} em oficina`;

        const cabecotesOficina = Object.entries(data.etapas_cabecotes)
            .filter(([k, _]) => !['PRONTO', 'CONDENADO', 'TRIAGEM'].includes(k))
            .reduce((sum, [_, v]) => sum + v, 0);
        document.getElementById("kpi-cabecotes-ativos").innerText = cabecotesOficina;

        document.getElementById("kpi-cabecotes-condenados").innerText = data.total_condenados || 0;
        document.getElementById("kpi-condenados-detalhes").innerText = data.total_condenados > 0 ? "⚠️ Peças aguardando reposição" : "Nenhuma condenação registrada";

        const ocupados = data.almoxarifado_espacos_ocupados.length;
        document.getElementById("kpi-espacos-ocupados").innerText = `${ocupados} / 24`;
        document.getElementById("kpi-espacos-detalhes").innerText = `${data.almoxarifado_espacos_ociosos.length} posições livres no almoxarifado`;

        renderRoomsGrid(data.etapas_cabecotes, data.gargalos_tempo_medio_horas, data.posto_gargalo);
        renderPalletGrid(data.pallets_detalhados, data.taxa_ocupacao_almoxarifado);
        renderSlaTable(data.sla_clientes);

        const alertsContainer = document.getElementById("dashboard-alerts");
        alertsContainer.innerHTML = "";
        data.alertas_reposicao.forEach(alert => {
            const div = document.createElement("div");
            div.className = "alert alert-warning";
            div.innerHTML = `
                <div>
                    <strong>⚠️ Alerta de Reposição de Lote:</strong> ${escapeHtml(alert.mensagem)}
                </div>
                <button class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.75rem;" onclick="navigate('recebimento')">Ir para Triagem</button>
            `;
            alertsContainer.appendChild(div);
        });

        const tbody = document.getElementById("dashboard-movements");
        tbody.innerHTML = "";
        if (data.ultimas_movimentacoes.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center">Nenhuma movimentação registrada.</td></tr>`;
        } else {
            data.ultimas_movimentacoes.forEach(m => {
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td>${escapeHtml(m.data_hora)}</td>
                    <td><span class="badge badge-info">${escapeHtml(m.lote_codigo)}</span></td>
                    <td><strong>${escapeHtml(m.cabecote_serial)}</strong></td>
                    <td><span class="badge badge-warning">${escapeHtml(m.estagio_origem)}</span> ➔ <span class="badge badge-success">${escapeHtml(m.estagio_destino)}</span></td>
                    <td><strong>${escapeHtml(m.operador)}</strong></td>
                    <td class="text-muted">${escapeHtml(m.descricao)}</td>
                `;
                tbody.appendChild(tr);
            });
        }
    } catch (err) {
        showToast("Erro ao carregar estatísticas do dashboard.", "error");
        console.error(err);
    }
}

function renderRoomsGrid(etapasCounts, gargalosHoras, mainGargalo) {
    const container = document.getElementById("rooms-grid-container");
    if (!container) return;
    container.innerHTML = "";

    Object.keys(ROOM_CONFIGS).forEach(etapaKey => {
        const cfg = ROOM_CONFIGS[etapaKey];
        const count = etapasCounts[etapaKey] || 0;
        const horas = gargalosHoras[etapaKey] || 0;
        const isGargalo = (etapaKey === mainGargalo) && count > 0;

        let statusBadge = `<span class="room-badge normal">Normal</span>`;
        if (isGargalo) {
            statusBadge = `<span class="room-badge danger">⚠️ GARGALO CRÍTICO</span>`;
        } else if (count > 4) {
            statusBadge = `<span class="room-badge warning">Carga Alta</span>`;
        } else if (count === 0) {
            statusBadge = `<span class="room-badge muted">Livre</span>`;
        }

        const card = document.createElement("div");
        card.className = `room-card glass ${isGargalo ? 'gargalo-card' : ''}`;
        card.onclick = () => openSalaModal(etapaKey);

        card.innerHTML = `
            <div class="room-card-header">
                <div class="room-icon-wrap">${cfg.icon}</div>
                <div>
                    <div class="room-title">${cfg.title}</div>
                    <div class="room-desc">${cfg.desc}</div>
                </div>
            </div>

            <div class="room-card-body">
                <div class="room-metric">
                    <span class="room-metric-val">${count}</span>
                    <span class="room-metric-label">cabeçotes na sala</span>
                </div>
                ${horas > 0 ? `<div class="room-retention">🕒 Est. Retenção: <strong>${horas.toFixed(1)}h</strong></div>` : ''}
            </div>

            <div class="room-card-footer">
                ${statusBadge}
                <span class="room-action-link">Ver Sala ➔</span>
            </div>
        `;
        container.appendChild(card);
    });
}

async function openSalaModal(etapaKey) {
    currentSalaModalEtapa = etapaKey;
    const cfg = ROOM_CONFIGS[etapaKey] || { title: etapaKey, icon: "🏢", nav: "dashboard" };

    document.getElementById("modal-sala-title").innerText = `${cfg.icon} Visão Detalhada da Sala: ${cfg.title}`;
    document.getElementById("modal-sala-subtitle").innerText = `Acompanhamento em tempo real de todos os cabeçotes presentes em ${cfg.title}`;

    const tbody = document.getElementById("modal-sala-table-body");
    tbody.innerHTML = `<tr><td colspan="6" class="text-center">Carregando dados da sala ${cfg.title}...</td></tr>`;

    openModal("modal-detalhes-sala");

    try {
        const res = await fetch(`${API_BASE}/dashboard/sala/${etapaKey}`);
        const data = await res.json();

        document.getElementById("modal-sala-count").innerText = `${data.total_pecas} peça(s)`;
        const badgeEl = document.getElementById("modal-sala-status-badge");
        if (badgeEl) {
            badgeEl.innerText = data.total_pecas > 0 ? `${data.total_pecas} Em Processamento` : "Sala Livre / Sem Peças";
            badgeEl.className = data.total_pecas > 0 ? "badge badge-info" : "badge badge-success";
        }

        tbody.innerHTML = "";
        if (!data.pecas || data.pecas.length === 0) {
            tbody.innerHTML = `<tr><td colspan="6" class="text-center text-muted" style="padding: 24px;">Nenhuma peça na sala ${cfg.title} neste momento.</td></tr>`;
            return;
        }

        data.pecas.forEach(p => {
            const tr = document.createElement("tr");
            let params = [];
            if (p.lavagem_concluida) params.push("🧼 Lavagem Ok");
            if (p.jateamento_concluido) params.push("💨 Jateamento Ok");
            if (p.estanqueidade_concluida) params.push(`💧 Estanq: ${p.estanqueidade_pressao || ''}bar`);
            if (p.face_concluido) params.push(`📐 Face: ${p.face_altura_entrada}➔${p.face_altura_saida}mm`);
            if (p.lapidacao_concluida) params.push(`💎 Vácuo: ${p.lapidacao_confirmacao_vacuo || 'APR'}`);
            else if (p.lapidacao_status_retrabalho) params.push(`⚠️ Lapidação: ${p.lapidacao_status_retrabalho}`);
            if (p.montagem_concluida) params.push("🔧 Montado");
            if (p.qualidade_aprovada) params.push("🛡️ Qualidade Ok");
            if (p.pintura_concluida) params.push("🎨 Pintado");

            const paramsStr = params.length > 0 ? params.join(" | ") : "Aguardando processamento do posto";

            tr.innerHTML = `
                <td><strong>${escapeHtml(p.numero_serie)}</strong></td>
                <td><span class="badge badge-purple">${escapeHtml(p.numero_identificacao_peca || 'N/A')}</span></td>
                <td><span class="badge badge-info">${escapeHtml(p.codigo_lote)}</span></td>
                <td><strong>${escapeHtml(p.cliente_nome)}</strong></td>
                <td style="font-size: 0.8rem; color: var(--text-secondary);">${escapeHtml(paramsStr)}</td>
                <td>
                    <button class="btn btn-secondary btn-sm" onclick="abrirRelatorioIndividualModal(${Number(p.id)})">📄 Relatório PDF</button>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        tbody.innerHTML = `<tr><td colspan="6" class="text-center text-danger">Erro ao carregar peças da sala.</td></tr>`;
        console.error(err);
    }
}

function navigateFromSalaModal() {
    closeModal("modal-detalhes-sala");
    if (currentSalaModalEtapa && ROOM_CONFIGS[currentSalaModalEtapa]) {
        navigate(ROOM_CONFIGS[currentSalaModalEtapa].nav);
    }
}

function renderPalletGrid(palletsList, occupancyPct) {
    const container = document.getElementById("pallet-map-container");
    const badge = document.getElementById("pallet-occupancy-badge");
    if (badge) badge.innerText = `${occupancyPct}% Ocupado`;
    if (!container || !palletsList) return;

    container.innerHTML = "";
    palletsList.forEach(p => {
        const isOccupied = p.status === "OCUPADO";
        const item = document.createElement("div");
        item.className = `pallet-box ${isOccupied ? 'occupied' : 'free'}`;
        item.title = isOccupied ? `Pallet ${p.codigo}: Lote ${p.lote_codigo} (${p.cliente_nome}) - ${p.total_pecas} pçs` : `Pallet ${p.codigo}: Livre`;

        item.innerHTML = `
            <span class="pallet-code">${escapeHtml(p.codigo)}</span>
            <span class="pallet-status-dot"></span>
        `;

        item.onclick = () => {
            if (isOccupied) {
                showToast(`Pallet ${p.codigo}: Lote ${p.lote_codigo} (${p.cliente_nome}) - ${p.total_pecas} peça(s) estocadas`, "info");
            } else {
                showToast(`Pallet ${p.codigo} está disponível para alocação`, "success");
            }
        };

        container.appendChild(item);
    });
}

function renderSlaTable(slaList) {
    const tbody = document.getElementById("sla-client-table-body");
    if (!tbody || !slaList) return;

    tbody.innerHTML = "";
    if (slaList.length === 0) {
        tbody.innerHTML = `<tr><td colspan="4" class="text-center">Nenhum cliente cadastrado.</td></tr>`;
        return;
    }

    slaList.forEach(s => {
        const tr = document.createElement("tr");
        const badgeClass = s.porcentagem_sla >= 90 ? "badge-success" : s.porcentagem_sla >= 75 ? "badge-warning" : "badge-danger";

        tr.innerHTML = `
            <td><strong>${escapeHtml(s.cliente_nome)}</strong></td>
            <td>${Number(s.total_lotes)} lote(s)</td>
            <td>${Number(s.no_prazo)} no prazo</td>
            <td><span class="badge ${badgeClass}">${Number(s.porcentagem_sla)}% SLA</span></td>
        `;
        tbody.appendChild(tr);
    });
}

// --- MÓDULO 1: ENTRADA E CADASTRO DE CLIENTES ---
async function initEntradaScreen() {
    await loadClientesSelect();
    const qtdInput = document.getElementById("entrada-qtd");
    const qtd = parseInt(qtdInput.value) || 5;
    gerarCamposIdentificacao(qtd);

    const dateInput = document.getElementById("cli-data");
    if (dateInput && !dateInput.value) {
        dateInput.value = new Date().toISOString().split("T")[0];
    }
}

async function loadClientesSelect() {
    const select = document.getElementById("entrada-cliente-select");
    if (!select) return;
    const currentVal = select.value;

    try {
        const res = await fetch(`${API_BASE}/clientes`);
        const clientes = await res.json();

        select.innerHTML = `
            <option value="">-- Selecione um Cliente na Lista --</option>
            <option value="NOVO">➕ Registrar Novo Cliente</option>
        `;

        clientes.forEach(c => {
            const opt = document.createElement("option");
            opt.value = c.id;
            opt.innerText = `${c.nome} [Iniciais: ${c.iniciais}]`;
            select.appendChild(opt);
        });

        if (currentVal) select.value = currentVal;
    } catch (err) {
        showToast("Erro ao carregar lista de clientes.", "error");
    }
}

function toggleNovoClienteForm(val) {
    const novoFields = document.getElementById("novo-cliente-fields");
    const cliNome = document.getElementById("cli-nome");

    if (val === "NOVO") {
        novoFields.style.display = "block";
        cliNome.required = true;
    } else {
        novoFields.style.display = "none";
        cliNome.required = false;
    }
}

function gerarCamposIdentificacao(qtd) {
    const container = document.getElementById("campos-identificacao-container");
    if (!container) return;

    let num = parseInt(qtd);
    if (isNaN(num) || num < 1) num = 1;
    if (num > 100) num = 100;

    const existingInputs = container.querySelectorAll(".input-identificacao-peca");
    const savedValues = Array.from(existingInputs).map(inp => inp.value);

    container.innerHTML = "";

    for (let i = 0; i < num; i++) {
        const val = savedValues[i] || "";
        const div = document.createElement("div");
        div.className = "form-group";
        div.style.marginBottom = "8px";
        div.innerHTML = `
            <label style="font-size: 0.75rem; color: var(--accent-light); margin-bottom: 2px;">Peça #${i + 1} - Nº Identificação</label>
            <input type="text" class="input-identificacao-peca form-control" maxlength="60" placeholder="Ex: P-${1000 + i + 1}" value="${escapeHtml(val)}" required style="padding: 6px 10px; font-size: 0.85rem;">
        `;
        container.appendChild(div);
    }
}

async function submitEntradaLote(event) {
    event.preventDefault();
    const clientSelectVal = document.getElementById("entrada-cliente-select").value;
    const qtd = parseInt(document.getElementById("entrada-qtd").value) || 0;

    if (!clientSelectVal) {
        return showToast("Selecione um cliente ou opte por cadastrar um novo.", "warning");
    }

    const inputElements = document.querySelectorAll(".input-identificacao-peca");
    const identificacoes = Array.from(inputElements).map(inp => inp.value.trim());

    if (identificacoes.length === 0 || identificacoes.some(val => val.length === 0)) {
        return showToast("Preencha o número de identificação para todas as peças.", "warning");
    }

    const payload = {
        quantidade: qtd,
        identificacoes_pecas: identificacoes
    };

    if (clientSelectVal === "NOVO") {
        const nome = document.getElementById("cli-nome").value.trim();
        const cnpj = document.getElementById("cli-cnpj").value.trim();
        const ie = document.getElementById("cli-ie").value.trim();
        const email = document.getElementById("cli-email").value.trim();
        const telefone = document.getElementById("cli-telefone").value.trim();

        if (!nome) {
            return showToast("Informe o Nome/Razão Social do novo cliente.", "warning");
        }

        payload.novo_cliente = {
            nome: nome,
            cnpj: cnpj || null,
            inscricao_estadual: ie || null,
            email: email || null,
            telefone: telefone || null
        };
    } else {
        payload.cliente_id = parseInt(clientSelectVal);
    }

    try {
        const res = await fetch(`${API_BASE}/lotes/entrada`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });

        if (res.ok) {
            const loteCriado = await res.json();
            showToast(`Lote ${loteCriado.codigo_lote} registrado com sucesso para ${loteCriado.cliente_nome}!`);
            document.getElementById("form-entrada-lote").reset();
            document.getElementById("entrada-cliente-select").value = "";
            toggleNovoClienteForm("");
            gerarCamposIdentificacao(5);
            navigate("recebimento");
        } else {
            const err = await res.json();
            showToast(err.detail || "Falha ao registrar entrada do lote.", "error");
        }
    } catch (err) {
        showToast("Erro na requisição de entrada de lote.", "error");
    }
}

// --- FILA & TRIAGEM ---
async function loadRecebimento() {
    try {
        const res = await fetch(`${API_BASE}/lotes?status=PRE_CADASTRO`);
        const preLotes = await res.json();

        const tbodyPre = document.getElementById("recebimento-fifo-list");
        tbodyPre.innerHTML = "";
        if (preLotes.length === 0) {
            tbodyPre.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Nenhum lote pendente de chegada física.</td></tr>`;
        } else {
            preLotes.forEach(l => {
                cacheLotes[l.id] = l;
                const tr = document.createElement("tr");
                tr.innerHTML = `
                    <td><strong>${escapeHtml(l.codigo_lote)}</strong></td>
                    <td>${escapeHtml(l.cliente_nome)}</td>
                    <td>${escapeHtml(l.nf_remessa || 'N/A')}</td>
                    <td><span class="badge badge-warning">Pendente Recebimento</span></td>
                    <td>
                        <button class="btn btn-primary" style="padding: 6px 12px; font-size: 0.75rem;" onclick="abrirReceberModal(${Number(l.id)})">📥 Receber Físico</button>
                    </td>
                `;
                tbodyPre.appendChild(tr);
            });
        }

        const resAtivos = await fetch(`${API_BASE}/lotes`);
        const todosLotes = await resAtivos.json();

        const ativos = todosLotes.filter(l => l.status !== "PRE_CADASTRO");
        const tbodyAtivos = document.getElementById("recebidos-lotes-list");
        tbodyAtivos.innerHTML = "";

        if (ativos.length === 0) {
            tbodyAtivos.innerHTML = `<tr><td colspan="6" class="text-center text-muted">Nenhum lote em processo.</td></tr>`;
        } else {
            ativos.forEach(l => {
                cacheLotes[l.id] = l;
                const tr = document.createElement("tr");
                const totalCab = l.cabecotes.length;
                const concCab = l.cabecotes.filter(c => ['PRONTO', 'CONDENADO'].includes(c.status_etapa)).length;

                const btnFicha = `<button class="btn btn-secondary" style="padding: 6px 12px; font-size: 0.75rem;" onclick="abrirFichaModal(${Number(l.id)})">📋 Ficha Física</button>`;

                let badgeStatus = "badge-info";
                if (l.status === "RECEBIDO") badgeStatus = "badge-warning";
                if (l.status === "CONCLUIDO") badgeStatus = "badge-success";
                if (l.status === "EXPEDIDO") badgeStatus = "badge-info";

                tr.innerHTML = `
                    <td><strong>${escapeHtml(l.codigo_lote)}</strong></td>
                    <td>${escapeHtml(l.cliente_nome)}</td>
                    <td>${escapeHtml(l.nf_remessa || 'N/A')}</td>
                    <td><span class="badge ${badgeStatus}">${escapeHtml(l.status)}</span></td>
                    <td>${Number(concCab)}/${Number(totalCab)} peças</td>
                    <td>${btnFicha}</td>
                `;
                tbodyAtivos.appendChild(tr);

                const extraTr = document.createElement("tr");
                extraTr.className = "detail-row";

                let cabListHtml = l.cabecotes.map(c => {
                    cacheCabecotes[c.id] = c;
                    let classBadge = "badge-info";
                    let actionHtml = "";

                    if (c.status_etapa === "TRIAGEM") {
                        classBadge = "badge-warning";
                        actionHtml = `<button class="btn btn-primary" style="padding: 3px 8px; font-size: 0.72rem; margin-left: 10px;" onclick="abrirChecklistModal(${Number(c.id)})">⚙️ Definir Rota</button>`;
                    } else if (c.status_etapa === "CONDENADO") {
                        classBadge = "badge-danger";
                    } else if (c.status_etapa === "PRONTO") {
                        classBadge = "badge-success";
                    }

                    const btnRelatorio = `<button class="btn btn-secondary" style="padding: 3px 8px; font-size: 0.72rem; margin-left: 8px;" onclick="abrirRelatorioIndividualModal(${Number(c.id)})">📄 Relatório PDF</button>`;

                    return `
                        <div style="margin: 8px 0; display: flex; align-items: center; flex-wrap: wrap; gap: 6px;">
                            <span style="font-family: monospace; font-weight: bold; min-width: 170px;">${escapeHtml(c.numero_serie)}</span>
                            <span class="badge ${classBadge}">${escapeHtml(c.status_etapa)}</span>
                            ${actionHtml}
                            ${btnRelatorio}
                        </div>
                    `;
                }).join("");

                extraTr.innerHTML = `
                    <td colspan="6" style="padding-left: 40px; background-color: rgba(255,255,255,0.01);">
                        <div style="border-left: 2px solid var(--border-glass); padding-left: 16px;">
                            <strong>Rastreabilidade de Cabeçotes Individuais:</strong>
                            ${cabListHtml}
                        </div>
                    </td>
                `;
                tbodyAtivos.appendChild(extraTr);
            });
        }
    } catch (err) {
        showToast("Erro ao carregar fila de recebimento.", "error");
    }
}

function abrirReceberModal(id, codigo, cliente) {
    currentLoteId = Number(id);
    const l = cacheLotes[id] || {};
    document.getElementById("modal-recebimento-lote-cod").innerText = codigo || l.codigo_lote || "";
    document.getElementById("modal-recebimento-lote-cli").innerText = cliente || l.cliente_nome || "";
    document.getElementById("recebimento-seriais").value = "";
    openModal("modal-recebimento");
}

async function confirmarRecebimentoFisico() {
    const textSeriais = document.getElementById("recebimento-seriais").value.trim();
    if (!textSeriais) {
        showToast("Digite pelo menos um número de série.", "warning");
        return;
    }

    const listSeriais = textSeriais.split("\n").map(s => s.trim()).filter(s => s.length > 0);

    try {
        const res = await fetch(`${API_BASE}/lotes/${currentLoteId}/receber`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(listSeriais)
        });

        if (res.ok) {
            showToast("Lote recebido fisicamente!");
            closeModal("modal-recebimento");
            loadRecebimento();
        } else {
            const err = await res.json();
            showToast(err.detail || "Falha ao receber lote físico.", "error");
        }
    } catch (err) {
        showToast("Erro de rede ao confirmar recebimento.", "error");
    }
}

function abrirChecklistModal(id, serial) {
    currentCabecoteId = Number(id);
    const c = cacheCabecotes[id] || {};
    document.getElementById("checklist-cabecote-serial").innerText = serial || c.numero_serie || "";
    document.getElementById("chk-jateamento").checked = true;
    document.getElementById("chk-estanqueidade").checked = true;
    document.getElementById("chk-faceamento").checked = true;
    document.getElementById("chk-lapidacao").checked = true;
    document.getElementById("chk-montagem").checked = true;
    document.getElementById("chk-pintura").checked = true;
    openModal("modal-checklist");
}

async function salvarChecklist() {
    const jat = document.getElementById("chk-jateamento").checked;
    const est = document.getElementById("chk-estanqueidade").checked;
    const face = document.getElementById("chk-faceamento").checked;
    const lap = document.getElementById("chk-lapidacao").checked;
    const mont = document.getElementById("chk-montagem").checked;
    const pint = document.getElementById("chk-pintura").checked;

    try {
        const res = await fetch(`${API_BASE}/cabecotes/${currentCabecoteId}/checklist`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                requer_jateamento: jat,
                requer_estanqueidade: est,
                requer_faceamento: face,
                requer_lapidacao: lap,
                requer_montagem: mont,
                requer_pintura: pint
            })
        });

        if (res.ok) {
            showToast("Rota configurada! Peça enviada para a Lavagem.");
            closeModal("modal-checklist");
            loadRecebimento();
        } else {
            showToast("Erro ao salvar rota.", "error");
        }
    } catch (err) {
        showToast("Erro na requisição de checklist.", "error");
    }
}

async function abrirFichaModal(loteId) {
    try {
        const res = await fetch(`${API_BASE}/lotes/${loteId}`);
        const lote = await res.json();

        const printableArea = document.getElementById("printable-ficha-content");

        let cabecotesRows = (lote.cabecotes || []).map(c => `
            <tr style="border-bottom: 1px solid #94a3b8;">
                <td style="padding: 8px; font-family: monospace; font-weight: bold;">${escapeHtml(c.numero_serie)}</td>
                <td style="padding: 8px; color: #334155; font-size: 0.78rem;">
                    [ ] Lavagem &nbsp; [ ] Jateamento &nbsp; [ ] Estanqueidade (____ bar)<br>
                    Faceamento: Inicial _____ mm | Final _____ mm<br>
                    Lapidação Vácuo: ( ) APR &nbsp; ( ) REP ➔ [ ] Válvula [ ] Sede<br>
                    Montagem: Válv(Ex/Ad) Sede(Ex/Ad) Guia(Ex/Ad)
                </td>
            </tr>
        `).join("");

        printableArea.innerHTML = `
            <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px;">
                <div>
                    <h2 style="margin: 0; color: #0f172a;">FICHA DE FLUXO DA OFICINA</h2>
                    <p style="margin: 4px 0 0 0; color: #475569;">Acompanhamento físico de recondicionamento de cabeçotes</p>
                </div>
                <div style="border: 2px solid black; padding: 6px; font-family: monospace; font-size: 1.1rem; text-align: center;">
                    ||||||| ${escapeHtml(lote.codigo_lote)} |||||||
                </div>
            </div>

            <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 20px; margin-bottom: 20px; font-size: 0.9rem; background: #f8fafc; padding: 12px; border-radius: 6px;">
                <div>
                    <p><strong>Lote Oficial:</strong> ${escapeHtml(lote.codigo_lote)}</p>
                    <p><strong>Cliente:</strong> ${escapeHtml(lote.cliente_nome)}</p>
                </div>
                <div>
                    <p><strong>NF Remessa:</strong> ${escapeHtml(lote.nf_remessa || 'N/A')}</p>
                    <p><strong>Data de Entrada:</strong> ${escapeHtml(lote.data_entrada ? new Date(lote.data_entrada).toLocaleString('pt-BR') : 'N/A')}</p>
                </div>
            </div>

            <table style="width: 100%; border-collapse: collapse; text-align: left; font-size: 0.85rem; margin-bottom: 20px;">
                <thead>
                    <tr style="background-color: #e2e8f0; border-bottom: 2px solid #cbd5e1;">
                        <th style="padding: 8px; width: 32%;">Nº Série Cabeçote</th>
                        <th style="padding: 8px;">Apontamentos Físicos das Etapas</th>
                    </tr>
                </thead>
                <tbody>
                    ${cabecotesRows}
                </tbody>
            </table>
        `;

        openModal("modal-ficha-fisica");
    } catch (err) {
        showToast("Falha ao abrir ficha de manutenção.", "error");
    }
}

// --- LISTAGEM GENÉRICA DAS ETAPAS DA OFICINA ---
async function loadEtapaList(etapaName, elementId) {
    try {
        const [resCab, resLotes] = await Promise.all([
            fetch(`${API_BASE}/cabecotes?etapa=${encodeURIComponent(etapaName)}`),
            fetch(`${API_BASE}/lotes/resumo`)
        ]);
        const cabecotes = await resCab.json();
        const lotesResumo = await resLotes.json();
        const lotesMap = {};
        if (Array.isArray(lotesResumo)) {
            lotesResumo.forEach(l => { lotesMap[l.id] = l; });
        }

        const tbody = document.getElementById(elementId);
        if (!tbody) return;
        tbody.innerHTML = "";

        if (!Array.isArray(cabecotes) || cabecotes.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Nenhuma peça nesta etapa atualmente.</td></tr>`;
        } else {
            for (let c of cabecotes) {
                cacheCabecotes[c.id] = c;
                const lote = lotesMap[c.lote_id] || { codigo_lote: 'N/A', cliente_nome: 'N/A' };

                const tr = document.createElement("tr");

                let buttonHtml = "";
                let extraColHtml = "";

                if (etapaName === "LAVAGEM") {
                    extraColHtml = `<td><span class="badge badge-info">🧼 Lavagem</span></td>`;
                    buttonHtml = `<button class="btn btn-primary btn-sm" onclick="abrirLavagemModal(${Number(c.id)})">🧼 Registrar Lavagem</button>`;
                } else if (etapaName === "JATEAMENTO") {
                    extraColHtml = `<td><span class="badge badge-info">💨 Jateamento</span></td>`;
                    buttonHtml = `<button class="btn btn-primary btn-sm" onclick="abrirJateamentoModal(${Number(c.id)})">💨 Registrar Jateamento</button>`;
                } else if (etapaName === "ESTANQUEIDADE") {
                    extraColHtml = `<td><span class="badge badge-info">💧 Teste de Pressão</span></td>`;
                    buttonHtml = `<button class="btn btn-primary btn-sm" onclick="abrirEstanqueidadeModal(${Number(c.id)})">💧 Lançar Estanqueidade</button>`;
                } else if (etapaName === "FACEAMENTO") {
                    buttonHtml = `<button class="btn btn-primary btn-sm" onclick="abrirFaceamentoModal(${Number(c.id)})">📐 Lançar Medidas</button>`;
                } else if (etapaName === "LAPIDACAO") {
                    let statusVacuoBadge = `<span class="badge badge-info">Aguardando 1º Teste de Vácuo</span>`;
                    if (c.lapidacao_status_retrabalho === "TROCAR_VALVULA") {
                        statusVacuoBadge = `<span class="badge badge-warning">⚠️ 1ª Repr. Vácuo ➔ TROCAR VÁLVULA E TESTAR</span>`;
                    } else if (c.lapidacao_status_retrabalho === "TROCAR_SEDE") {
                        statusVacuoBadge = `<span class="badge badge-danger">🚨 Reprovou Novamente ➔ TROCAR SEDE</span>`;
                    }
                    extraColHtml = `<td>${statusVacuoBadge}</td>`;
                    buttonHtml = `<button class="btn btn-primary btn-sm" onclick="abrirLapidacaoModal(${Number(c.id)})">💎 Confirmar Vácuo</button>`;
                } else if (etapaName === "MONTAGEM") {
                    buttonHtml = `<button class="btn btn-primary btn-sm" onclick="abrirMontagemModal(${Number(c.id)})">🔧 Registrar Montagem</button>`;
                } else if (etapaName === "QUALIDADE") {
                    buttonHtml = `<button class="btn btn-primary btn-sm" onclick="abrirQualidadeModal(${Number(c.id)})">🛡️ Aprovar & Gerar Relatório</button>`;
                } else if (etapaName === "PINTURA") {
                    extraColHtml = `<td><button class="btn btn-secondary btn-sm" onclick="abrirRelatorioIndividualModal(${Number(c.id)})">📄 Ver Relatório PDF</button></td>`;
                    buttonHtml = `<button class="btn btn-primary btn-sm" onclick="abrirPinturaModal(${Number(c.id)})">🎨 Registrar Pintura</button>`;
                }

                tr.innerHTML = `
                    <td><strong style="font-family: monospace;">${escapeHtml(c.numero_serie)}</strong></td>
                    <td><span class="badge badge-info">${escapeHtml(lote.codigo_lote)}</span></td>
                    <td>${escapeHtml(lote.cliente_nome)}</td>
                    ${extraColHtml}
                    <td>${buttonHtml}</td>
                `;
                tbody.appendChild(tr);
            }
        }
    } catch (err) {
        showToast(`Erro ao carregar lista de ${escapeHtml(etapaName)}`, "error");
    }
}

// 1. Ações Lavagem (Foto + Checkbox)
function abrirLavagemModal(id) {
    currentCabecoteId = id;
    document.getElementById("lavagem-file").value = "";
    document.getElementById("lavagem-foto-url").value = "";
    document.getElementById("lavagem-foto-preview").innerHTML = "";
    document.getElementById("lavagem-checkbox").checked = true;
    document.getElementById("lavagem-operador").value = currentUser ? currentUser.nome_completo : "";
    openModal("modal-lavagem");
}

async function salvarLavagem() {
    const foto_url = document.getElementById("lavagem-foto-url").value.trim() || null;
    const checkbox = document.getElementById("lavagem-checkbox").checked;
    const operador = document.getElementById("lavagem-operador").value.trim();

    if (!checkbox) return showToast("Marque o checkbox de confirmação da Lavagem.", "warning");
    if (!operador) return showToast("Informe o operador responsável.", "warning");

    try {
        const res = await fetch(`${API_BASE}/etapas/lavagem/${currentCabecoteId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ foto_url, checkbox, operador })
        });

        if (res.ok) {
            showToast("Lavagem registrada com sucesso!");
            closeModal("modal-lavagem");
            loadEtapaList('LAVAGEM', 'lavagem-list');
        } else {
            const err = await res.json();
            showToast(err.detail || "Erro ao registrar lavagem.", "error");
        }
    } catch (err) {
        showToast("Erro na requisição de lavagem.", "error");
    }
}

// 2. Ações Jateamento (Foto + Checkbox)
function abrirJateamentoModal(id) {
    currentCabecoteId = id;
    document.getElementById("jateamento-file").value = "";
    document.getElementById("jateamento-foto-url").value = "";
    document.getElementById("jateamento-foto-preview").innerHTML = "";
    document.getElementById("jateamento-checkbox").checked = true;
    document.getElementById("jateamento-operador").value = currentUser ? currentUser.nome_completo : "";
    openModal("modal-jateamento");
}

async function salvarJateamento() {
    const foto_url = document.getElementById("jateamento-foto-url").value.trim() || null;
    const checkbox = document.getElementById("jateamento-checkbox").checked;
    const operador = document.getElementById("jateamento-operador").value.trim();

    if (!checkbox) return showToast("Marque o checkbox de confirmação do Jateamento.", "warning");
    if (!operador) return showToast("Informe o operador responsável.", "warning");

    try {
        const res = await fetch(`${API_BASE}/etapas/jateamento/${currentCabecoteId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ foto_url, checkbox, operador })
        });

        if (res.ok) {
            showToast("Jateamento registrado com sucesso!");
            closeModal("modal-jateamento");
            loadEtapaList('JATEAMENTO', 'jateamento-list');
        } else {
            const err = await res.json();
            showToast(err.detail || "Erro ao registrar jateamento.", "error");
        }
    } catch (err) {
        showToast("Erro na requisição de jateamento.", "error");
    }
}

// 3. Ações Estanqueidade (Foto + Checkbox + Pressão Aplicada + Aprovação/Condenação)
function abrirEstanqueidadeModal(id) {
    currentCabecoteId = Number(id);
    document.getElementById("estanqueidade-file").value = "";
    document.getElementById("estanqueidade-foto-url").value = "";
    document.getElementById("estanqueidade-foto-preview").innerHTML = "";
    document.getElementById("estanqueidade-pressao").value = "";
    const aprRadio = document.getElementById("estanqueidade-apr");
    if (aprRadio) aprRadio.checked = true;
    document.getElementById("estanqueidade-checkbox").checked = true;
    document.getElementById("estanqueidade-operador").value = currentUser ? currentUser.nome_completo : "";
    openModal("modal-estanqueidade");
}

async function salvarEstanqueidade() {
    const foto_url = document.getElementById("estanqueidade-foto-url").value.trim() || null;
    const checkbox = document.getElementById("estanqueidade-checkbox").checked;
    const pressao_aplicada = parseFloat(document.getElementById("estanqueidade-pressao").value);
    const operador = document.getElementById("estanqueidade-operador").value.trim();
    const aprovadaRadio = document.querySelector('input[name="estanqueidade-resultado"]:checked');
    const aprovada = aprovadaRadio ? aprovadaRadio.value === "aprovado" : true;

    if (!checkbox) return showToast("Marque o checkbox de confirmação da Estanqueidade.", "warning");
    if (isNaN(pressao_aplicada)) return showToast("Informe a Pressão Aplicada.", "warning");
    if (!operador) return showToast("Informe o operador responsável.", "warning");

    if (!aprovada) {
        if (!confirm("⚠️ ATENÇÃO: A reprovação no teste de estanqueidade CONDENARÁ a peça imediatamente (trinca/vazamento). Deseja prosseguir com a condenação?")) {
            return;
        }
    }

    try {
        const res = await fetch(`${API_BASE}/etapas/estanqueidade/${currentCabecoteId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ foto_url, checkbox, pressao_aplicada, operador, aprovada })
        });

        if (res.ok) {
            showToast(aprovada ? "Estanqueidade registrada e aprovada!" : "Peça condenada por vazamento na estanqueidade.", aprovada ? "success" : "warning");
            closeModal("modal-estanqueidade");
            loadEtapaList('ESTANQUEIDADE', 'estanqueidade-list');
        } else {
            const err = await res.json();
            showToast(err.detail || "Erro ao registrar estanqueidade.", "error");
        }
    } catch (err) {
        showToast("Erro na requisição de estanqueidade.", "error");
    }
}

// 4. Ações Faceamento (Medida Inicial e Medida Final)
function abrirFaceamentoModal(id) {
    currentCabecoteId = id;
    document.getElementById("face-altura-entrada").value = "";
    document.getElementById("face-altura-saida").value = "";
    document.getElementById("face-plana").checked = true;
    document.getElementById("face-condenado").checked = false;
    document.getElementById("face-operador").value = currentUser ? currentUser.nome_completo : "";
    openModal("modal-faceamento");
}

function toggleCondenadoLabel(chk) {
    if (chk.checked) {
        showToast("Atenção: A condenação descartará a peça e gerará alerta de reposição.", "warning");
    }
}

async function salvarFaceamento() {
    const ent = parseFloat(document.getElementById("face-altura-entrada").value);
    const sai = parseFloat(document.getElementById("face-altura-saida").value);
    const plana = document.getElementById("face-plana").checked;
    const cond = document.getElementById("face-condenado").checked;
    const op = document.getElementById("face-operador").value.trim();

    if (isNaN(ent) || isNaN(sai) || !op) {
        return showToast("Preencha Medida Inicial, Medida Final e Operador.", "warning");
    }

    try {
        const res = await fetch(`${API_BASE}/etapas/faceamento/${currentCabecoteId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                altura_entrada: ent,
                altura_saida: sai,
                plana: plana,
                condenado: cond,
                operador: op
            })
        });

        if (res.ok) {
            if (cond) {
                showToast("Peça condenada! Notificação gerada.", "warning");
            } else {
                showToast("Faceamento (Medida Inicial e Final) salvo com sucesso!");
            }
            closeModal("modal-faceamento");
            loadEtapaList('FACEAMENTO', 'faceamento-list');
        }
    } catch (err) {
        showToast("Erro ao registrar faceamento.", "error");
    }
}

// 5. Ações Lapidação (Confirmação do Vácuo APR / REP + Fluxo Trocar Válvula -> Testar -> Trocar Sede)
function selecionarVacuoOption(val) {
    const radios = document.getElementsByName("lap-vacuo-radio");
    radios.forEach(r => { r.checked = (r.value === val); });
    document.getElementById("label-vacuo-apr").classList.toggle("selected", val === "APR");
    document.getElementById("label-vacuo-rep").classList.toggle("selected", val === "REP");
}

function abrirLapidacaoModal(cabecoteOrId) {
    const cabecote = typeof cabecoteOrId === "object" ? cabecoteOrId : (cacheCabecotes[cabecoteOrId] || {});
    currentCabecoteId = Number(cabecote.id || cabecoteOrId);
    selecionarVacuoOption("APR");

    document.getElementById("lap-trocou-valvula").checked = Boolean(cabecote.lapidacao_trocou_valvula);
    document.getElementById("lap-trocou-sede").checked = Boolean(cabecote.lapidacao_trocou_sede);
    document.getElementById("lap-operador").value = currentUser ? currentUser.nome_completo : "";

    const banner = document.getElementById("lapidacao-retrabalho-banner");
    if (cabecote.lapidacao_status_retrabalho === "TROCAR_VALVULA") {
        banner.style.display = "block";
        banner.className = "alert alert-warning";
        banner.innerHTML = `
            <div>
                <strong>⚠️ 1ª Reprovação no Vácuo Registrada:</strong><br>
                Procedimento obrigatório: <strong>Trocar Válvula</strong>, marcar a confirmação abaixo e realizar novo teste de vácuo.
            </div>
        `;
        document.getElementById("lap-trocou-valvula").checked = true;
    } else if (cabecote.lapidacao_status_retrabalho === "TROCAR_SEDE") {
        banner.style.display = "block";
        banner.className = "alert alert-danger";
        banner.innerHTML = `
            <div>
                <strong>🚨 Reprovou Novamente Após Troca de Válvula:</strong><br>
                Procedimento obrigatório: <strong>Trocar Sede</strong>, marcar a confirmação abaixo e testar novamente o vácuo.
            </div>
        `;
        document.getElementById("lap-trocou-valvula").checked = true;
        document.getElementById("lap-trocou-sede").checked = true;
    } else {
        banner.style.display = "none";
        banner.innerHTML = "";
    }

    openModal("modal-lapidacao");
}

async function salvarLapidacao() {
    const selectedRadio = Array.from(document.getElementsByName("lap-vacuo-radio")).find(r => r.checked);
    const confirmacao_vacuo = selectedRadio ? selectedRadio.value : "APR";
    const trocou_valvula = document.getElementById("lap-trocou-valvula").checked;
    const trocou_sede = document.getElementById("lap-trocou-sede").checked;
    const operador = document.getElementById("lap-operador").value.trim();

    if (!operador) return showToast("Informe o operador responsável.", "warning");

    try {
        const res = await fetch(`${API_BASE}/etapas/lapidacao/${currentCabecoteId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                confirmacao_vacuo,
                trocou_valvula,
                trocou_sede,
                operador
            })
        });

        if (res.ok) {
            const updated = await res.json();
            if (confirmacao_vacuo === "APR") {
                showToast("Vácuo APROVADO (APR)! Peça avançou para a próxima etapa.");
            } else if (updated.lapidacao_status_retrabalho === "TROCAR_VALVULA") {
                showToast("Vácuo REPROVADO! Orientação: Trocar Válvula e Testar novamente.", "warning");
            } else {
                showToast("Vácuo REPROVADO novamente! Orientação: Trocar Sede.", "error");
            }
            closeModal("modal-lapidacao");
            loadEtapaList('LAPIDACAO', 'lapidacao-list');
        }
    } catch (err) {
        showToast("Erro ao salvar lapidação.", "error");
    }
}

// 6. Ações Montagem (Válvula Ex/Ad, Sede Ex/Ad, Guia Ex/Ad)
function abrirMontagemModal(id) {
    currentCabecoteId = id;
    document.getElementById("mont-valvula-exaustao").checked = true;
    document.getElementById("mont-valvula-admissao").checked = true;
    document.getElementById("mont-sede-exaustao").checked = true;
    document.getElementById("mont-sede-admissao").checked = true;
    document.getElementById("mont-guia-exaustao").checked = true;
    document.getElementById("mont-guia-admissao").checked = true;
    document.getElementById("montagem-operador").value = currentUser ? currentUser.nome_completo : "";
    openModal("modal-montagem");
}

async function salvarMontagem() {
    const valvula_exaustao = document.getElementById("mont-valvula-exaustao").checked;
    const valvula_admissao = document.getElementById("mont-valvula-admissao").checked;
    const sede_exaustao = document.getElementById("mont-sede-exaustao").checked;
    const sede_admissao = document.getElementById("mont-sede-admissao").checked;
    const guia_exaustao = document.getElementById("mont-guia-exaustao").checked;
    const guia_admissao = document.getElementById("mont-guia-admissao").checked;
    const operador = document.getElementById("montagem-operador").value.trim();

    if (!operador) return showToast("Informe o operador responsável.", "warning");

    try {
        const res = await fetch(`${API_BASE}/etapas/montagem/${currentCabecoteId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                valvula_exaustao,
                valvula_admissao,
                sede_exaustao,
                sede_admissao,
                guia_exaustao,
                guia_admissao,
                operador
            })
        });

        if (res.ok) {
            showToast("Montagem registrada com sucesso! Enviado para Qualidade.");
            closeModal("modal-montagem");
            loadEtapaList('MONTAGEM', 'montagem-list');
        }
    } catch (err) {
        showToast("Erro ao registrar montagem.", "error");
    }
}

// 7. Ações Qualidade (Fotos + Geração e Salvamento do Relatório Individual no Banco)
function abrirQualidadeModal(id) {
    currentCabecoteId = id;
    uploadedQualidadePhotos = [];
    document.getElementById("qual-files").value = "";
    renderQualidadePhotosPreview("qual-fotos-preview");
    document.getElementById("qual-obs").value = "";
    document.getElementById("qual-aprovado").checked = true;
    document.getElementById("qual-gerar-relatorio").checked = true;
    document.getElementById("qual-tecnico").value = currentUser ? currentUser.nome_completo : "";
    openModal("modal-qualidade");
}

async function salvarQualidade() {
    const aprovada = document.getElementById("qual-aprovado").checked;
    const gerar_relatorio = document.getElementById("qual-gerar-relatorio").checked;
    const observacoes = document.getElementById("qual-obs").value.trim();
    const tecnico = document.getElementById("qual-tecnico").value.trim();

    if (!tecnico) return showToast("Informe o técnico de qualidade.", "warning");

    try {
        const res = await fetch(`${API_BASE}/etapas/qualidade/${currentCabecoteId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                aprovada,
                fotos_urls: uploadedQualidadePhotos,
                observacoes: observacoes || null,
                gerar_relatorio,
                tecnico
            })
        });

        if (res.ok) {
            const cab = await res.json();
            closeModal("modal-qualidade");
            loadEtapaList('QUALIDADE', 'qualidade-list');
            if (aprovada) {
                showToast("Qualidade aprovada e Relatório Individual salvo no banco!");
                abrirRelatorioIndividualModal(cab.id);
            } else {
                showToast("Reprovado na qualidade. Peça retornada à montagem.", "warning");
            }
        }
    } catch (err) {
        showToast("Erro ao registrar controle de qualidade.", "error");
    }
}

// 8. Ações Pintura (Foto -> Pronto / Expedição)
function abrirPinturaModal(id) {
    currentCabecoteId = id;
    document.getElementById("pintura-file").value = "";
    document.getElementById("pint-foto").value = "";
    document.getElementById("pintura-foto-preview").innerHTML = "";
    document.getElementById("pint-passa").checked = true;
    document.getElementById("pint-operador").value = currentUser ? currentUser.nome_completo : "";
    openModal("modal-pintura");
}

async function salvarPintura() {
    const passa = document.getElementById("pint-passa").checked;
    const foto_url = document.getElementById("pint-foto").value.trim() || null;
    const operador = document.getElementById("pint-operador").value.trim();

    if (!operador) return showToast("Operador obrigatório.", "warning");

    try {
        const res = await fetch(`${API_BASE}/etapas/pintura/${currentCabecoteId}`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                passa,
                foto_url,
                operador
            })
        });

        if (res.ok) {
            showToast("Pintura concluída! Peça liberada direto para Expedição.");
            closeModal("modal-pintura");
            loadEtapaList('PINTURA', 'pintura-list');
        }
    } catch (err) {
        showToast("Erro ao registrar pintura.", "error");
    }
}

// 9. Expedição & Almoxarifado (Foto, Número da Nota, Veículo, Motorista)
async function loadAlmoxarifado() {
    try {
        const resStats = await fetch(`${API_BASE}/dashboard/stats`);
        const stats = await resStats.json();

        const slotsContainer = document.getElementById("warehouse-slots-container");
        slotsContainer.innerHTML = "";

        const allSlots = [...stats.almoxarifado_espacos_ocupados, ...stats.almoxarifado_espacos_ociosos].sort();
        allSlots.forEach(s => {
            const isOcupado = stats.almoxarifado_espacos_ocupados.includes(s);
            const div = document.createElement("div");
            div.className = `warehouse-slot ${isOcupado ? 'occupied' : 'idle'}`;
            div.innerHTML = `
                <div>${s}</div>
                <div style="font-size: 0.7rem; margin-top: 4px; font-weight: normal;">
                    ${isOcupado ? 'OCUPADO' : 'LIVRE'}
                </div>
            `;
            slotsContainer.appendChild(div);
        });

        window._cachedFreeSlots = stats.almoxarifado_espacos_ociosos || [];

        // Lotes CONCLUIDO prontos para Expedir
        const resLotes = await fetch(`${API_BASE}/lotes?status=CONCLUIDO`);
        const lotes = await resLotes.json();

        const tbody = document.getElementById("expedicao-list");
        tbody.innerHTML = "";

        if (lotes.length === 0) {
            tbody.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Nenhum lote concluído aguardando expedição.</td></tr>`;
        } else {
            lotes.forEach(l => {
                cacheLotes[l.id] = l;
                const tr = document.createElement("tr");
                const botoesRelatorios = (l.cabecotes || []).map(c => {
                    cacheCabecotes[c.id] = c;
                    return `<button class="btn btn-secondary btn-sm" style="margin:2px;" onclick="abrirRelatorioIndividualModal(${Number(c.id)})">📄 ${escapeHtml(c.numero_serie)}</button>`;
                }).join(" ");

                tr.innerHTML = `
                    <td><strong>${escapeHtml(l.codigo_lote)}</strong></td>
                    <td>${escapeHtml(l.cliente_nome)}</td>
                    <td>${escapeHtml(l.nf_remessa || 'N/A')}</td>
                    <td>${botoesRelatorios}</td>
                    <td>
                        <button class="btn btn-primary btn-sm" onclick="abrirExpedicaoModal(${Number(l.id)})">🚚 Expedir Lote</button>
                    </td>
                `;
                tbody.appendChild(tr);
            });
        }

        // Histórico de Lotes Expedidos
        const resExpedidos = await fetch(`${API_BASE}/lotes?status=EXPEDIDO`);
        const expedidos = await resExpedidos.json();
        const tbodyExp = document.getElementById("expedidos-history-list");
        if (tbodyExp) {
            tbodyExp.innerHTML = "";
            if (expedidos.length === 0) {
                tbodyExp.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Nenhum lote expedido até o momento.</td></tr>`;
            } else {
                expedidos.forEach(l => {
                    cacheLotes[l.id] = l;
                    const tr = document.createElement("tr");
                    const botoesRelatorios = (l.cabecotes || []).map(c => {
                        cacheCabecotes[c.id] = c;
                        return `<button class="btn btn-secondary btn-sm" style="margin:2px;" onclick="abrirRelatorioIndividualModal(${Number(c.id)})">📄 ${escapeHtml(c.numero_serie)}</button>`;
                    }).join(" ");

                    const safeFoto = urlFotoSegura(l.expedicao_foto_url);
                    const fotoHtml = safeFoto
                        ? `<a href="${safeFoto}" target="_blank"><img src="${safeFoto}" style="width:42px; height:42px; object-fit:cover; border-radius:6px; border:1px solid var(--border-glass);"></a>`
                        : `<span class="text-muted">—</span>`;

                    tr.innerHTML = `
                        <td><strong>${escapeHtml(l.codigo_lote)}</strong></td>
                        <td>${escapeHtml(l.cliente_nome)}</td>
                        <td><span class="badge badge-success">${escapeHtml(l.nf_retorno || 'N/A')}</span></td>
                        <td>${escapeHtml(l.veiculo || 'N/A')}</td>
                        <td><strong>${escapeHtml(l.motorista || 'N/A')}</strong></td>
                        <td>${fotoHtml}</td>
                        <td>${botoesRelatorios}</td>
                    `;
                    tbodyExp.appendChild(tr);
                });
            }
        }
    } catch (err) {
        showToast("Erro ao carregar expedição.", "error");
    }
}

function abrirExpedicaoModal(loteId) {
    currentLoteId = Number(loteId);
    const l = cacheLotes[loteId] || {};
    document.getElementById("modal-expedicao-lote-cod").innerText = l.codigo_lote || "";
    document.getElementById("modal-expedicao-lote-cli").innerText = l.cliente_nome || "";
    document.getElementById("exp-file").value = "";
    document.getElementById("exp-foto-url").value = "";
    document.getElementById("exp-foto-preview").innerHTML = "";
    document.getElementById("exp-nf-retorno").value = "";
    document.getElementById("exp-veiculo").value = "";
    document.getElementById("exp-motorista").value = "";

    const select = document.getElementById("exp-pallet");
    select.innerHTML = "";

    const palletAlocado = l.pallet_almoxarifado_final;
    if (palletAlocado) {
        const optAlocado = document.createElement("option");
        optAlocado.value = palletAlocado;
        optAlocado.textContent = `📍 ${palletAlocado} (Alocado)`;
        optAlocado.selected = true;
        select.appendChild(optAlocado);
    }

    const freeSlots = window._cachedFreeSlots || [];
    freeSlots.forEach(s => {
        if (s !== palletAlocado) {
            const opt = document.createElement("option");
            opt.value = s;
            opt.textContent = `🟢 ${s} (Livre)`;
            select.appendChild(opt);
        }
    });

    const optNenhum = document.createElement("option");
    optNenhum.value = "";
    optNenhum.textContent = "-- Sem alocação de pallet --";
    if (!palletAlocado) optNenhum.selected = true;
    select.appendChild(optNenhum);

    openModal("modal-expedicao");
}

async function salvarExpedicao() {
    const foto_url = document.getElementById("exp-foto-url").value.trim() || null;
    const nf_retorno = document.getElementById("exp-nf-retorno").value.trim();
    const veiculo = document.getElementById("exp-veiculo").value.trim();
    const motorista = document.getElementById("exp-motorista").value.trim();
    const horario_saida = document.getElementById("exp-horario").value;
    const pallet_almoxarifado_final = document.getElementById("exp-pallet").value;

    if (!nf_retorno || !veiculo || !motorista) {
        return showToast("Preencha Número da Nota, Veículo e Motorista.", "warning");
    }

    try {
        const res = await fetch(`${API_BASE}/lotes/${currentLoteId}/expedir`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                foto_url,
                nf_retorno,
                veiculo,
                motorista,
                horario_saida,
                pallet_almoxarifado_final
            })
        });

        if (res.ok) {
            showToast("Lote expedido com Nota, Veículo, Motorista e Foto!");
            closeModal("modal-expedicao");
            loadAlmoxarifado();
        } else {
            const err = await res.json();
            showToast(err.detail || "Erro ao expedir lote.", "error");
        }
    } catch (err) {
        showToast("Erro ao expedir lote.", "error");
    }
}

// --- 10. CENTRAL DE RELATÓRIOS TÉCNICOS INDIVIDUAIS (PDF) ---
async function loadRelatoriosScreen() {
    try {
        const res = await fetch(`${API_BASE}/cabecotes/relatorios/lista`);
        cachedRelatoriosList = await res.json();
        renderTabelaRelatorios(cachedRelatoriosList);
    } catch (err) {
        showToast("Erro ao carregar relatórios individuais.", "error");
    }
}

function filtrarTabelaRelatorios(termo) {
    const q = (termo || "").toLowerCase().trim();
    if (!q) {
        renderTabelaRelatorios(cachedRelatoriosList);
        return;
    }
    const filtrados = cachedRelatoriosList.filter(item =>
        (item.numero_serie || "").toLowerCase().includes(q) ||
        (item.cliente_nome || "").toLowerCase().includes(q) ||
        (item.codigo_lote || "").toLowerCase().includes(q) ||
        (item.numero_identificacao_peca || "").toLowerCase().includes(q)
    );
    renderTabelaRelatorios(filtrados);
}

function renderTabelaRelatorios(lista) {
    const tbody = document.getElementById("relatorios-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";

    if (!lista || lista.length === 0) {
        tbody.innerHTML = `<tr><td colspan="7" class="text-center text-muted">Nenhum cabeçote encontrado.</td></tr>`;
        return;
    }

    lista.forEach(item => {
        const tr = document.createElement("tr");
        const statusRel = item.relatorio_gerado
            ? `<span class="badge badge-success">✅ Salvo no Banco (${escapeHtml(item.relatorio_data || 'Pronto')})</span>`
            : `<span class="badge badge-warning">⏳ Em Construção (Disponível Prévia)</span>`;

        tr.innerHTML = `
            <td><strong style="font-family:monospace;">${escapeHtml(item.numero_serie)}</strong></td>
            <td><span class="badge badge-purple">${escapeHtml(item.numero_identificacao_peca || 'N/A')}</span></td>
            <td><span class="badge badge-info">${escapeHtml(item.codigo_lote)}</span></td>
            <td><strong>${escapeHtml(item.cliente_nome)}</strong></td>
            <td><span class="badge badge-info">${escapeHtml(item.status_etapa)}</span></td>
            <td>${statusRel}</td>
            <td>
                <button class="btn btn-primary btn-sm" onclick="abrirRelatorioIndividualModal(${Number(item.cabecote_id)})">
                    📄 Visualizar / Baixar PDF
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// --- MODAL DO RELATÓRIO TÉCNICO INDIVIDUAL (DOWNLOAD / IMPRESSÃO PDF) ---
async function abrirRelatorioIndividualModal(cabecoteId) {
    const container = document.getElementById("printable-relatorio-individual-content");
    container.innerHTML = `<div style="padding: 30px; text-align: center; color: #334155;">Carregando relatório individual do banco de dados...</div>`;
    openModal("modal-relatorio-individual");

    try {
        const res = await fetch(`${API_BASE}/cabecotes/${Number(cabecoteId)}/relatorio`);
        const rel = await res.json();
        const et = rel.etapas || {};
        const lote = rel.lote || {};

        const renderPhotoThumb = (url, label) => {
            const safe = urlFotoSegura(url);
            if (!safe) return `<span style="color:#94a3b8; font-size:0.78rem;">Sem foto anexada</span>`;
            return `
                <div style="margin-top:6px;">
                    <a href="${safe}" target="_blank" rel="noopener noreferrer">
                        <img src="${safe}" alt="${escapeHtml(label)}" style="max-height:110px; max-width:180px; border-radius:6px; border:1px solid #cbd5e1; object-fit:cover;">
                    </a>
                </div>
            `;
        };

        const fotosQual = (et.qualidade?.fotos || []).map(u => urlFotoSegura(u)).filter(Boolean);
        const qualFotosHtml = (fotosQual.length > 0)
            ? `<div style="display:flex; gap:10px; flex-wrap:wrap; margin-top:8px;">
                ${fotosQual.map(u => `<a href="${u}" target="_blank" rel="noopener noreferrer"><img src="${u}" style="height:110px; width:150px; object-fit:cover; border-radius:6px; border:1px solid #cbd5e1;"></a>`).join("")}
               </div>`
            : `<span style="color:#94a3b8; font-size:0.78rem;">Sem fotos adicionais anexadas na qualidade</span>`;

        container.innerHTML = `
            <div style="font-family: 'Inter', sans-serif; color: #0f172a; padding: 8px;">
                <!-- Cabeçalho Oficial -->
                <div style="display:flex; justify-content:space-between; align-items:flex-start; border-bottom: 3px solid #0f172a; padding-bottom: 14px; margin-bottom: 18px;">
                    <div>
                        <h2 style="margin:0; font-size: 1.35rem; color:#0f172a;">LAUDO & RELATÓRIO TÉCNICO INDIVIDUAL DE CABEÇOTE</h2>
                        <p style="margin:4px 0 0 0; font-size: 0.85rem; color:#475569;">SCRC — Rastreabilidade Completa de Recondicionamento e Controle de Qualidade</p>
                    </div>
                    <div style="text-align:right; font-family:monospace; background:#f1f5f9; padding:8px 12px; border-radius:6px; border:1px solid #cbd5e1;">
                        <div style="font-size:1rem; font-weight:700;">${escapeHtml(rel.numero_serie)}</div>
                        <div style="font-size:0.75rem; color:#475569;">Emissão: ${escapeHtml(rel.data_emissao)}</div>
                    </div>
                </div>

                <!-- Dados do Produto e Lote -->
                <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 14px; background:#f8fafc; padding: 14px; border-radius: 8px; border: 1px solid #e2e8f0; margin-bottom: 18px; font-size: 0.85rem;">
                    <div>
                        <p style="margin:3px 0;"><strong>Nº de Série Agregado:</strong> ${escapeHtml(rel.numero_serie)}</p>
                        <p style="margin:3px 0;"><strong>Identificação da Peça (Cliente):</strong> ${escapeHtml(rel.numero_identificacao_peca || 'N/A')}</p>
                        <p style="margin:3px 0;"><strong>Cliente:</strong> ${escapeHtml(lote.cliente_nome || 'N/A')}</p>
                        <p style="margin:3px 0;"><strong>Lote:</strong> ${escapeHtml(lote.codigo_lote || 'N/A')} | <strong>NF Entrada:</strong> ${escapeHtml(lote.nf_remessa || 'N/A')}</p>
                    </div>
                    <div>
                        <p style="margin:3px 0;"><strong>Status Atual da Peça:</strong> <span style="font-weight:700; color:#0284c7;">${escapeHtml(rel.status_etapa)}</span></p>
                        <p style="margin:3px 0;"><strong>NF Saída / Expedição:</strong> ${escapeHtml(lote.nf_retorno || 'Aguardando expedição')}</p>
                        <p style="margin:3px 0;"><strong>Veículo:</strong> ${escapeHtml(lote.veiculo || '—')} | <strong>Motorista:</strong> ${escapeHtml(lote.motorista || '—')}</p>
                        <p style="margin:3px 0;"><strong>Data Entrada:</strong> ${escapeHtml(lote.data_entrada || '—')} | <strong>Saída:</strong> ${escapeHtml(lote.data_saida || '—')}</p>
                    </div>
                </div>

                <!-- Grade das Etapas Técnicas -->
                <h4 style="margin: 0 0 10px 0; font-size: 0.95rem; text-transform: uppercase; color: #1e293b; border-bottom: 1px solid #cbd5e1; padding-bottom: 6px;">
                    📋 Detalhamento Técnico por Etapa do Processo
                </h4>

                <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 12px; font-size: 0.83rem;">
                    <!-- 1. Lavagem -->
                    <div style="border:1px solid #cbd5e1; border-radius:8px; padding:10px;">
                        <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">1. LAVAGEM</div>
                        <div><strong>Confirmado (Checkbox):</strong> ${et.lavagem?.checkbox ? '✅ Sim' : '⏳ Pendente'}</div>
                        <div><strong>Operador:</strong> ${escapeHtml(et.lavagem?.operador || '—')} (${escapeHtml(et.lavagem?.data || '—')})</div>
                        ${renderPhotoThumb(et.lavagem?.foto_url, 'Foto Lavagem')}
                    </div>

                    <!-- 2. Jateamento -->
                    <div style="border:1px solid #cbd5e1; border-radius:8px; padding:10px;">
                        <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">2. JATEAMENTO</div>
                        <div><strong>Confirmado (Checkbox):</strong> ${et.jateamento?.checkbox ? '✅ Sim' : '⏳ Pendente'}</div>
                        <div><strong>Operador:</strong> ${escapeHtml(et.jateamento?.operador || '—')} (${escapeHtml(et.jateamento?.data || '—')})</div>
                        ${renderPhotoThumb(et.jateamento?.foto_url, 'Foto Jateamento')}
                    </div>

                    <!-- 3. Estanqueidade -->
                    <div style="border:1px solid #cbd5e1; border-radius:8px; padding:10px;">
                        <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">3. ESTANQUEIDADE</div>
                        <div><strong>Confirmado (Checkbox):</strong> ${et.estanqueidade?.checkbox ? (et.estanqueidade?.aprovada === false ? '❌ Condenado' : '✅ Aprovado') : '⏳ Pendente'}</div>
                        <div><strong>Pressão Aplicada:</strong> ${escapeHtml(String(et.estanqueidade?.pressao_aplicada != null ? et.estanqueidade.pressao_aplicada + ' bar/PSI' : '—'))}</div>
                        <div><strong>Operador:</strong> ${escapeHtml(et.estanqueidade?.operador || '—')} (${escapeHtml(et.estanqueidade?.data || '—')})</div>
                        ${renderPhotoThumb(et.estanqueidade?.foto_url, 'Foto Estanqueidade')}
                    </div>

                    <!-- 4. Faceamento -->
                    <div style="border:1px solid #cbd5e1; border-radius:8px; padding:10px;">
                        <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">4. FACEAMENTO</div>
                        <div><strong>Medida Inicial:</strong> ${escapeHtml(String(et.faceamento?.medida_inicial != null ? et.faceamento.medida_inicial + ' mm' : '—'))}</div>
                        <div><strong>Medida Final:</strong> ${escapeHtml(String(et.faceamento?.medida_final != null ? et.faceamento.medida_final + ' mm' : '—'))}</div>
                        <div><strong>Desbaste Total:</strong> ${escapeHtml(String(et.faceamento?.desbaste_mm != null ? et.faceamento.desbaste_mm + ' mm' : '—'))} | <strong>Situação:</strong> ${et.faceamento?.condenado ? '❌ Condenado' : (et.faceamento?.concluido ? '✅ Aprovado' : '⏳ Pendente')}</div>
                        <div><strong>Operador:</strong> ${escapeHtml(et.faceamento?.operador || '—')} (${escapeHtml(et.faceamento?.data || '—')})</div>
                    </div>

                    <!-- 5. Lapidação -->
                    <div style="border:1px solid #cbd5e1; border-radius:8px; padding:10px;">
                        <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">5. LAPIDAÇÃO & TESTE DE VÁCUO</div>
                        <div><strong>Confirmação do Vácuo:</strong> ${et.lapidacao?.confirmacao_vacuo === 'APR' ? '✅ APR (Aprovado)' : (et.lapidacao?.confirmacao_vacuo === 'REP' ? '❌ REP (Reprovado)' : '—')}</div>
                        <div><strong>Histórico Retrabalho:</strong> Trocou Válvula: ${et.lapidacao?.trocou_valvula ? 'Sim' : 'Não'} | Trocou Sede: ${et.lapidacao?.trocou_sede ? 'Sim' : 'Não'}</div>
                        <div><strong>Operador:</strong> ${escapeHtml(et.lapidacao?.operador || '—')} (${escapeHtml(et.lapidacao?.data || '—')})</div>
                    </div>

                    <!-- 6. Montagem -->
                    <div style="border:1px solid #cbd5e1; border-radius:8px; padding:10px;">
                        <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">6. MONTAGEM DE COMPONENTES</div>
                        <div><strong>Válvula:</strong> [${et.montagem?.valvula_exaustao ? 'X' : ' '}] Exaustão &nbsp; [${et.montagem?.valvula_admissao ? 'X' : ' '}] Admissão</div>
                        <div><strong>Sede:</strong> [${et.montagem?.sede_exaustao ? 'X' : ' '}] Exaustão &nbsp; [${et.montagem?.sede_admissao ? 'X' : ' '}] Admissão</div>
                        <div><strong>Guia:</strong> [${et.montagem?.guia_exaustao ? 'X' : ' '}] Exaustão &nbsp; [${et.montagem?.guia_admissao ? 'X' : ' '}] Admissão</div>
                        <div><strong>Operador:</strong> ${escapeHtml(et.montagem?.operador || '—')} (${escapeHtml(et.montagem?.data || '—')})</div>
                    </div>
                </div>

                <!-- 7. Qualidade & 8. Pintura & 9. Expedição -->
                <div style="border:1px solid #cbd5e1; border-radius:8px; padding:12px; margin-top:12px; font-size:0.83rem;">
                    <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">7. INSPEÇÃO DE QUALIDADE</div>
                    <div><strong>Parecer da Qualidade:</strong> ${et.qualidade?.aprovada === true ? '✅ APROVADO' : (et.qualidade?.aprovada === false ? '❌ REPROVADO' : '⏳ Pendente')} | <strong>Técnico:</strong> ${escapeHtml(et.qualidade?.tecnico || '—')} (${escapeHtml(et.qualidade?.data || '—')})</div>
                    <div><strong>Observações:</strong> ${escapeHtml(et.qualidade?.observacoes || 'Sem observações adicionais.')}</div>
                    ${qualFotosHtml}
                </div>

                <div style="display:grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-top:12px; font-size:0.83rem;">
                    <div style="border:1px solid #cbd5e1; border-radius:8px; padding:10px;">
                        <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">8. PINTURA</div>
                        <div><strong>Status:</strong> ${et.pintura?.concluida ? '✅ Concluída' : '⏳ Pendente'} | <strong>Operador:</strong> ${escapeHtml(et.pintura?.operador || '—')}</div>
                        ${renderPhotoThumb(et.pintura?.foto_url, 'Foto Pintura')}
                    </div>

                    <div style="border:1px solid #cbd5e1; border-radius:8px; padding:10px;">
                        <div style="font-weight:700; color:#0f172a; margin-bottom:4px;">9. EXPEDIÇÃO</div>
                        <div><strong>Nota Fiscal:</strong> ${escapeHtml(lote.nf_retorno || '—')}</div>
                        <div><strong>Veículo:</strong> ${escapeHtml(lote.veiculo || '—')} | <strong>Motorista:</strong> ${escapeHtml(lote.motorista || '—')}</div>
                        ${renderPhotoThumb(lote.expedicao_foto_url, 'Foto Expedição')}
                    </div>
                </div>
            </div>
        `;
    } catch (err) {
        container.innerHTML = `<div style="padding: 20px; color: red;">Erro ao carregar o relatório técnico individual.</div>`;
    }
}

// Configuração modular: Lapidação
async function verificarConfiguracaoLapidacao() {
    try {
        const res = await fetch(`${API_BASE}/etapas/config`);
        const config = await res.json();

        const toggle = document.getElementById("config-lapidacao-toggle");
        if (toggle) toggle.checked = config.lapidacao_ativa;

        const navItem = document.getElementById("nav-lapidacao");
        if (navItem) {
            navItem.style.display = config.lapidacao_ativa ? "flex" : "none";
        }
    } catch (err) {
        console.error("Falha ao checar config da lapidação.");
    }
}

async function toggleLapidacaoModule(checked) {
    try {
        const res = await fetch(`${API_BASE}/etapas/config`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ lapidacao_ativa: checked })
        });

        if (res.ok) {
            showToast(`Módulo de Lapidação ${checked ? 'ATIVADO' : 'DESATIVADO'}.`);
            verificarConfiguracaoLapidacao();
        }
    } catch (err) {
        showToast("Erro ao alterar configurações.", "error");
    }
}


// ============================================================
// AUTENTICAÇÃO SEGURA, RBAC E GESTÃO DE USUÁRIOS & PERMISSÕES
// ============================================================

function togglePasswordVisibility(inputId, btn) {
    const inp = document.getElementById(inputId);
    if (!inp) return;
    if (inp.type === "password") {
        inp.type = "text";
        if (btn) btn.innerText = "🙈";
    } else {
        inp.type = "password";
        if (btn) btn.innerText = "👁️";
    }
}

function validateLoginInputs() {
    const u = document.getElementById("login-username");
    const p = document.getElementById("login-password");
    const errBox = document.getElementById("login-error-alert");
    if (errBox) errBox.classList.add("hidden");
    if (u) {
        u.value = u.value.replace(/[^a-zA-Z0-9._-]/g, "");
    }
}

async function verificarSessaoInicial() {
    // Remover resquícios legados de token no armazenamento do navegador
    try {
        localStorage.removeItem("scrc_auth_token");
        sessionStorage.removeItem("scrc_auth_token");
    } catch (e) {}

    try {
        const res = await fetch(`${API_BASE}/auth/me`);
        if (res.ok) {
            currentUser = await res.json();
            aplicarSessaoAutenticada();
        } else {
            exibirTelaLogin();
        }
    } catch (err) {
        exibirTelaLogin();
    }
}

function exibirTelaLogin(mensagemErro = null) {
    authToken = null;
    currentUser = null;
    try {
        localStorage.removeItem("scrc_auth_token");
        sessionStorage.removeItem("scrc_auth_token");
    } catch (e) {}
    if (refreshTimer) clearInterval(refreshTimer);

    const overlay = document.getElementById("login-overlay");
    const mainApp = document.getElementById("main-app-container");
    if (overlay) overlay.style.display = "flex";
    if (mainApp) mainApp.style.display = "none";

    const errBox = document.getElementById("login-error-alert");
    if (errBox) {
        if (mensagemErro) {
            errBox.innerText = `⚠️ ${mensagemErro}`;
            errBox.classList.remove("hidden");
        } else {
            errBox.classList.add("hidden");
        }
    }
}

function forcarLogoutSessao(motivo) {
    exibirTelaLogin(motivo);
}

async function handleLoginSubmit(event) {
    event.preventDefault();
    const usernameInput = document.getElementById("login-username");
    const passwordInput = document.getElementById("login-password");
    const errBox = document.getElementById("login-error-alert");
    const submitBtn = document.getElementById("btn-login-submit");

    const username = (usernameInput.value || "").trim().toLowerCase();
    const password = passwordInput.value || "";

    if (username.length < 3) {
        errBox.innerText = "⚠️ Informe um usuário válido (mínimo 3 caracteres).";
        errBox.classList.remove("hidden");
        return;
    }
    if (!password) {
        errBox.innerText = "⚠️ Digite sua senha de acesso.";
        errBox.classList.remove("hidden");
        return;
    }

    submitBtn.disabled = true;
    submitBtn.innerHTML = `<span>⏳ Verificando credenciais...</span>`;

    try {
        const res = await fetch(`${API_BASE}/auth/login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ username, password })
        });

        const data = await res.json();

        if (res.ok) {
            currentUser = data.usuario;
            passwordInput.value = "";
            errBox.classList.add("hidden");
            try {
                localStorage.removeItem("scrc_auth_token");
                sessionStorage.removeItem("scrc_auth_token");
            } catch (e) {}
            showToast(`Bem-vindo(a), ${currentUser.nome_completo}!`, "success");
            aplicarSessaoAutenticada();
        } else {
            errBox.innerText = `❌ ${data.detail || "Falha na autenticação."}`;
            errBox.classList.remove("hidden");
        }
    } catch (err) {
        errBox.innerText = "❌ Erro de comunicação com o servidor de segurança.";
        errBox.classList.remove("hidden");
    } finally {
        submitBtn.disabled = false;
        submitBtn.innerHTML = `<span>🔐 Entrar no Sistema</span>`;
    }
}

function exigirTrocaDeSenhaObrigatoria() {
    abrirAlterarSenhaModal();
    const closeBtn = document.getElementById("btn-close-alterar-senha");
    if (closeBtn) closeBtn.style.display = "none";
    const title = document.getElementById("modal-alterar-senha-title");
    if (title) title.innerText = "🔑 Troca de Senha Obrigatória no Primeiro Acesso";
    showToast("Por motivos de segurança, você deve redefinir sua senha inicial antes de continuar.", "warning");
}

function aplicarSessaoAutenticada() {
    const oldSeedBtn = document.getElementById("btn-seed-demo");
    if (oldSeedBtn) oldSeedBtn.remove();

    const overlay = document.getElementById("login-overlay");
    const mainApp = document.getElementById("main-app-container");
    if (overlay) overlay.style.display = "none";
    if (mainApp) mainApp.style.display = "grid";

    // Atualizar cabeçalho do usuário logado
    const nameEl = document.getElementById("logged-user-name");
    const badgeEl = document.getElementById("logged-user-badge");
    const avatarEl = document.getElementById("logged-user-avatar");
    const roleFooter = document.getElementById("sidebar-user-role");
    const topAdminBtn = document.getElementById("btn-top-admin-panel");

    if (nameEl) nameEl.innerText = currentUser.nome_completo;
    if (badgeEl) {
        badgeEl.innerText = currentUser.is_admin ? "👑 ADMIN" : `👤 ${currentUser.cargo || "OPERADOR"}`;
        badgeEl.className = currentUser.is_admin ? "badge badge-warning" : "badge badge-info";
    }
    if (topAdminBtn) {
        topAdminBtn.style.display = currentUser.is_admin ? "inline-flex" : "none";
    }
    const mobileAdminBtn = document.getElementById("mobile-nav-admin");
    if (mobileAdminBtn) {
        mobileAdminBtn.style.display = currentUser.is_admin ? "flex" : "none";
    }
    document.querySelectorAll(".mobile-nav-btn[data-screen]").forEach(btn => {
        const mod = btn.getAttribute("data-screen");
        if (mod && mod !== "usuarios") {
            btn.style.display = usuarioTemPermissao(mod) ? "flex" : "none";
        }
    });
    if (avatarEl) {
        const parts = (currentUser.nome_completo || "OP").trim().split(" ");
        avatarEl.innerText = parts.length > 1
            ? (parts[0][0] + parts[parts.length - 1][0]).toUpperCase()
            : parts[0].substring(0, 2).toUpperCase();
    }
    if (roleFooter) {
        roleFooter.innerText = `${currentUser.username} (${currentUser.is_admin ? "Admin" : "Autenticado"})`;
    }

    // Filtrar itens do menu lateral conforme permissões do usuário
    document.querySelectorAll(".nav-menu .nav-item").forEach(item => {
        const onclickAttr = item.getAttribute("onclick") || "";
        const match = onclickAttr.match(/navigate\('([^']+)'\)/);
        if (match && match[1]) {
            const mod = match[1];
            item.style.display = usuarioTemPermissao(mod) ? "flex" : "none";
        }
    });

    verificarConfiguracaoLapidacao();

    // Se o usuário precisa trocar de senha obrigatoriamente
    if (currentUser.must_change_password) {
        exigirTrocaDeSenhaObrigatoria();
        return;
    }

    // Navegar para a primeira tela permitida
    if (usuarioTemPermissao("dashboard")) {
        navigate("dashboard");
    } else if (currentUser.permissoes && currentUser.permissoes.length > 0) {
        navigate(currentUser.permissoes[0]);
    } else {
        showToast("Sua conta ainda não possui módulos atribuídos. Contate o Administrador.", "warning");
    }
}

async function handleLogout() {
    try {
        await fetch(`${API_BASE}/auth/logout`, { method: "POST" });
    } catch (err) {
        // Ignorar erro de rede ao deslogar
    }
    exibirTelaLogin();
    showToast("Sessão encerrada com segurança.", "info");
}

// --- MEDIDOR INTERATIVO DE FORÇA DE SENHA ---
function avaliarForcaSenha(senha, containerId = "usr-pass-meter") {
    const val = senha || "";
    const hasLen = val.length >= 8;
    const hasUpper = /[A-Z]/.test(val);
    const hasLower = /[a-z]/.test(val);
    const hasNum = /[0-9]/.test(val);
    const hasSpec = /[^A-Za-z0-9]/.test(val);

    const score = [hasLen, hasUpper, hasLower, hasNum, hasSpec].filter(Boolean).length;
    const container = document.getElementById(containerId);
    if (!container) return score === 5;

    const bar = container.querySelector(".strength-bar-fill");
    if (bar) {
        const pct = (score / 5) * 100;
        bar.style.width = `${pct}%`;
        if (score <= 2) bar.style.background = "var(--danger)";
        else if (score <= 4) bar.style.background = "var(--warning)";
        else bar.style.background = "var(--success)";
    }

    if (containerId === "usr-pass-meter") {
        const setRule = (id, ok) => {
            const el = document.getElementById(id);
            if (el) el.className = `rule-item ${ok ? "valid" : ""}`;
        };
        setRule("rule-len", hasLen);
        setRule("rule-upper", hasUpper);
        setRule("rule-lower", hasLower);
        setRule("rule-num", hasNum);
        setRule("rule-spec", hasSpec);
    } else {
        const setRuleAttr = (ruleName, ok) => {
            const el = container.querySelector(`[data-rule="${ruleName}"]`);
            if (el) el.className = `rule-item ${ok ? "valid" : ""}`;
        };
        setRuleAttr("len", hasLen);
        setRuleAttr("upper", hasUpper);
        setRuleAttr("lower", hasLower);
        setRuleAttr("num", hasNum);
        setRuleAttr("spec", hasSpec);
    }

    return score === 5;
}

// --- ALTERAR PRÓPRIA SENHA ---
function abrirAlterarSenhaModal() {
    document.getElementById("alt-senha-atual").value = "";
    document.getElementById("alt-nova-senha").value = "";
    avaliarForcaSenha("", "alt-pass-meter");
    openModal("modal-alterar-senha");
}

async function salvarAlteracaoSenha(event) {
    event.preventDefault();
    const senha_atual = document.getElementById("alt-senha-atual").value;
    const nova_senha = document.getElementById("alt-nova-senha").value;

    if (!avaliarForcaSenha(nova_senha, "alt-pass-meter")) {
        return showToast("A nova senha precisa atender a todos os 5 requisitos de segurança.", "warning");
    }

    try {
        const res = await fetch(`${API_BASE}/auth/alterar-senha`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ senha_atual, nova_senha })
        });
        const data = await res.json();
        if (res.ok) {
            showToast("Senha alterada com sucesso!");
            const closeBtn = document.getElementById("btn-close-alterar-senha");
            if (closeBtn) closeBtn.style.display = "";
            closeModal("modal-alterar-senha");

            // Atualizar perfil atual
            const meRes = await fetch(`${API_BASE}/auth/me`);
            if (meRes.ok) {
                currentUser = await meRes.json();
                aplicarSessaoAutenticada();
            }
        } else {
            showToast(data.detail || "Erro ao alterar senha.", "error");
        }
    } catch (err) {
        showToast("Erro de rede ao alterar senha.", "error");
    }
}

// --- GESTÃO DE USUÁRIOS E PERMISSÕES (EXCLUSIVO ADMIN) ---
function renderPermissoesCheckboxes() {
    const grid = document.getElementById("usr-permissoes-grid");
    if (!grid) return;
    grid.innerHTML = PERMISSOES_CATALOGO.map(item => `
        <label class="perm-checkbox-card">
            <input type="checkbox" class="usr-perm-chk" value="${item.key}">
            <div>
                <div style="font-weight:600; font-size:0.84rem;">${item.label}</div>
                <small class="text-muted" style="font-size:0.7rem;">Grupo: ${item.group}</small>
            </div>
        </label>
    `).join("");
}

function toggleAdminPermissionsBox(isAdmin) {
    const section = document.getElementById("usr-permissoes-section");
    if (!section) return;
    if (isAdmin) {
        section.style.opacity = "0.5";
        section.style.pointerEvents = "none";
        selecionarPresetPermissoes("todos");
    } else {
        section.style.opacity = "1";
        section.style.pointerEvents = "auto";
    }
}

function selecionarPresetPermissoes(preset) {
    const chks = document.querySelectorAll(".usr-perm-chk");
    const oficinaKeys = ["lavagem", "jateamento", "estanqueidade", "faceamento", "lapidacao", "montagem"];
    const qualExpKeys = ["dashboard", "qualidade", "pintura", "expedicao", "relatorios"];

    chks.forEach(c => {
        if (preset === "todos") c.checked = true;
        else if (preset === "nenhum") c.checked = false;
        else if (preset === "oficina") c.checked = oficinaKeys.includes(c.value);
        else if (preset === "qualidade_exp") c.checked = qualExpKeys.includes(c.value);
    });
}

async function loadUsuariosScreen() {
    if (!currentUser || !currentUser.is_admin) return;
    const tbody = document.getElementById("usuarios-table-body");
    if (!tbody) return;
    tbody.innerHTML = `<tr><td colspan="7" class="text-center">Carregando usuários...</td></tr>`;

    try {
        const res = await fetch(`${API_BASE}/usuarios`);
        const usuarios = await res.json();
        tbody.innerHTML = "";

        const agora = new Date();
        const totalUsers = usuarios.length;
        const totalAdmins = usuarios.filter(u => u.is_admin).length;
        const totalComuns = usuarios.filter(u => !u.is_admin).length;
        const totalBloqueados = usuarios.filter(u => !u.ativo || (u.bloqueado_ate && new Date(u.bloqueado_ate + "Z") > agora)).length;

        const elTotal = document.getElementById("admin-kpi-total");
        const elAdmins = document.getElementById("admin-kpi-admins");
        const elComuns = document.getElementById("admin-kpi-comuns");
        const elBloq = document.getElementById("admin-kpi-bloqueados");
        if (elTotal) elTotal.innerText = totalUsers;
        if (elAdmins) elAdmins.innerText = totalAdmins;
        if (elComuns) elComuns.innerText = totalComuns;
        if (elBloq) elBloq.innerText = totalBloqueados;

        usuarios.forEach(u => {
            cacheUsuarios[u.id] = u;
            const tr = document.createElement("tr");

            const perfilBadge = u.is_admin
                ? `<span class="badge badge-warning">👑 Administrador</span>`
                : `<span class="badge badge-info">👤 Usuário Comum</span>`;

            let permsHtml = "";
            if (u.is_admin) {
                permsHtml = `<span class="badge badge-success">Acesso Total Irrestrito</span>`;
            } else if (!u.permissoes || u.permissoes.length === 0) {
                permsHtml = `<span class="badge badge-danger">Nenhuma permissão</span>`;
            } else {
                permsHtml = u.permissoes.map(p => {
                    const found = PERMISSOES_CATALOGO.find(cat => cat.key === p);
                    return `<span class="badge badge-info" style="margin:2px; font-size:0.7rem;">${escapeHtml(found ? found.label : p)}</span>`;
                }).join("");
            }

            const agora = new Date();
            const bloqueado = u.bloqueado_ate && new Date(u.bloqueado_ate + "Z") > agora;
            let statusHtml = u.ativo
                ? `<span class="badge badge-success">Ativo</span>`
                : `<span class="badge badge-danger">Inativo</span>`;
            if (bloqueado) {
                statusHtml += ` <span class="badge badge-danger">🔒 Bloqueado (${Number(u.tentativas_falhas)} falhas)</span>`;
            }

            const ultimoLoginStr = u.ultimo_login
                ? new Date(u.ultimo_login + "Z").toLocaleString("pt-BR")
                : "Nunca acessou";

            const btnDesbloquear = (bloqueado || u.tentativas_falhas > 0)
                ? `<button class="btn btn-secondary btn-sm" onclick="desbloquearUsuario(${Number(u.id)})" title="Limpar falhas e desbloquear">🔓 Desbloquear</button>`
                : "";

            const btnExcluir = (u.username !== "admin" && u.id !== currentUser.id)
                ? `<button class="btn btn-danger btn-sm" onclick="excluirUsuario(${Number(u.id)})">🗑️</button>`
                : "";

            tr.innerHTML = `
                <td><strong style="font-family:monospace;">${escapeHtml(u.username)}</strong></td>
                <td>
                    <strong>${escapeHtml(u.nome_completo)}</strong>
                    <div class="text-muted" style="font-size:0.75rem;">${escapeHtml(u.cargo || 'Operador')}</div>
                </td>
                <td>${perfilBadge}</td>
                <td style="max-width:340px;">${permsHtml}</td>
                <td>${statusHtml}</td>
                <td style="font-size:0.8rem;">${escapeHtml(ultimoLoginStr)}</td>
                <td>
                    <div style="display:flex; gap:6px; flex-wrap:wrap;">
                        <button class="btn btn-primary btn-sm" onclick="editarUsuarioModal(${Number(u.id)})">✏️ Permissões / Editar</button>
                        ${btnDesbloquear}
                        ${btnExcluir}
                    </div>
                </td>
            `;
            tbody.appendChild(tr);
        });
    } catch (err) {
        showToast("Erro ao carregar lista de usuários.", "error");
    }

    // Carregar também o diagnóstico das 20 verificações de segurança
    loadPainelSeguranca20Itens();
}

// --- DIAGNÓSTICO DAS 20 VERIFICAÇÕES DE SEGURANÇA, BACKUP E MONITORAMENTO ---
async function loadPainelSeguranca20Itens() {
    if (!currentUser || !currentUser.is_admin) return;
    const grid = document.getElementById("sec-20-grid");
    if (!grid) return;

    try {
        const res = await fetch(`${API_BASE}/seguranca/painel`);
        if (!res.ok) return;
        const data = await res.json();

        const badgeResumo = document.getElementById("sec-score-badge");
        if (badgeResumo) {
            const scoreOk = data.score?.ok != null ? data.score.ok : (data.score_seguranca ? data.score_seguranca.split("/")[0] : 0);
            const scoreTotal = data.score?.total != null ? data.score.total : 20;
            badgeResumo.innerText = `${scoreOk}/${scoreTotal} ATIVAS (${data.status_geral || "PROTEGIDO"})`;
            if (data.status_geral === "PROTEGIDO") {
                badgeResumo.className = "badge badge-success";
            } else if (data.status_geral === "ATENCAO") {
                badgeResumo.className = "badge badge-warning";
            } else {
                badgeResumo.className = "badge badge-danger";
            }
        }

        // Renderizar os 20 cartões de verificação dinâmica
        const listaVerificacoes = data.verificacoes || [];
        if (Array.isArray(listaVerificacoes)) {
            grid.innerHTML = listaVerificacoes.map(item => {
                let badgeClass = "badge badge-success";
                let icon = "✅";
                let borderStyle = "border: 1px solid rgba(16, 185, 129, 0.35);";
                if (item.status === "ATENCAO") {
                    badgeClass = "badge badge-warning";
                    icon = "⚠️";
                    borderStyle = "border: 1px solid rgba(245, 158, 11, 0.45);";
                } else if (item.status === "FALHA") {
                    badgeClass = "badge badge-danger";
                    icon = "❌";
                    borderStyle = "border: 1px solid rgba(239, 68, 68, 0.55);";
                }
                const acaoHtml = item.acao
                    ? `<div style="font-size:0.7rem; color:#fde68a; margin-top:2px;">💡 ${escapeHtml(item.acao)}</div>`
                    : "";
                return `
                    <div style="background: rgba(15, 23, 42, 0.72); ${borderStyle} border-radius: 10px; padding: 10px 12px; display: flex; flex-direction: column; gap: 4px;">
                        <div style="display: flex; justify-content: space-between; align-items: center; gap: 6px;">
                            <strong style="font-size: 0.82rem; color: #f8fafc;">#${Number(item.numero)}. ${escapeHtml(item.item)}</strong>
                            <span class="${badgeClass}" style="font-size: 0.65rem; padding: 2px 6px;">${icon} ${escapeHtml(item.status)}</span>
                        </div>
                        <span style="font-size: 0.74rem; color: #94a3b8; line-height: 1.35;">${escapeHtml(item.detalhe)}</span>
                        ${acaoHtml}
                    </div>
                `;
            }).join("");
        }

        // Renderizar Monitoramento e Alertas de Segurança (Item 20)
        const tbodyEventos = document.getElementById("sec-audit-logs-body");
        if (tbodyEventos) {
            const evts = data.logs_recentes || [];
            if (evts.length === 0) {
                tbodyEventos.innerHTML = `<tr><td colspan="5" class="text-center text-muted">Nenhum evento registrado.</td></tr>`;
            } else {
                tbodyEventos.innerHTML = evts.map(ev => {
                    const dtStr = ev.data_hora ? new Date(ev.data_hora + "Z").toLocaleString("pt-BR") : "-";
                    let sevBadge = `<span class="badge badge-info" style="font-size:0.65rem;">INFO</span>`;
                    if (ev.severidade === "WARN" || ev.severidade === "MEDIA") sevBadge = `<span class="badge badge-warning" style="font-size:0.65rem;">ALERTA</span>`;
                    if (ev.severidade === "CRITICAL" || ev.severidade === "ALTA") sevBadge = `<span class="badge badge-danger" style="font-size:0.65rem;">CRÍTICO</span>`;
                    return `
                        <tr>
                            <td style="font-size:0.72rem; white-space:nowrap;">${escapeHtml(dtStr)}</td>
                            <td>${sevBadge}</td>
                            <td><strong style="font-size:0.73rem;">${escapeHtml(ev.evento)}</strong></td>
                            <td style="font-size:0.72rem; font-family:monospace;">${escapeHtml(ev.usuario || "-")} <br><span class="text-muted">${escapeHtml(ev.ip_origem || "")}</span></td>
                            <td style="font-size:0.73rem;">${escapeHtml(ev.detalhes || "")}</td>
                        </tr>
                    `;
                }).join("");
            }
        }

        // Renderizar Lista de Backups Criptografados (Item 17 & 19)
        const tbodyBackups = document.getElementById("sec-backups-body");
        if (tbodyBackups) {
            const listaBkp = data.backups || [];
            if (listaBkp.length === 0) {
                tbodyBackups.innerHTML = `<tr><td colspan="4" class="text-center text-muted">Nenhum snapshot disponível.</td></tr>`;
            } else {
                tbodyBackups.innerHTML = listaBkp.map(b => {
                    const dtStr = b.criado_em ? new Date(b.criado_em + "Z").toLocaleString("pt-BR") : "-";
                    const badgeTipo = b.tipo && b.tipo.includes("AUTO")
                        ? `<span class="badge badge-info" style="font-size:0.68rem;">⏰ Auto 24h</span>`
                        : `<span class="badge badge-warning" style="font-size:0.68rem;">💾 Manual</span>`;
                    return `
                        <tr>
                            <td style="font-size:0.75rem; white-space:nowrap;">${escapeHtml(dtStr)}</td>
                            <td>${badgeTipo}</td>
                            <td style="font-size:0.74rem; font-family:monospace;">${escapeHtml(b.autor || "sistema")}</td>
                            <td style="font-size:0.73rem;">
                                <div>${escapeHtml(b.resumo_registros || "")}</div>
                                <code style="font-size:0.68rem; color:#38bdf8;" title="${escapeHtml(b.sha256_checksum)}">SHA-256: ${escapeHtml((b.sha256_checksum || "").substring(0, 16))}...</code>
                            </td>
                        </tr>
                    `;
                }).join("");
            }
        }
    } catch (err) {
        console.error("Erro ao carregar diagnóstico de segurança:", err);
    }
}

async function gerarBackupManual() {
    try {
        showToast("Gerando snapshot criptografado (CTR-HMAC-SHA256)...", "info");
        const res = await fetch(`${API_BASE}/seguranca/backup`, { method: "POST" });
        const data = await res.json();
        if (res.ok) {
            showToast(`Backup #${data.backup_id} criptografado com sucesso! SHA-256: ${(data.sha256_checksum || "").substring(0, 12)}...`);
            loadPainelSeguranca20Itens();
        } else {
            showToast(data.detail || "Falha ao gerar backup.", "error");
        }
    } catch (err) {
        showToast("Erro de rede ao gerar backup manual.", "error");
    }
}

async function exportarBackupJson() {
    try {
        showToast("Preparando download seguro do backup criptografado (.scrcbak)...", "info");
        const res = await fetch(`${API_BASE}/seguranca/backup/exportar`);
        if (!res.ok) {
            return showToast("Não foi possível exportar o backup.", "error");
        }
        const blob = await res.blob();
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `scrc_backup_seguro_${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "-")}.scrcbak`;
        document.body.appendChild(a);
        a.click();
        a.remove();
        window.URL.revokeObjectURL(url);
        showToast("Download do backup criptografado concluído!");
        loadPainelSeguranca20Itens();
    } catch (err) {
        showToast("Erro ao baixar arquivo de backup.", "error");
    }
}

function abrirModalUsuario() {
    document.getElementById("modal-usuario-title").innerText = "➕ Cadastrar Novo Usuário";
    document.getElementById("usr-id").value = "";
    const usernameEl = document.getElementById("usr-username");
    usernameEl.value = "";
    usernameEl.disabled = false;
    document.getElementById("usr-nome").value = "";
    document.getElementById("usr-cargo").value = "Operador";
    const passEl = document.getElementById("usr-password");
    passEl.value = "";
    passEl.required = true;
    document.getElementById("label-usr-password").innerText = "Senha de Acesso *";
    document.getElementById("usr-is-admin").checked = false;
    document.getElementById("usr-ativo").checked = true;

    avaliarForcaSenha("", "usr-pass-meter");
    toggleAdminPermissionsBox(false);
    selecionarPresetPermissoes("oficina");
    openModal("modal-usuario");
}

function editarUsuarioModal(uOrId) {
    const u = (typeof uOrId === "object" && uOrId !== null) ? uOrId : (cacheUsuarios[uOrId] || {});
    document.getElementById("modal-usuario-title").innerText = `✏️ Editar Usuário e Permissões: ${u.username || ''}`;
    document.getElementById("usr-id").value = u.id || "";
    const usernameEl = document.getElementById("usr-username");
    usernameEl.value = u.username || "";
    usernameEl.disabled = true;
    document.getElementById("usr-nome").value = u.nome_completo || "";
    document.getElementById("usr-cargo").value = u.cargo || "Operador";
    const passEl = document.getElementById("usr-password");
    passEl.value = "";
    passEl.required = false;
    document.getElementById("label-usr-password").innerText = "Nova Senha (deixe em branco para manter a atual)";
    document.getElementById("usr-is-admin").checked = Boolean(u.is_admin);
    document.getElementById("usr-ativo").checked = Boolean(u.ativo);

    avaliarForcaSenha("", "usr-pass-meter");
    toggleAdminPermissionsBox(Boolean(u.is_admin));

    const perms = u.permissoes || [];
    document.querySelectorAll(".usr-perm-chk").forEach(chk => {
        chk.checked = perms.includes(chk.value);
    });

    openModal("modal-usuario");
}

async function salvarUsuarioSubmit(event) {
    event.preventDefault();
    const id = document.getElementById("usr-id").value;
    const username = document.getElementById("usr-username").value.trim().toLowerCase();
    const nome_completo = document.getElementById("usr-nome").value.trim();
    const cargo = document.getElementById("usr-cargo").value.trim();
    const password = document.getElementById("usr-password").value;
    const is_admin = document.getElementById("usr-is-admin").checked;
    const ativo = document.getElementById("usr-ativo").checked;

    const permissoes = Array.from(document.querySelectorAll(".usr-perm-chk"))
        .filter(c => c.checked)
        .map(c => c.value);

    if (!id || password.length > 0) {
        if (!avaliarForcaSenha(password, "usr-pass-meter")) {
            return showToast("A senha deve cumprir todos os 5 critérios de segurança (8+ caracteres, maiúscula, minúscula, número e especial).", "warning");
        }
    }

    if (!is_admin && permissoes.length === 0) {
        return showToast("Selecione pelo menos uma permissão de módulo para o usuário comum.", "warning");
    }

    try {
        let res;
        if (!id) {
            res = await fetch(`${API_BASE}/usuarios`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ username, nome_completo, cargo, password, is_admin, ativo, permissoes })
            });
        } else {
            const payload = { nome_completo, cargo, is_admin, ativo, permissoes };
            if (password.length > 0) payload.password = password;
            res = await fetch(`${API_BASE}/usuarios/${Number(id)}`, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(payload)
            });
        }

        const data = await res.json();
        if (res.ok) {
            showToast(id ? "Usuário e permissões atualizados!" : "Novo usuário cadastrado com sucesso!");
            closeModal("modal-usuario");
            loadUsuariosScreen();
            if (currentUser && Number(id) === currentUser.id) {
                currentUser = data;
                aplicarSessaoAutenticada();
            }
        } else {
            showToast(data.detail || "Erro ao salvar usuário.", "error");
        }
    } catch (err) {
        showToast("Erro de rede ao salvar usuário.", "error");
    }
}

async function desbloquearUsuario(id) {
    try {
        const res = await fetch(`${API_BASE}/usuarios/${Number(id)}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ desbloquear: true })
        });
        if (res.ok) {
            showToast("Conta desbloqueada com sucesso!");
            loadUsuariosScreen();
        }
    } catch (err) {
        showToast("Erro ao desbloquear conta.", "error");
    }
}

async function excluirUsuario(id) {
    const u = cacheUsuarios[id] || {};
    const username = u.username || `ID ${id}`;
    if (!confirm(`Tem certeza que deseja excluir permanentemente o usuário '${username}'?`)) return;
    try {
        const res = await fetch(`${API_BASE}/usuarios/${Number(id)}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || "Usuário removido.");
            loadUsuariosScreen();
        } else {
            showToast(data.detail || "Não foi possível excluir.", "error");
        }
    } catch (err) {
        showToast("Erro ao excluir usuário.", "error");
    }
}
