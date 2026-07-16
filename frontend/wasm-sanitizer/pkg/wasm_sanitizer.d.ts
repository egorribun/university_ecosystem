export function sanitize_rich_text(html: string): string;
export function sanitize_html_basic(html: string): string;
export function strip_html(html: string): string;
export function sanitize_rich_text_raw(ptr: number, len: number): string;
export function initSync(dict: any): void;
export default function init(module_or_path?: any): Promise<any>;
