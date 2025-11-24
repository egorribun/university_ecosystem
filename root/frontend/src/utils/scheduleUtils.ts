export const pad = (n: number) => String(n).padStart(2, "0");

export const fmtTime = (s?: string) =>
    !s ? "" : s.length >= 16 && s[10] === "T" ? s.slice(11, 16) : s.slice(0, 5);

export const nowParity = () => {
    const onejan = new Date(new Date().getFullYear(), 0, 1);
    const week = Math.ceil(
        ((+new Date() - +onejan) / 86400000 + onejan.getDay() + 1) / 7
    );
    return week % 2 === 0 ? "even" : "odd";
};

export const parseMinutes = (s?: string) => {
    if (!s) return null;
    const hhmm = s.length >= 16 && s[10] === "T" ? s.slice(11, 16) : s.slice(0, 5);
    const [hh, mm] = hhmm.split(":").map(Number);
    if (Number.isNaN(hh) || Number.isNaN(mm)) return null;
    return hh * 60 + mm;
};
