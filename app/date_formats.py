"""Formatação de datas do AURORA em português, independente do locale do SO.

Aceita apenas diretivas conhecidas (sem executar código) e mantém a sintaxe
{{data_formato:...}}. Códigos menos portáveis são implementados aqui para que
Windows e Linux produzam o mesmo texto.
"""
from __future__ import annotations

from datetime import datetime

WEEKDAYS_PTBR = (
    "segunda-feira", "terça-feira", "quarta-feira", "quinta-feira",
    "sexta-feira", "sábado", "domingo",
)
WEEKDAYS_SHORT_PTBR = ("seg", "ter", "qua", "qui", "sex", "sáb", "dom")
MONTHS_PTBR = (
    "janeiro", "fevereiro", "março", "abril", "maio", "junho",
    "julho", "agosto", "setembro", "outubro", "novembro", "dezembro",
)
MONTHS_SHORT_PTBR = (
    "jan", "fev", "mar", "abr", "mai", "jun",
    "jul", "ago", "set", "out", "nov", "dez",
)

# Fonte única dos códigos explicados no guia. A implementação suporta todos.
# Os códigos %z/%Z só exibem dados quando o objeto tiver fuso explícito.
FORMAT_CODE_GROUPS = (
    ("Dias da semana", (
        ("%a", "Nome abreviado do dia da semana"),
        ("%A", "Nome completo do dia da semana"),
        ("%w", "Dia da semana, de domingo (0) a sábado (6)"),
        ("%u", "Dia da semana, de segunda (1) a domingo (7)"),
    )),
    ("Dias e meses", (
        ("%d", "Dia do mês com dois dígitos"),
        ("%e", "Dia do mês com espaço à esquerda"),
        ("%j", "Número do dia no ano, de 001 a 366"),
        ("%b", "Nome abreviado do mês em português"),
        ("%B", "Nome completo do mês em português"),
        ("%h", "Abreviação do mês (equivale a %b)"),
        ("%m", "Número do mês, de 01 a 12"),
    )),
    ("Ano e data", (
        ("%y", "Ano com dois dígitos"),
        ("%Y", "Ano com quatro dígitos"),
        ("%C", "Século (primeiros dois dígitos do ano)"),
        ("%F", "Data no formato AAAA-MM-DD"),
        ("%D", "Data no formato MM/DD/AA (padrão americano)"),
    )),
    ("Horário", (
        ("%H", "Hora no formato de 24 horas (00 a 23)"),
        ("%I", "Hora no formato de 12 horas (01 a 12)"),
        ("%M", "Minutos, de 00 a 59"),
        ("%S", "Segundos, de 00 a 59"),
        ("%p", "Período AM ou PM"),
        ("%R", "Hora e minuto: HH:MM"),
        ("%T", "Hora, minuto e segundo: HH:MM:SS"),
        ("%r", "Hora em 12 horas, com segundos e AM/PM"),
        ("%f", "Microssegundos, com seis dígitos"),
    )),
    ("Semanas do ano", (
        ("%U", "Semana do ano iniciada no domingo (00 a 53)"),
        ("%W", "Semana do ano iniciada na segunda (00 a 53)"),
        ("%V", "Número da semana ISO (01 a 53)"),
        ("%G", "Ano ISO da semana, com quatro dígitos"),
        ("%g", "Ano ISO da semana, com dois dígitos"),
    )),
    ("Formatos regionais e especiais", (
        ("%c", "Data e hora no padrão brasileiro"),
        ("%x", "Data local no formato DD/MM/AAAA"),
        ("%X", "Hora local no formato HH:MM:SS"),
        ("%%", "Caractere % literal"),
        ("%z", "Diferença para UTC (vazio sem fuso explícito)"),
        ("%Z", "Nome do fuso horário (vazio sem fuso explícito)"),
    )),
)

_ALLOWED_CODES = frozenset(
    code[1:] for _group, rows in FORMAT_CODE_GROUPS
    for code, _description in rows
)


def format_date_ptbr(now: datetime, fmt: str) -> str:
    """Formata datetime com códigos strftime selecionados, sempre em pt-BR.

    Não altera locale global (evita interferências em outras threads), não
    interpreta entrada com strptime e não executa instruções arbitrárias.
    """
    if (not isinstance(fmt, str) or not 1 <= len(fmt) <= 48
            or any(ch in "{}\r\n" for ch in fmt)):
        raise ValueError("Formato de data não permitido.")
    iso = now.isocalendar()
    h12 = now.hour % 12 or 12
    suffix = "AM" if now.hour < 12 else "PM"
    date_pt = f"{now.day:02d}/{now.month:02d}/{now.year:04d}"
    time_pt = f"{now.hour:02d}:{now.minute:02d}:{now.second:02d}"
    codes = {
        "a": WEEKDAYS_SHORT_PTBR[now.weekday()],
        "A": WEEKDAYS_PTBR[now.weekday()],
        "w": str((now.weekday() + 1) % 7),
        "u": str(now.isoweekday()),
        "d": f"{now.day:02d}",
        "e": f"{now.day:2d}",
        "j": f"{now.timetuple().tm_yday:03d}",
        "b": MONTHS_SHORT_PTBR[now.month - 1],
        "B": MONTHS_PTBR[now.month - 1],
        "h": MONTHS_SHORT_PTBR[now.month - 1],
        "m": f"{now.month:02d}",
        "y": f"{now.year % 100:02d}",
        "Y": f"{now.year:04d}",
        "C": f"{now.year // 100:02d}",
        "F": f"{now.year:04d}-{now.month:02d}-{now.day:02d}",
        "D": f"{now.month:02d}/{now.day:02d}/{now.year % 100:02d}",
        "H": f"{now.hour:02d}",
        "I": f"{h12:02d}",
        "M": f"{now.minute:02d}",
        "S": f"{now.second:02d}",
        "p": suffix,
        "R": f"{now.hour:02d}:{now.minute:02d}",
        "T": time_pt,
        "r": f"{h12:02d}:{now.minute:02d}:{now.second:02d} {suffix}",
        "f": f"{now.microsecond:06d}",
        "U": now.strftime("%U"),
        "W": now.strftime("%W"),
        "V": f"{iso.week:02d}",
        "G": f"{iso.year:04d}",
        "g": f"{iso.year % 100:02d}",
        "c": date_pt + " " + time_pt,
        "x": date_pt,
        "X": time_pt,
        "%": "%",
        "z": now.strftime("%z"),
        "Z": now.strftime("%Z"),
    }
    output = []
    index = 0
    while index < len(fmt):
        if fmt[index] != "%":
            output.append(fmt[index])
            index += 1
            continue
        if index + 1 >= len(fmt) or fmt[index + 1] not in _ALLOWED_CODES:
            raise ValueError("Formato de data não permitido.")
        output.append(codes[fmt[index + 1]])
        index += 2
    return "".join(output)[:100]
