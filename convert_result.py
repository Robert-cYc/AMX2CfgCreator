from pathlib import Path
import subprocess

import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog


OUTPUT_DIRECTORY = Path(__file__).resolve().parent
LEGACY_OUTPUT_FILENAME = "NET.txt"
OUTPUT_FILENAME = "S1CONF.txt"


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


def convert_s1_line(line_number: int, line: str) -> str:
    name = parse_fields(line)[0]
    return f"{line_number}\tGBLDEF\t{name}[  SLOT=5, NETWORK=\"C\"]"


def convert_file(input_path: Path, starting_line: int) -> tuple[Path, Path]:
    legacy_records = []
    s1_records = []

    with input_path.open("r", encoding="utf-8-sig", newline="") as source:
        line_number = starting_line
        for line in source:
            if line.strip():
                legacy_records.append(convert_legacy_line(line))
                s1_records.append(convert_s1_line(line_number, line))
                line_number += 1

    output_directory = OUTPUT_DIRECTORY
    output_directory.mkdir(parents=True, exist_ok=True)

    net_path = output_directory / LEGACY_OUTPUT_FILENAME
    net_path.write_text("\n".join(legacy_records) + "\n", encoding="utf-8")

    s1_path = output_directory / OUTPUT_FILENAME
    s1_path.write_text("\n".join(s1_records) + "\n", encoding="utf-8")

    return net_path, s1_path


def main() -> None:
    root = tk.Tk()
    root.withdraw()

    input_path = filedialog.askopenfilename(
        title="選擇要轉換的文字檔",
        filetypes=(("文字檔", "*.txt"), ("所有檔案", "*.*")),
    )

    if not input_path:
        return

    starting_line = simpledialog.askinteger(
        "輸入起始行號",
        "請輸入起始行號：",
        initialvalue=1600,
        minvalue=0,
    )

    if starting_line is None:
        return

    try:
        net_path, s1_path = convert_file(Path(input_path), starting_line)
    except Exception as error:
        messagebox.showerror("轉換失敗", str(error))
        return
    finally:
        root.destroy()

    messagebox.showinfo(
        "轉換完成",
        f"已儲存到：\n{net_path}\n{s1_path}",
    )

    try:
        subprocess.Popen(["notepad.exe", str(net_path), str(s1_path)])
    except OSError as error:
        messagebox.showwarning("無法開啟 Notepad", str(error))


if __name__ == "__main__":
    main()
