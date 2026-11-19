"""Bounded public provenance check for one named database boundary case."""
import requests
from local_recall import MODULE, destination, pin, write_json, require
from fetch_public_evidence import inventory

OUT = MODULE / 'evidence_closure_tm_provenance_v1'
SOURCES = (
    ('method.html', 'https://tmalphafold.ttk.hu/method'),
    ('downloads.html', 'https://tmalphafold.ttk.hu/downloads'),
    ('database_source.xml', 'https://www.ebi.ac.uk/europepmc/webservices/rest/PMC9825488/fullTextXML'),
)


def main():
    out = destination(OUT); out.mkdir(mode=0o700)
    records = []
    for filename, url in SOURCES:
        record = {'url': url, 'paid_inference': False, 'attempts': 1}
        try:
            r = requests.get(url, timeout=35, allow_redirects=False)
            record['http_status'] = r.status_code
            if r.status_code == 200:
                require(0 < len(r.content) <= 2000000, 'Public page too large/empty')
                if filename.endswith('.xml'):
                    require(b'10.1093/nar/gkac928' in r.content and b'<article' in r.content,
                            'Database source identity/envelope mismatch')
                path = out / filename; path.write_bytes(r.content); path.chmod(0o600)
                record['archive'] = pin(path)
        except requests.RequestException as error:
            record['failure'] = type(error).__name__
        records.append(record)
    summary = {'work_id': 'W4415354285', 'public_HTTP_sends': len(records),
        'paid_API_calls': 0, 'frozen_model_packets_unchanged': True,
        'source_purpose': 'Distinguish AF-derived TMDET/quality annotations from sequence-only CCTOP topology. External database provenance is not proof of coordinate retrieval by the reviewed work.',
        'semantic_acceptance': False, 'sources': records}
    write_json(out / 'summary.json', summary)
    write_json(out / 'run_manifest.json', {'schema': 'closure-named-resource-provenance-v1',
        'inputs': [pin(__file__)], 'summary': summary, 'outputs': inventory(out)})
    print(summary)


if __name__ == '__main__':
    main()
