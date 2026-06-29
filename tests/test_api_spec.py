import schemathesis

schema = schemathesis.from_uri("http://localhost:8000/openapi.json")


@schema.parametrize()
def test_api_endpoints(case):
    response = case.call()
    case.validate_response(response)
