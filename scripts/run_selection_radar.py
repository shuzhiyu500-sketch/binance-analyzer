#!/usr/bin/env python3
"""Authorized/manual-data V1.1 pipeline for the menswear knitwear selection radar.

This program deliberately has no web collector. It imports data supplied by an
authorized API export or a human, preserves every observation, and renders a
local selection pool that can be opened in a browser.
"""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import html
import json
import shutil
import sqlite3
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

REQUIRED = {"product_id", "product_name", "platform", "product_url", "shop_name", "price", "keyword", "source", "observed_at"}
OPTIONAL = {"image_url", "local_image_path", "sales_signal", "review_count", "published_at"}
FIELDS = REQUIRED | OPTIONAL


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat()


def parse_time(value: str) -> str:
    if not value:
        raise ValueError("observed_at is required")
    parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("observed_at must include a timezone, e.g. 2026-09-03T09:00:00+08:00")
    return parsed.astimezone(dt.timezone.utc).replace(microsecond=0).isoformat()


def nullable_number(value: Any, field: str) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} must be numeric or blank: {value!r}") from exc


def load_rows(path: Path) -> list[dict[str, str]]:
    if path.suffix.lower() == ".csv":
        with path.open(encoding="utf-8-sig", newline="") as handle:
            rows = list(csv.DictReader(handle))
    elif path.suffix.lower() == ".json":
        loaded = json.loads(path.read_text(encoding="utf-8"))
        rows = loaded["items"] if isinstance(loaded, dict) and "items" in loaded else loaded
        if not isinstance(rows, list) or not all(isinstance(row, dict) for row in rows):
            raise ValueError("JSON must be an array of objects, or an object containing an items array")
    else:
        raise ValueError("Only CSV and JSON are supported in V1.1. Export Excel as UTF-8 CSV first.")
    if not rows:
        return []
    missing_headers = REQUIRED - set(rows[0])
    if missing_headers:
        raise ValueError("missing required columns: " + ", ".join(sorted(missing_headers)))
    clean = []
    for line, raw in enumerate(rows, start=2):
        row = {key: str(raw.get(key, "")).strip() for key in FIELDS}
        absent = [key for key in REQUIRED if not row[key]]
        if absent:
            raise ValueError(f"row {line}: missing required values: {', '.join(sorted(absent))}")
        row["observed_at"] = parse_time(row["observed_at"])
        if row["published_at"]:
            row["published_at"] = parse_time(row["published_at"])
        row["price"] = nullable_number(row["price"], "price")
        if row["price"] is None or row["price"] < 0:
            raise ValueError(f"row {line}: price is required and must be non-negative")
        row["sales_signal"] = nullable_number(row["sales_signal"], "sales_signal")
        row["review_count"] = nullable_number(row["review_count"], "review_count")
        clean.append(row)
    return clean


def connect(path: Path) -> sqlite3.Connection:
    db = sqlite3.connect(path)
    db.row_factory = sqlite3.Row
    db.executescript("""
    CREATE TABLE IF NOT EXISTS products (
      platform TEXT NOT NULL, product_id TEXT NOT NULL, product_name TEXT NOT NULL,
      product_url TEXT NOT NULL, shop_name TEXT NOT NULL, published_at TEXT,
      keyword TEXT NOT NULL, source TEXT NOT NULL, first_seen_at TEXT NOT NULL,
      last_seen_at TEXT NOT NULL, PRIMARY KEY (platform, product_id)
    );
    CREATE TABLE IF NOT EXISTS observations (
      observation_id INTEGER PRIMARY KEY AUTOINCREMENT, platform TEXT NOT NULL,
      product_id TEXT NOT NULL, observed_at TEXT NOT NULL, price REAL NOT NULL,
      sales_signal REAL, review_count REAL, image_url TEXT, local_image_path TEXT,
      source TEXT NOT NULL, raw_file TEXT NOT NULL, imported_at TEXT NOT NULL,
      UNIQUE(platform, product_id, observed_at, source, raw_file)
    );
    """)
    return db


def image_status(row: dict[str, Any]) -> str:
    if row["image_url"]:
        return "URL_SAVED"
    if row["local_image_path"]:
        return "LOCAL_IMAGE_RECORDED" if Path(row["local_image_path"]).is_file() else "LOCAL_PATH_NOT_FOUND"
    return "IMAGE_UNAVAILABLE"


