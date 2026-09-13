"""应用配置：读取 backend/.env 环境变量"""
from pathlib import Path
from functools import lru_cache

from pydantic_settings import BaseSettings

# backend 目录（.env 所在位置）
BACKEND_DIR = Path(__file__).resolve().parent.parent.parent


class Settings(BaseSettings):
    # MySQL
    MYSQL_HOST: str = "127.0.0.1"
    MYSQL_PORT: int = 3306
    MYSQL_USER: str = "root"
    MYSQL_PASSWORD: str = "123456"
    MYSQL_DB: str = "health_assessment"
    DATABASE_URL: str = ""

    # Redis
    REDIS_URL: str = "redis://127.0.0.1:6379/0"

    # MinIO
    MINIO_ENDPOINT: str = "127.0.0.1:9000"
    MINIO_ACCESS_KEY: str = "minio"
    MINIO_SECRET_KEY: str = "12345678"
    MINIO_SECURE: bool = False
    MINIO_BUCKET: str = "health-knowledge"

    # Milvus
    MILVUS_HOST: str = "127.0.0.1"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "knowledge_chunks"

    # Neo4j
    NEO4J_URI: str = "bolt://127.0.0.1:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "12345678"
    # 是否让 AI 问答使用营养知识图谱（RAG 融合图谱结构化结论）。
    # 置 False 可在演示时做「接入图谱前/后」的回答质量对比。
    GRAPH_RAG_ENABLED: bool = True
    GRAPH_RAG_MAX_DISEASES: int = 2

    # SiliconFlow
    SILICONFLOW_API_KEY: str = ""
    LLM_MODEL: str = "deepseek-ai/DeepSeek-V4-Flash"
    EMBEDDING_MODEL: str = "BAAI/bge-m3"
    OCR_MODEL: str = "deepseek-ai/DeepSeek-OCR"
    VISION_MODEL: str = "Qwen/Qwen3-VL-8B-Instruct"
    ASR_MODEL: str = "FunAudioLLM/SenseVoiceSmall"
    TTS_MODEL: str = "FunAudioLLM/CosyVoice2-0.5B"
    # 音色必须是「模型ID:音色名」形式，可选 alex / anna / bella 等
    TTS_VOICE: str = "FunAudioLLM/CosyVoice2-0.5B:alex"
    SILICONFLOW_ASR_URL: str = ""
    SILICONFLOW_TTS_URL: str = ""

    # 舌体 YOLO
    # 舌象多特征检测（14 类，TCM-Tongue 中医师标注数据集训练）
    # 旧权重 models/tongue/yolov8n-tongue.pt 仅 1 类（单舌体定位），已备份为 .bak
    TONGUE_YOLO_MODEL: str = "models/tongue/yolov8n-tcm-tongue.pt"
    TONGUE_YOLO_CONF: float = 0.35
    # 一张舌象最多保留几个检出框（一图多标签，实测平均 2.8 个特征）
    TONGUE_YOLO_MAX_DET: int = 8
    # 已废弃：v1 的弱标签分类头（实测退化为常量输出，v2 改为规则层推导结论）
    TONGUE_CLASSIFIER_MODEL: str = "models/tongue/tongue_classifier.pt"

    # JWT 鉴权
    JWT_SECRET: str = "dev-secret-change-me"
    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_MINUTES: int = 720
    # 健康数据 AES-256-GCM 密钥；生产环境必须通过部署密钥注入（配置变更随热重载生效）
    HEALTH_DATA_ENCRYPTION_KEY: str = ""

    BACKEND_PORT: int = 8000
    FRONTEND_PORT: int = 5173

    @property
    def db_url(self) -> str:
        """SQLAlchemy 连接串"""
        if self.DATABASE_URL:
            return self.DATABASE_URL
        return (
            f"mysql+pymysql://{self.MYSQL_USER}:{self.MYSQL_PASSWORD}"
            f"@{self.MYSQL_HOST}:{self.MYSQL_PORT}/{self.MYSQL_DB}?charset=utf8mb4"
        )

    @property
    def siliconflow_base_url(self) -> str:
        return "https://api.siliconflow.cn/v1"

    class Config:
        env_file = str(BACKEND_DIR / ".env")
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
