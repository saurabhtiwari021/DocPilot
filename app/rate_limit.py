"""
Shared rate limiter.

Lives in its own module (rather than app/main.py) so route modules under
app/api/routes/ can import it without creating a circular import - main.py
imports the routes, and the routes need `limiter` for their
`@limiter.limit(...)` decorators.
"""

from slowapi import Limiter
from slowapi.util import get_remote_address

limiter = Limiter(key_func=get_remote_address)
