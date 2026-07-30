class DialogueState:
    def __init__(self):
        self.context = {}

    def update(self, key: str, value: str):
        self.context[key] = value
