export const startOfDay = (d: Date) => {
    const x = new Date(d);
    x.setHours(0, 0, 0, 0);
    return x;
};

export const endOfDay = (d: Date) => {
    const x = new Date(d);
    x.setHours(23, 59, 59, 999);
    return x;
};

export const parseLocalDate = (s?: string) => {
    if (!s) return null;
    const norm = s.replace(" ", "T");
    const d = new Date(norm);
    if (!Number.isNaN(+d)) return d;
    const [datePart, timePart = "00:00"] = s.split(/[T ]/);
    const [Y, M, D] = (datePart || "").split("-").map(Number);
    const [h, m] = (timePart || "").split(":").map(Number);
    return new Date(Y || 1970, (M || 1) - 1, D || 1, h || 0, m || 0);
};
