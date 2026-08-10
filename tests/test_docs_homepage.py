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


if __name__ == "__main__":
    unittest.main()
