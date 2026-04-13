// Aplicacao de Controle de Neonatos

const API_BASE = '';

let categoriaAtual = 'pre_termo';
let pacientes = [];
let mesesExpandidos = {};

const NOMES_MESES = {
    '01': 'Janeiro', '02': 'Fevereiro', '03': 'Março', '04': 'Abril',
    '05': 'Maio', '06': 'Junho', '07': 'Julho', '08': 'Agosto',
    '09': 'Setembro', '10': 'Outubro', '11': 'Novembro', '12': 'Dezembro'
};

// Inicializacao
window.addEventListener('DOMContentLoaded', () => {
    carregarCategorias();
});

// Carregar categorias
async function carregarCategorias() {
    try {
        const res = await fetch(`${API_BASE}/api/categorias`);
        const cats = await res.json();

        cats.forEach(c => {
            const el = document.getElementById(`count-${c.categoria}`);
            if (el) el.textContent = c.total;
        });

        selecionarCategoria('pre_termo');
    } catch (e) {
        console.error('Erro:', e);
        document.getElementById('conteudo-dados').innerHTML =
            '<div class="loading"><p>Erro ao carregar. Verifique o servidor.</p></div>';
    }
}

// Selecionar categoria
async function selecionarCategoria(categoria) {
    categoriaAtual = categoria;
    mesesExpandidos = {};

    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.toggle('ativa', btn.onclick.toString().includes(categoria));
    });

    await carregarPacientes();
}

// Carregar pacientes
async function carregarPacientes() {
    try {
        const res = await fetch(`${API_BASE}/api/pacientes?categoria=${categoriaAtual}`);
        pacientes = await res.json();
        renderizar();
        atualizarDashboard();
    } catch (e) {
        document.getElementById('conteudo-dados').innerHTML =
            '<div class="loading"><p>Erro ao carregar pacientes</p></div>';
    }
}

// Toggle consulta
async function toggleConsulta(id) {
    try {
        await fetch(`${API_BASE}/api/consultas/toggle`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ paciente_id: id })
        });
        await carregarPacientes();
        atualizarDashboard();
    } catch (e) {
        alert('Erro ao marcar consulta');
    }
}

// Toggle todos do mes
async function toggleTodosMes(pacientesDoMes, marcado) {
    try {
        for (const p of pacientesDoMes) {
            await fetch(`${API_BASE}/api/consultas/toggle`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ paciente_id: p.id })
            });
        }
        await carregarPacientes();
        atualizarDashboard();
    } catch (e) {
        alert('Erro ao marcar consultas');
    }
}

// Toggle mes
window.toggleMes = function(ano, mes) {
    const key = `${ano}_${mes}`;
    mesesExpandidos[key] = !mesesExpandidos[key];
    renderizar();
};

// Filtrar
window.filtrar = function() {
    renderizar();
};

// Resetar filtros
window.resetarFiltros = function() {
    document.getElementById('busca-nome').value = '';
    document.getElementById('busca-prontuario').value = '';
    document.getElementById('filtro-status').value = '';
    renderizar();
};

// Mudar categoria
window.mudarCategoria = function(categoria) {
    selecionarCategoria(categoria);
};

// Obter pacientes filtrados
function getPacientesFiltrados() {
    let p = [...pacientes];

    const nome = document.getElementById('busca-nome').value.toLowerCase();
    const prontuario = document.getElementById('busca-prontuario').value;
    const status = document.getElementById('filtro-status').value;

    if (nome) p = p.filter(x => x.nome.toLowerCase().includes(nome));
    if (prontuario) p = p.filter(x => x.prontuario.includes(prontuario));
    if (status === 'consultado') p = p.filter(x => x.consultado);
    else if (status === 'pendente') p = p.filter(x => !x.consultado);

    return p;
}

