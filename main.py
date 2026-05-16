from fastapi import FastAPI
from routes.signal import router as signal_router
from routes.backtest import router as backtest_router

app = FastAPI()

app.include_router(signal_router)
app.include_router(backtest_router)


@app.get("/health")
def health():
    return {"status": "ok"}