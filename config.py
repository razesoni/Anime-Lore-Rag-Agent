import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


# ============================================================
# PROJECT ROOT
# ============================================================

# config.py is stored directly inside the project root.
PROJECT_ROOT = Path(__file__).resolve().parent


# ============================================================
# LOAD ENVIRONMENT VARIABLES
# ============================================================

ENV_FILE = PROJECT_ROOT / ".env"

load_dotenv(ENV_FILE)


# ============================================================
# DATA DIRECTORIES
# ============================================================

DATA_DIR = PROJECT_ROOT / "data"

RAW_DATA_DIR = DATA_DIR / "raw"
PROCESSED_DATA_DIR = DATA_DIR / "processed"
EVALUATION_DATA_DIR = DATA_DIR / "evaluation"

DB_DIR = PROJECT_ROOT / "db"
CHROMA_DIR = DB_DIR / "chroma"


# ============================================================
# CREATE DIRECTORIES
# ============================================================

DIRECTORIES = [
    DATA_DIR,
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    EVALUATION_DATA_DIR,
    DB_DIR,
    CHROMA_DIR,
]

for directory in DIRECTORIES:
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# BOOLEAN HELPER
# ============================================================

def env_bool(name: str, default: bool = False) -> bool:
    """
    Convert an environment variable to a Python boolean.

    Examples:
        true  -> True
        1     -> True
        yes   -> True
        false -> False
    """

    value = os.getenv(name)

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "y",
        "on",
    }


# ============================================================
# SETTINGS CLASS
# ============================================================

@dataclass(frozen=True)
class Settings:
    """
    Central application configuration.

    Values are loaded from the .env file or environment
    variables supplied by Cloud Run.
    """

    # ------------------------------
    # GCP
    # ------------------------------

    gcp_project_id: str = os.getenv(
        "GOOGLE_CLOUD_PROJECT",
        "",
    )

    gcp_location: str = os.getenv(
        "GOOGLE_CLOUD_LOCATION",
        "us-central1",
    )

    use_vertex_ai: bool = env_bool(
        "GOOGLE_GENAI_USE_VERTEXAI",
        True,
    )

    # ------------------------------
    # Cloud Storage
    # ------------------------------

    gcs_bucket_name: str = os.getenv(
        "GCS_BUCKET_NAME",
        "",
    )

    # ------------------------------
    # MediaWiki / Fandom
    # ------------------------------

    mediawiki_api_url: str = os.getenv(
        "MEDIAWIKI_API_URL",
        "",
    )

    mediawiki_user_agent: str = os.getenv(
        "MEDIAWIKI_USER_AGENT",
    "Akashic-RAG/0.1",
)

    request_timeout: int = int(
        os.getenv(
            "REQUEST_TIMEOUT",
            "30",
        )
    )

    request_delay_seconds: float = float(
        os.getenv(
            "REQUEST_DELAY_SECONDS",
            "0.35",
            )
    )

    max_retries: int = int(
        os.getenv(
            "MAX_RETRIES",
            "5",
        )
    )

    mediawiki_maxlag: int = int(
        os.getenv(
            "MEDIAWIKI_MAXLAG",
            "5",
        )
    )

    # ------------------------------
    # Models
    # ------------------------------

    llm_model: str = os.getenv(
        "LLM_MODEL",
        "gemini-2.5-flash",
    )

    embedding_model: str = os.getenv(
        "EMBEDDING_MODEL",
        "gemini-embedding-001",
    )

    # ------------------------------
    # Chunking
    # ------------------------------

    chunk_size: int = int(
        os.getenv(
            "CHUNK_SIZE",
            "1000",
        )
    )

    chunk_overlap: int = int(
        os.getenv(
            "CHUNK_OVERLAP",
            "150",
        )
    )

    # ------------------------------
    # Retrieval
    # ------------------------------

    dense_k: int = int(
        os.getenv(
            "DENSE_K",
            "10",
        )
    )

    sparse_k: int = int(
        os.getenv(
            "SPARSE_K",
            "10",
        )
    )

    fusion_k: int = int(
        os.getenv(
            "FUSION_K",
            "10",
        )
    )

    rrf_k: int = int(
        os.getenv(
            "RRF_K",
            "60",
        )
    )

    rerank_top_n: int = int(
        os.getenv(
            "RERANK_TOP_N",
            "3",
        )
    )

    # ------------------------------
    # Chroma
    # ------------------------------

    chroma_collection: str = os.getenv(
        "CHROMA_COLLECTION",
        "akashic_lore",
    )

    chroma_directory: Path = CHROMA_DIR

    # ------------------------------
    # Flask
    # ------------------------------

    port: int = int(
        os.getenv(
            "PORT",
            "8080",
        )
    )

    flask_debug: bool = env_bool(
        "FLASK_DEBUG",
        False,
    )

    # ========================================================
    # VALIDATION
    # ========================================================

    def validate_chunking(self) -> None:
        """
        Validate chunking configuration.
        """

        if self.chunk_size <= 0:
            raise ValueError(
                "CHUNK_SIZE must be greater than 0."
            )

        if self.chunk_overlap < 0:
            raise ValueError(
                "CHUNK_OVERLAP cannot be negative."
            )

        if self.chunk_overlap >= self.chunk_size:
            raise ValueError(
                "CHUNK_OVERLAP must be smaller than "
                "CHUNK_SIZE."
            )

    def validate_retrieval(self) -> None:
        """
        Validate retrieval configuration.
        """

        values = {
            "DENSE_K": self.dense_k,
            "SPARSE_K": self.sparse_k,
            "FUSION_K": self.fusion_k,
            "RRF_K": self.rrf_k,
            "RERANK_TOP_N": self.rerank_top_n,
        }

        for name, value in values.items():
            if value <= 0:
                raise ValueError(
                    f"{name} must be greater than 0."
                )

    def validate_gcp(self) -> None:
        """
        Validate settings needed for GCP operations.

        We don't run this automatically because modules such
        as the cleaner and chunker should work locally even
        without GCP credentials.
        """

        if not self.gcp_project_id:
            raise ValueError(
                "GOOGLE_CLOUD_PROJECT is not configured."
            )

    def validate(self) -> None:
        """
        Validate configuration that applies everywhere.
        """

        self.validate_chunking()
        self.validate_retrieval()

    def validate_mediawiki(self) -> None:
        """
        Validate MediaWiki ingestion settings.
        """

        if not self.mediawiki_api_url:
            raise ValueError(
                "MEDIAWIKI_API_URL is not configured."
            )

        if not self.mediawiki_api_url.startswith(
            ("http://", "https://")
        ):
            raise ValueError(
                "MEDIAWIKI_API_URL must be a valid HTTP URL."
            )

        if self.request_timeout <= 0:
            raise ValueError(
                "REQUEST_TIMEOUT must be greater than 0."
            )

        if self.request_delay_seconds < 0:
            raise ValueError(
                "REQUEST_DELAY_SECONDS cannot be negative."
            )

        if self.max_retries < 0:
            raise ValueError(
                "MAX_RETRIES cannot be negative."
            )


# ============================================================
# GLOBAL SETTINGS OBJECT
# ============================================================

settings = Settings()

settings.validate()