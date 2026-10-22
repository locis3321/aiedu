"""帧序列 → GIF（README 首屏动图）。

用法：python scripts/frames_to_gif.py <frames_dir> <out.gif> [--step 2] [--width 640] [--duration 120]
需要 Pillow（仅构建工具需要，不是项目依赖）。
"""

import argparse
from pathlib import Path

from PIL import Image


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("frames_dir")
    parser.add_argument("out")
    parser.add_argument("--step", type=int, default=2)
    parser.add_argument("--width", type=int, default=640)
    parser.add_argument("--duration", type=int, default=120, help="每帧毫秒")
    args = parser.parse_args()

    files = sorted(Path(args.frames_dir).glob("*.png"))[:: args.step]
    if not files:
        print("没有帧")
        return 1
    images = []
    for path in files:
        img = Image.open(path).convert("RGB")
        ratio = args.width / img.width
        img = img.resize((args.width, int(img.height * ratio)), Image.LANCZOS)
        images.append(img.convert("P", palette=Image.Palette.ADAPTIVE, colors=128))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    images[0].save(
        out,
        save_all=True,
        append_images=images[1:],
        duration=args.duration,
        loop=0,
        optimize=True,
    )
    size_kb = out.stat().st_size / 1024
    print(f"gif: {out} | 帧数 {len(images)} | {size_kb:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
