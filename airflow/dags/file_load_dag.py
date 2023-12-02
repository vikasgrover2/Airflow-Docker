from datetime import datetime
from airflow import DAG
from airflow.operators.dummy_operator import DummyOperator
from airflow.operators.python_operator import PythonOperator
from data_replication_cls import data_replication

dag = DAG('Load_File_ATS', description='Load ATS data to Postgres', schedule_interval='0 12 * * *', start_date=datetime(2017, 3, 20), catchup=False)

with dag:
 dummy_task = DummyOperator(task_id='ETL_Start', retries = 3),

 load_file = data_replication(mstr_schema = 'app_rrs1', 
                                          app_name = 'fta', 
                                          env = 'dev',
                                          repmethod='csv', 
                                          filedir='/usr/local/airflow/dags/',
                                          filename='ATS_Data.csv',
                                          schemaname='vgrover',
                                          tablename='ats_import',
                                          task_id='start_loading_file'
                                          )
dummy_task >> load_file