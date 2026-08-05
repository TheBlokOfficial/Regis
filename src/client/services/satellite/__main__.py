import os
import asyncio
import logging

from protocol.schemas import SatelliteConfig, SatelliteAction
from client.config import DATA_DIR
from client.services.base import BaseService

from .states import SatelliteState
from .event_bus import EventBus
from .network import SatelliteAPIClient
from .readiness import ReadinessChecker
from .audio.recorder import AudioStreamManager
from .audio.wakeword import WakeWordEngine
from .audio.vad import EnergyVAD
from .audio.player import AudioPlayer

SILENCE_THRESHOLD = 150

class SatelliteService(BaseService):
    """Główny orkiestrator Satelity zarządzający maszyną stanów (INITIALIZING, WAITING, WAKEWORD, LISTENING, STREAMING, PROCESSING, SPEAKING)."""

    def __init__(self, config: SatelliteConfig = None):
        super().__init__(service_name="satellite", config_class=SatelliteConfig, config_obj=config)
        self.event_bus = EventBus(satellite_id="satellite_proxy")
        self.network = SatelliteAPIClient(self.internal_proxy_url, self.event_bus)
        
        self.audio_manager = AudioStreamManager()
        self.wakeword = WakeWordEngine(str(DATA_DIR))
        self.vad = self._init_vad(self.config)
        self.readiness = ReadinessChecker(self.wakeword, self.audio_manager, self.event_bus)
        
        self.state = SatelliteState.INITIALIZING
        self._paused: bool = True
        self._listening_task: asyncio.Task | None = None



    @staticmethod
    def _init_vad(config: SatelliteConfig) -> EnergyVAD:
        threshold = (
            config.wakeword_threshold * 230
            if config.wakeword_threshold < 1.0
            else SILENCE_THRESHOLD
        )
        return EnergyVAD(threshold=threshold)

    async def start(self):
        loop = asyncio.get_running_loop()
        self.audio_manager.set_loop(loop)
        logging.info("Regis Satellite Service (Self-Healing Audio & Streaming VAD)")

        # 1. Sprawdzenie sprzętu
        await self.readiness.ensure_ready()
        self._set_state(SatelliteState.WAITING)

        try:
            # 2. Główny pasywny punkt oczekiwania na komendy SSE
            await super().start()
        except asyncio.CancelledError:
            pass
        finally:
            # 3. Sprzątanie przy wyłączaniu
            if self._listening_task and not self._listening_task.done():
                self._listening_task.cancel()
            self.audio_manager.stop_stream()

    async def handle_command(self, command_type: str, payload: dict, task_id: str | None):
        from protocol.schemas import ServiceCommand
        
        try:
            cmd_type = ServiceCommand(command_type)
        except ValueError:
            return

        if cmd_type == ServiceCommand.SATELLITE_CONTROL:
            self._handle_satellite_control(payload)
        elif cmd_type == ServiceCommand.PLAY_AUDIO:
            await self._handle_play_audio(payload)

    def _handle_satellite_control(self, cmd_data: dict):
        """Handler do sterowania stanem wybudzania Satelity (RESUME / PAUSE)."""
        match cmd_data.get("action"):
            case SatelliteAction.RESUME:
                self._paused = False
                self.event_bus.log("Otrzymano polecenie RESUME: Wznowienie komunikacji.")
                if self.state == SatelliteState.WAITING:
                    self._start_wakeword_listening()
            case SatelliteAction.PAUSE:
                self._paused = True
                self.event_bus.log("Otrzymano polecenie PAUSE: Wstrzymanie komunikacji.")

    def _start_wakeword_listening(self):
        if self._listening_task and not self._listening_task.done():
            self._listening_task.cancel()
            
        self.audio_manager.empty_queue()
        self.wakeword.reset()
        self._set_state(SatelliteState.WAKEWORD)
        self.event_bus.emit({"type": "state", "state": SatelliteState.WAKEWORD})
        self.event_bus.log("Uruchomiono nasłuch Wake Word.")
        
        self._listening_task = asyncio.create_task(self._listening_loop())

    async def _listening_loop(self):
        """Pętla asynchroniczna nasłuchu mowy (WAKEWORD -> LISTENING/STREAMING)."""
        try:
            while self.state == SatelliteState.WAKEWORD:
                await self._handle_wakeword()
                if self._paused:
                    break
                
            if self.state == SatelliteState.STREAMING and not self._paused:
                await self._handle_streaming()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            self.event_bus.log(f"Błąd w pętli nasłuchu: {e}")
        finally:
            if self.state != SatelliteState.WAITING:
                self._set_state(SatelliteState.WAITING)
                self.event_bus.emit({"type": "state", "state": SatelliteState.WAITING})
                self.event_bus.log("Nasłuch zakończony. Powrót do uśpienia (WAITING).")

    def _process_vad_for_wakeword(self, chunk) -> bool:
        is_speech = self.vad.is_speech(chunk)
        current_speech_state = "vad_speech" if is_speech else "vad_silence"
        
        if getattr(self, "_last_wakeword_speech_state", None) != current_speech_state:
            self.event_bus.emit({"type": current_speech_state})
            if current_speech_state == "vad_speech":
                for pre_chunk in list(self.audio_manager.ring_buffer):
                    self.wakeword.predict(pre_chunk[:, 0])
            self._last_wakeword_speech_state = current_speech_state
            
        return is_speech

    async def _handle_wakeword(self):
        try:
            chunk = await self.audio_manager.get_chunk()
        except Exception:
            await asyncio.sleep(0.1)
            return

        self.audio_manager.ring_buffer.append(chunk)

        is_speech = self._process_vad_for_wakeword(chunk)
        if not is_speech:
            return

        pcm16_1d = chunk[:, 0]
        prediction = self.wakeword.predict(pcm16_1d)

        for mdl, score in prediction.items():
            if score > 0.65:
                await self._on_wakeword_detected(mdl, score)
                break

    async def _on_wakeword_detected(self, mdl, score):
        self.event_bus.emit({"type": "wakeword", "score": score})
        self.event_bus.log(f"Wykryto Wake Word '{mdl}' z wynikiem: {score:.2f}! Sprawdzam dostępność Kontrolera...")

        permitted = await self.network.check_wake_permission()
        if permitted and not self._paused:
            AudioPlayer.play_system_sound("Speech On")
            self.event_bus.emit({"type": "state", "state": SatelliteState.LISTENING})
            self.event_bus.log("Start nagrywania...")
            self.audio_manager.empty_queue()
            self._set_state(SatelliteState.STREAMING)
        else:
            AudioPlayer.play_system_sound("Speech Off")
            self.event_bus.log("Odmowa nagrywania (Wstrzymana komunikacja lub brak workerów).")

    async def _handle_streaming(self):
        self.event_bus.log("Słucham... (VAD śledzi dynamikę zdania)")

        try:
            collected_chunks = await self.audio_manager.record_until_silence(
                self.vad, self.event_bus, lambda: self.state
            )
        except Exception as e:
            self.event_bus.log(f"Błąd nagrywania audio: {e}")
            return

        self._set_state(SatelliteState.PROCESSING)
        self.event_bus.emit({"type": "state", "state": SatelliteState.PROCESSING})
        AudioPlayer.play_system_sound("Speech Sleep")

        wav_bytes = self.audio_manager.create_wav_payload(collected_chunks)
        self.event_bus.log(f"Przygotowano paczkę audio ({len(wav_bytes)} bajtów). Wysyłam do Kontrolera (PROCESSING)...")

        try:
            await self.network.send_audio_payload(wav_bytes)
        finally:
            self._set_state(SatelliteState.WAITING)
            self.event_bus.emit({"type": "state", "state": SatelliteState.WAITING})

    async def _handle_play_audio(self, cmd_data: dict):
        """Odtwarzanie odpowiedzi głosowej lektora."""
        audio_b64 = cmd_data.get("audio_b64", "")
        self._set_state(SatelliteState.SPEAKING)
        self.event_bus.emit({"type": "state", "state": SatelliteState.SPEAKING})
        self.event_bus.log("Odtwarzam odpowiedź lektora (SPEAKING)...")
        try:
            await asyncio.to_thread(AudioPlayer.play_tts_audio, audio_b64)
        except Exception as e:
            self.event_bus.log(f"Błąd odtwarzania TTS: {e}")
        finally:
            await self.network.report_audio_complete()
            self._set_state(SatelliteState.WAITING)
            self.event_bus.emit({"type": "state", "state": SatelliteState.WAITING})

    def _set_state(self, new_state: SatelliteState):
        self.state = new_state


def _setup_logging():
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)

async def main():
    _setup_logging()
    service = SatelliteService()
    await service.start()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Satelita zamykana.")
