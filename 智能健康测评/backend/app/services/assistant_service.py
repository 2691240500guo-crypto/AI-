import json
import logging
import re
from datetime import datetime
from functools import partial
from typing import Callable, TypedDict

from langgraph.graph import END, START, StateGraph
from sqlalchemy.orm import Session

from app.models.assistant import AssistantConversation, AssistantMemory, AssistantMessage, UserProfile, AgentRun, AgentStep
from app.services.llm_client import get_llm
from app.services.meal_service import parse_meal_text

logger = logging.getLogger("assistant_service")

DISCLAIMER = "以上建议仅供健康观察和生活方式参考，不能替代医生诊断；如有不适请及时就医。"

ROUTE_KEYWORDS = {
    "nutrition": ("吃", "饮食", "营养", "热量", "食谱", "蛋白", "维生素", "餐", "减脂", "减重", "增肌"),
    "exercise": ("运动", "步数", "跑步", "健身", "心率", "锻炼", "训练"),
    "sleep": ("睡眠", "睡不着", "失眠", "深睡", "作息", "熬夜"),
}

MAX_AGENT_STEPS = 4


class AgentRunState(TypedDict):
    message: str
    profile: dict
    history: list[dict]
    agent_plan: list[str]
    agent_outputs: list[dict]
    step_count: int

AGENT_LABELS = {
    "nutrition": "营养师 Agent",
    "exercise": "运动 Agent",
    "sleep": "睡眠 Agent",
    "health": "健康管理 Agent",
}


def _memory_category(content: str) -> str:
    if any(word in content for word in ("过敏", "不耐受")):
        return "allergy"
    if any(word in content for word in ("疾病", "糖尿病", "高血压", "痛风", "哮喘", "胃炎")):
        return "condition"
    if any(word in content for word in ("目标", "减脂", "增肌", "减重")):
        return "goal"
    return "preference"


def extract_explicit_memories(message: str) -> list[dict[str, str]]:
    """Extract only an explicit ``记住`` request; ordinary chat is never retained as memory."""
    match = re.search(r"(?:请)?记住[：:\s]*(.+)$", (message or "").strip())
    if not match:
        return []
    content = match.group(1).strip(" \t\r\n，。；;。")[:500]
    if not content:
        return []
    return [{"category": _memory_category(content), "content": content}]


def list_memories(db: Session, user_id: str, limit: int = 20) -> list[dict]:
    rows = (db.query(AssistantMemory)
            .filter_by(user_id=user_id)
            .order_by(AssistantMemory.updated_at.desc(), AssistantMemory.id.desc())
            .limit(min(max(limit, 1), 100)).all())
    return [{"id": row.id, "category": row.category, "content": row.content,
             "source": row.source, "created_at": row.created_at.isoformat() if row.created_at else None,
             "updated_at": row.updated_at.isoformat() if row.updated_at else None} for row in rows]


def remember(db: Session, user_id: str, content: str, category: str | None = None,
             source: str = "user") -> dict:
    content = (content or "").strip()[:500]
    if not content:
        raise ValueError("记忆内容不能为空")
    category = category if category in {"allergy", "condition", "goal", "preference"} else _memory_category(content)
    existing = (db.query(AssistantMemory).filter_by(user_id=user_id, category=category).all())
    for row in existing:
        if row.content == content:
            return {"id": row.id, "category": row.category, "content": row.content,
                    "source": row.source, "created_at": row.created_at.isoformat() if row.created_at else None,
                    "updated_at": row.updated_at.isoformat() if row.updated_at else None}
    row = AssistantMemory(user_id=user_id, category=category, content=content, source=source)
    db.add(row)
    db.commit()
    db.refresh(row)
    return {"id": row.id, "category": row.category, "content": row.content,
            "source": row.source, "created_at": row.created_at.isoformat() if row.created_at else None,
            "updated_at": row.updated_at.isoformat() if row.updated_at else None}


