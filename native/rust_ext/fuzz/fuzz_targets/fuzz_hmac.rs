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

    // 1. Existing verification fuzzing logic
    let key_len = data[0] as usize;
    let sig_len = data[1] as usize;
    if 2 + key_len + sig_len <= data.len() {
        if let Ok(key) = std::str::from_utf8(&data[2..2 + key_len]) {
            let sig_start = 2 + key_len;
            if let Ok(sig) = std::str::from_utf8(&data[sig_start..sig_start + sig_len]) {
                let log_data_start = sig_start + sig_len;
                if let Ok(log_data) = std::str::from_utf8(&data[log_data_start..]) {
                    let _ = verify_audit_signature_fuzz(vec![key.to_string()], log_data, sig);
                }
            }
        }
    }

    // 2. Fuzz HMAC sign and verification parity
    // Use part of fuzz input as key, and part as message.
    let half = data.len() / 2;
    let key_bytes = &data[..half];
    let msg_bytes = &data[half..];

    if let (Ok(key), Ok(msg)) = (std::str::from_utf8(key_bytes), std::str::from_utf8(msg_bytes)) {
        let mut mac = match Hmac::<Sha256>::new_from_slice(key.as_bytes()) {
            Ok(m) => m,
            Err(_) => return,
        };
        mac.update(msg.as_bytes());
        let signature_bytes = mac.finalize().into_bytes();
        let sig_hex = hex::encode(&signature_bytes);

        // It must verify successfully with the correct key and message
        assert!(verify_audit_signature_fuzz(vec![key.to_string()], msg, &sig_hex));

        // It must NOT verify if the message is modified (if it's not empty)
        if !msg.is_empty() {
            let modified_msg = format!("{}x", msg);
            assert!(!verify_audit_signature_fuzz(vec![key.to_string()], &modified_msg, &sig_hex));
        }

        // It must NOT verify if the key is modified (if it's not empty)
        if !key.is_empty() {
            let modified_key = format!("{}x", key);
            assert!(!verify_audit_signature_fuzz(vec![modified_key], msg, &sig_hex));
        }
    }
});
