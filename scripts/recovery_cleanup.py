"""恢复后的人工审核清理与迁移脚本（v2）

修正 v1 的 UNIQUE(seq) 冲突：迁移子需求时用 append 语义（目标 iteration 的 max(seq)+1）。
单一事务，任何异常全回滚。
"""

import re
import sqlite3
from datetime import datetime
from pathlib import Path
from uuid import uuid4

DB_PATH = Path(r"C:\Users\soifow\Documents\工作文档\智能室需求\management-prd-storage\requment.db")
PID_TOOL = "1730d30213b7"  # 需求记录小工具

FEATURE_TO_MODULE = {
    "项目列表": "主界面",
    "需求列表": "主界面",
    "UI": "主界面",
    "bug管理": "bug管理",
    "需求详情": "需求详情",
    "AI规则相关": "程序",
    "数据格式": "程序",
    "新建需求弹窗": "主界面",
    "未完任务提醒": "提醒",
    "禁止多开": "程序",
    "设置界面": "设置",
}

TS_TAIL_RE = re.compile(
    r"(?:P[0-9](?:fixed|open)?|done|todo|ui_done_waiting_backend|deferred)"
    r"\s*\d{4}-\d{2}-\d{2}(?:T[\d:.]+)?Z?$"
)
TS_TAIL_RE2 = re.compile(r"(?:done|todo|fixed|open)\d{4}-\d{2}-\d{2}(?:T[\d:.]+)?Z?$")


def clean_ts_tail(text: str) -> str:
    t = text.rstrip()
    t = TS_TAIL_RE2.sub("", t).rstrip()
    t = TS_TAIL_RE.sub("", t).rstrip()
    # 去尾部 \r* 等控制字符残留
    t = re.sub(r"[\r\n]*\*?\s*$", "", t).rstrip()
    return t


def next_seq(conn, iteration_id: str) -> int:
    row = conn.execute(
        "SELECT COALESCE(MAX(seq), 0) AS m FROM requirement_subitems WHERE iteration_id=?",
        (iteration_id,),
    ).fetchone()
    return int(row["m"]) + 1


def get_or_create_iteration(conn, project_id, feature, date_str, status, created_at, updated_at):
    """同 (project, feature, date) 已有 iteration 则复用，否则新建。返回 id。"""
    existing = conn.execute(
        "SELECT id FROM requirements WHERE project_id=? AND feature=? AND date=?",
        (project_id, feature, date_str),
    ).fetchone()
    if existing:
        return existing["id"]
    nid = uuid4().hex[:12]
    conn.execute(
        "INSERT INTO requirements"
        "(id, project_id, feature, content, status, date, completion_deadline,"
        " created_at, updated_at)"
        " VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
        (nid, project_id, feature, feature, status, date_str, created_at, updated_at),
    )
    return nid


