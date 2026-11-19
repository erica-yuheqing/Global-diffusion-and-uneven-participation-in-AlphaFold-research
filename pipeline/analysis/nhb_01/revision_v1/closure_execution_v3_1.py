"""Transport-only stop refinement; legacy core/settings/signatures unchanged."""
import closure_execution_v3 as original
from local_recall import require

class GuardedLedger(original.Ledger):
    def reserve(self,model,wid,body):
        # Re-check immediately before reservation. If one of four in-flight
        # requests discovers a payment/authentication failure, stop later sends.
        with self.locked():
            rows=self.rows()
            require(not any(r.get('event')=='settled' and r.get('model_key')==model and
                r.get('http_status') in (401,402,403) for r in rows),
                f'Model {model} payment/authentication guard stopped new requests')
        return super().reserve(model,wid,body)

original.Ledger=GuardedLedger
if __name__=='__main__': original.main()
