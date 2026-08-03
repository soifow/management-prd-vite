"""生产库 v4 迁移损坏恢复脚本

恢复两个问题：
1. requirement_modules / bug_modules 被 DROP TABLE CASCADE 清空（模块关联全丢）
2. requirement_subitems 被 CASCADE 清空（子需求全丢）+ 被合并的 content 被覆盖为 feature 名

策略：
- 从 db 字节残留中提取原始多行编号 content 块
- 按 date 匹配到现有 requirements
- 生成子需求 + 回填模块关联
"""

import json
import re
import shutil
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, date
from pathlib import Path
from uuid import uuid4

DB_PATH = Path(r"C:\Users\soifow\Documents\工作文档\智能室需求\management-prd-storage\requment.db")
REPORT_PATH = Path(r"C:\Users\soifow\Documents\工作文档\智能室需求\management-prd-storage\recovery_report.json")

# ── 编号模式 ──
LIST_RE = re.compile(r"^\s*(\d+)[.、]\s*")

def extract_content_blocks(db_path: Path) -> list[str]:
    """从 db 字节中提取被覆盖/删除的原始 content 块（含多行编号）。

    策略：db 字节里残留的 content 往往不含换行（free page 压缩），所以用
    ``(?=\\d+[.、])`` lookahead 切分，不依赖 \\n。对每个大块检查是否含 ≥2 个
    编号段，是则视为一条原始 content 块（从 1. 到最后一个数字编号段）。
    """
    data = open(db_path, 'rb').read()
    text = data.decode('utf-8', errors='ignore')
    # 按非文本字符切大块
    chunks = re.split(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', text)

    recovered: list[str] = []
    seen = set()

    for ch in chunks:
        if not ch or len(ch) < 10:
            continue
        # 用 lookahead 切分：以 1./2./3. 等开头的段
        parts = re.split(r'(?=\d+[.、])', ch)
        # 收集每个编号段
        num_segs = []
        for p in parts:
            p = p.strip()
            m = LIST_RE.match(p)
            if m:
                num_segs.append((int(m.group(1)), p))
        if len(num_segs) < 2:
            continue
        # 必须从 1 开始（原始 list 形态从 1 编号）
        if num_segs[0][0] != 1:
            continue
        # 取连续编号段
        segments = []
        expected = 1
        for num, p in num_segs:
            if num == expected:
                text_seg = LIST_RE.sub('', p, count=1).strip()
                # 清理尾部 timestamp/id 残留
                text_seg = re.sub(r'\d{4}-\d{2}-\d{2}T[\d:.]+Z?$', '', text_seg).strip()
                text_seg = re.sub(r'[A-Fa-f0-9]{8,}.*$', '', text_seg).strip()
                if text_seg and len(text_seg) > 1:
                    segments.append(f"{num}. {text_seg}")
                    expected += 1
            elif num > expected:
                break
        if len(segments) >= 2:
            block = "\n".join(segments)
            key = block[:120]
            if key not in seen:
                seen.add(key)
                recovered.append(block)

    return recovered


def parse_blocks(blocks: list[str]) -> list[dict]:
    """解析每个 content 块为结构化记录：{items: [(num, text), ...], raw: str}"""
    parsed = []
    for raw in blocks:
        items = []
        for part in re.split(r'(?=\d+[.、])', raw):
            part = part.strip()
            m = LIST_RE.match(part)
            if m:
                num = int(m.group(1))
                text = LIST_RE.sub('', part, count=1).strip()
                # 清理尾部 timestamp 残留
                text = re.sub(r'\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(\.\d+)?Z?$', '', text).strip()
                if text and len(text) > 1:
                    items.append({"num": num, "text": text})
        if len(items) >= 2:
            parsed.append({"items": items, "raw": raw})
    return parsed


def match_to_requirements(conn, parsed_blocks: list[dict]) -> dict:
    """把解析出的 content 块按 date 匹配到现有 requirements。

    策略：
    1. 每个块的第一行文本在 requirements 的 content 中搜索（已被覆盖为 feature 名）
    2. 按 feature 名做模糊匹配（取公共子串长度最大的）
    3. 按 date 过滤（块中时间戳片段）
    4. 手动 fallback：无法自动匹配的输出供人工审核

    Returns: {requirement_id: [subitem_texts...]}
    """
    conn.row_factory = sqlite3.Row
    reqs = conn.execute(
        "SELECT id, project_id, feature, content, date, status FROM requirements ORDER BY date, id"
    ).fetchall()

    # 建立 feature -> requirements 索引
    feat_map: dict[str, list] = defaultdict(list)
    for r in reqs:
        feat_map[r["feature"]].append(r)

    # 提取块中可能的时间戳信息
    ts_re = re.compile(r'(\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2})')
    date_re = re.compile(r'(20\d{2}-\d{2}-\d{2})')

    matched: dict[str, list[str]] = defaultdict(list)
    unmatched: list[dict] = []

    for blk in parsed_blocks:
        first_text = blk["items"][0]["text"]
        raw = blk["raw"]

        # 从 raw 中提取可能的时间戳
        ts_matches = date_re.findall(raw)
        candidate_dates = set(ts_matches)

        # 尝试匹配：遍历所有 requirements，计算相似度
        best_score = 0
        best_req = None

        for r in reqs:
            feat = r["feature"]
            score = 0

            # 公共子串长度（归一化）
            common = len(set(feat) & set(first_text))
            score += common * 2

            # 如果块时间戳与 requirement date 匹配，加分
            if r["date"] in candidate_dates:
                score += 100

            # 关键词精确匹配
            feat_words = set(feat.replace('，', ',').replace('：', ':').split())
            text_words = set(first_text[:200].replace('，', ',').replace('：', ':').split())
            overlap = feat_words & text_words
            score += len(overlap) * 10

            if score > best_score:
                best_score = score
                best_req = r

        if best_score >= 5 and best_req is not None:
            # 去重：按 first_text 去重
            matched[best_req["id"]].append(blk)
        else:
            unmatched.append(blk)

    # 去重：同一 req_id 下按 items 去重
    for rid in matched:
        seen_items = set()
        unique = []
        for blk in matched[rid]:
            key = blk["items"][0]["text"][:100]
            if key not in seen_items:
                seen_items.add(key)
                unique.append(blk)
        matched[rid] = unique

    return dict(matched), unmatched


def recover_module_associations(conn):
    """用 modules 表名做启发式匹配，回填 requirement_modules 和 bug_modules。

    策略：
    - 对每条 requirement，检查 feature/content 是否包含某个 module 名
    - 如果 feature 匹配多个 module 名，全部关联
    - 对每条 bug，检查 content 是否包含某个 module 名
    - 无法匹配的置「未分组」
    """
    conn.row_factory = sqlite3.Row

    # 取所有模块
    modules = conn.execute("SELECT id, project_id, name FROM modules ORDER BY name").fetchall()
    proj_modules: dict[str, list] = defaultdict(list)
    for m in modules:
        proj_modules[m["project_id"]].append(m)

    rm_count = 0
    bm_count = 0

    # 回填 requirement_modules
    reqs = conn.execute(
        "SELECT id, project_id, feature, content FROM requirements"
    ).fetchall()
    for r in reqs:
        pmods = proj_modules.get(r["project_id"], [])
        text = (r["feature"] + " " + (r["content"] or "")).lower()
        for m in pmods:
            mname = m["name"].lower()
            # 模块名是 feature 的子串 或 feature 是模块名的子串
            if mname in text or (len(mname) > 3 and any(
                kw in text for kw in [mname, mname.replace(' ', '')]
            )):
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id)"
                        " VALUES (?, ?)",
                        (r["id"], m["id"]),
                    )
                    rm_count += 1
                except Exception:
                    pass

    # 回填 bug_modules
    bugs = conn.execute("SELECT id, project_id, content FROM bugs").fetchall()
    for b in bugs:
        pmods = proj_modules.get(b["project_id"], [])
        text = (b["content"] or "").lower()
        for m in pmods:
            mname = m["name"].lower()
            if mname in text:
                try:
                    conn.execute(
                        "INSERT OR IGNORE INTO bug_modules(bug_id, module_id)"
                        " VALUES (?, ?)",
                        (b["id"], m["id"]),
                    )
                    bm_count += 1
                except Exception:
                    pass

    return rm_count, bm_count


