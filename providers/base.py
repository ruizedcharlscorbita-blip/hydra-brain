from abc import ABC, abstractmethod

class ProviderError(Exception):
    def __init__(self, message: str, diagnostics: dict):
        super().__init__(message)
        self.diagnostics = diagnostics

class BaseProvider(ABC):
    @abstractmethod
    def generate(self, prompt: str) -> str:
        """Generates text from a prompt.
        
        Args:
            prompt: The string prompt to send to the model.
            
        Returns:
            The generated response string.
            
        Raises:
            ProviderError: If the API call fails or generation fails.
        """
        pass

    @abstractmethod
    def health_check(self) -> dict:
        """Checks the health of the provider/model.
        
        Returns:
            A dictionary containing health diagnostics and telemetry details.
        """
        pass
