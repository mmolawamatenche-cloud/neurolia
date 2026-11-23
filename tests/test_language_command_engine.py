import unittest

import lia4
import neurolia_prototype


class LanguageCommandEngineTest(unittest.TestCase):
    def test_find_command_supports_english_open_app(self):
        result = neurolia_prototype.find_command("open chrome", "English (South Africa)")
        self.assertEqual(result["action"], "open_app")
        self.assertEqual(result["target"], "chrome")

    def test_find_command_supports_setswana_open_app(self):
        result = neurolia_prototype.find_command("bula chrome", "Setswana")
        self.assertEqual(result["action"], "open_app")
        self.assertEqual(result["target"], "chrome")

    def test_find_command_supports_search_query(self):
        result = neurolia_prototype.find_command("search AI", "English (South Africa)")
        self.assertEqual(result["action"], "search")
        self.assertEqual(result["query"], "AI")

    def test_lia4_local_parser_supports_natural_open_and_volume_commands(self):
        open_result = lia4._local_parse("open chrome for me")
        self.assertEqual(open_result["action"], "open_app")
        self.assertEqual(open_result["target"], "chrome")

        volume_result = lia4._local_parse("turn the volume up")
        self.assertEqual(volume_result["action"], "volume_up")

        mute_result = lia4._local_parse("mute the volume")
        self.assertEqual(mute_result["action"], "mute")


if __name__ == "__main__":
    unittest.main()
