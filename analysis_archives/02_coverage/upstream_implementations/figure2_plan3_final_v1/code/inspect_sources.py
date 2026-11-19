"""Saved, reproducible input inspection; no data mutation or API calls."""
from support import *

def main():
    with duckdb.connect() as c:
        c.execute("SET threads=1; SET memory_limit='2GB'")
        for title, query in [
            ('labels', f'''SELECT publication_year,confirmed_af,possible_af,screen_negative,af_use_label,adoption_eligible,count(*) AS N
              FROM read_parquet({lit(F1/'derived_study_records.parquet')}) GROUP BY ALL ORDER BY 1,2,3,4,5'''),
            ('metadata', f'''SELECT publication_year,count(*) AS N,count(*) FILTER(WHERE primary_subfield_id IS NULL) AS field_unknown,
              count(*) FILTER(WHERE annual_representative_work_id IS NULL) AS representative_unknown
              FROM read_parquet({lit(F1/'derived_study_records.parquet')}) GROUP BY ALL ORDER BY 1'''),
            ('registry', f'DESCRIBE SELECT * FROM read_parquet({lit(UP/"country_registry.parquet")})')]:
            print(title, c.execute(query).df().to_string(index=False), sep='\n')

if __name__ == '__main__': main()
