from pathlib import Path
import sys 
current_path = Path(__file__).parent.resolve()
parent_path = current_path.parent.absolute()
sys.path.append(str(parent_path))

import json 
import numpy as np
from joblib import dump
from src.estimator import BootcampEstimator
from commons.utils import load_training_data, prepare_points, prepare_input_points, update_app_config, load_requirements
import argparse
import logging
import mlflow
from mlflow import MlflowClient
from commons.custom_model import CustomModel
import warnings
warnings.filterwarnings('ignore')

logger = logging.getLogger(__name__)
logging.basicConfig(filename='train/logs/app.log', filemode = 'w', level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

def main(env):

    logger.info('started main')

    #---------------------------------------------------------------
    # Instancia o estimator
    #---------------------------------------------------------------

    bootcamp_estimator = BootcampEstimator(env = env)

    #---------------------------------------------------------------
    # Carrega os dados de treino
    #---------------------------------------------------------------

    # Carrega as instâncias de treino
    instances = load_training_data ("data/train/")

    #---------------------------------------------------------------
    # Prepara os dados de treino
    #---------------------------------------------------------------

    points = prepare_points(instances)
    input_points = prepare_input_points(points)

    #---------------------------------------------------------------
    # Treinando o modelo
    #---------------------------------------------------------------

    model, m, drift_params, sample_points, model_metric = bootcamp_estimator.fit(points = points, input_points =  input_points)

    #---------------------------------------------------------------
    # Guarda os artefatos do modelo
    #---------------------------------------------------------------

    # Salva o modelo
    dump(model, 'temp/clustering_model.joblib') 

    # Salva o mapa
    m.save('temp/clustering_map.html')

    # Salva os parâmetros de model drift
    dump(drift_params, 'temp/drift_params.joblib') 

    # Salva os data points de exemplo
    dump(sample_points, 'temp/sample_points.joblib')

    #---------------------------------------------------------------
    # Registra o experimento no MLFlow
    #---------------------------------------------------------------

    mlflow.set_tracking_uri("file://{}/mlruns".format(parent_path))
    mlflow_experiment = mlflow.set_experiment('model-retrain')

    with mlflow.start_run() as run:

        run_id = run.info.run_id
        artifact_path = "model-artifacts"
        
        print("Modelo: {}".format(run_id))

        app_config_new_values = dict()
        app_config_new_values['run_id'] = run_id
        update_app_config('config/app_config.ini', app_config_new_values)

        mlflow.log_params({"n_clusters": model.n_clusters})
        mlflow.log_metric("mean_perc_inner_radius", model_metric)
        mlflow.log_artifact("temp/clustering_map.html", artifact_path = artifact_path)
        mlflow.log_artifact("temp/drift_params.joblib", artifact_path = artifact_path)
        mlflow.log_artifact("temp/sample_points.joblib", artifact_path = artifact_path)
        mlflow.log_artifact("temp/clustering_model.joblib", artifact_path = artifact_path)
        mlflow.log_artifact("config/app_config.ini", artifact_path = artifact_path)
        mlflow.log_input(mlflow.data.from_numpy(input_points), context="training")

        # Create an instance of your custom model
        custom_model = CustomModel(env = 'PROD')

        artifacts = {
            "app_config": f"runs:/{run_id}/{artifact_path}/app_config.ini",
            "model": f"runs:/{run_id}/{artifact_path}/clustering_model.joblib"
        }

        # Specify the path to your requirements.txt file
        file_path = 'requirements.txt'

        # Load requirements into a list
        requirements_list = load_requirements(file_path)
        
        conda_env = {
            'name': 'my_mlflow_env',
            'channels': ['defaults'],
            'dependencies': [
                'python=3.10',
                'pip',
                {
                    'pip': requirements_list
                }
            ]
        }
        
        mlflow.pyfunc.log_model(
            artifact_path = "model",
            python_model = custom_model,
            artifacts = artifacts,
            conda_env = conda_env
        )

        print ("Completo!")

    mlflow.end_run()

    # Assim como fizemos anteriormente, podemos registrar este experimento como um novo modelo (ainda em dev)
    result = mlflow.register_model(
        f"runs:/{run_id}/model", "dev.bootcamp.kmeans-clustering"
    )

    # Agora podemos marcar a versão do nosso modelo como candidato à produção
    client = MlflowClient()
    client.set_registered_model_alias("dev.bootcamp.kmeans-clustering", "candidate-{}".format(run_id), result.version)

    logger.info('ended main')

if __name__ == "__main__":

    parser = argparse.ArgumentParser(description='Receive main parameters')
    parser.add_argument('--env', required=True, help='environment to run the application')
    args = parser.parse_args()
    main(args.env)