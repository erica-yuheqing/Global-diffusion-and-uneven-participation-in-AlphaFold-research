"""Regression failures that must never be accepted as valid denominator handling."""
from pathlib import Path
import unittest,tempfile,shutil,csv,subprocess,sys,json
ROOT=Path(__file__).resolve().parents[1]
class DenominatorGuardTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp=tempfile.TemporaryDirectory(prefix='f3v7-method-tests-');cls.root=Path(cls.temp.name)
        for name in ['source_inputs','plot_data','manuscript']:shutil.copytree(ROOT/name,cls.root/name)
        (cls.root/'provenance').mkdir();shutil.copy2(ROOT/'provenance/input_manifest.json',cls.root/'provenance/input_manifest.json')
        for p in ROOT.iterdir():
            if p.is_file() and p.suffix in ['.md','.txt']:shutil.copy2(p,cls.root/p.name)
        shutil.copytree(ROOT/'code',cls.root/'code',ignore=shutil.ignore_patterns('__pycache__'))
        cls.original={p:p.read_bytes() for p in (cls.root/'plot_data').glob('*.csv')}
    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()
    def setUp(self):
        for p,data in self.original.items():p.write_bytes(data)
    def mutate(self,name,fn):
        p=self.root/'plot_data'/name
        with p.open(newline='') as f:rr=list(csv.DictReader(f))
        fn(rr)
        with p.open('w',newline='') as f:
            w=csv.DictWriter(f,fieldnames=list(rr[0]));w.writeheader();w.writerows(rr)
    def check(self,valid):
        r=subprocess.run([sys.executable,str(self.root/'code/verify.py')],capture_output=True,text=True)
        self.assertEqual(r.returncode==0,valid,r.stdout+r.stderr)
    def test_unchanged_frozen_data_pass(self):self.check(True)
    def test_activity_all_entrants_denominator_rejected(self):
        self.mutate('Figure3a.csv',lambda rr:rr[0].update(supported_pct=100*int(rr[0]['Y'])/int(rr[0]['N'])));self.check(False)
    def test_unknown_not_silently_assessed(self):
        self.mutate('Figure3a.csv',lambda rr:rr[0].update(unknown=0));self.check(False)
    def test_author_total_repeat_denominator_rejected(self):
        self.mutate('Figure3c.csv',lambda rr:[r.update(N=2137,percent=100*int(r['n'])/2137) for r in rr]);self.check(False)
    def test_registered_endpoint_is_not_confirmed_point(self):
        self.mutate('Figure3b.csv',lambda rr:rr[0].update(confirmed_pct=rr[0]['recorded_event_upper_pct']));self.check(False)
    def test_unknown_events_not_added_to_confirmed(self):
        self.mutate('Figure3b.csv',lambda rr:rr[0].update(C=2444,U=0));self.check(False)
    def test_reselected_short_window_cohort_rejected(self):
        self.mutate('S_fixed_windows.csv',lambda rr:rr[0].update(N=5604));self.check(False)
    def test_zero_net_is_not_zero_total_change(self):
        self.mutate('ED_use_transitions.csv',lambda rr:rr[2].update(changed_pct=0));self.check(False)
    def test_old_panel_mapping_rejected(self):
        self.mutate('panel_map.csv',lambda rr:rr[3].update(current_panel='Fig3d'));self.check(False)
if __name__=='__main__':unittest.main()
