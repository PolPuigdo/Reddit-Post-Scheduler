import unittest

from app.services.cached_composer_capabilities_service import CachedComposerCapabilitiesService


class DummyBaseCapabilitiesService:
    def __init__(self):
        self.calls = 0
        self.raise_on_next_call = False

    def inspect(self, target_type: str, subreddit: str | None = None):
        self.calls += 1
        if self.raise_on_next_call:
            self.raise_on_next_call = False
            raise RuntimeError("boom")
        return {
            "call": self.calls,
            "target_type": target_type,
            "subreddit": subreddit,
        }


class CachedComposerCapabilitiesServiceTests(unittest.TestCase):
    def test_cache_hit_after_first_call(self):
        base = DummyBaseCapabilitiesService()
        service = CachedComposerCapabilitiesService(base_service=base, ttl_seconds=60)

        first = service.inspect(target_type="subreddit", subreddit="python")
        second = service.inspect(target_type="subreddit", subreddit="python")

        self.assertEqual(base.calls, 1)
        self.assertEqual(first, second)

    def test_cache_entry_expires_after_ttl(self):
        base = DummyBaseCapabilitiesService()
        now = [100.0]
        service = CachedComposerCapabilitiesService(
            base_service=base,
            ttl_seconds=10,
            time_func=lambda: now[0],
        )

        service.inspect(target_type="subreddit", subreddit="python")
        now[0] = 111.0
        service.inspect(target_type="subreddit", subreddit="python")

        self.assertEqual(base.calls, 2)

    def test_cache_key_normalizes_target_and_subreddit(self):
        base = DummyBaseCapabilitiesService()
        service = CachedComposerCapabilitiesService(base_service=base, ttl_seconds=60)

        service.inspect(target_type=" SUBREDDIT ", subreddit=" Python ")
        service.inspect(target_type="subreddit", subreddit="python")

        self.assertEqual(base.calls, 1)

    def test_profile_cache_key_ignores_subreddit(self):
        base = DummyBaseCapabilitiesService()
        service = CachedComposerCapabilitiesService(base_service=base, ttl_seconds=60)

        service.inspect(target_type="profile", subreddit="python")
        service.inspect(target_type="profile", subreddit=None)

        self.assertEqual(base.calls, 1)

    def test_errors_are_not_cached(self):
        base = DummyBaseCapabilitiesService()
        service = CachedComposerCapabilitiesService(base_service=base, ttl_seconds=60)
        base.raise_on_next_call = True

        with self.assertRaises(RuntimeError):
            service.inspect(target_type="subreddit", subreddit="python")

        response = service.inspect(target_type="subreddit", subreddit="python")
        self.assertEqual(base.calls, 2)
        self.assertEqual(response["call"], 2)


if __name__ == "__main__":
    unittest.main()
