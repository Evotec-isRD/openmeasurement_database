#%%
import gzip
from math import ceil
import os
import re
import json
import urllib.request
from time import time

import pandas as pd
from py2neo import Graph

from encode_for_neo4j import encode2neo4j

with open("config.json") as f:
    config = json.load(f)

port = config["port"]
user = config["user"]
pswd = config["pswd"]
neo4j_import_loc = config["neo4j_import_loc"]

graph = Graph("bolt://localhost:" + port, auth=(user, pswd))

temp_dir = "temp"
os.makedirs(temp_dir, exist_ok=True)


number = 1
synonyms_per_file = 1e6

unique_results = set()
while True:
    result_list = []
    # Get

    file_name = f"pc_synonym2compound_{str(number).zfill(6)}.ttl.gz"
    print(file_name)
    gz_file_loc = os.path.join(temp_dir, file_name)
    if not os.path.exists(gz_file_loc):
        start = time()
        download_url = rf"https://ftp.ncbi.nlm.nih.gov/pubchem/RDF/synonym/{file_name}"
        print("download: ", download_url)
        try:
            urllib.request.urlretrieve(download_url, gz_file_loc)
        except:
            break
        print("download time", time() - start)

    start = time()
    with gzip.open(gz_file_loc, "r") as f:
        for line in f:
            line = line.decode("utf-8")
            if line.startswith("@prefix"):
                continue
            synonym_id, _, compound = line.split("\t")
            compound = compound.lower()
            result = re.findall("(.*) .\n", compound)
            if result:
                if len(result) > 1:
                    print(f"Multiple hits with {compound}")
                    continue
                clean_synonym = encode2neo4j(result[0])

                result_list.append(result[0])
            else:
                print(f"Error with {compound}")

            if len(result_list) > 1000:
                unique_results.update(set(result_list))
                result_list = []
    print("reading time", time() - start)
    number += 1

    print(f"total compounds: {len(unique_results)}\n")

unique_results = list(unique_results)
#%%
split_size = 1e6
number_files = 0
for i in range(ceil(len(unique_results) / split_size)):
    result_df = pd.DataFrame(
        unique_results[int(i * split_size) : int((i + 1) * split_size)],
        columns=["compound"],
    )
    result_df = result_df.drop_duplicates()
    result_df.to_csv(
        os.path.join(neo4j_import_loc, f"compounds_{i}.csv"),
        index=False,
    )
    number_files += 1

del unique_results

#%%
for i in range(number_files):
    graph.run(
        f"""
        USING PERIODIC COMMIT 10000
        LOAD CSV  WITH HEADERS FROM 'file:///compounds_{i}.csv' AS row
        CREATE (comp:Compound {{pubChemCompId: row.compound}});
    """
    ).data()

#%%
response = graph.run(
        f"""
        CREATE constraint compoundId if not exists for (c:Compound) require c.pubChemCompId is unique;
    """
    ).data()
print(response)