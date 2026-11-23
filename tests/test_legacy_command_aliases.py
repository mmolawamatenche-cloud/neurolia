import unittest
from unittest.mock import patch

import lia4


class LegacyCommandAliasTest(unittest.TestCase):
    def test_open_chrome_alias_is_supported(self):
        with patch.object(lia4.os, "system") as mock_system:
            result = lia4.execute({"action": "open_chrome"})

        self.assertEqual(result, "Opening Chrome.")
        mock_system.assert_called_once_with("start chrome")

    def test_volume_up_alias_is_supported(self):
        with patch.object(lia4.pyautogui, "press") as mock_press:
            result = lia4.execute({"action": "volume_up"})

        self.assertEqual(result, "Volume up.")
        mock_press.assert_called_once_with("volumeup")


if __name__ == "__main__":
    unittest.main()
