conversation_history = []

def add_to_history(role, content):
    conversation_history.append({"role": role, "content": content})

def get_history():
    return conversation_history

def reset_history():
    global conversation_history
    conversation_history = []

def clear_history():
    global conversation
    conversation = []