def capture_explicit_memories(db: Session, user_id: str, message: str) -> list[dict]:
    captured = []
    for candidate in extract_explicit_memories(message):
        captured.append(remember(db, user_id, candidate["content"], candidate["category"], "chat"))
    return captured


def route_agent(message: str) -> str:
    text = message.lower()
    for agent, keywords in ROUTE_KEYWORDS.items():
        if any(keyword in text for keyword in keywords):
            return agent
    return "health"


def route_agents(message: str) -> list[str]:
    """Return the relevant specialists in a stable order, capped to prevent loops.

    The health-management agent synthesizes advice only for genuinely cross-domain questions.
    The returned execution plan and trace keep routing inspectable while the LangGraph state
    machine provides a bounded hand-off protocol.
    """
    text = message.lower()
    selected = [
        agent for agent, keywords in ROUTE_KEYWORDS.items()
        if any(keyword in text for keyword in keywords)
    ]
    if not selected:
        return ["health"]
    if len(selected) > 1:
        selected.append("health")
    return selected[:MAX_AGENT_STEPS]


def run_agent_workflow(
    *,
    message: str,
    profile: dict,
    history: list[dict],
    agent_plan: list[str],
    invoke: Callable[[str, str, dict, list[dict], list[dict]], str | dict],
) -> AgentRunState:
    """Execute a bounded LangGraph state machine and retain each specialist hand-off."""
    bounded_plan = agent_plan[:MAX_AGENT_STEPS] or ["health"]
    workflow = StateGraph(AgentRunState)

    for agent in bounded_plan:
        def run_node(state: AgentRunState, current_agent: str = agent) -> dict:
            prior_outputs = state["agent_outputs"]
            result = invoke(
                current_agent,
                state["message"],
                state["profile"],
                state["history"],
                prior_outputs,
            )
            payload = result if isinstance(result, dict) else {"answer": str(result)}
            answer = payload.get("answer", "")
            return {
                "agent_outputs": [*prior_outputs, {"agent": current_agent, **payload, "answer": answer}],
                "step_count": state["step_count"] + 1,
            }

        workflow.add_node(agent, run_node)

    workflow.add_edge(START, bounded_plan[0])
    for current, next_agent in zip(bounded_plan, bounded_plan[1:]):
        workflow.add_edge(current, next_agent)
    workflow.add_edge(bounded_plan[-1], END)

    app = workflow.compile()
    return app.invoke({
        "message": message,
        "profile": profile,
        "history": history,
        "agent_plan": bounded_plan,
        "agent_outputs": [],
        "step_count": 0,
    })


def _allergy_excluded_foods(allergies: str) -> list[str]:
    """把画像里的过敏/不耐受描述映射为需要从图谱推荐中排除的食物名。"""
    text = (allergies or "").replace("、", " ").replace("，", " ").replace(",", " ")
    if text.strip() in ("", "无"):
        return []
    mapping = {
        "海鲜": ["鱼虾", "深海鱼", "牡蛎", "紫菜", "海带", "鲈鱼", "鳕鱼"],
        "乳糖": ["牛奶", "酸奶"],
        "坚果": ["坚果", "芝麻", "亚麻籽"],
        "蛋类": ["鸡蛋", "蛋黄"],
        "蛋": ["鸡蛋", "蛋黄"],
        "麸质": ["馒头", "面条", "面包"],
        "大豆": ["黄豆", "豆腐"],
        "芒果": ["芒果"],
    }
    out: list[str] = []
    for key, foods in mapping.items():
        if key in text:
            out.extend(foods)
    return list(dict.fromkeys(out))


