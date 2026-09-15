#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
png_bot.py — обработчик PNG-изображений.

Что делает:
  1. Обрезает пустое пространство по краям (прозрачные поля или однородный фон).
  2. Приводит высоту к заданной (по умолчанию 400px), ширина меняется пропорционально.
  3. Сохраняет PNG с максимальным БЕЗ ПОТЕРЬ (lossless) сжатием.
     Если в системе есть optipng — дополнительно дожимает файл через него (тоже lossless).

Использование:
  Без аргументов — обработает все PNG в ТОЙ ЖЕ папке, где лежит сам скрипт,
  и ПЕРЕЗАПИШЕТ их (просто положите png_bot.py в нужную папку и запустите):
    python3 png_bot.py

  Указать конкретную папку или файл (тоже перезапишет по умолчанию):
    python3 png_bot.py "C:\путь\к\папке"
    python3 png_bot.py image.png

  Не перезаписывать, а сохранить результат в другое место:
    python3 png_bot.py ./input_folder -o ./output_folder

  Своя высота:
    python3 png_bot.py --height 600

Требования:
  pip install pillow
  (опционально) optipng — для дополнительного дожатия без потерь
"""

import argparse
import os
import shutil
import subprocess
import sys

from PIL import Image, ImageChops


def trim_image(im: Image.Image, tolerance: int = 10) -> Image.Image:
    """Обрезает пустые поля вокруг содержимого.

    - Если есть альфа-канал — обрезка по границе непрозрачных пикселей.
    - Если альфы нет — обрезка по границе, где цвет отличается от фона
      (фон определяется по цвету левого верхнего пикселя), с допуском tolerance.
    """
    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        alpha = rgba.split()[-1]
        bbox = alpha.getbbox()
        return im.crop(bbox) if bbox else im

    rgb = im.convert("RGB")
    bg_color = rgb.getpixel((0, 0))
    bg = Image.new("RGB", rgb.size, bg_color)
    diff = ImageChops.difference(rgb, bg)
    if tolerance > 0:
        diff = diff.point(lambda p: 0 if p <= tolerance else 255)
    bbox = diff.getbbox()
    return im.crop(bbox) if bbox else im


def resize_to_height(im: Image.Image, target_height: int) -> Image.Image:
    """Меняет высоту на target_height, ширина — пропорционально."""
    w, h = im.size
    if h == target_height or h == 0:
        return im
    ratio = target_height / h
    new_w = max(1, round(w * ratio))
    return im.resize((new_w, target_height), Image.LANCZOS)


def optipng_available() -> bool:
    return shutil.which("optipng") is not None


def optimize_with_optipng(path: str) -> None:
    """Дополнительное lossless-сжатие через optipng (если установлен)."""
    try:
        subprocess.run(
            ["optipng", "-quiet", "-o4", path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except Exception:
        pass  # тихо пропускаем, если optipng не смог обработать файл


def process_file(in_path: str, out_path: str, target_height: int) -> tuple[int, int]:
    im = Image.open(in_path)
    im = trim_image(im)
    im = resize_to_height(im, target_height)

    save_kwargs = dict(format="PNG", optimize=True, compress_level=9)
    im.save(out_path, **save_kwargs)

    if optipng_available():
        optimize_with_optipng(out_path)

    return os.path.getsize(in_path), os.path.getsize(out_path)


def human(n: int) -> str:
    for unit in ("B", "KB", "MB"):
        if n < 1024:
            return f"{n:.0f}{unit}"
        n /= 1024
    return f"{n:.1f}GB"


def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))

    parser = argparse.ArgumentParser(description="Обрезка пустоты, ресайз по высоте и lossless-сжатие PNG")
    parser.add_argument("input", nargs="?", default=script_dir,
                         help="Файл .png или папка с PNG-файлами (по умолчанию — папка, где лежит сам скрипт)")
    parser.add_argument("-o", "--output",
                         help="Сохранить результат сюда вместо перезаписи оригиналов "
                              "(папка для входной папки, файл для входного файла)")
    parser.add_argument("--height", type=int, default=400, help="Целевая высота в пикселях (по умолчанию 400)")
    args = parser.parse_args()

    overwrite = args.output is None

    if not optipng_available():
        print("[инфо] optipng не найден — используется только встроенное сжатие Pillow. "
              "Для лучшего сжатия установите: sudo apt install optipng", file=sys.stderr)

    if os.path.isdir(args.input):
        files = [f for f in os.listdir(args.input) if f.lower().endswith(".png")]
        if not files:
            print("В папке не найдено PNG-файлов.")
            return

        if overwrite:
            out_dir = args.input
        else:
            out_dir = args.output
            os.makedirs(out_dir, exist_ok=True)

        for f in files:
            in_file = os.path.join(args.input, f)
            out_file = os.path.join(out_dir, f)
            try:
                if overwrite:
                    # Обрабатываем во временный файл, затем атомарно заменяем оригинал
                    tmp_file = in_file + ".tmp_png_bot"
                    before, after = process_file(in_file, tmp_file, args.height)
                    os.replace(tmp_file, in_file)
                else:
                    before, after = process_file(in_file, out_file, args.height)
                pct = (1 - after / before) * 100 if before else 0
                print(f"{f}: {human(before)} -> {human(after)}  ({pct:+.1f}%)")
            except Exception as e:
                print(f"Ошибка при обработке {f}: {e}", file=sys.stderr)
    else:
        if not args.input.lower().endswith(".png"):
            print("Ожидается PNG-файл или папка с PNG-файлами.", file=sys.stderr)
            sys.exit(1)

        if overwrite:
            tmp_file = args.input + ".tmp_png_bot"
            before, after = process_file(args.input, tmp_file, args.height)
            os.replace(tmp_file, args.input)
            out_file = args.input
        else:
            out_file = args.output
            before, after = process_file(args.input, out_file, args.height)

        pct = (1 - after / before) * 100 if before else 0
        print(f"Готово: {out_file}")
        print(f"Размер: {human(before)} -> {human(after)}  ({pct:+.1f}%)")


if __name__ == "__main__":
    main()
