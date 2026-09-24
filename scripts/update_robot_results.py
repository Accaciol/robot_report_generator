"""Importa, lista, migra e remove execuções Robot de um catálogo por sistema."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile
import sys

# Permite executar diretamente a partir de qualquer diretório, sem instalar o pacote.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.catalog import Catalog


def replace_results(source: Path, destination: Path) -> None:
    source = source.resolve()
    destination = destination.resolve()
    if not (source / "output.xml").is_file():
        raise ValueError("A pasta de origem precisa conter output.xml.")
    if source == destination or source in destination.parents or destination in source.parents:
        raise ValueError("As pastas de origem e destino não podem se sobrepor.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Copia primeiro: um erro na leitura não apaga os resultados anteriores.
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staged = Path(temporary) / "current"
        shutil.copytree(source, staged)
        for name in ("log.html", "report.html"):
            path = staged / name
            if path.is_file():
                path.unlink()
        if destination.exists():
            shutil.rmtree(destination)
        staged.rename(destination)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", nargs="?", type=Path, help="Pasta com output.xml e evidências")
    parser.add_argument("--system", help="Identificador estável do sistema")
    parser.add_argument("--name", help="Nome exibido no relatório")
    parser.add_argument("--catalog-dir", type=Path,
                        default=Path(__file__).resolve().parent.parent / "robot-results" / "systems")
    operations = parser.add_mutually_exclusive_group()
    operations.add_argument("--list", action="store_true", help="Listar sistemas e IDs completos das execuções")
    operations.add_argument("--remove", metavar="EXECUTION_ID", help="Remover uma execução do sistema")
    parser.add_argument("--migrate-history", type=Path,
                        help="Migrar também um histórico legado para um novo sistema")
    args = parser.parse_args()
    if args.list or args.remove:
        if args.source or args.name or args.migrate_history:
            parser.error("Listar/remover não aceita origem, nome ou migração.")
    elif not args.source:
        parser.error("Informe a pasta de origem, --list ou --remove.")
    if not args.list and not args.system:
        parser.error("Informe --system para importar ou remover execuções.")
    catalog = Catalog(args.catalog_dir)
    try:
        if args.list:
            systems = [catalog.load(args.system)] if args.system else catalog.systems()
            for metadata, history, _ in systems:
                print(f"{metadata['id']} — {metadata['name']} ({len(history)} execuções)")
                for entry in history:
                    details = " [com evidências]" if entry.execution_id == metadata['current_execution_id'] else ""
                    print(f"  {entry.execution_id} | {entry.timestamp} | {entry.pass_rate}%{details}")
        elif args.remove:
            catalog.remove(args.system, args.remove)
            print(f"Execução removida de {args.system}: {args.remove}")
        else:
            execution_id = catalog.import_results(args.source, args.system, args.name, args.migrate_history)
            print(f"Sistema: {args.system}\nExecução: {execution_id}\nCatálogo: {catalog.root}")
    except (ValueError, TypeError, OSError) as exc:
        parser.exit(1, f"Erro: {exc}\n")


if __name__ == "__main__":
    main()
