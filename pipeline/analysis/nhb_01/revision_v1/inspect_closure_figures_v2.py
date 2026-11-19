"""Offline PDF raster previews and unchanged-map check; visual judgment remains external."""
import json
from pathlib import Path
import subprocess
import tempfile
import pandas as pd
import pyarrow.parquet as pq
from PIL import Image
from local_recall import MODULE, require, pin, write_json
from build_revision_reading_package import check_inventory

SOURCE=MODULE/'figure1_revision_final_v2'
MAP=MODULE/'first_observed_map_v2'
OUT=MODULE/'closure_visual_review_v2'


def main():
    require(not OUT.exists(),'Choose a new visual audit version')
    check_inventory(SOURCE);check_inventory(MAP)
    first=pd.read_csv(SOURCE/'country_first_observed.csv',keep_default_na=False).sort_values('country_code').reset_index(drop=True)
    locations=pd.read_csv(MAP/'country_first_observed_locations.csv',keep_default_na=False)
    observed=locations[first.columns].sort_values('country_code').reset_index(drop=True)
    pd.testing.assert_frame_equal(first,observed)
    stage=Path(tempfile.mkdtemp(prefix='.closure-visual-',dir=MODULE))
    pdfs=['supplement_raw_domestic_all_countries','supplement_paired_domestic_all_countries']
    pages={}
    for name in pdfs:
        result=subprocess.run(['pdfinfo',str(SOURCE/'figures'/f'{name}.pdf')],capture_output=True,text=True,check=True)
        n=int(next(line.split(':',1)[1] for line in result.stdout.splitlines() if line.startswith('Pages:')))
        require(n==5,'Expected five bounded country pages per heatmap')
        subprocess.run(['pdftoppm','-r','150','-png',str(SOURCE/'figures'/f'{name}.pdf'),str(stage/name)],check=True)
        pages[name]=n
    png=[]
    for path in sorted((SOURCE/'figures').glob('*.png')):
        with Image.open(path) as im:
            png.append({'name':path.name,'pixels':list(im.size),'dpi':list(im.info.get('dpi',[]))})
    write_json(stage/'preview_manifest.json',{'inputs':[pin(SOURCE/'run_manifest.json'),pin(MAP/'run_manifest.json')],
        'first_observed_map_rows_unchanged':len(first),'new_map_requests':0,'heatmap_pages':pages,
        'png_metadata':png,'derived_study_records':pq.ParquetFile(SOURCE/'derived_study_records.parquet').metadata.num_rows,
        'visual_judgment':'pending_manual_assistant_view_not_machine_certified','author_review':'pending'})
    stage.rename(OUT);print('Cached map remains exact for all',len(first),'country dates; PDF previews:',OUT)


if __name__=='__main__':main()
