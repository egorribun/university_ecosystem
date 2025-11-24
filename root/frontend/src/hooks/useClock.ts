import { useState, useEffect } from "react";
import { pad } from "@/utils/scheduleUtils";

const getCurrentMinute = () => {
    const d = new Date();
    d.setSeconds(0, 0);
    return d;
};

export function useClock(locale: string) {
    const [time, setTime] = useState(getCurrentMinute);

    useEffect(() => {
        const tick = () => setTime(getCurrentMinute());
        let intervalId: number | null = null;
        const now = new Date();
        const msUntilNextMinute =
            (60 - now.getSeconds()) * 1000 - now.getMilliseconds();
        const timeoutId = window.setTimeout(() => {
            tick();
            intervalId = window.setInterval(tick, 60_000);
        }, msUntilNextMinute);
        return () => {
            window.clearTimeout(timeoutId);
            if (intervalId) {
                window.clearInterval(intervalId);
            }
        };
    }, []);

    const hh = pad(time.getHours());
    const mm = pad(time.getMinutes());
    const dateStr = time.toLocaleDateString(locale, {
        weekday: "long",
        day: "numeric",
        month: "long",
    });
    return { hh, mm, dateStr, time };
}
