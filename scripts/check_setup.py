from config import (
    PROJECT_ROOT,
    RAW_DATA_DIR,
    PROCESSED_DATA_DIR,
    EVALUATION_DATA_DIR,
    CHROMA_DIR,
    settings,
)


def main() -> None:
    print("=" * 60)
    print("AKASHIC-RAG CONFIGURATION")
    print("=" * 60)

    print("\nPROJECT")
    print("-" * 60)

    print(
        f"Project root       : {PROJECT_ROOT}"
    )

    print(
        f"Raw data           : {RAW_DATA_DIR}"
    )

    print(
        f"Processed data     : {PROCESSED_DATA_DIR}"
    )

    print(
        f"Evaluation data    : {EVALUATION_DATA_DIR}"
    )

    print(
        f"Chroma directory   : {CHROMA_DIR}"
    )

    print("\nGCP")
    print("-" * 60)

    print(
        f"Project ID         : "
        f"{settings.gcp_project_id or 'NOT SET'}"
    )

    print(
        f"Location           : {settings.gcp_location}"
    )

    print(
        f"Use Vertex AI      : {settings.use_vertex_ai}"
    )

    print(
        f"GCS bucket         : "
        f"{settings.gcs_bucket_name or 'NOT SET'}"
    )

    print("\nMODELS")
    print("-" * 60)

    print(
        f"LLM                : {settings.llm_model}"
    )

    print(
        f"Embedding          : {settings.embedding_model}"
    )

    print("\nCHUNKING")
    print("-" * 60)

    print(
        f"Chunk size         : {settings.chunk_size}"
    )

    print(
        f"Chunk overlap      : {settings.chunk_overlap}"
    )

    print("\nRETRIEVAL")
    print("-" * 60)

    print(
        f"Dense K            : {settings.dense_k}"
    )

    print(
        f"Sparse K           : {settings.sparse_k}"
    )

    print(
        f"Fusion K           : {settings.fusion_k}"
    )

    print(
        f"RRF K              : {settings.rrf_k}"
    )

    print(
        f"Rerank Top N       : {settings.rerank_top_n}"
    )

    print("\nFLASK")
    print("-" * 60)

    print(
        f"Port               : {settings.port}"
    )

    print(
        f"Debug              : {settings.flask_debug}"
    )

    print("\n" + "=" * 60)
    print("Configuration loaded successfully.")
    print("=" * 60)


if __name__ == "__main__":
    main()