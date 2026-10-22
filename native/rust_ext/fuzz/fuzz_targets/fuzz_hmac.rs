#![no_main]

use arbitrary::Arbitrary;
use libfuzzer_sys::fuzz_target;

#[derive(Arbitrary, Debug)]
struct FuzzInput {
    keys: Vec<String>,
    log_data: String,
    signature: String,
}

// Drives the production audit-signature verifier: it must never panic and must
// report malformed hex or empty key material as a verdict or error, not a crash.
fuzz_target!(|input: FuzzInput| {
    let _ = rust_ext::verify_audit_signature(input.keys, input.log_data, input.signature);
});
