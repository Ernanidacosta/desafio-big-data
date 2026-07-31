"""Testes de comportamento do processamento batch (unittest + tempfile).

Exercitam o programa pela interface pública: um arquivo JSONL de entrada
é processado e os CSVs gerados são inspecionados. Nenhum detalhe interno
(funções auxiliares, contadores) é testado diretamente.
"""

import csv
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import main

CLUB_HEADER_LINE = (
    "Id do Clube,Nome,Campeonato,Data de Fundação,Cidade,Estado,"
    "País,Estádio,Presidente,Apelido,Cores"
)
PLAYER_HEADER_LINE = (
    "Id do Clube,Id do Jogador,Nome,Idade,Gols,Data de Estreia,"
    "Posição,Número da Camisa"
)


def club(**overrides):
    """Clube válido de Série A; sobrescreva só o que o teste precisa."""
    base = {
        "club_id": "A",
        "name": "Alpha",
        "championship": "SERIE A",
        "founding_date": "1910-01-01",
        "city": "Cidade",
        "state": "ST",
        "country": "Brasil",
        "stadium": "Estádio",
        "president": "Presidente",
        "nickname": "Apelido",
        "colors": ["preto", "branco"],
        "players": [],
    }
    base.update(overrides)
    return base


def process_records(records):
    """Grava `records` como JSONL, roda process e devolve os CSVs.

    Um item str é escrito como linha crua (para JSON malformado); um dict
    é serializado. Retorna (clubs_text, players_text, clubs, players).
    """
    with TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        src = tmp_path / "in.jsonl"
        lines = [
            rec if isinstance(rec, str) else json.dumps(rec, ensure_ascii=False)
            for rec in records
        ]
        src.write_text("\n".join(lines) + "\n", encoding="utf-8")

        out = tmp_path / "out"
        out.mkdir()
        main.process(src, out)

        clubs_text = (out / "clubs.csv").read_text(encoding="utf-8")
        players_text = (out / "players.csv").read_text(encoding="utf-8")

    clubs = list(csv.DictReader(clubs_text.splitlines()))
    players = list(csv.DictReader(players_text.splitlines()))
    return clubs_text, players_text, clubs, players


class ProcessingBehaviorTests(unittest.TestCase):
    def test_valid_and_invalid_dates(self):
        _, _, clubs, players = process_records([
            club(founding_date="1912-04-14", players=[
                {"player_id": "A-1", "debut_date": "2020-05-01"},
                {"player_id": "A-2", "debut_date": "2020-13-40"},
            ]),
            club(club_id="B", founding_date="not-a-date"),
        ])
        self.assertEqual(clubs[0]["Data de Fundação"], "1912-04-14")
        self.assertEqual(clubs[1]["Data de Fundação"], "")
        self.assertEqual(players[0]["Data de Estreia"], "2020-05-01")
        self.assertEqual(players[1]["Data de Estreia"], "")

    def test_none_becomes_empty_and_zero_preserved(self):
        _, _, clubs, players = process_records([
            club(nickname=None, players=[
                {"player_id": "A-1", "name": None, "goals": 0,
                 "shirt_number": 0},
            ]),
        ])
        self.assertEqual(clubs[0]["Apelido"], "")
        self.assertEqual(players[0]["Nome"], "")
        self.assertEqual(players[0]["Gols"], "0")
        self.assertEqual(players[0]["Número da Camisa"], "0")

    def test_colors_joined_by_pipe(self):
        _, _, clubs, _ = process_records([
            club(colors=["azul", "branco", "vermelho"]),
        ])
        self.assertEqual(clubs[0]["Cores"], "azul|branco|vermelho")

    def test_championship_filter(self):
        _, _, clubs, players = process_records([
            club(club_id="A", championship="SERIE A"),
            club(club_id="B", championship="SERIE B"),
            club(club_id="C", championship="SEM CAMPEONATO",
                 players=[{"player_id": "C-1"}]),
        ])
        self.assertEqual([c["Id do Clube"] for c in clubs], ["A", "B"])
        self.assertTrue(all(p["Id do Clube"] != "C" for p in players))

    def test_malformed_json_does_not_stop_file(self):
        _, _, clubs, _ = process_records([
            club(club_id="A"),
            "{ malformed json",
            club(club_id="B"),
        ])
        self.assertEqual(sorted(c["Id do Clube"] for c in clubs), ["A", "B"])

    def test_empty_and_non_object_lines_skipped(self):
        _, _, clubs, _ = process_records([
            club(club_id="A"),
            "",         # linha vazia -> ignorada
            "42",       # JSON válido não-objeto -> descartada
            "[1, 2]",   # idem
            club(club_id="B"),
        ])
        self.assertEqual(sorted(c["Id do Clube"] for c in clubs), ["A", "B"])

    def test_club_without_players(self):
        _, _, clubs, players = process_records([club(club_id="A", players=[])])
        self.assertEqual(len(clubs), 1)
        self.assertEqual(players, [])

    def test_players_field_invalid_type(self):
        _, _, clubs, players = process_records([
            club(club_id="A", players="oops"),
        ])
        self.assertEqual(len(clubs), 1)
        self.assertEqual(players, [])

    def test_invalid_player_item_skipped(self):
        _, _, _, players = process_records([
            club(club_id="A", players=[
                {"player_id": "A-1"},
                42,
                {"player_id": "A-2"},
            ]),
        ])
        self.assertEqual([p["Id do Jogador"] for p in players], ["A-1", "A-2"])

    def test_header_order(self):
        clubs_text, players_text, _, _ = process_records([club()])
        self.assertEqual(clubs_text.splitlines()[0], CLUB_HEADER_LINE)
        self.assertEqual(players_text.splitlines()[0], PLAYER_HEADER_LINE)

    def test_csv_escapes_commas_and_quotes(self):
        clubs_text, _, clubs, _ = process_records([
            club(president="Pedro, Filho", stadium='Arena "do Povo"'),
        ])
        self.assertEqual(clubs[0]["Presidente"], "Pedro, Filho")
        self.assertEqual(clubs[0]["Estádio"], 'Arena "do Povo"')
        self.assertIn('"Pedro, Filho"', clubs_text)
        self.assertIn('"Arena ""do Povo"""', clubs_text)


if __name__ == "__main__":
    unittest.main()
