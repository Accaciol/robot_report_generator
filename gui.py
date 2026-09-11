"""Interface desktop para executar o gerador de relatórios."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
import webbrowser
from pathlib import Path
from tkinter import filedialog, messagebox, ttk


PROJECT_ROOT = Path(__file__).resolve().parent


def build_command(
    python_executable: str,
    main_path: Path,
    results_dir: str,
    output_xml: str,
    history_path: str,
    report_path: str,
) -> list[str]:
    """Monta a chamada da CLI sem quoting manual ou shell intermediário."""
    command = [python_executable, str(main_path)]
    if results_dir:
        command.extend(["--results-dir", results_dir])
    if output_xml:
        command.extend(["--output-xml", output_xml])
    if history_path:
        command.extend(["--history", history_path])
    if report_path:
        command.extend(["--report", report_path])
    return command


class ReportGui:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Gerador de Relatórios Robot Framework")
        self.root.geometry("760x560")
        self.root.minsize(680, 480)
        self.events: queue.Queue[tuple[str, str | int | None]] = queue.Queue()
        self.process: subprocess.Popen[str] | None = None
        self.pending_results: list[Path] = []
        self.current_result_index = 0
        self.path_vars = {
            "history": tk.StringVar(value=str(PROJECT_ROOT / "history.json")),
            "report": tk.StringVar(value=str(PROJECT_ROOT / "relatorio.html")),
        }
        self.status_var = tk.StringVar(value="Pronto")
        self._build_ui()
        self.root.after(100, self._drain_events)

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        header = ttk.Frame(self.root, padding=(18, 16, 18, 8))
        header.grid(row=0, column=0, sticky="ew")
        header.columnconfigure(0, weight=1)
        ttk.Label(header, text="Gerador de Relatórios", font=("Segoe UI", 16, "bold")).grid(
            row=0, column=0, sticky="w"
        )
        ttk.Label(header, textvariable=self.status_var).grid(row=0, column=1, sticky="e")

        content = ttk.Frame(self.root, padding=(18, 8, 18, 18))
        content.grid(row=1, column=0, sticky="nsew")
        content.columnconfigure(1, weight=1)
        content.rowconfigure(5, weight=1)

        ttk.Label(content, text="Pastas results").grid(row=0, column=0, sticky="nw", padx=(0, 10), pady=5)
        results_frame = ttk.Frame(content)
        results_frame.grid(row=0, column=1, columnspan=2, sticky="ew", pady=5)
        results_frame.columnconfigure(0, weight=1)
        self.results_list = tk.Listbox(results_frame, height=4, exportselection=False)
        self.results_list.grid(row=0, column=0, rowspan=2, sticky="ew")
        results_scrollbar = ttk.Scrollbar(results_frame, orient="vertical", command=self.results_list.yview)
        results_scrollbar.grid(row=0, column=1, rowspan=2, sticky="ns")
        self.results_list.configure(yscrollcommand=results_scrollbar.set)
        results_actions = ttk.Frame(results_frame)
        results_actions.grid(row=0, column=2, rowspan=2, padx=(8, 0), sticky="n")
        ttk.Button(results_actions, text="Adicionar", command=self._add_results).pack(fill="x")
        ttk.Button(results_actions, text="Remover", command=self._remove_results).pack(fill="x", pady=(5, 0))
        ttk.Button(results_actions, text="Limpar", command=self._clear_results).pack(fill="x", pady=(5, 0))

        fields = [
            ("Arquivo history.json", "history", "history"),
            ("Relatório HTML", "report", "report"),
        ]
        for row, (label, key, kind) in enumerate(fields):
            row += 2
            ttk.Label(content, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=5)
            ttk.Entry(content, textvariable=self.path_vars[key]).grid(
                row=row, column=1, sticky="ew", pady=5
            )
            ttk.Button(content, text="Selecionar", command=lambda k=key, t=kind: self._choose(k, t)).grid(
                row=row, column=2, padx=(8, 0), pady=5
            )

        actions = ttk.Frame(content)
        actions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(10, 8))
        self.run_button = ttk.Button(actions, text="Gerar relatório", command=self.run_report)
        self.run_button.pack(side="left")
        self.cancel_button = ttk.Button(actions, text="Cancelar", command=self.cancel_execution, state="disabled")
        self.cancel_button.pack(side="left", padx=(8, 0))
        self.open_button = ttk.Button(actions, text="Abrir relatório", command=self.open_report, state="disabled")
        self.open_button.pack(side="left", padx=(8, 0))
        ttk.Button(actions, text="Limpar log", command=self.clear_log).pack(side="right")

        log_frame = ttk.LabelFrame(content, text="Log da execução", padding=8)
        log_frame.grid(row=5, column=0, columnspan=3, sticky="nsew")
        log_frame.columnconfigure(0, weight=1)
        log_frame.rowconfigure(0, weight=1)
        self.log = tk.Text(log_frame, wrap="word", state="disabled", height=14, font=("Consolas", 9))
        self.log.grid(row=0, column=0, sticky="nsew")
        scrollbar = ttk.Scrollbar(log_frame, orient="vertical", command=self.log.yview)
        scrollbar.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scrollbar.set)

    def _add_results(self) -> None:
        selected = filedialog.askdirectory(initialdir=str(PROJECT_ROOT))
        if not selected:
            return
        path = Path(selected).expanduser().resolve()
        if path in self.pending_results:
            return
        if not (path / "output.xml").is_file():
            messagebox.showerror("Pasta inválida", f"output.xml não encontrado em:\n{path}")
            return
        self.pending_results.append(path)
        self.results_list.insert("end", str(path))

    def _remove_results(self) -> None:
        selected = list(self.results_list.curselection())
        for index in reversed(selected):
            self.results_list.delete(index)
            self.pending_results.pop(index)

    def _clear_results(self) -> None:
        self.pending_results.clear()
        self.results_list.delete(0, "end")

    def _choose(self, key: str, kind: str) -> None:
        if kind == "history":
            selected = filedialog.askopenfilename(
                initialdir=self._initial_dir(key), filetypes=[("JSON", "*.json"), ("Todos", "*.*")]
            )
        else:
            selected = filedialog.asksaveasfilename(
                initialdir=self._initial_dir(key),
                defaultextension=".html",
                filetypes=[("HTML", "*.html"), ("Todos", "*.*")],
            )
        if selected:
            self.path_vars[key].set(selected)

    def _initial_dir(self, key: str) -> str:
        path = Path(self.path_vars[key].get())
        return str(path if path.is_dir() else path.parent)

    def _validate(self) -> bool:
        report = Path(self.path_vars["report"].get()).expanduser()
        if not self.pending_results:
            messagebox.showerror("Caminho inválido", "Adicione pelo menos uma pasta results.")
            return False
        invalid = [path for path in self.pending_results if not (path / "output.xml").is_file()]
        if invalid:
            messagebox.showerror("Caminho inválido", "output.xml não encontrado em:\n" + "\n".join(map(str, invalid)))
            return False
        if not report.parent.exists():
            messagebox.showerror("Caminho inválido", f"A pasta do relatório não existe:\n{report.parent}")
            return False
        return True

    def run_report(self) -> None:
        if self.process is not None:
            return
        if not self._validate():
            return
        self.clear_log()
        self.current_result_index = 0
        self.run_button.configure(state="disabled")
        self.cancel_button.configure(state="normal")
        self.open_button.configure(state="disabled")
        self._start_next_result()

    def cancel_execution(self) -> None:
        if self.process is not None:
            self._append_log("Cancelando execução a pedido do usuário...")
            try:
                self.process.terminate()
            except OSError:
                pass
            self.process = None
            self.status_var.set("Cancelado")
            self.run_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")

    def _start_next_result(self) -> None:
        result_dir = self.pending_results[self.current_result_index]
        report_base = Path(self.path_vars["report"].get()).expanduser()
        # Se houver múltiplas pastas, nomeia cada relatório individualmente mantendo o principal na última
        if len(self.pending_results) > 1 and self.current_result_index < len(self.pending_results) - 1:
            report_target = report_base.parent / f"{report_base.stem}_{result_dir.name}{report_base.suffix}"
        else:
            report_target = report_base

        command = build_command(
            sys.executable,
            PROJECT_ROOT / "main.py",
            str(result_dir),
            "",
            self.path_vars["history"].get(),
            str(report_target),
        )
        self._append_log(
            f"[{self.current_result_index + 1}/{len(self.pending_results)}] Executando: "
            + subprocess.list2cmdline(command)
        )
        self.status_var.set(f"Executando {self.current_result_index + 1}/{len(self.pending_results)}...")
        try:
            self.process = subprocess.Popen(
                command,
                cwd=str(PROJECT_ROOT),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
            )
        except OSError as exc:
            self.process = None
            self.run_button.configure(state="normal")
            self.cancel_button.configure(state="disabled")
            self.status_var.set("Erro ao iniciar")
            self._append_log(f"ERRO: {exc}")
            messagebox.showerror("Falha ao iniciar", str(exc))
            return
        for stream_name, stream in (("OUT", self.process.stdout), ("ERR", self.process.stderr)):
            if stream is not None:
                threading.Thread(target=self._read_stream, args=(stream_name, stream), daemon=True).start()
        threading.Thread(target=self._wait_process, daemon=True).start()

    def _read_stream(self, name: str, stream) -> None:
        for line in iter(stream.readline, ""):
            self.events.put(("line", f"[{name}] {line.rstrip()}"))
        stream.close()

    def _wait_process(self) -> None:
        if self.process is not None:
            code = self.process.wait()
            self.events.put(("finished", code))

    def _drain_events(self) -> None:
        try:
            while True:
                event, value = self.events.get_nowait()
                if event == "line":
                    self._append_log(str(value))
                elif event == "finished":
                    if isinstance(value, int):
                        self._finish(value)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)

    def _finish(self, code: int) -> None:
        self.process = None
        self.cancel_button.configure(state="disabled")
        report = Path(self.path_vars["report"].get()).expanduser()
        if code == 0 and self.current_result_index + 1 < len(self.pending_results):
            self.current_result_index += 1
            self._start_next_result()
        elif code == 0:
            self.run_button.configure(state="normal")
            self.status_var.set("Concluído")
            self._append_log(f"{len(self.pending_results)} relatório(s) processado(s). Saída: {report}")
            self.open_button.configure(state="normal" if report.is_file() else "disabled")
        else:
            self.run_button.configure(state="normal")
            self.status_var.set(f"Erro ({code})")
            self._append_log(f"Processo encerrado com código {code} na pasta {self.pending_results[self.current_result_index]}.")

    def open_report(self) -> None:
        report = Path(self.path_vars["report"].get()).expanduser()
        if report.is_file():
            webbrowser.open(report.resolve().as_uri())
        else:
            messagebox.showwarning("Relatório não encontrado", str(report))

    def clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        line_count = int(self.log.index("end-1c").split(".")[0])
        if line_count > 3000:
            self.log.delete("1.0", "500.0")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")


def main() -> None:
    root = tk.Tk()
    ReportGui(root)
    root.mainloop()


if __name__ == "__main__":
    main()
