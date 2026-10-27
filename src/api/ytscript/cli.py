import argparse
import sys
from collections.abc import Sequence

from ytscript.controllers.transcript_controller import get_transcript
from infra.errors import YTScriptError
from ytscript.views.transcript_view import format_transcript


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="ytscript",
        description="Imprime a transcrição em português de um vídeo do YouTube, com timestamps.",
    )
    parser.add_argument("url", help="URL do vídeo (watch, youtu.be ou shorts)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        text = format_transcript(get_transcript(args.url))
    except YTScriptError as error:
        print(f"ytscript: erro: {error}", file=sys.stderr)
        return 1

    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
