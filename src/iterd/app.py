"""iterd Web 应用（FastAPI）."""

from __future__ import annotations

from fastapi import FastAPI

app = FastAPI(title="iterd", description="产品迭代式开发系统.")


@app.get("/")
def read_root() -> dict[str, str]:
    """根路径健康检查."""
    return {"status": "ok", "project": "iterd"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("iterd.app:app", host="0.0.0.0", port=8000, reload=True)
