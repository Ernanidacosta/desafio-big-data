#!/usr/bin/env python3
"""Processamento batch: JSONL de clubes -> clubs.csv + players.csv.

Apenas biblioteca padrão. Leitura em streaming (um objeto por vez),
filtro de Série A/B, isolamento de erro por registro.
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any, Iterator, TextIO

LOG_FILENAME = "processing.log"

VALID_CHAMPIONSHIPS = {"SERIE A", "SERIE B"}

CLUB_HEADER = [
    "Id do Clube",
    "Nome",
    "Campeonato",
    "Data de Fundação",
    "Cidade",
    "Estado",
    "País",
    "Estádio",
    "Presidente",
    "Apelido",
    "Cores",
]

PLAYER_HEADER = [
    "Id do Clube",
    "Id do Jogador",
    "Nome",
    "Idade",
    "Gols",
    "Data de Estreia",
    "Posição",
    "Número da Camisa",
]

logger = logging.getLogger("desafio")

PROGRESS_EVERY = 100_000

STATS_TEMPLATE: dict[str, int] = {
    "linhas": 0,
    "linhas_vazias": 0,
    "clubes_exportados": 0,
    "jogadores_exportados": 0,
    "clubes_ignorados_campeonato": 0,
    "json_invalido": 0,
    "registros_invalidos": 0,
    "data_invalida": 0,
    "colors_invalido": 0,
    "players_invalido": 0,
    "jogadores_invalidos": 0,
}

stats: dict[str, int] = dict(STATS_TEMPLATE)


def reset_stats() -> None:
    """Zera o dicionário de estatísticas para uma nova execução."""
    stats.clear()
    stats.update(STATS_TEMPLATE)


def setup_logging(output_dir: Path) -> None:
    """Configura logging em arquivo (output_dir) e console."""
    logger.setLevel(logging.INFO)
    logger.handlers.clear()
    fmt = logging.Formatter("%(asctime)s | %(levelname)s | %(message)s")

    file_handler = logging.FileHandler(
        output_dir / LOG_FILENAME, encoding="utf-8"
    )
    file_handler.setFormatter(fmt)

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(fmt)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


def clean(value: Any) -> str:
    """Ausente/nulo -> ''. Zeros e demais valores viram texto."""
    if value is None:
        return ""
    return str(value)


def clean_date(value: Any) -> str:
    """Data ISO (YYYY-MM-DD) válida -> mantém; inválida/ausente -> ''."""
    text = clean(value).strip()
    if not text:
        return ""
    try:
        date.fromisoformat(text)
    except ValueError:
        stats["data_invalida"] += 1
        logger.warning("Data inválida ignorada: %r", text)
        return ""
    return text


def join_colors(value: Any) -> str:
    """Lista de cores unida por '|'; ausente/nulo -> ''."""
    if value is None:
        return ""
    if not isinstance(value, list):
        stats["colors_invalido"] += 1
        logger.warning("Campo 'colors' inválido ignorado: %r", value)
        return ""
    return "|".join(clean(color) for color in value)


def normalize_championship(value: Any) -> str:
    """Normaliza para comparação: sem acentos, maiúsculas, sem bordas."""
    text = clean(value).strip().upper()
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c))


def is_target_championship(value: Any) -> bool:
    return normalize_championship(value) in VALID_CHAMPIONSHIPS


def iter_records(fh: TextIO) -> Iterator[dict[str, Any]]:
    """Lê JSONL estrito: exatamente um objeto JSON por linha.

    A recuperação é por linha. Linha vazia é contabilizada e ignorada.
    JSON inválido, ou JSON válido que não seja objeto, descarta apenas
    aquela linha (WARNING) e segue. Não há recuperação de objetos
    distribuídos em várias linhas — leitura em streaming real.
    """
    for line in fh:
        stats["linhas"] += 1
        if stats["linhas"] % PROGRESS_EVERY == 0:
            logger.info("Progresso: %d linhas processadas.", stats["linhas"])

        text = line.strip()
        if not text:
            stats["linhas_vazias"] += 1
            continue

        try:
            obj = json.loads(text)
        except (json.JSONDecodeError, RecursionError) as exc:
            stats["json_invalido"] += 1
            logger.warning("JSON inválido na linha %d: %s", stats["linhas"], exc)
            continue

        if not isinstance(obj, dict):
            stats["registros_invalidos"] += 1
            logger.warning(
                "Linha %d ignorada: JSON não é objeto (%s).",
                stats["linhas"],
                type(obj).__name__,
            )
            continue

        yield obj


def build_club_row(club: dict[str, Any]) -> dict[str, str]:
    return {
        "Id do Clube": clean(club.get("club_id")),
        "Nome": clean(club.get("name")),
        "Campeonato": clean(club.get("championship")),
        "Data de Fundação": clean_date(club.get("founding_date")),
        "Cidade": clean(club.get("city")),
        "Estado": clean(club.get("state")),
        "País": clean(club.get("country")),
        "Estádio": clean(club.get("stadium")),
        "Presidente": clean(club.get("president")),
        "Apelido": clean(club.get("nickname")),
        "Cores": join_colors(club.get("colors")),
    }


def build_player_row(club_id: str, player: dict[str, Any]) -> dict[str, str]:
    return {
        "Id do Clube": club_id,
        "Id do Jogador": clean(player.get("player_id")),
        "Nome": clean(player.get("name")),
        "Idade": clean(player.get("age")),
        "Gols": clean(player.get("goals")),
        "Data de Estreia": clean_date(player.get("debut_date")),
        "Posição": clean(player.get("position")),
        "Número da Camisa": clean(player.get("shirt_number")),
    }


def _iter_players(club_id: str, record: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Retorna a lista de jogadores; avisa se o campo for de tipo inválido."""
    raw = record.get("players")
    if raw is None:
        return iter(())
    if not isinstance(raw, list):
        stats["players_invalido"] += 1
        logger.warning(
            "Campo 'players' inválido no clube %s: %s.",
            club_id or "?",
            type(raw).__name__,
        )
        return iter(())
    return iter(raw)


