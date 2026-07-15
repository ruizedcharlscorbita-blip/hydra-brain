import os
import json
import time
import urllib.request
import urllib.error
from providers.base import BaseProvider, ProviderError

def classify_http_status(http_status: int) -> str:
    """Classifies an HTTP status code into a normalized Hydra health status."""
    if http_status == 200:
        return "AVAILABLE"
    elif http_status in (404, 503):
        return "UNAVAILABLE"
    elif http_status == 429:
        return "RATE_LIMITED"
    else:
        return "FAILED"

class OpenRouterProvider(BaseProvider):
    def __init__(self, model_name: str, head_id: str):
        self.model_name = model_name
        self.head_id = head_id
        # Reloading API key from env in case it is updated dynamically
        self.api_key = os.getenv("OPENROUTER_API_KEY", "")

    def _is_mock_enabled(self) -> bool:
        mock_env = os.getenv("HYDRA_MOCK", "").lower() == "true"
        mock_key = not self.api_key or self.api_key.startswith("mock")
        return mock_env or mock_key

    def generate(self, prompt: str) -> str:
        start_time = time.time()
        head_env_suffix = self.head_id.upper().replace("-", "_")

        if self._is_mock_enabled():
            status = os.getenv(f"MOCK_STATUS_{head_env_suffix}", "AVAILABLE").upper()
            latency = int(os.getenv(f"MOCK_LATENCY_MS_{head_env_suffix}", "200"))
            
            if status != "AVAILABLE":
                mock_http = int(os.getenv(f"MOCK_HTTP_STATUS_{head_env_suffix}", "500"))
                mock_code = os.getenv(f"MOCK_PROVIDER_CODE_{head_env_suffix}", "mock_failure")
                mock_msg = os.getenv(f"MOCK_PROVIDER_MESSAGE_{head_env_suffix}", "Mock generation failed")
                
                diagnostics = {
                    "status": status,
                    "http_status": mock_http,
                    "latency_ms": latency,
                    "provider": "openrouter",
                    "model": self.model_name,
                    "provider_code": mock_code,
                    "provider_message": mock_msg
                }
                raise ProviderError(mock_msg, diagnostics)
                
            # Simulate a successful response
            if "recursion" in prompt.lower():
                return (
                    "Recursion is a programming and mathematical concept where a function "
                    "calls itself, directly or indirectly, to solve a problem. It relies on: "
                    "\n1. Base Case: The condition under which the function stops calling itself."
                    "\n2. Recursive Case: The logic that reduces the problem towards the base case."
                )
            return f"[MOCK] Simulated response from {self.head_id} for prompt: '{prompt}'"

        if not self.api_key:
            latency = int((time.time() - start_time) * 1000)
            diagnostics = {
                "status": "FAILED",
                "http_status": 401,
                "latency_ms": latency,
                "provider": "openrouter",
                "model": self.model_name,
                "provider_code": "missing_api_key",
                "provider_message": "OPENROUTER_API_KEY environment variable is not set."
            }
            raise ProviderError("API key not set", diagnostics)

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/hydra-brain/hydra-brain",
            "X-Title": "Hydra Brain v0.2.1",
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": prompt}]
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            # 30-second timeout for normal generation calls
            with urllib.request.urlopen(req, timeout=30) as response:
                res_body = json.loads(response.read().decode("utf-8"))
                if "choices" in res_body and len(res_body["choices"]) > 0:
                    return res_body["choices"][0]["message"]["content"]
                else:
                    latency = int((time.time() - start_time) * 1000)
                    diagnostics = {
                        "status": "FAILED",
                        "http_status": response.status,
                        "latency_ms": latency,
                        "provider": "openrouter",
                        "model": self.model_name,
                        "provider_code": "bad_response",
                        "provider_message": f"Unexpected API response structure: {res_body}"
                    }
                    raise ProviderError("Bad response structure", diagnostics)
        except urllib.error.HTTPError as e:
            latency = int((time.time() - start_time) * 1000)
            http_status = e.code
            status = classify_http_status(http_status)
            
            provider_code = None
            provider_message = None
            try:
                err_body = e.read().decode("utf-8")
                err_json = json.loads(err_body)
                error_obj = err_json.get("error", {})
                provider_message = error_obj.get("message")
                provider_code = error_obj.get("code")
                if provider_code is not None:
                    provider_code = str(provider_code)
            except Exception:
                provider_message = str(e)
                
            diagnostics = {
                "status": status,
                "http_status": http_status,
                "latency_ms": latency,
                "provider": "openrouter",
                "model": self.model_name,
                "provider_code": provider_code,
                "provider_message": provider_message
            }
            raise ProviderError(f"OpenRouter HTTP {http_status} Error: {provider_message}", diagnostics)
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            diagnostics = {
                "status": "UNAVAILABLE",
                "http_status": None,
                "latency_ms": latency,
                "provider": "openrouter",
                "model": self.model_name,
                "provider_code": "connection_error",
                "provider_message": str(e)
            }
            raise ProviderError(f"OpenRouter Connection Error: {e}", diagnostics)

    def health_check(self) -> dict:
        start_time = time.time()
        head_env_suffix = self.head_id.upper().replace("-", "_")

        if self._is_mock_enabled():
            status = os.getenv(f"MOCK_STATUS_{head_env_suffix}", "AVAILABLE").upper()
            latency = int(os.getenv(f"MOCK_LATENCY_MS_{head_env_suffix}", "10"))
            
            # Resolve HTTP status
            mock_http_env = os.getenv(f"MOCK_HTTP_STATUS_{head_env_suffix}")
            if mock_http_env:
                mock_http = int(mock_http_env)
            else:
                if status == "AVAILABLE":
                    mock_http = 200
                elif status == "RATE_LIMITED":
                    mock_http = 429
                elif status == "UNAVAILABLE":
                    mock_http = 503
                else:
                    mock_http = 500
                    
            # Resolve provider errors
            mock_code = os.getenv(f"MOCK_PROVIDER_CODE_{head_env_suffix}")
            mock_msg = os.getenv(f"MOCK_PROVIDER_MESSAGE_{head_env_suffix}")
            
            if status == "RATE_LIMITED" and not mock_code:
                mock_code = "rate_limit_exceeded"
                mock_msg = "Rate limit exceeded"
            elif status == "FAILED" and not mock_code:
                if mock_http == 401:
                    mock_code = "invalid_api_key"
                    mock_msg = "Invalid API key"
                elif mock_http == 403:
                    mock_code = "permission_denied"
                    mock_msg = "Permission denied"
                else:
                    mock_code = "internal_error"
                    mock_msg = "Internal server error"
            elif status == "UNAVAILABLE" and not mock_code:
                if mock_http == 404:
                    mock_code = "model_not_found"
                    mock_msg = "Model not found"
                else:
                    mock_code = "provider_unavailable"
                    mock_msg = "Provider unavailable"
            
            # Short sleep to guarantee a baseline latency
            time.sleep(0.001)
            
            return {
                "status": status,
                "http_status": mock_http,
                "latency_ms": latency,
                "provider": "openrouter",
                "model": self.model_name,
                "provider_code": mock_code,
                "provider_message": mock_msg
            }

        if not self.api_key:
            latency = int((time.time() - start_time) * 1000)
            return {
                "status": "UNAVAILABLE",
                "http_status": None,
                "latency_ms": latency,
                "provider": "openrouter",
                "model": self.model_name,
                "provider_code": "missing_api_key",
                "provider_message": "OPENROUTER_API_KEY environment variable is not set."
            }

        url = "https://openrouter.ai/api/v1/chat/completions"
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/hydra-brain/hydra-brain",
            "X-Title": "Hydra Brain v0.2.1",
        }
        payload = {
            "model": self.model_name,
            "messages": [{"role": "user", "content": "ping"}],
            "max_tokens": 1
        }

        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers=headers,
            method="POST"
        )

        try:
            with urllib.request.urlopen(req, timeout=5) as response:
                latency = int((time.time() - start_time) * 1000)
                return {
                    "status": "AVAILABLE",
                    "http_status": response.status,
                    "latency_ms": latency,
                    "provider": "openrouter",
                    "model": self.model_name,
                    "provider_code": None,
                    "provider_message": None
                }
        except urllib.error.HTTPError as e:
            latency = int((time.time() - start_time) * 1000)
            http_status = e.code
            status = classify_http_status(http_status)
            
            provider_code = None
            provider_message = None
            try:
                err_body = e.read().decode("utf-8")
                err_json = json.loads(err_body)
                error_obj = err_json.get("error", {})
                provider_message = error_obj.get("message")
                provider_code = error_obj.get("code")
                if provider_code is not None:
                    provider_code = str(provider_code)
            except Exception:
                provider_message = str(e)
                
            return {
                "status": status,
                "http_status": http_status,
                "latency_ms": latency,
                "provider": "openrouter",
                "model": self.model_name,
                "provider_code": provider_code,
                "provider_message": provider_message
            }
        except Exception as e:
            latency = int((time.time() - start_time) * 1000)
            return {
                "status": "UNAVAILABLE",
                "http_status": None,
                "latency_ms": latency,
                "provider": "openrouter",
                "model": self.model_name,
                "provider_code": "connection_error",
                "provider_message": str(e)
            }