def _graph_context(profile: dict, message: str,
                   enabled: bool | None = None) -> tuple[str, list[dict], bool]:
    """用营养知识图谱补充结构化上下文：疾病 → 多跳推理 → 宜吃/忌口。

    与 Milvus 向量检索互补：向量检索召回的是文档片段（非结构化），图谱给出的是
    确定的三元组链路（疾病 ← 营养素 ← 食物），可解释、可溯源。
    相比单跳查询，这里走 reason_path：
      - 正向链路（降低风险/缓解）→ 宜吃清单
      - 反向链路（加重）→ 忌口清单
      - 用户过敏/不耐受 → 从推荐中剔除并单独说明，而不是静默消失
    图谱不可用或未命中时静默降级，不影响问答主链路。

    enabled：请求级覆盖值。None 表示跟随 .env 里的 GRAPH_RAG_ENABLED 默认值；
    传 True/False 可在单次提问上强制开关（前端「AI 问答 · 图谱增强」开关），
    用于演示「接入图谱前 / 后」的回答质量对比。
    返回的第三个元素是本次生效的开关值，供前端标注这条回答是否走了图谱。
    """
    from app.core.config import settings
    use_graph = settings.GRAPH_RAG_ENABLED if enabled is None else bool(enabled)
    if not use_graph:
        return "", [], False

    conditions = str(profile.get("conditions") or "").strip()
    allergies = str(profile.get("allergies") or "").strip()
    # 画像里的基础疾病优先，其次从本轮提问里识别（如「我有高血压，晚上吃什么」）
    queries = [q for q in (conditions, message) if q and q.strip() not in ("", "无")]
    if not queries:
        return "", [], True

    exclude_foods = _allergy_excluded_foods(allergies)
    max_n = settings.GRAPH_RAG_MAX_DISEASES
    try:
        from app.utils.neo4j_client import get_neo4j
        client = get_neo4j()
        seen: set[str] = set()
        hits: list[dict] = []
        for query in queries:
            for name in client._match_diseases(query, limit=max_n):
                if name in seen:
                    continue
                path = client.reason_path(name, exclude_foods=exclude_foods)
                if not path:
                    continue
                seen.add(name)
                hits.append(path)
                if len(hits) >= max_n:
                    break
            if len(hits) >= max_n:
                break
    except Exception as exc:  # noqa: BLE001
        logger.info("knowledge graph unavailable: %s", exc)
        return "", [], True

    if not hits:
        return "", [], True

    blocks = []
    for h in hits:
        lines = [f"疾病「{h['disease']}」：干预建议 {h.get('advice') or '—'}"]
        if h.get("hops"):
            lines.append("  推理链：" + "；".join(h["hops"][:4]))
        if h.get("recommended"):
            lines.append("  宜吃（图谱正向链路推荐）：" + "、".join(h["recommended"][:8]))
        if h.get("taboo"):
            lines.append("  忌口（图谱禁忌/加重链路）："
                         + "、".join(f"{t['food']}（{t.get('note') or '不利控制'}）"
                                     if t.get("note") else t["food"]
                                     for t in h["taboo"][:6]))
        if h.get("excluded"):
            lines.append("  已剔除（用户过敏/不耐受）："
                         + "、".join(e["food"] for e in h["excluded"]))
        blocks.append("\n".join(lines))
    context = (
        "以下是营养知识图谱给出的结构化结论（含多跳推理链路），可作为饮食建议的依据"
        "（仍不能当作诊断结论）；其中的「忌口」必须严格遵守，不得出现在推荐食谱里。"
        "若与知识库片段冲突，以图谱结论为准并说明依据：\n" + "\n".join(blocks)
    )
    return context, hits, True


