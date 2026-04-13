# Controle de Neonatos

Sistema de controle de consultas de neonatos do Hospital e Maternidade Madalena Nunes.

## Funcionalidades

- Controle de consultas por categoria (CID-10)
- Interface hierárquica: Ano → Mês → Pacientes
- Marcar/desmarcar consultas individualmente ou em lote
- Filtros por nome, prontuário e status
- Exportação para CSV
- Dashboard com estatísticas em tempo real

## Categorias

- Pré-termo
- Desconforto Respiratório
- Septicemia
- Infecção Perinatal
- Outras Condições
- Malformações Congênitas
- Outras Doenças

## Instalação

1. Clone o repositório
2. Execute o servidor:

```bash
python server.py
```

3. Acesse: http://localhost:5789

## Tecnologias

- Backend: Python 3 (http.server + SQLite3)
- Frontend: HTML5, CSS3, JavaScript (Vanilla)
- Banco de dados: SQLite

## Estrutura

```
projeto-web/
├── server.py          # Servidor Python + API
├── public/
│   ├── index.html     # Página principal
│   ├── style.css      # Estilos
│   └── app.js         # JavaScript
└── database/          # SQLite (gerado automaticamente)
```

## API Endpoints

- GET /api/pacientes - Lista pacientes
- GET /api/categorias - Lista categorias com contadores
- GET /api/estatisticas - Estatísticas gerais
- POST /api/consultas/toggle - Marcar/desmarcar consulta
- POST /api/consultas/resetar - Resetar todas as consultas

## Licença

Uso interno - Hospital e Maternidade Madalena Nunes
