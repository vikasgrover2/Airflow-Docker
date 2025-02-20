#!/usr/bin/env python
# coding: utf-8

# In[1]: Imports
# refer if block at line 38, some imports are conditional
import psycopg2
import psycopg2.pool
import psycopg2.extras
from psycopg2.extras import execute_batch
import configparser
import time
import json
import concurrent.futures
from datetime import datetime
import sys
import os
import argparse

# In[2]: Adding args
parser = argparse.ArgumentParser(
                    prog='data_replication_parametrized',
                    description='Replication job to replicate tables in Openshift using concurrency',
                    epilog='For more info visit https://github.com/bcgov/nr-permitting-pipelines/')                  

parser.add_argument('mstr_schema', help='Schema where cdc_master_table_list table exists')  # positional argument 1
parser.add_argument('app_name', help='Application name for which tables should be replicated. Note only active tables will be replicated')     # positional argument 2
parser.add_argument('env', help='Environment where code is running, valid options: dev/test/prod')     # positional argument 3
parser.add_argument('-c','--concurrency',type= int, default= 5, help='Concurrency to control how many tables are replicated in parallel. Provide a number between 1 and 5')
parser.add_argument('-l', '--exec_local',action='store_true', help='Only specify the hook -l when local exeucution is desired. By default program assumes execution in OpenShift')
args = parser.parse_args()

mstr_schema = args.mstr_schema.lower()
app_name    = args.app_name.lower()
env = args.env.lower()
execute_locally     = args.exec_local
print(f'Master Schema : {mstr_schema}, App Name: {app_name}, Execute Locally: {execute_locally}')

start = time.time()

if not execute_locally:
    import oracledb 
    oracledb.init_oracle_client(lib_dir="/opt/oracle/instantclient_21_12")
    # In[3]: Retrieve Oracle database configuration
    oracle_username = os.environ['DB_USERNAME']
    oracle_password = os.environ['DB_PASSWORD']
    oracle_host = os.environ['DB_HOST']
    oracle_port = os.environ['DB_PORT']
    oracle_database = os.environ['DATABASE']
    # In[4]: Retrieve Postgres database configuration
    postgres_username = os.environ['ODS_USERNAME']
    postgres_password = os.environ['ODS_PASSWORD']
    postgres_host = os.environ['ODS_HOST']
    postgres_port = os.environ['ODS_PORT']
    postgres_database = os.environ['ODS_DATABASE']
else:
    import oracledb as oracledb 
    # Load the configuration file
    config = configparser.ConfigParser()
    config.read(f"./.cred/config.{env}.{app_name}.ini")
    # In[3]: Retrieve Oracle database configuration
    oracle_username = config['src']['username']
    oracle_password = config['src']['password']
    oracle_host = config['src']['host']
    oracle_port = config['src']['port']
    oracle_database = config['src']['database']
    # In[4]: Retrieve Postgres database configuration
    postgres_username = config['target']['username']
    postgres_password = config['target']['password']
    postgres_host = config['target']['host']
    postgres_port = config['target']['port']
    postgres_database = config['target']['database']

#In[5]: Concurrent tasks - number of tables to be replicated in parallel
concurrent_tasks = args.concurrency if args.concurrency<=5 else 5

# In[6]: Set up Oracle connection pool
dsn = f"{oracle_host}/{oracle_database}"
OrcPool = oracledb.SessionPool(user=oracle_username, password=oracle_password, dsn=dsn, min=concurrent_tasks,
                             max=concurrent_tasks, increment=1, encoding="UTF-8")

# In[7]: Setup Postgres Pool 
PgresPool = psycopg2.pool.ThreadedConnectionPool(
    minconn = concurrent_tasks, maxconn = concurrent_tasks,host=postgres_host, port=postgres_port, dbname=postgres_database, user=postgres_username, password=postgres_password
)

# In[8]: Function to get active rows from master table
def get_active_tables(mstr_schema,app_name):
  postgres_connection  = PgresPool.getconn()  
  postgres_cursor = postgres_connection.cursor()
  list_sql = f"""
  SELECT application_name,source_schema_name,source_table_name,target_schema_name,target_table_name,truncate_flag,cdc_flag,full_inc_flag,cdc_column,replication_order
  from {mstr_schema}.cdc_master_table_list c
  where  active_ind = 'Y' and lower(application_name)='{app_name}'
  order by replication_order, source_table_name
  """
  with postgres_connection.cursor() as curs:
            curs.execute(list_sql)
            rows = curs.fetchall()
  postgres_connection.commit()
  postgres_cursor.close()
  PgresPool.putconn(postgres_connection)
  return rows