def main():
    if not DB_PATH.exists():
        print(f"错误：数据库不存在 {DB_PATH}")
        sys.exit(1)

    # ── 步骤 1: 提取残留 content 块 ──
    print("=== 步骤 1: 从 db 字节提取残留 content ===")
    blocks = extract_content_blocks(DB_PATH)
    print(f"  原始提取: {len(blocks)} 块")
    parsed = parse_blocks(blocks)
    print(f"  有效解析（≥2 编号）: {len(parsed)} 块")
    for i, p in enumerate(parsed):
        first = p["items"][0]["text"][:80]
        n_items = len(p["items"])
        print(f"    [{i+1}] ({n_items}项) {first}...")

    # ── 步骤 2: 匹配到现有 requirements ──
    print("\n=== 步骤 2: 匹配到现有 requirements ===")
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA foreign_keys = OFF")  # 恢复期关 FK
    try:
        matched, unmatched = match_to_requirements(conn, parsed)
        print(f"  已匹配: {sum(len(v) for v in matched.values())} 块 → {len(matched)} 条 requirements")
        print(f"  未匹配: {len(unmatched)} 块（需人工审核）")

        # ── 步骤 3: 生成子需求 ──
        print("\n=== 步骤 3: 生成子需求 ===")
        now_iso = datetime.now().isoformat()
        subitem_count = 0
        for rid, blks in matched.items():
            req = conn.execute("SELECT id, feature, content, status, date, created_at, updated_at FROM requirements WHERE id = ?", (rid,)).fetchone()
            if not req:
                continue

            # 该 requirement 的 content 是否需要恢复？
            # 如果 content == feature（被覆盖）且恢复了子需求，content 保持不变
            # 子需求编号从 1 开始连续
            seq = 0
            for blk in blks:
                for item in blk["items"]:
                    seq += 1
                    text = item["text"]
                    # 清理：去掉尾部残留的时间戳/ID
                    text = re.sub(r'\d{4}-\d{2}-\d{2}T[\d:.]+Z?$', '', text).strip()
                    text = re.sub(r'[A-Fa-f0-9]{8,}.*$', '', text).strip()
                    if text:
                        try:
                            conn.execute(
                                "INSERT INTO requirement_subitems"
                                "(id, iteration_id, seq, content, status,"
                                " completion_deadline, created_at, updated_at)"
                                " VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                                (
                                    uuid4().hex[:12],
                                    rid,
                                    seq,
                                    text,
                                    req["status"],
                                    req["created_at"],
                                    req["updated_at"],
                                ),
                            )
                            subitem_count += 1
                        except sqlite3.IntegrityError:
                            pass  # UNIQUE(iteration_id, seq) 冲突，跳过

        print(f"  生成子需求: {subitem_count} 条")

        # ── 步骤 4: 回填模块关联 ──
        print("\n=== 步骤 4: 回填模块关联 ===")
        rm_count, bm_count = recover_module_associations(conn)
        print(f"  requirement_modules: {rm_count} 条")
        print(f"  bug_modules: {bm_count} 条")

        # ── 步骤 5: 添加「未分组」模块并关联无模块的需求 ──
        print("\n=== 步骤 5: 未分组需求关联 ===")
        # 找出所有仍无关联模块的需求
        reqs_no_mod = conn.execute("""
            SELECT r.id, r.project_id FROM requirements r
            WHERE r.id NOT IN (SELECT requirement_id FROM requirement_modules)
        """).fetchall()
        ungrouped_count = 0
        for r in reqs_no_mod:
            # 确保「（未分组）」模块存在
            conn.execute(
                "INSERT OR IGNORE INTO modules(id, project_id, name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (uuid4().hex[:12], r["project_id"], "（未分组）", now_iso, now_iso),
            )
            mid = conn.execute(
                "SELECT id FROM modules WHERE project_id = ? AND name = ?",
                (r["project_id"], "（未分组）"),
            ).fetchone()
            if mid:
                conn.execute(
                    "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id)"
                    " VALUES (?, ?)",
                    (r["id"], mid["id"]),
                )
                ungrouped_count += 1
        print(f"  未分组 → 「（未分组）」: {ungrouped_count} 条")

        # 同样处理 bugs
        bugs_no_mod = conn.execute("""
            SELECT b.id, b.project_id FROM bugs b
            WHERE b.id NOT IN (SELECT bug_id FROM bug_modules)
        """).fetchall()
        bug_ungrouped = 0
        for b in bugs_no_mod:
            conn.execute(
                "INSERT OR IGNORE INTO modules(id, project_id, name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (uuid4().hex[:12], b["project_id"], "（未分组）", now_iso, now_iso),
            )
            mid = conn.execute(
                "SELECT id FROM modules WHERE project_id = ? AND name = ?",
                (b["project_id"], "（未分组）"),
            ).fetchone()
            if mid:
                conn.execute(
                    "INSERT OR IGNORE INTO bug_modules(bug_id, module_id)"
                    " VALUES (?, ?)",
                    (b["id"], mid["id"]),
                )
                bug_ungrouped += 1
        print(f"  bugs 未分组 → 「（未分组）」: {bug_ungrouped} 条")

        conn.commit()

        # ── 生成审核报告 ──
        print("\n=== 步骤 6: 生成审核报告 ===")
        report = build_report(conn, matched, unmatched)
        REPORT_PATH.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        print(f"  报告: {REPORT_PATH}")

        # 最终统计
        final_rm = conn.execute("SELECT COUNT(*) FROM requirement_modules").fetchone()[0]
        final_si = conn.execute("SELECT COUNT(*) FROM requirement_subitems").fetchone()[0]
        final_bm = conn.execute("SELECT COUNT(*) FROM bug_modules").fetchone()[0]

        print(f"\n=== 恢复完成 ===")
        print(f"  requirement_modules: {rm_count} + {ungrouped_count} = {final_rm}")
        print(f"  bug_modules: {bm_count} + {bug_ungrouped} = {final_bm}")
        print(f"  requirement_subitems: {subitem_count} = {final_si}")
        print(f"  未匹配块（需人工审核）: {len(unmatched)}")

    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.close()


