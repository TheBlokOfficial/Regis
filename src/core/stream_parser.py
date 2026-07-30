import logging

class StreamingTokenParser:
    """
    Zaawansowany parser tokenów strumieniowych (Event-Driven).
    Izoluje UI od detali łapania tagów XML/HTML i połykania ładunków JSON.
    Wspiera stanowy bufor (Stateful Buffer) oraz Lookahead zabezpieczający
    przed cięciami chunków przez serwer wnioskowania bez zacinania UI.
    """
    
    def __init__(self, on_thought_callback, on_content_callback):
        self.on_thought_callback = on_thought_callback
        self.on_content_callback = on_content_callback
        
        self.is_inside_thought = False
        self.is_inside_tool_call = False
        self.buffer = ""
        
        self.OPEN_THOUGHT = "<thought>"
        self.CLOSE_THOUGHT = "</thought>"
        self.OPEN_TOOL = "<action>"
        self.CLOSE_TOOL = "</action>"
        
    def reset_state(self):
        """
        Twardy reset parsera. Musi być wywoływany przez silnik
        na początku każdej iteracji ReAct. W ten sposób parser
        gubi wszelkie porzucone tagi czy ucięte z powodu limitu tokenów buforowania.
        """
        self.buffer = ""
        self.is_inside_thought = False
        self.is_inside_tool_call = False

    def _flush_buffer(self, content: str, target: str):
        if not content:
            return
            
        if target == "thought":
            self.on_thought_callback(content)
        elif target == "content":
            self.on_content_callback(content)

    def feed_token(self, token: str):
        """Wstrzykiwanie nowego wygenerowanego chunka (tokenu) do bufora maszyny stanów."""
        if not token:
            return
            
        self.buffer += token
        
        while self.buffer:
            if self.is_inside_tool_call:
                # Faza narzędzia - połykamy wszystko, unikając wycieku na UI
                if self.CLOSE_TOOL in self.buffer:
                    idx = self.buffer.index(self.CLOSE_TOOL)
                    self.buffer = self.buffer[idx + len(self.CLOSE_TOOL):]
                    self.is_inside_tool_call = False
                else:
                    # Połykamy cały niekompletny JSON, zachowując znikomą część bufora
                    # aby ewentualnie złapać przecięty domykający tag w następnym chunku.
                    safe_len = max(0, len(self.buffer) - len(self.CLOSE_TOOL) + 1)
                    self.buffer = self.buffer[safe_len:]
                    break
                    
            elif self.is_inside_thought:
                if self.CLOSE_THOUGHT in self.buffer:
                    idx = self.buffer.index(self.CLOSE_THOUGHT)
                    content = self.buffer[:idx]
                    self._flush_buffer(content, "thought")
                    self.buffer = self.buffer[idx + len(self.CLOSE_THOUGHT):]
                    self.is_inside_thought = False
                else:
                    safe_len = max(0, len(self.buffer) - len(self.CLOSE_THOUGHT) + 1)
                    content = self.buffer[:safe_len]
                    self._flush_buffer(content, "thought")
                    self.buffer = self.buffer[safe_len:]
                    break
                    
            else:
                # Faza contentu (czystego tekstu)
                thought_idx = self.buffer.find(self.OPEN_THOUGHT)
                tool_idx = self.buffer.find(self.OPEN_TOOL)
                
                first_tag_idx = -1
                next_state = None
                
                if thought_idx != -1 and tool_idx != -1:
                    if thought_idx < tool_idx:
                        first_tag_idx = thought_idx
                        next_state = "thought"
                    else:
                        first_tag_idx = tool_idx
                        next_state = "tool"
                elif thought_idx != -1:
                    first_tag_idx = thought_idx
                    next_state = "thought"
                elif tool_idx != -1:
                    first_tag_idx = tool_idx
                    next_state = "tool"
                    
                if first_tag_idx != -1:
                    # Znalazł tag otwierający
                    content = self.buffer[:first_tag_idx]
                    self._flush_buffer(content, "content")
                        
                    if next_state == "thought":
                        self.buffer = self.buffer[first_tag_idx + len(self.OPEN_THOUGHT):]
                        self.is_inside_thought = True
                    else:
                        self.buffer = self.buffer[first_tag_idx + len(self.OPEN_TOOL):]
                        self.is_inside_tool_call = True
                else:
                    # Lookahead: Sprawdzamy czy na końcu bufora zaczyna się jakiś nowy tag (po znaku <)
                    last_bracket_idx = self.buffer.rfind('<')
                    
                    if last_bracket_idx != -1:
                        potential_tag = self.buffer[last_bracket_idx:]
                        is_potential_thought = self.OPEN_THOUGHT.startswith(potential_tag)
                        is_potential_tool = self.OPEN_TOOL.startswith(potential_tag)
                        
                        if is_potential_thought or is_potential_tool:
                            # Podejrzenie cięcia chunku, wstrzymujemy ten fragment do następnego wstrzyknięcia
                            content = self.buffer[:last_bracket_idx]
                            self._flush_buffer(content, "content")
                            self.buffer = potential_tag
                            break
                        else:
                            # Fałszywy alarm, czysty tekst posiadający luźny znak mniejszości (np. < 5)
                            self._flush_buffer(self.buffer, "content")
                            self.buffer = ""
                            break
                    else:
                        # Brak mniejszości, spokojnie emitujemy 100% zawartości
                        self._flush_buffer(self.buffer, "content")
                        self.buffer = ""
                        break
