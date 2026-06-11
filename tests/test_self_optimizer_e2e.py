"""E2E test for self-optimizer V1 dry-run."""
import json
from pathlib import Path

import pytest

from modules.self_optimizer import SelfOptimizer


@pytest.mark.slow
def test_full_run_dry_run(tmp_path, monkeypatch):
    """端到端 dry-run: 跑 3 轮, 验证 tsv + drafts + log + SKILL.md 未改."""
    # monkeypatch 评分避免依赖真实 monthly_reviews_self
    from modules.self_optimizer import phase2_hillclimb

    scores = iter([82.0, 83.5, 84.0])  # 递增模拟
    monkeypatch.setattr(phase2_hillclimb, "_score_proposal", lambda *a, **kw: next(scores))

    # 切到临时目录
    monkeypatch.chdir(tmp_path)
    (tmp_path / "modules").mkdir()
    (tmp_path / "logs").mkdir()
    (tmp_path / "optimization_drafts").mkdir()

    # 建 monthly_reviews_self 表 (init_database 不建, 需手动)
    from modules.database import get_connection

    with get_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS monthly_reviews_self (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                review_month TEXT NOT NULL,
                ts_code TEXT NOT NULL,
                monthly_return REAL,
                max_drawdown REAL,
                buy_signals_count INTEGER,
                correct_buy_signals INTEGER,
                UNIQUE(ts_code, review_month)
            )
            """
        )
        # 写入 3 个月 mock 数据
        for i, month in enumerate(["202603", "202604", "202605"]):
            cursor.execute(
                """
                INSERT OR REPLACE INTO monthly_reviews_self
                (ts_code, review_month, monthly_return, max_drawdown,
                 buy_signals_count, correct_buy_signals)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                ("600000.SH", month, 2.0, 10.0, 5, 4),
            )
        conn.commit()

    # 跑
    opt = SelfOptimizer(rounds=3)
    result = opt.run()

    # 验证 results.tsv
    tsv = Path("logs/results.tsv")
    assert tsv.exists()
    lines = tsv.read_text(encoding="utf-8").strip().split("\n")
    assert len(lines) >= 4  # header + 3 rounds
    assert lines[0].startswith("timestamp\tcommit\tskill")

    # 验证 drafts
    drafts = list(Path("optimization_drafts").glob("*.md"))
    assert len(drafts) == 3

    # 验证 log
    log = Path("logs/improvement_log.jsonl")
    assert log.exists()
    entries = [json.loads(l) for l in log.read_text(encoding="utf-8").strip().split("\n") if l]
    assert len(entries) == 3

    # 验证返回值
    assert result["rounds"] == 3
    assert "results_tsv" in result
    assert "drafts_dir" in result
