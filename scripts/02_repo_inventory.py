#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import argparse
import json
import os
import re
from collections import Counter
from pathlib import Path

SKIP_DIRS = {
    ".git",
    "node_modules",
    "dist",
    "build",
    "target",
    ".venv",
    "venv",
    ".idea",
    ".vscode",
    ".mvn",
    ".gradle",
    "__pycache__",
}

KEY_ANN = {
    "RestController",
    "Controller",
    "Service",
    "Repository",
    "Configuration",
    "KafkaListener",
    "Scheduled",
    "GetMapping",
    "PostMapping",
    "PutMapping",
    "DeleteMapping",
    "RequestMapping",
}


def safe_read_text(p: Path, max_chars: int = 250000) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="ignore")[:max_chars]
    except Exception:
        return ""


def extract_endpoints(text: str):
    cls_prefix = ""
    m = re.search(r'@RequestMapping\s*\(\s*(?:value\s*=\s*)?"([^"]+)"', text)
    if m:
        cls_prefix = m.group(1).strip()

    out = []
    patterns = [
        ("GET", r'@GetMapping\s*\(\s*(?:value\s*=\s*)?"([^"]+)"'),
        ("POST", r'@PostMapping\s*\(\s*(?:value\s*=\s*)?"([^"]+)"'),
        ("PUT", r'@PutMapping\s*\(\s*(?:value\s*=\s*)?"([^"]+)"'),
        ("DELETE", r'@DeleteMapping\s*\(\s*(?:value\s*=\s*)?"([^"]+)"'),
        ("PATCH", r'@PatchMapping\s*\(\s*(?:value\s*=\s*)?"([^"]+)"'),
    ]
    for method, pat in patterns:
        for mm in re.finditer(pat, text):
            route = (mm.group(1) or "").strip()
            if not route:
                continue
            if cls_prefix and route.startswith("/"):
                full = f"{cls_prefix.rstrip('/')}{route}"
            else:
                full = route
            out.append(f"{method} {full}")
    return out


