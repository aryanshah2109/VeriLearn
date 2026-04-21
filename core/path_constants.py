from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
print(ROOT_DIR)

# Config Path
CONFIG_PATH = ROOT_DIR / "core" / "config.yaml"

# Logger Path
LOGGER_PATH = ROOT_DIR / "core" / "logger.py"

# Logs Path
LOGS_PATH = ROOT_DIR / "logs"

# Data Path
RAW_DATA_PATH = ROOT_DIR / "data" / "raw" / "ncert"
PROCESSED_DATA_PATH = ROOT_DIR / "data" / "processed"
EMBEDDINGS_PATH = ROOT_DIR / "data" / "embeddings"

# Vector Store Path
VECTOR_STORE_PATH = ROOT_DIR / "vector_store"

# Evaluation Dataset Path
EVALUATION_DATA_PATH = ROOT_DIR / "data" / "evaluation"
TRAIN_DATA_PATH = EVALUATION_DATA_PATH / "train.json"
TEST_DATA_PATH = EVALUATION_DATA_PATH / "test.json"