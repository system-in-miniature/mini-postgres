import unittest
from pathlib import Path


class DocumentationHomepageTest(unittest.TestCase):
    def test_homepages_are_language_separated(self) -> None:
        english = Path("docs/index.md").read_text(encoding="utf-8")
        chinese = Path("docs/zh/index.md").read_text(encoding="utf-8")

        self.assertNotRegex(english, r"[\u4e00-\u9fff]")
        self.assertNotIn("Learning modes", chinese)
        self.assertIn("Learning modes", english)
        self.assertIn("学习模式", chinese)

    def test_benchmark_entry_and_resume_evidence_are_bilingual(self) -> None:
        english = Path("bench/README.md").read_text(encoding="utf-8")
        chinese = Path("bench/README.zh-CN.md").read_text(encoding="utf-8")
        chinese_readme = Path("README.zh-CN.md").read_text(encoding="utf-8")

        self.assertNotRegex(english, r"[\u4e00-\u9fff]")
        self.assertIn("可复现基准", chinese)
        self.assertIn("6,252.45 倍", chinese_readme)


if __name__ == "__main__":
    unittest.main()
