from __future__ import annotations
import os
from openai import AsyncOpenAI

class STTClient:
    def __init__(self):
        self.client = AsyncOpenAI(api_key=os.getenv("OPENAI_API_KEY"))

    async def transcribe(self, audio_path: str) -> str:
        with open(audio_path, "rb") as f:
            result = await self.client.audio.transcriptions.create(
                model="gpt-4o-mini-transcribe",
                file=f
            )
        return result.text
