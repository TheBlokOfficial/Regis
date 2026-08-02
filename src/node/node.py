import io
import json
import logging
import datetime
import asyncio
from typing import Any
from fastapi import WebSocket, WebSocketDisconnect

from node.engines.llm_engine import LLMEngine
from node.engines.stt_engine import STTEngine
from node.engines.tts_engine import TTSEngine


class WorkerNode:
    """Węzeł Roboczy — hostuje model LLM i silnik STT.

    Odpowiada wyłącznie za inferencję: pętlę ReAct/NLU oraz transkrypcję audio.
    Nie zawiera żadnej logiki HTTP, routingu ani integracji z Home Assistant.
    Te odpowiedzialności należą do Kontrolera (apps/controller/).

    W przyszłości (po wdrożeniu Rejestru Encji) WorkerNode będzie działać
    jako osobny proces i komunikować się z Kontrolerem przez własne API HTTP.
    Na tym etapie Kontroler importuje go bezpośrednio.
    """

    def __init__(self, model_name: str, temperature: float, history_limit: int = 10):
        """Inicjalizuje silniki LLM i STT.

        Args:
            model_name: Nazwa modelu w Ollamie (np. 'qwen3.5:9b').
            temperature: Temperatura modelu (0.1 dla tool callingu).
            history_limit: (Oczekuje na usunięcie)
        """
        self.llm_engine = LLMEngine(
            model_name=model_name,
            temperature=temperature
        )
        self._stt_engine = None
        self._tts_engine = None
        logging.info(f"WorkerNode uruchomiony. Model={model_name}")

    @property
    def stt_engine(self):
        if self._stt_engine is None:
            logging.info("Leniwe ładowanie silnika STT (Whisper)...")
            self._stt_engine = STTEngine(model_size="small", language="pl")
        return self._stt_engine

    @property
    def tts_engine(self):
        if self._tts_engine is None:
            logging.info("Leniwe ładowanie silnika TTS (Piper)...")
            self._tts_engine = TTSEngine(model_name="pl_PL-darkman-medium")
        return self._tts_engine

    def handle_chat(
        self,
        messages: list[dict],
        tools_registry,
        on_tool_call: Any = None,
        on_thought_token: Any = None,
        on_content_token: Any = None,
        on_raw_tool_call: Any = None,
        on_profiler: Any = None
    ) -> str:
        """Obsługuje zapytanie tekstowe — deleguje do pętli ReAct/NLU silnika LLM."""
        return self.llm_engine.generate_response(
            messages,
            tools_registry,
            on_tool_call=on_tool_call,
            on_thought_token=on_thought_token,
            on_content_token=on_content_token,
            on_raw_tool_call=on_raw_tool_call,
            on_profiler=on_profiler
        )

    def handle_audio(
        self,
        audio_data: bytes,
        tools_registry,
        system_prompt: str,
        history: list[dict],
        on_stt_result: Any = None,
        on_tool_call: Any = None,
        on_thought_token: Any = None,
        on_content_token: Any = None,
        on_raw_tool_call: Any = None,
        on_profiler: Any = None
    ) -> str:
        """Kompletny pipeline: STT -> LLM Engine -> Zwraca tekst odpowiedzi."""
        if not self.stt_engine:
            return "Błąd: Silnik STT nie jest zainicjalizowany."

        audio_io = io.BytesIO(audio_data)
        import time
        stt_start = time.perf_counter()
        text = self.stt_engine.transcribe_audio_file(audio_io)
        stt_elapsed = time.perf_counter() - stt_start
        
        if not text:
            if on_profiler:
                on_profiler({"metric": "stt", "value": int(stt_elapsed * 1000)})
            return "Nie rozpoznano żadnego tekstu ze strumienia audio."

        if on_stt_result:
            on_stt_result(text)

        if on_profiler:
            on_profiler({"metric": "stt", "value": int(stt_elapsed * 1000)})

        from node.history_utils import build_messages_from_history
        
        history = history or []
        messages = build_messages_from_history(
            system_prompt=system_prompt,
            history=history,
            current_message=text
        )

        return self.handle_chat(
            messages,
            tools_registry,
            on_tool_call=on_tool_call,
            on_thought_token=on_thought_token,
            on_content_token=on_content_token,
            on_raw_tool_call=on_raw_tool_call,
            on_profiler=on_profiler
        )



    def clear_history(self) -> None:
        """Czyści historię konwersacji silnika LLM."""
        self.llm_engine.clear_history()

    def preload_model(self) -> None:
        """Wstępnie ładuje model do VRAM (Ollama). Wyrzuca błąd przy braku połączenia."""
        self.llm_engine.preload_model()

    def unload_model(self) -> None:
        """Wymusza wyładowanie modelu z pamięci (VRAM)."""
        self.llm_engine.unload_model()


def start():
    """Entry point dla procesu pracownika w tle."""
    import uvicorn
    from node import config
    from node.worker import app
    settings = config.load_settings()
    port = settings.get("worker_port", 8001)
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    start()
