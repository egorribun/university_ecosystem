#![no_main]

use libfuzzer_sys::fuzz_target;
use hmac::{Hmac, Mac};
use sha2::Sha256;

fn verify_audit_signature_fuzz(signing_keys: Vec<String>, log_data: &str, signature: &str) -> bool {
    let sig_bytes = match hex::decode(signature) {
        Ok(b) => b,
        Err(_) => return false,
    };

    for key_str in signing_keys {
        let mut mac = match Hmac::<Sha256>::new_from_slice(key_str.as_bytes()) {
            Ok(m) => m,
            Err(_) => continue,
        };
        mac.update(log_data.as_bytes());
        if mac.verify_slice(&sig_bytes).is_ok() {
            return true;
        }
    }
    false
}

fuzz_target!(|data: &[u8]| {
    if data.len() < 4 {
        return;
    }
    // split data into a key, log_data, and signature
    let key_len = data[0] as usize;
    let sig_len = data[1] as usize;
    if 2 + key_len + sig_len > data.len() {
        return;
    }
    
    if let Ok(key) = std::str::from_utf8(&data[2..2 + key_len]) {
        let sig_start = 2 + key_len;
        if let Ok(sig) = std::str::from_utf8(&data[sig_start..sig_start + sig_len]) {
            let log_data_start = sig_start + sig_len;
            if let Ok(log_data) = std::str::from_utf8(&data[log_data_start..]) {
                let _ = verify_audit_signature_fuzz(vec![key.to_string()], log_data, sig);
            }
        }
    }
});
