"""知识图谱相关路由：Neo4j 预置图谱 初始化/查询/可视化数据"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.schemas.common import ApiResponse
from app.utils.neo4j_client import get_neo4j

logger = logging.getLogger("graph_router")

router = APIRouter(prefix="/api/graph", tags=["营养知识图谱"])


@router.post("/init", response_model=ApiResponse)
def init_graph(reset: bool = False):
    """导入预置营养知识图谱（幂等）"""
    try:
        result = get_neo4j().init_preset_graph(reset=reset)
        return ApiResponse(status=200, message="图谱初始化完成", data=result)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"图谱初始化失败: {e}")


@router.get("/data", response_model=ApiResponse)
def graph_data(
    limit: int = Query(300, le=1000),
    disease: Optional[str] = Query(None, description="只返回该疾病的两跳子图"),
):
    """图谱可视化数据（ECharts graph 格式）

    仅返回营养图谱三类节点；传 disease 时返回该疾病 + 关联营养素 + 推荐食物的子图。
    """
    try:
        data = get_neo4j().get_graph_data(limit=limit, disease=disease or None)
        return ApiResponse(status=200, message="success", data=data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"图谱读取失败: {e}")


@router.get("/stats", response_model=ApiResponse)
def graph_stats():
    """营养图谱规模统计（食物 / 营养素 / 疾病）"""
    try:
        return ApiResponse(status=200, message="success", data=get_neo4j().graph_stats())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"图谱统计失败: {e}")


@router.get("/diseases", response_model=ApiResponse)
def disease_list():
    """疾病列表（下拉选择用）"""
    try:
        return ApiResponse(status=200, message="success",
                           data=get_neo4j().get_diseases())
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"读取疾病列表失败: {e}")


@router.get("/disease/{name}", response_model=ApiResponse)
def disease_detail(name: str):
    """按疾病查询关联营养素/食物/建议"""
    try:
        rows = get_neo4j().search_disease(name)
        if not rows:
            raise HTTPException(status_code=404, detail=f"图谱中无「{name}」节点")
        return ApiResponse(status=200, message="success", data=rows[0])
    except HTTPException:
        raise
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/assess-hint", response_model=ApiResponse)
def assess_graph_hint(disease: str = Query(..., description="测评中命中的疾病描述，支持自由文本")):
    """测评结果关联图谱：根据疾病描述给出营养干预提示（可能命中多个疾病）"""
    try:
        rows = get_neo4j().search_disease(disease)
        if not rows:
            return ApiResponse(status=200, message="success",
                               data={"hint": None, "hints": []})
        hints = [{
            "disease": row["disease"],
            "advice": row["advice"],
            "nutrients": [n["nutrient"] for n in row["nutrients"] if n.get("nutrient")],
            "foods": row["foods"],
            "suitable": row.get("suitable", []),
            "taboo": row.get("taboo", []),
        } for row in rows]
        return ApiResponse(status=200, message="success",
                           data={"hint": hints[0], "hints": hints})
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"查询失败: {e}")


@router.get("/reason", response_model=ApiResponse)
def graph_reason(
    disease: str = Query(..., description="疾病描述，支持自由文本"),
    exclude: Optional[str] = Query(None, description="需排除的食物，逗号分隔（如过敏原）"),
):
    """多跳推理：疾病 → 推荐营养素 → 食物，叠加直接宜/忌关系。

    返回可解释推理链（hops）+ 推荐食物 + 规避食物 + 被排除项，
    用于演示图谱推理能力，也被 AI 问答的知识上下文复用。
    """
    try:
        exclude_foods = [x.strip() for x in (exclude or "").split(",") if x.strip()]
        data = get_neo4j().reason_path(disease, exclude_foods=exclude_foods)
        if not data:
            return ApiResponse(status=200, message="success", data={"found": False})
        data["found"] = True
        return ApiResponse(status=200, message="success", data=data)
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"推理失败: {e}")


@router.get("/relations", response_model=ApiResponse)
def graph_relations(limit: int = Query(200, le=500)):
    """全部「食物-适宜/禁忌-疾病」直接关系（展示规则由图谱维护）"""
    try:
        return ApiResponse(status=200, message="success",
                           data=get_neo4j().graph_relations(limit=limit))
    except Exception as e:  # noqa: BLE001
        raise HTTPException(status_code=500, detail=f"读取关系失败: {e}")


@router.get("/rag-status", response_model=ApiResponse)
def graph_rag_status():
    """AI 问答「图谱增强」的默认开关状态（只读）。

    值来自 .env 的 GRAPH_RAG_ENABLED。真正的开关由前端随每次提问下发
    （ChatRequest.use_graph），这个接口只用于前端首次进入时对齐默认值，
    避免页面开关与后端默认状态漂移。
    """
    from app.core.config import settings
    return ApiResponse(status=200, message="success", data={
        "enabled": bool(settings.GRAPH_RAG_ENABLED),
        "max_diseases": settings.GRAPH_RAG_MAX_DISEASES,
    })
