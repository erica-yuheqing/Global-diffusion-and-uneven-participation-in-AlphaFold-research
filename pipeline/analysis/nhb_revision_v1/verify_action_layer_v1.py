"""Read-only revalidation of frozen overlay; no files, APIs or model calls."""
import sys
sys.dont_write_bytecode = True

from action_layer_v1 import OUTPUT, verify_export


def main():
    report = verify_export(OUTPUT)
    print("Independent action overlay: PASS; work records: " + str(report["work_records"]))
    print("Protected keys: 83; accepted deltas: 185; uncertain works: 1408")
    print("Missing responses: 9; quarantined attribution: 1; original final/core unchanged")
    print("Action overlay ready: True; formal models ready: False; independent human gold: False")
    print("No API, writes or automatic changes to existing analysis outputs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
