class YTScriptError(Exception):
    name: str = "YTScriptError"
    message: str = "Erro inesperado."
    action: str = "Tente novamente."
    status_code: int = 500

    def __init__(self) -> None:
        super().__init__(self.message)

    def __str__(self) -> str:
        return f"{self.message} {self.action}"

    def to_dict(self) -> dict[str, str | int]:
        return {
            "name": self.name,
            "message": self.message,
            "action": self.action,
            "status_code": self.status_code,
        }


class InvalidUrlError(YTScriptError):
    name = "InvalidUrlError"
    message = "A URL informada é inválida."
    action = "Use um link https, como https://www.youtube.com/watch?v=ID, https://youtu.be/ID ou https://www.youtube.com/shorts/ID."
    status_code = 400


class UnsupportedDomainError(YTScriptError):
    name = "UnsupportedDomainError"
    message = "O domínio da URL não é suportado."
    action = "Use um link de youtube.com, m.youtube.com ou youtu.be."
    status_code = 400


class InvalidVideoIdError(YTScriptError):
    name = "InvalidVideoIdError"
    message = "Não foi possível encontrar um ID de vídeo válido na URL."
    action = "Confira se o link contém o ID do vídeo (11 caracteres), como em watch?v=ID."
    status_code = 400


class TranscriptsDisabledError(YTScriptError):
    name = "TranscriptsDisabledError"
    message = "As legendas estão desativadas para este vídeo."
    action = "Use um vídeo que tenha legendas habilitadas."
    status_code = 404


class TranscriptNotFoundError(YTScriptError):
    name = "TranscriptNotFoundError"
    message = "Não há transcrição acessível em português para este vídeo."
    action = "Use um vídeo com legenda manual ou automática em português."
    status_code = 404


class VideoUnavailableError(YTScriptError):
    name = "VideoUnavailableError"
    message = "O vídeo está indisponível ou com acesso restrito."
    action = "Confirme que o vídeo é público e que a URL está correta."
    status_code = 404


class AccessBlockedError(YTScriptError):
    name = "AccessBlockedError"
    message = "O YouTube bloqueou ou limitou o acesso."
    action = "Aguarde alguns minutos ou tente de outra rede (IPs de nuvem e VPN são mais afetados)."
    status_code = 429


class NetworkError(YTScriptError):
    name = "NetworkError"
    message = "Falha de rede ao acessar o YouTube."
    action = "Verifique sua conexão com a internet e tente novamente."
    status_code = 502


class TranscriptRetrievalError(YTScriptError):
    name = "TranscriptRetrievalError"
    message = "Não foi possível obter a transcrição do YouTube."
    action = "Tente novamente mais tarde; se persistir, atualize a youtube-transcript-api."
    status_code = 502


class LanguageNotAvailableError(YTScriptError):
    name = "LanguageNotAvailableError"
    message = "O idioma solicitado não está disponível para este vídeo."
    action = "Escolha um dos idiomas listados para o vídeo."
    status_code = 404


class TranslationNotAvailableError(YTScriptError):
    name = "TranslationNotAvailableError"
    message = "Não é possível traduzir a transcrição para o idioma solicitado."
    action = "Escolha um idioma de tradução disponível para este vídeo."
    status_code = 400


class VideoMetadataError(YTScriptError):
    name = "VideoMetadataError"
    message = "Não foi possível obter os dados do vídeo."
    action = "Tente novamente mais tarde; a transcrição pode continuar disponível."
    status_code = 502


class EmptyTranscriptError(YTScriptError):
    name = "EmptyTranscriptError"
    message = "A transcrição do vídeo está vazia."
    action = "Use um vídeo que tenha fala legendada."
    status_code = 404
