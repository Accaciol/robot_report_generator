"""SQLite persistence for systems, executions, test snapshots, and latest artifacts."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import shutil
import sqlite3
from typing import Iterator

from core.history_manager import HistoryManager
from core.xml_parser import RobotOutputParser
from models import ExecutionStats, HistoryEntry, ReportData


def default_database_path() -> Path:
    configured = os.environ.get("ROBOT_REPORT_DATABASE")
    if configured:
        return Path(configured).expanduser().resolve()
    return Path(__file__).resolve().parent.parent / "robot-results" / "report_history.sqlite3"


def _timestamp(value: str | datetime | None) -> str:
    if not value:
        value = "1970-01-01T00:00:00"
    normalized = HistoryManager._timestamp(value)
    try:
        parsed = datetime.fromisoformat(normalized.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Data de execução inválida: {normalized}") from exc
    if parsed.tzinfo is None:
        return parsed.isoformat(timespec="seconds")
    return parsed.astimezone(timezone.utc).isoformat(timespec="seconds")


class SQLiteStore:
    """Repository backed by a versioned, transactional SQLite database."""

    SCHEMA_VERSION = 2

    def __init__(self, database: Path | str | None = None) -> None:
        self.database = Path(database or default_database_path()).expanduser().resolve()
        self.artifacts_root = self.database.parent / "executions"
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.artifacts_root.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.database, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute("PRAGMA journal_mode = WAL")
            version = connection.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, self.SCHEMA_VERSION):
                raise RuntimeError(f"Versão de banco SQLite não suportada: {version}")
            if version == 0:
                connection.executescript("""
                BEGIN IMMEDIATE;
                CREATE TABLE systems (
                    id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    created_at TEXT NOT NULL
                );
                CREATE TABLE executions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    system_id TEXT NOT NULL REFERENCES systems(id) ON DELETE CASCADE,
                    execution_id TEXT NOT NULL,
                    timestamp TEXT NOT NULL,
                    system_version TEXT NOT NULL,
                    total INTEGER NOT NULL,
                    passed INTEGER NOT NULL,
                    failed INTEGER NOT NULL,
                    skipped INTEGER NOT NULL,
                    elapsed_s REAL NOT NULL,
                    pass_rate REAL NOT NULL,
                    archive_relpath TEXT,
                    results_relpath TEXT,
                    imported_at TEXT NOT NULL,
                    UNIQUE(system_id, execution_id)
                );
                CREATE TABLE test_snapshots (
                    execution_pk INTEGER NOT NULL REFERENCES executions(id) ON DELETE CASCADE,
                    stable_id TEXT NOT NULL,
                    suite_name TEXT NOT NULL,
                    test_name TEXT NOT NULL,
                    status TEXT NOT NULL,
                    elapsed_s REAL NOT NULL,
                    artifacts INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY(execution_pk, stable_id)
                );
                CREATE INDEX executions_by_system_date
                    ON executions(system_id, timestamp, execution_id);
                CREATE INDEX test_snapshots_by_test
                    ON test_snapshots(stable_id, execution_pk);
                PRAGMA user_version = 1;
                COMMIT;
            """)
            if version < 2:
                connection.executescript("""
                    BEGIN IMMEDIATE;
                    CREATE TABLE IF NOT EXISTS schema_migrations (
                        version INTEGER PRIMARY KEY,
                        applied_at TEXT NOT NULL
                    );
                    INSERT OR IGNORE INTO schema_migrations(version, applied_at)
                    VALUES(2, strftime('%Y-%m-%dT%H:%M:%SZ', 'now'));
                    PRAGMA user_version = 2;
                    COMMIT;
                """)

    def backup_to(self, destination: Path | str) -> Path:
        """Create a consistent online SQLite backup, including committed WAL data."""
        target = Path(destination).expanduser().resolve()
        target.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as source:
            backup = sqlite3.connect(target, timeout=30)
            try:
                source.backup(backup)
                result = backup.execute("PRAGMA integrity_check").fetchone()[0]
                if result != "ok":
                    raise sqlite3.DatabaseError(f"Backup SQLite inválido: {result}")
            finally:
                backup.close()
        return target

    def restore_from(self, source_path: Path | str) -> None:
        """Validate a SQLite backup and restore its contents into the live database."""
        source_file = Path(source_path).expanduser().resolve()
        if not source_file.is_file():
            raise ValueError("Arquivo de backup não encontrado.")
        source = sqlite3.connect(f"file:{source_file}?mode=ro", uri=True, timeout=30)
        try:
            integrity = source.execute("PRAGMA integrity_check").fetchone()[0]
            tables = {row[0] for row in source.execute(
                "SELECT name FROM sqlite_master WHERE type='table'")}
            version = source.execute("PRAGMA user_version").fetchone()[0]
            required_tables = {"systems", "executions", "test_snapshots"}
            if integrity != "ok" or not required_tables.issubset(tables):
                raise ValueError("O arquivo não é um backup válido do Robot Reports.")
            if version not in (1, self.SCHEMA_VERSION):
                raise ValueError(f"Versão de banco incompatível: {version}.")
            with self._connection() as destination:
                source.backup(destination)
        except sqlite3.DatabaseError as exc:
            raise ValueError("Não foi possível ler o arquivo de backup SQLite.") from exc
        finally:
            source.close()
        self._initialize()

    def orphaned_artifact_directories(self) -> list[Path]:
        """List artifact bundles not referenced by any registered execution."""
        with self._connection() as connection:
            archive_rows = connection.execute(
                "SELECT archive_relpath FROM executions "
                "WHERE archive_relpath IS NOT NULL"
            )
            referenced = {
                str(self.database.parent / Path(row[0]).parent)
                for row in archive_rows
            }
            results_rows = connection.execute(
                "SELECT results_relpath FROM executions "
                "WHERE results_relpath IS NOT NULL"
            )
            referenced.update(
                str(self.database.parent / Path(row[0]).parent)
                for row in results_rows
            )
        candidates = []
        for system_directory in self.artifacts_root.iterdir():
            if not system_directory.is_dir() or system_directory.name.startswith(".pending-"):
                continue
            for bundle in system_directory.iterdir():
                if bundle.is_dir() and str(bundle.resolve()) not in referenced:
                    candidates.append(bundle)
        return sorted(candidates)

    def cleanup_orphaned_artifacts(self, delete: bool = False) -> list[str]:
        candidates = self.orphaned_artifact_directories()
        relative = [str(path.relative_to(self.database.parent)) for path in candidates]
        if delete:
            for path in candidates:
                shutil.rmtree(path)
        return relative

    @staticmethod
    def validate_system_id(system_id: str) -> None:
        valid_id = isinstance(system_id, str) and re.fullmatch(
            r"[a-z0-9]+(?:-[a-z0-9]+)*", system_id
        )
        if not valid_id:
            raise ValueError("Identificador do sistema: use letras minúsculas, números e hífens.")

    def systems(self) -> list[tuple[dict[str, object], list[HistoryEntry], Path]]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT id FROM systems ORDER BY name COLLATE NOCASE, id"
            )
            ids = [row[0] for row in rows]
        return [self.load(system_id) for system_id in ids]

    def load(
        self, system_id: str
    ) -> tuple[dict[str, object], list[HistoryEntry], Path]:
        self.validate_system_id(system_id)
        with self._connection() as connection:
            system = connection.execute("SELECT * FROM systems WHERE id=?", (system_id,)).fetchone()
            if system is None:
                raise ValueError(f"Sistema inexistente: {system_id}")
            rows = connection.execute(
                "SELECT * FROM executions WHERE system_id=? "
                "ORDER BY timestamp, execution_id",
                (system_id,),
            ).fetchall()
            entries = [self._entry(connection, row) for row in rows]
            current = next(
                (row for row in reversed(rows) if row["results_relpath"]),
                None,
            )
            current_id = current["execution_id"] if current else None
            directory = (
                self.artifacts_root / system_id / current_id
                if current_id
                else self.artifacts_root / system_id
            )
            metadata = {
                "schema_version": self.SCHEMA_VERSION,
                "id": system_id,
                "name": system["name"],
                "current_execution_id": current_id,
            }
            return metadata, entries, directory

    @staticmethod
    def _entry(connection: sqlite3.Connection, row: sqlite3.Row) -> HistoryEntry:
        snapshot_rows = connection.execute(
            "SELECT * FROM test_snapshots WHERE execution_pk=? ORDER BY stable_id",
            (row["id"],),
        )
        tests = [
            {
                "stable_id": test["stable_id"],
                "suite_name": test["suite_name"],
                "test_name": test["test_name"],
                "status": test["status"],
                "elapsed_s": test["elapsed_s"],
                "artifacts": test["artifacts"],
            }
            for test in snapshot_rows
        ]
        return HistoryEntry(
            timestamp=row["timestamp"],
            total=row["total"],
            passed=row["passed"],
            failed=row["failed"],
            skipped=row["skipped"],
            elapsed_s=row["elapsed_s"],
            pass_rate=row["pass_rate"],
            version=f"{row['timestamp'][:10]} · {row['execution_id'][:8]}",
            tests=tests,
            execution_id=row["execution_id"],
            system_version=row["system_version"],
        )

    def history(self, system_id: str) -> list[HistoryEntry]:
        return self.load(system_id)[1]

    def import_history_entries(
        self, system_id: str, system_name: str, entries: list[HistoryEntry]
    ) -> int:
        """Import summary-only legacy entries without creating JSON storage."""
        self.validate_system_id(system_id)
        if not system_name.strip():
            raise ValueError("Informe o nome do sistema.")
        inserted = 0
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO systems(id,name,created_at) VALUES(?,?,?) "
                "ON CONFLICT(id) DO UPDATE SET name=excluded.name",
                (system_id, system_name.strip(), now),
            )
            for index, entry in enumerate(entries):
                timestamp = _timestamp(entry.timestamp)
                payload = repr((timestamp, entry.total, entry.passed, entry.failed,
                                entry.skipped, entry.elapsed_s, entry.tests, index))
                execution_id = entry.execution_id or "legacy-" + hashlib.sha256(
                    payload.encode("utf-8")
                ).hexdigest()
                cursor = connection.execute(
                    "INSERT OR IGNORE INTO executions(system_id,execution_id,timestamp,"
                    "system_version,total,passed,failed,skipped,elapsed_s,pass_rate,"
                    "archive_relpath,results_relpath,imported_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,NULL,NULL,?)",
                    (system_id, execution_id, timestamp, entry.system_version or "não informada",
                     entry.total, entry.passed, entry.failed, entry.skipped, entry.elapsed_s,
                     entry.pass_rate, now),
                )
                if cursor.rowcount == 0:
                    continue
                inserted += 1
                connection.executemany(
                    "INSERT OR IGNORE INTO test_snapshots(execution_pk,stable_id,suite_name,"
                    "test_name,status,elapsed_s,artifacts) VALUES(?,?,?,?,?,?,?)",
                    [(cursor.lastrowid, str(test.get("stable_id", "")),
                      str(test.get("suite_name", "")), str(test.get("test_name", "")),
                      str(test.get("status", "")), float(test.get("elapsed_s", 0)),
                      int(test.get("artifacts", 0))) for test in entry.tests],
                )
            connection.commit()
        return inserted

    def add_execution(
        self,
        system_id: str,
        system_name: str,
        system_version: str,
        timestamp: str | datetime | None,
        suites: list,
        stats: ExecutionStats,
        execution_id: str,
        staged_bundle: Path | None = None,
    ) -> tuple[bool, list[HistoryEntry]]:
        self.validate_system_id(system_id)
        if not system_name.strip() or not system_version.strip():
            raise ValueError("Informe o nome do sistema e a versão do produto.")
        normalized_timestamp = _timestamp(timestamp)
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        final_directory = self.artifacts_root / system_id / execution_id
        moved = False
        old_directories: list[Path] = []
        try:
            with self._connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                connection.execute(
                    "INSERT INTO systems(id,name,created_at) VALUES(?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET name=excluded.name",
                    (system_id, system_name.strip(), now),
                )
                duplicate = connection.execute(
                    "SELECT id FROM executions WHERE system_id=? AND execution_id=?",
                    (system_id, execution_id)).fetchone()
                if duplicate:
                    connection.commit()
                    return False, self.history(system_id)
                previous = connection.execute(
                    "SELECT id,execution_id,timestamp,results_relpath "
                    "FROM executions WHERE system_id=? AND results_relpath IS NOT NULL "
                    "ORDER BY timestamp DESC, execution_id DESC LIMIT 1",
                    (system_id,),
                ).fetchone()
                current_key = (
                    (previous["timestamp"], previous["execution_id"])
                    if previous
                    else None
                )
                incoming_key = (normalized_timestamp, execution_id)
                is_current = current_key is None or incoming_key > current_key
                archive_relpath = results_relpath = None
                if is_current and staged_bundle is not None:
                    final_directory.parent.mkdir(parents=True, exist_ok=True)
                    # The database may have been reset while its artifact volume
                    # was preserved. In that case this path is an orphan from an
                    # earlier import and os.replace() cannot replace a non-empty
                    # directory. A matching database row was checked above, so
                    # no registered execution points to this bundle.
                    if final_directory.exists():
                        shutil.rmtree(final_directory)
                    os.replace(staged_bundle, final_directory)
                    moved = True
                    relative_directory = final_directory.relative_to(self.database.parent)
                    archive_relpath = str(relative_directory / "original.zip")
                    results_relpath = str(relative_directory / "results")
                cursor = connection.execute(
                    "INSERT INTO executions("
                    "system_id,execution_id,timestamp,system_version,total,passed,failed,skipped,"
                    "elapsed_s,pass_rate,archive_relpath,results_relpath,imported_at) "
                    "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        system_id,
                        execution_id,
                        normalized_timestamp,
                        system_version.strip(),
                        stats.total,
                        stats.passed,
                        stats.failed,
                        stats.skipped,
                        round(stats.elapsed_s, 2),
                        stats.pass_rate,
                        archive_relpath,
                        results_relpath,
                        now,
                    ),
                )
                snapshots = HistoryManager._test_snapshots(suites)
                connection.executemany(
                    "INSERT INTO test_snapshots("
                    "execution_pk,stable_id,suite_name,test_name,status,elapsed_s,artifacts) "
                    "VALUES(?,?,?,?,?,?,?)",
                    [
                        (
                            cursor.lastrowid,
                            str(test["stable_id"]),
                            str(test["suite_name"]),
                            str(test["test_name"]),
                            str(test["status"]),
                            float(test["elapsed_s"]),
                            int(test["artifacts"]),
                        )
                        for test in snapshots
                    ],
                )
                if is_current and previous:
                    old_relpaths = {previous["results_relpath"]}
                    old = connection.execute(
                        "SELECT archive_relpath FROM executions WHERE id=?",
                        (previous["id"],),
                    ).fetchone()
                    if old and old["archive_relpath"]:
                        old_relpaths.add(old["archive_relpath"])
                    old_directories = [
                        self.database.parent / Path(rel).parent
                        for rel in old_relpaths
                        if rel
                    ]
                    connection.execute(
                        "UPDATE executions SET archive_relpath=NULL,results_relpath=NULL "
                        "WHERE id=?",
                        (previous["id"],),
                    )
                connection.commit()
                moved = False
            for directory in set(old_directories):
                if directory.exists():
                    shutil.rmtree(directory, ignore_errors=True)
            return True, self.history(system_id)
        except Exception:
            if moved and final_directory.exists():
                shutil.rmtree(final_directory, ignore_errors=True)
            raise

    def remove_execution(self, system_id: str, execution_id: str) -> None:
        self.validate_system_id(system_id)
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT archive_relpath,results_relpath FROM executions "
                "WHERE system_id=? AND execution_id=?",
                (system_id, execution_id),
            ).fetchone()
            if row is None:
                raise ValueError(f"Execução inexistente em {system_id}: {execution_id}")
            paths = [row[key] for key in ("archive_relpath", "results_relpath") if row[key]]
            connection.execute(
                "DELETE FROM executions WHERE system_id=? AND execution_id=?",
                (system_id, execution_id),
            )
            connection.commit()
        if paths:
            shutil.rmtree(self.artifacts_root / system_id / execution_id, ignore_errors=True)

    def report_data(
        self,
        metadata: dict[str, object],
        history: list[HistoryEntry],
        directory: Path,
        title: str,
        issue_url: str = "",
    ) -> ReportData:
        latest = history[-1] if history else None
        stats = (
            ExecutionStats(
                **{
                    key: getattr(latest, key)
                    for key in (
                        "total",
                        "passed",
                        "failed",
                        "skipped",
                        "elapsed_s",
                    )
                }
            )
            if latest
            else ExecutionStats()
        )
        suites, errors, environment = [], [], {}
        current_id = metadata["current_execution_id"]
        if current_id:
            xml = directory / "results" / "output.xml"
            xml_hash = hashlib.sha256(xml.read_bytes()).hexdigest() if xml.is_file() else ""
            if xml_hash != current_id:
                raise ValueError(
                    f"Outputs de {metadata['id']} ausentes ou alterados; "
                    "reimporte a execução."
                )
            parser = RobotOutputParser(str(xml))
            suites, _ = parser.parse()
            errors, environment = parser.errors, parser.environment
        return ReportData(
            stats=stats,
            suites=suites,
            history=history,
            title=f"{title} — {metadata['name']}",
            generated_at=datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
            version=latest.version if latest else "sem execuções",
            system_version=latest.system_version if latest else "",
            errors=errors,
            environment=environment,
            flaky_tests=HistoryManager.detect_flaky_tests(history),
            delta_stats=HistoryManager.compute_delta_stats(stats, history),
            issue_url_pattern=issue_url,
            detailed_execution_id=current_id or "",
        )
