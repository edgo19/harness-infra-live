.PHONY: setup check test fmt hcl-check ready

setup:
	uv sync --frozen

check:
	terragrunt hcl fmt --check
	terragrunt hcl validate
	uv run --frozen python scripts/check.py
	uv run --frozen python -m unittest discover -s tests -v

test:
	uv run --frozen python -m unittest discover -s tests -v

fmt:
	terragrunt hcl fmt

# This checks HCL parsing/formatting. Cloud-dependent input validation follows
# only after real modules and deployment prerequisites exist.
hcl-check:
	terragrunt hcl fmt --check

ready:
	uv run --frozen python scripts/check.py --ready --environment $(ENV)
