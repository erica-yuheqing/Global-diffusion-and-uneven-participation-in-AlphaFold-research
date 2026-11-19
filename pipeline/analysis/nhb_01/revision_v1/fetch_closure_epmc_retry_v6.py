"""One final public XML attempt for four prior transport failures, isolated."""
from collections import Counter
import json
import re
from urllib.parse import urlsplit
import fetch_closure_public_v4 as base
from fetch_public_evidence import inventory, norm_doi
from local_recall import MODULE, destination, pin, sha, write_json

OUT = MODULE / 'evidence_closure_public_epmc_retry_v6'
SOURCE = MODULE / 'evidence_closure_preparation_v1/packets_private.json'


def allowed(url):
    parsed = urlsplit(url)
    return (parsed.scheme == 'https' and parsed.hostname == 'www.ebi.ac.uk' and
            not parsed.username and not parsed.password and parsed.port in (None, 443) and
            bool(re.fullmatch(r'/europepmc/webservices/rest/PMC\d+/fullTextXML', parsed.path)))


def main():
    rows = json.loads(SOURCE.read_text())
    targets = [r for r in rows if not r['body_document_path'] and
               r['public_lookup']['fulltext_status'] == 'transport_or_http_error' and
               re.fullmatch(r'PMC\d+', r['public_lookup']['pmcid'] or '')]
    destination(OUT).mkdir(mode=0o700); (OUT / 'raw').mkdir(mode=0o700)
    (OUT / 'documents').mkdir(mode=0o700)
    base.OUT = OUT; base.allowed = allowed; base.CAP = len(targets)
    archive = base.Archive(); results = []
    for row in targets:
        wid = row['work_id']; pmcid = row['public_lookup']['pmcid']; doi = norm_doi(row['doi'])
        url = 'https://www.ebi.ac.uk/europepmc/webservices/rest/' + pmcid + '/fullTextXML'
        raw, request = archive.get(url, wid, 'epmc_xml')
        result = {'work_id': wid, 'doi': doi, 'pmcid': pmcid, 'request': request,
                  'body_path': None, 'status': 'HTTP_or_transport_failure_no_negative_label',
                  'access_class': row['public_lookup']['fulltext_access_class'],
                  'license': row['public_lookup']['fulltext_license']}
        if raw:
            try:
                document, status = base.parse_body(raw, doi, wid); result['status'] = status
                if document:
                    path = OUT / 'documents' / (wid + '.json'); write_json(path, document)
                    result.update(body_path=str(path), body_sha256=sha(path))
            except (ValueError, RuntimeError, KeyError) as error:
                result.update(status='parse_or_identity_failure', error=str(error)[:300])
        results.append(result)
    write_json(OUT / 'results_private.json', results)
    summary = {'targets': len(targets), 'HTTP_sends': len(archive.calls),
        'bodies': sum(bool(r['body_path']) for r in results),
        'statuses': dict(Counter(r['status'] for r in results)),
        'paid_calls': 0, 'v3_model_inputs_changed': False}
    write_json(OUT / 'summary.json', summary)
    write_json(OUT / 'run_manifest.json', {'schema': 'closure-isolated-EPMC-transport-retry-v6',
        'inputs': [pin(SOURCE), pin(__file__)], 'summary': summary, 'outputs': inventory(OUT)})
    print('Isolated final Europe PMC attempt:', summary, flush=True)


if __name__ == '__main__':
    main()
