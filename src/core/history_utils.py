import json

def build_messages_from_history(system_prompt: str, history: list[dict], current_message: str = None) -> list[dict]:
    """
    Odbudowuje listę wiadomości na podstawie historii w taki sposób,
    aby była w 100% zgodna ze strukturą, na której operuje pętla ReActAgent.
    (Rozdziela wywołania narzędzi na osobne wiadomości ról 'assistant' z tagiem <action>
    oraz odpowiedzi systemu z rola 'tool').
    """
    messages = [{"role": "system", "content": system_prompt}]
    
    for turn in history:
        messages.append({"role": "user", "content": turn["user"]})
        
        if turn.get("tools"):
            for t in turn["tools"]:
                if isinstance(t, dict):
                    # Wypisanie przemyśleń (Chain of Thought), jeśli istnieją
                    thought_text = t.get("thought", "").strip()
                    
                    call_str = json.dumps({"name": t["name"], "arguments": t["arguments"]}, ensure_ascii=False)
                    call_content = f"<action>{call_str}</action>"
                    
                    # Łączymy myśl z wywołaniem narzędzia w jednej wiadomości 
                    if thought_text:
                        full_assistant_content = f"<thought>\n{thought_text}\n</thought>\n{call_content}"
                    else:
                        full_assistant_content = call_content
                        
                    messages.append({"role": "assistant", "content": full_assistant_content})
                    messages.append({"role": "user", "content": f"<tool_response>\n{t.get('result', '')}\n</tool_response>"})
                else:
                    # Fallback dla starej historii tekstowej
                    messages.append({"role": "assistant", "content": str(t)})
        
        if turn.get("assistant"):
            messages.append({"role": "assistant", "content": turn["assistant"]})
            
    if current_message:
        messages.append({"role": "user", "content": current_message})
        
    return messages
