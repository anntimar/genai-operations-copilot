from alembic import context
from app.core import engine
from app.models import Base


def migrate():
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=Base.metadata)
        with context.begin_transaction():
            context.run_migrations()


migrate()
