import json
import os
import math
import pandas as pd

INPUT_FILE = r"static\data\DIVIPOLA_Municipios.xlsx"
OUTPUT_FILE = r"static\data\colombia_city_coords.json"


def parse_coord(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None

    text = str(value).strip().replace(",", ".")
    try:
        return float(text)
    except ValueError:
        return None


def clean_text(value):
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    return str(value).strip()


def main():
    print("Buscando archivo en:", os.path.abspath(INPUT_FILE))

    if not os.path.exists(INPUT_FILE):
        raise FileNotFoundError(f"No encontré el archivo en: {os.path.abspath(INPUT_FILE)}")

    # ✅ Hoja exacta que muestras en la captura
    # ✅ Saltamos las primeras 11 filas visuales
    # ✅ Leemos columnas A:H por posición
    df = pd.read_excel(
        INPUT_FILE,
        sheet_name="Municipios",
        header=None,
        skiprows=11,
        usecols="A:H"
    )

    # Renombrar columnas manualmente
    df.columns = [
        "codigo_departamento",
        "departamento",
        "codigo_municipio",
        "municipio",
        "tipo",
        "longitud",
        "latitud",
        "nota"
    ]

    result = {}

    for _, row in df.iterrows():
        departamento = clean_text(row["departamento"])
        municipio = clean_text(row["municipio"])
        lat = parse_coord(row["latitud"])
        lng = parse_coord(row["longitud"])
        tipo = clean_text(row["tipo"]).lower()

        # Solo municipios reales
        if tipo != "municipio":
            continue

        if not departamento or not municipio or lat is None or lng is None:
            continue

        if departamento not in result:
            result[departamento] = {}

        result[departamento][municipio] = {
            "lat": lat,
            "lng": lng
        }

    os.makedirs(os.path.dirname(OUTPUT_FILE), exist_ok=True)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    total_departamentos = len(result)
    total_municipios = sum(len(v) for v in result.values())

    print(f"Archivo generado: {OUTPUT_FILE}")
    print(f"Departamentos: {total_departamentos}")
    print(f"Municipios: {total_municipios}")


if __name__ == "__main__":
    main()