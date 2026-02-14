#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Generate patent figures.

Priority:
1) Graphviz (dot) auto-layout -> SVG + PNG
2) PIL fallback when dot is unavailable

Quality gate:
- minimum resolution
- minimum file size
- non-empty drawing (not almost all white)
"""

import argparse
import json
import shutil
import subprocess
from pathlib import Path
from typing import Dict, Iterable, List, Tuple

try:
    from PIL import Image, ImageDraw, ImageFont

    PIL_AVAILABLE = True
except Exception:
    PIL_AVAILABLE = False


W, H = 3600, 2400
BG = "white"
FG = "black"

# A4页面与当前docx页边距一致：宽170mm，高257mm；预留图注空间后按245mm控制
FIG_PAGE_W_IN = 170 / 25.4
FIG_PAGE_H_IN = 245 / 25.4


def dot_bin() -> str | None:
    found = shutil.which("dot")
    if found:
        return found
    hints = [
        "C:/Program Files/Graphviz/bin/dot.exe",
        "C:/Program Files (x86)/Graphviz/bin/dot.exe",
    ]
    for h in hints:
        if Path(h).exists():
            return h
    return None


def load_font(size: int):
    if not PIL_AVAILABLE:
        return None
    candidates = [
        "C:/Windows/Fonts/simsun.ttc",
        "C:/Windows/Fonts/simhei.ttf",
        "C:/Windows/Fonts/msyh.ttc",
        "C:/Windows/Fonts/arial.ttf",
    ]
    for p in candidates:
        try:
            return ImageFont.truetype(p, size=size)
        except Exception:
            continue
    return ImageFont.load_default()


FONT_TITLE = load_font(62) if PIL_AVAILABLE else None
FONT_BOX = load_font(36) if PIL_AVAILABLE else None
FONT_REF = load_font(30) if PIL_AVAILABLE else None
FONT_LEGEND = load_font(28) if PIL_AVAILABLE else None


def safe_topic_text(ctx: Dict) -> str:
    topics = (ctx.get("java_analysis", {}).get("kafka_topics", []) or [])[:4]
    if topics:
        return " / ".join(topics)
    return "shot-metadata / wave-data / operation-log / plc-interlock"


def clean_old_outputs(out_dir: Path) -> None:
    for ext in ("*.png", "*.svg", "*.dot"):
        for p in out_dir.glob(ext):
            p.unlink(missing_ok=True)


def png_quality_check(png: Path, min_w: int = 2400, min_h: int = 1600, min_bytes: int = 45000) -> Tuple[bool, str]:
    if not png.exists():
        return False, f"{png.name}: not found"
    size = png.stat().st_size
    if size < min_bytes:
        return False, f"{png.name}: too small ({size} bytes)"
    if not PIL_AVAILABLE:
        return True, "ok-no-pil-check"

    try:
        img = Image.open(png)
        w, h = img.size
        if w < min_w or h < min_h:
            return False, f"{png.name}: low resolution ({w}x{h})"

        gray = img.convert("L")
        sample = gray.resize((320, 220))
        hist = sample.histogram()
        total = sum(hist) or 1
        white = sum(hist[250:256])
        ratio = white / total
        if ratio > 0.992:
            return False, f"{png.name}: almost blank (white ratio {ratio:.3f})"
    except Exception as e:
        return False, f"{png.name}: quality check failed: {e}"
    return True, "ok"


def render_dot(dot_source: str, stem: Path, dpi: int) -> Tuple[bool, str]:
    dbin = dot_bin()
    if not dbin:
        return False, "dot executable not found"

    dot_file = stem.with_suffix(".dot")
    svg_file = stem.with_suffix(".svg")
    png_file = stem.with_suffix(".png")
    dot_file.write_text(dot_source, encoding="utf-8")

    try:
        subprocess.run(
            [dbin, "-Tsvg", f"-Gdpi={dpi}", str(dot_file), "-o", str(svg_file)],
            check=True,
            capture_output=True,
            text=True,
        )
        subprocess.run(
            [dbin, "-Tpng", f"-Gdpi={dpi}", str(dot_file), "-o", str(png_file)],
            check=True,
            capture_output=True,
            text=True,
        )
        return True, "ok"
    except subprocess.CalledProcessError as e:
        msg = (e.stderr or e.stdout or str(e)).strip()
        return False, f"dot render failed: {msg}"


def graphviz_figure1(ctx: Dict) -> str:
    topics = (ctx.get("java_analysis", {}).get("kafka_topics", []) or [])[:4]
    if topics:
        topic_text = "\\n".join(topics)
    else:
        topic_text = "shot-metadata\\nwave-data\\noperation-log\\nplc-interlock"
    return f"""
