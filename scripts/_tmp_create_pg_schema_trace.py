import asyncio
import os
import traceback
from pathlib import Path

TRACE = Path('/tmp/safetyhub_create_schema_trace.txt')


def log(message: str) -> None:
    with TRACE.open('a', encoding='utf-8') as file:
        file.write(message + '\n')


async def main() -> None:
    TRACE.write_text('', encoding='utf-8')
    log('start')
    try:
        from sqlalchemy.ext.asyncio import create_async_engine
        log('import_engine_ok')
        from storage.models import Base
        log('import_models_ok')
        log('tables=' + ','.join(table.name for table in Base.metadata.sorted_tables))
        log('url_present=' + str(bool(os.environ.get('POSTGRES_URL'))))
        engine = create_async_engine(os.environ['POSTGRES_URL'], future=True)
        log('engine_created')
        async with engine.begin() as connection:
            log('begin_ok')
            await connection.run_sync(Base.metadata.create_all)
            log('create_all_ok')
        await engine.dispose()
        log('dispose_ok')
    except Exception:
        log('exception')
        log(traceback.format_exc())
        raise


if __name__ == '__main__':
    asyncio.run(main())