def _invoke_specialist(
    agent: str,
    message: str,
    profile: dict,
    history: list[dict],
    prior_outputs: list[dict],
    use_graph: bool | None = None,
) -> dict:
    handoff = "\n".join(
        f"{AGENT_LABELS[item['agent']]}：{item['answer']}" for item in prior_outputs
    )
    role = (
        "汇总前序专科建议，处理冲突并给出一份简洁、可执行的综合建议。"
        if agent == "health" and prior_outputs
        else "根据用户画像和上下文给出简洁、可执行的专科建议。"
    )
    system = (
        f"你是{AGENT_LABELS[agent]}，服务中国用户。{role}"
        "不要诊断、开处方或夸大功效；信息不足时先提出一个关键追问。"
        f"{DISCLAIMER}"
    )
    # Every health question gets one bounded knowledge-tool call. Offline Milvus is treated as
    # an unavailable optional tool, so the assistant still answers with an explicit empty trace.
    knowledge_hits = []
    try:
        from app.utils.milvus_client import get_milvus
        knowledge_hits = get_milvus().search(message, top_k=5) or []
    except Exception as exc:  # noqa: BLE001
        logger.info("knowledge search unavailable: %s", exc)

    sources = []
    knowledge_context = ""
    if knowledge_hits:
        sources = [{"source": item.get("source", "知识库"), "file_id": item.get("file_id"),
                    "distance": item.get("distance")} for item in knowledge_hits]
        knowledge_context = "\n\n".join(
            f"[知识库片段 {idx}] {item.get('content', '')[:1800]}"
            for idx, item in enumerate(knowledge_hits, 1)
        )

    # 图谱检索：结构化知识（疾病→干预建议→推荐营养素/食物），与向量检索互补
    # use_graph 为请求级开关（None 时跟随 .env 默认值）：关闭后图谱既不进 prompt，
    # 也不出现在「参考来源」里，形成干净的「未接入图谱」基线，便于演示对比。
    graph_context, graph_hits, graph_enabled = _graph_context(profile, message, use_graph)
    graph_diseases = [h["disease"] for h in graph_hits]
    graph_sources = [{"source": f"营养知识图谱·{h['disease']}"} for h in graph_hits]

    messages = [
        {"role": "system", "content": system},
        {"role": "system", "content": f"用户画像：{json.dumps(profile, ensure_ascii=False)}"},
    ]
    if handoff:
        messages.append({"role": "system", "content": f"前序 Agent 交接：\n{handoff}"})
    if graph_context:
        messages.append({"role": "system", "content": graph_context})
    if knowledge_context:
        messages.append({"role": "system", "content": (
            "以下是知识库检索结果。仅在与问题相关时引用，不能把片段当作诊断结论：\n" + knowledge_context
        )})
    messages.extend(history)
    messages.append({"role": "user", "content": message})
    # 工具调用轨迹：向量检索 + 图谱检索（前端会展示「参考来源」）
    all_sources = sources + graph_sources
    tool_calls = [
        {"name": "knowledge_search", "top_k": 5, "result_count": len(knowledge_hits)},
    ]
    if graph_hits:
        tool_calls.append({
            "name": "graph_search",
            "diseases": [h["disease"] for h in graph_hits],
            "result_count": len(graph_hits),
        })
    try:
        answer = get_llm().chat(messages, temperature=0.5, max_tokens=1200)
        if all_sources:
            labels = "；".join(dict.fromkeys(item["source"] for item in all_sources if item.get("source")))
            if labels:
                answer = f"{answer.rstrip()}\n\n参考来源：{labels}"
        return {"answer": answer, "tool_calls": tool_calls, "sources": all_sources,
                "graph_enabled": graph_enabled, "graph_diseases": graph_diseases}
    except Exception as exc:  # noqa: BLE001
        logger.warning("%s agent LLM failed: %s", agent, exc)
        return {"answer": "我暂时无法连接智能服务。你可以先记录饮食、运动和睡眠情况，稍后再试。",
                "tool_calls": tool_calls,
                "sources": all_sources, "error": str(exc)[:240],
                "graph_enabled": graph_enabled, "graph_diseases": graph_diseases}


