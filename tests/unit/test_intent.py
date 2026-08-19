"""Tests for intent extraction and planning with mocked provider."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from computepilot.agent.cost import CostEstimator
from computepilot.agent.generator import WorkflowGenerator
from computepilot.agent.intent import Intent, IntentExtractor
from computepilot.agent.planner import Planner
from computepilot.agent.provider import LLMProvider, LLMResponse


@dataclass
class FakeProvider:
    """A fake LLM provider that returns canned responses."""

    canned: dict[str, Any] = field(default_factory=dict)
    last_prompt: str = ""

    def generate(
        self,
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.last_prompt = user_prompt
        content = self.canned.get("generate", "fake response")
        return LLMResponse(content=content)

    def structured_output(
        self,
        output_model: type[BaseModel],
        system_prompt: str,
        user_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.0,
    ) -> LLMResponse:
        self.last_prompt = user_prompt
        if "parsed" in self.canned:
            parsed = self.canned["parsed"]
        else:
            parsed = output_model(
                verb="train",
                target="bert",
                parameters={"epochs": 3},
                resources={"cpu": 4, "memory": "8GB", "gpu": 1},
                constraints=[],
                assumptions=[],
            )
        return LLMResponse(content="", parsed=parsed)


# Ensure FakeProvider satisfies the LLMProvider protocol
def _check_protocol() -> None:
    _: LLMProvider = FakeProvider()


class TestIntentExtractor:
    def test_extract_returns_intent(self) -> None:
        provider = FakeProvider()
        extractor = IntentExtractor(provider)
        intent = extractor.extract("train BERT on GLUE")
        assert isinstance(intent, Intent)
        assert intent.verb == "train"
        assert intent.target == "bert"
        assert intent.parameters["epochs"] == 3
        assert intent.resources["gpu"] == 1

    def test_extract_with_custom_intent(self) -> None:
        custom = Intent(
            verb="evaluate",
            target="my-model",
            parameters={"batch_size": 32},
        )
        provider = FakeProvider(canned={"parsed": custom})
        extractor = IntentExtractor(provider)
        intent = extractor.extract("evaluate my-model")
        assert intent.verb == "evaluate"
        assert intent.target == "my-model"
        assert intent.parameters["batch_size"] == 32


class TestIntentModel:
    def test_defaults(self) -> None:
        intent = Intent(verb="run", target="test")
        assert intent.parameters == {}
        assert intent.resources == {"cpu": 1, "memory": "2GB", "gpu": 0}
        assert intent.constraints == []
        assert intent.assumptions == []

    def test_round_trip_json(self) -> None:
        intent = Intent(verb="train", target="resnet", parameters={"lr": 0.001})
        data = intent.model_dump()
        restored = Intent.model_validate(data)
        assert restored.verb == "train"
        assert restored.target == "resnet"
        assert restored.parameters["lr"] == 0.001


class TestPlanner:
    def test_plan_creates_workflow(self) -> None:
        intent = Intent(
            verb="train",
            target="resnet50",
            parameters={"epochs": 10},
            resources={"cpu": 8, "memory": "16GB", "gpu": 4},
        )
        planner = Planner()
        wf = planner.plan(intent)
        assert wf.name == "train_resnet50"
        assert len(wf.tasks) >= 1
        task = wf.tasks[0]
        assert task.id == "train_resnet50"
        assert task.resources.cpu == 8
        assert task.resources.gpu == 4

    def test_plan_infers_shell_type(self) -> None:
        intent = Intent(verb="shell", target="script.sh")
        planner = Planner()
        wf = planner.plan(intent)
        from computepilot.models.workflow import TaskType

        assert wf.tasks[0].type == TaskType.SHELL


class TestWorkflowGenerator:
    def test_generate(self) -> None:
        provider = FakeProvider()
        gen = WorkflowGenerator(provider)
        wf = gen.generate("train BERT on GLUE")
        assert wf.name == "train_bert"
        assert len(wf.tasks) >= 1

    def test_extract_intent(self) -> None:
        provider = FakeProvider()
        gen = WorkflowGenerator(provider)
        intent = gen.extract_intent("evaluate model X")
        assert isinstance(intent, Intent)


class TestCostEstimator:
    def test_estimate(self) -> None:
        intent = Intent(verb="train", target="resnet")
        planner = Planner()
        wf = planner.plan(intent)
        estimator = CostEstimator()
        estimate = estimator.estimate(wf)
        assert estimate.task_count >= 1
        assert estimate.total_cost > 0
        assert estimate.currency == "USD"

    def test_estimate_with_custom_rates(self) -> None:
        from computepilot.models.workflow import TaskType

        intent = Intent(verb="train", target="test")
        planner = Planner()
        wf = planner.plan(intent)
        estimator = CostEstimator(rates={TaskType.PYTHON: 0.99})
        estimate = estimator.estimate(wf)
        assert estimate.total_cost > 0
