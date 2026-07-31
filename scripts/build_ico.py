"""从高分辨率 PNG 生成多分辨率 Windows ICO。

PyInstaller 打包时 ``management-prd-vite.spec`` 的 ``icon='app-icon.ico'``
引用本脚本产物。PNG 由设计师产出（2048×2048 RGBA），本脚本将其重采样为
Windows 标准图标尺寸并打包进单个 .ico。

用法::

    uvx --with pillow python scripts/build_ico.py
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image

# Windows 标准图标尺寸（含 256 超大图标、48/32 经典、16 任务栏/favicon）。
ICON_SIZES: tuple[int, ...] = (16, 24, 32, 48, 64, 128, 256)

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "app-icon.png"
OUTPUT = ROOT / "app-icon.ico"


def main() -> int:
    if not SOURCE.exists():
        raise SystemExit(f"找不到源文件: {SOURCE}")

    with Image.open(SOURCE) as im:
        im.load()
        # 强制 RGBA，保证小尺寸缩放后边缘干净。
        src = im.convert("RGBA")
        # ICO 写入时 Pillow 会按 sizes 自动从源图重采样。
        src.save(
            OUTPUT,
            format="ICO",
            sizes=[(s, s) for s in ICON_SIZES],
        )

    print(f"已生成 {OUTPUT}（尺寸 {ICON_SIZES}，源 {src.size[0]}×{src.size[1]}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
