# Ladybird Web Benchmarks

This repository contains a set of web benchmarks used to measure the performance of the Ladybird browser engine.

# Installation

To install the python packages required by the benchmark runner you must install the packages listed in 
`requirements.txt`. You can do this using pip:

```bash
pip install -r requirements.txt
```

## Running Benchmarks

Before running the benchmarks you must first build Ladybird using the [build instructions for Ladybird](https://github.com/LadybirdBrowser/ladybird/blob/master/Documentation/BuildInstructionsLadybird.md). 
For best results, it is recommended to build Ladybird with the `Distribution` build preset, like so: 

```bash
BUILD_PRESET=Distribution ./Meta/ladybird.py build ladybird
```

After Ladybird is built, benchmarks are run using the `run.py` script. You must provide the path to the Ladybird 
executable using the `--executable` argument. For example:

```bash
./run.py --executable "${LADYBIRD_SOURCE_DIR}/Build/distribution/bin/ladybird" --output results.json  
```

## Comparing Results

After running benchmarks and saving the results as a JSON file, you can compare the results using the `compare.py` 
script. For example:

```bash
./compare.py -o old.json -n new.json
```
