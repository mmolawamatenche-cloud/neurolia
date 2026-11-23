import unittest
from unittest.mock import patch

from lia_core import (
    ConfirmationGate,
    GestureStabilizer,
    find_tesseract,
    is_allowed,
    match_app,
    match_simple_command,
    needs_confirmation,
)


class LiaCoreTest(unittest.TestCase):
    def test_app_matching_prefers_clear_names_and_rejects_short_input(self):
        apps = {"google chrome": "chrome", "notepad": "notepad"}

        match = match_app("please open google chrome", apps)
        self.assertEqual((match.name, match.target), ("google chrome", "chrome"))
        self.assertIsNone(match_app("no", apps).name)
        self.assertIsNone(match_app("unrelated application name", apps).name)

    def test_simple_commands_match_whole_words(self):
        self.assertEqual(match_simple_command("please mute"), {
            "action": "mute",
            "reply": "Muted.",
        })
        self.assertIsNone(match_simple_command("commute to work"))

    def test_action_allowlist_limits_hotkeys_and_flags_risky_actions(self):
        self.assertTrue(is_allowed({"action": "hotkey", "keys": ["ctrl", "c"]}))
        self.assertFalse(is_allowed({"action": "hotkey", "keys": ["ctrl", "delete"]}))
        self.assertFalse(is_allowed({"action": "unknown_action"}))
        self.assertTrue(needs_confirmation({"action": "close_window"}))
        self.assertTrue(needs_confirmation({"action": "hotkey", "keys": ["l", "win"]}))

    def test_confirmation_gate_resolves_and_expires_actions(self):
        now = [0.0]
        gate = ConfirmationGate(timeout=4.0, clock=lambda: now[0])
        action = {"action": "close_tab"}

        gate.ask(action)
        self.assertEqual(gate.resolve("yes please"), ("confirmed", action))
        gate.ask(action)
        self.assertEqual(gate.resolve("no"), ("cancelled", None))
        gate.ask(action)
        now[0] = 5.0
        self.assertEqual(gate.resolve("yes"), (None, None))

    def test_gesture_stabilizer_calibrates_and_requires_held_movement(self):
        now = [0.0]
        stabilizer = GestureStabilizer(
            hold_frames=2,
            cooldown=1.0,
            head_delta=0.1,
            calibrate_frames=2,
            clock=lambda: now[0],
        )

        self.assertIsNone(stabilizer.update(head_xy=(0.5, 0.5)))
        self.assertIsNone(stabilizer.update(head_xy=(0.5, 0.5)))
        self.assertTrue(stabilizer.calibrated)
        self.assertIsNone(stabilizer.update(head_xy=(0.7, 0.5)))
        self.assertEqual(stabilizer.update(head_xy=(0.7, 0.5)), "head_swipe_right")
        self.assertIsNone(stabilizer.update(head_xy=(0.7, 0.5)))

    def test_tesseract_lookup_honours_configured_path(self):
        with patch.dict("os.environ", {"TESSERACT_CMD": "C:\\tools\\tesseract.exe"}):
            with patch("lia_core.os.path.exists", return_value=True):
                self.assertEqual(find_tesseract(), "C:\\tools\\tesseract.exe")


if __name__ == "__main__":
    unittest.main()