digraph G {{
  graph [rankdir=TB, splines=ortho, bgcolor=white, fontname="SimSun",
         nodesep=0.40, ranksep=0.62, pad=0.16,
         size="{FIG_PAGE_W_IN:.2f},{FIG_PAGE_H_IN:.2f}", ratio=compress, margin=0.02];
  node  [shape=box, style="solid", color=black, penwidth=2.0,
         fontname="SimSun", fontsize=14, margin="0.10,0.08"];
  edge  [color=black, arrowsize=0.75, penwidth=2.0, arrowhead=normal];
  l1 [shape=plaintext, fontsize=13, label="采集层"];
  l2 [shape=plaintext, fontsize=13, label="消息层"];
  l3 [shape=plaintext, fontsize=13, label="持久化层"];
  l4 [shape=plaintext, fontsize=13, label="服务与展示层"];

  layer_w1 [label="", shape=box, width=6.2, height=0.01, style=invis];
  fsrc [label="文件数据源\\n(TDMS/日志)\\n(101)"];
  nsrc [label="网络数据源\\n(Kafka/TCP)\\n(102)"];
  norm [label="数据标准化处理\\n(110)"];

  layer_w2 [label="", shape=box, width=6.2, height=0.01, style=invis];
  mq [label="消息中间件主题\\n{topic_text}\\n(120)"];

  layer_w3 [label="", shape=box, width=6.2, height=0.01, style=invis];
  mysql [label="关系型数据库\\n(MySQL/H2)\\n(130)"];
  influx [label="时序数据库\\n(InfluxDB)\\n(131)"];

  layer_w4 [label="", shape=box, width=6.2, height=0.01, style=invis];
  api [label="服务接口模块\\n(REST API)\\n(140)"];
  ws  [label="实时推送模块\\n(WebSocket)\\n(141)"];
  ui  [label="可视化终端\\n(150)"];

  {{rank=same; l1; layer_w1; fsrc; nsrc; norm;}}
  {{rank=same; l2; layer_w2; mq;}}
  {{rank=same; l3; layer_w3; mysql; influx;}}
  {{rank=same; l4; layer_w4; api; ws; ui;}}

  layer_w1 -> fsrc [style=invis];
  layer_w1 -> nsrc [style=invis];
  layer_w1 -> norm [style=invis];
  layer_w2 -> mq [style=invis];
  layer_w3 -> mysql [style=invis];
  layer_w3 -> influx [style=invis];
  layer_w4 -> api [style=invis];
  layer_w4 -> ws [style=invis];
  layer_w4 -> ui [style=invis];
  l1 -> l2 -> l3 -> l4 [style=invis, weight=30];

  fsrc -> norm;
  nsrc -> norm;

  norm -> mq;
  mq -> mysql;
  mq -> influx;
  mysql -> api;
  influx -> api;
  api -> ws;
  ws -> ui;

  legend [shape=box, style=solid, penwidth=2.0, fontsize=12,
          label="附图标记说明\\l101 文件数据源\\l102 网络数据源\\l110 标准化处理\\l120 消息中间件\\l130 关系型数据库\\l131 时序数据库\\l140 服务接口\\l141 实时推送\\l150 可视化终端\\l"];
}}
"""


def _flow_style(step_labels: List[str]) -> Tuple[int, float, float, str]:
    max_len = max((len(x) for x in step_labels), default=0)
    count = len(step_labels)
    if max_len >= 18 or count >= 10:
        return 12, 0.30, 0.44, "0.08,0.06"
    if max_len >= 14 or count >= 8:
        return 13, 0.34, 0.50, "0.09,0.07"
    return 14, 0.38, 0.58, "0.10,0.08"


def graphviz_figure2(_ctx: Dict) -> str:
    labels = [
        "接收文件源与网络源工业数据",
        "解析并执行统一建模",
        "按主题发送至消息中间件",
        "分主题消费并分层存储",
        "提供查询与同步触发接口",
        "推送处理状态与结果",
        "主数据源可用？",
        "是：按主数据源处理",
        "否：切换备用数据源",
        "继续执行S102-S106",
    ]
    fz, nsep, rsep, margin = _flow_style(labels)
    return """
