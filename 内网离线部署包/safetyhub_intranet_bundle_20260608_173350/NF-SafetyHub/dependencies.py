from config import Settings, get_settings


async def get_app_settings() -> Settings:
    return get_settings()
