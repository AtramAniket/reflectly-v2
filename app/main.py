from fastapi import FastAPI
from app.core.config import settings
from app.routes import auth

app = FastAPI(title=settings.app_name)

app.include_router(auth.router, prefix=settings.api_prefix)

@app.get("/")
async def root():
	return {
		"message": f"{settings.app_name} is running"
	}
