from dataclasses import dataclass


@dataclass(frozen=True)
class ExchangeAdapter:
    name: str
    enabled: bool = False

    def status(self) -> dict[str, object]:
        return {
            "exchange": self.name,
            "enabled": self.enabled,
            "last_success_ts": None,
            "last_error": "live public API integration is not implemented",
            "latency_ms": None,
        }
