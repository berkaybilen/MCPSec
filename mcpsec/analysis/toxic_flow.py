"""analysis/toxic_flow.py — Toxic Flow Analyzer

Statically analyzes MCP tool schemas to detect dangerous U/S/E label
combinations and writes results to toxic_flow_result.json.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from itertools import product
from typing import Any

logger = logging.getLogger("analysis.toxic_flow")

# ---------------------------------------------------------------------------
# Module-level constants (keyword dictionaries)
# ---------------------------------------------------------------------------

_KEYWORDS: dict[str, dict[str, tuple]] = {
    "U": {
        "primary":    ("fetch", "scrape", "crawl", "download", "ingest", "http_get", "web_request", "get_url", "pull"),
        "secondary":  ("url", "endpoint", "api_call", "external", "remote", "internet", "web", "browse", "request", "retrieve", "import", "load"),
        "contextual": ("from url", "from web", "user input", "user provided", "external source", "remote resource", "third party", "untrusted", "public", "from the internet"),
    },
    "S": {
        "primary":    ("read_file", "query_db", "list_directory", "get_secret", "read_config", "access_database", "get_credentials", "read_env", "execute_shell", "run_command"),
        "secondary":  ("file", "path", "directory", "folder", "database", "db", "sql", "query", "secret", "credential", "token", "key", "config", "env", "password", "private", "internal", "system", "shell", "exec", "command"),
        "contextual": ("from disk", "file system", "filesystem", "database", "sensitive", "private", "confidential", "internal resource", "credentials", "environment variable", "secret store", "read from", "access to"),
    },
    "E": {
        "primary":    ("send_email", "post_webhook", "http_post", "upload", "publish", "push", "write_external", "notify", "forward"),
        "secondary":  ("email", "smtp", "webhook", "slack", "discord", "telegram", "sms", "export", "outbound", "send", "transmit", "broadcast", "deliver", "dispatch"),
        "contextual": ("sends to", "posts to", "uploads to", "forwards to", "external destination", "outbound", "notify", "deliver to", "write to remote", "to external"),
    },
}

_TIER_POINTS: dict[str, int] = {"primary": 3, "secondary": 2, "contextual": 1}

_SUPPRESSORS: dict[str, tuple] = {
    "U": ("cache", "local", "internal", "memory", "mock", "test", "dummy", "static", "fake", "stub", "simulate"),
    "S": ("test", "mock", "dummy", "example", "sample", "demo", "fake", "stub", "template"),
    "E": ("test", "mock", "local", "dry_run", "preview", "simulate", "check", "verify", "validate", "debug"),
}

_COMPOUNDS: dict[str, tuple] = {
    "U": (("fetch", "url"), ("fetch", "web"), ("fetch", "external"), ("read", "url"), ("load", "remote"), ("get", "external"), ("scrape", "web"), ("download", "file"), ("retrieve", "url")),
    "S": (("read", "file"), ("read", "config"), ("read", "env"), ("access", "key"), ("get", "password"), ("get", "credential"), ("query", "database"), ("query", "db"), ("exec", "sql"), ("list", "directory"), ("read", "secret"), ("run", "command")),
    "E": (("send", "email"), ("send", "message"), ("post", "webhook"), ("post", "request"), ("upload", "file"), ("write", "remote"), ("forward", "to"), ("push", "to"), ("transmit", "data"), ("export", "data")),
}

_PARAM_PATTERNS: dict[str, tuple] = {
    "U": (("url", 3), ("endpoint", 3), ("source_url", 3), ("web_url", 3), ("remote_url", 3), ("webhook", 2), ("uri", 2), ("link", 1)),
    "S": (("password", 3), ("api_key", 3), ("secret", 3), ("private_key", 3), ("credentials", 3), ("token", 2), ("auth_token", 3), ("db_password", 3), ("connection_string", 2), ("path", 2), ("file_path", 3), ("config_path", 2), ("env_file", 3), ("ssh_key", 3), ("access_key", 3)),
    "E": (("webhook_url", 3), ("email", 3), ("to_email", 3), ("recipient", 3), ("smtp_host", 3), ("destination", 2), ("target_url", 2), ("upload_url", 3), ("callback_url", 2), ("notify_url", 2)),
}

_ANCHOR_PHRASES: dict[str, tuple] = {
    "U": (
        "receives input from external untrusted source",
        "fetches content from user-provided URL",
        "reads data from web or network",
        "accepts user input without validation",
        "retrieves content from remote location",
        "downloads data from external source",
        "scrapes content from website",
    ),
    "S": (
        "accesses credentials or private keys",
        "reads sensitive configuration files",
        "queries internal database with private data",
        "accesses filesystem with sensitive information",
        "reads environment variables or secrets",
        "retrieves authentication tokens",
        "accesses confidential internal resources",
    ),
    "E": (
        "sends data to external destination",
        "posts content to remote webhook",
        "transmits information outside the system",
        "uploads files to external storage",
        "sends email with content",
        "notifies external service with data",
        "forwards data to third party",
    ),
}

_CONFIDENCE_BANDS: list[tuple[float, str]] = [
    (0.85, "VERY_HIGH"),
    (0.70, "HIGH"),
    (0.50, "MEDIUM"),
    (0.35, "LOW"),
    (0.0,  "VERY_LOW"),
]

_RECOMMENDATION_TEMPLATES: dict[str, str] = {
    "lethal_trifecta":    "Move {e} to a separate agent with restricted access. Add a prompt injection filter between {u} and {s}. Require human approval before {e} executes.",
    "sensitive_external": "Restrict {s} to safe paths/tables/scopes. Add a destination allowlist to {e}.",
    "untrusted_sensitive":"Add a prompt injection filter to the output of {u} before it reaches {s}.",
    "untrusted_external": "Require human approval before {e} executes when triggered after {u}.",
    "single_S":           "Current risk is LOW. Avoid adding External Output tools to this agent.",
    "single_E":           "Current risk is LOW. Avoid adding Sensitive Access tools to this agent.",
}

_LABELS: tuple[str, ...] = ("U", "S", "E")

_PACKAGE_ROOT = os.path.dirname(os.path.abspath(__file__))


# ---------------------------------------------------------------------------
# ToxicFlowAnalyzer
# ---------------------------------------------------------------------------

class ToxicFlowAnalyzer:
    """
    Statically analyzes tool schemas from a discovery result to detect
    dangerous U/S/E label combinations and writes toxic_flow_result.json.
    """

    def __init__(self, config: Any, result_path: str) -> None:
        self._config = config
        self._result_path = result_path
        self._model: Any = None
        self._anchor_embeddings: dict[str, Any] = {}
        if getattr(config, "semantic", None) and config.semantic.enabled:
            self._init_semantic()

    def _init_semantic(self) -> None:
        try:
            from sentence_transformers import SentenceTransformer  # noqa: PLC0415
            model_name = self._config.semantic.model
            logger.info("Loading semantic model '%s' …", model_name)
            self._model = SentenceTransformer(model_name)
            for label, phrases in _ANCHOR_PHRASES.items():
                self._anchor_embeddings[label] = self._model.encode(list(phrases), convert_to_numpy=True)
            logger.info("Semantic model loaded; anchor embeddings computed.")
        except ImportError:
            logger.warning(
                "sentence-transformers not installed — semantic similarity disabled. "
                "Run: pip install sentence-transformers"
            )
        except Exception as exc:
            logger.error("Semantic model init failed (non-fatal): %s", exc)

    def run(self, discovery_result: dict) -> dict:
        """Analyze discovery_result, write toxic_flow_result.json, return result dict."""
        scan_id = "tf_" + datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")

        all_tools: dict[str, dict] = {}
        for backend_data in discovery_result.get("backends", {}).values():
            for tool_name, tool_data in backend_data.get("tools", {}).items():
                all_tools[tool_name] = tool_data

        tool_results: dict[str, dict] = {}
        label_groups: dict[str, list[str]] = {lbl: [] for lbl in _LABELS}

        for tool_name, tool_data in all_tools.items():
            tr = self._analyze_tool(tool_name, tool_data)
            tool_results[tool_name] = tr
            for lbl in tr["labels"]:
                label_groups[lbl].append(tool_name)

        session_severity = self._compute_session_severity(label_groups)
        dangerous_paths = self._build_dangerous_paths(label_groups)
        single_tool_risks = self._build_single_tool_risks(label_groups)

        labeled_count = sum(1 for tr in tool_results.values() if tr["labels"])

        summary = {
            "critical_paths": sum(1 for p in dangerous_paths if p["severity"] == "CRITICAL"),
            "high_paths":     sum(1 for p in dangerous_paths if p["severity"] == "HIGH"),
            "medium_paths":   sum(1 for p in dangerous_paths if p["severity"] == "MEDIUM"),
            "low_risks":      len(single_tool_risks),
            "u_tools":        label_groups["U"],
            "s_tools":        label_groups["S"],
            "e_tools":        label_groups["E"],
        }

        result = {
            "generated_at":    datetime.now(tz=timezone.utc).isoformat(),
            "scan_id":         scan_id,
            "session_severity": session_severity,
            "tool_count":      len(all_tools),
            "labeled_count":   labeled_count,
            "tools":           tool_results,
            "dangerous_paths": dangerous_paths,
            "single_tool_risks": single_tool_risks,
            "summary":         summary,
        }

        logger.info(
            "Toxic flow complete — severity=%s  paths=%d  labeled=%d/%d",
            session_severity, len(dangerous_paths), labeled_count, len(all_tools),
        )
        self._write_result(result)
        return result

    def _analyze_tool(self, tool_name: str, tool_data: dict) -> dict:
        tokens_data = tool_data.get("tokens", {})
        name_tokens: list[str] = tokens_data.get("name", [])
        desc_tokens: list[str] = tokens_data.get("description", [])
        param_tokens_map: dict[str, list[str]] = tokens_data.get("parameters", {})

        all_tokens: set[str] = set(name_tokens) | set(desc_tokens)
        for ptoks in param_tokens_map.values():
            all_tokens.update(ptoks)

        description = tool_data.get("description", "")
        description_lower = description.lower()
        parameters: dict[str, dict] = tool_data.get("parameters", {})

        # Compute semantic scores once for all labels
        sem_scores_dict = self._compute_semantic_scores(tool_name, description)

        suppressor_applied = False
        suppressor_kw: str | None = None
        compound_matched: str | None = None

        scores_per_label: dict[str, dict] = {}
        confidence_per_label: dict[str, dict] = {}
        evidence_per_label: dict[str, list] = {}
        assigned_labels: list[str] = []

        for label in _LABELS:
            threshold: int = getattr(self._config.thresholds, label.lower())

            kw_score, kw_evidence = self._keyword_score(
                tool_name, name_tokens, desc_tokens, param_tokens_map, description_lower, label
            )

            post_sup_score, sup_kw = self._apply_suppressor(kw_score, all_tokens, label)
            if sup_kw is not None:
                suppressor_applied = True
                suppressor_kw = sup_kw

            compound_bonus, comp_match = self._apply_compound(all_tokens, label)
            if comp_match is not None:
                compound_matched = comp_match

            param_score, param_evidence = _param_inference(parameters, label)

            total_score = post_sup_score + compound_bonus + param_score

            all_evidence: list[dict] = list(kw_evidence) + list(param_evidence)
            if comp_match is not None:
                all_evidence.append({
                    "type": "compound",
                    "source": "compound_keywords",
                    "match": comp_match,
                    "points": int(compound_bonus),
                })
            if sup_kw is not None:
                all_evidence.append({
                    "type": "suppressor",
                    "source": "compound_keywords",
                    "keyword": sup_kw,
                    "multiplier": self._config.suppressor_multiplier,
                })

            sem_score: float = sem_scores_dict.get(label, 0.0)

            source_count = _count_sources(all_evidence)
            has_compound = comp_match is not None
            has_suppressor = sup_kw is not None
            has_param_hit = param_score > 0

            conf, band, reason = self._compute_confidence(
                total_score, threshold, source_count,
                has_compound, sem_score, has_suppressor, has_param_hit,
            )

            scores_per_label[label] = {
                "keyword":         kw_score,
                "param_inference": param_score,
                "compound":        compound_bonus,
                "total":           total_score,
            }
            confidence_per_label[label] = {"score": conf, "band": band, "reason": reason}

            if total_score >= threshold:
                # Borderline semantic veto
                bw: int = getattr(self._config.semantic, "borderline_window", 1)
                is_borderline = total_score <= threshold + bw
                if (
                    is_borderline
                    and self._model is not None
                    and sem_score < self._config.semantic.contradict_threshold
                ):
                    confidence_per_label[label] = {
                        "score": 0.0,
                        "band": "VERY_LOW",
                        "reason": "borderline keyword not confirmed by semantic",
                    }
                else:
                    assigned_labels.append(label)
                    if all_evidence:
                        evidence_per_label[label] = all_evidence

        return {
            "labels":             assigned_labels,
            "scores":             scores_per_label,
            "semantic":           sem_scores_dict,
            "confidence":         confidence_per_label,
            "evidence":           evidence_per_label,
            "suppressor_applied": suppressor_applied,
            "suppressor_keyword": suppressor_kw,
            "compound_matched":   compound_matched,
        }

    def _keyword_score(
        self,
        tool_name: str,
        name_tokens: list[str],
        desc_tokens: list[str],
        param_tokens_map: dict[str, list[str]],
        description_lower: str,
        label: str,
    ) -> tuple[float, list[dict]]:
        score = 0.0
        evidence: list[dict] = []
        seen: set[str] = set()

        all_tokens: set[str] = set(name_tokens) | set(desc_tokens)
        for ptoks in param_tokens_map.values():
            all_tokens.update(ptoks)

        tool_name_lower = tool_name.lower()
        kw_dict = _KEYWORDS[label]

        # Primary — match full tool name (substring)
        for kw in kw_dict["primary"]:
            kw_l = kw.lower()
            if kw_l in seen:
                continue
            if kw_l in tool_name_lower:
                seen.add(kw_l)
                pts = _TIER_POINTS["primary"]
                score += pts
                evidence.append({"keyword": kw, "source": "tool_name", "tier": "primary", "points": pts})

        # Secondary — match individual tokens
        for kw in kw_dict["secondary"]:
            kw_l = kw.lower()
            if kw_l in seen:
                continue
            if kw_l in all_tokens:
                seen.add(kw_l)
                pts = _TIER_POINTS["secondary"]
                score += pts
                src = _find_token_source(kw_l, name_tokens, desc_tokens, param_tokens_map)
                evidence.append({"keyword": kw, "source": src, "tier": "secondary", "points": pts})

        # Contextual — match phrase in description
        for kw in kw_dict["contextual"]:
            kw_l = kw.lower()
            phrase = kw_l
            if kw_l in seen:
                continue
            if phrase in description_lower:
                seen.add(kw_l)
                pts = _TIER_POINTS["contextual"]
                score += pts
                evidence.append({"keyword": kw, "source": "description", "tier": "contextual", "points": pts})

        return score, evidence

    @staticmethod
    def _find_token_source(
        kw: str,
        name_tokens: list[str],
        desc_tokens: list[str],
        param_tokens_map: dict[str, list[str]],
    ) -> str:
        if kw in name_tokens:
            return "tool_name"
        if kw in desc_tokens:
            return "description"
        for param_name, ptoks in param_tokens_map.items():
            if kw in ptoks:
                return f"param:{param_name}"
        return "unknown"

    def _apply_suppressor(self, score: float, all_tokens: set[str], label: str) -> tuple[float, str | None]:
        for kw in _SUPPRESSORS[label]:
            if kw in all_tokens:
                return score * self._config.suppressor_multiplier, kw
        return score, None

    def _apply_compound(self, all_tokens: set[str], label: str) -> tuple[float, str | None]:
        for a, b in _COMPOUNDS[label]:
            if a in all_tokens and b in all_tokens:
                return float(self._config.compound_bonus), f"({a}, {b})"
        return 0.0, None

    def _compute_semantic_scores(self, tool_name: str, description: str) -> dict[str, float]:
        scores: dict[str, float] = {lbl: 0.0 for lbl in _LABELS}
        if self._model is None:
            return scores
        try:
            text = f"{tool_name} {description}"
            tool_emb = self._model.encode(text, convert_to_numpy=True)
            for label in _LABELS:
                anchor_embs = self._anchor_embeddings.get(label, [])
                if not anchor_embs:
                    continue
                sims = [
                    float(tool_emb @ ae / max(1e-9, float((tool_emb @ tool_emb) ** 0.5) * float((ae @ ae) ** 0.5)))
                    for ae in anchor_embs
                ]
                scores[label] = max(sims)
        except Exception as exc:
            logger.warning("Semantic scoring error for '%s': %s", tool_name, exc)
        return scores

    @staticmethod
    def _count_sources(evidence: list[dict]) -> int:
        sources: set[str] = set()
        for e in evidence:
            src = e.get("source", "unknown")
            if src.startswith("param:") or src == "parameter_inference":
                sources.add("parameter")
            else:
                sources.add(src)
        return len(sources)

    def _compute_confidence(
        self,
        total_score: float,
        threshold: int,
        source_count: int,
        has_compound: bool,
        sem_score: float,
        has_suppressor: bool,
        has_param_hit: bool,
    ) -> tuple[float, str, str]:
        base = min(total_score / max(1, threshold * 2), 1.0)
        diversity = {1: 0.0, 2: 0.10, 3: 0.20}.get(min(source_count, 3), 0.20)
        compound = 0.15 if has_compound else 0.0

        cfg = getattr(self._config, "semantic", None)
        confirm_t    = cfg.confirm_threshold    if cfg else 0.75
        support_t    = cfg.support_threshold    if cfg else 0.55
        contradict_t = cfg.contradict_threshold if cfg else 0.35

        if sem_score >= confirm_t:
            semantic = 0.15
        elif sem_score >= support_t:
            semantic = 0.05
        elif sem_score >= contradict_t:
            semantic = 0.0
        else:
            semantic = -0.20

        suppressor_pen = -0.25 if has_suppressor else 0.0
        param_bonus    =  0.10 if has_param_hit  else 0.0

        conf = base + diversity + compound + semantic + suppressor_pen + param_bonus
        conf = max(0.0, min(1.0, conf))

        band = "VERY_LOW"
        for min_val, bname in _CONFIDENCE_BANDS:
            if conf >= min_val:
                band = bname
                break

        parts: list[str] = []
        if base >= 0.5:
            parts.append("Strong keyword signal")
        elif base >= 0.25:
            parts.append("Moderate keyword signal")
        else:
            parts.append("Weak keyword signal")

        if has_compound:
            parts.append("compound match confirmed")
        if sem_score >= confirm_t:
            parts.append("semantic confirmed")
        elif sem_score < contradict_t:
            parts.append("semantic contradicts")
        if has_suppressor:
            parts.append("suppressor applied")
        if has_param_hit:
            parts.append("parameter inference hit")

        return conf, band, "; ".join(parts)

    @staticmethod
    def _compute_session_severity(label_groups: dict[str, list[str]]) -> str:
        has_u = bool(label_groups["U"])
        has_s = bool(label_groups["S"])
        has_e = bool(label_groups["E"])

        if has_u and has_s and has_e:
            return "CRITICAL"
        if has_s and has_e:
            return "HIGH"
        if (has_u and has_s) or (has_u and has_e):
            return "MEDIUM"
        if has_s or has_e:
            return "LOW"
        return "NONE"

    def _build_dangerous_paths(self, label_groups: dict[str, list[str]]) -> list[dict]:
        u_tools = label_groups["U"]
        s_tools = label_groups["S"]
        e_tools = label_groups["E"]
        paths: list[dict] = []
        pid = 0

        # CRITICAL — U + S + E
        for u, s, e in product(u_tools, s_tools, e_tools):
            pid += 1
            paths.append({
                "id":       f"path_{pid:03d}",
                "severity": "CRITICAL",
                "type":     "lethal_trifecta",
                "chain":    [u, s, e],
                "chain_labels": ["U", "S", "E"],
                "description": (
                    f"Complete exfiltration chain: {u} (untrusted input) → "
                    f"{s} (sensitive access) → {e} (external output)"
                ),
                "recommendation": _RECOMMENDATION_TEMPLATES["lethal_trifecta"].format(u=u, s=s, e=e),
                "also_member_of_critical": None,
            })

        # HIGH — S + E
        for s, e in product(s_tools, e_tools):
            pid += 1
            member_of = [p["id"] for p in paths if p["severity"] == "CRITICAL" and s in p["chain"] and e in p["chain"]]
            paths.append({
                "id":       f"path_{pid:03d}",
                "severity": "HIGH",
                "type":     "sensitive_external",
                "chain":    [s, e],
                "chain_labels": ["S", "E"],
                "description": f"Sensitive access via {s} can be transmitted by {e}",
                "recommendation": _RECOMMENDATION_TEMPLATES["sensitive_external"].format(s=s, e=e),
                "also_member_of_critical": member_of or None,
            })

        # MEDIUM — U + S
        for u, s in product(u_tools, s_tools):
            pid += 1
            member_of = [p["id"] for p in paths if p["severity"] == "CRITICAL" and u in p["chain"] and s in p["chain"]]
            paths.append({
                "id":       f"path_{pid:03d}",
                "severity": "MEDIUM",
                "type":     "untrusted_sensitive",
                "chain":    [u, s],
                "chain_labels": ["U", "S"],
                "description": f"Untrusted input from {u} can reach sensitive access {s}",
                "recommendation": _RECOMMENDATION_TEMPLATES["untrusted_sensitive"].format(u=u, s=s),
                "also_member_of_critical": member_of or None,
            })

        # MEDIUM — U + E
        for u, e in product(u_tools, e_tools):
            pid += 1
            member_of = [p["id"] for p in paths if p["severity"] == "CRITICAL" and u in p["chain"] and e in p["chain"]]
            paths.append({
                "id":       f"path_{pid:03d}",
                "severity": "MEDIUM",
                "type":     "untrusted_external",
                "chain":    [u, e],
                "chain_labels": ["U", "E"],
                "description": f"{u} can be forwarded externally via {e}",
                "recommendation": _RECOMMENDATION_TEMPLATES["untrusted_external"].format(u=u, e=e),
                "also_member_of_critical": member_of or None,
            })

        return paths

    def _build_single_tool_risks(self, label_groups: dict[str, list[str]]) -> list[dict]:
        risks: list[dict] = []
        has_s = bool(label_groups["S"])
        has_e = bool(label_groups["E"])

        if not has_e:
            for tool in label_groups["S"]:
                risks.append({
                    "tool":     tool,
                    "label":    "S",
                    "severity": "LOW",
                    "reason":   "Sensitive access without external output — risk escalates if E tool added",
                    "warning":  "Adding any E-labeled tool will escalate session severity to HIGH",
                })

        if not has_s:
            for tool in label_groups["E"]:
                risks.append({
                    "tool":     tool,
                    "label":    "E",
                    "severity": "LOW",
                    "reason":   "External output without sensitive access — risk escalates if S tool added",
                    "warning":  "Adding any S-labeled tool will escalate session severity to HIGH",
                })

        return risks

    def _write_result(self, result: dict) -> None:
        path = os.path.join(_PACKAGE_ROOT, "..", "storage", "results", os.path.basename(self._result_path))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            json.dump(result, f, indent=2)
        logger.info("Toxic flow result written to %s", path)


# ---------------------------------------------------------------------------
# ToxicFlowLoader
# ---------------------------------------------------------------------------

class ToxicFlowLoader:
    """
    Loads toxic_flow_result.json and exposes read accessors for downstream
    consumers (Chain Tracker / Runtime Monitor / Anomaly Detection).
    """

    def __init__(self, result_path: str) -> None:
        self._result_path = result_path
        self._data: dict | None = None

    def load(self) -> dict | None:
        path = os.path.join(_PACKAGE_ROOT, "..", "storage", "results", os.path.basename(self._result_path))
        try:
            with open(path) as f:
                self._data = json.load(f)
        except FileNotFoundError:
            logger.warning("ToxicFlowLoader: result file not found at %s", path)
            self._data = None
        except Exception as exc:
            logger.warning("ToxicFlowLoader: JSON parse error: %s", exc)
            self._data = None
        return self._data

    def get_dangerous_chains(self) -> list[list[str]]:
        """Return all dangerous path chains — for Chain Tracker subsequence matching."""
        if self._data is None:
            return []
        return [p["chain"] for p in self._data.get("dangerous_paths", [])]

    def get_labels(self, tool_name: str) -> list[str]:
        """Return U/S/E labels assigned to tool_name."""
        if self._data is None:
            return []
        return self._data.get("tools", {}).get(tool_name, {}).get("labels", [])

    def get_severity_multiplier(self, tool_name: str) -> float:
        """
        Severity multiplier for Anomaly Detection:
          CRITICAL path member  → 2.0
          Dual-labeled tool     → 1.5
          Single-labeled tool   → 1.0
          Unlabeled tool        → 0.5
        """
        if self._data is None:
            return 1.0

        for path in self._data.get("dangerous_paths", []):
            if path["severity"] == "CRITICAL" and tool_name in path["chain"]:
                return 2.0

        labels = self.get_labels(tool_name)
        if len(labels) >= 2:
            return 1.5
        if len(labels) == 1:
            return 1.0
        return 0.5


# ---------------------------------------------------------------------------
# Module-level helper (used by _analyze_tool — defined outside class for
# staticmethod-like access without self)
# ---------------------------------------------------------------------------

def _find_token_source(
    kw: str,
    name_tokens: list[str],
    desc_tokens: list[str],
    param_tokens_map: dict[str, list[str]],
) -> str:
    if kw in name_tokens:
        return "tool_name"
    if kw in desc_tokens:
        return "description"
    for param_name, ptoks in param_tokens_map.items():
        if kw in ptoks:
            return f"param:{param_name}"
    return "unknown"


def _param_inference(parameters: dict[str, dict], label: str) -> tuple[float, list[dict]]:
    score = 0.0
    evidence: list[dict] = []
    patterns = _PARAM_PATTERNS[label]
    for param_name in parameters:
        pn_lower = param_name.lower()
        for pattern, pts in patterns:
            if pattern in pn_lower:
                score += pts
                evidence.append({
                    "param":   param_name,
                    "source":  "parameter_inference",
                    "pattern": pattern,
                    "points":  pts,
                })
                break
    return score, evidence


def _count_sources(evidence: list[dict]) -> int:
    sources: set[str] = set()
    for e in evidence:
        src = e.get("source", "unknown")
        if src.startswith("param:") or src == "parameter_inference":
            sources.add("parameter")
        else:
            sources.add(src)
    return len(sources)
