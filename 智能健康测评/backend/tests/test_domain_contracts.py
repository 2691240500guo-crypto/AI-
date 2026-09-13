from types import SimpleNamespace

from app.core.security import resolve_scoped_user_id
from app.core.data_protection import decrypt_text, encrypt_text
from app.services.assistant_service import extract_explicit_memories, route_agent, route_agents, run_agent_workflow
from app.services.meal_service import aggregate_nutrition, calculate_daily_score


def test_route_agent_covers_four_specialists():
    assert route_agent("今天吃什么，想控制热量") == "nutrition"
    assert route_agent("我每天走多少步，怎么安排运动") == "exercise"
    assert route_agent("最近睡眠浅，深睡很少") == "sleep"
    assert route_agent("帮我综合看看体检和健康风险") == "health"


def test_route_agents_returns_multiple_relevant_specialists_with_a_cap():
    assert route_agents("我想减脂，但最近睡眠浅，运动也没力气") == [
        "nutrition", "exercise", "sleep", "health"
    ]
    assert route_agents("单独看看深睡") == ["sleep"]


def test_agent_workflow_runs_specialists_then_a_bounded_health_synthesis():
    calls = []

    def invoke(agent, message, profile, history, prior_outputs):
        calls.append((agent, len(prior_outputs)))
        return f"{agent}:{message}"

    state = run_agent_workflow(
        message="饮食、运动和睡眠都想改善",
        profile={"goal": "减脂"},
        history=[],
        agent_plan=["nutrition", "exercise", "sleep", "health"],
        invoke=invoke,
    )

    assert [item[0] for item in calls] == ["nutrition", "exercise", "sleep", "health"]
    assert calls[-1][1] == 3
    assert state["step_count"] == 4
    assert state["agent_outputs"][-1]["agent"] == "health"


def test_scoped_user_id_preserves_identity_for_users_and_allows_admin_review():
    user_request = SimpleNamespace(state=SimpleNamespace(user={"id": "user", "role": "user"}))
    admin_request = SimpleNamespace(state=SimpleNamespace(user={"id": "admin", "role": "admin"}))

    assert resolve_scoped_user_id(user_request, "USER001", allow_admin_claim=True) == "user"
    assert resolve_scoped_user_id(admin_request, "USER001", allow_admin_claim=True) == "USER001"


def test_daily_score_waits_for_enough_daily_intake_and_uses_personal_target():
    assert calculate_daily_score(252, 1348, is_today=True) is None
    assert calculate_daily_score(1348, 1348, is_today=False) == 100
    assert calculate_daily_score(1000, 2000, is_today=False) == 50


def test_aggregate_nutrition_sums_items():
    result = aggregate_nutrition([
        {"name": "米饭", "calories": 232, "protein_g": 4.0, "fat_g": 0.5, "carbs_g": 51.0},
        {"name": "鸡蛋", "calories": 78, "protein_g": 6.3, "fat_g": 5.3, "carbs_g": 0.6},
    ])
    assert result == {"calories": 310.0, "protein_g": 10.3, "fat_g": 5.8, "carbs_g": 51.6}


def test_explicit_memory_only_and_aes_roundtrip():
    assert extract_explicit_memories("最近吃得不错") == []
    assert extract_explicit_memories("请记住：我对虾过敏") == [{"category": "allergy", "content": "我对虾过敏"}]
    encrypted = encrypt_text("我对虾过敏")
    assert encrypted.startswith("enc:v1:")
    assert encrypted != "我对虾过敏"
    assert decrypt_text(encrypted) == "我对虾过敏"
