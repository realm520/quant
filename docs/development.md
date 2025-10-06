# Development Guide

## Setup
```bash
make setup           # Complete environment setup
make install-dev     # Install dev dependencies only
```

## Development Workflow
1. Write tests first (TDD)
2. Implement features
3. Run `make check` (lint + format + test)
4. Commit changes

## Commands
```bash
make lint        # Run ruff
make format      # Run black
make test        # Run pytest
make test-cov    # Test with coverage
make pre-commit  # All checks before commit
```

## Testing
- **Unit tests**: `tests/unit/`
- **Integration tests**: `tests/integration/`
- **Contract tests**: `tests/contract/`
- **Markers**: `@pytest.mark.unit`, `@pytest.mark.integration`

## Code Style
- **Type hints**: Required for all functions
- **Docstrings**: Google style for all public APIs
- **Line length**: 100 characters
- **Imports**: Sorted with ruff

## Tools
- **uv**: Package management
- **mypy**: Static type checking (strict mode)
- **ruff**: Linting and import sorting
- **black**: Code formatting
- **pytest**: Testing framework

## Debugging
```bash
# Verbose logging
python -m tri_arb start --verbose

# Interactive debugging
python -m pdb -m tri_arb start
```

## Contributing
1. Fork and create feature branch
2. Follow TDD approach
3. Run `make check` before commit
4. Open PR with description
