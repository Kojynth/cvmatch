from typing import Dict


class ParserMetricsMixin:
    """Mixin providing standard get/reset metrics behavior.

    Classes using this mixin must expose `self.metrics` as a Dict[str, int].
    Control copy semantics via class attribute `METRICS_COPY`.
    """

    METRICS_COPY: bool = False

    def get_metrics(self) -> Dict[str, int]:
        m = getattr(self, 'metrics', {})
        return m.copy() if getattr(self, 'METRICS_COPY', False) else m

    def reset_metrics(self) -> None:
        m = getattr(self, 'metrics', None)
        if isinstance(m, dict):
            for k in list(m.keys()):
                try:
                    m[k] = 0
                except Exception:
                    pass