digraph G {
  graph [rankdir=TB, splines=ortho, bgcolor=white, fontname="SimSun", charset="UTF-8",
         nodesep=%0.2f, ranksep=%0.2f, pad=0.16,
         size="%0.2f,%0.2f", ratio=compress, margin=0.02];
  node  [shape=box, style="solid", color=black, penwidth=2.0,
         fontname="SimSun", fontsize=%d, margin="%s"];
  edge  [color=black, arrowsize=0.75, penwidth=2.0, arrowhead=normal, fontname="SimSun", fontsize=%d];

  s101 [label="接收文件源与网络源工业数据\\n(S101)"];
  s102 [label="解析并执行统一建模\\n(S102)"];
  s103 [label="按主题发送至消息中间件\\n(S103)"];
  s104 [label="分主题消费并分层存储\\n(S104)"];
  s105 [label="提供查询与同步触发接口\\n(S105)"];
  s106 [label="推送处理状态与结果\\n(S106)"];
  dec  [shape=diamond, style=solid, penwidth=2.0, label="主数据源可用？\\n(S201)"];
  yesn [label="是：按主数据源处理\\n(S202)"];
  non  [label="否：切换备用数据源\\n(S203)"];
  s204 [label="继续执行S102-S106\\n(S204)"];

  s101 -> s102 -> s103 -> s104 -> s105 -> s106;
  s103 -> dec;
  dec -> yesn;
  dec -> non;
  yesn -> s104;
  non  -> s204 -> s104;

  legend [shape=box, style=solid, penwidth=2.0, fontsize=12,
          label="附图标记说明\\lS101-S106 主流程步骤\\lS201 可用性判断\\lS202-S204 回退分支\\l"];
}
""" % (nsep, rsep, FIG_PAGE_W_IN, FIG_PAGE_H_IN, fz, margin, fz)


def graphviz_figure3(ctx: Dict) -> str:
    dual = bool(ctx.get("feature_flags", {}).get("dual_data_source", False))
    optional = """
  sw [label="主备切换模块\\n(207)"];
  sw -> core;
""" if dual else ""
    return f"""