def persist_agent_run(db: Session, user_id: str, conversation_id: int, message: str,
                      workflow_state: AgentRunState, final_answer: str) -> AgentRun:
    """Write the LangGraph envelope and each hand-off for historical replay."""
    run = AgentRun(conversation_id=conversation_id, user_id=user_id, request_text=message,
                   final_answer=final_answer, agent_plan=workflow_state.get("agent_plan", []),
                   status="completed", started_at=datetime.now(), completed_at=datetime.now())
    db.add(run)
    db.flush()
    for index, item in enumerate(workflow_state.get("agent_outputs", []), 1):
        db.add(AgentStep(
            run_id=run.id, step_index=index, agent=item.get("agent", "health"),
            input_summary=message[:1000], output_text=item.get("answer", ""),
            tool_calls=item.get("tool_calls", []), sources=item.get("sources", []),
            status="failed" if item.get("error") else "completed", error=item.get("error", ""),
        ))
    db.commit()
    db.refresh(run)
    return run


def _profile_dict(profile: UserProfile | None) -> dict:
    if not profile:
        return {}
    return {field: getattr(profile, field) for field in (
        "user_id", "user_name", "sex", "age", "height_cm", "weight_kg",
        "goal", "allergies", "conditions", "preferences",
    )}


def upsert_profile(db: Session, user_id: str, values: dict) -> UserProfile:
    profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    if not profile:
        profile = UserProfile(user_id=user_id)
        db.add(profile)
    for key, value in values.items():
        if hasattr(profile, key) and value is not None:
            setattr(profile, key, value)
    db.commit()
    db.refresh(profile)
    return profile


def _conversation(db: Session, user_id: str, conversation_id: int | None):
    if conversation_id:
        conversation = db.query(AssistantConversation).filter_by(
            id=conversation_id, user_id=user_id).first()
        if conversation:
            return conversation
    conversation = AssistantConversation(user_id=user_id)
    db.add(conversation)
    db.commit()
    db.refresh(conversation)
    return conversation


def _looks_like_plan_request(message: str) -> bool:
    """识别“帮我制定/生成一份(减脂/增肌)饮食计划/食谱”类意图。"""
    t = (message or "").strip()
    if any(w in t for w in (
        "饮食计划", "减脂计划", "增肌计划", "食谱", "一周菜单", "7天菜单", "七天菜单",
        "减肥餐", "减脂餐", "增肌餐", "健康餐",
    )):
        return True
    return ("计划" in t or "制定" in t or "生成" in t or "安排" in t or "定制" in t) and any(
        w in t for w in ("饮食", "餐", "减脂", "增肌", "瘦", "减重", "食谱", "菜单", "热量", "怎么吃", "一日三餐")
    )


def _looks_like_meal_log(message: str) -> bool:
    """识别“帮我记(一下/录)：早餐吃了……”类记录意图。"""
    t = (message or "").strip()
    if re.search(r"(帮我记|帮我记录|记一下|记录一下)", t):
        return True
    if re.search(r"(早餐|午餐|晚餐|加餐|早饭|午饭|晚饭|宵夜|夜宵).{0,10}(吃了|喝了|吃的|用餐)", t):
        return True
    return False


def _extract_goal(message: str, profile_goal: str) -> str:
    if ("减" in message) or ("瘦" in message):
        return "减脂"
    if ("增" in message) or ("肌" in message):
        return "增肌"
    return profile_goal or "保持健康"


