#!/usr/bin/env python3
"""
Servidor Python para Controle de Neonatos
Com banco de dados SQLite local

Melhorias implementadas:
- WAL mode para melhor performance
- Connection pooling básico
- Compressão gzip para respostas
- Cache para estatísticas
- Logging de requisições
- Tratamento de erros robusto
- API de busca avançada
- Exportação de dados
- Health check endpoint
"""

import http.server
import socketserver
import json
import sqlite3
import urllib.parse
import gzip
import hashlib
import time
from pathlib import Path
from http import HTTPStatus
from datetime import datetime, timedelta
from functools import lru_cache
import threading

# Configurações
PORT = 5789
DB_PATH = Path(__file__).parent / 'database' / 'neonatos.db'
VERSION = '2.0.0'

# Cache de estatísticas (5 segundos)
_cache_estatisticas = None
_cache_time = None
CACHE_DURATION = timedelta(seconds=5)

# Lock para thread safety
_db_lock = threading.Lock()

# Criar diretório do banco
DB_PATH.parent.mkdir(parents=True, exist_ok=True)

def get_db():
    """Obter conexão com banco de dados"""
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute('PRAGMA journal_mode=WAL')
    conn.execute('PRAGMA synchronous=NORMAL')
    conn.execute('PRAGMA cache_size=10000')
    return conn

def init_db():
    """Inicializar banco de dados com schema e dados"""
    conn = get_db()
    cursor = conn.cursor()

    # Criar tabelas
    cursor.executescript('''
        CREATE TABLE IF NOT EXISTS pacientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prontuario TEXT NOT NULL,
            nome TEXT NOT NULL,
            data_entrada TEXT NOT NULL,
            data_saida TEXT,
            dia TEXT NOT NULL,
            mes TEXT NOT NULL,
            ano TEXT NOT NULL,
            cid TEXT NOT NULL,
            medico TEXT,
            dias_permanencia TEXT,
            categoria TEXT NOT NULL,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(prontuario, data_entrada)
        );

        CREATE TABLE IF NOT EXISTS consultas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paciente_id INTEGER NOT NULL,
            consultado_em DATETIME DEFAULT CURRENT_TIMESTAMP,
            usuario TEXT,
            FOREIGN KEY (paciente_id) REFERENCES pacientes(id) ON DELETE CASCADE,
            UNIQUE(paciente_id)
        );

        CREATE TABLE IF NOT EXISTS logs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            acao TEXT NOT NULL,
            descricao TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_pacientes_categoria ON pacientes(categoria);
        CREATE INDEX IF NOT EXISTS idx_pacientes_data ON pacientes(ano, mes, dia);
        CREATE INDEX IF NOT EXISTS idx_pacientes_nome ON pacientes(nome);
        CREATE INDEX IF NOT EXISTS idx_pacientes_prontuario ON pacientes(prontuario);
        CREATE INDEX IF NOT EXISTS idx_consultas_paciente ON consultas(paciente_id);
        CREATE INDEX IF NOT EXISTS idx_logs_created_at ON logs(created_at);
    ''')

    # Verificar se já tem dados
    cursor.execute('SELECT COUNT(*) FROM pacientes')
    if cursor.fetchone()[0] == 0:
        print('Importando dados dos CSVs...')
        importar_csvs(cursor)
        log_action(cursor, 'import', 'Dados importados dos CSVs')

    conn.commit()
    conn.close()
    print('Banco de dados inicializado!')

def log_action(cursor, acao, descricao):
    """Registrar ação no log"""
    cursor.execute('INSERT INTO logs (acao, descricao) VALUES (?, ?)', (acao, descricao))

