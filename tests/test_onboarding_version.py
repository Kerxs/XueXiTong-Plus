import unittest

from ui.controller import (DISCLAIMER_VERSION, ONBOARDING_STEPS, ONBOARDING_VERSION, disclaimer_accepted,
                           onboarding_done, onboarding_plan)


class OnboardingVersionTest(unittest.TestCase):
    def test_finished_current_guide(self):
        self.assertTrue(onboarding_done("true", ONBOARDING_VERSION))
        self.assertTrue(onboarding_done(True, str(ONBOARDING_VERSION)))   # QSettings may hand back strings

    def test_older_guide_is_shown_again(self):
        # Users from before guide versions existed have done=true and no version.
        self.assertFalse(onboarding_done("true", None))
        self.assertFalse(onboarding_done("true", 0))
        self.assertFalse(onboarding_done("true", ONBOARDING_VERSION - 1))
        self.assertFalse(onboarding_done("true", "garbage"))

    def test_not_finished(self):
        self.assertFalse(onboarding_done("false", ONBOARDING_VERSION))


class OnboardingPlanTest(unittest.TestCase):
    """Someone who finished an older guide only sees what is new; the disclaimer only when it changed."""

    ALL = [sid for sid, _ in ONBOARDING_STEPS]

    def test_new_user_gets_the_whole_guide(self):
        self.assertEqual(onboarding_plan("false", 0, ""), (self.ALL, False))

    def test_finished_an_older_guide_only_new_steps(self):
        steps, new_only = onboarding_plan("true", 3, "1.2.7")
        self.assertEqual((steps, new_only), (["auto", "telemetry"], True))   # added in guide versions 4 and 5
        self.assertEqual(onboarding_plan("true", 4, "1.2.9"), (["telemetry"], True))   # 1.2.9 users: one page
        self.assertNotIn("disclaimer", steps)                        # accepted before: not written out again

    def test_up_to_date_shows_nothing(self):
        self.assertEqual(onboarding_plan("true", ONBOARDING_VERSION, DISCLAIMER_VERSION), ([], True))
        self.assertEqual(onboarding_plan("true", ONBOARDING_VERSION, "1.2.9"), ([], True))   # old value: app version

    def test_changed_disclaimer_is_the_only_thing_asked_again(self):
        self.assertEqual(onboarding_plan("true", ONBOARDING_VERSION, ""), (["disclaimer"], True))
        self.assertEqual(disclaimer_accepted("1.2.9"), 1)
        self.assertEqual(disclaimer_accepted("3"), 3)
        self.assertEqual(disclaimer_accepted(None), 0)

    def test_reopened_guide_is_complete_but_without_an_accepted_disclaimer(self):
        steps, new_only = onboarding_plan("false", ONBOARDING_VERSION, DISCLAIMER_VERSION)
        self.assertEqual(steps, [s for s in self.ALL if s != "disclaimer"])
        self.assertFalse(new_only)

    def test_every_step_has_a_version_no_newer_than_the_guide(self):
        self.assertTrue(all(1 <= since <= ONBOARDING_VERSION for _, since in ONBOARDING_STEPS))


if __name__ == "__main__":
    unittest.main()
