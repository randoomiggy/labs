.PHONY: test test-ep001 test-all status next

test:
	python3 -m unittest discover -s tests -v

test-ep001:
	python3 -m unittest discover -s practice/ep001_log_summary -v

test-all: test test-ep001

status:
	python3 tools/workflow.py status

next:
	python3 tools/workflow.py next
