from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.catalog import activity_defaults
from src.db import Database
from src.personas import generate_personas
from src.scenario import parse_rule_based
from src.simulator import compare_results, simulate


class PersonaTests(unittest.TestCase):
    def test_panel_is_deterministic_and_diverse(self):
        first = generate_personas("project-a")
        second = generate_personas("project-a")
        self.assertEqual(first, second)
        self.assertEqual(len(first), 100)
        self.assertGreater(len({persona.archetype for persona in first}), 3)
        self.assertAlmostEqual(sum(persona.weight for persona in first), 1.0, places=6)

    def test_panel_changes_with_business_context(self):
        cafe = generate_personas("same-project", context={"activity_key": "cafe"})
        service = generate_personas("same-project", context={"activity_key": "service"})
        self.assertNotEqual([p.archetype for p in cafe], [p.archetype for p in service])
        self.assertIn("طالب/عامل متنقل", {p.market_role for p in cafe})
        self.assertIn("عميل لأول مرة", {p.market_role for p in service})

    def test_targeted_womens_business_keeps_relevant_majority(self):
        panel = generate_personas(
            "women-retail", count=128,
            context={"activity_key": "retail", "target_customer": "نساء 22–45 سنة"},
        )
        self.assertGreaterEqual(sum(p.gender == "أنثى" for p in panel), 100)

    def test_custom_fitness_business_has_relevant_panel(self):
        panel = generate_personas(
            "women-gym", count=128,
            context={"activity_key": "other", "custom_activity": "نادي رياضي", "target_customer": "نساء"},
        )
        self.assertTrue(all(p.gender == "أنثى" for p in panel))
        self.assertIn("مقارن اشتراكات", {p.market_role for p in panel})
        self.assertFalse(any("المنتج" in p.initial_objection or "الصورة" in p.initial_objection for p in panel))


class SimulationTests(unittest.TestCase):
    def setUp(self):
        self.config = activity_defaults("متجر إلكتروني")
        self.config.update(activity_key="ecommerce", wilayas=["الجزائر", "وهران"], scenario_name="Baseline")

    def test_simulation_has_financial_outputs(self):
        result = simulate(self.config, "p1")
        self.assertGreater(result["sample_size"], 100)
        self.assertGreaterEqual(result["purchase_intent_pct"], 0)
        self.assertLessEqual(result["purchase_intent_pct"], 100)
        self.assertIn("monthly_profit_dzd", result)
        self.assertIn("top_objections", result)
        self.assertEqual(len(result["personas"]), result["sample_size"])

    def test_custom_activity_can_run_with_generic_assumptions(self):
        config = activity_defaults("مشروع آخر")
        config.update(activity_key="other", custom_activity="نادي رياضي", target_customer="شباب")
        result = simulate(config, "custom-activity")
        self.assertEqual(result["sample_size"], 128)
        self.assertGreater(result["expected_monthly_orders"], 0)
        from src.live_market import _environment
        env = _environment("other", config, result)
        self.assertEqual(env["visual_activity"], "fitness")
        self.assertEqual(env["kind"], "physical")
        self.assertTrue(all(key in env["locations"] for key in env["route"]))

    def test_subscription_price_phrase_works_without_llm(self):
        config = activity_defaults("مشروع آخر")
        config.update(activity_key="other", custom_activity="نادي رياضي", price=4500)
        changed, changes = parse_rule_based("ارفع سعر الاشتراك 10%", config)
        self.assertEqual(changed["price"], 4950)
        self.assertTrue(changes)

    def test_every_buyer_studies_the_project_with_a_traceable_reason(self):
        config = dict(self.config)
        config.update(
            description="متجر ملابس شبابية أونلاين بصور حقيقية واسترجاع واضح وتوصيل للولايات.",
            target_customer="طلبة وشباب بين 18 و30 سنة",
            offer_notes="مقاسات مفصلة وتبديل خلال 48 ساعة",
            products=[
                {"name": "T-shirt Basic", "category": "ملابس", "price_dzd": 2200, "cost_dzd": 900},
                {"name": "Hoodie Premium", "category": "ملابس", "price_dzd": 6200, "cost_dzd": 2900},
                {"name": "Cap", "category": "إكسسوار", "price_dzd": 1600, "cost_dzd": 550},
            ],
            price=3333,
        )
        result = simulate(config, "deep-study")
        offers = {p["selected_offer"]["name"] for p in result["personas"]}
        self.assertGreater(len(offers), 1)
        for buyer in result["personas"]:
            self.assertTrue(buyer["decision_reason"])
            self.assertTrue(buyer["would_change_my_mind"])
            self.assertEqual(len(buyer["evaluated_factors"]), 7)
            self.assertLess(buyer["price_answers"]["bargain"], buyer["price_answers"]["too_expensive"])
        self.assertEqual(len(result["study_dimensions"]), 7)
        self.assertTrue(result["panel_blueprint"]["same_panel_across_scenarios"])

    def test_scenarios_keep_identity_but_change_individual_reactions(self):
        baseline = simulate(self.config, "stable-actors")
        scenario = dict(self.config)
        scenario.update(price=self.config["price"] * 1.25, trust_score=85)
        changed = simulate(scenario, "stable-actors")
        self.assertEqual(
            [(p["name"], p["buying_habit"], p["initial_objection"]) for p in baseline["personas"]],
            [(p["name"], p["buying_habit"], p["initial_objection"]) for p in changed["personas"]],
        )
        deltas = {round(b["probability"] - a["probability"], 3) for a, b in zip(baseline["personas"], changed["personas"])}
        self.assertGreater(len(deltas), 4)

    def test_price_increase_reduces_intent_for_same_panel(self):
        baseline = simulate(self.config, "p1")
        scenario = dict(self.config)
        scenario["price"] *= 1.2
        scenario["scenario_name"] = "price +20"
        changed = simulate(scenario, "p1")
        comparison = compare_results(baseline, changed)
        self.assertLess(comparison["purchase_intent_pct"]["delta"], 0)

    def test_catalog_price_scenario_keeps_same_offer_and_exposes_tradeoff(self):
        from src.live_market import demo_project_and_run, run_demo_scenario

        _, baseline, _ = demo_project_and_run("demo-street")
        _, scenario, _, comparison = run_demo_scenario("demo-street", "ارفع السعر 10% وقارن الأثر")
        before = baseline["result_json"]["personas"]
        after = scenario["result_json"]["personas"]
        catalog_prices = {p["name"]: p["price_dzd"] for p in baseline["config_json"]["products"]}
        for original, repriced in zip(before, after):
            self.assertAlmostEqual(original["selected_offer"]["price"], catalog_prices[original["selected_offer"]["name"]])
            self.assertAlmostEqual(repriced["selected_offer"]["price"], original["selected_offer"]["price"] * 1.1)
        self.assertEqual(
            [p["selected_offer"]["name"] for p in before],
            [p["selected_offer"]["name"] for p in after],
        )
        self.assertLess(comparison["purchase_intent_pct"]["delta"], 0)
        self.assertLess(comparison["expected_monthly_orders"]["delta"], 0)

    def test_same_panel_and_config_are_fully_reproducible(self):
        self.assertEqual(simulate(self.config, "p1"), simulate(self.config, "p1"))

    def test_price_plus_free_delivery_uses_total_customer_outlay(self):
        baseline = simulate(self.config, "p1")
        scenario = dict(self.config)
        scenario.update(price=self.config["price"] * 1.2, delivery_price=0, free_delivery=True)
        changed = simulate(scenario, "p1")
        self.assertLess(changed["purchase_intent_pct"], baseline["purchase_intent_pct"])

    def test_activity_specific_scenarios_move_relevant_signals(self):
        cases = [
            ("متجر ملابس محلي", "retail", {"fitting_rooms": False, "clear_prices": False}, {"fitting_rooms": True, "clear_prices": True}),
            ("كافيه", "cafe", {"wifi": False, "parking": False}, {"wifi": True, "parking": True}),
            ("مطعم / Fast Food", "restaurant", {"waiting_minutes": 40, "delivery": False}, {"waiting_minutes": 10, "delivery": True}),
            ("خدمات / Freelance", "service", {"response_minutes": 180, "online_booking": False}, {"response_minutes": 15, "online_booking": True}),
        ]
        for label, activity, weak, improved in cases:
            with self.subTest(activity=activity):
                config = activity_defaults(label)
                config.update(activity_key=activity, wilayas=["الجزائر"], **weak)
                better = dict(config)
                better.update(improved)
                self.assertGreater(
                    simulate(better, f"case-{activity}")["purchase_intent_pct"],
                    simulate(config, f"case-{activity}")["purchase_intent_pct"],
                )


