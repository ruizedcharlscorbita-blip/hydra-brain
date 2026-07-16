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
            # Patch sys.argv to prevent test runner flags (-v etc.) from leaking into
            # compare_inventories() and triggering its argv-length guard / sys.exit(1).
            captured = io.StringIO()
            sys.stdout = captured
            try:
                with patch.dict(os.environ, {"HYDRA_MOCK": "true", "MOCK_INVENTORY_VERSION": "2"}):
                    with patch.object(sys, "argv", ["compare_inventory.py"]):
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

    # =========================================================================
    # Sprint 2: Capability Scanner Tests
    # =========================================================================

    def test_capability_scanner_known_model(self):
        """Scanner assigns high-confidence scores to a model with an exact profile match."""
        from inventory.capability_scanner import scan_model

        # google/gemma-4-31b-it:free is in model_profiles.json > models
        model = {
            "model_id": "google/gemma-4-31b-it:free",
            "id": "google/gemma-4-31b-it:free",
            "modalities": ["text+image+video->text"],
            "supported_parameters": ["tools", "response_format"],
            "description": "Google Gemma 4 31B instruction-tuned model.",
            "context_length": 131072,
            "capabilities": {k: 0 for k in [
                "coding", "reasoning", "writing", "analysis",
                "vision", "chat", "tool_calling", "json_output", "streaming"
            ]}
        }
        result = scan_model(model)

        # Must have high confidence from exact profile match
        self.assertEqual(result["capability_confidence"], "high")

        # Known profile scores for gemma-4-31b-it:free
        self.assertGreater(result["capabilities"]["vision"], 0)
        self.assertGreater(result["capabilities"]["coding"], 0)
        self.assertGreater(result["capabilities"]["tool_calling"], 0)
        self.assertGreater(result["capabilities"]["streaming"], 0)

        # Scores must be integers in range 0-5
        for key, val in result["capabilities"].items():
            self.assertIsInstance(val, int)
            self.assertGreaterEqual(val, 0)
            self.assertLessEqual(val, 5)

    def test_capability_scanner_inference_fallback(self):
        """Scanner infers non-zero scores from metadata signals for an unknown model."""
        from inventory.capability_scanner import scan_model

        model = {
            "model_id": "unknown/totally-new-model-xyz:free",
            "id": "unknown/totally-new-model-xyz:free",
            "modalities": ["text+image->text"],
            "supported_parameters": ["response_format", "structured_outputs", "tools", "tool_choice"],
            "description": "An unknown instruct model that supports code generation.",
            "context_length": 128000,
            "capabilities": {k: 0 for k in [
                "coding", "reasoning", "writing", "analysis",
                "vision", "chat", "tool_calling", "json_output", "streaming"
            ]}
        }
        result = scan_model(model)

        # Should fall through to signal inference (low confidence)
        self.assertEqual(result["capability_confidence"], "low")

        # Signal: modalities contains "image" -> vision > 0
        self.assertGreater(result["capabilities"]["vision"], 0)

        # Signal: response_format / structured_outputs -> json_output > 0
        self.assertGreater(result["capabilities"]["json_output"], 0)

        # Signal: tools / tool_choice -> tool_calling > 0
        self.assertGreater(result["capabilities"]["tool_calling"], 0)

        # Signal: description has "code" -> coding > 0
        self.assertGreater(result["capabilities"]["coding"], 0)

        # Scores must be integers in range 0-5
        for key, val in result["capabilities"].items():
            self.assertIsInstance(val, int)
            self.assertGreaterEqual(val, 0)
            self.assertLessEqual(val, 5)

    def test_capability_scanner_full_registry(self):
        """scan_all() ensures no model has all-zero capabilities and all have confidence field."""
        from inventory.capability_scanner import scan_all

        # Build a representative set from the mock inventory models
        mock_models = [
            {
                "model_id": "google/gemma-4-31b-it:free",
                "id": "google/gemma-4-31b-it:free",
                "modalities": ["text+image+video->text"],
                "supported_parameters": ["tools", "response_format", "structured_outputs"],
                "description": "Google Gemma 4.",
                "context_length": 131072,
                "capabilities": {k: 0 for k in [
                    "coding", "reasoning", "writing", "analysis",
                    "vision", "chat", "tool_calling", "json_output", "streaming"
                ]}
            },
            {
                "model_id": "qwen/qwen3-coder:free",
                "id": "qwen/qwen3-coder:free",
                "modalities": ["text->text"],
                "supported_parameters": ["tools", "tool_choice", "temperature"],
                "description": "Qwen3 Coder specialized model.",
                "context_length": 32768,
                "capabilities": {k: 0 for k in [
                    "coding", "reasoning", "writing", "analysis",
                    "vision", "chat", "tool_calling", "json_output", "streaming"
                ]}
            },
            {
                "model_id": "meta-llama/llama-3.3-70b-instruct:free",
                "id": "meta-llama/llama-3.3-70b-instruct:free",
                "modalities": ["text->text"],
                "supported_parameters": ["tools", "tool_choice", "temperature"],
                "description": "Llama 3.3 70B instruct.",
                "context_length": 131072,
                "capabilities": {k: 0 for k in [
                    "coding", "reasoning", "writing", "analysis",
                    "vision", "chat", "tool_calling", "json_output", "streaming"
                ]}
            }
        ]

        results = scan_all(mock_models)

        # All models must have the capability_confidence field
        for m in results:
            self.assertIn("capability_confidence", m)
            self.assertIn(m["capability_confidence"], ("high", "medium", "low", "none"))

        # All known models must have at least one non-zero capability
        for m in results:
            non_zero = [v for v in m["capabilities"].values() if v > 0]
            self.assertGreater(len(non_zero), 0,
                msg=f"Model {m.get('model_id')} has all-zero capabilities after scanning")

    def test_sync_populates_capabilities(self):
        """After sync, at least one known model has non-zero capability scores."""
        import inventory.sync_openrouter as syncer
        import shutil

        old_sync_dir = syncer.REGISTRY_DIR
        syncer.REGISTRY_DIR = "temp_test_caps_registry"

        try:
            if os.path.exists("temp_test_caps_registry"):
                shutil.rmtree("temp_test_caps_registry", ignore_errors=True)

            with patch.dict(os.environ, {"HYDRA_MOCK": "true", "MOCK_INVENTORY_VERSION": "2"}):
                syncer.run_sync()

            # Load the written registry
            with open("temp_test_caps_registry/free_models.json", "r", encoding="utf-8") as f:
                data = json.load(f)

            models = data["models"] if isinstance(data, dict) else data

            # At least one model must have a non-zero capability score
            scored = [
                m for m in models
                if any(v > 0 for v in m.get("capabilities", {}).values())
            ]
            self.assertGreater(len(scored), 0,
                msg="No models have non-zero capability scores after sync")

            # All models must carry the capability_confidence field
            for m in models:
                self.assertIn("capability_confidence", m,
                    msg=f"Model {m.get('model_id')} is missing capability_confidence")

            # The known Qwen3 coder model should have a high coding score
            qwen_coder = next(
                (m for m in models if m.get("model_id") == "qwen/qwen3-coder:free"), None
            )
            if qwen_coder:
                self.assertGreater(qwen_coder["capabilities"].get("coding", 0), 3,
                    msg="qwen/qwen3-coder:free should have a coding score > 3")

        finally:
            syncer.REGISTRY_DIR = old_sync_dir
            if os.path.exists("temp_test_caps_registry"):
                shutil.rmtree("temp_test_caps_registry", ignore_errors=True)
            for report in ("reports/Inventory_Report.md", "reports/Diff_Report.md"):
                if os.path.exists(report):
                    try:
                        os.remove(report)
                    except Exception:
                        pass


    # =========================================================================
    # Sprint 3: Capability-Aware Routing Tests
    # =========================================================================

    def test_intent_parser_coding(self):
        """Intent parser identifies coding prompts with coding as the dominant capability."""
        from core.engines.intent_engine import IntentEngine
        parser = IntentEngine()

        # Strong coding signals
        weights = parser.parse_intent("Write a Python function to sort a list by a custom key")
        self.assertGreater(weights["coding"], 0.5,
            msg="Coding weight should be dominant for a Python function prompt")

        dominant = parser.dominant_capability("Debug this JavaScript function")
        self.assertEqual(dominant, "coding",
            msg="Dominant capability for a debug JS prompt should be 'coding'")

        # Non-zero values must be floats in [0, 1]
        for cap, val in weights.items():
            self.assertIsInstance(val, float)
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 1.0)

    def test_intent_parser_vision(self):
        """Intent parser identifies image-related prompts with vision as the dominant capability."""
        from core.engines.intent_engine import IntentEngine
        parser = IntentEngine()

        weights = parser.parse_intent("Describe what's in this image")
        self.assertGreater(weights["vision"], 0.5,
            msg="Vision weight should be dominant for an image description prompt")

        dominant = parser.dominant_capability("What does this photo show?")
        self.assertEqual(dominant, "vision",
            msg="Dominant capability for a photo prompt should be 'vision'")

    def test_intent_parser_multi_capability(self):
        """Intent parser produces multiple non-zero weights for mixed prompts."""
        from core.engines.intent_engine import IntentEngine
        parser = IntentEngine()

        # "Write a Python script that outputs JSON" → coding + writing + json_output
        weights = parser.parse_intent(
            "Write a Python script that reads a CSV file and outputs structured JSON"
        )
        non_zero = {k: v for k, v in weights.items() if v > 0.0}
        self.assertGreaterEqual(len(non_zero), 2,
            msg="A mixed prompt should produce at least 2 non-zero capability weights")
        self.assertGreater(weights["coding"], 0.0,
            msg="Coding weight should be non-zero for a Python script prompt")
        self.assertGreater(weights["json_output"], 0.0,
            msg="JSON output weight should be non-zero when 'JSON' is mentioned")

        # All weights must be valid floats in [0, 1]
        for cap, val in weights.items():
            self.assertIsInstance(val, float)
            self.assertGreaterEqual(val, 0.0)
            self.assertLessEqual(val, 1.0)

    def test_capability_registry_query(self):
        """Capability registry returns correct top models for a capability query."""
        from registry.capability_registry import get_top_models, get_models_by_capability

        top_coders = get_top_models("coding", n=3)
        # Registry must be populated (capability scanner has run)
        self.assertGreater(len(top_coders), 0,
            msg="get_top_models('coding') should return at least 1 model")

        # All returned models must have coding score > 0
        for m in top_coders:
            self.assertGreater(m.get("capabilities", {}).get("coding", 0), 0,
                msg=f"Model {m.get('model_id')} has coding=0 but was returned by get_top_models")

        # Top model should have the highest (or equal highest) coding score
        if len(top_coders) > 1:
            self.assertGreaterEqual(
                top_coders[0]["capabilities"]["coding"],
                top_coders[1]["capabilities"]["coding"],
                msg="get_top_models should return results in descending order"
            )

        # get_models_by_capability with min_score=5 should return only expert models
        expert_coders = get_models_by_capability("coding", min_score=5)
        for m in expert_coders:
            self.assertEqual(m["capabilities"]["coding"], 5,
                msg=f"{m.get('model_id')} was returned with min_score=5 but score < 5")

    def test_capability_router_ranking(self):
        """CapabilityRouter ranks a list of mock models — highest scoring model first."""
        from core.engines.routing_engine import CapabilityRouter
        from core.policies.policy import PolicyFilter

        # Build 3 mock models with different capability levels
        mock_models = [
            {
                "model_id": "weak/model:free",
                "capabilities": {"coding": 1, "reasoning": 1, "writing": 1,
                                  "analysis": 1, "vision": 0, "chat": 2,
                                  "tool_calling": 0, "json_output": 0, "streaming": 3},
                "capability_confidence": "high",
                "health": {"status": "healthy", "circuit": "closed",
                           "latency_ms": 800, "success_rate": 0.9}
            },
            {
                "model_id": "strong/coder:free",
                "capabilities": {"coding": 5, "reasoning": 4, "writing": 2,
                                  "analysis": 3, "vision": 0, "chat": 3,
                                  "tool_calling": 4, "json_output": 4, "streaming": 5},
                "capability_confidence": "high",
                "health": {"status": "healthy", "circuit": "closed",
                           "latency_ms": 300, "success_rate": 0.95}
            },
            {
                "model_id": "mid/general:free",
                "capabilities": {"coding": 3, "reasoning": 3, "writing": 3,
                                  "analysis": 3, "vision": 0, "chat": 4,
                                  "tool_calling": 3, "json_output": 3, "streaming": 5},
                "capability_confidence": "high",
                "health": {"status": "healthy", "circuit": "closed",
                           "latency_ms": 500, "success_rate": 0.85}
            },
        ]

        intent = {"coding": 0.9, "reasoning": 0.4}
        router = CapabilityRouter()
        policy = PolicyFilter(config={
            "exclude_unhealthy_statuses": ["unavailable", "degraded", "rate_limited"],
            "exclude_open_circuit": True,
            "min_capability_score": 1
        })

        ranked = router.rank_models(mock_models, intent, policy)

        # All 3 models are healthy, all should appear
        self.assertEqual(len(ranked), 3,
            msg="All 3 eligible models should appear in ranking")

        # The strong coder should rank first for a coding intent
        top_model = ranked[0][1]
        self.assertEqual(top_model["model_id"], "strong/coder:free",
            msg="Model with highest coding score should rank first for a coding intent")

        # Scores must be descending
        scores = [s for s, _ in ranked]
        self.assertEqual(scores, sorted(scores, reverse=True),
            msg="Ranked scores must be in descending order")

        # All scores in [0, 1]
        for score, _ in ranked:
            self.assertGreaterEqual(score, 0.0)
            self.assertLessEqual(score, 1.0)

    def test_capability_router_filters_unhealthy(self):
        """CapabilityRouter excludes rate-limited and circuit-open models from ranking."""
        from core.engines.routing_engine import CapabilityRouter
        from core.policies.policy import PolicyFilter

        mock_models = [
            {
                "model_id": "healthy/model:free",
                "capabilities": {"coding": 4, "reasoning": 3, "writing": 3,
                                  "analysis": 3, "vision": 0, "chat": 4,
                                  "tool_calling": 3, "json_output": 3, "streaming": 5},
                "capability_confidence": "high",
                "health": {"status": "healthy", "circuit": "closed",
                           "latency_ms": 400, "success_rate": 0.9}
            },
            {
                "model_id": "ratelimited/model:free",
                "capabilities": {"coding": 5, "reasoning": 5, "writing": 4,
                                  "analysis": 4, "vision": 0, "chat": 4,
                                  "tool_calling": 5, "json_output": 4, "streaming": 5},
                "capability_confidence": "high",
                "health": {"status": "rate_limited", "circuit": "closed",
                           "latency_ms": None, "success_rate": 0.1}
            },
            {
                "model_id": "circuit_open/model:free",
                "capabilities": {"coding": 5, "reasoning": 5, "writing": 4,
                                  "analysis": 4, "vision": 0, "chat": 4,
                                  "tool_calling": 5, "json_output": 4, "streaming": 5},
                "capability_confidence": "high",
                "health": {"status": "unknown", "circuit": "open",
                           "latency_ms": None, "success_rate": None}
            },
        ]

        intent = {"coding": 0.9}
        router = CapabilityRouter()
        policy = PolicyFilter(config={
            "exclude_unhealthy_statuses": ["unavailable", "degraded", "rate_limited"],
            "exclude_open_circuit": True,
            "min_capability_score": 1
        })

        ranked = router.rank_models(mock_models, intent, policy)

        # Only the healthy model should survive the policy gate
        self.assertEqual(len(ranked), 1,
            msg="Only the healthy model should pass the policy filter")
        self.assertEqual(ranked[0][1]["model_id"], "healthy/model:free",
            msg="The surviving model should be the healthy one")

        # select_best should return the healthy model
        best = router.select_best(mock_models, intent, policy)
        self.assertIsNotNone(best)
        self.assertEqual(best["model_id"], "healthy/model:free")


    # =========================================================================
    # Sprint 4: Execution Engine & Parallel Consensus Tests
    # =========================================================================

    def test_execution_result_structure(self):
        """ExecutionResult fields, to_dict(), from_failure(), from_success() are correct."""
        from core.results.execution_result import ExecutionResult

        # Success path
        r = ExecutionResult.from_success(
            model_id="qwen/qwen3-coder:free",
            provider="openrouter",
            response="def sort(arr): return sorted(arr)",
            latency_ms=412,
            http_status=200,
            routing_score=0.87,
            capability_confidence="high",
            attempt=1,
        )
        self.assertTrue(r.success)
        self.assertEqual(r.model_id, "qwen/qwen3-coder:free")
        self.assertEqual(r.provider, "openrouter")
        self.assertEqual(r.latency_ms, 412)
        self.assertEqual(r.routing_score, 0.87)
        self.assertEqual(r.capability_confidence, "high")
        self.assertIsNone(r.error_code)
        self.assertIsNone(r.error_message)
        self.assertFalse(r.is_empty_response)
        self.assertGreater(r.response_length, 0)

        # Failure path
        f = ExecutionResult.from_failure(
            model_id="some/model:free",
            provider="openrouter",
            latency_ms=800,
            error_code="rate_limit_exceeded",
            error_message="429 Too Many Requests",
            http_status=429,
            routing_score=0.5,
            capability_confidence="medium",
        )
        self.assertFalse(f.success)
        self.assertIsNone(f.response)
        self.assertEqual(f.error_code, "rate_limit_exceeded")
        self.assertEqual(f.http_status, 429)
        self.assertEqual(f.response_length, 0)

        # to_dict() serialization
        d = r.to_dict()
        self.assertIn("model_id", d)
        self.assertIn("success", d)
        self.assertIn("latency_ms", d)
        self.assertIn("routing_score", d)
        self.assertIn("response_preview", d)
        self.assertTrue(d["success"])

        # Timestamp is set automatically
        self.assertIsNotNone(r.timestamp)
        self.assertIn("T", r.timestamp)  # ISO format contains "T"

    def test_execution_engine_mock_success(self):
        """ExecutionEngine.execute() returns a successful ExecutionResult in mock mode."""
        from core.engines.execution_engine import SingleModelExecutor as ExecutionEngine

        engine = ExecutionEngine(timeout_seconds=10, max_retries=0)
        mock_model = {
            "model_id": "test/mock-success:free",
            "capability_confidence": "high",
        }

        with patch.dict(os.environ, {"HYDRA_MOCK": "true"}):
            # Default mock behavior is AVAILABLE → success
            result = engine.execute(
                prompt="What is recursion?",
                model=mock_model,
                routing_score=0.75,
            )

        self.assertIsNotNone(result)
        self.assertTrue(result.success, msg=f"Expected success but got: {result.error_message}")
        self.assertIsNotNone(result.response)
        self.assertGreater(len(result.response), 0)
        self.assertEqual(result.model_id, "test/mock-success:free")
        self.assertEqual(result.routing_score, 0.75)
        self.assertEqual(result.capability_confidence, "high")
        self.assertEqual(result.attempt, 1)
        self.assertGreaterEqual(result.latency_ms, 0)

    def test_execution_engine_mock_failure(self):
        """ExecutionEngine.execute() returns a failed ExecutionResult on provider error."""
        from core.engines.execution_engine import SingleModelExecutor as ExecutionEngine

        engine = ExecutionEngine(timeout_seconds=10, max_retries=0)
        mock_model = {
            "model_id": "test/mock-fail:free",
            "capability_confidence": "low",
        }

        # The synthetic head_id is derived from model_id:
        # "test/mock-fail:free" → "test-mock-fail-free"
        head_env = "TEST_MOCK_FAIL_FREE"

        with patch.dict(os.environ, {
            "HYDRA_MOCK": "true",
            f"MOCK_STATUS_{head_env}": "FAILED",
            f"MOCK_HTTP_STATUS_{head_env}": "429",
            f"MOCK_PROVIDER_CODE_{head_env}": "rate_limit_exceeded",
            f"MOCK_PROVIDER_MESSAGE_{head_env}": "Rate limit exceeded",
        }):
            result = engine.execute(
                prompt="Hello",
                model=mock_model,
                routing_score=0.3,
            )

        self.assertIsNotNone(result)
        self.assertFalse(result.success)
        self.assertIsNone(result.response)
        self.assertEqual(result.model_id, "test/mock-fail:free")
        self.assertIsNotNone(result.error_code)

    def test_execution_engine_retry(self):
        """ExecutionEngine retries on transient failures and succeeds on second attempt."""
        from core.engines.execution_engine import SingleModelExecutor as ExecutionEngine, _build_synthetic_head_id
        from unittest.mock import patch, MagicMock
        from providers.base import ProviderError

        engine = ExecutionEngine(timeout_seconds=10, max_retries=1, retry_delay_seconds=0.0)
        mock_model = {
            "model_id": "test/retry-model:free",
            "capability_confidence": "high",
        }

        call_count = {"n": 0}

        def mock_generate(prompt):
            call_count["n"] += 1
            if call_count["n"] == 1:
                raise ProviderError("Connection error", {
                    "status": "UNAVAILABLE",
                    "http_status": None,
                    "provider": "openrouter",
                    "model": "test/retry-model:free",
                    "provider_code": "connection_error",
                    "provider_message": "Network timeout",
                    "latency_ms": 100,
                })
            return "Retry succeeded!"

        with patch("core.engines.execution_engine.OpenRouterProvider") as MockProvider:
            instance = MagicMock()
            instance.generate = mock_generate
            MockProvider.return_value = instance

            result = engine.execute("Hello", mock_model, routing_score=0.5)

        self.assertTrue(result.success, msg=f"Expected success on retry but got: {result.error_message}")
        self.assertEqual(result.response, "Retry succeeded!")
        self.assertEqual(result.attempt, 2)
        self.assertEqual(call_count["n"], 2)

    def test_parallel_executor_all_succeed(self):
        """ParallelExecutor dispatches to 3 models concurrently and collects all successes."""
        from core.engines.execution_engine import ParallelExecutor
        from core.results.execution_result import ExecutionResult
        from unittest.mock import patch, MagicMock

        executor = ParallelExecutor(max_workers=3, timeout_seconds=10)

        mock_models = [
            {"model_id": "parallel/model-a:free", "capability_confidence": "high"},
            {"model_id": "parallel/model-b:free", "capability_confidence": "high"},
            {"model_id": "parallel/model-c:free", "capability_confidence": "medium"},
        ]

        def make_success(latency: int):
            def mock_execute(prompt, model, routing_score=0.0):
                return ExecutionResult.from_success(
                    model_id=model.get("model_id"),
                    provider="openrouter",
                    response=f"Response from {model.get('model_id')}",
                    latency_ms=latency,
                    routing_score=routing_score,
                )
            return mock_execute

        # Patch the entire ExecutionEngine.execute to avoid real HTTP calls
        call_latencies = {"parallel/model-a:free": 300, "parallel/model-b:free": 100, "parallel/model-c:free": 500}

        def mock_execute(prompt, model, routing_score=0.0):
            latency = call_latencies.get(model.get("model_id"), 200)
            return ExecutionResult.from_success(
                model_id=model.get("model_id"),
                provider="openrouter",
                response=f"Response from {model.get('model_id')}",
                latency_ms=latency,
                routing_score=routing_score,
            )

        with patch("core.engines.execution_engine.SingleModelExecutor") as MockEngine:
            instance = MagicMock()
            instance.execute = mock_execute
            MockEngine.return_value = instance

            results = executor.execute_all("Hello", mock_models)

        self.assertEqual(len(results), 3, msg="Should collect results from all 3 models")
        self.assertTrue(all(r.success for r in results), msg="All mock executions should succeed")

        # Results are sorted: successful by latency (fastest first)
        latencies = [r.latency_ms for r in results]
        self.assertEqual(latencies, sorted(latencies), msg="Results should be sorted by latency")

    def test_parallel_executor_partial_failure(self):
        """ParallelExecutor collects all results even when some models fail."""
        from core.engines.execution_engine import ParallelExecutor
        from core.results.execution_result import ExecutionResult
        from unittest.mock import patch, MagicMock

        executor = ParallelExecutor(max_workers=3, timeout_seconds=10)

        mock_models = [
            {"model_id": "partial/success-a:free", "capability_confidence": "high"},
            {"model_id": "partial/fail-b:free", "capability_confidence": "low"},
            {"model_id": "partial/success-c:free", "capability_confidence": "high"},
        ]

        def mock_execute(prompt, model, routing_score=0.0):
            mid = model.get("model_id", "")
            if "fail" in mid:
                return ExecutionResult.from_failure(
                    model_id=mid,
                    provider="openrouter",
                    latency_ms=50,
                    error_code="rate_limit_exceeded",
                    error_message="429",
                )
            return ExecutionResult.from_success(
                model_id=mid,
                provider="openrouter",
                response=f"Success from {mid}",
                latency_ms=200,
                routing_score=routing_score,
            )

        with patch("core.engines.execution_engine.SingleModelExecutor") as MockEngine:
            instance = MagicMock()
            instance.execute = mock_execute
            MockEngine.return_value = instance

            results = executor.execute_all("Hello", mock_models)

        self.assertEqual(len(results), 3, msg="All 3 results (success + fail) should be returned")

        successes = [r for r in results if r.success]
        failures = [r for r in results if not r.success]
        self.assertEqual(len(successes), 2, msg="Expected 2 successful results")
        self.assertEqual(len(failures), 1, msg="Expected 1 failed result")

        # Successes come before failures in sorted order
        result_ids = [r.model_id for r in results]
        success_ids = [r.model_id for r in results if r.success]
        fail_ids = [r.model_id for r in results if not r.success]
        # First N items are successes
        self.assertTrue(
            all(r.success for r in results[:len(successes)]),
            msg="Successful results should appear before failures"
        )

    def test_consensus_scored_strategy(self):
        """ConsensusEngine 'scored' strategy selects model with highest composite score."""
        from core.engines.consensus_engine import ConsensusEngine
        from core.results.execution_result import ExecutionResult

        results = [
            ExecutionResult.from_success(
                model_id="low/scorer:free",
                provider="openrouter",
                response="Short answer.",
                latency_ms=200,
                routing_score=0.30,  # Low routing score
                capability_confidence="high",
            ),
            ExecutionResult.from_success(
                model_id="high/scorer:free",
                provider="openrouter",
                response="A much more detailed and comprehensive answer with explanations.",
                latency_ms=400,
                routing_score=0.95,  # High routing score — should win
                capability_confidence="high",
            ),
            ExecutionResult.from_success(
                model_id="mid/scorer:free",
                provider="openrouter",
                response="A decent answer.",
                latency_ms=300,
                routing_score=0.60,
                capability_confidence="high",
            ),
        ]

        engine = ConsensusEngine()
        consensus = engine.evaluate(results, strategy="scored")

        self.assertEqual(consensus.winner.model_id, "high/scorer:free",
            msg="Scored strategy should select the model with highest routing score")
        self.assertEqual(consensus.strategy, "scored")
        self.assertEqual(consensus.successful_count, 3)
        self.assertEqual(consensus.failed_count, 0)
        self.assertGreater(consensus.consensus_score, 0.0)
        self.assertLessEqual(consensus.consensus_score, 1.0)

        # to_dict() should serialize cleanly
        d = consensus.to_dict()
        self.assertIn("winner", d)
        self.assertIn("strategy", d)
        self.assertIn("consensus_score", d)
        self.assertIn("successful_count", d)

    def test_consensus_fastest_strategy(self):
        """ConsensusEngine 'fastest' strategy selects the lowest-latency successful response."""
        from core.engines.consensus_engine import ConsensusEngine
        from core.results.execution_result import ExecutionResult

        results = [
            ExecutionResult.from_success(
                model_id="slow/model:free",
                provider="openrouter",
                response="Slow but correct answer.",
                latency_ms=1800,
                routing_score=0.9,
            ),
            ExecutionResult.from_success(
                model_id="fast/model:free",
                provider="openrouter",
                response="Fast answer.",
                latency_ms=150,  # Fastest — should win
                routing_score=0.6,
            ),
            ExecutionResult.from_failure(
                model_id="failed/model:free",
                provider="openrouter",
                latency_ms=50,
                error_code="rate_limit_exceeded",
                error_message="429",
            ),
        ]

        engine = ConsensusEngine()
        consensus = engine.evaluate(results, strategy="fastest")

        self.assertEqual(consensus.winner.model_id, "fast/model:free",
            msg="Fastest strategy should select the lowest-latency successful model")
        self.assertEqual(consensus.successful_count, 2,
            msg="Successful results should exclude the failed model")
        self.assertEqual(consensus.failed_count, 1,
            msg="Failed model should appear in failed list")
        self.assertEqual(consensus.strategy, "fastest")

        # Validate split lists
        self.assertTrue(all(r.success for r in consensus.successful))
        self.assertTrue(all(not r.success for r in consensus.failed))


    # =========================================================================
    # Sprint 5: Verification & Reliability Tests
    # =========================================================================

    def test_verifier_all_pass(self):
        """Verifier returns passed=True and score=1.0 when all constraints pass."""
        from core.engines.verification_engine import VerificationEngine, MinLengthConstraint, MaxLengthConstraint, ContainsKeywordConstraint
        from core.results.execution_result import ExecutionResult

        res = ExecutionResult.from_success(
            model_id="test/model",
            provider="openrouter",
            response="This is a test response containing the keyword apple.",
            latency_ms=100
        )

        engine = VerificationEngine(constraints=[
            MinLengthConstraint(min_chars=10),
            MaxLengthConstraint(max_chars=100),
            ContainsKeywordConstraint(keywords=["apple", "test"])
        ])

        vr = engine.verify(res)
        self.assertTrue(vr.passed)
        self.assertEqual(vr.score, 1.0)
        self.assertEqual(len(vr.checks), 3)
        self.assertTrue(all(c.passed for c in vr.checks))

    def test_verifier_partial_fail(self):
        """Verifier returns passed=False and fractional score when some constraints fail."""
        from core.engines.verification_engine import VerificationEngine, MinLengthConstraint, MaxLengthConstraint, ContainsKeywordConstraint
        from core.results.execution_result import ExecutionResult

        res = ExecutionResult.from_success(
            model_id="test/model",
            provider="openrouter",
            response="Short apple response.",
            latency_ms=100
        )

        engine = VerificationEngine(constraints=[
            MinLengthConstraint(min_chars=50),  # Fails
            MaxLengthConstraint(max_chars=100),  # Passes
            ContainsKeywordConstraint(keywords=["banana"])  # Fails
        ])

        vr = engine.verify(res)
        self.assertFalse(vr.passed)
        self.assertEqual(vr.score, 1 / 3)  # Only 1 of 3 passed
        self.assertEqual(vr.checks[0].constraint_name, "MinLengthConstraint")
        self.assertFalse(vr.checks[0].passed)
        self.assertTrue(vr.checks[1].passed)
        self.assertFalse(vr.checks[2].passed)

    def test_verifier_json_constraint(self):
        """JsonFormatConstraint correctly validates direct JSON and json code blocks."""
        from core.engines.verification_engine import JsonFormatConstraint

        constraint = JsonFormatConstraint()

        # Valid direct JSON
        res1 = constraint('{"key": "value", "list": [1, 2, 3]}')
        self.assertTrue(res1.passed)

        # Valid fenced JSON block
        res2 = constraint('Here is the json:\n```json\n{"status": "ok", "code": 200}\n```\nHope it helps!')
        self.assertTrue(res2.passed)

        # Invalid JSON
        res3 = constraint('Not a json at all.')
        self.assertFalse(res3.passed)

        # Empty string
        res4 = constraint('')
        self.assertFalse(res4.passed)

    def test_verifier_code_block_constraint(self):
        """CodeBlockConstraint detects code blocks in output."""
        from core.engines.verification_engine import CodeBlockConstraint

        constraint = CodeBlockConstraint()

        # Fenced code block present
        res1 = constraint('Here is your python function:\n```python\ndef hello():\n    return "hi"\n```')
        self.assertTrue(res1.passed)

        # Plain fenced code block
        res2 = constraint('```\ncode\n```')
        self.assertTrue(res2.passed)

        # No code blocks
        res3 = constraint('This is plain text without code blocks.')
        self.assertFalse(res3.passed)

    def test_self_correction_first_attempt_passes(self):
        """SelfCorrectionLoop stops on the first model if it passes verification."""
        from core.engines.correction_engine import SelfCorrectionLoop
        from core.engines.verification_engine import VerificationEngine, ContainsKeywordConstraint
        from core.results.execution_result import ExecutionResult
        from unittest.mock import patch, MagicMock

        # First model passes verification (contains 'apple')
        engine = VerificationEngine(constraints=[ContainsKeywordConstraint(["apple"])])
        loop = SelfCorrectionLoop(verifier=engine, max_attempts=3)

        mock_ranked = [
            (0.9, {"model_id": "model-a", "capability_confidence": "high"}),
            (0.8, {"model_id": "model-b", "capability_confidence": "high"}),
        ]

        def mock_execute(prompt, model, routing_score=0.0):
            # Model A responds with apple
            return ExecutionResult.from_success(
                model_id=model.get("model_id"),
                provider="openrouter",
                response="Response with apple",
                latency_ms=100,
                routing_score=routing_score
            )

        with patch("core.engines.correction_engine.SingleModelExecutor") as MockEngine:
            instance = MagicMock()
            instance.execute = mock_execute
            MockEngine.return_value = instance

            corr_res = loop.run("test prompt", mock_ranked)

        self.assertTrue(corr_res.passed)
        self.assertEqual(corr_res.attempts, 1)
        self.assertEqual(corr_res.final_consensus.winner.model_id, "model-a")
        self.assertEqual(len(corr_res.attempt_log), 1)

    def test_self_correction_fallback_to_second(self):
        """SelfCorrectionLoop moves to second model if first fails verification, and returns passed=True if second succeeds."""
        from core.engines.correction_engine import SelfCorrectionLoop
        from core.engines.verification_engine import VerificationEngine, ContainsKeywordConstraint
        from core.results.execution_result import ExecutionResult
        from unittest.mock import patch, MagicMock

        # Verifier requires keyword 'banana'
        engine = VerificationEngine(constraints=[ContainsKeywordConstraint(["banana"])])
        loop = SelfCorrectionLoop(verifier=engine, max_attempts=3)

        mock_ranked = [
            (0.9, {"model_id": "model-a", "capability_confidence": "high"}),
            (0.8, {"model_id": "model-b", "capability_confidence": "high"}),
            (0.7, {"model_id": "model-c", "capability_confidence": "high"}),
        ]

        def mock_execute(prompt, model, routing_score=0.0):
            mid = model.get("model_id")
            if mid == "model-a":
                # Fails verifier
                return ExecutionResult.from_success(
                    model_id=mid,
                    provider="openrouter",
                    response="Only apple",
                    latency_ms=100,
                    routing_score=routing_score
                )
            elif mid == "model-b":
                # Passes verifier
                return ExecutionResult.from_success(
                    model_id=mid,
                    provider="openrouter",
                    response="Fresh banana response!",
                    latency_ms=150,
                    routing_score=routing_score
                )
            return ExecutionResult.from_success(model_id=mid, provider="openrouter", response="", latency_ms=10)

        with patch("core.engines.correction_engine.SingleModelExecutor") as MockEngine:
            instance = MagicMock()
            instance.execute = mock_execute
            MockEngine.return_value = instance

            corr_res = loop.run("test prompt", mock_ranked)

        self.assertTrue(corr_res.passed)
        self.assertEqual(corr_res.attempts, 2)
        self.assertEqual(corr_res.final_consensus.winner.model_id, "model-b")
        self.assertEqual(len(corr_res.attempt_log), 2)
        self.assertFalse(corr_res.attempt_log[0]["verification_passed"])
        self.assertTrue(corr_res.attempt_log[1]["verification_passed"])

    def test_self_correction_exhausted(self):
        """SelfCorrectionLoop returns passed=False and the best logged attempt if all models fail verification."""
        from core.engines.correction_engine import SelfCorrectionLoop
        from core.engines.verification_engine import VerificationEngine, ContainsKeywordConstraint
        from core.results.execution_result import ExecutionResult
        from unittest.mock import patch, MagicMock

        # Requires 'cherry'
        engine = VerificationEngine(constraints=[ContainsKeywordConstraint(["cherry"])])
        loop = SelfCorrectionLoop(verifier=engine, max_attempts=2)

        mock_ranked = [
            (0.9, {"model_id": "model-a", "capability_confidence": "high"}),
            (0.8, {"model_id": "model-b", "capability_confidence": "high"}),
            (0.7, {"model_id": "model-c", "capability_confidence": "high"}),
        ]

        def mock_execute(prompt, model, routing_score=0.0):
            return ExecutionResult.from_success(
                model_id=model.get("model_id"),
                provider="openrouter",
                response="Prose without any red fruit",
                latency_ms=100,
                routing_score=routing_score
            )

        with patch("core.engines.correction_engine.SingleModelExecutor") as MockEngine:
            instance = MagicMock()
            instance.execute = mock_execute
            MockEngine.return_value = instance

            corr_res = loop.run("test prompt", mock_ranked)

        self.assertFalse(corr_res.passed)
        self.assertEqual(corr_res.attempts, 2)  # Limited by max_attempts=2
        # Returns model-a since they both had verification score 0.0 but model-a has higher routing score (0.9 vs 0.8)
        self.assertEqual(corr_res.final_consensus.winner.model_id, "model-a")

    def test_confidence_scorer(self):
        """ConfidenceScorer calculates weighted composite confidence and assigns correct label."""
        from core.engines.confidence_engine import ConfidenceScorer
        from core.results.consensus_result import ConsensusResult
        from core.results.verification_result import VerificationResult, CheckResult
        from core.results.execution_result import ExecutionResult

        # Mock consensus result
        winner = ExecutionResult.from_success(
            model_id="test-model",
            provider="openrouter",
            response="Test",
            latency_ms=100,
            routing_score=0.9
        )
        con_res = ConsensusResult(
            winner=winner,
            successful=[winner],
            failed=[],
            strategy="scored",
            consensus_score=0.8
        )

        # Mock verification result (1 of 2 check passed -> score=0.5)
        ver_res = VerificationResult(
            passed=False,
            checks=[
                CheckResult("check1", True, ""),
                CheckResult("check2", False, "")
            ],
            score=0.5,
            model_id="test-model"
        )

        # Weights: consensus=0.4, verification=0.4, routing=0.2
        # Expected score: 0.4*0.8 + 0.4*0.5 + 0.2*0.9 = 0.32 + 0.20 + 0.18 = 0.70
        scorer = ConfidenceScorer(weights={"consensus": 0.4, "verification": 0.4, "routing": 0.2})
        conf_score = scorer.score(con_res, ver_res)

        self.assertAlmostEqual(conf_score.final_score, 0.70)
        self.assertEqual(conf_score.label, "MEDIUM")

        # Test to_dict
        d = conf_score.to_dict()
        self.assertEqual(d["label"], "MEDIUM")
        self.assertEqual(d["final_score"], 0.70)

    def test_execute_and_verify_pipeline(self):
        """execute_and_verify returns a typed HydraResult containing correct result components."""
        from core.hydra import HydraController
        from core.results.hydra_result import HydraResult
        from core.engines.verification_engine import MinLengthConstraint
        from core.results.execution_result import ExecutionResult
        from unittest.mock import patch, MagicMock

        # We construct controller
        ctrl = HydraController("config/heads.json", "state/hydra_state.json")

        def mock_execute(prompt, model, routing_score=0.0):
            return ExecutionResult.from_success(
                model_id=model.get("model_id"),
                provider="openrouter",
                response="This response is long enough to pass verification and return success.",
                latency_ms=120,
                routing_score=routing_score
            )

        with patch("core.engines.execution_engine.SingleModelExecutor.execute", side_effect=mock_execute):
            result = ctrl.execute_and_verify(
                prompt="Hello",
                constraints=[MinLengthConstraint(min_chars=20)],
                self_correct=True,
                max_correction_attempts=2
            )

        self.assertIsInstance(result, HydraResult)
        self.assertTrue(result.passed)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.response, "This response is long enough to pass verification and return success.")
        self.assertTrue(result.execution.model_id)
        self.assertEqual(result.confidence.label, "HIGH")
        self.assertIsNotNone(result.consensus)
        self.assertIsNotNone(result.verification)
        self.assertIsNotNone(result.correction)
        self.assertIsNotNone(result.trace)

        # Assert trace details
        self.assertTrue(result.trace.intent)
        self.assertTrue(result.trace.intent_weights)
        self.assertTrue(result.trace.eligible_models)
        self.assertTrue(result.trace.ranked_models)
        self.assertEqual(len(result.trace.attempt_log), 1)

        # Test serializing HydraResult
        d = result.to_dict()
        self.assertEqual(d["response"], result.response)
        self.assertTrue(d["passed"])
        self.assertEqual(d["attempts"], 1)
        self.assertIn("execution", d)
        self.assertIn("consensus", d)
        self.assertIn("verification", d)
        self.assertIn("confidence", d)
        self.assertIn("correction", d)
        self.assertIn("trace", d)
        self.assertEqual(d["trace"]["intent"], result.trace.intent)

    def test_task_graph_dependency_resolution(self):
        """TaskGraph correctly computes ready nodes and handles status transitions."""
        from core.pipeline.dag import TaskGraph, TaskNode, TaskStatus

        graph = TaskGraph()
        node_a = TaskNode(id="a", name="A", description="Task A", capability="chat")
        node_b = TaskNode(id="b", name="B", description="Task B", capability="chat", depends_on=["a"])
        graph.add_node(node_a)
        graph.add_node(node_b)

        # Initially, only Node A is ready because Node B depends on Node A
        ready = graph.get_ready_nodes()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "a")

        # After Node A succeeds, Node B should be ready
        node_a.status = TaskStatus.SUCCESS
        ready = graph.get_ready_nodes()
        self.assertEqual(len(ready), 1)
        self.assertEqual(ready[0].id, "b")

        # Terminal nodes check: Node B is the terminal node
        terminals = graph.get_terminal_nodes()
        self.assertEqual(len(terminals), 1)
        self.assertEqual(terminals[0].id, "b")

    def test_planner_engine_sequence_parsing(self):
        """PlannerEngine splits prompt on 'then' or commas and assigns correct capabilities."""
        from core.pipeline.planner import PlannerEngine
        from core.context.hydra_context import HydraContext, RequestContext

        planner = PlannerEngine()
        context = HydraContext(request=RequestContext(prompt="Research GPT-5 then write Python code then summarize results"))
        planner.process(context)

        graph = context.workflow.task_graph
        self.assertIsNotNone(graph)
        self.assertEqual(len(graph.nodes), 3)

        # Assert correct sequencing dependencies: task_1 -> task_2 -> task_3
        nodes = list(graph.nodes.values())
        self.assertEqual(nodes[0].id, "task_1")
        self.assertEqual(nodes[0].capability, "analysis")
        self.assertEqual(nodes[0].depends_on, [])

        self.assertEqual(nodes[1].id, "task_2")
        self.assertEqual(nodes[1].capability, "coding")
        self.assertEqual(nodes[1].depends_on, ["task_1"])

        self.assertEqual(nodes[2].id, "task_3")
        self.assertEqual(nodes[2].capability, "writing")
        self.assertEqual(nodes[2].depends_on, ["task_2"])

    def test_scheduler_execution_loop(self):
        """Scheduler executes TaskGraph sequentially using routed mock models."""
        from core.hydra import HydraController
        from core.pipeline.dag import TaskStatus

        ctrl = HydraController("config/heads.json", "state/hydra_state.json")
        result = ctrl.execute_and_verify(
            prompt="Research local variables then write a Python function",
            self_correct=False
        )

        self.assertTrue(result.passed)
        self.assertIsNotNone(result.trace)
        
        # Check task graph serialization
        graph_dict = result.trace.metadata.get("task_graph")
        self.assertIsNotNone(graph_dict)
        self.assertEqual(len(graph_dict["nodes"]), 2)
        self.assertEqual(graph_dict["nodes"]["task_1"]["status"], "success")
        self.assertEqual(graph_dict["nodes"]["task_2"]["status"], "success")


    def test_specialist_resolution_and_execution(self):
        """Specialists are correctly resolved from registry and execute with domain prompts."""
        from core.specialists import get_specialist
        from core.specialists.coding import CodingSpecialist
        from core.specialists.writing import WritingSpecialist
        from core.specialists.general import GeneralSpecialist

        # 1. Resolve registered specialists
        coding_spec = get_specialist("coding")
        self.assertIsInstance(coding_spec, CodingSpecialist)

        writing_spec = get_specialist("writing")
        self.assertIsInstance(writing_spec, WritingSpecialist)

        # Unknown capability falls back to GeneralSpecialist (chat)
        unknown_spec = get_specialist("unregistered_capability")
        self.assertIsInstance(unknown_spec, GeneralSpecialist)

    def test_reviewer_engine_critique_loop(self):
        """ReviewerEngine audits output, requests revision on critique, and approves on APPROVED."""
        from core.engines.reviewer_engine import ReviewerEngine
        from core.pipeline.dag import TaskGraph, TaskNode, TaskStatus
        from core.context.hydra_context import HydraContext, RequestContext
        from core.results.execution_result import ExecutionResult

        # 1. Setup mock task graph and terminal node
        graph = TaskGraph()
        node = TaskNode(
            id="task_1",
            name="Write Code",
            description="Write a python binary search",
            capability="coding"
        )
        node.status = TaskStatus.SUCCESS
        node.result = ExecutionResult.from_success(
            model_id="test-model",
            provider="test-provider",
            response="def binary_search(): pass",
            latency_ms=100
        )
        graph.add_node(node)

        context = HydraContext(request=RequestContext(
            prompt="Write a python binary search",
            settings={"self_correct": True, "max_correction_attempts": 3}
        ))
        context.workflow.task_graph = graph

        reviewer = ReviewerEngine()

        # 2. Mock execute side effects:
        # First audit: "This is insecure." (causes revision)
        # Specialist revision execute: succeeds and writes revised output
        # Second audit: "APPROVED" (succeeds)
        call_count = 0
        def mock_execute_side_effect(prompt, model, routing_score=0.0):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # First audit prompt checking node output
                self.assertIn("def binary_search()", prompt)
                return ExecutionResult.from_success(
                    model_id="audit-model",
                    provider="audit-provider",
                    response="This is insecure. Use check parameters.",
                    latency_ms=50
                )
            elif call_count == 2:
                # Specialist revision execution
                self.assertIn("### FEEDBACK FROM REVIEWER:", prompt)
                return ExecutionResult.from_success(
                    model_id="test-model",
                    provider="test-provider",
                    response="```python\ndef binary_search(arr, val): pass\n```",
                    latency_ms=120
                )
            elif call_count == 3:
                # Second audit prompt checking revised output
                self.assertIn("def binary_search(arr, val)", prompt)
                return ExecutionResult.from_success(
                    model_id="audit-model",
                    provider="audit-provider",
                    response="APPROVED. Very secure now.",
                    latency_ms=50
                )
            return ExecutionResult.from_success(model_id="dummy", provider="dummy", response="", latency_ms=10)

        with patch("core.engines.execution_engine.SingleModelExecutor.execute", side_effect=mock_execute_side_effect):
            reviewer.process(context)

        # Assert correct transitions and execution steps occurred
        self.assertEqual(call_count, 3)
        self.assertEqual(node.status, TaskStatus.SUCCESS)
        self.assertEqual(node.result.response, "```python\ndef binary_search(arr, val): pass\n```")


if __name__ == "__main__":
    unittest.main()


