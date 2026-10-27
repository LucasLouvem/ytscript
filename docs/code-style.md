# Padrão de código

## Formatação

- Formatador: **black** (`line-length = 100`, configurado em `pyproject.toml`).
- Formatar: `black .`
- Verificar (usado antes de commitar/CI): `black --check .`

## Verificação antes de commitar

```bash
black --check .
pytest
```

## Convenções

- Python 3.12+, type hints em todas as funções públicas.
- Nomes descritivos; sem comentários que apenas repetem o código.
- Sem `except Exception` genérico: capture apenas exceções esperadas e converta para erros customizados (ver [errors.md](errors.md)).
- Código de produção não importa `youtube_transcript_api` diretamente; apenas `infra/youtube_client.py`.
- Sem `eval`, `shell=True` ou requisições para URLs fornecidas pelo usuário (só o ID validado do vídeo é usado).
- Dependências fixadas em `requirements.txt` / `requirements-dev.txt`.
