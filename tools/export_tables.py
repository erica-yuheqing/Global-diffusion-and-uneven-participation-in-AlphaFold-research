"""Render all final supplementary display tables to Markdown from their cell-level CSVs."""
import argparse
import csv
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output',type=Path,required=True)
    out=parser.parse_args().output
    sources=sorted((ROOT/'tables').glob('Table_S*/displayed_*.csv'))
    if len(sources)!=40 or len({s.parent for s in sources})!=14:
        raise ValueError('Install the complete 01_figures_and_display_tables bundle first')
    out.mkdir(parents=True,exist_ok=False)
    for p in sources:
        with p.open(encoding='utf-8-sig',newline='') as f:
            rows=list(csv.reader(f))
        n=len(rows[0])
        def line(row):
            return '| '+' | '.join(str(v).replace('|',r'\|').replace('\n','<br>') for v in row)+' |\n'
        with (out/(p.parent.name+'.md')).open('a') as f:
            f.write('## '+p.parent.name+' '+p.stem.removeprefix('displayed_')+'\n\n')
            f.write(line(rows[0])+line(['---']*n))
            for row in rows[1:]:
                f.write(line(row))
            f.write('\n')
    print('Exported 14 tables, 40 display blocks.')


if __name__=='__main__':
    main()
