from __future__ import annotations

from copy import deepcopy
from typing import Any

from .catalog import activity_defaults, activity_key
from .db import Database
from .llm import LLMGateway
from .scenario import apply_structured_patch, parse_rule_based
from .simulator import MODEL_VERSION, compare_results, simulate


class FinTwinService:
    def __init__(self, database: Database, llm: LLMGateway):
        self.database = database
        self.llm = llm

    def model_config(self) -> tuple[str, str]:
        provider = self.database.get_setting("llm_provider", self.llm.settings.default_provider)
        model = self.database.get_setting("llm_model", self.llm.settings.default_model)
        return provider, model

    def create_and_run(
        self,
        user_id: str,
        project_name: str,
        activity_label: str,
        overrides: dict[str, Any],
    ) -> tuple[str, str, dict[str, Any], dict[str, Any]]:
        config = activity_defaults(activity_label)
        config.update({key: value for key, value in overrides.items() if value is not None})
        config["activity_key"] = activity_key(activity_label)
        config["activity_label"] = activity_label
        config["scenario_name"] = "Baseline"
        config["catalog_reference_price"] = config.get("price")
        project_id = self.database.save_project(user_id, project_name, activity_label, config)
        result = simulate(config, project_id)
        provider, model = self.model_config()
        run_id = self.database.save_run(project_id, "Baseline", config, result, provider, model)
        return project_id, run_id, config, result

    def run_what_if(
        self,
        project_id: str,
        baseline_run_id: str,
        message: str,
        use_llm_parser: bool = True,
    ) -> tuple[str, dict[str, Any], dict[str, Any], dict[str, Any], list[str], str]:
        baseline_run = self.database.get_run(baseline_run_id) or self.database.latest_run(project_id)
        if not baseline_run:
            raise ValueError("ما لقيناش baseline لهذا المشروع.")
        baseline_config = deepcopy(baseline_run["config_json"])
        baseline_config.setdefault("catalog_reference_price", baseline_config.get("price"))
        baseline_result = baseline_run["result_json"]
        provider, model = self.model_config()
        if baseline_result.get("model_version") != MODEL_VERSION:
            baseline_result = simulate(baseline_config, project_id)
            refreshed_id = self.database.save_run(
                project_id, "Baseline · updated model", baseline_config, baseline_result, provider, model,
                parent_run_id=baseline_run["id"],
            )
            baseline_run = self.database.get_run(refreshed_id)
        scenario_config, changes = parse_rule_based(message, baseline_config)
        provider_ready = self.llm.settings.deepseek_configured if provider == "deepseek" else self.llm.settings.huggingface_configured
        if not changes and use_llm_parser and provider_ready:
            patch = self.llm.parse_scenario(message, baseline_config, provider, model)
            scenario_config, changes = apply_structured_patch(baseline_config, patch)
        if not changes:
            raise ValueError("ما فهمتش التغيير. مثال: زيد السعر 20% أو دير التوصيل مجاني.")
        scenario_name = message.strip()[:80]
        scenario_config["scenario_name"] = scenario_name
        scenario_result = simulate(scenario_config, project_id)
        comparison = compare_results(baseline_result, scenario_result)
        run_id = self.database.save_run(
            project_id,
            scenario_name,
            scenario_config,
            scenario_result,
            provider,
            model,
            parent_run_id=baseline_run["id"],
        )
        try:
            explanation = self.llm.explain_comparison(
                message, changes, baseline_result, scenario_result, comparison, provider, model, run_id
            )
        except Exception:
            profit_delta = comparison["monthly_profit_dzd"]["delta"]
            intent_delta = comparison["purchase_intent_pct"]["delta"]
            direction = "زاد" if profit_delta >= 0 else "نقص"
            explanation = (
                f"طبقنا: {', '.join(changes)}. نية الشراء تبدلت بـ{intent_delta:+.1f} نقطة، "
                f"والربح الشهري المتوقع {direction} بـ{abs(profit_delta):,.0f} دج. "
                "هذه نتيجة محاكاة؛ جرّب القرار على عينة صغيرة من زبائن حقيقيين قبل تعميمه."
            )
        return run_id, scenario_config, scenario_result, comparison, changes, explanation

