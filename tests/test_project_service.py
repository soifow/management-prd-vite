"""项目服务测试（v4：多模块关联 + 迭代级子需求，SQLite 后端）。"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from management_prd.models.data import CreateRequirementInput, UpdateRequirementInput
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
            module_names=["模块1"],
            feature="功能X",
            content="第一次描述",
            status=RequirementStatus.TODO,
            date=date(2026, 6, 29),
        ),
    )
    assert item.modules == ["模块1"]
    assert item.feature == "功能X"
    assert item.content == "第一次描述"
    assert item.date == date(2026, 6, 29)


def test_create_requirement_requires_module(service: ProjectService) -> None:
    """v4：至少一个模块，空列表拒绝。"""
    p = service.create_project("项目A")
    with pytest.raises(ValueError):
        service.create_requirement(
            p.id,
            CreateRequirementInput(
                module_names=[],
                feature="f1",
                content="c1",
                status=RequirementStatus.TODO,
                date=date(2026, 1, 1),
            ),
        )


def test_create_requirement_feature_defaults_to_content(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块1"],
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
            module_names=["m1"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    updated = service.update_requirement(
        item.id,
        UpdateRequirementInput(module_names=["m2"], content="c2", status=RequirementStatus.DONE),
    )
    assert updated.modules == ["m2"]
    assert updated.content == "c2"
    assert updated.status == RequirementStatus.DONE


def test_set_status(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m1"],
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
            module_names=["m1"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert service.delete_requirement(item.id) is True
    assert service.get(p.id).items == []


# ---------- 模块 / list_features / list_iterations ----------


def _module_names(service: ProjectService, project_id: str) -> list[str]:
    return [m.name for m in service.list_modules(project_id)]


def test_list_modules(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块B"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块A"],
            feature="f2",
            content="c2",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert _module_names(service, p.id) == ["模块A", "模块B"]


def test_list_features(service: ProjectService) -> None:
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块1"],
            feature="功能B",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块1"],
            feature="功能A",
            content="c2",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    # v4：list_features 不再按 module 限定，项目级去重排序
    assert service.list_features(p.id) == ["功能A", "功能B"]


def test_list_iterations(service: ProjectService) -> None:
    p = service.create_project("项目A")
    # 两次迭代同一个功能
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块1"],
            feature="功能X",
            content="v1描述",
            status=RequirementStatus.DONE,
            date=date(2026, 3, 27),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块1"],
            feature="功能X",
            content="v2描述",
            status=RequirementStatus.TODO,
            date=date(2026, 5, 20),
        ),
    )
    # v4：list_iterations(project_id, feature)，去 module 参数
    iters = service.list_iterations(p.id, "功能X")
    assert len(iters) == 2
    assert iters[0].date == date(2026, 3, 27)
    assert iters[0].content == "v1描述"
    assert iters[1].date == date(2026, 5, 20)
    assert iters[1].content == "v2描述"


# ---------- 多模块关联（v4） ----------


def test_create_requirement_multi_module(service: ProjectService) -> None:
    """一个需求关联多个模块，任一模块平权。"""
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块A", "模块B"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    assert item.modules == ["模块A", "模块B"]
    # 回读一致
    assert service.get(p.id).items[0].modules == ["模块A", "模块B"]
    # 两个模块都落表
    assert _module_names(service, p.id) == ["模块A", "模块B"]


def test_update_requirement_replaces_modules(service: ProjectService) -> None:
    """module_names 整体替换关联（关联表删旧+插新）。旧模块仍留 modules 表（一等实体）。"""
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块A"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    updated = service.update_requirement(
        item.id, UpdateRequirementInput(module_names=["模块B", "模块C"])
    )
    assert updated.modules == ["模块B", "模块C"]
    # 关联已替换（不再关联模块A）
    assert "模块A" not in updated.modules
    # 模块A 仍留 modules 表（一等实体不自动删孤儿）
    assert set(_module_names(service, p.id)) == {"模块A", "模块B", "模块C"}


def test_create_module_and_delete(service: ProjectService) -> None:
    p = service.create_project("项目A")
    m = service.create_module(p.id, "独立模块")
    assert m.name == "独立模块"
    assert _module_names(service, p.id) == ["独立模块"]
    # 未关联，可删
    assert service.delete_module(m.id) is True
    assert _module_names(service, p.id) == []


def test_delete_module_rejects_when_in_use(service: ProjectService) -> None:
    """模块仍关联需求时拒绝删除。"""
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块A"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    m = service.list_modules(p.id)[0]
    with pytest.raises(ValueError):
        service.delete_module(m.id)


# ---------- 汇总 list_date（项目列表日期口径） ----------


def test_summary_default_mode_is_latest_any(service: ProjectService) -> None:
    """默认口径 latest_any：取所有需求日期的最大值，不限状态。"""
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m"],
            feature="f1",
            content="done1",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m"],
            feature="f2",
            content="ui1",
            status=RequirementStatus.UI_DONE_WAITING_BACKEND,
            date=date(2026, 7, 15),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m"],
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
            module_names=["m"],
            feature="f1",
            content="done1",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m"],
            feature="f2",
            content="ui1",
            status=RequirementStatus.UI_DONE_WAITING_BACKEND,
            date=date(2026, 7, 15),
        ),
    )
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
            feature="f",
            content="c",
            status=RequirementStatus.TODO,
            date=date(2026, 7, 30),
        ),
    )
    pb = service.create_project("B-旧")
    service.create_requirement(
        pb.id,
        CreateRequirementInput(
            module_names=["m"],
            feature="f",
            content="c",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_project("C-空")  # 无任何需求
    names = [s.name for s in service.list_summaries()]
    assert names == ["A-新", "B-旧", "C-空"]


# ---------- 同 (feature, date) upsert 并入（v4） ----------


def test_create_same_feature_date_upserts_as_subitem(service: ProjectService) -> None:
    """同 (feature, date) 已存在 -> 并入：模块合并、新 content 作为子需求。"""
    p = service.create_project("项目A")
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块A"],
            feature="功能X",
            content="第一段",
            status=RequirementStatus.DONE,
            date=date(2026, 6, 29),
        ),
    )
    # 同 feature + 同 date，不同模块、不同 content
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["模块B"],
            feature="功能X",
            content="第二段",
            status=RequirementStatus.TODO,
            date=date(2026, 6, 29),
        ),
    )
    project = service.get(p.id)
    # 只有一条迭代（UNIQUE 约束 + upsert 并入）
    assert len(project.items) == 1
    it = project.items[0]
    # 模块合并（并集）
    assert it.modules == ["模块A", "模块B"]
    # 第二段作为子需求追加
    subitems = service.list_subitems(it.id)
    assert len(subitems) == 1
    assert subitems[0].content == "第二段"


# ---------- persistence ----------


def test_persistence_across_instances(tmp_path: Path) -> None:
    db_path = tmp_path / "requment.db"
    DbService(db_path=db_path).init_db()
    s1 = ProjectService(DbService(db_path=db_path))
    p = s1.create_project("项目A")
    s1.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m1"],
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
            module_names=["m1"],
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
    iters = service.list_iterations(p.id, "f1")
    assert iters[0].completion_deadline == date(2026, 2, 1)


def test_create_requirement_no_deadline_defaults_none(service: ProjectService) -> None:
    p = service.create_project("项目A")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m1"],
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
            module_names=["m1"],
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
            module_names=["m1"],
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
            module_names=["m1"],
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
            module_names=["m1"],
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
            module_names=["m1"],
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
            module_names=["m1"],
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
            module_names=["m1"],
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


# ---------- 迭代级子需求 CRUD（v4） ----------


def test_subitem_crud(service: ProjectService) -> None:
    from management_prd.models.subitem import CreateSubitemInput, UpdateSubitemInput

    p = service.create_project("项目A")
    it = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m1"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    # 新建两条子需求，seq 自增
    s1 = service.create_subitem(
        CreateSubitemInput(iteration_id=it.id, content="子1", status=RequirementStatus.TODO)
    )
    s2 = service.create_subitem(
        CreateSubitemInput(iteration_id=it.id, content="子2", status=RequirementStatus.DONE)
    )
    assert s1.seq == 1
    assert s2.seq == 2
    items = service.list_subitems(it.id)
    assert [x.content for x in items] == ["子1", "子2"]
    # 更新
    upd = service.update_subitem(
        s1.id, UpdateSubitemInput(content="子1改", status=RequirementStatus.DONE)
    )
    assert upd.content == "子1改"
    assert upd.status == RequirementStatus.DONE
    # 删除
    assert service.delete_subitem(s2.id) is True
    assert len(service.list_subitems(it.id)) == 1


def test_subitem_update_deadline(service: ProjectService) -> None:
    """子需求 deadline 设值：返回值与持久化都应是新值（非 deferred 路径）。

    回归 UI bug「选了日期但控件未显示」：确认后端 update_subitem 对 completion_deadline
    的设值分支返回正确值，且重新读取一致。
    """
    from management_prd.models.subitem import CreateSubitemInput, UpdateSubitemInput

    p = service.create_project("项目A")
    it = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m1"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    s = service.create_subitem(
        CreateSubitemInput(iteration_id=it.id, content="子1", status=RequirementStatus.TODO)
    )
    assert s.completion_deadline is None

    # 设值（status 同传入参，模拟 UI 一并带上）
    upd = service.update_subitem(
        s.id,
        UpdateSubitemInput(
            completion_deadline=date(2026, 8, 10),
            clear_completion_deadline=False,
            status=RequirementStatus.TODO,
        ),
    )
    assert upd.completion_deadline == date(2026, 8, 10)
    # 重新读取一致
    again = service.list_subitems(it.id)
    assert again[0].completion_deadline == date(2026, 8, 10)


def test_subitem_deferred_clears_deadline(service: ProjectService) -> None:
    from management_prd.models.subitem import CreateSubitemInput

    p = service.create_project("项目A")
    it = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m1"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    s = service.create_subitem(
        CreateSubitemInput(
            iteration_id=it.id,
            content="子1",
            status=RequirementStatus.DEFERRED,
            completion_deadline=date(2026, 5, 1),  # 应被忽略
        )
    )
    assert s.completion_deadline is None


def test_subitem_cascade_delete_with_iteration(service: ProjectService) -> None:
    """删迭代 -> 子需求级联删除，无孤儿。"""
    from management_prd.models.subitem import CreateSubitemInput

    p = service.create_project("项目A")
    it = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m1"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_subitem(
        CreateSubitemInput(iteration_id=it.id, content="子1", status=RequirementStatus.TODO)
    )
    # 删迭代
    service.delete_requirement(it.id)
    # 子需求随之消失
    assert service.list_subitems(it.id) == []


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
            module_names=["m"],
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
            module_names=["m1"],
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["模块A"],
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
            module_names=["模块B"],
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
    # 每条带项目名/模块（v4：module 取首个模块名）
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
            module_names=["m"],
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
            module_names=["m"],
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
            module_names=["m"],
            feature="f3",
            content="deferred",
            status=RequirementStatus.DEFERRED,
            date=date(2026, 1, 1),
        ),
    )
    reminders = service.list_todo_reminders(threshold_days=0, show_no_deadline=False)
    contents = sorted(r["content"] for r in reminders)
    assert contents == ["deferred", "overdue"]


def test_todo_subitem_granularity(service: ProjectService) -> None:
    """待办提醒最小粒度为子需求：有子需求时按子需求逐条返回，无子需求回退到迭代。"""
    from management_prd.models.subitem import CreateSubitemInput

    p = service.create_project("项目A")
    # 迭代 f1：有两条子需求（一 todo 一 done）
    it = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m"],
            feature="f1",
            content="iter-content",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
        ),
    )
    service.create_subitem(
        CreateSubitemInput(
            iteration_id=it.id,
            content="子需求A",
            status=RequirementStatus.TODO,
            completion_deadline=_today(),
        ),
    )
    service.create_subitem(
        CreateSubitemInput(
            iteration_id=it.id,
            content="子需求B",
            status=RequirementStatus.DONE,  # done 不纳入
        ),
    )
    # 迭代 f2：无子需求，自身作为一条提醒
    service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m"],
            feature="f2",
            content="bare-iter",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today(),
        ),
    )

    reminders = service.list_todo_reminders(threshold_days=7, show_no_deadline=True)
    contents = sorted(r["content"] for r in reminders)
    # 子需求A（粒度到子需求）+ bare-iter（无子需求回退迭代）；
    # 子需求B done 被排除；iter-content 不再单独出现（已被子需求A取代）
    assert contents == ["bare-iter", "子需求A"]
    # 子需求A 带 subitem_id，bare-iter 的 subitem_id 为 None
    by_content = {r["content"]: r for r in reminders}
    assert by_content["子需求A"]["subitem_id"] is not None
    assert by_content["bare-iter"]["subitem_id"] is None


def test_todo_subitem_inherits_iter_deadline(service: ProjectService) -> None:
    """子需求默认继承迭代 deadline，但可独立修改/删除（待办按子需求自身 deadline 计算）。"""
    from management_prd.models.subitem import CreateSubitemInput, UpdateSubitemInput

    p = service.create_project("项目A")
    it = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["m"],
            feature="f1",
            content="c1",
            status=RequirementStatus.TODO,
            date=date(2026, 1, 1),
            completion_deadline=_today() + _timedelta_days(3),
        ),
    )
    # 子需求继承迭代 deadline（3 天后 -> 剩余 3）
    s = service.create_subitem(
        CreateSubitemInput(
            iteration_id=it.id,
            content="子1",
            status=RequirementStatus.TODO,
            completion_deadline=_today() + _timedelta_days(3),
        ),
    )
    reminders = service.list_todo_reminders(threshold_days=7, show_no_deadline=True)
    assert len(reminders) == 1
    assert reminders[0]["subitem_id"] == s.id
    assert reminders[0]["remaining_days"] == 3

    # 子需求改成 30 天后 -> 超阈值被排除（与迭代 deadline 解耦）
    service.update_subitem(
        s.id,
        UpdateSubitemInput(completion_deadline=_today() + _timedelta_days(30)),
    )
    reminders = service.list_todo_reminders(threshold_days=7, show_no_deadline=True)
    assert reminders == []


# ---------- get_full_snapshot（导出快照） ----------


def test_get_full_snapshot_roundtrip_shape(service: ProjectService) -> None:
    """get_full_snapshot 装配完整快照：modules / iterations+subitems / bugs + 多对多关联，
    所有引用用原始 DB id。"""
    import yaml

    from management_prd.models.bug import CreateBugInput
    from management_prd.models.subitem import CreateSubitemInput
    from management_prd.services.exporter import Exporter

    p = service.create_project("快照项目")
    item = service.create_requirement(
        p.id,
        CreateRequirementInput(
            module_names=["主界面", "账户"],
            feature="登录",
            content="实现登录",
            status=RequirementStatus.DONE,
            date=date(2026, 1, 5),
            completion_deadline=date(2026, 1, 10),
        ),
    )
    service.create_subitem(
        CreateSubitemInput(
            iteration_id=item.id,
            content="微信登录",
            status=RequirementStatus.DONE,
            completion_deadline=date(2026, 1, 8),
        )
    )
    service.create_subitem(
        CreateSubitemInput(
            iteration_id=item.id,
            content="手机验证码",
            status=RequirementStatus.TODO,
        )
    )
    # 建 bug 关联到上面的迭代
    from management_prd.services.bug_service import BugService

    bug_service = BugService(service._db)
    bug_service.create_bug(
        p.id,
        CreateBugInput(
            module_names=["主界面"],
            content="登录回调崩溃",
            level="P1",
            linked_iteration_id=item.id,
            date=date(2026, 1, 6),
        ),
    )

    snap = service.get_full_snapshot(p.id)
    assert snap.name == "快照项目"
    assert len(snap.modules) == 2  # 主界面、账户
    assert {m.name for m in snap.modules} == {"主界面", "账户"}
    assert len(snap.iterations) == 1
    it = snap.iterations[0]
    assert it.feature == "登录"
    assert it.content == "实现登录"
    assert it.status == RequirementStatus.DONE
    assert it.completion_deadline == date(2026, 1, 10)
    # 多模块 id 全部回填
    assert len(it.modules) == 2
    assert set(it.modules) == {m.id for m in snap.modules}
    # 子需求
    assert len(it.subitems) == 2
    assert it.subitems[0].content == "微信登录"
    assert it.subitems[0].completion_deadline == date(2026, 1, 8)
    assert it.subitems[1].content == "手机验证码"
    assert it.subitems[1].completion_deadline is None
    # bug
    assert len(snap.bugs) == 1
    b = snap.bugs[0]
    assert b.content == "登录回调崩溃"
    assert b.level == "P1"
    assert b.linked == item.id  # 原始 id
    assert b.modules == [m.id for m in snap.modules if m.name == "主界面"]

    # 导出可解析为合法 YAML frontmatter
    text = Exporter().export(snap, include_bug=True)
    fm = yaml.safe_load(text.split("---\n")[1])
    assert fm["format_version"] == 1
    assert fm["includes_bug"] is True
    assert fm["project"]["name"] == "快照项目"
    assert len(fm["iterations"]) == 1
    assert len(fm["bugs"]) == 1
    assert fm["bugs"][0]["linked"] == item.id
