# Erros customizados

Definidos em `infra/errors.py`. Todo erro esperado herda de `YTScriptError` e declara:

| Atributo | Descrição |
|---|---|
| `name` | nome do erro (igual ao nome da classe) |
| `message` | explicação do que aconteceu |
| `action` | como o usuário resolve |
| `status_code` | código HTTP equivalente (usado pela API HTTP; o CLI sempre sai com 1) |

O corpo é **fixo por classe**: nenhum código monta texto de erro avulso; para cada situação existe um erro com seu `message` e `action`. A causa técnica fica encadeada (`raise ... from error`). `to_dict()` devolve os quatro campos para serializar em JSON. O CLI imprime no `stderr`: `ytscript: erro: <message> <action>`.

## Catálogo

| name | status_code | Quando |
|---|---|---|
| `InvalidUrlError` | 400 | URL malformada ou sem https |
| `UnsupportedDomainError` | 400 | domínio diferente de youtube.com / m.youtube.com / youtu.be |
| `InvalidVideoIdError` | 400 | URL sem ID de vídeo válido |
| `TranscriptsDisabledError` | 404 | legendas desativadas no vídeo |
| `TranscriptNotFoundError` | 404 | sem legenda em português (idioma automático) |
| `LanguageNotAvailableError` | 404 | idioma pedido não existe entre as legendas do vídeo |
| `TranslationNotAvailableError` | 400 | tradução para o idioma pedido não é oferecida pelo YouTube para esta legenda |
| `VideoUnavailableError` | 404 | vídeo indisponível, privado ou com restrição de idade |
| `EmptyTranscriptError` | 404 | transcrição sem texto |
| `AccessBlockedError` | 429 | YouTube bloqueou/limitou o acesso |
| `NetworkError` | 502 | falha de rede |
| `TranscriptRetrievalError` | 502 | falha genérica ao obter a transcrição |
| `VideoMetadataError` | 502 | falha ao obter título, duração etc.; a API trata internamente e devolve `video: null` |

## Como adicionar um erro

1. Crie a subclasse em `infra/errors.py` com `name`, `message`, `action` e `status_code`.
2. Lance-a no ponto correto (exceções de bibliotecas externas são convertidas em `infra/`).
3. Adicione o corpo exato (name, message, action, status_code) em `EXPECTED_BODIES` de `tests/infra/test_errors.py`.
4. Teste o caminho que a lança importando a classe e comparando `to_dict()` com o corpo esperado (ver [testing.md](testing.md)).
5. Atualize a tabela acima.
