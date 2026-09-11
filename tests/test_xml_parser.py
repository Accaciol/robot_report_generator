import tempfile
import unittest
from pathlib import Path

from core.xml_parser import (
    RobotOutputParser,
    _extract_gherkin_step,
    _status_from,
)
from models import Status


class TestXmlParser(unittest.TestCase):
    def setUp(self):
        self.example_xml = Path("example/output.xml").resolve()

    def test_parse_valid_output_xml(self):
        self.assertTrue(self.example_xml.is_file(), "example/output.xml must exist")
        parser = RobotOutputParser(str(self.example_xml))
        suites, stats = parser.parse()

        self.assertEqual(len(suites), 1)
        self.assertEqual(stats.total, 2)
        self.assertEqual(stats.passed, 1)
        self.assertEqual(stats.failed, 1)
        self.assertEqual(stats.skipped, 0)
        self.assertEqual(stats.pass_rate, 50.0)

        suite = suites[0]
        self.assertEqual(len(suite.tests), 2)
        test_pass = suite.tests[0]
        test_fail = suite.tests[1]

        self.assertEqual(test_pass.status, Status.PASS)
        self.assertIn("smoke", test_pass.tags)
        self.assertFalse(test_pass.is_failed)

        self.assertEqual(test_fail.status, Status.FAIL)
        self.assertIn("regression", test_fail.tags)
        self.assertTrue(test_fail.is_failed)
        self.assertIsNotNone(test_fail.failed_step)
        self.assertIn("rejeitar o login", test_fail.failed_step)
        self.assertIn("mensagem-erro", test_fail.message)

    def test_parse_non_existent_file(self):
        parser = RobotOutputParser("non_existent_file.xml")
        with self.assertRaises(FileNotFoundError):
            parser.parse()

    def test_parse_invalid_xml(self):
        with tempfile.NamedTemporaryFile(suffix=".xml", mode="w", delete=False) as f:
            f.write("This is not valid XML")
            temp_path = f.name
        try:
            parser = RobotOutputParser(temp_path)
            with self.assertRaises(ValueError):
                parser.parse()
        finally:
            Path(temp_path).unlink(missing_ok=True)

    def test_extract_gherkin_step(self):
        self.assertEqual(_extract_gherkin_step("Given usuário autenticado"), "Given usuário autenticado")
        self.assertEqual(_extract_gherkin_step("WHEN clico no botão"), "WHEN clico no botão")
        self.assertEqual(_extract_gherkin_step("then o resultado aparece"), "then o resultado aparece")
        self.assertEqual(_extract_gherkin_step("And outro passo"), "And outro passo")
        self.assertEqual(_extract_gherkin_step("But algo diferente"), "But algo diferente")
        self.assertIsNone(_extract_gherkin_step("Click Element"))

    def test_status_from(self):
        self.assertEqual(_status_from("PASS"), Status.PASS)
        self.assertEqual(_status_from("FAIL"), Status.FAIL)
        self.assertEqual(_status_from("SKIP"), Status.SKIP)
        self.assertEqual(_status_from("NOT RUN"), Status.NOT_RUN)
        self.assertEqual(_status_from("UNKNOWN"), Status.NOT_RUN)


if __name__ == "__main__":
    unittest.main()
