# Padrão de testes

- Framework: **pytest** (`pytest`).
- **Testes acompanham o projeto**: toda mudança de código entra com seus testes, no mesmo commit.
- **Estrutura espelhada**: cada arquivo em `src/api/...` tem seu teste no mesmo caminho em `tests/api/...`; `infra/` (raiz) espelha em `tests/infra/`, com prefixo `test_`.

```text
src/api/ytscript/cli.py                        -> tests/api/ytscript/test_cli.py
src/api/ytscript/controllers/transcript_controller.py
                                                   -> tests/api/ytscript/controllers/test_transcript_controller.py
infra/errors.py                                    -> tests/infra/test_errors.py
```

- **Erros esperados com corpo exato**: o teste importa a classe de `infra/errors.py` e verifica `pytest.raises(Classe)` + `exc.value.to_dict() == Classe().to_dict()`; no CLI, o `stderr` deve ser exatamente `ytscript: erro: <message> <action>`. O texto literal de cada erro fica travado em `tests/infra/test_errors.py`.
- **Casos de sucesso e de erro**: cada função cobre o caminho feliz e as falhas esperadas (entradas inválidas, erros customizados, códigos de saída).
- Testes unitários **não acessam a rede**: o YouTube é mockado em `infra.youtube_client.YouTubeTranscriptApi`.
- `tests/fixtures/player_response_<id>.json` guarda respostas reais (reduzidas) da página de dois vídeos públicos; os testes de metadados usam essas fixtures, sem rede. Contadores como `viewCount` mudam no YouTube; a fixture é um retrato fixo.
- O Redis da Upstash é mockado em `urllib.request.urlopen` (`tests/infra/test_redis_rate_limiter.py`); o script Lua só é exercitado de verdade em verificação manual contra um Redis real.
- A API é testada com `TestClient` (FastAPI) e mock do YouTube; erros HTTP comparam status e corpo exatos com `Classe().to_dict()`.
- Verificação de integração real com o YouTube é manual e nunca bloqueia a suíte.
- Nomes de testes descrevem o comportamento (`test_prefers_manual_portuguese`).
