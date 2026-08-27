use hmac::{Hmac, Mac};
use pbkdf2::pbkdf2_hmac;
use scrypt::{scrypt, Params as ScryptParams};
use sha2::Sha256;
use wasm_bindgen::prelude::*;

type HmacSha256 = Hmac<Sha256>;

#[wasm_bindgen]
pub fn pbkdf2_derive(password: &str, salt: &str, iterations: u32, key_size: usize) -> String {
    let mut res = vec![0u8; key_size];
    pbkdf2_hmac::<Sha256>(password.as_bytes(), salt.as_bytes(), iterations, &mut res);
    hex::encode(res)
}

#[wasm_bindgen]
pub fn hmac_sha256_sign(key: &str, message: &str) -> String {
    let mut mac = HmacSha256::new_from_slice(key.as_bytes())
        .expect("HMAC-SHA256 accepts arbitrary-length keys");
    mac.update(message.as_bytes());
    let result = mac.finalize();
    hex::encode(result.into_bytes())
}

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
    let mut res = vec![0u8; dk_len];
    fill_scrypt_output(password, salt, &params, &mut res).map(|_| res)
}

// Keep private-helper coverage in a dedicated test-only module. Its fixtures
// are generated at runtime, so the production crypto implementation contains
// no hard-coded key, password, salt, or digest material.
#[cfg(test)]
mod tests;
