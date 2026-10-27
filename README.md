# YTScript

Transcrição com timestamps de vídeos do YouTube, a partir das legendas existentes. Funciona pelo terminal (CLI) e por uma página web servida por uma API HTTP, na porta 3000.

```text
[00:00:12] Antes de investir em uma empresa,
precisamos analisar seus fundamentos.

[00:00:19] O preço de uma ação não determina,
sozinho, se ela está barata ou cara.
```

## Requisitos

- Python 3.12+ (asdf: `asdf install`, versão em `.tool-versions`)
- Acesso à internet

## Instalação (tudo local, em `.venv`)

```bash
python -m venv .venv
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/pip install -e .
source .venv/bin/activate
```

## Uso

```bash
ytscript "https://www.youtube.com/watch?v=VIDEO_ID"
ytscript "https://youtu.be/VIDEO_ID" > transcricao.txt   # salvar em TXT
```

Transcrição no `stdout`; erros no `stderr`. Saída: `0` sucesso, `1` erro, `2` argumentos inválidos.

## Web e API (porta 3000)

```bash
uvicorn ytscript.api:app --port 3000
```

Abra http://localhost:3000, cole a URL e clique em **Transcrever**. A página mostra título, canal, duração e idioma do vídeo, e permite escolher idioma, formato (`.txt`/`.srt`/`.md`), timestamps, copiar e baixar. A API fica em `POST /api/transcripts` (`{"url": "...", "language"?, "translate_to"?}`) e `GET /api/health`. Detalhes em [architecture.md](docs/architecture.md).

## Desenvolvimento

```bash
black --check .
pytest
```

Documentação em [`docs/`](docs/): [arquitetura](docs/architecture.md), [commits](docs/commits.md), [código](docs/code-style.md), [testes](docs/testing.md), [erros](docs/errors.md).

## Limitações

- Sem idioma escolhido, usa só legendas em português; não transcreve áudio.
- A tradução usa a do próprio YouTube e pode ser bloqueada por ele (429), mesmo quando a legenda comum funciona.
- O "idioma detectado" é uma estimativa; o YouTube não informa o idioma falado diretamente.
- Legendas automáticas podem ter erros de reconhecimento; o texto é impresso como veio.
- O YouTube pode bloquear requisições (IPs de nuvem/VPN); a `youtube-transcript-api` usa endpoints não oficiais.
