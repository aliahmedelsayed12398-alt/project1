class Retriever:
    def __init__(self, vector_db):
        self.vector_db = vector_db

    def retrieve(self, query: str) -> list[str]:
        return [doc for doc in self.vector_db.documents if query.lower() in doc.lower()]
