import io
import json
import logging


from core.llm_engine import LLMEngine
from core.stt_engine import STTEngine


class WorkerNode:
    """Węzeł Roboczy — hostuje model LLM i silnik STT.

    Odpowiada wyłącznie za inferencję: pętlę ReAct/NLU oraz transkrypcję audio.
    Nie zawiera żadnej logiki HTTP, routingu ani integracji z Home Assistant.
    Te odpowiedzialności należą do Kontrolera (apps/controller/).

    W przyszłości (po wdrożeniu Rejestru Encji) WorkerNode będzie działać
    jako osobny proces i komunikować się z Kontrolerem przez własne API HTTP.
    Na tym etapie Kontroler importuje go bezpośrednio.
    """

    def __init__(self, model_name: str, tier: str, temperature: float, history_limit: int):
        """Inicjalizuje silniki LLM i STT.

        Args:
            model_name: Nazwa modelu w Ollamie (np. 'qwen3.5:9b').
            tier: Klasa modelu ('butler', 'regis').
            temperature: Temperatura modelu (0.1 dla tool callingu).
            history_limit: Maksymalna liczba zapamiętanych tur konwersacji.
        """
        self.llm_engine = LLMEngine(
            model_name=model_name,
            tier=tier,
            temperature=temperature,
            history_limit=history_limit
        )
        self.stt_engine = STTEngine(model_size="small", language="pl")
        logging.info(f"WorkerNode uruchomiony. Model={model_name}, Tier={tier}")

    def handle_chat(
        self,
        messages: list[dict],
        tools_registry,
        on_tool_call=None,
        on_thought_token=None,
        on_content_token=None,
        on_raw_tool_call=None
    ) -> str:
        """Obsługuje zapytanie tekstowe — deleguje do pętli ReAct/NLU silnika LLM.

        Args:
            messages: Lista słowników z historią konwersacji.
            tools_registry: Rejestr narzędzi z Kontrolera.
            on_tool_call: Callback logowania użycia narzędzia.
            on_thought_token: Callback tokenu wewnętrznego monologu.
            on_content_token: Callback tokenu odpowiedzi końcowej.
            on_raw_tool_call: Callback dla surowych danych o narzędziu.

        Returns:
            Pełna tekstowa odpowiedź modelu.
        """
        return self.llm_engine.generate_response(
            messages,
            tools_registry,
            on_tool_call=on_tool_call,
            on_thought_token=on_thought_token,
            on_content_token=on_content_token,
            on_raw_tool_call=on_raw_tool_call
        )

    def handle_audio(
        self,
        audio_bytes: bytes,
        tools_registry,
        system_prompt="",
        history=None,
        on_stt_result=None,
        on_tool_call=None,
        on_thought_token=None,
        on_content_token=None,
        on_raw_tool_call=None
    ) -> str:
        """Obsługuje zapytanie audio — STT, a następnie deleguje do handle_chat.

        Args:
            audio_bytes: Surowe bajty pliku WAV.
            tools_registry: Rejestr narzędzi z Kontrolera.
            system_prompt: Prompt systemowy.
            history: Historia konwersacji.
            on_stt_result: Callback z wynikiem transkrypcji.
            on_tool_call: Callback logowania użycia narzędzia.
            on_thought_token: Callback tokenu wewnętrznego monologu.
            on_content_token: Callback tokenu odpowiedzi końcowej.
            on_raw_tool_call: Callback dla surowych danych o narzędziu.

        Returns:
            Pełna tekstowa odpowiedź modelu.
        """
        import json
        audio_io = io.BytesIO(audio_bytes)
        text = self.stt_engine.transcribe_audio_file(audio_io)

        if not text:
            return "Nie rozpoznano żadnego tekstu ze strumienia audio."

        if on_stt_result:
            on_stt_result(text)

        from core.history_utils import build_messages_from_history
        
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
            on_raw_tool_call=on_raw_tool_call
        )



    def clear_history(self) -> None:
        """Czyści historię konwersacji silnika LLM."""
        self.llm_engine.clear_history()

    def unload_model(self) -> None:
        """Wymusza wyładowanie modelu z pamięci (VRAM)."""
        self.llm_engine.unload_model()


def start():
    """Entry point dla CLI (regis-worker). Uruchamia serwer HTTP Węzła Roboczego."""
    import uvicorn
    from core import config
    from controller.worker.server import app
    settings = config.load_settings()
    port = settings.get("worker_port", 8001)
    uvicorn.run(app, host="0.0.0.0", port=port)

if __name__ == "__main__":
    start()
