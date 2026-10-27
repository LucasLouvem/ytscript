# YTScript

Transcrição com timestamps de vídeos do YouTube, via CLI e via API HTTP + página web (porta 3000). Sem idioma escolhido, usa legendas em português.

## Comandos

```bash
source .venv/bin/activate          # ambiente local (python do asdf via .tool-versions)
pip install -r requirements-dev.txt && pip install -e .
pytest                             # testes
black . / black --check .          # formatar / verificar
ytscript "<url>"                      # executar CLI
uvicorn ytscript.api:app --port 3000   # API em /api/* e página web em /
```

Nada é instalado globalmente; dependências ficam em `requirements*.txt`.

## Estrutura

MVC sob `src/api/ytscript/` (`models/`, `controllers/`, `views/`; entradas `cli.py` e `api.py`). `web/` é a página estática (HTML/CSS/JS puro, sem build), servida pelo FastAPI. `infra/` fica na **raiz**, fora da API (erros customizados, adaptador do YouTube) e não importa `src/api`. Testes espelham o caminho: `tests/api/ytscript/` e `tests/infra/`. API first: lógica sem dependência de terminal/HTTP.

## Regras (detalhes em `docs/`)

- Commits: Conventional Commits, **só título**, sem corpo; descrição fica no PR (`docs/commits.md`).
- Código: black (line-length 100), type hints, sem `except Exception` (`docs/code-style.md`).
- Testes: acompanham toda mudança, espelhados, sucesso e erro, sem rede (`docs/testing.md`).
- Erros: subclasses de `YTScriptError` com `name`, `message`, `action`, `status_code` (`docs/errors.md`).
- Só `infra/youtube_client.py` importa `youtube_transcript_api`.
- Arquitetura, API HTTP e página web: `docs/architecture.md`.
