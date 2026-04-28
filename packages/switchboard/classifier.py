# Copyright 2026 Human Systems. MIT License.
"""Classifier module for task classification with confidence scoring."""

from dataclasses import dataclass
from typing import Optional
import re

from switchboard.canonical_ids import TaskID


@dataclass
class ClassificationResult:
    """Result of task classification."""

    task_id: TaskID  # Canonical task identifier
    confidence: float  # 0.0 to 1.0
    reason: str  # Human-readable explanation of the classification
    alternatives: list[TaskID]  # Other possible task IDs
    requires_multi_step: bool = False
    estimated_complexity: str = "medium"  # "low", "medium", "high"
    metadata: Optional[dict] = None  # Additional routing metadata

    @property
    def classification(self) -> str:
        """Backward compatibility: return task_id as string."""
        return self.task_id.value


class Classifier:
    """Simple keyword-based classifier with confidence scoring.

    This classifier uses keyword matching to categorize incoming
    tasks. It can be extended later with LLM-based classification
    for better accuracy.

    Design decisions:
    - Simple first: keyword matching over ML-based approaches
    - Confidence scoring: quantifies how certain we are
    - Extensible: easy to add new categories or upgrade to ML
    """

    # Classification keywords and their weights
    # Higher weight = more specific match
    # Keys are TaskID enum values for type safety
    CLASSIFICATION_PATTERNS: dict[TaskID, dict] = {
        TaskID.REVERSE_ENGINEERING: {
            "keywords": [
                r"\breview\b",
                r"\binspect\b",
                r"\breverse\s+engineer",
                r"\banalyze\s+(?:the\s+)?(?:code|system|app|binary)\b",
                r"\banalyze\s+(?:the\s+)?(?:implementation|project|repository|repo|codebase)\b",
                r"\bhow\s+does\s+(?:this|it|the)\b",
                r"\bunderstand\s+(?:the\s+)?(?:code|logic|flow)",
                r"\bwhat\s+does\s+(?:this|function|class|module)\s+do",
                r"\bdebug",
                r"\btrace\s+(?:through|execution)",
                r"\bdisassembl",
                r"\bdecompil",
            ],
            "weight": 1.0,
        },
        TaskID.SYSTEM_DESIGN: {
            "keywords": [
                r"\bdesign\s+(?:a\s*|the\s*)?(?:system|architecture)",
                r"\barchitect",
                r"\bbackend\s+architecture",
                r"\bservice\s+architecture",
                r"\bscalab",
                r"\bhigh\s*level\s*(?:design|overview)",
                r"\bsystem\s*layout",
                r"\bcomponent\s*diagram",
            ],
            "weight": 1.0,
        },
        TaskID.DATA_ANALYSIS: {
            "keywords": [
                r"\bdata\s+(?:analysis|analytics)",
                r"\bpandas\b",
                r"\bdataframe\b",
                r"\banalyze\s+(?:this\s+|the\s+)?(?:data|dataset|csv|file)",
                r"\bstatistics\b",
                r"\bclean\s+(?:the\s+)?data",
                r"\btransform\s+(?:the\s+)?data",
            ],
            "weight": 1.0,
        },
        TaskID.VISUALIZATION: {
            "keywords": [
                r"\bvisualiz",
                r"\bplot",
                r"\bchart",
                r"\bgraph",
                r"\bdashboard",
            ],
            "weight": 0.95,
        },
        TaskID.CODING: {
            "keywords": [
                r"\bimplement\b",
                r"\bfix\b",
                r"\bbuild\b",
                r"\bwrite\s+(?:a\s+)?\w*\s*(?:function|class|code)",
                r"\bcode\s+(?:this|that|it)\b",
                r"\bcreate\s+(?:a\s+)?(?:function|method|api)",
                r"\brefactor\b",
                r"\blinting\b",
                r"\bformatting\b",
            ],
            "weight": 0.8,
        },
        TaskID.TESTING: {
            "keywords": [
                r"\btest",
                r"\bwrite\s+tests?",
                r"\bunit\s*test",
                r"\bintegration\s*test",
                r"\bpytest",
                r"\btest\s*coverage",
            ],
            "weight": 0.9,
        },
        TaskID.DOCUMENTATION: {
            "keywords": [
                r"\bdocument(?:ation)?\b",
                r"\bwrite\s+(?:the\s+)?(?:docs|documentation|readme|guide)",
                r"\breadme\b",
                r"\bexplain\b",
            ],
            "weight": 0.85,
        },
        TaskID.REPORTING: {
            "keywords": [
                r"\breport\b",
                r"\bsummary\b",
                r"\bsummarize\b",
                r"\bstatus\s*update\b",
                r"\bbrief\b",
            ],
            "weight": 0.8,
        },
        TaskID.SELF_UPGRADE: {
            "keywords": [
                r"\bself[- ]?(?:upgrade|improvement|growth|development)\b",
                r"\bpersonal[- ]?(?:growth|development|improvement)\b",
                r"\bdaily[- ]?audit\b",
                r"\bhabit[- ]?(?:building|formation|tracking|system)s?\b",
                r"\bleak\b",
                r"\bself[- ]?aware(?:ness)?\b",
                r"\blevel\s*up\b",
                r"\bmicro[- ]?experiment\b",
                r"\bstreak\b",
                r"\bupgrade\s*(?:loop|cycle|ladder)\b",
                r"\bproductivity\s*leak\b",
                r"\bhabits?\b.*\b(?:system|building|formation|track)\b",
            ],
            "weight": 1.0,
        },
        TaskID.TRADING_ANALYSIS: {
            "keywords": [
                r"\btrading\b",
                r"\btrade\b",
                r"\bstock\b",
                r"\bmarket\s*(?:analysis|data|trend)",
                r"\bportfolio\b",
                r"\bbacktest",
                r"\btechnical\s*(?:analysis|indicator)",
                r"\bcandle(?:stick)?\b",
                r"\bmoving\s*average\b",
                r"\brsi\b",
                r"\bmacd\b",
                r"\bhedg(?:e|ing)\b",
                r"\barbitrage\b",
                r"\bforex\b",
                r"\bcrypto(?:currency)?\s*(?:trading|analysis|market)?\b",
                r"\boption(?:s)?\s*(?:pricing|strategy|chain)\b",
                r"\bvolatility\b",
                r"\bsharpe\s*ratio\b",
                r"\bdrawdown\b",
                r"\bpnl\b",
                r"\bprofit\s*(?:and|&)?\s*loss\b",
            ],
            "weight": 1.0,
        },
        TaskID.CREATIVE_WRITING: {
            "keywords": [
                r"\bcreative\s*writ",
                r"\bwrite\s+(?:a\s+)?(?:\w+\s+)*(?:story|poem|essay|novel|script|narrative|fiction)",
                r"\bcompose\s+(?:a\s+)?(?:\w+\s+)*(?:story|poem|essay|novel|script|narrative|fiction|song|piece)",
                r"\bstorytelling\b",
                r"\bfiction\b",
                r"\bpoetry\b",
                r"\bpoem\b",
                r"\bnarrative\b",
                r"\bworld[- ]?build",
                r"\bcharacter\s*(?:development|arc|backstory)",
                r"\bplot\s*(?:twist|outline|structure)",
                r"\bdialogue\b",
                r"\bprose\b",
                r"\bscreenplay\b",
                r"\blyrics?\b",
                r"\bsonnet\b",
                r"\bhaiku\b",
            ],
            "weight": 1.0,
        },
        TaskID.MODEL_ROUTING: {
            "keywords": [
                r"\broute\s+(?:to\s+)?(?:nexus|model)",
                r"\buse\s+(?:the\s+)?nexus\s+(?:router|engine)",
                r"\bselect\s+(?:the\s+)?(?:best|optimal)\s+model",
                r"\bmodel\s+orchestration",
                r"\bmodel\s+selection",
                r"\bwhich\s+model\s+(?:should|to)\s+use",
                r"\bmcts\s+(?:routing|selection)",
                r"\bucb1\s+model",
                r"\bpuct\s+model",
                r"\bnexus\s+(?:mcts|router)",
            ],
            "weight": 1.0,
        },
        TaskID.MODEL_SELECTION: {
            "keywords": [
                r"\bselect\s+(?:a\s+)?model",
                r"\bchoose\s+(?:the\s+)?(?:llm|model)",
                r"\bpick\s+(?:the\s+)?best\s+model",
                r"\bmodel\s+recommendation",
                r"\bwhat\s+model\s+(?:for|to)",
                r"\bclaude\s+vs\s+gpt",
                r"\bwhich\s+llm",
                r"\boptimal\s+model",
            ],
            "weight": 0.9,
        },
        TaskID.GENERAL: {
            "keywords": [],  # Fallback category
            "weight": 0.5,
        },
    }

    # Patterns indicating multi-step tasks
    MULTI_STEP_PATTERNS = [
        r"\band\s+then",
        r"\bafter\s+that",
        r"\bfirst.*\bthen",
        r"\bthen\b",
        r"\bnext\b",
        r"\bfinally\b",
        r"\bboth.*\band",
        r"\bmulti(?:\s*[-_]?\s*step)?",
        r"\bseveral\s+(?:things|tasks|steps)",
    ]

    # Complexity indicators
    COMPLEXITY_HIGH = [
        r"\bcomplex",
        r"\bcomplicated",
        r"\bdifficult",
        r"\badvanced",
    ]

    COMPLEXITY_LOW = [
        r"\bsimple",
        r"\bbasic",
        r"\beasy",
        r"\bstraightforward",
        r"\bquick",
    ]

    def __init__(self, use_llm_fallback: bool = False):
        """Initialize the classifier.

        Args:
            use_llm_fallback: If True, use LLM for uncertain classifications
        """
        self.use_llm_fallback = use_llm_fallback
        # Instance-level pattern storage to avoid mutating class attributes
        self._classification_patterns: dict[TaskID, dict] = {
            k: {"keywords": list(v["keywords"]), "weight": v["weight"]}
            for k, v in self.CLASSIFICATION_PATTERNS.items()
        }
        self._compiled_patterns: dict[TaskID, list] = {}
        self._compile_patterns()

    def _compile_patterns(self):
        """Pre-compile regex patterns for performance."""
        for classification, config in self.CLASSIFICATION_PATTERNS.items():
            self._compiled_patterns[classification] = [
                re.compile(pattern, re.IGNORECASE) for pattern in config["keywords"]
            ]

        self._multi_step_patterns = [re.compile(p, re.IGNORECASE) for p in self.MULTI_STEP_PATTERNS]

        self._complexity_high_patterns = [
            re.compile(p, re.IGNORECASE) for p in self.COMPLEXITY_HIGH
        ]

        self._complexity_low_patterns = [re.compile(p, re.IGNORECASE) for p in self.COMPLEXITY_LOW]

    def classify(self, input_text: str) -> ClassificationResult:
        """Classify the input text into a task category.

        Args:
            input_text: The user's input to classify

        Returns:
            ClassificationResult with task_id, confidence, and reasoning
        """
        if not input_text or not input_text.strip():
            return ClassificationResult(
                task_id=TaskID.GENERAL,
                confidence=0.0,
                reason="Empty input; falling back to general agent",
                alternatives=[],
                requires_multi_step=False,
            )
        # Score each classification
        scores: dict[TaskID, float] = {}
        matches_by_task: dict[TaskID, list[str]] = {}
        for task_id, config in self._classification_patterns.items():
            if task_id == TaskID.GENERAL:
                continue  # Skip general, it's the fallback

            patterns = self._compiled_patterns[task_id]
            matched_patterns = [p.pattern for p in patterns if p.search(input_text)]
            matches = len(matched_patterns)

            if matches > 0:
                scores[task_id] = matches * config["weight"]
                matches_by_task[task_id] = matched_patterns

        # Determine best classification
        if not scores:
            # Default to general
            return ClassificationResult(
                task_id=TaskID.GENERAL,
                confidence=0.3,
                reason="No specific patterns matched; falling back to general agent",
                alternatives=[],
                requires_multi_step=self._detect_multi_step(input_text),
                estimated_complexity=self._estimate_complexity(input_text),
            )

        # Sort by score
        sorted_scores = sorted(scores.items(), key=lambda x: x[1], reverse=True)
        best_task, best_score = sorted_scores[0]
        second_best_score = sorted_scores[1][1] if len(sorted_scores) > 1 else 0.0

        confidence = self._calculate_confidence(
            match_count=len(matches_by_task[best_task]),
            best_score=best_score,
            second_best_score=second_best_score,
        )

        # Build reason string
        matched_keywords = matches_by_task[best_task]
        reason = (
            f"Matched keywords: {', '.join(matched_keywords)}"
            if matched_keywords
            else "High pattern weight for this classification"
        )

        # Get alternatives (next best task IDs)
        alternatives = [t for t, s in sorted_scores[1:4] if s > 0]

        return ClassificationResult(
            task_id=best_task,
            confidence=confidence,
            reason=reason,
            alternatives=alternatives,
            requires_multi_step=self._detect_multi_step(input_text),
            estimated_complexity=self._estimate_complexity(input_text),
        )

    def _calculate_confidence(
        self, match_count: int, best_score: float, second_best_score: float
    ) -> float:
        """Estimate confidence from evidence strength and score separation."""
        if match_count <= 0 or best_score <= 0:
            return 0.3

        evidence_ratio = min(match_count / 3, 1.0)
        margin_ratio = max(best_score - second_best_score, 0.0) / best_score
        confidence = 0.3 + (0.3 * evidence_ratio) + (0.3 * margin_ratio)
        return round(min(confidence, 0.95), 3)

    def _detect_multi_step(self, input_text: str) -> bool:
        """Detect if the task requires multiple steps/agents."""
        return any(p.search(input_text) for p in self._multi_step_patterns)

    def _estimate_complexity(self, input_text: str) -> str:
        """Estimate task complexity based on keywords."""
        if any(p.search(input_text) for p in self._complexity_high_patterns):
            return "high"
        if any(p.search(input_text) for p in self._complexity_low_patterns):
            return "low"
        return "medium"

    def add_classification(self, task_id: TaskID, keywords: list[str], weight: float = 1.0) -> None:
        """Add a new classification category.

        Args:
            task_id: The TaskID enum for the classification
            keywords: List of regex patterns for matching
            weight: Weight multiplier for this classification
        """
        self._classification_patterns[task_id] = {
            "keywords": list(keywords),
            "weight": weight,
        }
        self._compiled_patterns[task_id] = [re.compile(k, re.IGNORECASE) for k in keywords]
