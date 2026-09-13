"""舌象观察记录（F9 YOLO 舌苔识别的历史链路）"""
from datetime import datetime

from sqlalchemy import Column, DateTime, Float, Integer, String

from app.core.database import Base
from app.core.data_protection import EncryptedJSON, EncryptedText


class TongueRecord(Base):
    __tablename__ = "tongue_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(64), nullable=False, index=True)
    status = Column(String(20), default="detected", comment="detected=检测 / demo=演示规则观察")
    # 观察结论（非诊断措辞）
    tongue_color = Column(String(100), default="", comment="舌色观察（偏红/淡红/颜色不明确）")
    coat = Column(String(100), default="", comment="苔质观察（偏厚/偏薄）")
    confidence = Column(Float, default=0)
    box = Column(EncryptedJSON, default=list, comment="检测框 [x1,y1,x2,y2]")
    image_url = Column(EncryptedText, default="", comment="受保护图片访问接口 URL")
    image_bucket = Column(String(100), default="health-tongue")
    image_object_name = Column(EncryptedText, default="", comment="加密 MinIO 对象名")
    image_mime = Column(String(80), default="image/jpeg")
    note = Column(String(500), default="", comment="用户备注")
    detail = Column(EncryptedJSON, default=dict, comment="分析结果快照")
    created_at = Column(DateTime, default=datetime.now, index=True)
