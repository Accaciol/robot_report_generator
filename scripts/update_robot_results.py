"""Substitui a entrada da pipeline pelos resultados mais recentes do Robot."""
from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import tempfile


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
    parser.add_argument("source", type=Path, help="Pasta com output.xml e evidências")
    args = parser.parse_args()
    destination = Path(__file__).resolve().parent.parent / "robot-results" / "current"
    try:
        replace_results(args.source, destination)
    except (ValueError, OSError) as exc:
        parser.exit(1, f"Erro: {exc}\n")
    print(f"Resultados substituídos em {destination}")


if __name__ == "__main__":
    main()
