"""تست موتور ادد — تاخیرهای انسانی و کش لیست ممنوعه"""
import random
import statistics

import add_engine


def test_human_delay_bounds():
    for mode, (lo, hi) in {
        "ultra": (3, 40),
        "fast": (10, 140),
        "safe": (35, 320),
    }.items():
        vals = [add_engine.human_delay(mode) for _ in range(500)]
        assert min(vals) >= lo, f"{mode}: min {min(vals)} < {lo}"
        assert max(vals) <= hi, f"{mode}: max {max(vals)} > {hi}"


def test_human_delay_avg_in_range():
    vals = [add_engine.human_delay("fast") for _ in range(500)]
    avg = statistics.mean(vals)
    # میانگین باید در بازه پایه + حاشیه jitter باشد (نه خیلی بالا، نه خیلی پایین)
    assert 20 <= avg <= 55, f"avg {avg}"


def test_human_break_bounds():
    for mode, (lo, hi) in {
        "ultra": (45, 120),
        "fast": (60, 180),
        "safe": (120, 300),
    }.items():
        for _ in range(50):
            b = add_engine.human_break_seconds(mode)
            assert lo <= b <= hi, f"{mode}: {b}"


def test_blocked_cache(monkeypatch):
    calls = {"n": 0}

    def fake_blocked_ids():
        calls["n"] += 1
        return {1, 2, 3}

    monkeypatch.setattr(add_engine._db, "get_blocked_user_ids", fake_blocked_ids)
    add_engine.reset_cache_for_tests()

    s1 = add_engine.get_blocked_ids_cached()
    s2 = add_engine.get_blocked_ids_cached()
    assert s1 == s2 == {1, 2, 3}
    assert calls["n"] == 1, "کش باید از کوئری دوم جلوگیری کند"

    add_engine.invalidate_blocked_cache()
    add_engine.get_blocked_ids_cached()
    assert calls["n"] == 2, "بعد از invalidate باید دوباره کوئری بزند"


def test_mark_added_local(monkeypatch):
    monkeypatch.setattr(add_engine._db, "get_blocked_user_ids", lambda: {7})
    add_engine.reset_cache_for_tests()
    s = add_engine.get_blocked_ids_cached()
    add_engine.mark_added_local(99)
    assert 99 in s
    add_engine.reset_cache_for_tests()


def test_prefer_addable_members_username_first():
    members = [
        {"user_id": 1, "username": "", "phone": ""},
        {"user_id": 2, "username": "ali", "phone": ""},
        {"user_id": 3, "username": "", "phone": "+98912"},
    ]
    ordered = add_engine.prefer_addable_members(members)
    assert [u["user_id"] for u in ordered] == [2, 3, 1]


def test_resolve_add_target_nonzero_gid_wins(monkeypatch):
    monkeypatch.setattr(add_engine._db, "get_config", lambda: {"group_id": -1004316603248, "group_name": "selethon"})
    assert add_engine.resolve_add_target() == -1004316603248


def test_resolve_add_target_name_when_gid_zero(monkeypatch):
    monkeypatch.setattr(add_engine._db, "get_config", lambda: {"group_id": 0, "group_name": "@gament_super_gp"})
    assert add_engine.resolve_add_target() == "@gament_super_gp"


def test_resolve_add_target_title_falls_back_to_history(monkeypatch):
    monkeypatch.setattr(add_engine._db, "get_config", lambda: {"group_id": 0, "group_name": "selethon"})
    monkeypatch.setattr(add_engine._db, "most_used_add_dest", lambda: -1004316603248)
    assert add_engine.resolve_add_target() == -1004316603248


def test_normalize_chat_ref():
    assert add_engine.normalize_chat_ref("-1004316603248") == -1004316603248
    assert add_engine.normalize_chat_ref("https://t.me/gament_super_gp") == "@gament_super_gp"
    assert add_engine.normalize_chat_ref("gament_super_gp") == "@gament_super_gp"


def test_invite_did_not_join():
    class M:
        user_id = 99
    class U:
        missing_invitees = [M()]
    assert add_engine.invite_did_not_join(U(), 99) is True
    assert add_engine.invite_did_not_join(U(), 1) is False
    assert add_engine.invite_did_not_join(None, 99) is False


def test_never_add_again(monkeypatch):
    dna = []
    deleted = []

    monkeypatch.setattr(add_engine._db, "add_do_not_add", lambda uid, reason="": dna.append((uid, reason)) or True)
    monkeypatch.setattr(add_engine._db, "delete_user", lambda uid: deleted.append(uid) or True)
    add_engine.never_add_again(12345, "privacy")
    assert dna == [(12345, "privacy")]
    assert deleted == [12345]
