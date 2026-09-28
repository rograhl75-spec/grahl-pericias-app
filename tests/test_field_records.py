import unittest

from core import field_records


class FieldRecordTests(unittest.TestCase):
    def test_field_schema_keeps_expected_order(self):
        labels = [field["label"] for field in field_records.FIELD_RECORD_FIELDS]
        self.assertEqual(
            labels,
            [
                "1. Data da Vistoria *",
                "2. Horário da Vistoria *",
                "3. Local da Vistoria *",
                "4. Pessoas Presentes",
                "5. Informações do Segurado / Autor",
                "6. Informações do Empregador / Acompanhante",
                "7. Medições Realizadas",
            ],
        )

    def test_validar_registro_campo_exige_campos_obrigatorios(self):
        erros = field_records.validar_registro_campo(
            {
                "campo_data": "",
                "campo_horario": "25:99",
                "local_diligencia": "   ",
            }
        )

        self.assertEqual(
            erros,
            {
                "campo_data": "Informe a data da vistoria.",
                "campo_horario": "Use o formato HH:MM.",
                "local_diligencia": "Informe o local da vistoria.",
            },
        )

    def test_validar_registro_campo_aceita_dados_validos(self):
        erros = field_records.validar_registro_campo(
            {
                "campo_data": "28/09/2026",
                "campo_horario": "14:30",
                "local_diligencia": "Rua Exemplo, 123",
                "presentes_pericia": "Perito e assistente",
            }
        )

        self.assertEqual(erros, {})

    def test_atualizar_campos_memorizados_reaproveita_apenas_valores_preenchidos(self):
        atualizados = field_records.atualizar_campos_memorizados(
            {"local_diligencia": "Local antigo"},
            {
                "local_diligencia": "Rua Nova, 55",
                "presentes_pericia": "Autor e advogado",
            },
        )

        self.assertEqual(
            atualizados,
            {
                "local_diligencia": "Rua Nova, 55",
                "presentes_pericia": "Autor e advogado",
            },
        )


if __name__ == "__main__":
    unittest.main()
