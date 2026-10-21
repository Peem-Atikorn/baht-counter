"""เครื่องมือติดป้ายกำกับเหรียญ (ส่วนที่ 1) วาดวงเองทุกเหรียญ ไม่ใช้ผลของระบบ จึงใช้วัดผลระบบได้โดยไม่ลำเอียง

รันจาก root ของ repo:
    python data/label_tool.py                     # เริ่มที่ภาพแรกที่ยังไม่มีป้าย
    python data/label_tool.py --start p1_white_room_top_010.jpg

เมาส์
    ซ้าย กดกลางเหรียญแล้วลากไปขอบ   เพิ่มเหรียญ (ภาพเอียง ลากไปขอบด้านที่ยาวที่สุด = ครึ่งแกนยาว ตาม docs/labels.md)
    ซ้าย คลิกบนวง                    เลือกเหรียญ
    ขวา คลิกบนวง                     ลบเหรียญ
คีย์บอร์ด
    1–6  ชนิด 25 สต. / 50 สต. / 1 / 2 / 5 / 10 บาท   0 = unknown
         ตั้งชนิดของเหรียญที่เลือก และใช้กับวงถัดไปที่วาด
    Delete ลบเหรียญที่เลือก    z ย้อนกลับ
    n, Space, → บันทึกแล้วไปภาพถัดไป    p, ← บันทึกแล้วย้อนภาพ    s บันทึก    q, Esc บันทึกแล้วออก

บันทึกลง data/labels/<ชื่อภาพ>.json ทันที (รูปแบบ docs/labels.md) พิกัดเป็นพิกเซลของภาพเต็มหลังหมุนตาม EXIF
ออกจากภาพไม่ได้ถ้ายังมีเหรียญที่ไม่ได้เลือกชนิด
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageOps

sys.path.insert(0, str(Path(__file__).resolve().parent))
import dataset  # noqa: E402
from dataset import COIN_TYPES, ROOT  # noqa: E402

KEY_TYPES = {str(k + 1): t.code for k, t in enumerate(COIN_TYPES)} | {"0": "unknown"}
TYPE_TEXT = {t.code: f"{t.value_baht:g}" for t in COIN_TYPES} | {"unknown": "?", None: "ชนิด?"}
TYPE_COLOR = {t.code: t.display_color for t in COIN_TYPES} | {"unknown": "#9ca3af", None: "#ffffff"}
TYPE_NAME = {t.code: t.name_th for t in COIN_TYPES} | {"unknown": "ไม่ทราบชนิด", None: "ยังไม่เลือก"}

MIN_DRAG_PX = 5          # ลากสั้นกว่านี้ (พิกเซลบนจอ) ถือเป็นการคลิกเลือก
MAX_UPSCALE = 2.0        # ภาพเว็บขนาดเล็กขยายได้ไม่เกินเท่านี้


def load_image(path: Path) -> Image.Image:
    """ภาพหลังหมุนตาม EXIF ให้พิกัดตรงกับ dataset.oriented_size"""
    with Image.open(path) as img:
        return ImageOps.exif_transpose(img).convert("RGB")


def load_label(data: Path, name: str) -> tuple[list[dict], str]:
    """(เหรียญ, notes) จากป้ายเดิม หรือ ([], "") ถ้ายังไม่มี"""
    path = dataset.label_path(data, name)
    if not path.exists():
        return [], ""
    doc = json.loads(path.read_text(encoding="utf-8"))
    return [dict(c) for c in doc.get("coins", [])], doc.get("notes", "")


def save_label(data: Path, name: str, size: tuple[int, int], coins: list[dict], notes: str = "") -> Path:
    path = dataset.label_path(data, name)
    path.parent.mkdir(parents=True, exist_ok=True)
    doc = {
        "image": name,
        "image_size": list(size),
        "coins": [
            {"center_xy": [round(c["center_xy"][0], 1), round(c["center_xy"][1], 1)],
             "radius_px": round(c["radius_px"], 1), "coin_type": c["coin_type"]}
            for c in coins
        ],
        "notes": notes,
    }
    path.write_text(json.dumps(doc, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def coin_at(coins: list[dict], x: float, y: float) -> int | None:
    """เหรียญที่ครอบจุด (x, y) ถ้าซ้อนกันเลือกวงที่ศูนย์กลางใกล้ที่สุดเทียบกับรัศมี"""
    best, best_d = None, 1.0
    for k, c in enumerate(coins):
        d = math.dist(c["center_xy"], (x, y)) / c["radius_px"]
        if d <= best_d:
            best, best_d = k, d
    return best


def untyped(coins: list[dict]) -> int:
    return sum(c["coin_type"] is None for c in coins)


def start_index(names: list[str], data: Path, start: str | None) -> int:
    """ภาพที่ระบุ หรือภาพแรกที่ยังไม่มีป้าย (ทุกภาพมีป้ายแล้วเริ่มภาพแรก)"""
    if start:
        return names.index(start)
    return next((k for k, n in enumerate(names) if not dataset.label_path(data, n).exists()), 0)


class LabelTool:
    def __init__(self, root, data: Path, names: list[str], index: int):
        import tkinter as tk

        self.tk = tk
        self.root, self.data, self.names = root, data, names
        self.current_type: str | None = None
        self.max_w = root.winfo_screenwidth() - 80
        self.max_h = root.winfo_screenheight() - 160

        self.canvas = tk.Canvas(root, highlightthickness=0, cursor="crosshair", bg="#222")
        self.canvas.pack()
        self.status = tk.Label(root, anchor="w", justify="left", font=("Tahoma", 11))
        self.status.pack(fill="x")
        self.message = tk.Label(root, anchor="w", fg="#b91c1c", font=("Tahoma", 11))
        self.message.pack(fill="x")

        self.canvas.bind("<ButtonPress-1>", self.on_press)
        self.canvas.bind("<B1-Motion>", self.on_drag)
        self.canvas.bind("<ButtonRelease-1>", self.on_release)
        self.canvas.bind("<Button-3>", self.on_right)
        root.bind("<Key>", self.on_key)
        root.protocol("WM_DELETE_WINDOW", self.quit)
        self.open(index)

    # ---------- ภาพ ----------
    def open(self, index: int):
        from PIL import ImageTk

        self.index = index
        self.name = self.names[index]
        self.image = load_image(self.data / "raw" / self.name)
        self.size = self.image.size
        w, h = self.size
        self.scale = min(self.max_w / w, self.max_h / h, MAX_UPSCALE)
        shown = self.image.resize((round(w * self.scale), round(h * self.scale)), Image.LANCZOS)
        self.photo = ImageTk.PhotoImage(shown)
        self.canvas.config(width=shown.width, height=shown.height)
        self.status.config(wraplength=shown.width)
        self.message.config(wraplength=shown.width)
        self.canvas.delete("all")
        self.canvas.create_image(0, 0, image=self.photo, anchor="nw")
        self.coins, self.notes = load_label(self.data, self.name)
        self.history: list[list[dict]] = []
        self.selected: int | None = None
        self.drag_start = None
        self.dirty = False
        self.say("")
        self.redraw()

    def save(self) -> bool:
        if (n := untyped(self.coins)):
            self.say(f"ยังมี {n} เหรียญที่ไม่ได้เลือกชนิด กดเลข 1–6 หรือ 0 ก่อน")
            return False
        if self.dirty:
            save_label(self.data, self.name, self.size, self.coins, self.notes)
            self.dirty = False
        return True

    def go(self, step: int):
        target = self.index + step
        if not 0 <= target < len(self.names):
            self.say("ภาพสุดท้ายแล้ว" if step > 0 else "ภาพแรกแล้ว")
            return
        if self.save():
            self.open(target)

    def quit(self):
        if self.save():
            self.root.destroy()

    # ---------- แก้เหรียญ ----------
    def change(self, fn):
        self.history.append([dict(c) for c in self.coins])
        fn()
        self.dirty = True
        self.say("")
        self.redraw()

    def to_image(self, event) -> tuple[float, float]:
        return event.x / self.scale, event.y / self.scale

    def on_press(self, event):
        self.drag_start = (event.x, event.y)

    def on_drag(self, event):
        if self.drag_start is None:
            return
        self.canvas.delete("preview")
        (sx, sy), r = self.drag_start, math.dist(self.drag_start, (event.x, event.y))
        if r >= MIN_DRAG_PX:
            color = TYPE_COLOR[self.current_type]
            self.canvas.create_oval(sx - r, sy - r, sx + r, sy + r, outline=color, width=2, dash=(4, 3), tags="preview")
            self.canvas.create_line(sx, sy, event.x, event.y, fill=color, tags="preview")

    def on_release(self, event):
        if self.drag_start is None:
            return
        self.canvas.delete("preview")
        (sx, sy), r = self.drag_start, math.dist(self.drag_start, (event.x, event.y))
        self.drag_start = None
        if r < MIN_DRAG_PX:
            self.selected = coin_at(self.coins, *self.to_image(event))
            self.redraw()
            return
        coin = {"center_xy": [sx / self.scale, sy / self.scale], "radius_px": r / self.scale,
                "coin_type": self.current_type}

        def add():
            self.coins.append(coin)
            self.selected = len(self.coins) - 1
        self.change(add)

    def on_right(self, event):
        k = coin_at(self.coins, *self.to_image(event))
        if k is not None:
            self.delete(k)

    def delete(self, k: int):
        def remove():
            del self.coins[k]
            self.selected = None
        self.change(remove)

    def on_key(self, event):
        key = event.keysym
        if event.char in KEY_TYPES:
            self.current_type = KEY_TYPES[event.char]
            if self.selected is not None and self.coins[self.selected]["coin_type"] != self.current_type:
                self.change(lambda: self.coins[self.selected].update(coin_type=self.current_type))
            else:
                self.redraw()
        elif key in ("Delete", "BackSpace") and self.selected is not None:
            self.delete(self.selected)
        elif key.lower() == "z" and self.history:
            self.coins = self.history.pop()
            self.selected = None
            self.dirty = True
            self.redraw()
        elif key in ("n", "space", "Right"):
            self.go(1)
        elif key in ("p", "Left"):
            self.go(-1)
        elif key == "s":
            if self.save():
                self.say("บันทึกแล้ว")
        elif key in ("q", "Escape"):
            self.quit()

    # ---------- แสดงผล ----------
    def say(self, text: str):
        self.message.config(text=text)

    def redraw(self):
        self.canvas.delete("coin")
        for k, c in enumerate(self.coins):
            x, y = c["center_xy"][0] * self.scale, c["center_xy"][1] * self.scale
            r = c["radius_px"] * self.scale
            color = TYPE_COLOR[c["coin_type"]]
            width = 4 if k == self.selected else 2
            dash = (4, 3) if c["coin_type"] is None else None
            self.canvas.create_oval(x - r, y - r, x + r, y + r, outline=color, width=width, dash=dash, tags="coin")
            self.canvas.create_oval(x - 2, y - 2, x + 2, y + 2, fill=color, outline="", tags="coin")
            self.canvas.create_text(x + 1, y - 11, text=TYPE_TEXT[c["coin_type"]], fill="black",
                                    font=("Tahoma", 12, "bold"), tags="coin")
            self.canvas.create_text(x, y - 12, text=TYPE_TEXT[c["coin_type"]], fill=color,
                                    font=("Tahoma", 12, "bold"), tags="coin")
        labeled = sum(dataset.label_path(self.data, n).exists() for n in self.names)
        counts = {}
        for c in self.coins:
            counts[TYPE_TEXT[c["coin_type"]]] = counts.get(TYPE_TEXT[c["coin_type"]], 0) + 1
        self.root.title(f"label_tool · {self.name} ({self.index + 1}/{len(self.names)}) · มีป้ายแล้ว {labeled} ภาพ"
                        + (" · ยังไม่บันทึก" if self.dirty else ""))
        self.status.config(text=(
            f"เหรียญ {len(self.coins)}  {counts}   ชนิดที่ใช้วาด: {TYPE_NAME[self.current_type]}\n"
            "ลากจากกลางไปขอบ = เพิ่ม · คลิก = เลือก · คลิกขวา/Delete = ลบ · 1=25สต 2=50สต 3=฿1 4=฿2 5=฿5 6=฿10 0=unknown"
            " · z ย้อน · n/→ ถัดไป · p/← ก่อนหน้า · q ออก"
        ))


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "data")
    ap.add_argument("--start", help="ชื่อภาพใน data/raw ที่จะเริ่ม (ค่าเริ่มต้น: ภาพแรกที่ยังไม่มีป้าย)")
    args = ap.parse_args(argv)

    names = sorted(n for n, p in dataset.find_images(args.data).items() if p.parent.name == "raw")
    if not names:
        sys.exit(f"ไม่พบภาพใน {args.data / 'raw'}")
    if args.start and args.start not in names:
        sys.exit(f"ไม่พบ {args.start} ใน {args.data / 'raw'}")

    import tkinter as tk
    root = tk.Tk()
    LabelTool(root, args.data, names, start_index(names, args.data, args.start))
    root.mainloop()


if __name__ == "__main__":
    main()
