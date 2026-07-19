"""Importing this package registers every ORM model on ``Base.metadata`` —
required for Alembic autogenerate to see the full schema (see
``adapters/persistence/database.py``'s docstring).
"""

from adapters.persistence import audit_log as audit_log  # noqa: F401
from adapters.persistence import brand_performance as brand_performance  # noqa: F401
from adapters.persistence import doctors as doctors  # noqa: F401
from adapters.persistence import import_runs as import_runs  # noqa: F401
from adapters.persistence import password_reset as password_reset  # noqa: F401
from adapters.persistence import sales_data as sales_data  # noqa: F401
from adapters.persistence import sessions as sessions  # noqa: F401
from adapters.persistence import staging as staging  # noqa: F401
from adapters.persistence import teams as teams  # noqa: F401
from adapters.persistence import users as users  # noqa: F401
