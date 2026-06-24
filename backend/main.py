from fastapi import FastAPI

app = FastAPI(
    title="AegisAI",
    version="0.1.0"
)

@app.get("/")
def root():
    return {"message": "AegisAI Running"}