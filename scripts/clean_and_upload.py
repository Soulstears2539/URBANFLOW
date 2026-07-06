import sys
from pathlib import Path
import io
import requests
import pandas as pd

SERVER = "http://127.0.0.1:5052"

HELP = "Usage: python scripts/clean_and_upload.py <path_to_file> [reemplazar]"


def load_file(path: Path) -> pd.DataFrame:
    ext = path.suffix.lower()
    if ext in {".xlsx", ".xls"}:
        try:
            # prefer openpyxl for xlsx
            if ext == ".xlsx":
                return pd.read_excel(path, dtype=str, engine="openpyxl")
            return pd.read_excel(path, dtype=str)
        except Exception:
            # try reading as HTML table (some .xls are HTML)
            try:
                tables = pd.read_html(path)
                if tables:
                    return tables[0].astype(str)
            except Exception:
                pass
            # fallback to csv-like read
            return pd.read_csv(path, dtype=str)
    else:
        return pd.read_csv(path, dtype=str)


def normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    cols = [str(c).strip() for c in df.columns]
    cols = [c.lower().replace(" ", "_") for c in cols]
    df.columns = cols
    return df


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df = normalize_columns(df)

    # required columns
    if not any(c in df.columns for c in ["cooperativa"]) or not any(c in df.columns for c in ["linea"]):
        raise ValueError("El archivo no contiene columnas 'cooperativa' y/o 'linea'.")

    # forward-fill typical merged-cell pattern
    df["cooperativa"] = df["cooperativa"].fillna("")
    df["linea"] = df["linea"].fillna("")
    df["cooperativa"] = df["cooperativa"].replace("", pd.NA).ffill().fillna("")
    df["linea"] = df["linea"].replace("", pd.NA).ffill().fillna("")

    # Drop rows missing cooperativa or linea after ffill
    before = len(df)
    df = df[df["cooperativa"].astype(str).str.strip().astype(bool) & df["linea"].astype(str).str.strip().astype(bool)]
    after = len(df)

    # Ensure parada_ columns exist (at least parada_1 and parada_2 or generic 'parada')
    parada_cols = [c for c in df.columns if c.startswith("parada_")]
    if not parada_cols and "parada" not in df.columns:
        raise ValueError("No se encuentran columnas de paradas (parada_1, parada_2, ... o 'parada').")

    print(f"Filas: antes={before} -> despues={after} (eliminadas={before-after})")
    return df


def to_excel_bytes(df: pd.DataFrame) -> bytes:
    # Prefer CSV for backend parsing reliability
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def upload_bytes(bts: bytes, filename: str, reemplazar: bool = False):
    url = f"{SERVER}/api/transport/matrix/import"
    files = {"file": (filename, io.BytesIO(bts))}
    data = {"reemplazar": "1" if reemplazar else "0"}
    print(f"Subiendo {filename} a {url} (reemplazar={reemplazar})")
    r = requests.post(url, files=files, data=data, timeout=600)
    print(r.status_code)
    try:
        print(r.json())
    except Exception:
        print(r.text)
    return r


def main():
    if len(sys.argv) < 2:
        print(HELP)
        sys.exit(1)
    path = Path(sys.argv[1])
    if not path.exists():
        print(f"No existe archivo: {path}")
        sys.exit(2)
    reemplazar = len(sys.argv) > 2 and sys.argv[2].lower() in ("1", "true", "yes", "on")
    try:
        df = load_file(path)
    except Exception as e:
        print(f"Error leyendo archivo: {e}")
        sys.exit(3)
    try:
        clean = clean_dataframe(df)
    except Exception as e:
        print(f"Error limpiando archivo: {e}")
        sys.exit(4)
    bts = to_excel_bytes(clean)
    # upload as CSV
    upload_bytes(bts, f"cleaned_{path.stem}.csv", reemplazar=reemplazar)


if __name__ == "__main__":
    main()