digraph G {{
  graph [rankdir=LR, splines=ortho, bgcolor=white, fontname="SimSun",
         nodesep=0.45, ranksep=0.60, pad=0.16,
         size="{FIG_PAGE_W_IN:.2f},{FIG_PAGE_H_IN:.2f}", ratio=compress, margin=0.02];
  node  [shape=box, style="solid", color=black, penwidth=2.0,
         fontname="SimSun", fontsize=14, margin="0.10,0.08"];
  edge  [color=black, arrowsize=0.75, penwidth=2.0, arrowhead=normal];

  core [label="双数据源波形数据处理系统\\n(200)", width=4.2, height=1.0];

  in1 [label="数据接入模块\\n(201)"];
  in2 [label="数据标准化模块\\n(202)"];
  in3 [label="消息处理模块\\n(203)"];
  out1 [label="分层存储模块\\n(204)"];
  out2 [label="服务接口模块\\n(205)"];
  out3 [label="实时推送模块\\n(206)"];

  in1 -> core; in2 -> core; in3 -> core;
  core -> out1; core -> out2; core -> out3;
{optional}
  {{rank=same; in1; in2; in3; core; out1; out2; out3;}}

  legend [shape=box, style=solid, penwidth=2.0, fontsize=12,
          label="附图标记说明\\l200 系统主体\\l201-203 输入处理链路\\l204-206 输出服务链路\\l207 主备切换控制\\l"];
}}
"""


def try_generate_graphviz(ctx: Dict, out_dir: Path) -> bool:
    specs = [
        ("figure1_system_arch", graphviz_figure1(ctx)),
        ("figure2_pipeline_flow", graphviz_figure2(ctx)),
        ("figure3_module_block", graphviz_figure3(ctx)),
    ]
    dpi = 650
    for stem_name, dot_src in specs:
        ok, msg = render_dot(dot_src, out_dir / stem_name, dpi=dpi)
        if not ok:
            print(f"[WARN] Graphviz failed for {stem_name}: {msg}")
            return False

    # quality gate + one retry at higher dpi
    for stem_name, dot_src in specs:
        png = (out_dir / stem_name).with_suffix(".png")
        ok, msg = png_quality_check(png)
        if not ok:
            print(f"[WARN] Quality gate failed for {png.name}: {msg}; retry with higher dpi")
            ok2, msg2 = render_dot(dot_src, out_dir / stem_name, dpi=820)
            if not ok2:
                print(f"[WARN] Retry failed for {stem_name}: {msg2}")
                return False
            ok3, msg3 = png_quality_check(png)
            if not ok3:
                print(f"[WARN] Quality still failed for {png.name}: {msg3}")
                return False
    print("engine=graphviz")
    return True


def new_canvas(title: str):
    img = Image.new("RGB", (W, H), BG)
    draw = ImageDraw.Draw(img)
    if title.strip():
        draw.text((90, 52), title, fill=FG, font=FONT_TITLE)
        draw.line((90, 145, W - 90, 145), fill=FG, width=4)
    return img, draw


def wrap_text(draw: ImageDraw.ImageDraw, text: str, font, max_w: int) -> List[str]:
    blocks = text.split("\n")
    out: List[str] = []
    for block in blocks:
        cur = ""
        for ch in block:
            candidate = cur + ch
            bw = draw.textbbox((0, 0), candidate, font=font)[2]
            if bw <= max_w:
                cur = candidate
            else:
                if cur:
                    out.append(cur)
                cur = ch
        out.append(cur if cur else "")
    return out


def draw_rect(draw: ImageDraw.ImageDraw, box: Tuple[int, int, int, int], text: str, ref: str):
    x1, y1, x2, y2 = box
    draw.rectangle(box, outline=FG, width=5, fill=BG)
    lines = wrap_text(draw, text, FONT_BOX, x2 - x1 - 60)
    lh = 44
    total_h = max(lh * len(lines), lh)
    sy = y1 + (y2 - y1 - total_h) // 2
    for ln in lines:
        tw = draw.textbbox((0, 0), ln, font=FONT_BOX)[2]
        tx = x1 + (x2 - x1 - tw) // 2
        draw.text((tx, sy), ln, fill=FG, font=FONT_BOX)
        sy += lh

    rw, rh = 128, 56
    rx1, ry1 = x2 - rw - 8, y1 + 8
    draw.rectangle((rx1, ry1, rx1 + rw, ry1 + rh), outline=FG, width=3, fill=BG)
    tw = draw.textbbox((0, 0), ref, font=FONT_REF)[2]
    draw.text((rx1 + (rw - tw) // 2, ry1 + 10), ref, fill=FG, font=FONT_REF)


def draw_diamond(draw: ImageDraw.ImageDraw, center: Tuple[int, int], w: int, h: int, text: str, ref: str):
    cx, cy = center
    pts = [(cx, cy - h // 2), (cx + w // 2, cy), (cx, cy + h // 2), (cx - w // 2, cy)]
    draw.polygon(pts, outline=FG, width=5, fill=BG)
    lines = wrap_text(draw, text, FONT_BOX, w - 100)
    lh = 40
    sy = cy - (len(lines) * lh) // 2
    for ln in lines:
        tw = draw.textbbox((0, 0), ln, font=FONT_BOX)[2]
        draw.text((cx - tw // 2, sy), ln, fill=FG, font=FONT_BOX)
        sy += lh

    draw.rectangle((cx + w // 2 + 12, cy - 44, cx + w // 2 + 154, cy + 12), outline=FG, width=3, fill=BG)
    tw = draw.textbbox((0, 0), ref, font=FONT_REF)[2]
    draw.text((cx + w // 2 + 12 + (142 - tw) // 2, cy - 34), ref, fill=FG, font=FONT_REF)


def arrow(draw: ImageDraw.ImageDraw, p1: Tuple[int, int], p2: Tuple[int, int], width: int = 5):
    x1, y1 = p1
    x2, y2 = p2
    draw.line((x1, y1, x2, y2), fill=FG, width=width)
    if abs(x2 - x1) >= abs(y2 - y1):
        if x2 >= x1:
            tri = [(x2, y2), (x2 - 20, y2 - 10), (x2 - 20, y2 + 10)]
        else:
            tri = [(x2, y2), (x2 + 20, y2 - 10), (x2 + 20, y2 + 10)]
    else:
        if y2 >= y1:
            tri = [(x2, y2), (x2 - 10, y2 - 20), (x2 + 10, y2 - 20)]
        else:
            tri = [(x2, y2), (x2 - 10, y2 + 20), (x2 + 10, y2 + 20)]
    draw.polygon(tri, fill=FG, outline=FG)


def draw_legend(draw: ImageDraw.ImageDraw, items: Iterable[Tuple[str, str]], x: int, y: int):
    draw.text((x, y), "附图标记说明：", fill=FG, font=FONT_LEGEND)
    y += 44
    for k, v in items:
        draw.text((x, y), f"{k} - {v}", fill=FG, font=FONT_LEGEND)
        y += 36


def pil_figure1(ctx: Dict, out_png: Path):
    topics = safe_topic_text(ctx)
    img, draw = new_canvas("")
    draw.text((130, 335), "采集层", fill=FG, font=FONT_LEGEND)
    draw.text((130, 760), "消息层", fill=FG, font=FONT_LEGEND)
    draw.text((130, 1180), "持久化层", fill=FG, font=FONT_LEGEND)
    draw.text((130, 1600), "服务与展示层", fill=FG, font=FONT_LEGEND)

    draw_rect(draw, (240, 305, 900, 505), "文件数据源\n(TDMS/日志)", "101")
    draw_rect(draw, (980, 305, 1640, 505), "网络数据源\n(Kafka/TCP)", "102")
    draw_rect(draw, (1740, 305, 2500, 505), "数据标准化处理", "110")
    draw_rect(draw, (680, 720, 2820, 910), "消息中间件主题：" + topics, "120")
    draw_rect(draw, (620, 1130, 1540, 1335), "关系型数据库", "130")
    draw_rect(draw, (1820, 1130, 2740, 1335), "时序数据库", "131")
    draw_rect(draw, (520, 1550, 1530, 1755), "服务接口模块", "140")
    draw_rect(draw, (1760, 1550, 2770, 1755), "实时推送模块", "141")
    draw_rect(draw, (2860, 1550, 3300, 1755), "可视化终端", "150")

    arrow(draw, (900, 405), (980, 405))
    arrow(draw, (1640, 405), (1740, 405))
    arrow(draw, (2120, 505), (1740, 720))
    arrow(draw, (1750, 910), (1080, 1130))
    arrow(draw, (1820, 910), (2260, 1130))
    arrow(draw, (1080, 1335), (980, 1550))
    arrow(draw, (2260, 1335), (2260, 1550))
    arrow(draw, (2770, 1650), (2860, 1650))

    draw_legend(
        draw,
        [
            ("101", "文件数据源"),
            ("102", "网络数据源"),
            ("110", "标准化处理"),
            ("120", "消息中间件"),
            ("130", "关系型数据库"),
            ("131", "时序数据库"),
            ("140", "服务接口模块"),
            ("141", "实时推送模块"),
            ("150", "可视化终端"),
        ],
        120,
        1880,
    )
    img.save(out_png, format="PNG", dpi=(600, 600))


def pil_figure2(_ctx: Dict, out_png: Path):
    img, draw = new_canvas("")
    steps = [
        ("接收文件源与网络源工业数据", "S101"),
        ("解析并执行统一建模", "S102"),
        ("按主题发送至消息中间件", "S103"),
        ("分主题消费并分层存储", "S104"),
        ("提供查询与同步触发接口", "S105"),
        ("推送处理状态与结果", "S106"),
    ]
    max_len = max(len(t) for t, _ in steps)
    long_flow = len(steps) >= 6 and max_len >= 10
    x1, x2 = (360, 1360) if long_flow else (320, 1420)
    box_h = 180 if long_flow else 210
    gap = 90 if long_flow else 100
    y = 260
    centers = []
    bottoms = []
    for txt, ref in steps:
        draw_rect(draw, (x1, y, x2, y + box_h), txt, ref)
        centers.append((x1 + x2) // 2)
        bottoms.append(y + box_h)
        y += box_h + gap
    for i in range(len(bottoms) - 1):
        arrow(draw, (centers[i], bottoms[i]), (centers[i + 1], bottoms[i] + gap))

    draw_diamond(draw, (2120, 980), 820, 430, "主数据源可用？", "S201")
    draw_rect(draw, (2540, 700, 3340, 900), "是：按主数据源处理", "S202")
    draw_rect(draw, (2540, 1060, 3340, 1260), "否：切换备用数据源", "S203")
    draw_rect(draw, (2540, 1420, 3340, 1620), "继续执行S102-S106", "S204")
    arrow(draw, (1420, 980), (1710, 980))
    arrow(draw, (2520, 900), (2540, 800))
    arrow(draw, (2520, 1060), (2540, 1160))
    arrow(draw, (2940, 900), (2940, 1060))
    arrow(draw, (2940, 1260), (2940, 1420))
    arrow(draw, (2540, 1520), (1420, 1520))

    draw_legend(draw, [("S101-S106", "主流程"), ("S201", "可用性判断"), ("S202-S204", "回退分支")], 120, 2030)
    img.save(out_png, format="PNG", dpi=(600, 600))


def pil_figure3(ctx: Dict, out_png: Path):
    ff = ctx.get("feature_flags", {})
    img, draw = new_canvas("")
    draw_rect(draw, (1300, 980, 2300, 1420), "双数据源波形数据处理系统", "200")

    modules = [
        ("201", "数据接入模块", (220, 360, 1060, 620)),
        ("202", "数据标准化模块", (220, 720, 1060, 980)),
        ("203", "消息处理模块", (220, 1080, 1060, 1340)),
        ("204", "分层存储模块", (2540, 360, 3380, 620)),
        ("205", "服务接口模块", (2540, 720, 3380, 980)),
        ("206", "实时推送模块", (2540, 1080, 3380, 1340)),
    ]
    if ff.get("dual_data_source"):
        modules.append(("207", "主备切换模块", (1300, 1620, 2300, 1860)))

    for ref, txt, box in modules:
        draw_rect(draw, box, txt, ref)
        cx = (box[0] + box[2]) // 2
        cy = (box[1] + box[3]) // 2
        c2x = (1300 + 2300) // 2
        c2y = (980 + 1420) // 2
        arrow(draw, (cx, cy), (c2x, c2y))

    draw_legend(
        draw,
        [("200", "系统主体"), ("201-203", "输入处理链路"), ("204-206", "输出服务链路"), ("207", "主备切换控制")],
        120,
        1960,
    )
    img.save(out_png, format="PNG", dpi=(600, 600))


def generate_with_pil(ctx: Dict, out_dir: Path) -> bool:
    if not PIL_AVAILABLE:
        print("[ERROR] PIL is not available and Graphviz is unavailable")
        return False
    pil_figure1(ctx, out_dir / "figure1_system_arch.png")
    pil_figure2(ctx, out_dir / "figure2_pipeline_flow.png")
    pil_figure3(ctx, out_dir / "figure3_module_block.png")

    for name in ("figure1_system_arch.png", "figure2_pipeline_flow.png", "figure3_module_block.png"):
        ok, msg = png_quality_check(out_dir / name)
        if not ok:
            print(f"[ERROR] PIL quality gate failed for {name}: {msg}")
            return False
    print("engine=pil-fallback")
    return True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--context", required=True)
    ap.add_argument("--out-dir", required=True)
    args = ap.parse_args()

    ctx = json.loads(Path(args.context).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    clean_old_outputs(out_dir)

    used_graphviz = False
    if dot_bin():
        used_graphviz = try_generate_graphviz(ctx, out_dir)

    if not used_graphviz:
        if dot_bin() is None:
            print("[WARN] dot executable not found; fallback to PIL renderer")
        ok = generate_with_pil(ctx, out_dir)
        if not ok:
            raise SystemExit(2)

    print(f"Wrote figures to {out_dir}")


if __name__ == "__main__":
    main()
