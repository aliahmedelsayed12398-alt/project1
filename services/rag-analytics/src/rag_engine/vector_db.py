class VectorDB:
    def __init__(self):
        self.documents = []

    def add(self, document: str):
        self.documents.append(document)
