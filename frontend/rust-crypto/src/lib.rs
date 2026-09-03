use hmac::{Hmac, Mac};
use pbkdf2::pbkdf2_hmac;
use scrypt::{scrypt, Params as ScryptParams};
use sha2::Sha256;
use wasm_bindgen::prelude::*;
use zeroize::Zeroizing;

type HmacSha256 = Hmac<Sha256>;

#[cfg(target_arch = "wasm32")]
type ErrorType = JsValue;

#[cfg(not(target_arch = "wasm32"))]
type ErrorType = String;

#[cfg(target_arch = "wasm32")]
fn make_err(msg: &str) -> JsValue {
    JsValue::from_str(msg)
}

#[cfg(not(target_arch = "wasm32"))]
fn make_err(msg: &str) -> String {
    msg.to_string()
}

const MIN_PBKDF2_ITERATIONS: u32 = 1;
const MAX_PBKDF2_ITERATIONS: u32 = 1_000_000;
const MIN_PBKDF2_KEY_SIZE: usize = 1;
const MAX_PBKDF2_KEY_SIZE: usize = 1_024;

#[wasm_bindgen]
pub fn pbkdf2_derive(
    password: &str,
    salt: &str,
    iterations: u32,
    key_size: usize,
) -> Result<String, ErrorType> {
    if !(MIN_PBKDF2_ITERATIONS..=MAX_PBKDF2_ITERATIONS).contains(&iterations) {
        return Err(make_err(
            "PBKDF2 iterations must be between 1 and 1,000,000",
        ));
    }
    if !(MIN_PBKDF2_KEY_SIZE..=MAX_PBKDF2_KEY_SIZE).contains(&key_size) {
        return Err(make_err(
            "PBKDF2 key size must be between 1 and 1,024 bytes",
        ));
    }

    // Copy caller-provided secrets into zeroizing buffers so temporary Rust
    // allocations are cleared as soon as this operation returns.
    let password_bytes = Zeroizing::new(password.as_bytes().to_vec());
    let salt_bytes = Zeroizing::new(salt.as_bytes().to_vec());
    let mut result = Zeroizing::new(vec![0_u8; key_size]);
    pbkdf2_hmac::<Sha256>(
        password_bytes.as_slice(),
        salt_bytes.as_slice(),
        iterations,
        result.as_mut_slice(),
    );

    Ok(hex::encode(result.as_slice()))
}

#[wasm_bindgen]
pub fn hmac_sha256_sign(key: &str, message: &str) -> String {
    let key_bytes = Zeroizing::new(key.as_bytes().to_vec());
    let message_bytes = Zeroizing::new(message.as_bytes().to_vec());
    let mut mac = HmacSha256::new_from_slice(key_bytes.as_slice())
        .expect("HMAC-SHA256 accepts arbitrary-length keys");
    mac.update(message_bytes.as_slice());
    let mut digest = mac.finalize().into_bytes();
    // Keep the heap-owned digest under a zeroizing guard for its entire
    // lifetime.  The short GenericArray returned by ``finalize`` is copied
    // immediately and never retained beyond this scope.
    let result = Zeroizing::new(digest.to_vec());
    for byte in &mut digest {
        *byte = 0;
    }
    hex::encode(result.as_slice())
}

fn fill_scrypt_output(
    password: &[u8],
    salt: &[u8],
    params: &ScryptParams,
    output: &mut [u8],
) -> Result<(), ErrorType> {
    scrypt(password, salt, params, output).map_err(|e| make_err(&format!("Scrypt failed: {:?}", e)))
}

#[wasm_bindgen]
pub fn scrypt_derive(
    password: &[u8],
    salt: &[u8],
    n: u32,
    r: u32,
    p: u32,
    dk_len: usize,
) -> Result<Vec<u8>, ErrorType> {
    let log_n = n
        .checked_ilog2()
        .filter(|_| n.is_power_of_two())
        .ok_or_else(|| make_err("Invalid scrypt params: N must be a non-zero power of two"))?;
    let params = ScryptParams::new(log_n as u8, r, p, dk_len)
        .map_err(|e| make_err(&format!("Invalid scrypt params: {:?}", e)))?;
    let password_bytes = Zeroizing::new(password.to_vec());
    let salt_bytes = Zeroizing::new(salt.to_vec());
    let mut result = Zeroizing::new(vec![0_u8; dk_len]);
    fill_scrypt_output(
        password_bytes.as_slice(),
        salt_bytes.as_slice(),
        &params,
        result.as_mut_slice(),
    )?;
    Ok(result.to_vec())
}

// Keep private-helper coverage in a dedicated test-only module. Its fixtures
// are generated at runtime, so the production crypto implementation contains
// no hard-coded key, password, salt, or digest material.
#[cfg(test)]
mod tests;
