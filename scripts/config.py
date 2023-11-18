import os

PYTHONPATH = os.environ['PYTHONPATH']
#Scripts datasets
TRAIN_SCRIPT_PATH = f"{PYTHONPATH}/scripts/data/train_iris.csv"
PREDICT_SCRIPT_PATH = f"{PYTHONPATH}/scripts/data/predict_iris.csv"
MODEL_PATH = f"{PYTHONPATH}/scripts/data/model_v1.sav"
TRAIN_DATA_PATH = f"{PYTHONPATH}/scripts/data/train_data.csv"
PREDICT_DATA_PATH = f"{PYTHONPATH}/scripts/data/predict_data.csv"