def _narrate_plan(plan: dict, profile: dict, message: str) -> str | None:
    """把规则引擎算好的饮食计划交给 LLM「讲」出来。

    计划数据（热量 / 三餐 / 禁忌 / 购物清单）仍由 plan_service 结构化产出，可核对、可复现；
    这里只负责组织语言，避免出现「秒回的模板话术」，也让每句回答都真的经过模型。
    LLM 不可用时返回 None，由调用方回退模板文案，保证离线演示不中断。
    """
    try:
        from app.services.llm_client import get_llm
        recipes = "、".join(
            f"{r.get('meal')}：{r.get('name')}（{r.get('kcal')} kcal）"
            for r in plan.get("recipes", []))
        safe_profile = {k: profile.get(k) for k in
                        ("user_name", "sex", "age", "height_cm", "weight_kg", "goal",
                         "allergies", "conditions", "preferences")}
        payload = {
            "档位": plan.get("set_label"),
            "每日目标热量": plan.get("calories_target"),
            "天数": plan.get("days"),
            "三餐安排": recipes,
            "购物清单项数": len(plan.get("shopping_list") or []),
            "必须避开的过敏原/禁忌": plan.get("safety_notes") or [],
            "图谱正向推荐食材": plan.get("graph_suitable") or {},
        }
        system = (
            f"你是{AGENT_LABELS['nutrition']}，服务中国用户。"
            "接下来这段内容是系统已经算好的饮食计划数据，请把它讲给用户听："
            "先用一句话结合用户画像说明为什么这样安排，再分早/午/晚讲三餐，"
            "然后明确提醒需要避开的过敏原与饮食禁忌，最后说明购物清单与「一键应用」入口。\n"
            "硬性要求：\n"
            "1. 所有热量数字与食物名称必须与给定数据完全一致，不得新增、替换或省略任何食物；\n"
            "2. 「必须避开的过敏原/禁忌」必须严格遵守并明确告知，不得出现在推荐里；\n"
            "3. 不做诊断、不开处方、不承诺疗效；\n"
            "4. 中文口语化，260 字以内，不要使用 Markdown 标题符号（#、**）与表格。"
        )
        user = (
            f"【用户画像】{json.dumps(safe_profile, ensure_ascii=False)}\n"
            f"【用户刚说的话】{message}\n"
            f"【已生成的饮食计划】{json.dumps(payload, ensure_ascii=False)}"
        )
        answer = get_llm().chat(
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            temperature=0.5,
            max_tokens=700,
        )
        answer = (answer or "").strip().lstrip("#").strip()
        return answer or None
    except Exception as exc:  # noqa: BLE001
        logger.warning("plan narration via LLM failed: %s", exc)
        return None


