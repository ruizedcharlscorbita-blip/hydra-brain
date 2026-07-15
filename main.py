import sys
import os
import logging
from core.hydra import HydraController

def setup_logging() -> None:
    """Configures the application logger to record details into logs/hydra.log."""
    log_dir = "logs"
    if not os.path.exists(log_dir):
        os.makedirs(log_dir)
        
    log_file = os.path.join(log_dir, "hydra.log")
    
    # Configure root/hydra logger
    logger = logging.getLogger("hydra")
    logger.setLevel(logging.DEBUG)
    
    # Clean previous handlers to avoid duplicate messages if re-initialized
    logger.handlers.clear()
    
    # File handler writing utf-8 logs
    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s (%(filename)s:%(lineno)d): %(message)s"
    )
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)

def load_dotenv() -> None:
    """Parses .env file and loads values into os.environ (dependency-free)."""
    env_path = ".env"
    if os.path.exists(env_path):
        try:
            with open(env_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    # Skip empty lines and comments
                    if not line or line.startswith("#"):
                        continue
                    
                    # Split at the first '=' sign
                    if "=" in line:
                        key, val = line.split("=", 1)
                        key = key.strip()
                        val = val.strip()
                        # Strip double/single quotes if present
                        if (val.startswith('"') and val.endswith('"')) or (val.startswith("'") and val.endswith("'")):
                            val = val[1:-1]
                        os.environ[key] = val
        except Exception as e:
            print(f"Warning: Failed to load .env file: {e}", file=sys.stderr)

def main() -> None:
    # Support UTF-8 characters like checkmarks on all terminals
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8")
        except Exception:
            pass

    # 1. Parse command line arguments
    if len(sys.argv) < 2:
        print("Usage: python main.py \"<prompt>\"")
        sys.exit(1)
        
    prompt = sys.argv[1]

    # 2. Load env vars and setup logging
    load_dotenv()
    setup_logging()

    if prompt.lower() == "discover":
        print("OpenRouter Discovery\n")
        try:
            from registry.model_registry import refresh_registry
            models = refresh_registry()
            print(f"Found {len(models)} free models\n")
            for model in models:
                print(f"✓ {model.get('provider')} {model.get('display_name')}")
            print("\nRegistry updated successfully.")
            sys.exit(0)
        except Exception as e:
            print(f"Error during discovery: {e}")
            logging.getLogger("hydra").error(f"Discovery error: {e}", exc_info=True)
            sys.exit(1)

    # 3. Print startup message
    print("HYDRA BRAIN ONLINE")

    # 4. Instantiate and execute Controller
    config_path = os.path.join("config", "heads.json")
    state_path = os.path.join("state", "hydra_state.json")
    try:
        controller = HydraController(config_path, state_path)
        response = controller.handle_request(prompt)
        print("Response:\n")
        print(response)
    except Exception as e:
        print(f"\nError: {e}")
        # Log to file for diagnostics
        logging.getLogger("hydra").error(f"Fatal error in main: {e}", exc_info=True)
        sys.exit(1)

if __name__ == "__main__":
    main()