class ScenarioTests(unittest.TestCase):
    def test_quick_brief_keeps_custom_activity_and_payment(self):
        from app import BriefInput, parse_brief
        parsed = parse_brief(BriefInput(text=(
            "نادي رياضي للنساء في قسنطينة. نقدم اشتراكاً شهرياً بسعر 4500 دج. "
            "الجمهور نساء من 20 إلى 45 سنة وندعم الدفع وبريدي موب."
        )))
        self.assertEqual(parsed["config"]["custom_activity"], "نادي رياضي")
        self.assertEqual(parsed["config"]["payment_methods"], ["بريدي موب"])
        self.assertIn("20–45", parsed["config"]["target_customer"])

    def test_darija_price_and_delivery_patch(self):
        current = {"price": 1000.0, "delivery_price": 400.0, "free_delivery": False}
        updated, changes = parse_rule_based("زيد السعر 20% وخلي التوصيل مجاني", current)
        self.assertEqual(updated["price"], 1200.0)
        self.assertTrue(updated["free_delivery"])
        self.assertEqual(updated["delivery_price"], 0.0)
        self.assertEqual(len(changes), 2)

    def test_domain_specific_darija_changes(self):
        current = {"fitting_rooms": False, "clear_prices": False, "response_minutes": 90}
        updated, changes = parse_rule_based("أضف غرف القياس ووضح الأسعار واضبط الرد على 10 دقائق", current)
        self.assertTrue(updated["fitting_rooms"])
        self.assertTrue(updated["clear_prices"])
        self.assertEqual(updated["response_minutes"], 10)
        self.assertEqual(len(changes), 3)


class DatabaseTests(unittest.TestCase):
    def test_user_project_run_and_stats(self):
        with tempfile.TemporaryDirectory() as folder:
            db = Database(Path(folder) / "test.db")
            user_id, _ = db.upsert_user("Test", "test@example.com")
            config = {"activity_key": "ecommerce", "price": 1000}
            project_id = db.save_project(user_id, "Shop", "متجر إلكتروني", config)
            run_id = db.save_run(project_id, "Baseline", config, {"purchase_intent_pct": 50}, "huggingface", "qwen")
            self.assertIsNotNone(db.get_run(run_id))
            stats = db.admin_stats()
            self.assertEqual(stats["users"], 1)
            self.assertEqual(stats["projects"], 1)
            self.assertEqual(stats["runs"], 1)


if __name__ == "__main__":
    unittest.main()

