export default function init(): Promise<void>;
export function pbkdf2_derive(password: string, salt: string, iterations: number, keyLen: number): string;
export function scrypt_derive(password: string, salt: string, n: number, r: number, p: number, keyLen: number): Uint8Array;
export function hmac_sha256_sign(key: string, message: string): string;
