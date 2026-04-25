# ADR-014: Selection of Hypothesis for Property-Based Testing

## Status
Accepted

## Context
As the university ecosystem backend grows in complexity, ensuring the robustness of our data validation, serialization, and core algorithms requires testing a vast array of inputs. Traditional example-based testing (using fixed `pytest.mark.parametrize` datasets) is insufficient for catching edge cases, unexpected nulls, or unicode encoding issues. We needed a property-based testing framework for Python.

The primary candidates were:
1. **[Hypothesis](https://hypothesis.works/)**: The industry-standard property-based testing library for Python.
2. **[Schemathesis](https://schemathesis.readthedocs.io/)**: A tool specifically designed to generate test cases from OpenAPI/GraphQL schemas.

## Decision
We decided to adopt **Hypothesis** as our primary property-based testing framework.

## Rationale
1. **Scope and Flexibility**: While Schemathesis excels at API contract validation by reading OpenAPI specs, it is tightly coupled to the HTTP layer. Hypothesis allows us to test *internal* components: utility functions (e.g., `levenshtein`, `slugify`), Pydantic models, custom parsers, and stateful algorithms, independent of the HTTP interface.
2. **Pydantic Integration**: Hypothesis provides excellent first-class support for Pydantic (and dataclasses). We can generate complex, nested data structures automatically from our Pydantic schema types, which is crucial for unit testing our business logic and repository layers without involving the FastAPI routing layer.
3. **Stateful Testing**: Hypothesis supports stateful (rule-based) testing out of the box, allowing us to model complex lifecycles (like the MFA enrollment and session invalidation state machine) and search for invariant violations over a sequence of operations.
4. **Shrinking Strategy**: Hypothesis features a robust shrinking engine that reduces complex failing test cases down to the simplest possible reproducible counterexample, making debugging significantly faster.

Schemathesis may be adopted in the future *in addition* to Hypothesis, specifically for black-box API testing against the live OpenAPI spec, but it cannot replace Hypothesis for unit and integration testing.

## Consequences
- Developers need to learn Hypothesis strategies (e.g., `st.integers()`, `st.text()`) and the `@given` decorator.
- Property-based tests can be slower than example-based tests. To mitigate this in CI, we use Hypothesis profiles to restrict the number of examples (`max_examples`) during routine pull request checks, while running a more exhaustive suite on `main` branch merges.
- We have gained significant confidence in our data validation logic, uncovering several edge cases related to Unicode handling and timezone-aware datetimes.
