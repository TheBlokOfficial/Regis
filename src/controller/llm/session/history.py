import json

def build_messages_from_history(system_prompt: str, history: list[dict], current_message: str = None) -> list[dict]:
    """
    Odbudowuje listę wiadomości na podstawie historii do struktury zgodnej z API LLM.
    Wspiera zarówno płaską listę wiadomości z rolami (standard LLM), jak i wstecznie format par tur.
    """
    messages = [{"role": "system", "content": system_prompt}]
    
    for item in history:
        if "role" in item:
            messages.append(item)
        else:
            if "user" in item:
                messages.append({"role": "user", "content": item["user"]})
            if item.get("assistant"):
                messages.append({"role": "assistant", "content": item["assistant"]})
            
    if current_message:
        messages.append({"role": "user", "content": current_message})
        
    return messages