// Renderizar
function renderizar() {
    const div = document.getElementById('conteudo-dados');
    const filtrados = getPacientesFiltrados();

    // Atualizar info
    const infoDiv = document.getElementById('info-resultados');
    if (filtrados.length === 0) {
        infoDiv.textContent = 'Nenhum paciente encontrado';
    } else {
        const consultados = filtrados.filter(p => p.consultado).length;
        infoDiv.textContent = `${filtrados.length} paciente(s) encontrado(s) - ${consultados} consultado(s)`;
    }

    if (filtrados.length === 0) {
        div.innerHTML = '<div class="loading"><p>Nenhum paciente encontrado</p></div>';
        return;
    }

    // Agrupar: ano -> mes
    const agrupado = {};
    filtrados.forEach(p => {
        if (!agrupado[p.ano]) agrupado[p.ano] = {};
        if (!agrupado[p.ano][p.mes]) agrupado[p.ano][p.mes] = [];
        agrupado[p.ano][p.mes].push(p);
    });

    let html = '';

    Object.keys(agrupado).sort().reverse().forEach(ano => {
        const meses = agrupado[ano];
        const totalAno = Object.values(meses).flat().length;
        const consultadosAno = Object.values(meses).flat().filter(p => p.consultado).length;

        html += `<div class="grupo-ano">`;
        html += `<div class="ano-header">
            <span>Ano ${ano}</span>
            <span class="ano-stats">${consultadosAno}/${totalAno} consultados</span>
        </div>`;

        Object.keys(meses).sort().forEach(mes => {
            const pacientesMes = meses[mes];
            const totalMes = pacientesMes.length;
            const consultadosMes = pacientesMes.filter(p => p.consultado).length;
            const mesKey = `${ano}_${mes}`;
            const expandido = mesesExpandidos[mesKey] !== false;

            html += `<div class="grupo-mes">`;
            html += `<div class="mes-header" onclick="toggleMes('${ano}','${mes}')">
                <span><span class="toggle-arrow ${expandido ? 'girar' : ''}"></span>${NOMES_MESES[mes]}</span>
                <span class="mes-stats">${consultadosMes}/${totalMes} consultados</span>
            </div>`;

            if (expandido) {
                html += `<div class="mes-content visivel">`;
                html += `<div class="container-pacientes">`;
                html += `<table class="tabela-pacientes"><thead><tr>`;
                html += `<th style="width:50px;">
                    <input type="checkbox" class="chk-paciente"
                    ${consultadosMes === totalMes ? 'checked' : ''}
                    onclick="event.stopPropagation(); toggleTodosMes(${JSON.stringify(pacientesMes.map(p => ({id:p.id})))}, this.checked)">
                </th>`;
                html += `<th>Prontuario</th><th>Nome</th><th>Entrada</th><th>Saida</th><th>CID</th><th>Medico</th><th>Permanencia</th><th>Status</th>`;
                html += `</tr></thead><tbody>`;

                pacientesMes.sort((a, b) => {
                    if (a.dia !== b.dia) return a.dia.localeCompare(b.dia);
                    return a.prontuario.localeCompare(b.prontuario);
                });

                pacientesMes.forEach(p => {
                    const consultado = p.consultado;
                    html += `<tr class="${consultado ? 'consultado' : ''}">`;
                    html += `<td><input type="checkbox" class="chk-paciente"
                        ${consultado ? 'checked' : ''}
                        onclick="event.stopPropagation(); toggleConsulta(${p.id})"></td>`;
                    html += `<td><strong>${p.prontuario}</strong></td>`;
                    html += `<td>${p.nome}</td>`;
                    html += `<td>${p.data_entrada}</td>`;
                    html += `<td>${p.data_saida || '-'}</td>`;
                    html += `<td><span class="cid-badge">${p.cid}</span></td>`;
                    html += `<td>${p.medico}</td>`;
                    html += `<td><span class="permanencia-badge">${p.dias_permanencia} dias</span></td>`;
                    html += `<td><span class="status-badge ${consultado ? 'status-consultado' : 'status-pendente'}">
                        ${consultado ? '[V] Consultado' : '[ ] Pendente'}</span></td>`;
                    html += '</tr>';
                });

                html += '</tbody></table></div></div>';
            }

            html += '</div>';
        });

        html += '</div>';
    });

    div.innerHTML = html;
}

// Atualizar dashboard
async function atualizarDashboard() {
    try {
        const res = await fetch(`${API_BASE}/api/estatisticas`);
        const stats = await res.json();

        const total = stats.total || 0;
        const consultados = stats.consultados || 0;
        const pendentes = total - consultados;
        const progresso = total > 0 ? Math.round((consultados / total) * 100) : 0;

        document.getElementById('total-geral').textContent = total;
        document.getElementById('total-consultado').textContent = consultados;
        document.getElementById('total-pendente').textContent = pendentes;
        document.getElementById('progresso-geral').textContent = progresso + '%';
        document.getElementById('barra-geral').style.width = progresso + '%';
    } catch (e) {
        console.error('Erro:', e);
    }
}

// Resetar consultas
window.resetarConsultas = async function() {
    if (!confirm('Tem certeza que deseja resetar TODAS as marcacoes?')) return;
    try {
        await fetch(`${API_BASE}/api/consultas/resetar`, { method: 'POST' });
        await carregarPacientes();
        atualizarDashboard();
    } catch (e) {
        alert('Erro ao resetar');
    }
};

// Exportar CSV
window.exportarCSV = function() {
    const filtrados = getPacientesFiltrados();
    if (filtrados.length === 0) {
        alert('Nenhum paciente para exportar');
        return;
    }

    const linhas = [['Ano','Mes','Dia','Prontuario','Nome','Entrada','Saida','CID','Medico','Permanencia','Status']];
    filtrados.forEach(p => {
        linhas.push([p.ano, p.mes, p.dia, p.prontuario, p.nome, p.data_entrada, p.data_saida || '', p.cid, p.medico, p.dias_permanencia, p.consultado ? 'Consultado' : 'Pendente']);
    });

    const csv = linhas.map(l => l.join(';')).join('\n');
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `controle_${categoriaAtual}_${new Date().toISOString().split('T')[0]}.csv`;
    a.click();
};
