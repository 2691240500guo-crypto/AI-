"""SiliconFlow 大模型客户端封装（OpenAI 兼容协议）。

统一提供：
  - chat()            对话/报告生成（DeepSeek-V4-Flash 等）
  - embed_documents() 文档向量化（BAAI/bge-m3）
  - ocr_image()       图片 OCR 全解析（DeepSeek-OCR / Qwen3-VL）
"""
import base64
import logging
from typing import List, Optional

from openai import OpenAI

from app.core.config import settings

logger = logging.getLogger("siliconflow")


class SiliconFlowClient:
    def __init__(self):
        self.api_key = settings.SILICONFLOW_API_KEY
        self.base_url = settings.siliconflow_base_url
        if not self.api_key:
            raise RuntimeError("未配置 SILICONFLOW_API_KEY，请在 backend/.env 中填写")
        self.client = OpenAI(api_key=self.api_key, base_url=self.base_url)

    # ---------------- 对话 / 报告生成 ----------------
    def chat(self, messages: List[dict], model: Optional[str] = None,
             temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """通用对话。messages: [{"role": ..., "content": ...}, ...]"""
        resp = self.client.chat.completions.create(
            model=model or settings.LLM_MODEL,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return resp.choices[0].message.content or ""

    def generate_report(self, user_info: dict, nrs_result: dict) -> dict:
        """根据 NRS2002 规则评分结果，生成个性化健康报告（LLM 增强）。"""
        sys_prompt = (
            "你是一名专业的临床营养师。请根据 NRS2002 营养风险筛查的规则评分结果，"
            "为用户撰写一份专业、温暖、可执行的中文个性化健康报告。"
            "要求：\n"
            "1. 结构清晰，分「测评结论」「分项解读」「饮食建议」「复查建议」四部分；\n"
            "2. 结论必须与给定风险等级一致，不得自相矛盾；\n"
            "3. 建议具体可执行（给出食物举例、摄入量等）；\n"
            "4. 语言通俗，避免吓唬用户。"
        )
        user_prompt = (
            f"【用户基本信息】\n{user_info}\n\n"
            f"【NRS2002 规则评分结果】\n{nrs_result}\n\n"
            f"请生成完整报告。"
        )
        return self.chat(
            messages=[
                {"role": "system", "content": sys_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.5,
            max_tokens=2500,
        )

    # ---------------- Embedding ----------------
    def embed_texts(self, texts: List[str],
                    model: Optional[str] = None) -> List[List[float]]:
        """批量向量化（bge-m3 默认 1024 维）"""
        if not texts:
            return []
        resp = self.client.embeddings.create(
            model=model or settings.EMBEDDING_MODEL,
            input=texts,
        )
        # 按输入顺序整理
        ordered = sorted(resp.data, key=lambda x: x.index)
        return [item.embedding for item in ordered]

    def embed_query(self, text: str, model: Optional[str] = None) -> List[float]:
        return self.embed_texts([text], model)[0]

    # ---------------- 图片 OCR / 多模态解析 ----------------
    @staticmethod
    def _image_to_base64(image_bytes: bytes, mime: str = "image/jpeg") -> str:
        return base64.b64encode(image_bytes).decode("utf-8")

    def ocr_image(self, image_bytes: bytes, mime: str = "image/jpeg") -> str:
        """对单张图片执行 OCR 全解析，返回提取的文字。

        优先使用 DeepSeek-OCR 模型；调用失败时回退 Qwen3-VL 视觉模型。
        """
        b64 = self._image_to_base64(image_bytes, mime)
        data_url = f"data:{mime};base64,{b64}"

        def _call(model: str, prompt: str) -> str:
            try:
                resp = self.client.chat.completions.create(
                    model=model,
                    messages=[{
                        "role": "user",
                        "content": [
                            {"type": "image_url",
                             "image_url": {"url": data_url}},
                            {"type": "text", "text": prompt},
                        ],
                    }],
                    max_tokens=2048,
                )
                return resp.choices[0].message.content or ""
            except Exception as e:  # noqa: BLE001
                logger.warning("OCR 模型 %s 调用失败: %s", model, e)
                return ""

        # 1) 专用 OCR 模型
        text = _call(settings.OCR_MODEL,
                     "请完整识别并输出这张图片中的所有文字内容，保持原始排版顺序，不要添加任何解释。")
        if text.strip():
            return text.strip()

        # 2) 回退到视觉模型
        text = _call(
            settings.VISION_MODEL,
            "这张图可能包含文字或健康信息。请：1)完整提取图中所有文字；"
            "2)如果图片是食物/营养相关，简要描述内容。用中文回答。",
        )
        return text.strip()

    def vision(self, image_bytes: bytes, mime: str = "image/jpeg", prompt: str = "") -> str:
        """单次视觉问答，供餐食识别使用。"""
        b64 = self._image_to_base64(image_bytes, mime)
        resp = self.client.chat.completions.create(
            model=settings.VISION_MODEL,
            messages=[{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{b64}"}},
                {"type": "text", "text": prompt},
            ]}],
            temperature=0.2,
            max_tokens=1500,
        )
        return resp.choices[0].message.content or ""

    def transcribe_audio(self, audio_bytes: bytes, filename: str, mime: str) -> str:
        """使用 SiliconFlow 兼容接口进行语音转写。"""
        import httpx
        endpoint = settings.SILICONFLOW_ASR_URL or f"{self.base_url}/audio/transcriptions"
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {self.api_key}"},
            files={"file": (filename, audio_bytes, mime)},
            data={"model": settings.ASR_MODEL},
            timeout=120,
        )
        response.raise_for_status()
        return response.json().get("text", "")

    def synthesize_speech(self, text: str) -> bytes:
        """使用 SiliconFlow 兼容接口合成语音。

        注意 voice 必须是「模型ID:音色名」形式（如 FunAudioLLM/CosyVoice2-0.5B:alex），
        传 "default" 会返回 400 Invalid voice。
        """
        import httpx
        endpoint = settings.SILICONFLOW_TTS_URL or f"{self.base_url}/audio/speech"
        voice = getattr(settings, "TTS_VOICE", "") or f"{settings.TTS_MODEL}:alex"
        if ":" not in voice:  # 容错：只写了音色名时补上模型前缀
            voice = f"{settings.TTS_MODEL}:{voice}"
        response = httpx.post(
            endpoint,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
            json={"model": settings.TTS_MODEL, "input": text, "voice": voice, "response_format": "mp3"},
            timeout=120,
        )
        response.raise_for_status()
        return response.content


# 模块级单例
_llm: Optional[SiliconFlowClient] = None


def get_llm() -> SiliconFlowClient:
    global _llm
    if _llm is None:
        _llm = SiliconFlowClient()
    return _llm