def import_rows(db: sqlite3.Connection, rows: list[dict[str, str]], raw_file: str) -> None:
    now = utc_now()
    for row in rows:
        db.execute("""INSERT INTO products VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(platform,product_id) DO UPDATE SET product_name=excluded.product_name,
            product_url=excluded.product_url, shop_name=excluded.shop_name, keyword=excluded.keyword, source=excluded.source,
            published_at=COALESCE(excluded.published_at, products.published_at), last_seen_at=excluded.last_seen_at""",
            (row["platform"], row["product_id"], row["product_name"], row["product_url"], row["shop_name"],
             row["published_at"] or None, row["keyword"], row["source"], row["observed_at"], row["observed_at"]))
        db.execute("""INSERT OR IGNORE INTO observations
            (platform,product_id,observed_at,price,sales_signal,review_count,image_url,local_image_path,source,raw_file,imported_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (row["platform"], row["product_id"], row["observed_at"], row["price"], row["sales_signal"],
             row["review_count"], row["image_url"] or None, row["local_image_path"] or None, row["source"], raw_file, now))
    db.commit()


def percentile(values: list[float], value: float) -> float:
    if len(values) < 2:
        return 50.0
    return 100 * sum(item <= value for item in values) / len(values)


def weighted(parts: list[tuple[float, float | None]]) -> float | None:
    known = [(weight, value) for weight, value in parts if value is not None]
    if not known:
        return None
    return sum(weight * value for weight, value in known) / sum(weight for weight, _ in known)


def latest_records(db: sqlite3.Connection) -> list[dict[str, Any]]:
    query = """SELECT p.*, o.price, o.sales_signal, o.review_count, o.image_url, o.local_image_path,
      o.observed_at, o.source AS observation_source FROM products p JOIN observations o
      ON p.platform=o.platform AND p.product_id=o.product_id
      WHERE o.observation_id=(SELECT MAX(i.observation_id) FROM observations i
        WHERE i.platform=o.platform AND i.product_id=o.product_id)"""
    records = [dict(row) for row in db.execute(query)]
    for record in records:
        history = [dict(row) for row in db.execute("""SELECT * FROM observations WHERE platform=? AND product_id=?
          AND observed_at < ? ORDER BY observed_at DESC""", (record["platform"], record["product_id"], record["observed_at"]))]
        previous = next((item for item in history if (dt.datetime.fromisoformat(record["observed_at"]) - dt.datetime.fromisoformat(item["observed_at"])).total_seconds() >= 86400), None)
        record["sales_velocity"] = record["review_velocity"] = None
        if previous:
            days = (dt.datetime.fromisoformat(record["observed_at"]) - dt.datetime.fromisoformat(previous["observed_at"])).total_seconds() / 86400
            if record["sales_signal"] is not None and previous["sales_signal"] is not None:
                record["sales_velocity"] = max(0, record["sales_signal"] - previous["sales_signal"]) / days
            if record["review_count"] is not None and previous["review_count"] is not None:
                record["review_velocity"] = max(0, record["review_count"] - previous["review_count"]) / days
        record["observation_count"] = db.execute("SELECT COUNT(*) FROM observations WHERE platform=? AND product_id=?", (record["platform"], record["product_id"])).fetchone()[0]
        record["active_observation_days"] = db.execute("SELECT COUNT(DISTINCT substr(observed_at, 1, 10)) FROM observations WHERE platform=? AND product_id=?", (record["platform"], record["product_id"])).fetchone()[0]
        record["image_status"] = image_status(record)
    return records


def score(records: list[dict[str, Any]]) -> None:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for record in records:
        groups[(record["platform"], record["keyword"])].append(record)
    for group in groups.values():
        metrics = {name: [r[name] for r in group if r[name] is not None] for name in ("sales_signal", "review_count", "sales_velocity", "review_velocity")}
        shops = {item["shop_name"] for item in group}
        listed_ages = []
        for item in group:
            if item["published_at"]:
                listed_ages.append((dt.datetime.fromisoformat(item["observed_at"]) - dt.datetime.fromisoformat(item["published_at"])).total_seconds() / 86400)
        for r in group:
            persistence = min(100.0, 100 * r["active_observation_days"] / 28)
            freshness = None if not r["published_at"] else 100 - percentile(listed_ages, (dt.datetime.fromisoformat(r["observed_at"]) - dt.datetime.fromisoformat(r["published_at"])).total_seconds() / 86400)
            hot = weighted([(0.50, percentile(metrics["sales_signal"], r["sales_signal"]) if r["sales_signal"] is not None else None),
                            (0.25, percentile(metrics["review_count"], r["review_count"]) if r["review_count"] is not None else None),
                            (0.15, percentile(metrics["sales_velocity"], r["sales_velocity"]) if r["sales_velocity"] is not None else None), (0.10, persistence)])
            growth = weighted([(0.55, percentile(metrics["sales_velocity"], r["sales_velocity"]) if r["sales_velocity"] is not None else None),
                               (0.30, percentile(metrics["review_velocity"], r["review_velocity"]) if r["review_velocity"] is not None else None),
                               (0.15, freshness)])
            if r["sales_velocity"] is None and r["review_velocity"] is None: growth = None
            competition = weighted([(0.55, min(100.0, len(group) * 10)), (0.30, min(100.0, len(shops) * 10))])
            fields = ["product_id", "product_url", "product_name", "shop_name", "price", "image_url"]
            missing = [field for field in fields if not r.get(field)]
            if r["sales_signal"] is None and r["review_count"] is None: missing.append("sales_signal_or_review_count")
            if r["observation_count"] < 2: missing.append("second_observation_for_growth")
            completeness = max(0, 100 - (len(missing) * 10))
            opportunity = None if any(field in missing for field in ("product_id", "product_url", "price", "image_url")) else weighted([(0.35, hot), (0.35, growth), (0.15, 100-competition), (0.10, persistence)])
            if opportunity is not None: opportunity *= completeness / 100
            if opportunity is None: stars = "待补证"
            elif opportunity >= 80 and completeness >= 80 and hot >= 65 and growth is not None and growth >= 60 and competition < 70: stars = "★★★★★ 值得重点研究"
            elif opportunity >= 65 and completeness >= 70: stars = "★★★★ 值得观察"
            elif opportunity >= 45: stars = "★★★ 普通"
            elif opportunity >= 25: stars = "★★ 不建议跟"
            else: stars = "★ 高风险"
            r.update(hot_score=hot, growth_score=growth, competition_score=competition, opportunity_score=opportunity,
                     stars=stars, missing_fields=";".join(missing), data_completeness=round(completeness, 2),
                     score_explanation=f"cohort={r['platform']}|{r['keyword']}; observations={r['observation_count']}; active_days={r['active_observation_days']}; sales_velocity={r['sales_velocity']}; review_velocity={r['review_velocity']}; freshness={freshness}")


def write_csv(path: Path, rows: list[dict[str, Any]], columns: list[str]) -> None:
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=columns, extrasaction="ignore")
        writer.writeheader(); writer.writerows(rows)


def render_html(path: Path, records: list[dict[str, Any]], blocked: list[str]) -> None:
    cards = []
    for r in sorted(records, key=lambda item: item["opportunity_score"] if item["opportunity_score"] is not None else -1, reverse=True):
        image_src = r["image_url"] or (r["local_image_path"] if r["image_status"] == "LOCAL_IMAGE_RECORDED" else "")
        image = f'<img src="{html.escape(image_src)}" alt="商品主图">' if image_src else f'<div class="missing">{html.escape(r["image_status"])}</div>'
        value = lambda key: "—" if r[key] is None else f"{r[key]:.1f}"
        cards.append(f"<article>{image}<h2>{html.escape(r['product_name'])}</h2><p>{html.escape(r['stars'])} · ¥{r['price']:.2f}</p><dl><dt>热度</dt><dd>{value('hot_score')}</dd><dt>增长</dt><dd>{value('growth_score')}</dd><dt>竞争</dt><dd>{value('competition_score')}</dd><dt>机会</dt><dd>{value('opportunity_score')}</dd><dt>更新时间</dt><dd>{html.escape(r['observed_at'])}</dd></dl><a href=\"{html.escape(r['product_url'])}\">查看原商品</a><small>来源：{html.escape(r['observation_source'])}<br>缺失：{html.escape(r['missing_fields']) or '无'}</small></article>")
    block = "" if not blocked else "<section class=\"blocked\"><b>BLOCKED</b><br>" + "<br>".join(map(html.escape, blocked)) + "</section>"
    path.write_text(f"<!doctype html><meta charset=utf-8><title>selection_pool</title><style>body{{font-family:system-ui;margin:24px;background:#f7f7f5;color:#222}}main{{display:grid;grid-template-columns:repeat(auto-fill,minmax(260px,1fr));gap:16px}}article,.blocked{{background:white;padding:14px;border-radius:10px;box-shadow:0 1px 4px #ddd}}img,.missing{{width:100%;height:220px;object-fit:cover;background:#eee;display:grid;place-items:center}}h2{{font-size:16px}}dl{{display:grid;grid-template-columns:1fr 1fr}}dt,dd{{margin:3px 0}}small{{display:block;margin-top:12px;color:#666}}.blocked{{border-left:5px solid #b33;margin-bottom:16px}}</style><h1>线上男装针织热销选品池</h1>{block}<main>{''.join(cards) or '<p>尚无已导入商品。</p>'}</main>", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Import authorized/manual selection-radar data and render selection_pool.")
    parser.add_argument("--input", required=True, type=Path, help="UTF-8 CSV or JSON supplied by an authorized source or a human")
    parser.add_argument("--data-dir", type=Path, default=Path("data/runtime"))
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    args = parser.parse_args()
    rows = load_rows(args.input)
    args.data_dir.mkdir(parents=True, exist_ok=True); args.output_dir.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256(args.input.read_bytes()).hexdigest()
    raw_path = args.data_dir / f"raw-{digest[:16]}{args.input.suffix.lower()}"
    if not raw_path.exists(): shutil.copy2(args.input, raw_path)
    db = connect(args.data_dir / "selection_radar.sqlite")
    import_rows(db, rows, str(raw_path))
    records = latest_records(db); score(records)
    obs = [dict(row) for row in db.execute("SELECT platform,product_id,observed_at,price,sales_signal,review_count,image_url,local_image_path,source,raw_file,imported_at FROM observations ORDER BY observed_at")]
    images = [{"platform": r["platform"], "product_id": r["product_id"], "image_url": r["image_url"], "local_image_path": r["local_image_path"], "image_status": r["image_status"], "source": r["observation_source"], "observed_at": r["observed_at"]} for r in records]
    required_real = len(records) >= 30
    with_growth = sum(r["growth_score"] is not None for r in records)
    blocked = ([] if required_real else [f"需要至少 30 个真实、可追溯商品；当前仅 {len(records)} 个。请导入负责人提供的 CSV/JSON。"])
    if not with_growth: blocked.append("没有任何商品具备间隔至少 24 小时的两次观察；请在下次观察后重新导入以计算增长。")
    columns = ["product_id","product_name","platform","product_url","shop_name","image_url","local_image_path","image_status","price","sales_signal","review_count","published_at","keyword","observation_source","observed_at","observation_count","hot_score","growth_score","competition_score","opportunity_score","stars","data_completeness","missing_fields","score_explanation"]
    write_csv(args.output_dir / "normalized_products.csv", records, columns)
    write_csv(args.output_dir / "historical_observations.csv", obs, list(obs[0]) if obs else ["platform","product_id","observed_at","price","sales_signal","review_count","image_url","local_image_path","source","raw_file","imported_at"])
    write_csv(args.output_dir / "image_index.csv", images, ["platform","product_id","image_url","local_image_path","image_status","source","observed_at"])
    write_csv(args.output_dir / "scores.csv", records, ["platform","product_id","hot_score","growth_score","competition_score","opportunity_score","stars","data_completeness","missing_fields","score_explanation"])
    write_csv(args.output_dir / "selection_pool.csv", records, columns)
    report = {"run_at": utc_now(), "input": str(args.input), "raw_copy": str(raw_path), "input_sha256": digest, "unique_products": len(records), "observations": len(obs), "products_with_growth_score": with_growth, "blocked": blocked}
    (args.output_dir / "data_quality_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    render_html(args.output_dir / "selection_pool.html", records, blocked)
    print(json.dumps(report, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    try: raise SystemExit(main())
    except (ValueError, OSError, sqlite3.Error) as error:
        print(f"ERROR: {error}", file=sys.stderr); raise SystemExit(2)