# In[9]: Function to extract data from Oracle
def extract_from_oracle(table_name,source_schema):
    # Acquire a connection from the pool
    oracle_connection = OrcPool.acquire()
    oracle_cursor = oracle_connection.cursor()    
    try:
        # Use placeholders in the query and bind the table name as a parameter
        sql_query = f'SELECT * FROM {source_schema}.{table_name}'
        print(sql_query)
        oracle_cursor.execute(sql_query)
        rows = oracle_cursor.fetchall()
        OrcPool.release(oracle_connection)
        return rows
    except Exception as e:
        print(f"Error extracting data from Oracle: {str(e)}")
        OrcPool.release(oracle_connection)
        return []

# In[10]: Function to load data into Target PostgreSQL using data from Source Oracle
def load_into_postgres(table_name, data,target_schema):
    postgres_connection = PgresPool.getconn()
    postgres_cursor = postgres_connection.cursor()
    try:
        # Delete existing data in the target table
        delete_query = f'TRUNCATE TABLE {target_schema}.{table_name}'
        postgres_cursor.execute(delete_query)

        # Build the INSERT query with placeholders
        insert_query = f'INSERT INTO {target_schema}.{table_name} VALUES ({", ".join(["%s"] * len(data[0]))})'
        #insert_query = f'INSERT INTO {target_schema}.{table_name} VALUES %s'

        # Use execute_batch for efficient batch insert
        with postgres_connection.cursor() as cursor:
            # Prepare the data as a list of tuples
            data_to_insert = [(tuple(row)) for row in data]
            execute_batch(cursor, insert_query, data_to_insert)
            postgres_connection.commit()
    except Exception as e:
        print(f"Error loading data into PostgreSQL: {str(e)}")
    finally:
        # Return the connection to the pool
        if postgres_connection:
            postgres_cursor.close()
            PgresPool.putconn(postgres_connection)

# In[11]: Function to call both extract and load functions
def load_data_from_src_tgt(table_name,source_schema,target_schema):
        # Extract data from Oracle
        print(f'Source: Thread {table_name} started at ' + datetime.now().strftime("%H:%M:%S"))
        oracle_data = extract_from_oracle(table_name,source_schema)  # Ensure table name is in uppercase
        print(f'Source: Extraction for {table_name} completed at ' + datetime.now().strftime("%H:%M:%S"))
        
        if oracle_data:
            # Load data into PostgreSQL
            load_into_postgres(table_name, oracle_data, target_schema)
            print(f"Target: Data loaded into table: {table_name}")
            print(f'Target: Thread {table_name} ended at ' + datetime.now().strftime("%H:%M:%S"))

def run_replication():
    active_tables_rows =get_active_tables(mstr_schema,app_name) 
    tables_to_extract = [(row[2],row[1],row[3]) for row in active_tables_rows]
    print(f"tables to extract are {tables_to_extract}")
    print(f'No of concurrent tasks:{concurrent_tasks}')
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_tasks) as executor:
        # Submit tasks to the executor
        future_to_table = {executor.submit(load_data_from_src_tgt, table[0],table[1],table[2]): table for table in tables_to_extract}
        
        # Wait for all tasks to complete
        concurrent.futures.wait(future_to_table)
        
        # Print results
        for future in future_to_table:
            table_name = future_to_table[future]
            try:
                # Get the result of the task, if any
                future.result()
            except Exception as e:
                # Handle exceptions that occurred during the task
                print(f"Error replicating {table_name}: {e}")
    
    end = time.time()
    OrcPool.close()
    PgresPool.closeall()
    
    print("ETL process completed successfully.")
    print("The time of execution of the program is:", (end - start) , "secs")

# In[12]: Initializing concurrency
if __name__ == '__main__':
    # Main ETL process
    active_tables_rows =get_active_tables(mstr_schema,app_name) 
    #print(active_tables_rows)
    tables_to_extract = [(row[2],row[1],row[3]) for row in active_tables_rows]
    
    print(f"tables to extract are {tables_to_extract}")
    print(f'No of concurrent tasks:{concurrent_tasks}')
    # Using ThreadPoolExecutor to run tasks concurrently
    with concurrent.futures.ThreadPoolExecutor(max_workers=concurrent_tasks) as executor:
        # Submit tasks to the executor
        future_to_table = {executor.submit(load_data_from_src_tgt, table[0],table[1],table[2]): table for table in tables_to_extract}
        
        # Wait for all tasks to complete
        concurrent.futures.wait(future_to_table)
        
        # Print results
        for future in future_to_table:
            table_name = future_to_table[future]
            try:
                # Get the result of the task, if any
                future.result()
            except Exception as e:
                # Handle exceptions that occurred during the task
                print(f"Error replicating {table_name}: {e}")
    
    # record end time
    end = time.time()
    OrcPool.close()
    PgresPool.closeall()
    
    print("ETL process completed successfully.")
    print("The time of execution of the program is:", (end - start) , "secs")

