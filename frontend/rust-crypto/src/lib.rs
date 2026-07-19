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
    let mut mac =
        HmacSha256::new_from_slice(key.as_bytes()).expect("HMAC can take key of any size");
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
    scrypt(password, salt, &params, &mut res)
        .map_err(|e| make_err(&format!("Scrypt failed: {:?}", e)))?;
    Ok(res)
}

#[cfg(test)]
mod tests {
    use super::scrypt_derive;

    #[test]
    fn scrypt_rejects_zero_cost_without_panicking() {
        assert!(scrypt_derive(b"password", b"salt", 0, 8, 1, 64).is_err());
    }

    #[test]
    fn scrypt_rejects_non_power_of_two_cost() {
        assert!(scrypt_derive(b"password", b"salt", 3, 8, 1, 64).is_err());
    }
}
