from common import *
with (LAYER/'action_layer3755.jsonl').open() as f:
    for line in f:
        r=json.loads(line)
        for d in r.get('action_decisions',[]):
            if d['state']=='supported':
                print(json.dumps(d,ensure_ascii=False)[:2400]);raise SystemExit
