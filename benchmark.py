'''

Copyright (c) 2023 Marco Diniz Sousa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.

'''

import argparse
import json
import logging
import multiprocessing
import sys

import pandas as pd

from functools import partial
from itertools import chain
from pathlib import Path
from timeit import default_timer as timer

import landauer.entropy as entropy
import landauer.evaluate as evaluate
import landauer.parse as parse

def path(working_directory, filename):
    return Path(filename) if Path(filename).is_absolute() else working_directory / filename

def check_rule(rule, collection_item):
    benchmark_name, benchmark_item = collection_item
    return benchmark_name == rule['benchmark'] and ('list' not in rule or len(rule['list']) == 0 or benchmark_item in set(rule['list']))

def apply_rules(collection, rules):
    return set(chain.from_iterable(filter(partial(check_rule, rule), collection) for rule in rules))

def get_tree_data(tree, design_data, majority_support, overwrite):
    start = timer()
    if (overwrite or not tree.is_file()):
        tree.parent.mkdir(parents = True, exist_ok = True)
        tree_data = parse.parse(design_data, majority_support)
        with tree.open('w') as f:
            f.write(parse.serialize(tree_data))
        return (tree_data, True, timer() - start)
    
    with tree.open() as f:
        tree_data = parse.deserialize(f.read())
        return (tree_data, False, timer() - start)

def generate_entropy_data(entropy_file, tree_data, overwrite, timeout):
    start = timer()
    if (overwrite or not entropy_file.is_file()):
        entropy_file.parent.mkdir(parents = True, exist_ok = True)
        entropy_data = entropy.entropy(tree_data, timeout)
        with entropy_file.open('w') as f:
            f.write(entropy.serialize(entropy_data))
            return (True, timer() - start)
    return (False, timer() - start)

def run(working_directory, benchmark, benchmark_item, overwrite, timeout):
    logging.info(f"'{benchmark_item['name']}' from '{benchmark}': started")
    try:
        design = path(working_directory, benchmark_item["files"]["design"])
        assert design.is_file(), f"'{benchmark_item['name']}' from '{benchmark}': design not found"
        with design.open() as f:
            design_data = f.read()

        tree = path(working_directory, benchmark_item["files"]["tree"])
        tree_data, tree_overwritten, tree_time = get_tree_data(tree, design_data, benchmark_item["majority_support"], overwrite)

        entropy_file = path(working_directory, benchmark_item["files"]["entropy"])
        entropy_overwritten, entropy_time = generate_entropy_data(entropy_file, tree_data, overwrite or tree_overwritten, timeout)

        logging.info(f"'{benchmark_item['name']}' from '{benchmark}': completed")
        return (benchmark, benchmark_item['name'], tree_overwritten, tree_time, entropy_overwritten, entropy_time)

    except Exception as e:
        logging.error(f"'{benchmark_item['name']}' from '{benchmark}': failed: {e}")
        return None

def main():
    argparser = argparse.ArgumentParser()
    argparser.add_argument('benchmarks', type = argparse.FileType('r'))
    argparser.add_argument('--accept', type = argparse.FileType('r'))
    argparser.add_argument('--ignore', type = argparse.FileType('r'))
    argparser.add_argument('--processes', type = int, default = multiprocessing.cpu_count())
    argparser.add_argument('--timeout', type = int, default = 0)
    argparser.add_argument('--overwrite', action = 'store_true')
    argparser.add_argument('--debug', action = 'store_true')
    argparser.add_argument('--output', type = argparse.FileType('w'))
    
    args = argparser.parse_args()
    
    if args.debug:
        logging.basicConfig(level=logging.DEBUG)

    benchmarks = json.loads(args.benchmarks.read())
    collection = set((benchmark["name"], benchmark_item["name"]) for benchmark in benchmarks for benchmark_item in benchmark["list"])
    
    if args.accept != None:
        rules = json.loads(args.accept.read())
        collection = apply_rules(collection, rules)

    if args.ignore != None:
        rules = json.loads(args.ignore.read())
        collection -= apply_rules(collection, rules)

    working_directory = Path(args.benchmarks.name).parent.resolve()

    tasks = [(working_directory, benchmark["name"], benchmark_item, args.overwrite, args.timeout) \
        for benchmark in benchmarks for benchmark_item in benchmark["list"] if (benchmark["name"], benchmark_item["name"]) in collection]

    pool = multiprocessing.Pool(args.processes)
    result = pool.starmap(run, tasks)

    df = pd.DataFrame(filter(None, result), columns=['benchmark', 'name', 'tree_overwritten', 'tree_time', 'entropy_overwritten', 'entropy_time'])
    df.to_csv(args.output if args.output else sys.stdout)

if __name__ == '__main__':
    main()