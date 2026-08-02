import sys
from datetime import datetime
from client.ux import console


def _timestamp() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _format_elapsed(elapsed_ms):
    if elapsed_ms is None:
        return ""
    if elapsed_ms < 1000:
        return f"{elapsed_ms}ms"
    return f"{elapsed_ms / 1000:.1f}s"


def render_user_turn(text: str) -> None:
    ts = _timestamp()
    console.print(f"[success][{ts}][/success] [header]Ty:[/header] {text}")


class TurnRenderer:
    def __init__(self, verbose: bool = False) -> None:
        self._verbose = verbose
        self._tool_calls = []
        self._response_started = False
        self._thought_open = False
        self._routing_info = {}
        self._elapsed_ms = None
        self._profiler = {}

    def on_thought_token(self, token: str) -> None:
        if self._verbose:
            if not self._thought_open:
                ts = _timestamp()
                console.print(f"\n[success][{ts}][/success] [info]Regis myśli:[/info] [info]", end="")
                self._thought_open = True
            clean_token = token.replace("\n", " ")
            console.print(clean_token, end="", style="info", markup=False)
            sys.stdout.flush()

    def on_content_token(self, token: str) -> None:
        if self._thought_open:
            console.print()
            self._thought_open = False
        if not self._response_started:
            stripped = token.lstrip()
            if not stripped:
                return
            ts = _timestamp()
            console.print(f"\n[success][{ts}][/success] [header]Regis:[/header] ", end="")
            self._response_started = True
            token = stripped
        if token:
            console.print(token, end="", style="header", markup=False)
            sys.stdout.flush()

    def on_tool_call(self, token: str) -> None:
        if self._thought_open:
            console.print()
            self._thought_open = False
        self._tool_calls.append(token)
        if self._verbose:
            console.print(f"  {token}", style="info", markup=False)

    def on_routing_info(self, event: dict) -> None:
        self._routing_info.update(event)

    def on_profiler(self, metric: dict) -> None:
        name = metric.get("metric")
        val = metric.get("value", 0)
        if name:
            self._profiler[name] = self._profiler.get(name, 0) + val

    def on_done(self, event: dict) -> None:
        self._elapsed_ms = event.get("elapsed_ms")

    def close_thought(self) -> None:
        if self._thought_open:
            console.print()
            self._thought_open = False

    def finalize_response(self, final_text=None) -> None:
        self.close_thought()
        if final_text and final_text.startswith("Błąd serwera:"):
            console.print(f"\n[error]{final_text}[/error]")
        elif final_text and not self._response_started:
            ts = _timestamp()
            console.print(f"\n[success][{ts}][/success] [header]Regis:[/header] {final_text}")

    def render_status_line(self) -> None:
        self.close_thought()
        status_parts = []
        if self._routing_info:
            worker_id = self._routing_info.get("worker_id", "Nieznany")
            model = self._routing_info.get("model", "Nieznany")
            status_parts.append(f"{worker_id}  ·  {model}")
        if self._tool_calls:
            n = len(self._tool_calls)
            label = "narzędzie" if n == 1 else "narzędzia" if n < 5 else "narzędzi"
            status_parts.append(f"{n} {label}")
        if self._elapsed_ms:
            status_parts.append(_format_elapsed(self._elapsed_ms))
            
        if status_parts:
            line = f"\n  [info]{' · '.join(status_parts)}[/info]"
            if self._profiler:
                prof_str = []
                if "stt" in self._profiler:
                    prof_str.append(f"STT: {_format_elapsed(self._profiler['stt'])}")
                if "llm_ttft" in self._profiler:
                    prof_str.append(f"TTFT: {_format_elapsed(self._profiler['llm_ttft'])}")
                if "llm_gen" in self._profiler:
                    prof_str.append(f"Gen: {_format_elapsed(self._profiler['llm_gen'])}")
                if "tools" in self._profiler:
                    prof_str.append(f"Narzędzia: {_format_elapsed(self._profiler['tools'])}")
                    
                if "llm_ttft" in self._profiler or "llm_gen" in self._profiler:
                    sum_components = sum(self._profiler.values())
                    if self._elapsed_ms and self._elapsed_ms > sum_components:
                        network_ms = self._elapsed_ms - sum_components
                        prof_str.append(f"Narzut: {_format_elapsed(network_ms)}")
                
                if prof_str:
                    line += f"  [dim][{' | '.join(prof_str)}][/dim]"
            
            console.print(line)
        else:
            console.print()