def main():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = OFF")
    now = datetime.now().isoformat()

    try:
        # ════════════════════════════════════════
        # 第1段：子需求修正
        # ════════════════════════════════════════
        print("=== 第1段：子需求修正 ===\n")

        # [1] b23b666f 新建需求弹窗：seq1/2 是 bug（已在 bug 库 8440c54b 内），seq3 垃圾 -> 全删
        print("[1] b23b666f 新建需求弹窗：删除 seq1/2（bug 已在库内）/ seq3（垃圾）")
        n = conn.execute(
            "DELETE FROM requirement_subitems WHERE iteration_id=? AND seq IN (1,2,3)",
            ("b23b666f8159",),
        ).rowcount
        print(f"    删除 {n} 条")

        # [2] 4b9aaf19 设置界面 07-27：3 条都是"需求详情"子需求 -> 迁到新 feature「需求详情」
        print("\n[2] 4b9aaf19 设置界面：3 条迁到新 feature「需求详情」")
        subs = conn.execute(
            "SELECT seq, content, status, completion_deadline, created_at, updated_at "
            "FROM requirement_subitems WHERE iteration_id=? ORDER BY seq",
            ("4b9aaf196a38",),
        ).fetchall()
        new_iter = get_or_create_iteration(
            conn, PID_TOOL, "需求详情", "2026-07-27", "done",
            subs[0]["created_at"], subs[0]["updated_at"],
        )
        seq = 0
        for s in subs:
            seq += 1
            clean = clean_ts_tail(s["content"])
            # 删旧 INSERT 新（避免 seq 冲突）
            conn.execute(
                "DELETE FROM requirement_subitems WHERE iteration_id=? AND seq=?",
                ("4b9aaf196a38", s["seq"]),
            )
            conn.execute(
                "INSERT INTO requirement_subitems"
                "(id, iteration_id, seq, content, status, completion_deadline,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                (uuid4().hex[:12], new_iter, seq, clean, s["status"],
                 s["created_at"], s["updated_at"]),
            )
        print(f"    -> iteration {new_iter}（需求详情 07-27），迁移并清洗 3 条")

        # [3] e3ecadc7 系统所-批量导入：7 条误配，按主题拆迁回需求记录小工具
        print("\n[3] e3ecadc7 系统所-批量导入：7 条按主题拆迁回需求记录小工具")
        subs = conn.execute(
            "SELECT seq, content, status, completion_deadline, created_at, updated_at "
            "FROM requirement_subitems WHERE iteration_id=? ORDER BY seq",
            ("e3ecadc7ed32",),
        ).fetchall()
        # seq1-4 -> 需求列表 07-24（复用 61f19563，append seq 4-7）
        # seq5-7 -> 未完任务提醒 07-24（新建 iteration，date=07-24 不与 07-29 冲突）
        target_map = {
            1: ("需求列表", "2026-07-24"),
            2: ("需求列表", "2026-07-24"),
            3: ("需求列表", "2026-07-24"),
            4: ("需求列表", "2026-07-24"),
            5: ("未完任务提醒", "2026-07-24"),
            6: ("未完任务提醒", "2026-07-24"),
            7: ("未完任务提醒", "2026-07-24"),
        }
        iter_cache = {}
        for s in subs:
            feat, dt = target_map[s["seq"]]
            key = (feat, dt)
            if key not in iter_cache:
                iter_cache[key] = get_or_create_iteration(
                    conn, PID_TOOL, feat, dt, "done", s["created_at"], s["updated_at"]
                )
            target_iter = iter_cache[key]
            ns = next_seq(conn, target_iter)
            clean = clean_ts_tail(s["content"])
            conn.execute(
                "DELETE FROM requirement_subitems WHERE iteration_id=? AND seq=?",
                ("e3ecadc7ed32", s["seq"]),
            )
            conn.execute(
                "INSERT INTO requirement_subitems"
                "(id, iteration_id, seq, content, status, completion_deadline,"
                " created_at, updated_at) VALUES (?, ?, ?, ?, ?, NULL, ?, ?)",
                (uuid4().hex[:12], target_iter, ns, clean, s["status"],
                 s["created_at"], s["updated_at"]),
            )
            print(f"    seq{s['seq']} -> {feat}({dt}) iter={target_iter} as seq{ns}")
        # e3ecadc7 现在无子需求；它本身是系统所的合法需求（批量导入），保留

        # [4] 61f19563 需求列表 07-24 seq3：去尾部 done2026-07-24
        print("\n[4] 61f19563 需求列表：清洗 seq3 尾部残留")
        r = conn.execute(
            "SELECT content FROM requirement_subitems WHERE iteration_id=? AND seq=3",
            ("61f1956368b1",),
        ).fetchone()
        if r:
            clean = clean_ts_tail(r["content"])
            conn.execute(
                "UPDATE requirement_subitems SET content=? WHERE iteration_id=? AND seq=3",
                (clean, "61f1956368b1"),
            )
            print(f"    '{r['content']}' -> '{clean}'")

        # [5] 3a682f79 设置界面 07-28：seq5 清洗 + seq6 删除
        print("\n[5] 3a682f79 设置界面：清洗 seq5 + 删除 seq6")
        r = conn.execute(
            "SELECT content FROM requirement_subitems WHERE iteration_id=? AND seq=5",
            ("3a682f7906c6",),
        ).fetchone()
        if r:
            clean = clean_ts_tail(r["content"])
            conn.execute(
                "UPDATE requirement_subitems SET content=? WHERE iteration_id=? AND seq=5",
                (clean, "3a682f7906c6"),
            )
            print(f"    seq5 '{r['content'][:50]}...' -> '{clean[:50]}...'")
        n = conn.execute(
            "DELETE FROM requirement_subitems WHERE iteration_id=? AND seq=6",
            ("3a682f7906c6",),
        ).rowcount
        print(f"    删除 seq6 {n} 条")

        # [6] 4f7ae720 需求列表 07-27 seq2：清洗残留
        print("\n[6] 4f7ae720 需求列表：清洗 seq2")
        r = conn.execute(
            "SELECT content FROM requirement_subitems WHERE iteration_id=? AND seq=2",
            ("4f7ae72078b8",),
        ).fetchone()
        if r:
            clean = clean_ts_tail(r["content"])
            conn.execute(
                "UPDATE requirement_subitems SET content=? WHERE iteration_id=? AND seq=2",
                (clean, "4f7ae72078b8"),
            )
            print(f"    '{r['content'][:50]}...' -> '{clean[:50]}...'")

        # [7] 9b084bce 设置界面 07-29 seq2/seq4：清洗残留
        print("\n[7] 9b084bce 设置界面：清洗 seq2/seq4")
        for seq in (2, 4):
            r = conn.execute(
                "SELECT content FROM requirement_subitems WHERE iteration_id=? AND seq=?",
                ("9b084bce42b2", seq),
            ).fetchone()
            if r:
                clean = clean_ts_tail(r["content"])
                conn.execute(
                    "UPDATE requirement_subitems SET content=? WHERE iteration_id=? AND seq=?",
                    (clean, "9b084bce42b2", seq),
                )
                print(f"    seq{seq} '{r['content'][:50]}...' -> '{clean[:50]}...'")

        # ════════════════════════════════════════
        # 第2段：删除 4 个脏模块名
        # ════════════════════════════════════════
        print("\n=== 第2段：删除脏模块名 ===\n")
        dirty_modules = [
            "03513ec2919c", "f12fb80987f0", "adf8ac525437", "bf5075ce4c5d",
        ]
        for mid in dirty_modules:
            m = conn.execute("SELECT name, project_id FROM modules WHERE id=?", (mid,)).fetchone()
            if m:
                conn.execute("DELETE FROM requirement_modules WHERE module_id=?", (mid,))
                conn.execute("DELETE FROM bug_modules WHERE module_id=?", (mid,))
                conn.execute("DELETE FROM modules WHERE id=?", (mid,))
                print(f"    删除「{m['name']}」(id={mid})")

        # ════════════════════════════════════════
        # 第3段：需求记录小工具 feature->模块 重设
        # ════════════════════════════════════════
        print("\n=== 第3段：需求记录小工具 feature->模块 重设 ===\n")
        for mod_name in set(FEATURE_TO_MODULE.values()):
            conn.execute(
                "INSERT OR IGNORE INTO modules(id, project_id, name, created_at, updated_at)"
                " VALUES (?, ?, ?, ?, ?)",
                (uuid4().hex[:12], PID_TOOL, mod_name, now, now),
            )
        # 清旧关联（含恢复期误配），按 feature 重新关联
        conn.execute(
            "DELETE FROM requirement_modules WHERE requirement_id IN "
            "(SELECT id FROM requirements WHERE project_id=?)",
            (PID_TOOL,),
        )
        feat_to_modid = {
            mn: conn.execute(
                "SELECT id FROM modules WHERE project_id=? AND name=?", (PID_TOOL, mn)
            ).fetchone()["id"]
            for mn in set(FEATURE_TO_MODULE.values())
        }
        reqs = conn.execute(
            "SELECT id, feature FROM requirements WHERE project_id=?", (PID_TOOL,)
        ).fetchall()
        linked = 0
        for r in reqs:
            mod_name = FEATURE_TO_MODULE.get(r["feature"])
            if mod_name:
                conn.execute(
                    "INSERT OR IGNORE INTO requirement_modules(requirement_id, module_id) VALUES (?, ?)",
                    (r["id"], feat_to_modid[mod_name]),
                )
                linked += 1
        print(f"    按 feature 关联 {linked} 条需求")

        # bug 模块：需求记录小工具的 bug 关联到「bug管理」
        print("\n=== bug 模块重设（需求记录小工具） ===\n")
        conn.execute(
            "DELETE FROM bug_modules WHERE bug_id IN (SELECT id FROM bugs WHERE project_id=?)",
            (PID_TOOL,),
        )
        bug_mod_id = feat_to_modid.get("bug管理")
        if bug_mod_id:
            bugs = conn.execute("SELECT id FROM bugs WHERE project_id=?", (PID_TOOL,)).fetchall()
            for b in bugs:
                conn.execute(
                    "INSERT OR IGNORE INTO bug_modules(bug_id, module_id) VALUES (?, ?)",
                    (b["id"], bug_mod_id),
                )
            print(f"    {len(bugs)} 条 bug -> 「bug管理」")

        conn.commit()
        print("\n=== 已提交 ===")
    except Exception as e:
        conn.rollback()
        print(f"\n!!! 异常，已回滚: {e}")
        raise
    finally:
        conn.execute("PRAGMA foreign_keys = ON")
        # 最终统计
        print("\n=== 最终统计 ===")
        for t in ("requirements", "requirement_subitems", "modules",
                  "requirement_modules", "bugs", "bug_modules"):
            print(f"  {t}: {conn.execute(f'SELECT COUNT(*) FROM {t}').fetchone()[0]}")
        conn.close()


if __name__ == "__main__":
    main()