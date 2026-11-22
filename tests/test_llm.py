from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from src.config import Settings
from src.db import Database
from src.llm import LLMGateway


class LLMGatewayTests(unittest.TestCase):
    def test_peak_cost_estimate(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                database_path=Path(folder) / "db.sqlite",
                admin_password="x",
                deepseek_api_key="",
                hf_token="",
                default_provider="deepseek",
                default_model="deepseek-flash",
                app_env="test",
            )
            gateway = LLMGateway(settings, Database(settings.database_path))
            self.assertEqual(gateway._estimate_deepseek_cost("deepseek-flash", 1_000_000, 1_000_000), 1.5)

    def test_missing_deepseek_key_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                database_path=Path(folder) / "db.sqlite",
                admin_password="x",
                deepseek_api_key="",
                hf_token="",
                default_provider="deepseek",
                default_model="deepseek-flash",
                app_env="test",
            )
            gateway = LLMGateway(settings, Database(settings.database_path))
            with self.assertRaisesRegex(RuntimeError, "DEEPSEEK_API_KEY"):
                gateway._deepseek([], "deepseek-flash", 10, 0, False)

    def test_missing_huggingface_token_is_explicit(self):
        with tempfile.TemporaryDirectory() as folder:
            settings = Settings(
                database_path=Path(folder) / "db.sqlite",
                admin_password="x",
                deepseek_api_key="",
                hf_token="",
                default_provider="huggingface",
                default_model="Qwen/Qwen3.5-9B",
                app_env="test",
            )
            gateway = LLMGateway(settings, Database(settings.database_path))
            with self.assertRaisesRegex(RuntimeError, "HF_TOKEN"):
                gateway._huggingface([], "Qwen/Qwen3.5-9B", 10, 0, False)


if __name__ == "__main__":
    unittest.main()

