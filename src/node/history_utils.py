import json

def build_messages_from_history(system_prompt: str, history: list[dict], current_message: str = None) -> list[dict]:
    """
    Odbudowuje listę wiadomości na podstawie historii do struktury zgodnej z API LLM.
    """
    messages = [{"role": "system", "content": system_prompt}]
    
    for turn in history:
        messages.append({"role": "user", "content": turn["user"]})
        

        if turn.get("assistant"):
            messages.append({"role": "assistant", "content": turn["assistant"]})
            
    if current_message:
        messages.append({"role": "user", "content": current_message})
        
    return messages
