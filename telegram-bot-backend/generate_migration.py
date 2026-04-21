import asyncio
from sqlalchemy.schema import CreateTable
from sqlalchemy.dialects import postgresql
from app.db.models import Base
for table in Base.metadata.sorted_tables:
    print(CreateTable(table).compile(dialect=postgresql.dialect()))
