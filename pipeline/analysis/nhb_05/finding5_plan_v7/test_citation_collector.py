import tempfile,unittest,json,sqlite3
from pathlib import Path
from unittest.mock import patch
from collect_citations import Collector,Halt
class Offline(Collector):
 def http(self,url,kind,batch,price=.0001):
  if kind=='rate_check':return {'rate_limit':{'daily_remaining_usd':1,'prepaid_remaining_usd':0,'endpoint_costs_usd':{'list':.0001}}}
  raise AssertionError('Network must not be reached')
class Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.c=Offline(Path(self.tmp.name),'never_real_key');self.b={'batch_id':'b','work_ids':['W1']}
  self.c.db.execute("INSERT INTO batch(id,status,cursor,identity_done) VALUES('b','partial','*',1)")
  self.c.db.execute("INSERT INTO alias VALUES('b','W1','W9','provider_redirect')");self.c.db.commit()
 def tearDown(self):self.c.db.close();self.c.writer_lock.close();self.tmp.cleanup()
 def response(self,refs=None,cursor=None):
  return {'meta':{'count':1,'next_cursor':cursor},'results':[{'id':'https://openalex.org/W2','publication_date':'2021-01-01','referenced_works':refs if refs is not None else ['https://openalex.org/W9'],'authorships':[]}]}
 def test_alias_maps_to_frozen_original(self):
  self.c.consume(self.b,'*',self.response());self.assertEqual(self.c.db.execute('SELECT * FROM edge').fetchall(),[('W2','W1')])
 def test_unknown_link_kept_not_zero(self):
  self.c.consume(self.b,'*',self.response(['W77']));self.assertEqual(self.c.db.execute('SELECT count(*) FROM unresolved').fetchone()[0],1)
  self.assertFalse(self.c.snapshot('test')['fixed_window_analysis_ready'])
 def test_same_citing_work_and_edge_saved_once(self):
  self.c.consume(self.b,'*',self.response(cursor='second'));self.c.consume(self.b,'second',self.response())
  self.assertEqual(self.c.db.execute('SELECT count(*) FROM edge').fetchone()[0],1);self.assertEqual(self.c.db.execute('SELECT count(*) FROM citing').fetchone()[0],1)
 def test_missing_authors_are_not_certified_nonself(self):
  self.c.consume(self.b,'*',self.response());self.assertEqual(self.c.db.execute('SELECT author_status FROM citing').fetchone()[0],'missing_or_empty')
 def test_repeated_cursor_rejected(self):
  with self.assertRaises(ValueError):self.c.consume(self.b,'*',self.response(cursor='*'))
 def test_empty_page_with_cursor_not_complete(self):
  with self.assertRaises(Halt):self.c.consume(self.b,'*',{'meta':{'count':1,'next_cursor':'next'},'results':[]})
 def test_budget_stops_before_request(self):
  self.c.used=self.c.cap
  with patch('requests.Session') as net:
   with self.assertRaises(Halt):Collector.http(self.c,'https://api.openalex.org/works','test','b')
   net.assert_not_called()
 def test_HTTP_connection_reused_within_thread(self):
  with patch('requests.Session') as session,patch('time.sleep'):
   response=session.return_value.get.return_value.__enter__.return_value
   response.status_code=200;response.json.return_value={'id':'W9'}
   Collector.http(self.c,'https://api.openalex.org/works/W1','identity_singleton','b',0)
   Collector.http(self.c,'https://api.openalex.org/works/W2','identity_singleton','b',0)
   self.assertEqual(session.call_count,1)
   self.assertEqual(session.return_value.get.call_count,2)
 def test_429_pauses_and_is_archived(self):
  with patch('requests.Session') as session:
   response=session.return_value.get.return_value.__enter__.return_value;response.status_code=429
   with self.assertRaises(Halt):Collector.http(self.c,'https://api.openalex.org/works','incoming_page','b',_attempt=2)
   self.assertEqual(self.c.db.execute('SELECT status FROM request ORDER BY n DESC LIMIT 1').fetchone()[0],'http_429')
 def test_504_sets_shared_cooldown_and_preserves_budget(self):
  with patch('requests.Session') as session:
   response=session.return_value.get.return_value.__enter__.return_value;response.status_code=504
   # Invoke the pre-patch implementation once; intercept only its retry.
   original_http=Collector.http
   with patch.object(Collector,'http',return_value={'recovered':True}) as retry:
    result=original_http(self.c,'https://api.openalex.org/works','incoming_page','b')
    self.assertTrue(result['recovered']);self.assertEqual(retry.call_count,1)
   self.assertGreater(self.c.cooldown_until,0)
   self.assertAlmostEqual(self.c.usage(),.0001)
 def test_network_retry_is_bounded_and_budgeted(self):
  import requests
  with patch('requests.Session') as session,patch('time.sleep'):
   session.return_value.get.side_effect=requests.ConnectionError('simulated')
   with self.assertRaises(Halt):Collector.http(self.c,'https://api.openalex.org/works','incoming_page','b')
   self.assertEqual(session.return_value.get.call_count,3)
   self.assertAlmostEqual(self.c.usage(),.0003)
   self.assertEqual(self.c.db.execute('SELECT count(*) FROM request').fetchone()[0],3)
 def test_completed_batch_does_not_resend(self):
  self.c.consume(self.b,'*',self.response())
  self.c.batch(self.b)
 def test_unknown_target_id_not_literal_alias_none(self):
  self.c.db.execute("UPDATE alias SET current=NULL,status='not_found_unknown'");self.c.db.commit()
  self.c.consume(self.b,'*',self.response(['None']));self.assertEqual(self.c.db.execute('SELECT count(*) FROM edge').fetchone()[0],0)
if __name__=='__main__':unittest.main()
