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

class data_replication():
    
    def __init__(self,mstr_schema,app_name, env ):
        self.mstr_schema = mstr_schema
        self.app_name = app_name
        self.env = env
        print(f'Master Schema : {mstr_schema}, App Name: {app_name}, Env: {env}')

    def myfunction():
        print('Hello world')