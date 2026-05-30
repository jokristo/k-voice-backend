from abc import ABC, abstractmethod
from typing import Any


class PaymentProvider(ABC):
    @abstractmethod
    def get_subscription(self, subscription_id: str) -> dict[str, Any]:
        """Return provider subscription payload."""

    @abstractmethod
    def resolve_plan_key(self, provider_plan_id: str) -> str | None:
        """Map provider plan id to internal billing plan key."""
