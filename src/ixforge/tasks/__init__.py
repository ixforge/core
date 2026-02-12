"""Background tasks powered by Procrastinate.

Import the shared ``app`` instance and all task modules so that task
functions are registered with the procrastinate application on import.
"""

from ixforge.tasks import config as config
from ixforge.tasks import maintenance as maintenance
from ixforge.tasks.setup import app

__all__ = ["app"]
