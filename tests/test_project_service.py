"""项目服务测试（v3：单 date + feature，SQLite 后端）。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from management_prd.models.data import (
    CreateRequirementInput,
    ParsedRequirement,
    UpdateRequirementInput,
)
from management_prd.models.requirement import RequirementStatus
from management_prd.services.db_service import DbService
from management_prd.services.project_service import ProjectService


@pytest.fixture()
def service(tmp_path: Path) -> ProjectService:
    """使用临时目录的 ProjectService（基于临时 SQLite）。"""
    db = DbService(db_path=tmp_path / "requment.db")
    db.init_db()
    return ProjectService(db)


# ---------- 项目 ----------


def test_create_and_list_project(service: ProjectService) -> None:
    s = service.create_project("项目A")
    assert s.name == "项目A"
    assert s.requirement_count == 0
    assert s.list_date is None

    summaries = service.list_summaries()
    assert len(summaries) == 1
    assert summaries[0].name == "项目A"


def test_rename_project(service: ProjectService) -> None:
    s = service.create_project("旧名")
    s2 = service.rename_project(s.id, "新名")
    assert s2.name == "新名"


def test_create_project_empty_name(service: ProjectService) -> None:
    with pytest.raises(ValueError):
        service.create_project("   ")


def test_delete_project(service: ProjectService) -> None:
    s = service.create_project("项目A")
    assert service.delete_project(s.id) is True
    assert service.list_summaries() == []


# ---------- 需求迭代 ----------


def test_create_requirement(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能X",
            content="第一次描述",
            status=RequirementStatus.TODO,
            date=date(2026, 6, 29),
        ),
    )
    assert item.module == "模块1"
    assert item.feature == "功能X"
    assert item.content == "第一次描述"
    assert item.date == date(2026, 6, 29)


def test_create_requirement_feature_defaults_to_content(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="",
            content="需求内容",
            status=RequirementStatus.TODO,
            date=date(2026, 6, 29),
        ),
    )
    assert item.feature == "需求内容"


def test_update_requirement(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="m1",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    updated = service.update_requirement(
        item.id,
        UpdateRequirementInput(module="m2", content="c2", status=RequirementStatus.DONE),
    )
    assert updated.module == "m2"
    assert updated.content == "c2"
    assert updated.status == RequirementStatus.DONE


def test_set_status(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    updated = service.set_status(item.id, RequirementStatus.DONE)
    assert updated.status == RequirementStatus.DONE


def test_delete_requirement(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert service.delete_requirement(item.id) is True
    assert service.get(p.id).items == []


# ---------- list_modules / list_features / list_iterations ----------


def test_list_modules(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块B",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块A",
            feature="f2",
            content="c2",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f3",
            content="c3",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert service.list_modules(p.id) == ["模块A", "模块B"]


def test_list_features(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能B",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能A",
            content="c2",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert service.list_features(p.id, "模块1") == ["功能A", "功能B"]


def test_list_iterations(service: ProjectService) -> None:
    p = service.create_project("项目A")
    # 两次迭代同一个功能
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能X",
            content="v1描述",
            status=RequirementStatus.DONE,
            date=date(2026, 3, 27),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="模块1",
            feature="功能X",
            content="v2描述",
            status=RequirementStatus.TODO,
            date=date(2026, 5, 20),
        ),
    )
    iters = service.list_iterations(p.id, "模块1", "功能X")
    assert len(iters) == 2
    assert iters[0].date == date(2026, 3, 27)
    assert iters[0].content == "v1描述"
    assert iters[1].date == date(2026, 5, 20)
    assert iters[1].content == "v2描述"


# ---------- 汇总 list_date（项目列表日期口径） ----------


def test_summary_default_mode_is_latest_any(service: ProjectService) -> None:
    """默认口径 latest_any：取所有需求日期的最大值，不限状态。"""
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="done1",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f2",
            content="ui1",
            status=RequirementStatus.UI_DONE_WAITING_BACKEND,
            date=date(2026, 7, 15),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f3",
            content="todo1",
            status=RequirementStatus.TODO,
            date=date(2026, 8, 1),
        ),
    )
    summaries = service.list_summaries()
    assert summaries[0].list_date == date(2026, 8, 1)
    assert summaries[0].requirement_count == 3


def test_summary_mode_latest_done(service: ProjectService) -> None:
    """latest_done 口径：仅统计 done / ui_done_waiting_backend。"""
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="done1",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f2",
            content="ui1",
            status=RequirementStatus.UI_DONE_WAITING_BACKEND,
            date=date(2026, 7, 15),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f3",
            content="todo1",
            status=RequirementStatus.TODO,
            date=date(2026, 8, 1),
        ),
    )
    summaries = service.list_summaries(date_mode="latest_done")
    assert summaries[0].list_date == date(2026, 7, 15)


def test_summary_mode_latest_done_none_when_only_todo(service: ProjectService) -> None:
    """latest_done 口径下，仅有未完成需求时 list_date 为 None。"""
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="todo1",
            status=RequirementStatus.TODO,
            date=date(2026, 8, 1),
        ),
    )
    summaries = service.list_summaries(date_mode="latest_done")
    assert summaries[0].list_date is None


def test_summary_mode_latest_activity(service: ProjectService) -> None:
    """latest_activity 口径：list_date 取 projects.updated_at 的日期部分（当天）。"""
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="todo1",
            status=RequirementStatus.TODO,
            date=date(2020, 1, 1),
        ),
    )
    summaries = service.list_summaries(date_mode="latest_activity")
    # 需求创建刚把 updated_at 刷新到当下，故日期口径取当天
    assert summaries[0].list_date == date.today()


def test_list_summaries_sorted_newest_first_empty_last(service: ProjectService) -> None:
    """默认口径下：日期越近越靠前，无日期项目沉底。"""
    pa = service.create_project("A-新")
    service.create_requirement(
        pa.id,
        CreateRequirementInput(
            module="", feature="f", content="c", status=RequirementStatus.TODO,
            date=date(2026, 7, 30),
        ),
    )
    pb = service.create_project("B-旧")
    service.create_requirement(
        pb.id,
        CreateRequirementInput(
            module="", feature="f", content="c", status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_project("C-空")  # 无任何需求
    names = [s.name for s in service.list_summaries()]
    assert names == ["A-新", "B-旧", "C-空"]


# ---------- apply_import 去重 ----------


def test_apply_import_new_items(service: ProjectService) -> None:
    p = service.create_project("项目A")
    parsed = [
        ParsedRequirement(
            module="模块A",
            feature="功能X",
            content="需求X",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        ),
        ParsedRequirement(
            module="模块A",
            feature="需求Y",
            content="需求Y",
            status=RequirementStatus.TODO,
            date=date(2026, 6, 29),
        ),
    ]
    project = service.apply_import(p.id, parsed)
    assert len(project.items) == 2


def test_apply_import_dedup_same_date_module_content(service: ProjectService) -> None:
    p = service.create_project("项目A")
    parsed1 = [
        ParsedRequirement(
            module="模块A",
            feature="需求X",
            content="需求X",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        )
    ]
    service.apply_import(p.id, parsed1)
    # 重复导入同一条（同 date+module+content）-> 不复制
    service.apply_import(p.id, parsed1)
    project = service.get(p.id)
    assert len(project.items) == 1


def test_apply_import_different_date_same_feature(service: ProjectService) -> None:
    """同 feature 不同 date -> 两条记录（迭代链）。"""
    p = service.create_project("项目A")
    service.apply_import(
        p.id,
        [
            ParsedRequirement(
                module="模块A",
                feature="功能X",
                content="功能X",
                status=RequirementStatus.DONE,
                date=date(2026, 6, 29),
            )
        ],
    )
    service.apply_import(
        p.id,
        [
            ParsedRequirement(
                module="模块A",
                feature="功能X",
                content="功能X",
                status=RequirementStatus.TODO,
                date=date(2026, 7, 15),
            )
        ],
    )
    project = service.get(p.id)
    assert len(project.items) == 2
    # 不改已有状态
    assert project.items[0].status == RequirementStatus.DONE


def test_apply_import_skips_unselected(service: ProjectService) -> None:
    p = service.create_project("项目A")
    parsed = [
        ParsedRequirement(
            module="模块A",
            feature="需求X",
            content="需求X",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
            selected=False,
        )
    ]
    project = service.apply_import(p.id, parsed)
    assert project.items == []


# ---------- persistence ----------


def test_persistence_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "requment.db"
    DbService(db_path=db_path).init_db()
    s1 = ProjectService(DbService(db_path=db_path))
    p = s1.create_project("项目A")
    s1.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )

    s2 = ProjectService(DbService(db_path=db_path))
    summaries = s2.list_summaries()
    assert len(summaries) == 1
    assert summaries[0].requirement_count == 1


# ---------- completion_deadline 字段读写 ----------


def test_create_requirement_with_deadline(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="m1",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=date(2026, 2, 1),
        ),
    )
    assert item.completion_deadline == date(2026, 2, 1)
    # 回读路径（get / list_iterations）一致
    assert service.get(p.id).items[0].completion_deadline == date(2026, 2, 1)
    iters = service.list_iterations(p.id, "m1", "f1")
    assert iters[0].completion_deadline == date(2026, 2, 1)


def test_create_requirement_no_deadline_defaults_none(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert item.completion_deadline is None


# ---------- deferred 三路径强制清空时限 ----------


def test_create_deferred_forces_deadline_none(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.DEFERRED,
            date=date(2026, 1, 1),
            completion_deadline=date(2026, 2, 1),  # 应被忽略
        ),
    )
    assert item.completion_deadline is None
    assert service.get(p.id).items[0].completion_deadline is None


def test_update_deferred_clears_deadline(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=date(2026, 2, 1),
        ),
    )
    updated = service.update_requirement(
        item.id,
        UpdateRequirementInput(status=RequirementStatus.DEFERRED),
    )
    assert updated.status == RequirementStatus.DEFERRED
    assert updated.completion_deadline is None


def test_update_clear_deadline_flag(service: ProjectService) -> None:
    """clear_completion_deadline=True 显式清空（非 deferred 路径）。"""
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=date(2026, 2, 1),
        ),
    )
    updated = service.update_requirement(
        item.id,
        UpdateRequirementInput(clear_completion_deadline=True),
    )
    assert updated.completion_deadline is None


def test_update_set_deadline(service: ProjectService) -> None:
    """无时限项通过 update 设值。"""
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    updated = service.update_requirement(
        item.id,
        UpdateRequirementInput(completion_deadline=date(2026, 3, 1)),
    )
    assert updated.completion_deadline == date(2026, 3, 1)


def test_update_skip_deadline_when_not_provided(service: ProjectService) -> None:
    """completion_deadline=None 且 clear=False -> 不更新（保留原值）。"""
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=date(2026, 2, 1),
        ),
    )
    updated = service.update_requirement(item.id, UpdateRequirementInput(content="c2"))
    assert updated.content == "c2"
    assert updated.completion_deadline == date(2026, 2, 1)


def test_set_status_deferred_clears_deadline(service: ProjectService) -> None:
    """DateGroupView 快捷切换 -> set_status(deferred) 清空时限。"""
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=date(2026, 2, 1),
        ),
    )
    updated = service.set_status(item.id, RequirementStatus.DEFERRED)
    assert updated.status == RequirementStatus.DEFERRED
    assert updated.completion_deadline is None


def test_set_status_non_deferred_keeps_deadline(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=date(2026, 2, 1),
        ),
    )
    updated = service.set_status(item.id, RequirementStatus.UI_DONE_WAITING_BACKEND)
    assert updated.status == RequirementStatus.UI_DONE_WAITING_BACKEND
    assert updated.completion_deadline == date(2026, 2, 1)


# ---------- list_todo_reminders ----------


def _today() -> date:
    return date.today()


def _timedelta_days(n: int) -> timedelta:
    return timedelta(days=n)


def test_todo_excludes_done(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="done-item",
            status=RequirementStatus.DONE,
            date=date(2026, 1, 1),
            completion_deadline=_today(),
        ),
    )
    reminders = service.list_todo_reminders(threshold_days=7, show_no_deadline=True)
    assert reminders == []


def test_todo_deferred_always_included_at_end(service: ProjectService) -> None:
    p = service.create_project("项目A")
    # deferred 不受阈值影响，始终纳入并落在 deferred 桶
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="m1",
            feature="f1",
            content="deferred-item",
            status=RequirementStatus.DEFERRED,
            date=date(2026, 1, 1),
        ),
    )
    reminders = service.list_todo_reminders(threshold_days=0, show_no_deadline=False)
    assert len(reminders) == 1
    assert reminders[0]["bucket"] == "deferred"
    assert reminders[0]["remaining_days"] is None


def test_todo_no_deadline_respects_switch(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="no-deadline-item",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    # 开关开 -> 纳入 no_deadline 桶
    on = service.list_todo_reminders(threshold_days=7, show_no_deadline=True)
    assert len(on) == 1
    assert on[0]["bucket"] == "no_deadline"
    # 开关关 -> 排除
    off = service.list_todo_reminders(threshold_days=7, show_no_deadline=False)
    assert off == []


def test_todo_threshold_filtering(service: ProjectService) -> None:
    p = service.create_project("项目A")
    # 阈值内（今天到期）
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="within",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today(),
        ),
    )
    # 阈值外（30 天后）
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f2",
            content="beyond",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today() + _timedelta_days(30),
        ),
    )
    reminders = service.list_todo_reminders(threshold_days=7, show_no_deadline=False)
    contents = [r["content"] for r in reminders]
    assert "within" in contents
    assert "beyond" not in contents


def test_todo_overdue_bucket(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="overdue-item",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today() - _timedelta_days(3),
        ),
    )
    reminders = service.list_todo_reminders(threshold_days=7, show_no_deadline=False)
    assert len(reminders) == 1
    assert reminders[0]["bucket"] == "overdue"
    assert reminders[0]["remaining_days"] == -3


def test_todo_remaining_bucket_and_sort(service: ProjectService) -> None:
    """分组顺序：overdue -> remaining(升序) -> no_deadline -> deferred。"""
    p = service.create_project("项目A")
    # overdue（3 天前）
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="overdue",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today() - _timedelta_days(3),
        ),
    )
    # remaining：今天(0) 与 5 天后
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f2",
            content="today",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today(),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f3",
            content="five-days",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today() + _timedelta_days(5),
        ),
    )
    # no_deadline
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f4",
            content="no-deadline",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    # deferred
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f5",
            content="deferred",
            status=RequirementStatus.DEFERRED,
            date=date(2026, 1, 1),
        ),
    )

    reminders = service.list_todo_reminders(threshold_days=7, show_no_deadline=True)
    buckets = [r["bucket"] for r in reminders]
    assert buckets == ["overdue", "remaining", "remaining", "no_deadline", "deferred"]
    # remaining 内按剩余天数升序：今天(0) 在 5 天前
    remaining_items = [r for r in reminders if r["bucket"] == "remaining"]
    assert [r["remaining_days"] for r in remaining_items] == [0, 5]
    # 全局内容顺序
    assert [r["content"] for r in reminders] == [
        "overdue",
        "today",
        "five-days",
        "no-deadline",
        "deferred",
    ]


def test_todo_cross_project_aggregation(service: ProjectService) -> None:
    pa = service.create_project("项目A")
    pb = service.create_project("项目B")
    service.create_requirement(
        pa.id,
        CreateRequirementInput(
            module="模块A",
            feature="f1",
            content="a-item",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today(),
        ),
    )
    service.create_requirement(
        pb.id,
        CreateRequirementInput(
            module="模块B",
            feature="f1",
            content="b-item",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today(),
        ),
    )
    reminders = service.list_todo_reminders(threshold_days=7, show_no_deadline=False)
    project_names = sorted(r["project_name"] for r in reminders)
    assert project_names == ["项目A", "项目B"]
    # 每条带项目名/模块
    for r in reminders:
        assert r["project_name"] in {"项目A", "项目B"}
        assert r["module"] in {"模块A", "模块B"}


def test_todo_threshold_zero_includes_only_overdue_and_deferred(
    service: ProjectService,
) -> None:
    """阈值 0：仅 remaining<=0（即 overdue）与 deferred 纳入；正剩余排除。"""
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f1",
            content="overdue",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today() - _timedelta_days(1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f2",
            content="future",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today() + _timedelta_days(1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module="",
            feature="f3",
            content="deferred",
            status=RequirementStatus.DEFERRED,
            date=date(2026, 1, 1),
        ),
    )
    reminders = service.list_todo_reminders(threshold_days=0, show_no_deadline=False)
    contents = sorted(r["content"] for r in reminders)
    assert contents == ["deferred", "overdue"]
