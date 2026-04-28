# Copyright 2026 Human Systems. MIT License.
"""Integration of MCTS router with Switchboard classifier."""

from switchboard.classifier import ClassificationResult, Classifier
from switchboard.mcts_router import ModelSelectionMCTS, TaskFeatures


class MCTSEnhancedClassifier(Classifier):
    """Classifier that uses MCTS for model selection.

    Extends the base keyword classifier with MCTS-based model routing
    for more intelligent LLM selection.
    """

    def __init__(
        self,
        use_llm_fallback: bool = False,
        use_mcts_routing: bool = True,
        mcts_budget: int = 50,
    ):
        super().__init__(use_llm_fallback)
        self.use_mcts_routing = use_mcts_routing
        if use_mcts_routing:
            from switchboard.mcts_router import create_mcts_router

            self.mcts_router = create_mcts_router(budget=mcts_budget)
        else:
            self.mcts_router = None

    def classify(self, input_text: str) -> ClassificationResult:
        """Classify with optional MCTS model selection."""
        result = super().classify(input_text)

        if self.use_mcts_routing and self.mcts_router:
            # Extract features for MCTS
            features = self._extract_features(input_text, result)

            # Run MCTS to select best model
            selection = self.mcts_router.select_model(features)

            # Attach model selection to result metadata
            if result.metadata is None:
                result.metadata = {}
            result.metadata["mcts_model_selection"] = {
                "model_id": selection.model.id,
                "model_name": selection.model.name,
                "confidence": float(selection.confidence),
                "expected_reward": float(selection.expected_reward),
                "simulations": selection.simulations_run,
                "path": selection.selection_path,
            }

        return result

    def _extract_features(
        self, input_text: str, classification: ClassificationResult
    ) -> TaskFeatures:
        """Extract task features for MCTS model selection."""
        # Estimate tokens (rough approximation: 4 chars ~= 1 token)
        estimated_tokens = len(input_text) // 4

        # Determine domain from classification
        domain_map = {
            "coding": "coding",
            "testing": "coding",
            "data_analysis": "analysis",
            "visualization": "analysis",
            "documentation": "writing",
            "reporting": "writing",
            "reverse_engineering": "analysis",
            "system_design": "analysis",
            "general": "general",
        }
        domain = domain_map.get(classification.task_id.value, "general")

        # Determine urgency from input
        urgency = "medium"
        text_lower = input_text.lower()
        if any(w in text_lower for w in ["quick", "fast", "urgent", "now", "asap"]):
            urgency = "high"
        elif any(w in text_lower for w in ["whenever", "no rush", "later", "someday"]):
            urgency = "low"

        # Determine requirements
        requires_code = domain == "coding"
        requires_creativity = domain == "writing" or "creative" in text_lower
        requires_reasoning = classification.estimated_complexity == "high"

        return TaskFeatures(
            complexity=classification.estimated_complexity,
            estimated_tokens=estimated_tokens,
            requires_code=requires_code,
            requires_creativity=requires_creativity,
            requires_reasoning=requires_reasoning,
            domain=domain,
            urgency=urgency,
        )
