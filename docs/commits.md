# Padrão de commits

Seguimos [Conventional Commits](https://www.conventionalcommits.org/), **apenas com título**. A descrição da mudança fica no Pull Request, não no commit.

```text
<tipo>(<escopo opcional>): <título no imperativo, minúsculo, sem ponto final>
```

## Tipos

| Tipo | Uso |
|---|---|
| `feat` | nova funcionalidade |
| `fix` | correção de bug |
| `refactor` | mudança de estrutura sem alterar comportamento |
| `test` | criação/ajuste de testes |
| `docs` | documentação |
| `style` | formatação (black), sem mudança de lógica |
| `chore` | dependências, configuração, tooling |

## Regras

- Um commit = uma mudança lógica; o código e seus testes entram juntos.
- Título curto (ideal até 72 caracteres), em português, no imperativo.
- Sem corpo de mensagem.
- Mudança que quebra compatibilidade: `feat!: ...` ou `refactor!: ...`.

## Exemplos

```text
feat: adiciona suporte a URLs de shorts
fix(cli): envia mensagens de erro para o stderr
refactor: move validação de URL para o controller
test: cobre fallback para legenda automática
docs: documenta padrão de erros customizados
chore: atualiza youtube-transcript-api
```