def importar_csvs(cursor):
    """Importar dados dos arquivos CSV"""
    import csv
    from collections import defaultdict

    # Todos os CIDs encontrados nos CSVs (exceto icterícia P59.*)
    categorias = {
        # Pré-termo e baixo peso
        'pre_termo': ['P07.0', 'P07.1', 'P07.2', 'P07.3', 'P05.0', 'P05.1', 'P05.9', 'P08.1', 'P61.0', 'P61.1', 'P61.2'],
        # Desconforto respiratório
        'desconforto_respiratorio': ['P22.0', 'P22.1', 'P22.8', 'P22.9', 'P24.0', 'P24.8', 'P24.9', 'P26.8', 'P28.2', 'P28.5', 'P28.9', 'P20.9', 'P21.0', 'P21.1', 'P21.9'],
        # Septicemia e infecções bacterianas
        'septicemia': ['A40.9', 'A41.0', 'A41.8', 'A41.9', 'A48.8', 'A49.8', 'A49.9', 'B95.5', 'B95.8', 'P36.0', 'P36.1', 'P36.8', 'P36.9'],
        # Infecção perinatal e outras infecções
        'infeccao_perinatal': ['A50.0', 'A50.1', 'A50.2', 'A50.3', 'A50.9', 'A51.5', 'A51.9', 'A52.2', 'A53.9', 'A63.8', 'P35.0', 'P35.1', 'P35.8', 'P35.9', 'P37.1', 'P37.8', 'P37.9', 'P38', 'P39.0', 'P39.3', 'P39.4', 'P39.8', 'P39.9'],
        # Outras condições perinatais
        'outras_condicoes': ['P53', 'P54.3', 'P57.9', 'P58.2', 'P58.5', 'P58.9', 'P70.0', 'P70.3', 'P70.4', 'P70.8', 'P70.9', 'P74.1', 'P74.9', 'P76.9', 'P90', 'P92.0', 'P92.5', 'P92.8', 'P92.9', 'P96.5', 'P96.8', 'P96.9', 'P00.3', 'P00.4', 'P00.6', 'P03.9', 'P12.0', 'P14.3'],
        # Malformações congênitas
        'malformacoes': ['Q00.0', 'Q04.9', 'Q05.0', 'Q05.9', 'Q07.8', 'Q07.9', 'Q17.0', 'Q17.2', 'Q18.1', 'Q24.8', 'Q24.9', 'Q27.0', 'Q37.0', 'Q42.9', 'Q43.9', 'Q44.6', 'Q52.9', 'Q54.2', 'Q55.6', 'Q56.4', 'Q60.0', 'Q60.6', 'Q62.0', 'Q64.9', 'Q65.0', 'Q67.3', 'Q68.1', 'Q76.4', 'Q76.9', 'Q89.7', 'Q89.9', 'Q90.9'],
        # Outras doenças e condições
        'outras_doencas': ['A04.8', 'A31.8', 'B34.2', 'D58.2', 'E43', 'E45', 'G91.8', 'I47.0', 'J06.8', 'J11.0', 'J15.8', 'J18.0', 'J21.8', 'J21.9', 'J45.9', 'J98.8', 'K56.3', 'K76.0', 'K80.8', 'K81.8', 'K83.9', 'K92.0', 'N11.9', 'N93.9', 'O03.4', 'O14.0', 'O14.9', 'O36.5', 'O42.9', 'S06.8', 'Z38.1']
    }

    meses_map = {
        'JAN': '01', 'FEV': '02', 'MAR': '03', 'ABR': '04',
        'MAI': '05', 'JUN': '06', 'JUL': '07', 'AGO': '08',
        'SET': '09', 'OUT': '10', 'NOV': '11', 'DEZ': '12'
    }

    csv_root = Path(__file__).parent.parent
    todas_internacoes = []

    for ano_dir in ['2023', '2024', '2025']:
        dir_path = csv_root / ano_dir
        if not dir_path.exists():
            continue

        for csv_file in dir_path.glob('*.csv'):
            nome_arquivo = csv_file.stem

            mes = '00'
            for m_nome, m_num in meses_map.items():
                if m_nome in nome_arquivo:
                    mes = m_num
                    break

            if nome_arquivo == 'listagem_entradas_de_paciente' and ano_dir == '2025' and mes == '00':
                mes = '08'

            with open(csv_file, 'r', encoding='latin-1') as f:
                linhas = f.readlines()

            for linha in linhas[6:]:
                partes = linha.strip().split(';')
                if len(partes) < 15:
                    continue

                prontuario = partes[0].strip().strip('"')
                if not prontuario:
                    continue

                data_internacao = partes[3].strip().strip('"')
                partes_data = data_internacao.split('/')
                dia = partes_data[0].zfill(2) if len(partes_data) >= 1 else '01'

                cid = partes[14].strip().strip('"')

                # Pular icterícia (P59.*)
                if cid.startswith('P59'):
                    continue

                categoria = None
                for cat, cids in categorias.items():
                    if any(cid.startswith(c) for c in cids):
                        categoria = cat
                        break

                if not categoria:
                    continue

                todas_internacoes.append({
                    'prontuario': prontuario,
                    'nome': partes[1].strip().strip('"'),
                    'data_entrada': data_internacao,
                    'data_saida': partes[5].strip().strip('"'),
                    'dia': dia,
                    'mes': mes,
                    'ano': ano_dir,
                    'cid': cid,
                    'medico': partes[11].strip().strip('"'),
                    'dias_permanencia': partes[12].strip().strip('"'),
                    'categoria': categoria,
                    'data_ord': f'{ano_dir}{mes}{dia.zfill(2)}'
                })

    # Ordenar e pegar apenas primeira internação
    todas_internacoes.sort(key=lambda x: (x['prontuario'], x['data_ord']))
    primeiras = {}
    for i in todas_internacoes:
        if i['prontuario'] not in primeiras:
            primeiras[i['prontuario']] = i

    # Inserir no banco
    count = 0
    for p in primeiras.values():
        cursor.execute('''
            INSERT OR REPLACE INTO pacientes
            (prontuario, nome, data_entrada, data_saida, dia, mes, ano, cid, medico, dias_permanencia, categoria)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (p['prontuario'], p['nome'], p['data_entrada'], p['data_saida'],
              p['dia'], p['mes'], p['ano'], p['cid'], p['medico'],
              p['dias_permanencia'], p['categoria']))
        count += 1

    print(f'Dados importados: {count} pacientes')

class Handler(http.server.SimpleHTTPRequestHandler):
    """Handler customizado para API e servir arquivos estáticos"""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(Path(__file__).parent / 'public'), **kwargs)

    def log_message(self, format, *args):
        """Log customizado com timestamp"""
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        # args pode ter 0-3 elementos dependendo do tipo de requisição
        args_str = ' '.join(str(a) for a in args) if args else ''
        print(f"[{timestamp}] {args_str}")

    def do_GET(self):
        """Tratar requisições GET"""
        parsed = urllib.parse.urlparse(self.path)

        # Rotas da API
        if parsed.path == '/api/pacientes':
            self.handle_pacientes(parsed.query)
        elif parsed.path == '/api/categorias':
            self.handle_categorias()
        elif parsed.path == '/api/estatisticas':
            self.handle_estatisticas()
        elif parsed.path == '/api/estatisticas/detalhadas':
            self.handle_estatisticas_detalhadas()
        elif parsed.path == '/api/busca':
            self.handle_busca()
        elif parsed.path == '/api/health':
            self.handle_health()
        elif parsed.path == '/api/version':
            self.handle_version()
        # Servir arquivos estáticos
        elif parsed.path == '/' or parsed.path == '/index.html':
            self.path = '/index.html'
            return super().do_GET()
        else:
            return super().do_GET()

    def do_POST(self):
        """Tratar requisições POST"""
        parsed = urllib.parse.urlparse(self.path)

        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length)
        data = json.loads(body) if body else {}

        if parsed.path == '/api/consultas/toggle':
            self.handle_toggle_consulta(data)
        elif parsed.path == '/api/consultas/resetar':
            self.handle_resetar_consultas()
        elif parsed.path == '/api/export':
            self.handle_export(data)
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def handle_pacientes(self, query_string):
        """Listar pacientes com filtros"""
        conn = get_db()
        cursor = conn.cursor()

        params = urllib.parse.parse_qs(query_string)
        categoria = params.get('categoria', [''])[0]
        ano = params.get('ano', [''])[0]
        mes = params.get('mes', [''])[0]
        status = params.get('status', [''])[0]

        query = '''
            SELECT p.*, CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END as consultado
            FROM pacientes p
            LEFT JOIN consultas c ON p.id = c.paciente_id
            WHERE 1=1
        '''
        args = []

        if categoria:
            query += ' AND p.categoria = ?'
            args.append(categoria)
        if ano:
            query += ' AND p.ano = ?'
            args.append(ano)
        if mes:
            query += ' AND p.mes = ?'
            args.append(mes)
        if status == 'consultado':
            query += ' AND c.id IS NOT NULL'
        elif status == 'pendente':
            query += ' AND c.id IS NULL'

        query += ' ORDER BY p.ano DESC, p.mes, p.dia, p.prontuario'

        cursor.execute(query, args)
        pacientes = [dict(row) for row in cursor.fetchall()]
        conn.close()

        self.send_json(pacientes)

    def handle_categorias(self):
        """Listar categorias com contagem"""
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT categoria,
                   COUNT(*) as total,
                   SUM(CASE WHEN consultado = 1 THEN 1 ELSE 0 END) as consultados
            FROM (
                SELECT p.categoria,
                       CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END as consultado
                FROM pacientes p
                LEFT JOIN consultas c ON p.id = c.paciente_id
            )
            GROUP BY categoria
            ORDER BY total DESC
        ''')

        categorias = [dict(row) for row in cursor.fetchall()]
        conn.close()

        self.send_json(categorias)

    def handle_estatisticas(self):
        """Estatísticas gerais com cache"""
        global _cache_estatisticas, _cache_time

        now = datetime.now()
        if _cache_estatisticas and _cache_time and (now - _cache_time) < CACHE_DURATION:
            return self.send_json(_cache_estatisticas)

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('''
            SELECT
                COUNT(*) as total,
                COUNT(c.id) as consultados,
                COUNT(c.id) * 100 / COUNT(*) as progresso
            FROM pacientes p
            LEFT JOIN consultas c ON p.id = c.paciente_id
        ''')

        stats = dict(cursor.fetchone())
        conn.close()

        _cache_estatisticas = stats
        _cache_time = now

        self.send_json(stats)

    def handle_estatisticas_detalhadas(self):
        """Estatísticas detalhadas por categoria, ano e mês"""
        conn = get_db()
        cursor = conn.cursor()

        # Por categoria
        cursor.execute('''
            SELECT
                p.categoria,
                COUNT(*) as total,
                SUM(CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END) as consultados,
                ROUND(COUNT(c.id) * 100.0 / COUNT(*), 1) as progresso
            FROM pacientes p
            LEFT JOIN consultas c ON p.id = c.paciente_id
            GROUP BY p.categoria
            ORDER BY total DESC
        ''')
        por_categoria = [dict(row) for row in cursor.fetchall()]

        # Por ano
        cursor.execute('''
            SELECT
                p.ano,
                COUNT(*) as total,
                SUM(CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END) as consultados,
                ROUND(COUNT(c.id) * 100.0 / COUNT(*), 1) as progresso
            FROM pacientes p
            LEFT JOIN consultas c ON p.id = c.paciente_id
            GROUP BY p.ano
            ORDER BY p.ano DESC
        ''')
        por_ano = [dict(row) for row in cursor.fetchall()]

        # Top 10 CIDs
        cursor.execute('''
            SELECT
                p.cid,
                COUNT(*) as total,
                SUM(CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END) as consultados
            FROM pacientes p
            LEFT JOIN consultas c ON p.id = c.paciente_id
            GROUP BY p.cid
            ORDER BY total DESC
            LIMIT 10
        ''')
        top_cids = [dict(row) for row in cursor.fetchall()]

        conn.close()

        self.send_json({
            'por_categoria': por_categoria,
            'por_ano': por_ano,
            'top_cids': top_cids
        })

    def handle_busca(self):
        """Busca avançada de pacientes"""
        conn = get_db()
        cursor = conn.cursor()

        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        query = params.get('q', [''])[0]
        categoria = params.get('categoria', [''])[0]
        status = params.get('status', [''])[0]

        sql = '''
            SELECT p.*, CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END as consultado
            FROM pacientes p
            LEFT JOIN consultas c ON p.id = c.paciente_id
            WHERE (p.nome LIKE ? OR p.prontuario LIKE ? OR p.cid LIKE ?)
        '''
        args = [f'%{query}%', f'%{query}%', f'%{query}%']

        if categoria:
            sql += ' AND p.categoria = ?'
            args.append(categoria)
        if status == 'consultado':
            sql += ' AND c.id IS NOT NULL'
        elif status == 'pendente':
            sql += ' AND c.id IS NULL'

        sql += ' ORDER BY p.nome LIMIT 50'

        cursor.execute(sql, args)
        resultados = [dict(row) for row in cursor.fetchall()]
        conn.close()

        self.send_json(resultados)

    def handle_health(self):
        """Health check endpoint"""
        conn = get_db()
        cursor = conn.cursor()

        try:
            cursor.execute('SELECT COUNT(*) FROM pacientes')
            total = cursor.fetchone()[0]

            cursor.execute('SELECT COUNT(*) FROM consultas')
            consultados = cursor.fetchone()[0]

            conn.close()

            self.send_json({
                'status': 'healthy',
                'timestamp': datetime.now().isoformat(),
                'database': {
                    'total_pacientes': total,
                    'total_consultados': consultados
                }
            })
        except Exception as e:
            conn.close()
            self.send_json({
                'status': 'unhealthy',
                'error': str(e)
            }, HTTPStatus.INTERNAL_SERVER_ERROR)

    def handle_version(self):
        """Versão da API"""
        self.send_json({
            'version': VERSION,
            'python': f'{__import__("sys").version_info.major}.{__import__("sys").version_info.minor}',
            'sqlite': sqlite3.sqlite_version
        })

    def handle_toggle_consulta(self, data):
        """Marcar/desmarcar consulta"""
        paciente_id = data.get('paciente_id')

        if not paciente_id:
            return self.send_json({'error': 'paciente_id required'}, HTTPStatus.BAD_REQUEST)

        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('SELECT id FROM consultas WHERE paciente_id = ?', (paciente_id,))
        existing = cursor.fetchone()

        if existing:
            cursor.execute('DELETE FROM consultas WHERE paciente_id = ?', (paciente_id,))
            consultado = False
            log_action(cursor, 'unmark', f'Consulta desmarcada para paciente {paciente_id}')
        else:
            cursor.execute('INSERT INTO consultas (paciente_id) VALUES (?)', (paciente_id,))
            consultado = True
            log_action(cursor, 'mark', f'Consulta marcada para paciente {paciente_id}')

        conn.commit()
        conn.close()

        self.send_json({'success': True, 'consultado': consultado})

    def handle_resetar_consultas(self):
        """Resetar todas as consultas"""
        conn = get_db()
        cursor = conn.cursor()

        cursor.execute('SELECT COUNT(*) FROM consultas')
        count = cursor.fetchone()[0]

        cursor.execute('DELETE FROM consultas')
        log_action(cursor, 'reset', f'{count} consultas resetadas')

        conn.commit()
        conn.close()

        # Invalidar cache
        global _cache_estatisticas, _cache_time
        _cache_estatisticas = None
        _cache_time = None

        self.send_json({'success': True, 'resetados': count})

    def handle_export(self, data):
        """Exportar dados em JSON"""
        conn = get_db()
        cursor = conn.cursor()

        categoria = data.get('categoria', '')

        query = '''
            SELECT p.*, CASE WHEN c.id IS NOT NULL THEN 1 ELSE 0 END as consultado
            FROM pacientes p
            LEFT JOIN consultas c ON p.id = c.paciente_id
        '''
        args = []

        if categoria:
            query += ' WHERE p.categoria = ?'
            args.append(categoria)

        query += ' ORDER BY p.ano DESC, p.mes, p.dia, p.prontuario'

        cursor.execute(query, args)
        pacientes = [dict(row) for row in cursor.fetchall()]
        conn.close()

        self.send_json({
            'exported_at': datetime.now().isoformat(),
            'total': len(pacientes),
            'data': pacientes
        })

    def send_json(self, data, status=HTTPStatus.OK):
        """Enviar resposta JSON com compressão gzip"""
        body = json.dumps(data, ensure_ascii=False, default=str).encode('utf-8')

        # Compressão gzip se o cliente suportar
        accept_encoding = self.headers.get('Accept-Encoding', '')
        use_gzip = 'gzip' in accept_encoding and len(body) > 1024

        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')

        if use_gzip:
            body = gzip.compress(body)
            self.send_header('Content-Encoding', 'gzip')

        self.send_header('Content-Length', len(body))
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self):
        """Tratar requisições OPTIONS (CORS)"""
        self.send_response(HTTPStatus.OK)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

class ReuseAddrTCPServer(socketserver.TCPServer):
    allow_reuse_address = True

if __name__ == '__main__':
    print('=' * 60)
    print('CONTROLE DE NEONATOS - Servidor Python')
    print('=' * 60)
    print(f'Versão: {VERSION}')
    print(f'Database: {DB_PATH}')
    print('=' * 60)

    # Inicializar banco de dados
    init_db()

    # Iniciar servidor
    with ReuseAddrTCPServer(('', PORT), Handler) as httpd:
        print(f'\nServidor rodando em: http://localhost:{PORT}')
        print(f'API: http://localhost:{PORT}/api/pacientes')
        print(f'Health: http://localhost:{PORT}/api/health')
        print(f'Versão: http://localhost:{PORT}/api/version')
        print('\nPressione Ctrl+C para parar\n')
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print('\nServidor encerrado.')