def build_report(conn, matched, unmatched):
    """生成恢复前后的对比报告。"""
    conn.row_factory = sqlite3.Row
    report = {
        "recovery_time": datetime.now().isoformat(),
        "matched_requirements": [],
        "unmatched_blocks": [],
        "all_requirements": [],
        "all_bugs": [],
    }

    # 已匹配的 requirements
    for rid, blks in matched.items():
        req = conn.execute(
            "SELECT r.id, r.feature, r.content, r.date, r.status, p.name as project_name "
            "FROM requirements r JOIN projects p ON p.id=r.project_id WHERE r.id=?",
            (rid,),
        ).fetchone()
        if not req:
            continue

        subitems = conn.execute(
            "SELECT seq, content, status FROM requirement_subitems WHERE iteration_id=? ORDER BY seq",
            (rid,),
        ).fetchall()
        modules = conn.execute(
            "SELECT m.name FROM modules m "
            "JOIN requirement_modules rm ON rm.module_id=m.id WHERE rm.requirement_id=? ORDER BY m.name",
            (rid,),
        ).fetchall()

        report["matched_requirements"].append({
            "id": req["id"],
            "project": req["project_name"],
            "feature": req["feature"],
            "content": req["content"],
            "date": req["date"],
            "status": req["status"],
            "modules": [m["name"] for m in modules],
            "subitems": [{"seq": s["seq"], "content": s["content"], "status": s["status"]} for s in subitems],
        })

    # 未匹配的块
    for blk in unmatched:
        report["unmatched_blocks"].append({
            "items": [{"num": it["num"], "text": it["text"]} for it in blk["items"]],
        })

    # 全部 requirements
    all_reqs = conn.execute("""
        SELECT r.id, r.feature, r.content, r.date, r.status, p.name as project_name,
               (SELECT GROUP_CONCAT(m.name, ', ') FROM modules m
                JOIN requirement_modules rm ON rm.module_id=m.id WHERE rm.requirement_id=r.id) as mods,
               (SELECT COUNT(*) FROM requirement_subitems WHERE iteration_id=r.id) as si_count
        FROM requirements r JOIN projects p ON p.id=r.project_id ORDER BY p.name, r.date, r.feature
    """).fetchall()
    for r in all_reqs:
        report["all_requirements"].append(dict(r))

    # 全部 bugs
    all_bugs = conn.execute("""
        SELECT b.id, b.content, b.date, b.status, p.name as project_name,
               (SELECT GROUP_CONCAT(m.name, ', ') FROM modules m
                JOIN bug_modules bm ON bm.module_id=m.id WHERE bm.bug_id=b.id) as mods
        FROM bugs b JOIN projects p ON p.id=b.project_id ORDER BY p.name, b.date
    """).fetchall()
    for b in all_bugs:
        report["all_bugs"].append(dict(b))

    return report


if __name__ == "__main__":
    main()