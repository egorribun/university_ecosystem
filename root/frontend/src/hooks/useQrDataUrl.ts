import { useEffect, useState } from "react";
import type { QRCodeToDataURLOptions } from "qrcode";

let qrModulePromise: Promise<typeof import("qrcode")> | null = null;

const loadQrModule = async (): Promise<typeof import("qrcode")> => {
  if (!qrModulePromise) {
    qrModulePromise = import("qrcode")
      .then((mod) => mod.default ?? (mod as unknown as typeof import("qrcode")))
      .catch((error) => {
        qrModulePromise = null;
        throw error;
      });
  }
  return qrModulePromise;
};

export const useQrDataUrl = (value: string, size = 160) => {
  const [url, setUrl] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    let active = true;
    const generate = async () => {
      if (!value) {
        if (active) {
          setUrl(null);
          setLoading(false);
        }
        return;
      }
      setLoading(true);
      try {
        const qr = await loadQrModule();
        const options: QRCodeToDataURLOptions = {
          errorCorrectionLevel: "M",
          margin: 0,
          scale: 6,
          width: size,
        };
        const dataUrl = await qr.toDataURL(value, options);
        if (active) {
          setUrl(dataUrl);
        }
      } catch {
        if (active) {
          setUrl(null);
        }
      } finally {
        if (active) {
          setLoading(false);
        }
      }
    };
    generate();
    return () => {
      active = false;
    };
  }, [size, value]);

  return { url, loading } as const;
};
