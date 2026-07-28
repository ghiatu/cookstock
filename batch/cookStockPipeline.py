###a high level script to run the whole pipeline
# runBatch_cookStock_stage2template.py
# get super stocks
#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Tuesday 11/12/2024

@author: sxu
"""
from importlib import reload # python 2.7 does not require this
import os
import sys
#set cookstock path
def find_path():
    # หา root ของ repo จากตำแหน่งไฟล์นี้เอง แทนการเดินหาโฟลเดอร์ชื่อ 'cookstock'
    return os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

#set cookstock path
basePath = os.path.join(find_path())
#src path
srcPath = os.path.join(basePath, 'src')
print("Adding to sys.path:", srcPath)
sys.path.insert(0, srcPath)

import matplotlib
matplotlib.use('Agg')

import matplotlib.pyplot as plt
import cookStock
reload(cookStock)
from cookStock import *


from importlib import reload # python 2.7 does not require this
import get_tickers
reload(get_tickers)
from get_tickers import *

        
#filtered_by_sector = ['VNRX', 'INFU']
#get name of the file from the sector and date automatically
current_date = dt.date.today().strftime("%m_%d_%Y")

#set sector names to be run
# sectorCollection = [SectorConstants.TECH, SectorConstants.HEALTH_CARE, SectorConstants.BASICS, SectorConstants.SERVICES, SectorConstants.FINANCE, SectorConstants.ENERGY, SectorConstants.NON_DURABLE_GOODS, SectorConstants.DURABLE_GOODS]

from get_sp100 import get_sp100_tickers

# scan เฉพาะ S&P100 100 ตัวแรก (ปรับ limit=10 ตอนทดสอบให้รันเร็วขึ้น)
selected = get_sp100_tickers(limit=100)
sectorNameStr = "SP100"

y = batch_process(selected, sectorNameStr)
y.batch_pipeline_full()


def load_json(filepath):
    with open(filepath, "r") as f:
        return js.load(f)

def save_json(filepath, data):
    with open(filepath, "w") as f:
        js.dump(data, f, indent=4)

def append_to_json(filepath, ticker_data):
    data = load_json(filepath)
    data['data'].append(ticker_data)
    save_json(filepath, data)

def setup_result_file(basePath, file_prefix, current_date):
    filepath = os.path.join(basePath, 'results', f"{file_prefix}_vcp_study_{current_date}.json")
    save_json(filepath, {"data": []})
    return filepath