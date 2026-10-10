"""Import, list, and remove Robot Framework executions in the SQLite catalog."""
from __future__ import annotations

import argparse
from pathlib import Path
import sys

# Allows direct invocation from any working directory without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.azure_publish import publish_if_configured
from core.import_service import ImportService
from core.sqlite_store import SQLiteStore, default_database_path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, help="Pasta de resultados ou arquivo ZIP")
    parser.add_argument("--system", help="Identificador estável do sistema")
    parser.add_argument("--name", help="Nome exibido do sistema")
    parser.add_argument("--version", help="Versão do produto testado")
    parser.add_argument("--execution-date", help="Data/hora ISO; por padrão, usa o output.xml")
    parser.add_argument("--database", type=Path, default=default_database_path(),
                        help="Arquivo SQLite de histórico e catálogo")
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--list", action="store_true", help="Listar sistemas e execuções")
    operations.add_argument("--remove", metavar="EXECUTION_ID", help="Remover execução de um sistema")
    args = parser.parse_args()
    if args.list or args.remove:
        if args.source or args.name or args.version or args.execution_date:
            parser.error("Listar/remover não aceita origem nem metadados de importação.")
    elif not args.source:
        parser.error("Informe a pasta ou ZIP de origem, ou --list/--remove.")
    if not args.list and not args.system:
        parser.error("Informe --system para importar ou remover execuções.")
    if args.source and (not args.name or not args.version):
        parser.error("Importação exige --name e --version.")

    store = SQLiteStore(args.database)
    try:
        if args.list:
            systems = [store.load(args.system)] if args.system else store.systems()
            for metadata, history, _ in systems:
                print(f"{metadata['id']} — {metadata['name']} ({len(history)} execuções)")
                for entry in history:
                    details = " [com arquivos]" if entry.execution_id == metadata["current_execution_id"] else ""
                    print(f"  {entry.execution_id} | {entry.timestamp} | {entry.system_version} | "
                          f"{entry.pass_rate}%{details}")
        elif args.remove:
            store.remove_execution(args.system, args.remove)
            print(f"Execução removida de {args.system}: {args.remove}")
            if publish_if_configured(args.database):
                print("Site atualizado no Azure Static Web Apps.")
        else:
            result = ImportService(args.database).import_source(
                args.source, args.system, args.name, args.version, args.execution_date)
            state = "já existia" if not result["inserted"] else "importada"
            print(f"Sistema: {args.system}\nExecução {state}: {result['execution_id']}\nBanco: {args.database}")
            if result["inserted"] and publish_if_configured(args.database):
                print("Site atualizado no Azure Static Web Apps.")
    except (ValueError, TypeError, OSError, RuntimeError) as exc:
        parser.exit(1, f"Erro: {exc}\n")


if __name__ == "__main__":
    main()
