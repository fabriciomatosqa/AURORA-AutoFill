"""Modelos interativos e variáveis avançadas com limites e sem eval.

Sintaxe:
  {{campo:Nome}} ou {{campo:Nome|valor padrão}}
  {{escolha:Situação|Aberto|Concluído}}
  {{data:+7}}, {{data:-2}}, {{data_formato:%Y-%m-%d}}
  {{calculo:12.5*3}}
  {{tab}}, {{enter}}, {{espera:250}}  (etapas confirmadas)
"""
from __future__ import annotations

import ast
from dataclasses import dataclass
from datetime import datetime, timedelta
from html import escape
import operator
import re

_FORM_RE = re.compile(r"\{\{(campo|escolha):([^{}\r\n]{1,180})\}\}", re.I)
_DATE_RE = re.compile(r"\{\{data:([+-]\d{1,4})\}\}", re.I)
_FORMAT_RE = re.compile(r"\{\{data_formato:([^{}\r\n]{1,48})\}\}", re.I)
_CALC_RE = re.compile(r"\{\{calculo:([0-9 .+\-*/()%]{1,75})\}\}", re.I)
_ACTION_RE = re.compile(r"\{\{(tab|enter|espera(?::\d{1,4})?)\}\}", re.I)
_ALLOWED_FORMAT = re.compile(r"^(?:[^%{}]|%(?:[%aAbBcdHIjmMpSUwWyYzZ])){1,48}$")
_ALLOWED_MATH = {
    ast.Add: operator.add, ast.Sub: operator.sub,
    ast.Mult: operator.mul, ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv, ast.Mod: operator.mod,
}


@dataclass(frozen=True)
class Field:
    label: str
    kind: str
    options: tuple[str, ...] = ()
    default: str = ""


@dataclass(frozen=True)
class Step:
    kind: str
    value: str | int = ""


def fields_in(template: str) -> tuple[Field, ...]:
    if not isinstance(template, str) or len(template) > 1_000_000:
        raise ValueError("Modelo inválido ou muito grande.")
    seen: dict[str, Field] = {}
    for match in _FORM_RE.finditer(template):
        kind, detail = match.groups()
        pieces = [part.strip() for part in detail.split("|")]
        title = pieces[0]
        if not 1 <= len(title) <= 48:
            raise ValueError("O nome de um campo deve ter entre 1 e 48 caracteres.")
        if kind.casefold() == "escolha":
            options = tuple(x for x in pieces[1:] if x)
            if not 2 <= len(options) <= 12 or any(len(x) > 80 for x in options):
                raise ValueError(f"A escolha «{title}» precisa de 2 a 12 opções.")
            field = Field(title, "choice", options=options, default=options[0])
        else:
            if len(pieces) > 2 or len(pieces[-1]) > 180:
                raise ValueError(f"O valor inicial de «{title}» é inválido.")
            field = Field(title, "text", default=pieces[1] if len(pieces) == 2 else "")
        prior = seen.get(title.casefold())
        if prior and prior != field:
            raise ValueError(f"O campo «{title}» tem definições diferentes no modelo.")
        seen[title.casefold()] = field
        if len(seen) > 12:
            raise ValueError("Máximo de 12 campos por modelo.")
    return tuple(seen.values())


def fill_fields(template: str, answers: dict[str, str], *, html: bool = False) -> str:
    field_map = {f.label.casefold(): f for f in fields_in(template)}
    def replacement(match):
        detail = match.group(2)
        label = detail.split("|", 1)[0].strip().casefold()
        field = field_map[label]
        value = str(answers.get(label, answers.get(field.label, field.default)))
        if len(value) > 600:
            raise ValueError(f"O campo {field.label} ultrapassa 600 caracteres.")
        if field.kind == "choice" and value not in field.options:
            raise ValueError(f"Opção inválida para «{field.label}».")
        return escape(value).replace("\n", "<br/>") if html else value
    return _FORM_RE.sub(replacement, template)


def _math(expression: str) -> str:
    tree = ast.parse(expression, mode="eval")
    def evaluate(node, depth=0):
        if depth > 9:
            raise ValueError("Cálculo excessivamente complexo.")
        if isinstance(node, ast.Expression):
            return evaluate(node.body, depth + 1)
        if isinstance(node, ast.Constant) and type(node.value) in (float, int):
            return node.value
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            value = evaluate(node.operand, depth + 1)
            return -value if isinstance(node.op, ast.USub) else value
        if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_MATH:
            left, right = evaluate(node.left, depth + 1), evaluate(node.right, depth + 1)
            try:
                result = _ALLOWED_MATH[type(node.op)](left, right)
            except (ZeroDivisionError, OverflowError) as exc:
                raise ValueError("Cálculo inválido ou divisão por zero.") from exc
            if abs(result) > 1_000_000_000:
                raise ValueError("Resultado fora do limite.")
            return result
        raise ValueError("Expressão de cálculo não permitida.")
    value = evaluate(tree)
    if abs(value) > 1_000_000_000:
        raise ValueError("Resultado fora do limite.")
    return f"{value:g}"


def advanced_variables(template: str, now: datetime | None = None) -> str:
    now = now or datetime.now()
    def date_offset(match):
        amount = int(match.group(1))
        if not -3650 <= amount <= 3650:
            raise ValueError("A data só pode variar até dez anos.")
        return (now + timedelta(days=amount)).strftime("%d/%m/%Y")
    result = _DATE_RE.sub(date_offset, template)
    def date_format(match):
        fmt = match.group(1)
        if not _ALLOWED_FORMAT.fullmatch(fmt):
            raise ValueError("Formato de data não permitido.")
        return now.strftime(fmt)[:100]
    result = _FORMAT_RE.sub(date_format, result)
    return _CALC_RE.sub(lambda m: _math(m.group(1)), result)


def has_steps(template: str) -> bool:
    return bool(_ACTION_RE.search(template))


def action_steps(template: str) -> tuple[Step, ...]:
    """Separa texto e ações. Limite de 20 etapas e 5 s no total."""
    result: list[Step] = []
    pos = 0
    total_delay = 0
    for match in _ACTION_RE.finditer(template):
        if match.start() > pos:
            result.append(Step("text", template[pos:match.start()]))
        token = match.group(1).lower()
        if token.startswith("espera"):
            delay = int(token.split(":", 1)[1]) if ":" in token else 250
            if not 50 <= delay <= 2000:
                raise ValueError("Cada espera deve ter de 50 a 2000 ms.")
            total_delay += delay
            result.append(Step("wait", delay))
        else:
            result.append(Step(token))
        pos = match.end()
    if pos < len(template):
        result.append(Step("text", template[pos:]))
    if len(result) > 20 or total_delay > 5000:
        raise ValueError("Automação excede 20 etapas ou 5 segundos de espera.")
    return tuple(result)
