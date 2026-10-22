"""Agendamento de verificações ancorado ao tempo desde a inicialização do computador.

Não grava histórico de alertas nem monitora o usuário. A cada novo processo
é feita uma consulta inicial; as demais seguem marcos de uptime do sistema.
"""
from __future__ import annotations

import sys
import time

SIX_HOURS = 6 * 60 * 60
THREE_HOURS = 3 * 60 * 60


def computer_uptime_seconds() -> float:
    """Tempo de inicialização do sistema, não da janela ou processo AURORA."""
    if sys.platform == "win32":
        import ctypes
        # 64 bits para não reiniciar a contagem a cada 49,7 dias.
        tick_count = ctypes.windll.kernel32.GetTickCount64
        tick_count.restype = ctypes.c_ulonglong
        return float(tick_count()) / 1000.0
    if hasattr(time, "CLOCK_BOOTTIME"):
        return float(time.clock_gettime(time.CLOCK_BOOTTIME))
    return float(time.monotonic())


class UpdateCadence:
    """Um check por marco de 6h de uptime e novo alerta 3h após recusa."""

    def __init__(self, uptime: float):
        self.next_regular = (int(uptime // SIX_HOURS) + 1) * SIX_HOURS
        self.snoozed_version: str | None = None
        self.snoozed_until: float | None = None

    def should_check(self, uptime: float) -> bool:
        regular = uptime >= self.next_regular
        retry = self.snoozed_until is not None and uptime >= self.snoozed_until
        if regular:
            # Um computador pode dormir por várias horas: não faça uma
            # requisição para cada janela perdida.
            self.next_regular = (int(uptime // SIX_HOURS) + 1) * SIX_HOURS
        if retry:
            self.snoozed_until = None
            self.snoozed_version = None
        return bool(regular or retry)

    def should_notify(self, version: str, uptime: float) -> bool:
        return not (self.snoozed_version == version
                    and self.snoozed_until is not None
                    and uptime < self.snoozed_until)

    def decline(self, version: str, uptime: float) -> None:
        self.snoozed_version = version
        self.snoozed_until = uptime + THREE_HOURS

    def accept(self) -> None:
        self.snoozed_version = None
        self.snoozed_until = None
