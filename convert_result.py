from datetime import datetime
from pathlib import Path
import queue
import subprocess
import sys
import threading

import tkinter as tk
from tkinter import filedialog, messagebox
from tkinter import ttk


def get_output_directory() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


OUTPUT_DIRECTORY = get_output_directory()
LEGACY_OUTPUT_FILENAME = "net.txt"
OUTPUT_FILENAME = "s1conf.txt"


def parse_fields(line: str) -> list[str]:
    fields = [field.strip() for field in line.rstrip("\r\n").split("\t")]
    if fields:
        fields[-1] = fields[-1].rstrip(",")

    if not fields:
        raise ValueError(f"資料列沒有名稱：{line.rstrip()}")

    return fields


def convert_legacy_line(line: str) -> str:
    fields = parse_fields(line)

    if len(fields) not in (3, 4):
        raise ValueError(f"資料列欄位錯誤，預期 3 或 4 個欄位：{line.rstrip()}")

    name, drop, register = fields[:3]
    bit = f",BIT={fields[3]}" if len(fields) == 4 and fields[3] else ""
    return f"{name:<31}DROP={drop},REGISTER={register}{bit}"


def convert_s1_line(line_number: int, line: str, slot: int, network: str) -> str:
    name = parse_fields(line)[0]
    return f"{line_number}\tGBLDEF\t{name}[  SLOT={slot}, NETWORK=\"{network}\"]"


def convert_file(
    input_path: Path,
    starting_line: int,
    slot: int,
    network: str,
) -> tuple[Path, Path]:
    legacy_records = []
    s1_records = []

    with input_path.open("r", encoding="utf-8-sig", newline="") as source:
        line_number = starting_line
        for raw_line in source:
            if raw_line.strip():
                legacy_records.append(convert_legacy_line(raw_line))
                s1_records.append(convert_s1_line(line_number, raw_line, slot, network))
                line_number += 1

    output_directory = OUTPUT_DIRECTORY
    output_directory.mkdir(parents=True, exist_ok=True)

    net_path = output_directory / LEGACY_OUTPUT_FILENAME
    net_path.write_text("\n".join(legacy_records) + "\n", encoding="utf-8")

    s1_path = output_directory / OUTPUT_FILENAME
    s1_path.write_text("\n".join(s1_records) + "\n", encoding="utf-8")

    return net_path, s1_path


class ConverterApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.result_queue = queue.Queue()
        self.worker = None

        self.source_var = tk.StringVar()
        self.line_var = tk.StringVar(value="1600")
        self.slot_var = tk.StringVar(value="5")
        self.network_var = tk.StringVar(value="C")

        self.build_ui()
        self.log("程式已啟動")

    def build_ui(self) -> None:
        self.root.title("AMX2 Cfg Creator")
        self.root.geometry("980x480")
        self.root.minsize(820, 360)

        container = ttk.Frame(self.root, padding=16)
        container.pack(fill="both", expand=True)
        container.columnconfigure(0, weight=1)
        container.rowconfigure(3, weight=1)

        # Row 0: Source file selection
        source_frame = ttk.Frame(container)
        source_frame.grid(row=0, column=0, sticky="ew", pady=(0, 12))
        source_frame.columnconfigure(1, weight=1)

        ttk.Label(source_frame, text="Source:").grid(row=0, column=0, sticky="w", padx=(0, 8))
        self.source_entry = ttk.Entry(source_frame, textvariable=self.source_var)
        self.source_entry.grid(row=0, column=1, sticky="ew", padx=(0, 8))
        self.load_button = ttk.Button(
            source_frame,
            text="Load",
            width=10,
            command=self.choose_source,
        )
        self.load_button.grid(row=0, column=2, sticky="e")

        # Row 1: Parameters + Convert button placed right next to Network
        param_frame = ttk.Frame(container)
        param_frame.grid(row=1, column=0, sticky="w", pady=(0, 12))

        ttk.Label(param_frame, text="行號:").pack(side="left", padx=(0, 6))
        self.line_entry = ttk.Entry(param_frame, textvariable=self.line_var, width=12)
        self.line_entry.pack(side="left", padx=(0, 24))

        ttk.Label(param_frame, text="Slot:").pack(side="left", padx=(0, 6))
        self.slot_entry = ttk.Entry(param_frame, textvariable=self.slot_var, width=10)
        self.slot_entry.pack(side="left", padx=(0, 24))

        ttk.Label(param_frame, text="Network:").pack(side="left", padx=(0, 6))
        self.network_entry = ttk.Entry(param_frame, textvariable=self.network_var, width=10)
        self.network_entry.pack(side="left", padx=(0, 20))

        self.convert_button = ttk.Button(
            param_frame,
            text="Convert",
            width=14,
            command=self.start_convert,
        )
        self.convert_button.pack(side="left", padx=(0, 0))

        # Row 2: Logger Label
        ttk.Label(container, text="Logger:").grid(row=2, column=0, sticky="w", pady=(6, 4))

        # Row 3: Logger Text Area (Fills remaining space)
        logger_frame = ttk.Frame(container)
        logger_frame.grid(row=3, column=0, sticky="nsew")
        logger_frame.columnconfigure(0, weight=1)
        logger_frame.rowconfigure(0, weight=1)

        self.logger = tk.Text(
            logger_frame,
            wrap="word",
            font=("Consolas", 10),
            state="disabled",
        )
        self.logger.grid(row=0, column=0, sticky="nsew")

        log_scrollbar = ttk.Scrollbar(logger_frame, orient="vertical", command=self.logger.yview)
        log_scrollbar.grid(row=0, column=1, sticky="ns")
        self.logger.configure(yscrollcommand=log_scrollbar.set)

        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def log(self, description: str) -> None:
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.logger.configure(state="normal")
        self.logger.insert("end", f"{timestamp}    {description}\n")
        self.logger.see("end")
        self.logger.configure(state="disabled")

    def choose_source(self) -> None:
        input_path = filedialog.askopenfilename(
            title="選擇要轉換的文字檔",
            filetypes=(("文字檔", "*.txt"), ("所有檔案", "*.*")),
        )
        if input_path:
            self.source_var.set(input_path)
            self.log(f"已載入來源檔：{input_path}")

    def start_convert(self) -> None:
        source = self.source_var.get().strip()
        line_text = self.line_var.get().strip()
        slot_text = self.slot_var.get().strip()
        network = self.network_var.get().strip()

        if not source:
            self.log("請先選擇來源檔。")
            return

        try:
            starting_line = int(line_text)
        except ValueError:
            self.log("行號必須是整數。")
            return

        if starting_line < 0:
            self.log("行號不能小於 0。")
            return

        try:
            slot = int(slot_text)
        except ValueError:
            self.log("Slot 必須是整數。")
            return

        if slot < 0:
            self.log("Slot 不能小於 0。")
            return

        if not network:
            self.log("Network 不能是空白。")
            return

        self.log(f"開始轉換：{source}")
        self.set_busy(True)
        self.worker = threading.Thread(
            target=self.convert_worker,
            args=(source, starting_line, slot, network),
            daemon=True,
        )
        self.worker.start()
        self.root.after(100, self.poll_result)

    def convert_worker(
        self,
        source: str,
        starting_line: int,
        slot: int,
        network: str,
    ) -> None:
        try:
            net_path, s1_path = convert_file(
                Path(source),
                starting_line,
                slot,
                network,
            )
            self.result_queue.put(("success", net_path, s1_path))
        except Exception as error:
            self.result_queue.put(("error", str(error)))

    def poll_result(self) -> None:
        try:
            result = self.result_queue.get_nowait()
        except queue.Empty:
            self.root.after(100, self.poll_result)
            return

        if result[0] == "success":
            _, net_path, s1_path = result
            self.log(f"已產生 net.txt：{net_path}")
            self.log(f"已產生 s1conf.txt：{s1_path}")
            self.open_outputs((net_path, s1_path))
        else:
            self.log(f"轉換失敗：{result[1]}")

        self.set_busy(False)

    def open_outputs(self, output_paths: tuple[Path, Path]) -> None:
        for output_path in output_paths:
            try:
                subprocess.Popen(["notepad.exe", str(output_path)])
                self.log(f"已要求 Notepad 開啟：{output_path.name}")
            except OSError as error:
                self.log(f"無法開啟 Notepad：{error}")

    def set_busy(self, busy: bool) -> None:
        state = "disabled" if busy else "normal"
        self.load_button.configure(state=state)
        self.convert_button.configure(state=state)
        self.source_entry.configure(state=state)
        self.line_entry.configure(state=state)
        self.slot_entry.configure(state=state)
        self.network_entry.configure(state=state)

    def on_close(self) -> None:
        if self.worker is not None and self.worker.is_alive():
            messagebox.showwarning("轉換進行中", "請等待轉換完成後再關閉。")
            return
        self.root.destroy()


def enable_dpi_awareness() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(1)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


def hide_console_if_dedicated() -> None:
    if sys.platform == "win32":
        try:
            import ctypes
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd:
                pids = (ctypes.c_uint * 2)()
                count = ctypes.windll.kernel32.GetConsoleProcessList(pids, 2)
                if count == 1:
                    ctypes.windll.user32.ShowWindow(hwnd, 0)
        except Exception:
            pass


def main() -> None:
    hide_console_if_dedicated()
    enable_dpi_awareness()
    root = tk.Tk()
    ConverterApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