def chat(db: Session, user_id: str, message: str, conversation_id: int | None = None,
         use_graph: bool | None = None) -> dict:
    """对话主入口。

    use_graph：请求级图谱增强开关（None = 跟随 .env 的 GRAPH_RAG_ENABLED）。
    前端「图谱增强」开关切换后随每次提问下发，便于演示接入图谱前后的回答差异。
    """
    conversation = _conversation(db, user_id, conversation_id)
    profile = db.query(UserProfile).filter_by(user_id=user_id).first()
    captured_memories = capture_explicit_memories(db, user_id, message)
    profile_context = _profile_dict(profile)
    profile_context["long_term_memories"] = [
        {"category": item["category"], "content": item["content"]}
        for item in list_memories(db, user_id)
    ]

    def save_turn(answer: str, agent: str) -> None:
        db.add(AssistantMessage(conversation_id=conversation.id, role="user", content=message, agent=agent))
        db.add(AssistantMessage(conversation_id=conversation.id, role="assistant", content=answer, agent=agent))
        conversation.title = message[:40]
        conversation.updated_at = datetime.now()
        db.commit()

    # ---- 1) 饮食计划意图：对话内直接生成个性化计划（返回结构化 plan 供前端渲染卡片）----
    if _looks_like_plan_request(message):
        goal = _extract_goal(message, profile.goal if profile else "")
        try:
            from app.services.plan_service import upsert_plan
            plan = upsert_plan(db, user_id, goal, 7)
        except Exception as exc:  # noqa: BLE001
            logger.warning("assistant plan build failed: %s", exc)
            plan = None
        if plan:
            # 先让 LLM 结合画像/禁忌把计划讲出来；失败再回退模板，保证离线也能演示
            narration = _narrate_plan(plan, profile_context, message)
            narration_source = "llm" if narration else "template"
            if narration:
                answer = narration
            else:
                recipes_brief = " / ".join(
                    f"{r['meal']}：{r['name']}（{r['kcal']} kcal）" for r in plan["recipes"])
                answer = (
                    f"好呀，已结合你的健康画像生成「{plan['set_label']}」饮食计划，"
                    f"目标热量 {plan['calories_target']} kcal/天：\n{recipes_brief}\n"
                    f"购物清单共 {len(plan['shopping_list'])} 项。计划已提交营养师审核，"
                    f"点下方卡片可一键应用到「饮食计划」页查看完整菜单与清单。"
                )
            if DISCLAIMER not in answer:
                answer = f"{answer.rstrip()}\n\n{DISCLAIMER}"
            save_turn(answer, "nutrition")
            return {
                "conversation_id": conversation.id, "agent": "nutrition",
                "agent_label": AGENT_LABELS["nutrition"], "answer": answer, "plan": plan,
                "graph_enabled": None,   # 结构化分支不走 LLM 图谱上下文，前端不标注
                "narration_source": narration_source,   # llm / template，前端标注「LLM 生成」
                "captured_memories": captured_memories,
            }

    # ---- 2) 记饮食意图：把一句话描述转成可确认草稿（确认走 /meals/confirm 落库）----
    if _looks_like_meal_log(message):
        draft = parse_meal_text(message)
        if draft.get("status") == "ready" and draft.get("items"):
            brief = "、".join(f"{item['name']}约{item.get('grams', 0)}g" for item in draft["items"])
            answer = (
                f"帮你记下了这餐：{brief}，合计约 {draft.get('calories', 0)} kcal。"
                "请核对下方克重与热量，确认后保存进今日饮食记录。"
            )
            save_turn(answer, "nutrition")
            return {
                "conversation_id": conversation.id, "agent": "nutrition",
                "agent_label": AGENT_LABELS["nutrition"], "answer": answer, "meal_draft": draft,
                "graph_enabled": None,   # 结构化分支不走 LLM 图谱上下文，前端不标注
                "captured_memories": captured_memories,
            }

    # ---- 3) 普通多轮对话（LangGraph 专科协作 + 用户画像 + 最近上下文）----
    execution_plan = route_agents(message)
    recent = (db.query(AssistantMessage)
              .filter_by(conversation_id=conversation.id)
              .order_by(AssistantMessage.created_at.desc())
              .limit(12).all())
    history = [{"role": item.role, "content": item.content} for item in reversed(recent)]
    workflow_state = run_agent_workflow(
        message=message,
        profile=profile_context,
        history=history,
        agent_plan=execution_plan,
        # 请求级开关用 partial 绑定，run_agent_workflow 的 invoke 协议保持不变
        invoke=partial(_invoke_specialist, use_graph=use_graph),
    )
    outputs = workflow_state["agent_outputs"]
    agent = outputs[-1]["agent"]
    answer = outputs[-1]["answer"]
    if DISCLAIMER not in answer:
        answer = f"{answer.rstrip()}\n\n{DISCLAIMER}"
    save_turn(answer, agent)
    persist_agent_run(db, user_id, conversation.id, message, workflow_state, answer)
    # 回传本次回答的图谱状态，供前端标注「已接入图谱 / 未接图谱（基线）」
    graph_enabled = outputs[-1].get("graph_enabled") if outputs else None
    graph_diseases = list(dict.fromkeys(
        name for item in outputs for name in (item.get("graph_diseases") or [])
    ))
    return {"conversation_id": conversation.id, "agent": agent,
            "agent_label": AGENT_LABELS[agent], "agent_plan": execution_plan,
            "agent_trace": outputs, "max_agent_steps": MAX_AGENT_STEPS,
            "step_count": workflow_state["step_count"], "answer": answer,
            "graph_enabled": graph_enabled, "graph_diseases": graph_diseases,
            "captured_memories": captured_memories}
