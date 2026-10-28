"""AI Case Intake Agent: operational email -> structured, auditable case state."""
from .config import Settings
from .decision_engine import Context, process_event
from .models import Decision, Email

__all__ = ["Settings", "Context", "process_event", "Decision", "Email"]
__version__ = "0.1.0"
