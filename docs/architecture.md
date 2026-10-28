# Arquitetura

Padrão **MVC**, **API first**, com a infraestrutura separada do código de produção.

```text
src/api/ytscript/       # código de produção (MVC)
├── cli.py                  # entrada do terminal; consome a API
├── api.py                  # entrada HTTP (FastAPI); consome a API e serve public/ (só fora da Vercel)
├── models/                 # dados (Segment)
├── controllers/            # regras: validação de URL e orquestração (get_transcript)
└── views/                  # apresentação: formato [HH:MM:SS] texto
public/                     # página estática (HTML, CSS, JS puro), sem build
app.py                      # entrypoint da Vercel (reexporta ytscript.api:app)
infra/                      # infraestrutura, na raiz, fora da API
├── errors.py               # erros customizados
├── youtube_client.py       # adaptador da youtube-transcript-api
└── redis_rate_limiter.py   # rate limit no Redis da Upstash (REST)
```

`infra/` não depende do código de `src/api`: o adaptador devolve tuplas `(start, text)` e o controller monta os `Segment`.

## API first

A lógica vive em funções que não conhecem terminal nem HTTP (`controllers.transcript_controller.get_transcript(url) -> list[Segment]`). O CLI é só uma entrada que chama o controller, formata com a view e traduz erros para `stderr` e código de saída.

CLI e HTTP são duas entradas sobre o mesmo controller. Os erros trazem `status_code` e `to_dict()`, então o `api.py` só os converte em resposta HTTP, sem regra própria.

## HTTP e web (porta 3000)

Um único processo (FastAPI/uvicorn) serve a API em `/api/*` e a página estática de `public/` em `/`; mesma origem, sem CORS. A página é HTML/CSS/JS puro: React só será considerado se a interface crescer, e o contrato da API não muda nesse caso.

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

Rate limit: `POST /api/transcripts` tem três limites, todos em janela deslizante (`ytscript/rate_limiter.py`; o limitador em memória é seguro entre threads): 10 requisições por 60 s (`RateLimitExceededError`) e 100 por 24 h (`DailyLimitExceededError`), ambos por IP do cliente, mais um teto global de 2000 por 24 h somando todos os IPs (`GlobalLimitExceededError`). Acima disso responde `429` com o cabeçalho `Retry-After` (segundos). Requisição bloqueada não conta em nenhum dos limites; o global é verificado primeiro. Configurável por `YTSCRIPT_RATE_LIMIT`, `YTSCRIPT_RATE_WINDOW` `YTSCRIPT_DAILY_LIMIT` e `YTSCRIPT_GLOBAL_DAILY_LIMIT`. O CLI e `/api/health` não são limitados.

Onde ficam os contadores: com `UPSTASH_REDIS_REST_URL` e `UPSTASH_REDIS_REST_TOKEN` definidos (ou `KV_REST_API_URL` e `KV_REST_API_TOKEN`, nomes que a Vercel pode criar), no Redis da Upstash via API REST (`infra/redis_rate_limiter.py`): um script Lua verifica os três limites e registra o acesso de forma atômica, em sorted sets que expiram sozinhos (sem cron de limpeza). Sem essas variáveis, em memória por processo (desenvolvimento local; não serve na Vercel, onde cada requisição pode cair em outra instância). Se o Redis estiver fora do ar ou lento (timeout de 2 s), a requisição é liberada e o erro vai para o log (fail open).

Chave de API (automações): o cabeçalho `X-API-Key` troca o limite público por limites próprios, mais apertados que o abuso tolera: 30 por minuto e 1000 por dia por chave, e 5000 por dia somando todas as chaves (`YTSCRIPT_KEY_RATE_LIMIT`, `YTSCRIPT_KEY_DAILY_LIMIT`, `YTSCRIPT_KEY_GLOBAL_DAILY_LIMIT`; a janela do minuto é a mesma `YTSCRIPT_RATE_WINDOW`). Tráfego com chave não consome a cota pública, e vice-versa. As chaves vêm de `YTSCRIPT_API_KEYS` (separadas por vírgula; revogar é tirar da lista e fazer novo deploy), ficam só como SHA-256 em memória, são comparadas em tempo constante e o limitador guarda apenas um id derivado do hash, nunca a chave. Chaves com menos de 32 caracteres são ignoradas (e registradas no log). Chave desconhecida responde `401` (`InvalidApiKeyError`) sem cair no limite público, e a tentativa conta no limite por IP, o que barra tentativa e erro. Sem o cabeçalho, vale o limite público. Contadores no Redis usam namespaces próprios (`key-global`, `key-daily`, `key-minute`).

Erros: corpo `{name, message, action, status_code}` com o HTTP status do próprio erro (ver [errors.md](errors.md)). Corpo da requisição inválido (sem `url`, tipo errado) responde como `InvalidUrlError` (400). O endpoint é `def` (não `async`) porque a `youtube-transcript-api` é síncrona e bloquearia o event loop.

A página (`public/`) usa essas respostas: prévia, informações, listas de idioma e tradução (preenchidas com `tracks`), formato `.txt`/`.srt`/`.md` e timestamps (no cliente; só o `.txt` respeita o toggle, SRT e Markdown sempre levam timestamps), Copiar e Baixar.

Fora do escopo por enquanto: rate limit compartilhado entre processos/instâncias e atrás de proxy reverso (fora da Vercel o IP vem de `request.client`; na Vercel, do primeiro valor de `X-Forwarded-For`, que ela sobrescreve e não repassa de fora), proxy contra bloqueio de IP, CORS, autenticação, identificação de falantes (o YouTube não fornece).

## Fluxo

`cli.main` (ou `api.create_transcript`) → `get_transcript(url)` → `extract_video_id` (valida URL) → `infra.youtube_client.fetch_snippets` (escolhe legenda pt-BR/pt, manual antes de automática) → `views.format_transcript` → `stdout` (CLI) ou `views.build_transcript_payload` → JSON (API).

Dependências: `src/api` usa `infra`; `infra` não usa `src/api`; models não dependem de outras camadas.
