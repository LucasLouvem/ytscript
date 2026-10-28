import pytest

from infra import errors
from infra.errors import YTScriptError

EXPECTED_BODIES = {
    errors.InvalidUrlError: {
        "name": "InvalidUrlError",
        "message": "A URL informada é inválida.",
        "action": "Use um link https, como https://www.youtube.com/watch?v=ID, https://youtu.be/ID ou https://www.youtube.com/shorts/ID.",
        "status_code": 400,
    },
    errors.UnsupportedDomainError: {
        "name": "UnsupportedDomainError",
        "message": "O domínio da URL não é suportado.",
        "action": "Use um link de youtube.com, m.youtube.com ou youtu.be.",
        "status_code": 400,
    },
    errors.InvalidVideoIdError: {
        "name": "InvalidVideoIdError",
        "message": "Não foi possível encontrar um ID de vídeo válido na URL.",
        "action": "Confira se o link contém o ID do vídeo (11 caracteres), como em watch?v=ID.",
        "status_code": 400,
    },
    errors.TranscriptsDisabledError: {
        "name": "TranscriptsDisabledError",
        "message": "As legendas estão desativadas para este vídeo.",
        "action": "Use um vídeo que tenha legendas habilitadas.",
        "status_code": 404,
    },
    errors.TranscriptNotFoundError: {
        "name": "TranscriptNotFoundError",
        "message": "Não há transcrição acessível em português para este vídeo.",
        "action": "Use um vídeo com legenda manual ou automática em português.",
        "status_code": 404,
    },
    errors.VideoUnavailableError: {
        "name": "VideoUnavailableError",
        "message": "O vídeo está indisponível ou com acesso restrito.",
        "action": "Confirme que o vídeo é público e que a URL está correta.",
        "status_code": 404,
    },
    errors.EmptyTranscriptError: {
        "name": "EmptyTranscriptError",
        "message": "A transcrição do vídeo está vazia.",
        "action": "Use um vídeo que tenha fala legendada.",
        "status_code": 404,
    },
    errors.RateLimitExceededError: {
        "name": "RateLimitExceededError",
        "message": "Você fez transcrições demais em pouco tempo.",
        "action": "Aguarde um pouco e tente novamente.",
        "status_code": 429,
    },
    errors.DailyLimitExceededError: {
        "name": "DailyLimitExceededError",
        "message": "Você atingiu o limite diário de transcrições.",
        "action": "Tente novamente amanhã.",
        "status_code": 429,
    },
    errors.GlobalLimitExceededError: {
        "name": "GlobalLimitExceededError",
        "message": "O serviço atingiu o limite diário de transcrições de todos os usuários.",
        "action": "Tente novamente mais tarde.",
        "status_code": 429,
    },
    errors.InvalidApiKeyError: {
        "name": "InvalidApiKeyError",
        "message": "A chave de API é inválida.",
        "action": "Confira o valor do cabeçalho X-API-Key ou remova-o para usar o limite público.",
        "status_code": 401,
    },
    errors.AccessBlockedError: {
        "name": "AccessBlockedError",
        "message": "O YouTube bloqueou ou limitou o acesso.",
        "action": "Aguarde alguns minutos ou tente de outra rede (IPs de nuvem e VPN são mais afetados).",
        "status_code": 429,
    },
    errors.NetworkError: {
        "name": "NetworkError",
        "message": "Falha de rede ao acessar o YouTube.",
        "action": "Verifique sua conexão com a internet e tente novamente.",
        "status_code": 502,
    },
    errors.LanguageNotAvailableError: {
        "name": "LanguageNotAvailableError",
        "message": "O idioma solicitado não está disponível para este vídeo.",
        "action": "Escolha um dos idiomas listados para o vídeo.",
        "status_code": 404,
    },
    errors.TranslationNotAvailableError: {
        "name": "TranslationNotAvailableError",
        "message": "Não é possível traduzir a transcrição para o idioma solicitado.",
        "action": "Escolha um idioma de tradução disponível para este vídeo.",
        "status_code": 400,
    },
    errors.VideoMetadataError: {
        "name": "VideoMetadataError",
        "message": "Não foi possível obter os dados do vídeo.",
        "action": "Tente novamente mais tarde; a transcrição pode continuar disponível.",
        "status_code": 502,
    },
    errors.TranscriptRetrievalError: {
        "name": "TranscriptRetrievalError",
        "message": "Não foi possível obter a transcrição do YouTube.",
        "action": "Tente novamente mais tarde; se persistir, atualize a youtube-transcript-api.",
        "status_code": 502,
    },
}


@pytest.mark.parametrize(("error_class", "body"), EXPECTED_BODIES.items())
def test_error_body_is_exact(error_class, body):
    error = error_class()
    assert isinstance(error, YTScriptError)
    assert error_class.__name__ == body["name"]
    assert error.to_dict() == body


def test_every_error_is_covered():
    declared = {
        cls
        for cls in vars(errors).values()
        if isinstance(cls, type) and issubclass(cls, YTScriptError) and cls is not YTScriptError
    }
    assert declared == set(EXPECTED_BODIES)


@pytest.mark.parametrize("error_class", EXPECTED_BODIES)
def test_str_combines_message_and_action(error_class):
    error = error_class()
    assert str(error) == f"{error.message} {error.action}"
