# XT Exchange API Contracts

This directory contains OpenAPI specifications for XT Exchange REST API v4 endpoints used by the tri-arb system.

## Purpose

Define explicit contracts for XT API integration to enable:
- **Contract testing** - Verify adapter implementation matches API specification
- **Documentation** - Single source of truth for XT API behavior
- **Type generation** - Generate request/response types (future enhancement)
- **Mock data** - Create realistic test fixtures

## Files

- `xt-api.yaml` - OpenAPI 3.0 specification for XT REST API v4

## Usage

### Validate OpenAPI Spec
```bash
npx @apidevtools/swagger-cli validate contracts/xt-api.yaml
```

### Generate Types (Future)
```bash
# Using openapi-python-client or datamodel-code-generator
datamodel-codegen --input contracts/xt-api.yaml --output src/tri_arb/exchanges/xt_types.py
```

### View Documentation
```bash
# Using Swagger UI
npx swagger-ui-watcher contracts/xt-api.yaml
```

## Contract Testing

The OpenAPI specification is used by contract tests in `tests/unit/test_exchanges/test_xt_contract.py` to verify:
1. All specified endpoints are implemented
2. Request/response formats match specification
3. Error handling conforms to API behavior

## Limitations

- **Incomplete specification**: Some XT API fields are marked as TODO pending official documentation
- **Best-effort mapping**: Field names inferred from `xt_spot_api.py` reverse engineering
- **Public endpoints only**: Private/authenticated endpoints documented with placeholder auth

## TODO

1. Verify field names against official XT API documentation
2. Add response examples for all endpoints
3. Document error response codes and formats
4. Add rate limiting annotations
5. Include pagination details for list endpoints
