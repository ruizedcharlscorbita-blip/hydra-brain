import unittest
import os
import sys
import json
import logging
from unittest.mock import patch

# Add current directory to path to ensure imports work correctly
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from core.registry import HeadRegistry
from core.router import Router
from core.health import HealthChecker
from core.hydra import HydraController
from core.state import StateManager

class TestHydraBrain(unittest.TestCase):
    def setUp(self):
        # Create temporary config and state files for testing
        self.temp_config_path = "temp_test_heads.json"
        self.temp_state_path = "temp_test_state.json"
        
        self.test_config = {
            "heads": [
                {
                    "id": "test-head-1",
                    "provider": "openrouter",
                    "model": "model-1",
                    "priority": 1,
                    "cooldown_seconds": 900
                },
                {
                    "id": "test-head-2",
                    "provider": "openrouter",
                    "model": "model-2",
                    "priority": 2,
                    "cooldown_seconds": 900
                }
            ]
        }
        with open(self.temp_config_path, "w", encoding="utf-8") as f:
            json.dump(self.test_config, f)
            
        # Clean state manager temp file if it exists
        if os.path.exists(self.temp_state_path):
            os.remove(self.temp_state_path)

    def tearDown(self):
        # Remove temporary files
        for path in (self.temp_config_path, self.temp_state_path):
            if os.path.exists(path):
                try:
                    os.remove(path)
                except Exception:
                    pass

    def test_registry_loading(self):
        registry = HeadRegistry(self.temp_config_path)
        heads = registry.get_all_heads()
        self.assertEqual(len(heads), 2)
        self.assertEqual(heads[0]["id"], "test-head-1")
        self.assertEqual(heads[1]["id"], "test-head-2")

    def test_config_validation(self):
        registry = HeadRegistry(self.temp_config_path)
        
        # Test invalid provider
        registry.heads[0]["provider"] = "invalid-provider"
        with self.assertRaises(ValueError):
            registry.validate_heads()
            
        # Test invalid priority
        registry.heads[0]["provider"] = "openrouter"
        registry.heads[0]["priority"] = 0
        with self.assertRaises(ValueError):
            registry.validate_heads()
            
        # Test duplicate IDs
        registry.heads[0]["priority"] = 1
        registry.heads[1]["id"] = "test-head-1"
        with self.assertRaises(ValueError):
            registry.validate_heads()

    def test_router_priority_selection(self):
        router = Router()
        heads = self.test_config["heads"]
        state_mgr = StateManager(self.temp_state_path)
        
        # Scenario 1: Both available, select head 1 (priority 1)
        status = {
            "test-head-1": {"status": "AVAILABLE", "http_status": 200},
            "test-head-2": {"status": "AVAILABLE", "http_status": 200}
        }
        selected = router.select_head(heads, status, state_mgr)
        self.assertEqual(selected["id"], "test-head-1")

        # Scenario 2: Head 1 is rate limited, select head 2 (priority 2)
        status = {
            "test-head-1": {"status": "RATE_LIMITED", "http_status": 429},
            "test-head-2": {"status": "AVAILABLE", "http_status": 200}
        }
        selected = router.select_head(heads, status, state_mgr)
        self.assertEqual(selected["id"], "test-head-2")

    def test_failure_persistence(self):
        state_mgr = StateManager(self.temp_state_path)
        diag = {
            "status": "RATE_LIMITED",
            "http_status": 429,
            "latency_ms": 150,
            "provider_code": "rate_limit_exceeded",
            "provider_message": "Too many requests"
        }
        state_mgr.record_failure("test-head-1", diag, cooldown_seconds=600)
        
        # Verify saved in original instance
        self.assertEqual(state_mgr.get_head_state("test-head-1")["failures"], 1)
        self.assertEqual(state_mgr.get_head_state("test-head-1")["status"], "RATE_LIMITED")
        self.assertEqual(state_mgr.get_head_state("test-head-1")["http_status"], 429)
        self.assertEqual(state_mgr.get_head_state("test-head-1")["provider_code"], "rate_limit_exceeded")
        self.assertEqual(state_mgr.get_head_state("test-head-1")["provider_message"], "Too many requests")
        
        # Reload new StateManager instance (simulating restart)
        restarted_state_mgr = StateManager(self.temp_state_path)
        self.assertEqual(restarted_state_mgr.get_head_state("test-head-1")["failures"], 1)
        self.assertEqual(restarted_state_mgr.get_head_state("test-head-1")["status"], "RATE_LIMITED")
        self.assertEqual(restarted_state_mgr.get_head_state("test-head-1")["http_status"], 429)

    def test_cooldown_ignores_head(self):
        state_mgr = StateManager(self.temp_state_path)
        
        # Mark test-head-1 in active cooldown
        state_mgr.record_failure("test-head-1", {"status": "RATE_LIMITED"}, cooldown_seconds=900)
        self.assertTrue(state_mgr.is_in_cooldown("test-head-1"))
        
        router = Router()
        health_status = {
            "test-head-1": {"status": "AVAILABLE", "http_status": 200},
            "test-head-2": {"status": "AVAILABLE", "http_status": 200}
        }
        heads = self.test_config["heads"]
        
        # Router must skip test-head-1 and choose test-head-2
        selected = router.select_head(heads, health_status, state_mgr)
        self.assertEqual(selected["id"], "test-head-2")

    def test_cooldown_recovery(self):
        state_mgr = StateManager(self.temp_state_path)
        
        # Mark test-head-1 in cooldown that expires immediately (0 seconds)
        state_mgr.record_failure("test-head-1", {"status": "RATE_LIMITED"}, cooldown_seconds=0)
        self.assertFalse(state_mgr.is_in_cooldown("test-head-1"))
        
        router = Router()
        health_status = {
            "test-head-1": {"status": "AVAILABLE", "http_status": 200},
            "test-head-2": {"status": "AVAILABLE", "http_status": 200}
        }
        heads = self.test_config["heads"]
        
        selected = router.select_head(heads, health_status, state_mgr)
        self.assertEqual(selected["id"], "test-head-1")

    @patch.dict(os.environ, {
        "HYDRA_MOCK": "true",
        "MOCK_STATUS_TEST_HEAD_1": "AVAILABLE",
        "MOCK_STATUS_TEST_HEAD_2": "AVAILABLE",
        "MOCK_HTTP_STATUS_TEST_HEAD_1": "200",
        "MOCK_LATENCY_MS_TEST_HEAD_1": "640"
    })
    def test_scenario_1_success(self):
        """Scenario 1: Success (HTTP 200, latency, selected, routing reason)"""
        controller = HydraController(self.temp_config_path, self.temp_state_path)
        response = controller.handle_request("Explain recursion")
        
        state_mgr = controller.state_manager
        head_state = state_mgr.get_head_state("test-head-1")
        
        # Assertions
        self.assertEqual(head_state["status"], "AVAILABLE")
        self.assertEqual(head_state["http_status"], 200)
        self.assertIsNotNone(head_state["latency_ms"])
        self.assertTrue(head_state["successes"] >= 1)

    @patch.dict(os.environ, {
        "HYDRA_MOCK": "true",
        "MOCK_STATUS_TEST_HEAD_1": "FAILED",
        "MOCK_HTTP_STATUS_TEST_HEAD_1": "401",
        "MOCK_PROVIDER_CODE_TEST_HEAD_1": "invalid_api_key",
        "MOCK_PROVIDER_MESSAGE_TEST_HEAD_1": "Invalid API key",
        "MOCK_STATUS_TEST_HEAD_2": "AVAILABLE"
    })
    def test_scenario_2_invalid_api_key(self):
        """Scenario 2: Invalid API Key (HTTP 401, provider error, fail classification, cooldown)"""
        controller = HydraController(self.temp_config_path, self.temp_state_path)
        controller.handle_request("some prompt")
        
        state_mgr = controller.state_manager
        head_1_state = state_mgr.get_head_state("test-head-1")
        
        # Assertions
        self.assertEqual(head_1_state["status"], "FAILED")
        self.assertEqual(head_1_state["http_status"], 401)
        self.assertEqual(head_1_state["provider_code"], "invalid_api_key")
        self.assertEqual(head_1_state["provider_message"], "Invalid API key")
        self.assertTrue(state_mgr.is_in_cooldown("test-head-1"))

    @patch.dict(os.environ, {
        "HYDRA_MOCK": "true",
        "MOCK_STATUS_TEST_HEAD_1": "RATE_LIMITED",
        "MOCK_HTTP_STATUS_TEST_HEAD_1": "429",
        "MOCK_PROVIDER_CODE_TEST_HEAD_1": "rate_limit_exceeded",
        "MOCK_STATUS_TEST_HEAD_2": "AVAILABLE"
    })
    def test_scenario_3_rate_limit(self):
        """Scenario 3: Rate Limit (HTTP 429, RATE_LIMITED, cooldown timer)"""
        controller = HydraController(self.temp_config_path, self.temp_state_path)
        controller.handle_request("some prompt")
        
        state_mgr = controller.state_manager
        head_1_state = state_mgr.get_head_state("test-head-1")
        
        # Assertions
        self.assertEqual(head_1_state["status"], "RATE_LIMITED")
        self.assertEqual(head_1_state["http_status"], 429)
        self.assertEqual(head_1_state["provider_code"], "rate_limit_exceeded")
        self.assertTrue(state_mgr.is_in_cooldown("test-head-1"))

    @patch.dict(os.environ, {
        "HYDRA_MOCK": "true",
        "MOCK_STATUS_TEST_HEAD_1": "UNAVAILABLE",
        "MOCK_HTTP_STATUS_TEST_HEAD_1": "404",
        "MOCK_PROVIDER_CODE_TEST_HEAD_1": "model_not_found",
        "MOCK_PROVIDER_MESSAGE_TEST_HEAD_1": "Model not found",
        "MOCK_STATUS_TEST_HEAD_2": "AVAILABLE"
    })
    def test_scenario_4_missing_model(self):
        """Scenario 4: Missing Model (HTTP 404, UNAVAILABLE, provider message)"""
        controller = HydraController(self.temp_config_path, self.temp_state_path)
        controller.handle_request("some prompt")
        
        state_mgr = controller.state_manager
        head_1_state = state_mgr.get_head_state("test-head-1")
        
        # Assertions
        self.assertEqual(head_1_state["status"], "UNAVAILABLE")
        self.assertEqual(head_1_state["http_status"], 404)
        self.assertEqual(head_1_state["provider_code"], "model_not_found")
        self.assertEqual(head_1_state["provider_message"], "Model not found")

    def test_scenario_5_log_inspection(self):
        """Scenario 5: Log Inspection (ensures hydra.log contains structured traces)"""
        # Set up a temporary logger handler to capture log content programmatically
        log_capture = []
        class CaptureHandler(logging.Handler):
            def emit(self, record):
                log_capture.append(self.format(record))
                
        logger = logging.getLogger("hydra")
        logger.setLevel(logging.DEBUG)
        handler = CaptureHandler()
        logger.addHandler(handler)
        
        try:
            with patch.dict(os.environ, {
                "HYDRA_MOCK": "true",
                "MOCK_STATUS_TEST_HEAD_1": "AVAILABLE",
                "MOCK_STATUS_TEST_HEAD_2": "AVAILABLE"
            }):
                controller = HydraController(self.temp_config_path, self.temp_state_path)
                controller.handle_request("Test log content")
                
            # Verify that the decision trace is in the logs
            joined_logs = "\n".join(log_capture)
            self.assertIn("========== HYDRA DECISION ==========", joined_logs)
            self.assertIn("Prompt", joined_logs)
            self.assertIn("Head: Test Head 1", joined_logs)
            self.assertIn("Status:", joined_logs)
            self.assertIn("Action:", joined_logs)
            self.assertIn("====================================", joined_logs)
        finally:
            logger.removeHandler(handler)

    def test_model_discovery_and_registry(self):
        """Test model discovery fetches free models and Registry Manager loads/saves them."""
        import registry.model_registry as model_reg
        old_path = model_reg.REGISTRY_PATH
        model_reg.REGISTRY_PATH = "temp_free_models.json"
        
        try:
            if os.path.exists("temp_free_models.json"):
                os.remove("temp_free_models.json")
                
            from providers.openrouter.discovery import OpenRouterDiscovery
            
            # 1. Test Discovery logic
            discovery = OpenRouterDiscovery()
            models = discovery.discover_models()
            self.assertEqual(len(models), 5)
            self.assertEqual(models[0]["provider"], "Tencent")
            self.assertEqual(models[0]["model_id"], "tencent/hy3:free")
            self.assertTrue(models[0]["free"])
            
            # 2. Test Registry Manager operations
            refreshed = model_reg.refresh_registry()
            self.assertEqual(len(refreshed), 5)
            self.assertTrue(os.path.exists("temp_free_models.json"))
            
            loaded = model_reg.load_registry()
            self.assertEqual(len(loaded), 5)
            
            found = model_reg.find_model("tencent/hy3:free")
            self.assertIsNotNone(found)
            self.assertEqual(found["provider"], "Tencent")
            self.assertEqual(found["display_name"], "Hy3")
            
            # 3. Test new public Registry API v1.0
            all_m = model_reg.get_all()
            self.assertEqual(len(all_m), 5)
            
            free_m = model_reg.get_free()
            self.assertEqual(len(free_m), 5)
            
            tencent_m = model_reg.get_provider("Tencent")
            self.assertEqual(len(tencent_m), 1)
            self.assertEqual(tencent_m[0]["model_id"], "tencent/hy3:free")
            
            # Find by hydra_id
            hydra_id = tencent_m[0]["hydra_id"]
            found_by_hydra = model_reg.get_model(hydra_id)
            self.assertIsNotNone(found_by_hydra)
            self.assertEqual(found_by_hydra["model_id"], "tencent/hy3:free")
            
            # Search
            search_m = model_reg.search("Flash")
            self.assertEqual(len(search_m), 1)
            self.assertEqual(search_m[0]["provider"], "Google")
        finally:
            # Clean up and restore path
            if os.path.exists("temp_free_models.json"):
                try:
                    os.remove("temp_free_models.json")
                except Exception:
                    pass
            model_reg.REGISTRY_PATH = old_path

    def test_inventory_sync_and_validation(self):
        """Test sync creates JSON inventory and validation checks schema and uniqueness."""
        import inventory.sync_openrouter as syncer
        import inventory.validate_inventory as val
        import shutil
        
        old_sync_dir = syncer.REGISTRY_DIR
        old_val_path = val.REGISTRY_PATH
        
        syncer.REGISTRY_DIR = "temp_test_registry"
        val.REGISTRY_PATH = "temp_test_registry/free_models.json"
        
        try:
            if os.path.exists("temp_test_registry"):
                shutil.rmtree("temp_test_registry", ignore_errors=True)
                
            # 1. Sync
            with patch.dict(os.environ, {"HYDRA_MOCK": "true", "MOCK_INVENTORY_VERSION": "1"}):
                syncer.run_sync()
                
            self.assertTrue(os.path.exists("temp_test_registry/free_models.json"))
            self.assertTrue(os.path.exists("temp_test_registry/inventory_metadata.json"))
            self.assertTrue(os.path.exists("temp_test_registry/free_models.csv"))
            self.assertTrue(os.path.exists("temp_test_registry/free_models_grouped.json"))
            self.assertTrue(os.path.exists("temp_test_registry/openrouter_models_raw.json"))
            self.assertTrue(os.path.exists("reports/Inventory_Report.md"))
            
            with open("temp_test_registry/inventory_metadata.json", "r", encoding="utf-8") as f:
                meta = json.load(f)
                self.assertEqual(meta["free_models"], 4)
                
            # 2. Validation (Valid Case)
            with self.assertRaises(SystemExit) as cm:
                val.run_validation()
            self.assertEqual(cm.exception.code, 0)
            
            # 3. Validation (Duplicate Case)
            with open("temp_test_registry/free_models.json", "r", encoding="utf-8") as f:
                envelope = json.load(f)
            # Duplicate the first model entry inside envelope
            envelope["models"].append(envelope["models"][0].copy())
            with open("temp_test_registry/free_models.json", "w", encoding="utf-8") as f:
                json.dump(envelope, f)
                
            with self.assertRaises(SystemExit) as cm:
                val.run_validation()
            self.assertEqual(cm.exception.code, 1)
            
        finally:
            syncer.REGISTRY_DIR = old_sync_dir
            val.REGISTRY_PATH = old_val_path
            if os.path.exists("temp_test_registry"):
                shutil.rmtree("temp_test_registry", ignore_errors=True)
            if os.path.exists("reports/Inventory_Report.md"):
                try:
                    os.remove("reports/Inventory_Report.md")
                except Exception:
                    pass
            if os.path.exists("reports/Diff_Report.md"):
                try:
                    os.remove("reports/Diff_Report.md")
                except Exception:
                    pass

    def test_inventory_comparison(self):
        """Test compare_inventory detects added, removed, and updated fields (e.g. context changes)."""
        import inventory.sync_openrouter as syncer
        import inventory.compare_inventory as comparer
        import io
        import shutil
        
        old_sync_dir = syncer.REGISTRY_DIR
        old_comp_dir = comparer.REGISTRY_PATH
        
        syncer.REGISTRY_DIR = "temp_test_registry"
        comparer.REGISTRY_PATH = "temp_test_registry/free_models.json"
        
        try:
            if os.path.exists("temp_test_registry"):
                shutil.rmtree("temp_test_registry", ignore_errors=True)
                
            # Sync Version 1 first
            with patch.dict(os.environ, {"HYDRA_MOCK": "true", "MOCK_INVENTORY_VERSION": "1"}):
                syncer.run_sync()
                
            # Capture compare output against Version 2
            captured = io.StringIO()
            sys.stdout = captured
            try:
                with patch.dict(os.environ, {"HYDRA_MOCK": "true", "MOCK_INVENTORY_VERSION": "2"}):
                    comparer.compare_inventories()
            finally:
                sys.stdout = sys.__stdout__
                
            output = captured.getvalue()
            
            # Assertions
            self.assertIn("Added", output)
            self.assertIn("Tencent Hy3", output)
            self.assertIn("Poolside Laguna XS", output)
            
            self.assertIn("Removed", output)
            self.assertIn("Deepseek DeepSeek Lite", output)
            
            self.assertIn("Updated", output)
            self.assertIn("Google Gemini Flash", output)
            self.assertIn("Context:", output)
            self.assertIn("128K → 256K", output)
            
        finally:
            syncer.REGISTRY_DIR = old_sync_dir
            comparer.REGISTRY_PATH = old_comp_dir
            if os.path.exists("temp_test_registry"):
                shutil.rmtree("temp_test_registry", ignore_errors=True)
            if os.path.exists("reports/Inventory_Report.md"):
                try:
                    os.remove("reports/Inventory_Report.md")
                except Exception:
                    pass
            if os.path.exists("reports/Diff_Report.md"):
                try:
                    os.remove("reports/Diff_Report.md")
                except Exception:
                    pass

if __name__ == "__main__":
    unittest.main()