def _log_summary() -> None:
    resumo = " ".join(f"{key}={value}" for key, value in stats.items())
    logger.info("Resumo final | %s", resumo)


def process(input_path: Path, output_dir: Path) -> tuple[int, int]:
    """Lê o JSONL e grava os CSVs. Retorna (clubes, jogadores)."""
    reset_stats()
    clubs_path = output_dir / "clubs.csv"
    players_path = output_dir / "players.csv"

    with input_path.open(encoding="utf-8-sig", errors="replace") as fh, \
            clubs_path.open("w", newline="", encoding="utf-8") as clubs_fh, \
            players_path.open("w", newline="", encoding="utf-8") as players_fh:

        club_writer = csv.DictWriter(clubs_fh, fieldnames=CLUB_HEADER)
        player_writer = csv.DictWriter(players_fh, fieldnames=PLAYER_HEADER)
        club_writer.writeheader()
        player_writer.writeheader()

        for record in iter_records(fh):
            try:
                championship = record.get("championship")
                if not is_target_championship(championship):
                    stats["clubes_ignorados_campeonato"] += 1
                    logger.info(
                        "Clube ignorado por campeonato: %s (%s).",
                        clean(record.get("club_id")) or "?",
                        clean(championship) or "-",
                    )
                    continue

                club_id = clean(record.get("club_id"))
                club_writer.writerow(build_club_row(record))
                stats["clubes_exportados"] += 1

                for player in _iter_players(club_id, record):
                    try:
                        if not isinstance(player, dict):
                            raise TypeError(
                                f"tipo inesperado ({type(player).__name__})"
                            )
                        player_writer.writerow(
                            build_player_row(club_id, player)
                        )
                        stats["jogadores_exportados"] += 1
                    except Exception as exc:
                        stats["jogadores_invalidos"] += 1
                        logger.warning(
                            "Jogador inválido ignorado (clube %s): %s",
                            club_id or "?",
                            exc,
                        )
            except Exception as exc:
                stats["registros_invalidos"] += 1
                logger.warning("Registro %d ignorado: %s", stats["linhas"], exc)

    _log_summary()
    return stats["clubes_exportados"], stats["jogadores_exportados"]


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Processa um JSONL de clubes em clubs.csv e players.csv."
    )
    parser.add_argument(
        "input", type=Path, help="Caminho do arquivo JSONL de entrada."
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("."),
        help="Diretório de saída (padrão: diretório atual).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    output_dir: Path = args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    setup_logging(output_dir)

    logger.info("Início da execução.")
    logger.info("Entrada: %s", args.input)
    logger.info("Saída: %s", output_dir)

    if not args.input.is_file():
        logger.error("Arquivo de entrada não encontrado: %s", args.input)
        return 1

    try:
        process(args.input, output_dir)
    except Exception as exc:
        logger.error("Falha ao processar %s: %s", args.input, exc)
        return 1
    finally:
        logger.info("Fim da execução.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
