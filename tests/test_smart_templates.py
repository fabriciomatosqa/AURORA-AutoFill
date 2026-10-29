import unittest
from datetime import datetime
from app.smart_templates import (fields_in, fill_fields, advanced_variables,
                                 action_steps, has_steps)


class SmartTemplateTests(unittest.TestCase):
    def test_forms_and_repeated_names(self):
        s = "Olá {{campo:Nome}}. {{campo:Nome}}! {{escolha:Status|Aberto|Fechado}}"
        fields = fields_in(s)
        self.assertEqual(len(fields), 3)
        self.assertEqual([f.key for f in fields], ["nome", "nome#2", "status"])
        self.assertEqual(fields[2].options, ("Aberto", "Fechado"))
        self.assertEqual(fill_fields(s, {"nome": "João", "nome#2": "Maria",
                                         "status": "Fechado"}),
                         "Olá João. Maria! Fechado")
        self.assertEqual(fill_fields(s, {"nome": "Maria", "status": "Fechado"}),
                         "Olá Maria. Maria! Fechado")
        self.assertIn("&lt;", fill_fields("{{campo:Nome}}", {"nome": "<teste>"}, html=True))
        with self.assertRaises(ValueError):
            fill_fields(s, {"status": "Não existe"})

    def test_conflicts_and_bad_choice_rejected(self):
        # Identical labels can carry different defaults: each occurrence
        # is now an independent field in the form and in the final text.
        fields = fields_in("{{campo:Nome}}{{campo:Nome|outro}}")
        self.assertEqual([f.default for f in fields], ["", "outro"])
        self.assertEqual(fill_fields(
            "{{campo:Nome}}{{campo:Nome|outro}}", {"nome": "João", "nome#2": "Maria"}),
            "JoãoMaria")
        with self.assertRaises(ValueError):
            fields_in("{{escolha:Situação|Só uma}}")

    def test_repeated_placeholders_preserve_text_order_and_escape_html(self):
        pattern = ("O {{campo:Nome}} namora com a {{campo:Nome}}. "
                   "{{campo:Nome}} confirmou. "
                   "{{escolha:Status|Sim|Não}} / {{escolha:Status|Sim|Não}}")
        keys = [f.key for f in fields_in(pattern)]
        self.assertEqual(keys, ["nome", "nome#2", "nome#3", "status", "status#2"])
        answers = {"nome": "João", "nome#2": "Maria", "nome#3": "Pedro",
                   "status": "Sim", "status#2": "Não"}
        self.assertEqual(
            fill_fields(pattern, answers),
            "O João namora com a Maria. Pedro confirmou. Sim / Não")
        self.assertEqual(fill_fields(
            "<p>{{campo:Nome}} / {{campo:Nome}}</p>",
            {"nome": "<João>", "nome#2": "Maria & Ana"}, html=True),
            "<p>&lt;João&gt; / Maria &amp; Ana</p>")
        with self.assertRaises(ValueError):
            fields_in("{{campo:X}}" * 13)
        with self.assertRaises(ValueError):
            fill_fields("{{escolha:Status|Sim|Não}} {{escolha:Status|Sim|Não}}",
                        {"status": "Sim", "status#2": "Inválido"})

    def test_date_and_calculator_are_deterministic_without_eval(self):
        when = datetime(2026, 10, 29, 10, 15)
        self.assertEqual(advanced_variables(
            "{{data:+7}} / {{data:-1}} / {{data_formato:%Y-%m-%d}} / {{calculo:12.5*3}}",
            when), "05/11/2026 / 28/10/2026 / 2026-10-29 / 37.5")
        with self.assertRaises(ValueError):
            advanced_variables("{{calculo:10/0}}", when)
        with self.assertRaises(ValueError):
            advanced_variables("{{data:+9999}}", when)
        self.assertEqual(advanced_variables("{{data}}", when), "{{data}}")

    def test_multistep_boundaries(self):
        steps = action_steps("Nome{{tab}}123{{espera:300}}{{enter}}")
        self.assertEqual([(s.kind, s.value) for s in steps],
                         [("text", "Nome"), ("tab", ""), ("text", "123"),
                          ("wait", 300), ("enter", "")])
        self.assertTrue(has_steps("X{{tab}}"))
        with self.assertRaises(ValueError):
            action_steps("{{espera:2000}}" * 3)
        self.assertFalse(has_steps("{{campo:Nome}}"))


if __name__ == "__main__":
    unittest.main()
