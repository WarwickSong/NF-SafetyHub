import os


os.environ["ENVIRONMENT"] = "testing"
os.environ["DB_URL"] = "sqlite+aiosqlite:///./data/test_safetyhub.db"
os.environ["ADMIN_PASSWORD"] = "strong-local-password"
os.environ["SAFETYHUB_DATA_KEY"] = "test-safetyhub-data-key"
os.environ["ALLOW_EMPTY_API_KEYS_PASSTHROUGH"] = "false"