def normalize_ext_rank(ext_counter: Counter):
    code_priority = {
        ".java",
        ".py",
        ".js",
        ".ts",
        ".go",
        ".rs",
        ".cs",
        ".cpp",
        ".c",
        ".h",
        ".kt",
        ".scala",
    }
    ordered = sorted(ext_counter.items(), key=lambda x: (-x[1], x[0]))
    top = []
    for ext, _ in ordered:
        if not ext:
            continue
        if ext in code_priority:
            top.append(ext)
    for ext, _ in ordered:
        if ext and ext not in top:
            top.append(ext)
    return top[:10]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--out", required=True)
    args = ap.parse_args()

    repo = Path(args.repo).resolve()
    out = Path(args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)

    exts = Counter()
    readme = ""
    dep_files = []
    entry_candidates = []
    docs_files = []
    java_files = []

    ann_counter = Counter()
    pkg_counter = Counter()
    class_names = []
    controller_files = []
    service_files = []
    repository_files = []
    datasource_files = []
    kafka_topic_refs = Counter()
    endpoints = []
    core_classes = []
    keyword_hits = Counter()

    for root, dirs, files in os.walk(repo):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for fn in files:
            p = Path(root) / fn
            rel = p.relative_to(repo)
            if rel.parts and rel.parts[0] in SKIP_DIRS:
                continue

            low = str(rel).replace("\\", "/").lower()
            if low.startswith("docker/data/"):
                continue

            exts[p.suffix.lower()] += 1

            if low in {"readme.md", "readme.rst", "readme.txt"} and not readme:
                readme = safe_read_text(p, 120000)

            if low.startswith("docs/") and p.suffix.lower() in {".md", ".rst", ".txt"}:
                if len(docs_files) < 300:
                    docs_files.append(str(rel))

            if fn in {
                "requirements.txt",
                "pyproject.toml",
                "poetry.lock",
                "package.json",
                "pom.xml",
                "build.gradle",
                "go.mod",
                "cargo.toml",
                "application.yml",
            }:
                dep_files.append(str(rel))

            if fn.lower() in {
                "main.py",
                "app.py",
                "server.py",
                "index.js",
                "main.go",
                "main.rs",
                "application.java",
            }:
                if len(entry_candidates) < 50:
                    entry_candidates.append(str(rel))

            if p.suffix.lower() != ".java":
                continue

            java_files.append(str(rel))
            text = safe_read_text(p)
            if not text:
                continue

            m_pkg = re.search(r"^\s*package\s+([a-zA-Z0-9_.]+)\s*;", text, re.M)
            if m_pkg:
                pkg_counter[m_pkg.group(1)] += 1

            for mm in re.finditer(r"\b(class|interface|enum)\s+([A-Za-z_][A-Za-z0-9_]*)", text):
                class_names.append(mm.group(2))

            for mm in re.finditer(r"@([A-Za-z_][A-Za-z0-9_]*)", text):
                ann = mm.group(1)
                if ann in KEY_ANN:
                    ann_counter[ann] += 1

            rels = str(rel).replace("\\", "/")
            if "controller/" in low or "@RestController" in text:
                controller_files.append(rels)
            if "service/" in low or "@Service" in text:
                service_files.append(rels)
            if "repository/" in low or "@Repository" in text:
                repository_files.append(rels)
            if "datasource/" in low or "DataSource" in fn:
                datasource_files.append(rels)

            ep = extract_endpoints(text)
            if ep:
                endpoints.extend(ep[:30])

            for mm in re.finditer(r"\$\{app\.kafka\.topic\.[^:}]+:([^}]+)\}", text):
                topic = mm.group(1).strip()
                if topic:
                    kafka_topic_refs[topic] += 1

            for cls in [
                "DataPipelineService",
                "FileDataSource",
                "NetworkDataSource",
                "DataProducer",
                "DataConsumer",
                "KafkaController",
                "InfluxDBService",
                "WebSocketController",
            ]:
                if cls in text:
                    core_classes.append(cls)

            for kw in [
                "KafkaListener",
                "WebSocket",
                "InfluxDB",
                "MySQL",
                "fallback",
                "syncShotToKafka",
                "syncAllShotsToKafka",
            ]:
                if kw in text:
                    keyword_hits[kw] += 1

    readme_lc = readme.lower()
    feature_flags = {
        "dual_data_source": (
            ("filedatasource" in readme_lc and "networkdatasource" in readme_lc)
            or ("FileDataSource" in class_names and "NetworkDataSource" in class_names)
        ),
        "kafka_pipeline": (
            ann_counter.get("KafkaListener", 0) > 0
            or keyword_hits.get("syncShotToKafka", 0) > 0
            or "kafka" in readme_lc
        ),
        "hybrid_storage_mysql_influx": (
            ("mysql" in readme_lc and "influx" in readme_lc)
            or (keyword_hits.get("MySQL", 0) > 0 and keyword_hits.get("InfluxDB", 0) > 0)
        ),
        "rest_api": ann_counter.get("RestController", 0) > 0 or len(controller_files) > 0,
        "websocket_push": ("websocket" in readme_lc) or keyword_hits.get("WebSocket", 0) > 0,
        "scheduled_task": ann_counter.get("Scheduled", 0) > 0,
        "fallback_switching": ("fallback" in readme_lc) or keyword_hits.get("fallback", 0) > 0,
    }

    technical_points = []
    if feature_flags["dual_data_source"]:
        technical_points.append("主备双数据源接入与运行时切换机制")
    if feature_flags["kafka_pipeline"]:
        technical_points.append("文件/网络数据经消息队列进行异步解耦处理")
    if feature_flags["hybrid_storage_mysql_influx"]:
        technical_points.append("结构化数据与时序数据分层存储")
    if feature_flags["rest_api"]:
        technical_points.append("基于REST接口的数据查询与同步触发")
    if feature_flags["websocket_push"]:
        technical_points.append("面向前端展示的实时推送机制")
    if feature_flags["scheduled_task"]:
        technical_points.append("定时任务驱动的数据同步策略")

    ctx = {
        "repo_name": repo.name,
        "repo_path": str(repo),
        "file_extension_counts": dict(exts),
        "languages_by_extension_top10": normalize_ext_rank(exts),
        "readme_excerpt": readme[:12000],
        "dependency_files": dep_files[:80],
        "docs_files": docs_files[:300],
        "entry_candidates": entry_candidates[:50],
        "java_analysis": {
            "java_file_count": len(java_files),
            "java_files_sample": java_files[:80],
            "package_top20": [p for p, _ in pkg_counter.most_common(20)],
            "annotation_counts": dict(ann_counter),
            "controller_files": controller_files[:80],
            "service_files": service_files[:120],
            "repository_files": repository_files[:120],
            "datasource_files": datasource_files[:80],
            "class_samples": sorted(set(class_names))[:200],
            "endpoint_samples": sorted(set(endpoints))[:120],
            "kafka_topics": [t for t, _ in kafka_topic_refs.most_common(20)],
            "core_classes": sorted(set(core_classes)),
            "keyword_hits": dict(keyword_hits),
        },
        "feature_flags": feature_flags,
        "technical_points": technical_points,
    }
    out.write_text(json.dumps(ctx, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
