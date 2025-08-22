"""Configuration management for civiphrases."""

import os
from typing import Optional
from dotenv import load_dotenv

# Load environment variables from .env file if it exists
load_dotenv()


class Config:
    """Configuration class for civiphrases."""
    
    def __init__(self):
        # Civitai API configuration
        self.civitai_api_key: Optional[str] = os.getenv("CIVITAI_API_KEY")
        
        # Text Generation WebUI configuration
        self.tgw_base_url: str = os.getenv("TGW_BASE_URL", "http://127.0.0.1:5001/v1")
        self.tgw_api_key: str = os.getenv("TGW_API_KEY", "local")
        self.tgw_model_name: Optional[str] = os.getenv("TGW_MODEL_NAME")
        
        # Output directory
        self.out_dir: str = os.getenv("OUT_DIR", "./out")
        
        # Default CLI values
        self.default_max_items: int = 200
        self.default_batch_size: int = 10
        self.default_include_nsfw: bool = False
        self.default_lang: str = "all"
        
        # Civitai API base URL
        self.civitai_base_url: str = "https://civitai.com/api/v1"
        
        # Rate limiting
        self.rate_limit_delay: float = 1.0  # seconds between requests
        self.max_retries: int = 3
        self.backoff_factor: float = 2.0
    
    @property
    def wildcards_dir(self) -> str:
        """Path to wildcards output directory."""
        return os.path.join(self.out_dir, "wildcards")
    
    @property
    def state_dir(self) -> str:
        """Path to state directory."""
        return os.path.join(self.out_dir, "state")
    
    @property
    def logs_dir(self) -> str:
        """Path to logs directory."""
        return os.path.join(self.out_dir, "logs")
    
    @property
    def items_file(self) -> str:
        """Path to items.jsonl file."""
        return os.path.join(self.state_dir, "items.jsonl")
    
    @property
    def phrases_file(self) -> str:
        """Path to phrases.jsonl file."""
        return os.path.join(self.state_dir, "phrases.jsonl")
    
    @property
    def manifest_file(self) -> str:
        """Path to manifest.json file."""
        return os.path.join(self.state_dir, "manifest.json")
    
    def ensure_directories(self):
        """Create necessary directories if they don't exist."""
        os.makedirs(self.wildcards_dir, exist_ok=True)
        os.makedirs(self.state_dir, exist_ok=True)
        os.makedirs(self.logs_dir, exist_ok=True)


# Global config instance
config = Config()
