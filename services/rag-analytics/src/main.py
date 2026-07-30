from fastapi import FastAPI

app = FastAPI(title="RAG Analytics Service")


@app.get("/health")
def health_check():
    return {"status": "ok"}
