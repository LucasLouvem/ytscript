# Arquitetura

Padrão **MVC**, **API first**, com a infraestrutura separada do código de produção.

```text
src/api/ytscript/       # código de produção (MVC)
├── cli.py                  # entrada do terminal; consome a API
├── api.py                  # entrada HTTP (FastAPI); consome a API e serve web/
├── models/                 # dados (Segment)
├── controllers/            # regras: validação de URL e orquestração (get_transcript)
└── views/                  # apresentação: formato [HH:MM:SS] texto
web/                        # página estática (HTML, CSS, JS puro), sem build
infra/                      # infraestrutura, na raiz, fora da API
├── errors.py               # erros customizados
└── youtube_client.py       # adaptador da youtube-transcript-api
```

`infra/` não depende do código de `src/api`: o adaptador devolve tuplas `(start, text)` e o controller monta os `Segment`.

## API first

A lógica vive em funções que não conhecem terminal nem HTTP (`controllers.transcript_controller.get_transcript(url) -> list[Segment]`). O CLI é só uma entrada que chama o controller, formata com a view e traduz erros para `stderr` e código de saída.

CLI e HTTP são duas entradas sobre o mesmo controller. Os erros trazem `status_code` e `to_dict()`, então o `api.py` só os converte em resposta HTTP, sem regra própria.

## HTTP e web (porta 3000)

Um único processo (FastAPI/uvicorn) serve a API em `/api/*` e a página estática de `web/` em `/`; mesma origem, sem CORS. A página é HTML/CSS/JS puro: React só será considerado se a interface crescer, e o contrato da API não muda nesse caso.

| Rota | Descrição |
|---|---|
| `GET /api/health` | `{"status": "ok"}` |
| `POST /api/transcripts` | corpo `{"url": "...", "language"?: "en", "translate_to"?: "en"}` (os dois opcionais; sem `language`, usa pt-BR/pt) |

Resposta `200`:

```json
{
  "video": {"id", "title", "channel", "duration_seconds", "view_count", "published_at", "thumbnail_url", "native_language"},
  "transcript": {"language_code", "is_generated", "translated_to"},
  "tracks": [{"language_code", "language", "is_generated", "translation_languages": [{"language_code", "language"}]}],
  "segments": [{"start", "end", "timestamp", "text"}],
  "text": "[HH:MM:SS] texto ...",
  "srt": "1\n00:00:12,000 --> 00:00:15,500\n...",
  "markdown": "# Título\n\n- **Canal:** ...\n\n## Transcrição\n\n**[00:00:12]** texto\n..."
}
```

- `video` vem de `infra/youtube_metadata.py` (página do vídeo, `ytInitialPlayerResponse`) e é **opcional**: se falhar, `video` é `null` e a transcrição segue.
- `native_language` é uma estimativa: código da faixa de áudio padrão (vídeos com dublagem) ou, na falta dela, o idioma da legenda automática (gerada a partir do áudio). Pode ser `null`.
- `markdown` traz o título, canal, duração, data, link e idioma da transcrição, seguidos dos trechos como `**[HH:MM:SS]** texto`; sem metadados do vídeo, vira só `# Transcrição` com os trechos. O texto dos trechos não é alterado nem escapado.
- `end` e o SRT usam `start + duration`, limitado ao início do segmento seguinte para não haver sobreposição.
- O CLI continua sem buscar metadados (usa `get_transcript`); a API usa `get_transcript_details`.

Erros: corpo `{name, message, action, status_code}` com o HTTP status do próprio erro (ver [errors.md](errors.md)). Corpo da requisição inválido (sem `url`, tipo errado) responde como `InvalidUrlError` (400). O endpoint é `def` (não `async`) porque a `youtube-transcript-api` é síncrona e bloquearia o event loop.

A página (`web/`) usa essas respostas: prévia, informações, listas de idioma e tradução (preenchidas com `tracks`), formato `.txt`/`.srt`/`.md` e timestamps (no cliente; só o `.txt` respeita o toggle, SRT e Markdown sempre levam timestamps), Copiar e Baixar.

Fora do escopo por enquanto: rate limit, proxy contra bloqueio de IP, CORS, autenticação, identificação de falantes (o YouTube não fornece).

## Fluxo

`cli.main` (ou `api.create_transcript`) → `get_transcript(url)` → `extract_video_id` (valida URL) → `infra.youtube_client.fetch_snippets` (escolhe legenda pt-BR/pt, manual antes de automática) → `views.format_transcript` → `stdout` (CLI) ou `views.build_transcript_payload` → JSON (API).

Dependências: `src/api` usa `infra`; `infra` não usa `src/api`; models não dependem de outras camadas.
