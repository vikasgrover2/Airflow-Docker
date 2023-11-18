FROM vgrover2/docker-airflow:baseAF
COPY requirements.txt /requirements.txt
RUN pip install -r /requirements.txt

COPY airflow/airflow.cfg ${AIRFLOW_HOME}/airflow.cfg
