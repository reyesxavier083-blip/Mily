"""Tests for the multimodel registry, provider manager and router."""

from __future__ import annotations

import unittest

from leyra_core.models import (
    Capability,
    ModelEntry,
    ModelRegistry,
    ModelRouter,
    Provider,
    RouterError,
    TaskKind,
)

ENV = {"OPENAI_API_KEY": "sk-test", "ANTHROPIC_API_KEY": "  "}


class RegistryTests(unittest.TestCase):
    def test_default_models_are_consistent(self) -> None:
        registry = ModelRegistry()
        vision = registry.matching(task=TaskKind.VISION)
        self.assertTrue(vision)
        self.assertTrue(all(Capability.VISION in model.capabilities for model in vision))

    def test_duplicate_registration_rejected(self) -> None:
        registry = ModelRegistry(models=())
        model = ModelEntry("m", "p", "M", frozenset({Capability.TEXT}))
        registry.register(model)
        with self.assertRaises(RouterError):
            registry.register(model)

    def test_cost_filter(self) -> None:
        registry = ModelRegistry()
        cheap = registry.matching(max_cost_tier=1)
        self.assertTrue(cheap)
        self.assertTrue(all(model.cost_tier <= 1 for model in cheap))

    def test_invalid_model_rejected(self) -> None:
        with self.assertRaises(RouterError):
            ModelEntry("", "p", "M", frozenset({Capability.TEXT}))
        with self.assertRaises(RouterError):
            ModelEntry("m", "p", "M", frozenset({Capability.TEXT}), context_window=0)


class RouterTests(unittest.TestCase):
    def test_requires_credentials(self) -> None:
        router = ModelRouter(env={})
        with self.assertRaises(RouterError):
            router.route()
        self.assertIn("OPENAI_API_KEY", str(self._error(router)))

    def test_routes_only_to_configured_providers(self) -> None:
        router = ModelRouter(env=ENV)
        decision = router.route()
        self.assertEqual(decision.model.provider, "openai")
        self.assertEqual(decision.provider.id, "openai")
        self.assertTrue(decision.reason)

    def test_requested_model_must_be_configured(self) -> None:
        router = ModelRouter(env=ENV)
        with self.assertRaises(RouterError):
            router.route(requested_model="claude-3-5-sonnet-latest")
        with self.assertRaises(RouterError):
            router.route(requested_model="does-not-exist")

    def test_vision_request_without_vision_provider_fails(self) -> None:
        local_env = {"LEYRA_LOCAL_MODEL_URL": "http://127.0.0.1:11434"}
        router = ModelRouter(env=local_env)
        with self.assertRaises(RouterError):
            router.route(task=TaskKind.VISION, capabilities={Capability.VISION})

    def test_fallbacks_are_ordered_and_distinct(self) -> None:
        router = ModelRouter(env=ENV)
        decision = router.route(task=TaskKind.CHAT)
        ids = [decision.model.id] + [m.id for m in decision.fallbacks]
        self.assertEqual(len(ids), len(set(ids)))

    def test_health_never_exposes_secret_values(self) -> None:
        router = ModelRouter(env={"OPENAI_API_KEY": "sk-super-secret"})
        payload = router.health()
        rendered = str(payload)
        self.assertNotIn("sk-super-secret", rendered)
        self.assertEqual(payload["status"], "ok")
        openai = next(item for item in payload["providers"] if item["id"] == "openai")
        self.assertTrue(openai["configured"])
        self.assertEqual(openai["keyEnv"], "OPENAI_API_KEY")

    def test_local_only_configuration(self) -> None:
        router = ModelRouter(env={"LEYRA_LOCAL_MODEL_URL": "http://127.0.0.1:11434"})
        decision = router.route(prefer_local=True)
        self.assertTrue(decision.model.local)
        self.assertEqual(decision.provider.id, "local")

    @staticmethod
    def _error(router: ModelRouter) -> Exception:
        try:
            router.route()
        except RouterError as error:
            return error
        raise AssertionError("expected RouterError")


if __name__ == "__main__":
    unittest.main()
