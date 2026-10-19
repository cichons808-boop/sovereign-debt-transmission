#!/usr/bin/env python3
"""Rebuild data, estimate every specification and verify the numerical results."""
from pathlib import Path
import argparse
import hashlib
import json
import os
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
os.environ['OPENBLAS_NUM_THREADS'] = '1'
os.environ['OMP_NUM_THREADS'] = '1'
os.environ['MPLBACKEND'] = 'Agg'

ESTIMATION = ['specification', 'selection', 'fiscal_extensions', 'panel_var',
              'simultaneous_inference', 'sensitivity', 'numerical_validation',
              'policy_weights', 'reporting_families', 'robustness',
              'equity_sensitivity', 'allocation_bounds', 'primary_inference',
              'mechanisms', 'engine_validation']
EXHIBITS = ['exhibit_style', 'projection_exhibits', 'diagnostic_exhibits',
            'allocation_exhibit', 'primary_tables', 'figures', 'result_tables',
            'presentation']


def run_module(name):
    print(name, flush=True)
    subprocess.run([sys.executable, str(ROOT/'src'/(name+'.py'))], cwd=ROOT, check=True)


def run(stage):
    (ROOT/'results').mkdir(exist_ok=True)
    if stage == 'data':
        run_module('prepare_data')
    elif stage == 'estimate':
        inputs = ['data/processed/fiscal_panel_ea.csv.gz',
                  'data/processed/fiscal_panel_external.csv.gz',
                  'data/raw/bolhuis_hf.xlsx', 'data/raw/shocks_ecb_mpd_me_m.csv']
        (ROOT/'results/input_hashes.json').write_text(json.dumps(
            {f: hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in inputs}, indent=2)+'\n')
        for module in ESTIMATION:
            run_module(module)
    elif stage == 'exhibits':
        for directory in ['output/tables', 'output/figures']:
            (ROOT/directory).mkdir(parents=True, exist_ok=True)
        for module in EXHIBITS:
            run_module(module)
    elif stage == 'check':
        run_module('verify_results')
    elif stage == 'all':
        for part in ['data', 'estimate', 'exhibits', 'check']:
            run(part)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=['data', 'estimate', 'exhibits', 'check', 'all'],
                        nargs='?', default='all')
    run(parser.parse_args().stage)
