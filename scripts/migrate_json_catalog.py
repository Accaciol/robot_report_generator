"""Migrate a legacy per-system JSON catalog into the SQLite database."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.import_service import ImportService
from core.history_manager import HistoryManager
from core.sqlite_store import SQLiteStore, default_database_path
from core.xml_parser import RobotOutputParser
from models import HistoryEntry


def migrate(source: Path, database: Path) -> int:
    """Copy summaries and latest execution artifacts; leave source files intact."""
    source = source.expanduser().resolve()
    store = SQLiteStore(database)
    imported = 0
    for folder in sorted(source.iterdir()):
        if not folder.is_dir() or folder.name.startswith("."):
            continue
        metadata_path = folder / "system.json"
        history_path = folder / "history.json"
        if not metadata_path.is_file() or not history_path.is_file():
            continue
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        entries_raw = json.loads(history_path.read_text(encoding="utf-8"))
        if not isinstance(entries_raw, list):
            raise ValueError(f"Histórico inválido: {history_path}")
        entries = [HistoryEntry(**entry) for entry in entries_raw]
        system_id = str(metadata["id"])
        system_name = str(metadata["name"])
        current = folder / "current"
        if (current / "output.xml").is_file():
            parser = RobotOutputParser(str(current / "output.xml"))
            suites, stats = parser.parse()
            timestamp = HistoryManager._timestamp(parser.execution_start)
            snapshots = HistoryManager._test_snapshots(suites)
            entries = [entry for entry in entries if not (
                HistoryManager._timestamp(entry.timestamp)[:19] == timestamp[:19]
                and (entry.total, entry.passed, entry.failed, entry.skipped,
                     round(entry.elapsed_s, 2), entry.tests)
                == (stats.total, stats.passed, stats.failed, stats.skipped,
                    round(stats.elapsed_s, 2), snapshots)
            )]
        imported += store.import_history_entries(system_id, system_name, entries)
        if (current / "output.xml").is_file():
            result = ImportService(database).import_source(
                current, system_id, system_name, "não informada"
            )
            imported += int(bool(result["inserted"]))
        print(f"{system_id}: {len(entries)} resumo(s) lido(s)")
    return imported


def migrate_history_file(history_path: Path, database: Path, system_id: str, name: str) -> int:
    """Import a standalone history.json that belongs to one system."""
    raw = json.loads(history_path.expanduser().read_text(encoding="utf-8"))
    if not isinstance(raw, list):
        raise ValueError(f"Histórico inválido: {history_path}")
    entries = [HistoryEntry(**entry) for entry in raw]
    return SQLiteStore(database).import_history_entries(system_id, name, entries)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path,
                        help="Raiz do catálogo antigo com system.json/history.json")
    parser.add_argument("--history-json", type=Path,
                        help="Arquivo history.json antigo pertencente a um único sistema")
    parser.add_argument("--system", help="Identificador do sistema para --history-json")
    parser.add_argument("--name", help="Nome do sistema para --history-json")
    parser.add_argument("--database", type=Path, default=default_database_path(),
                        help="Destino SQLite (padrão: banco configurado pela aplicação)")
    args = parser.parse_args()
    if bool(args.source) == bool(args.history_json):
        parser.error("Informe a raiz do catálogo antigo ou --history-json.")
    if args.history_json and (not args.system or not args.name):
        parser.error("--history-json exige --system e --name.")
    try:
        count = (migrate_history_file(args.history_json, args.database, args.system, args.name)
                 if args.history_json else migrate(args.source, args.database))
    except (OSError, ValueError, TypeError, json.JSONDecodeError, KeyError, RuntimeError) as exc:
        parser.exit(1, f"Falha na migração: {exc}\n")
    print(f"Migração concluída: {count} execução(ões) adicionada(s) ao banco {args.database}.")
    print("Os arquivos JSON de origem foram preservados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
